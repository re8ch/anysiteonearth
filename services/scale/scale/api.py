from contextlib import asynccontextmanager
from threading import Event, Thread
from typing import Any
from uuid import UUID

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response

from .config import settings
from .geo import validate_bbox_size
from .schemas import (
    AnalysisAccepted,
    AnalysisCreate,
    AnalysisStatus,
    AnalysisView,
    FeedbackAccepted,
    FeedbackCreate,
    GpsTraceAccepted,
    GpsTraceCreate,
    ModelInfo,
    TwinAccepted,
    TwinCreate,
    TwinView,
)
from .tiles import TileRenderer
from .verification import (
    find_target, independent_support_count, layer_for_target, match_trace, recalculate_target,
    verification_state,
)
from .storage import Repository, create_repository
from .worker import run_worker

repository = create_repository(
    settings.database_url, settings.postgrest_jwt_secret, settings.postgrest_role
)
stop_worker = Event()
worker_thread: Thread | None = None
tile_renderer = TileRenderer(settings.stac_url, settings.cache_dir)


@asynccontextmanager
async def lifespan(_: FastAPI):
    global worker_thread
    if settings.embedded_worker:
        worker_thread = Thread(
            target=run_worker, args=(repository, settings, stop_worker), daemon=True
        )
        worker_thread.start()
    yield
    stop_worker.set()


app = FastAPI(title="Anysite Scale", version="1.3.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)


def get_repository() -> Repository:
    return repository


@app.exception_handler(ValueError)
async def value_error_handler(_: Request, error: ValueError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "code": "INVALID_REQUEST",
            "message": str(error),
            "retryable": False,
            "details": {},
        },
    )


@app.exception_handler(HTTPException)
async def http_error_handler(_: Request, error: HTTPException) -> JSONResponse:
    body = error.detail if isinstance(error.detail, dict) else {
        "code": "HTTP_ERROR",
        "message": str(error.detail),
        "retryable": False,
        "details": {},
    }
    return JSONResponse(status_code=error.status_code, content=body)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_: Request, error: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "code": "VALIDATION_ERROR",
            "message": "Request validation failed",
            "retryable": False,
            "details": {"errors": error.errors()},
        },
    )


@app.exception_handler(httpx.HTTPError)
async def upstream_storage_error_handler(_: Request, error: httpx.HTTPError) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "code": "STORAGE_TEMPORARILY_UNAVAILABLE",
            "message": str(error),
            "retryable": True,
            "details": {},
        },
    )


@app.get("/healthz")
def health() -> dict[str, str]:
    return {"status": "ok", "version": "1.3.0"}


@app.post("/v1/analyses", response_model=AnalysisAccepted, status_code=202)
def create_analysis(
    request: AnalysisCreate, storage: Repository = Depends(get_repository)
) -> AnalysisAccepted:
    validate_bbox_size(request.bbox, settings.max_aoi_side_km)
    item = storage.create_analysis(request)
    return AnalysisAccepted(
        analysis_id=item["analysis_id"],
        status=AnalysisStatus(item["status"]),
        stage=item["stage"],
    )


def require_analysis(analysis_id: UUID, storage: Repository) -> dict[str, Any]:
    item = storage.get_analysis(analysis_id)
    if item is None:
        raise HTTPException(
            404,
            detail={
                "code": "ANALYSIS_NOT_FOUND",
                "message": "Analysis does not exist",
                "retryable": False,
                "details": {},
            },
        )
    return item


def require_twin(twin_id: UUID, storage: Repository) -> dict[str, Any]:
    item = storage.get_twin(twin_id)
    if item is None:
        raise HTTPException(404, detail={"code": "TWIN_NOT_FOUND",
            "message": "Trip twin does not exist", "retryable": False, "details": {}})
    return item


@app.post("/v1/twins", response_model=TwinAccepted, status_code=202)
def create_twin(request: TwinCreate,
                storage: Repository = Depends(get_repository)) -> TwinAccepted:
    analysis = require_analysis(request.analysis_id, storage)
    if analysis["status"] != AnalysisStatus.completed.value:
        raise HTTPException(409, detail={"code": "TWIN_ANALYSIS_NOT_READY",
            "message": f"Source analysis is {analysis['status']}", "retryable": True,
            "details": {"analysis_id": str(request.analysis_id)}})
    item = storage.create_twin(request)
    return TwinAccepted(twin_id=item["twin_id"], status=AnalysisStatus(item["status"]),
                        stage=item["stage"])


@app.get("/v1/twins/{twin_id}", response_model=TwinView)
def get_twin(twin_id: UUID, storage: Repository = Depends(get_repository)) -> TwinView:
    item = require_twin(twin_id, storage)
    # Polling stays small; the scene manifest has its own result endpoint.
    return TwinView.model_validate({**item, "result": None})


