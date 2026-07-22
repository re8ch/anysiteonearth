from datetime import date

from fastapi.testclient import TestClient

from scale.api import app, get_repository
from scale.schemas import AnalysisCreate
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
    assert models.json()[0]["version"] == "scale_v1.2"
    assert models.json()[0]["limitations"]


def test_trip_twin_lifecycle_requires_completed_analysis():
    repository = MemoryRepository()
    app.dependency_overrides[get_repository] = lambda: repository
    analysis = repository.create_analysis(AnalysisCreate.model_validate(request_body()))
    body = {
        "analysis_id": str(analysis["analysis_id"]),
        "route_geometry": {"type": "LineString", "coordinates": [
            [111.78, 27.59], [111.825, 27.61], [111.87, 27.59]]},
        "scenario": "mist", "camera_modes": ["aerial", "follow"],
    }
    with TestClient(app) as client:
        pending = client.post("/v1/twins", json=body)
        assert pending.status_code == 409
        repository.update_analysis(analysis["analysis_id"], status="completed", result={})
        accepted = client.post("/v1/twins", json=body)
        assert accepted.status_code == 202
        twin_id = accepted.json()["twin_id"]
        status = client.get(f"/v1/twins/{twin_id}")
        assert status.status_code == 200
        assert status.json()["status"] == "queued"
    app.dependency_overrides.clear()
