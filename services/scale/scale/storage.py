import json
import base64
import hashlib
import hmac
import threading
import time
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Protocol
from uuid import UUID, uuid4

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
import httpx

from .schemas import AnalysisCreate, AnalysisStatus, TwinCreate


def now() -> datetime:
    return datetime.now(timezone.utc)


class Repository(Protocol):
    def create_analysis(self, request: AnalysisCreate) -> dict[str, Any]: ...
    def get_analysis(self, analysis_id: UUID) -> dict[str, Any] | None: ...
    def claim_analysis(self) -> dict[str, Any] | None: ...
    def update_analysis(self, analysis_id: UUID, **changes: Any) -> None: ...
    def save_feedback(self, feedback: dict[str, Any]) -> UUID: ...
    def save_gps_trace(self, trace: dict[str, Any]) -> UUID: ...
    def list_gps_traces(self, analysis_id: UUID, target_id: str) -> list[dict[str, Any]]: ...
    def revoke_gps_trace(self, trace_id: UUID) -> dict[str, Any] | None: ...
    def save_layers(self, analysis_id: UUID, layers: dict[str, Any]) -> None: ...
    def get_layer(self, analysis_id: UUID, layer_name: str) -> dict[str, Any] | None: ...
    def get_layers(self, analysis_id: UUID) -> dict[str, Any]: ...
    def create_twin(self, request: TwinCreate) -> dict[str, Any]: ...
    def get_twin(self, twin_id: UUID) -> dict[str, Any] | None: ...
    def claim_twin(self) -> dict[str, Any] | None: ...
    def update_twin(self, twin_id: UUID, **changes: Any) -> None: ...


class MemoryRepository:
    def __init__(self) -> None:
        self.items: dict[UUID, dict[str, Any]] = {}
        self.feedback: dict[UUID, dict[str, Any]] = {}
        self.gps_traces: dict[UUID, dict[str, Any]] = {}
        self.layers: dict[tuple[UUID, str], dict[str, Any]] = {}
        self.twins: dict[UUID, dict[str, Any]] = {}
        self.lock = threading.Lock()

    def create_analysis(self, request: AnalysisCreate) -> dict[str, Any]:
        analysis_id = uuid4()
        stamp = now()
        item = {
            "analysis_id": analysis_id,
            "request": request.model_dump(mode="json"),
            "status": AnalysisStatus.queued.value,
            "stage": "waiting_for_worker",
            "progress": 0,
            "created_at": stamp,
            "updated_at": stamp,
            "error": None,
            "result": None,
        }
        with self.lock:
            self.items[analysis_id] = item
        return deepcopy(item)

    def get_analysis(self, analysis_id: UUID) -> dict[str, Any] | None:
        with self.lock:
            item = self.items.get(analysis_id)
            return deepcopy(item) if item else None

    def claim_analysis(self) -> dict[str, Any] | None:
        with self.lock:
            queued = next(
                (item for item in self.items.values() if item["status"] == AnalysisStatus.queued.value),
                None,
            )
            if queued is None:
                return None
            queued["status"] = AnalysisStatus.acquiring.value
            queued["stage"] = "acquiring_sources"
            queued["progress"] = 5
            queued["updated_at"] = now()
            return deepcopy(queued)

    def update_analysis(self, analysis_id: UUID, **changes: Any) -> None:
        with self.lock:
            self.items[analysis_id].update(changes, updated_at=now())

    def save_feedback(self, feedback: dict[str, Any]) -> UUID:
        feedback_id = uuid4()
        with self.lock:
            self.feedback[feedback_id] = {**feedback, "feedback_id": feedback_id}
        return feedback_id

    def save_gps_trace(self, trace: dict[str, Any]) -> UUID:
        trace_id = uuid4()
        self.gps_traces[trace_id] = {**deepcopy(trace), "trace_id": trace_id, "revoked_at": None}
        return trace_id

    def list_gps_traces(self, analysis_id: UUID, target_id: str) -> list[dict[str, Any]]:
        return [deepcopy(item) for item in self.gps_traces.values()
                if item["analysis_id"] == analysis_id and item["target_id"] == target_id
                and item.get("revoked_at") is None]

    def revoke_gps_trace(self, trace_id: UUID) -> dict[str, Any] | None:
        item = self.gps_traces.get(trace_id)
        if item:
            item["revoked_at"] = now()
            return deepcopy(item)
        return None

    def save_layers(self, analysis_id: UUID, layers: dict[str, Any]) -> None:
        for name, payload in layers.items():
            self.layers[(analysis_id, name)] = deepcopy(payload)

    def get_layer(self, analysis_id: UUID, layer_name: str) -> dict[str, Any] | None:
        value = self.layers.get((analysis_id, layer_name))
        return deepcopy(value) if value else None

    def get_layers(self, analysis_id: UUID) -> dict[str, Any]:
        return {name: deepcopy(value) for (owner, name), value in self.layers.items()
                if owner == analysis_id}

    def create_twin(self, request: TwinCreate) -> dict[str, Any]:
        twin_id, stamp = uuid4(), now()
        item = {"twin_id": twin_id, "analysis_id": request.analysis_id,
                "request": request.model_dump(mode="json"), "status": "queued",
                "stage": "waiting_for_worker", "progress": 0, "created_at": stamp,
                "updated_at": stamp, "error": None, "result": None}
        with self.lock:
            self.twins[twin_id] = item
        return deepcopy(item)

    def get_twin(self, twin_id: UUID) -> dict[str, Any] | None:
        with self.lock:
            item = self.twins.get(twin_id)
            return deepcopy(item) if item else None

    def claim_twin(self) -> dict[str, Any] | None:
        with self.lock:
            item = next((value for value in self.twins.values() if value["status"] == "queued"), None)
            if item:
                item.update(status="acquiring", stage="resolving_route", progress=5, updated_at=now())
            return deepcopy(item) if item else None

    def update_twin(self, twin_id: UUID, **changes: Any) -> None:
        with self.lock:
            self.twins[twin_id].update(changes, updated_at=now())