@app.get("/v1/twins/{twin_id}/result")
def get_twin_result(twin_id: UUID,
                    storage: Repository = Depends(get_repository)) -> dict[str, Any]:
    item = require_twin(twin_id, storage)
    if item["status"] != AnalysisStatus.completed.value:
        raise HTTPException(409, detail={"code": "TWIN_NOT_READY",
            "message": f"Trip twin is {item['status']}",
            "retryable": item["status"] != AnalysisStatus.failed.value,
            "details": {"status": item["status"]}})
    return item["result"]


@app.get("/v1/twins/{twin_id}/assets/{asset_name}")
def get_twin_asset(twin_id: UUID, asset_name: str,
                   storage: Repository = Depends(get_repository)) -> FileResponse:
    item = require_twin(twin_id, storage)
    if item["status"] != AnalysisStatus.completed.value:
        raise HTTPException(409, detail={"code": "TWIN_NOT_READY",
            "message": f"Trip twin is {item['status']}", "retryable": True, "details": {}})
    allowed = asset_name == "scene.json" or (
        asset_name.startswith(("preview-720p-", "export-1080p-"))
        and asset_name.endswith(".mp4")
        and asset_name.removesuffix(".mp4").rsplit("-", 1)[-1] in {"aerial", "follow"})
    if not allowed:
        raise HTTPException(404, detail={"code": "TWIN_ASSET_NOT_FOUND",
            "message": "Twin asset does not exist", "retryable": False, "details": {}})
    path = settings.twin_asset_dir / str(twin_id) / asset_name
    if not path.exists():
        raise HTTPException(404, detail={"code": "TWIN_ASSET_NOT_FOUND",
            "message": "Twin asset is not available", "retryable": False, "details": {}})
    return FileResponse(path, media_type=("application/json" if asset_name == "scene.json"
                                          else "video/mp4"), filename=asset_name,
                        content_disposition_type=("attachment" if asset_name == "scene.json"
                                                  else "inline"))


@app.get("/v1/analyses/{analysis_id}", response_model=AnalysisView)
def get_analysis(
    analysis_id: UUID, storage: Repository = Depends(get_repository)
) -> AnalysisView:
    return AnalysisView.model_validate(require_analysis(analysis_id, storage))


@app.get("/v1/analyses/{analysis_id}/result")
def get_result(
    analysis_id: UUID, storage: Repository = Depends(get_repository)
) -> dict[str, Any]:
    item = require_analysis(analysis_id, storage)
    if item["status"] != AnalysisStatus.completed.value:
        raise HTTPException(
            409,
            detail={
                "code": "ANALYSIS_NOT_READY",
                "message": f"Analysis is {item['status']}",
                "retryable": item["status"] != AnalysisStatus.failed.value,
                "details": {"status": item["status"]},
            },
        )
    result = dict(item["result"])
    result["layers"] = storage.get_layers(analysis_id)
    return result


@app.get("/v1/analyses/{analysis_id}/layers/{layer}")
def get_layer(
    analysis_id: UUID, layer: str, storage: Repository = Depends(get_repository)
) -> dict[str, Any]:
    item = require_analysis(analysis_id, storage)
    if item["status"] != AnalysisStatus.completed.value:
        raise HTTPException(409, detail={"code": "ANALYSIS_NOT_READY", "message":
                            f"Analysis is {item['status']}", "retryable": True, "details": {}})
    value = storage.get_layer(analysis_id, layer)
    if not value or value.get("type") != "FeatureCollection":
        raise HTTPException(404, detail={"code": "LAYER_NOT_FOUND", "message":
                            f"Vector layer {layer} does not exist", "retryable": False, "details": {}})
    return value


@app.get("/v1/analyses/{analysis_id}/tiles/{layer}/{season}/{z}/{x}/{y}.png")
def get_tile(
    analysis_id: UUID, layer: str, season: str, z: int, x: int, y: int,
    storage: Repository = Depends(get_repository),
) -> Response:
    item = require_analysis(analysis_id, storage)
    request = AnalysisCreate.model_validate(item["request"])
    try:
        payload = tile_renderer.render(str(analysis_id), layer, season, z, x, y,
                                       request.bbox, request.time_window.start, request.time_window.end)
    except ValueError as error:
        raise HTTPException(422, detail={"code": "INVALID_TILE", "message": str(error),
                            "retryable": False, "details": {}}) from error
    except Exception as error:
        raise HTTPException(503, detail={"code": "TILE_SOURCE_UNAVAILABLE", "message": str(error),
                            "retryable": True, "details": {}}) from error
    return Response(payload, media_type="image/png", headers={"Cache-Control": "public, max-age=86400"})


