from datetime import date

import httpx

from scale.schemas import AnalysisCreate
from scale.storage import MemoryRepository
from scale.worker import process_one


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