class PostgresRepository:
    def __init__(self, database_url: str) -> None:
        self.pool = ConnectionPool(database_url, kwargs={"row_factory": dict_row})

    def create_analysis(self, request: AnalysisCreate) -> dict[str, Any]:
        analysis_id = uuid4()
        with self.pool.connection() as connection:
            row = connection.execute(
                """
                INSERT INTO scale.analyses (id, request, status, stage, progress)
                VALUES (%s, %s::jsonb, 'queued', 'waiting_for_worker', 0)
                RETURNING id AS analysis_id, request, status, stage, progress,
                          created_at, updated_at, error, result
                """,
                (analysis_id, json.dumps(request.model_dump(mode="json"))),
            ).fetchone()
        return row

    def get_analysis(self, analysis_id: UUID) -> dict[str, Any] | None:
        with self.pool.connection() as connection:
            return connection.execute(
                """
                SELECT id AS analysis_id, request, status, stage, progress,
                       created_at, updated_at, error, result
                FROM scale.analyses WHERE id = %s
                """,
                (analysis_id,),
            ).fetchone()

    def claim_analysis(self) -> dict[str, Any] | None:
        with self.pool.connection() as connection:
            with connection.transaction():
                return connection.execute(
                    """
                    WITH candidate AS (
                      SELECT id FROM scale.analyses
                      WHERE status = 'queued' ORDER BY created_at
                      FOR UPDATE SKIP LOCKED LIMIT 1
                    )
                    UPDATE scale.analyses a
                    SET status = 'acquiring', stage = 'acquiring_sources',
                        progress = 5, updated_at = now()
                    FROM candidate WHERE a.id = candidate.id
                    RETURNING a.id AS analysis_id, a.request, a.status, a.stage,
                              a.progress, a.created_at, a.updated_at, a.error, a.result
                    """
                ).fetchone()

    def update_analysis(self, analysis_id: UUID, **changes: Any) -> None:
        allowed = {"status", "stage", "progress", "error", "result"}
        updates = {key: value for key, value in changes.items() if key in allowed}
        assignments, values = [], []
        for key, value in updates.items():
            if key in {"error", "result"}:
                assignments.append(f"{key} = %s::jsonb")
                values.append(json.dumps(value) if value is not None else None)
            else:
                assignments.append(f"{key} = %s")
                values.append(value)
        assignments.append("updated_at = now()")
        values.append(analysis_id)
        with self.pool.connection() as connection:
            connection.execute(
                f"UPDATE scale.analyses SET {', '.join(assignments)} WHERE id = %s",
                values,
            )

    def save_feedback(self, feedback: dict[str, Any]) -> UUID:
        feedback_id = uuid4()
        with self.pool.connection() as connection:
            connection.execute(
                """
                INSERT INTO scale.feedback
                  (id, analysis_id, segment_id, target_type, target_id, payload, visibility, observed_at)
                VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s)
                """,
                (
                    feedback_id,
                    feedback["analysis_id"],
                    feedback["segment_id"],
                    feedback["target_type"], feedback["target_id"],
                    json.dumps(feedback, default=str),
                    feedback["visibility"],
                    feedback["observed_at"],
                ),
            )
        return feedback_id

    def save_gps_trace(self, trace: dict[str, Any]) -> UUID:
        trace_id = uuid4()
        with self.pool.connection() as connection:
            connection.execute("""
                INSERT INTO scale.gps_traces
                  (id, analysis_id, target_type, target_id, geometry, observed_at, observer_id,
                   visibility, mean_distance_m, coverage, verification_state)
                VALUES (%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s,%s)
            """, (trace_id, trace["analysis_id"], trace["target_type"], trace["target_id"],
                  json.dumps(trace["geometry"]), trace["observed_at"], trace.get("observer_id"),
                  trace["visibility"], trace.get("mean_distance_m"), trace["coverage"],
                  trace["verification_state"]))
        return trace_id

    def list_gps_traces(self, analysis_id: UUID, target_id: str) -> list[dict[str, Any]]:
        with self.pool.connection() as connection:
            return connection.execute("""
                SELECT * FROM scale.gps_traces
                WHERE analysis_id=%s AND target_id=%s AND revoked_at IS NULL ORDER BY created_at
            """, (analysis_id, target_id)).fetchall()

    def revoke_gps_trace(self, trace_id: UUID) -> dict[str, Any] | None:
        with self.pool.connection() as connection:
            return connection.execute("""
                UPDATE scale.gps_traces SET revoked_at=now() WHERE id=%s AND revoked_at IS NULL
                RETURNING *
            """, (trace_id,)).fetchone()

    def save_layers(self, analysis_id: UUID, layers: dict[str, Any]) -> None:
        with self.pool.connection() as connection:
            for name, payload in layers.items():
                connection.execute("""
                    INSERT INTO scale.analysis_layers(analysis_id,layer_name,payload,feature_count)
                    VALUES (%s,%s,%s::jsonb,%s)
                    ON CONFLICT(analysis_id,layer_name) DO UPDATE
                    SET payload=excluded.payload,feature_count=excluded.feature_count,updated_at=now()
                """, (analysis_id, name, json.dumps(payload), len(payload.get("features", []))))

    def get_layer(self, analysis_id: UUID, layer_name: str) -> dict[str, Any] | None:
        with self.pool.connection() as connection:
            row = connection.execute("SELECT payload FROM scale.analysis_layers WHERE analysis_id=%s AND layer_name=%s",
                                     (analysis_id, layer_name)).fetchone()
        return row["payload"] if row else None

    def get_layers(self, analysis_id: UUID) -> dict[str, Any]:
        with self.pool.connection() as connection:
            rows = connection.execute("SELECT layer_name,payload FROM scale.analysis_layers WHERE analysis_id=%s",
                                      (analysis_id,)).fetchall()
        return {row["layer_name"]: row["payload"] for row in rows}

    def create_twin(self, request: TwinCreate) -> dict[str, Any]:
        twin_id = uuid4()
        with self.pool.connection() as connection:
            return connection.execute("""
                INSERT INTO scale.trip_twins(id,analysis_id,request,status,stage,progress)
                VALUES (%s,%s,%s::jsonb,'queued','waiting_for_worker',0)
                RETURNING id AS twin_id,analysis_id,request,status,stage,progress,
                          created_at,updated_at,error,result
            """, (twin_id, request.analysis_id,
                    json.dumps(request.model_dump(mode="json")))).fetchone()

    def get_twin(self, twin_id: UUID) -> dict[str, Any] | None:
        with self.pool.connection() as connection:
            return connection.execute("""
                SELECT id AS twin_id,analysis_id,request,status,stage,progress,
                       created_at,updated_at,error,result
                FROM scale.trip_twins WHERE id=%s
            """, (twin_id,)).fetchone()

    def claim_twin(self) -> dict[str, Any] | None:
        with self.pool.connection() as connection:
            with connection.transaction():
                row = connection.execute("SELECT * FROM scale.claim_trip_twin()").fetchone()
                if row:
                    row["twin_id"] = row.pop("id")
                return row

    def update_twin(self, twin_id: UUID, **changes: Any) -> None:
        allowed = {"status", "stage", "progress", "error", "result"}
        updates = {key: value for key, value in changes.items() if key in allowed}
        assignments, values = [], []
        for key, value in updates.items():
            if key in {"error", "result"}:
                assignments.append(f"{key}=%s::jsonb")
                values.append(json.dumps(value) if value is not None else None)
            else:
                assignments.append(f"{key}=%s")
                values.append(value)
        assignments.append("updated_at=now()")
        values.append(twin_id)
        with self.pool.connection() as connection:
            connection.execute(f"UPDATE scale.trip_twins SET {', '.join(assignments)} WHERE id=%s", values)