@app.get("/v1/models", response_model=list[ModelInfo])
def list_models() -> list[ModelInfo]:
    return [
        ModelInfo(
            version="scale_v1.2",
            production=True,
            kind="interpretable_multisource_discovery",
            training_data_version="multisource_radar_weather_hydrology_rules_v1.2",
            applicable_region="Yangshi Town pilot; 25 km maximum AOI",
            limitations=[
                "Candidate corridors are landscape inference, not observed paths",
                "Sentinel-2 cannot resolve trail width or surface",
                "ERA5/GPM precipitation is regional context, not a local rain gauge",
                "DEM hydrology cannot resolve small culverts or roadside drains",
                "Not a navigation safety guarantee",
            ],
        )
    ]


@app.post("/v1/feedback", response_model=FeedbackAccepted, status_code=202)
def create_feedback(
    feedback: FeedbackCreate, storage: Repository = Depends(get_repository)
) -> FeedbackAccepted:
    item = require_analysis(feedback.analysis_id, storage)
    feedback_id = storage.save_feedback(feedback.model_dump(mode="json"))
    if feedback.target_type == "candidate_corridor" and feedback.exists is not None:
        result = item.get("result") or {}
        result["layers"] = storage.get_layers(feedback.analysis_id)
        target = find_target(result, feedback.target_type, str(feedback.target_id))
        if target:
            properties = target["properties"]
            if feedback.exists:
                properties["verification_state"] = "verified"
                properties["observation_state"] = "verified"
                properties["navigable"] = True
                properties["confidence"] = max(0.9, float(properties.get("confidence", 0)))
            else:
                properties["verification_state"] = "rejected"
                properties["navigable"] = False
                properties["confidence"] = 0
            storage.save_layers(feedback.analysis_id, {"candidate_corridors": result["layers"]["candidate_corridors"]})
    return FeedbackAccepted(feedback_id=feedback_id, visibility=feedback.visibility)


@app.post("/v1/gps-traces", response_model=GpsTraceAccepted, status_code=202)
def create_gps_trace(
    trace: GpsTraceCreate, storage: Repository = Depends(get_repository)
) -> GpsTraceAccepted:
    item = require_analysis(trace.analysis_id, storage)
    result = item.get("result") or {}
    result["layers"] = storage.get_layers(trace.analysis_id)
    target = find_target(result, trace.target_type, trace.target_id)
    if target is None:
        raise HTTPException(404, detail={"code": "TARGET_NOT_FOUND", "message":
                            "GPS verification target does not exist", "retryable": False, "details": {}})
    mean_distance, coverage = match_trace(trace.geometry, target["geometry"])
    existing = storage.list_gps_traces(trace.analysis_id, trace.target_id)
    payload = trace.model_dump(mode="python") | {
        "mean_distance_m": mean_distance, "coverage": coverage,
    }
    support_count = independent_support_count(existing + [payload])
    state = verification_state(mean_distance, coverage, support_count)
    payload["verification_state"] = state
    trace_id = storage.save_gps_trace(payload)
    traces = existing + [payload]
    recalculate_target(result, trace.target_type, trace.target_id, traces)
    layer_name = layer_for_target(trace.target_type)
    storage.save_layers(trace.analysis_id, {layer_name: result["layers"][layer_name]})
    return GpsTraceAccepted(trace_id=trace_id, verification_state=state,
                            mean_distance_m=round(mean_distance, 2), coverage=round(coverage, 3))


@app.delete("/v1/gps-traces/{trace_id}")
def revoke_gps_trace(
    trace_id: UUID, storage: Repository = Depends(get_repository)
) -> dict[str, Any]:
    revoked = storage.revoke_gps_trace(trace_id)
    if revoked is None:
        raise HTTPException(404, detail={"code": "TRACE_NOT_FOUND", "message":
                            "GPS trace does not exist or is already revoked", "retryable": False, "details": {}})
    analysis_id = UUID(str(revoked["analysis_id"]))
    item = require_analysis(analysis_id, storage)
    result = item.get("result") or {}
    result["layers"] = storage.get_layers(analysis_id)
    traces = storage.list_gps_traces(analysis_id, revoked["target_id"])
    state = recalculate_target(result, revoked["target_type"], revoked["target_id"], traces)
    layer_name = layer_for_target(revoked["target_type"])
    storage.save_layers(analysis_id, {layer_name: result["layers"][layer_name]})
    return {"trace_id": str(trace_id), "revoked": True, "verification_state": state}
