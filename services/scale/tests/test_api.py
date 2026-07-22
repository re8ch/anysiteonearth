from datetime import date

from fastapi.testclient import TestClient

from scale.api import app, get_repository
from scale.storage import MemoryRepository


def request_body():
    return {
        "bbox": {"west": 111.80, "south": 27.56, "east": 111.86, "north": 27.63},
        "activities": ["hiking", "gravel_bike"],
        "time_window": {"start": "2026-01-01", "end": date.today().isoformat()},
    }


def test_analysis_lifecycle_contract():
    repository = MemoryRepository()
    app.dependency_overrides[get_repository] = lambda: repository
    with TestClient(app) as client:
        created = client.post("/v1/analyses", json=request_body())
        assert created.status_code == 202
        analysis_id = created.json()["analysis_id"]
        status = client.get(f"/v1/analyses/{analysis_id}")
        assert status.status_code == 200
        assert status.json()["status"] == "queued"
        pending = client.get(f"/v1/analyses/{analysis_id}/result")
        assert pending.status_code == 409
    app.dependency_overrides.clear()


def test_models_describe_limitations():
    with TestClient(app) as client:
        models = client.get("/v1/models")
    assert models.status_code == 200
    assert models.json()[0]["version"] == "scale_v1.1"
    assert models.json()[0]["limitations"]