class PostgrestRepository:
    def __init__(self, base_url: str, jwt_secret: str, role: str) -> None:
        if not jwt_secret:
            raise ValueError("SCALE_POSTGREST_JWT_SECRET is required for PostgREST")
        self.base_url = base_url.rstrip("/")
        self.jwt_secret = jwt_secret.encode()
        self.role = role
        self.client = httpx.Client(timeout=30)

    def _request_with_retry(
        self,
        method: str,
        url: str,
        *,
        attempts: int = 5,
        **kwargs: Any,
    ) -> httpx.Response:
        """Retry idempotent/upsert requests during brief gateway outages."""
        last_error: Exception | None = None
        for attempt in range(attempts):
            try:
                response = self.client.request(method, url, **kwargs)
                if response.status_code not in {429, 502, 503, 504}:
                    response.raise_for_status()
                    return response
                last_error = httpx.HTTPStatusError(
                    f"Transient PostgREST response {response.status_code}",
                    request=response.request,
                    response=response,
                )
            except (httpx.ConnectError, httpx.ReadError, httpx.RemoteProtocolError,
                    httpx.TimeoutException) as error:
                last_error = error
            if attempt + 1 < attempts:
                time.sleep(min(2 ** attempt, 8))
        assert last_error is not None
        raise last_error

    def _token(self) -> str:
        def encode(value: dict[str, Any]) -> str:
            raw = json.dumps(value, separators=(",", ":")).encode()
            return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

        header = encode({"alg": "HS256", "typ": "JWT"})
        payload = encode({"role": self.role, "exp": int(time.time()) + 300})
        signature = hmac.new(
            self.jwt_secret, f"{header}.{payload}".encode(), hashlib.sha256
        ).digest()
        encoded_signature = base64.urlsafe_b64encode(signature).rstrip(b"=").decode()
        return f"{header}.{payload}.{encoded_signature}"

    def _headers(self, prefer: str | None = None) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self._token()}",
            "Content-Type": "application/json",
        }
        if prefer:
            headers["Prefer"] = prefer
        return headers

    @staticmethod
    def _normalize(row: dict[str, Any]) -> dict[str, Any]:
        item = dict(row)
        item["analysis_id"] = item.pop("id")
        return item

    def create_analysis(self, request: AnalysisCreate) -> dict[str, Any]:
        analysis_id = uuid4()
        response = self.client.post(
            f"{self.base_url}/analyses",
            headers=self._headers("return=representation"),
            json={
                "id": str(analysis_id),
                "request": request.model_dump(mode="json"),
                "status": AnalysisStatus.queued.value,
                "stage": "waiting_for_worker",
                "progress": 0,
            },
        )
        response.raise_for_status()
        return self._normalize(response.json()[0])

    def get_analysis(self, analysis_id: UUID) -> dict[str, Any] | None:
        response = self._request_with_retry(
            "GET",
            f"{self.base_url}/analyses",
            headers=self._headers(),
            params={"id": f"eq.{analysis_id}", "limit": "1"},
        )
        rows = response.json()
        return self._normalize(rows[0]) if rows else None

    def claim_analysis(self) -> dict[str, Any] | None:
        response = self.client.post(
            f"{self.base_url}/rpc/claim_analysis",
            headers=self._headers(),
            json={},
        )
        response.raise_for_status()
        rows = response.json()
        return self._normalize(rows[0]) if rows else None

    def update_analysis(self, analysis_id: UUID, **changes: Any) -> None:
        allowed = {"status", "stage", "progress", "error", "result"}
        payload = {key: value for key, value in changes.items() if key in allowed}
        payload["updated_at"] = now().isoformat()
        self._request_with_retry(
            "PATCH",
            f"{self.base_url}/analyses",
            headers=self._headers(),
            params={"id": f"eq.{analysis_id}"},
            json=payload,
        )

    def save_feedback(self, feedback: dict[str, Any]) -> UUID:
        feedback_id = uuid4()
        response = self.client.post(
            f"{self.base_url}/feedback",
            headers=self._headers(),
            json={
                "id": str(feedback_id),
                "analysis_id": str(feedback["analysis_id"]),
                "segment_id": feedback["segment_id"],
                "target_type": feedback["target_type"],
                "target_id": feedback["target_id"],
                "payload": feedback,
                "visibility": feedback["visibility"],
                "observed_at": feedback["observed_at"],
            },
        )
        response.raise_for_status()
        return feedback_id

    def save_gps_trace(self, trace: dict[str, Any]) -> UUID:
        trace_id = uuid4()
        response = self.client.post(
            f"{self.base_url}/gps_traces", headers=self._headers(),
            json={**trace, "id": str(trace_id), "analysis_id": str(trace["analysis_id"]),
                  "observed_at": trace["observed_at"].isoformat()},
        )
        response.raise_for_status()
        return trace_id

    def list_gps_traces(self, analysis_id: UUID, target_id: str) -> list[dict[str, Any]]:
        response = self._request_with_retry(
            "GET",
            f"{self.base_url}/gps_traces", headers=self._headers(),
            params={"analysis_id": f"eq.{analysis_id}", "target_id": f"eq.{target_id}",
                    "revoked_at": "is.null", "order": "created_at.asc"},
        )
        return response.json()

    def revoke_gps_trace(self, trace_id: UUID) -> dict[str, Any] | None:
        response = self.client.patch(
            f"{self.base_url}/gps_traces", headers=self._headers("return=representation"),
            params={"id": f"eq.{trace_id}", "revoked_at": "is.null"},
            json={"revoked_at": now().isoformat()},
        )
        response.raise_for_status()
        rows = response.json()
        return rows[0] if rows else None

    def save_layers(self, analysis_id: UUID, layers: dict[str, Any]) -> None:
        for name, payload in layers.items():
            self._request_with_retry(
                "POST",
                f"{self.base_url}/analysis_layers",
                headers=self._headers("resolution=merge-duplicates"),
                params={"on_conflict": "analysis_id,layer_name"},
                json={"analysis_id": str(analysis_id), "layer_name": name, "payload": payload,
                      "feature_count": len(payload.get("features", [])),
                      "updated_at": now().isoformat()},
            )

    def get_layer(self, analysis_id: UUID, layer_name: str) -> dict[str, Any] | None:
        response = self._request_with_retry(
            "GET",
            f"{self.base_url}/analysis_layers", headers=self._headers(),
            params={"analysis_id": f"eq.{analysis_id}", "layer_name": f"eq.{layer_name}",
                    "select": "payload", "limit": "1"},
        )
        rows = response.json()
        return rows[0]["payload"] if rows else None

    def get_layers(self, analysis_id: UUID) -> dict[str, Any]:
        response = self._request_with_retry(
            "GET",
            f"{self.base_url}/analysis_layers", headers=self._headers(),
            params={"analysis_id": f"eq.{analysis_id}", "select": "layer_name,payload"},
        )
        return {row["layer_name"]: row["payload"] for row in response.json()}

    def create_twin(self, request: TwinCreate) -> dict[str, Any]:
        twin_id = uuid4()
        response = self.client.post(f"{self.base_url}/trip_twins",
            headers=self._headers("return=representation"), json={
                "id": str(twin_id), "analysis_id": str(request.analysis_id),
                "request": request.model_dump(mode="json"), "status": "queued",
                "stage": "waiting_for_worker", "progress": 0})
        response.raise_for_status()
        row = response.json()[0]
        row["twin_id"] = row.pop("id")
        return row

    def get_twin(self, twin_id: UUID) -> dict[str, Any] | None:
        response = self._request_with_retry("GET", f"{self.base_url}/trip_twins",
            headers=self._headers(), params={"id": f"eq.{twin_id}", "limit": "1"})
        rows = response.json()
        if not rows:
            return None
        rows[0]["twin_id"] = rows[0].pop("id")
        return rows[0]

    def claim_twin(self) -> dict[str, Any] | None:
        response = self.client.post(f"{self.base_url}/rpc/claim_trip_twin",
                                    headers=self._headers(), json={})
        response.raise_for_status()
        rows = response.json()
        if not rows:
            return None
        rows[0]["twin_id"] = rows[0].pop("id")
        return rows[0]

    def update_twin(self, twin_id: UUID, **changes: Any) -> None:
        allowed = {"status", "stage", "progress", "error", "result"}
        payload = {key: value for key, value in changes.items() if key in allowed}
        payload["updated_at"] = now().isoformat()
        self._request_with_retry("PATCH", f"{self.base_url}/trip_twins",
            headers=self._headers(), params={"id": f"eq.{twin_id}"}, json=payload)


def create_repository(
    database_url: str, jwt_secret: str = "", role: str = "anysite_app_rw"
) -> Repository:
    if database_url == "memory://":
        return MemoryRepository()
    if database_url.startswith(("http://", "https://")):
        return PostgrestRepository(database_url, jwt_secret, role)
    return PostgresRepository(database_url)
