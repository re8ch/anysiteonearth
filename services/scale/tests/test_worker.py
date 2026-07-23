from datetime import date

import httpx

from scale.schemas import AnalysisCreate, TwinCreate
from scale.storage import MemoryRepository
from scale.worker import process_one, process_twin


class StubPipeline:
    def run(self, request, progress):
        progress("extracting", 60)
        return {
            "type": "FeatureCollection",
            "features": [],
            "metadata": {"model_version": "baseline_rules_v1"},
        }


class TransientPipeline:
    def run(self, request, progress):
        raise httpx.ConnectError("temporary DNS failure")


def test_worker_completes_claimed_job():
    repository = MemoryRepository()
    created = repository.create_analysis(
        AnalysisCreate.model_validate(
            {
                "bbox": {"west": 111.80, "south": 27.56, "east": 111.86, "north": 27.63},
                "activities": ["hiking"],
                "time_window": {"start": "2026-01-01", "end": date.today().isoformat()},
            }
        )
    )
    assert process_one(repository, StubPipeline())
    completed = repository.get_analysis(created["analysis_id"])
    assert completed["status"] == "completed"
    assert completed["progress"] == 100
    assert completed["result"]["type"] == "FeatureCollection"


def test_worker_requeues_transient_storage_failure():
    repository = MemoryRepository()
    created = repository.create_analysis(AnalysisCreate.model_validate({
        "bbox": {"west": 111.80, "south": 27.56, "east": 111.86, "north": 27.63},
        "activities": ["hiking"],
        "time_window": {"start": "2026-01-01", "end": date.today().isoformat()},
    }))

    assert process_one(repository, TransientPipeline())

    queued = repository.get_analysis(created["analysis_id"])
    assert queued["status"] == "queued"
    assert queued["error"]["retryable"] is True


class StubTwinCompiler:
    def compile(self, twin_id, request, analysis, layers, progress):
        progress("building_camera_tracks", 62)
        return {"manifest": {"twin_id": str(twin_id)}, "assets": {}}


def test_worker_completes_trip_twin_job():
    repository = MemoryRepository()
    analysis = repository.create_analysis(AnalysisCreate.model_validate({
        "bbox": {"west": 111.70, "south": 27.48, "east": 111.95, "north": 27.71},
        "activities": ["gravel_bike"],
        "time_window": {"start": "2026-01-01", "end": date.today().isoformat()},
    }))
    repository.update_analysis(analysis["analysis_id"], status="completed", result={})
    twin = repository.create_twin(TwinCreate.model_validate({
        "analysis_id": analysis["analysis_id"],
        "route_geometry": {"type": "LineString", "coordinates": [
            [111.78, 27.59], [111.825, 27.61], [111.87, 27.59]]},
    }))
    assert process_twin(repository, StubTwinCompiler())
    completed = repository.get_twin(twin["twin_id"])
    assert completed["status"] == "completed"
    assert completed["result"]["manifest"]["twin_id"] == str(twin["twin_id"])
