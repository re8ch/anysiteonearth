import logging
import time
from threading import Event
from uuid import UUID

import httpx

from .config import Settings, settings
from .pipeline import ScalePipeline
from .schemas import AnalysisCreate, AnalysisStatus
from .sources import SourceError
from .storage import Repository, create_repository
from .schemas import TwinCreate
from .twin import TwinCompiler, TwinError

logger = logging.getLogger("scale.worker")


def process_one(repository: Repository, pipeline: ScalePipeline) -> bool:
    item = repository.claim_analysis()
    if item is None:
        return False
    analysis_id = UUID(str(item["analysis_id"]))
    try:
        request = AnalysisCreate.model_validate(item["request"])

        def progress(stage: str, value: int) -> None:
            status = (
                AnalysisStatus.acquiring.value
                if value < 50
                else AnalysisStatus.processing.value
                if value < 75
                else AnalysisStatus.inferencing.value
            )
            repository.update_analysis(
                analysis_id, status=status, stage=stage, progress=value
            )

        result = pipeline.run(request, progress)
        layers = result.pop("layers", {})
        repository.save_layers(analysis_id, layers)
        result["layer_names"] = list(layers)
        repository.update_analysis(
            analysis_id,
            status=AnalysisStatus.completed.value,
            stage="completed",
            progress=100,
            result=result,
            error=None,
        )
    except SourceError as error:
        repository.update_analysis(
            analysis_id,
            status=AnalysisStatus.failed.value,
            stage="failed",
            progress=100,
            error={
                "code": error.code,
                "message": str(error),
                "retryable": error.retryable,
                "details": {},
            },
        )
    except httpx.HTTPError as error:
        logger.warning("Analysis %s hit a transient storage error: %s", analysis_id, error)
        repository.update_analysis(
            analysis_id,
            status=AnalysisStatus.queued.value,
            stage="retrying_transient_backend",
            progress=min(int(item.get("progress", 0)), 94),
            error={
                "code": "STORAGE_TEMPORARILY_UNAVAILABLE",
                "message": str(error),
                "retryable": True,
                "details": {},
            },
        )
    except Exception as error:
        logger.exception("Analysis %s failed", analysis_id)
        repository.update_analysis(
            analysis_id,
            status=AnalysisStatus.failed.value,
            stage="failed",
            progress=100,
            error={
                "code": "PIPELINE_FAILED",
                "message": str(error),
                "retryable": False,
                "details": {},
            },
        )
    return True


def process_twin(repository: Repository, compiler: TwinCompiler) -> bool:
    item = repository.claim_twin()
    if item is None:
        return False
    twin_id = UUID(str(item["twin_id"]))
    try:
        request = TwinCreate.model_validate(item["request"])
        analysis = repository.get_analysis(request.analysis_id)
        if not analysis or analysis.get("status") != AnalysisStatus.completed.value:
            raise TwinError("TWIN_ANALYSIS_NOT_READY", "source analysis is not completed")
        layers = repository.get_layers(request.analysis_id)

        def progress(stage: str, value: int) -> None:
            repository.update_twin(twin_id, status=(
                AnalysisStatus.acquiring.value if value < 40 else
                AnalysisStatus.processing.value if value < 75 else
                AnalysisStatus.inferencing.value), stage=stage, progress=value)

        result = compiler.compile(twin_id, request, analysis, layers, progress)
        repository.update_twin(twin_id, status=AnalysisStatus.completed.value,
                               stage="completed", progress=100, result=result, error=None)
    except TwinError as error:
        repository.update_twin(twin_id, status=AnalysisStatus.failed.value, stage="failed",
            progress=100, error={"code": error.code, "message": str(error),
                                 "retryable": error.retryable, "details": {}})
    except Exception as error:
        logger.exception("Trip twin %s failed", twin_id)
        repository.update_twin(twin_id, status=AnalysisStatus.failed.value, stage="failed",
            progress=100, error={"code": "TWIN_PIPELINE_FAILED", "message": str(error),
                                 "retryable": False, "details": {}})
    return True


def run_worker(
    repository: Repository,
    app_settings: Settings = settings,
    stop: Event | None = None,
) -> None:
    pipeline = ScalePipeline(app_settings)
    twin_compiler = TwinCompiler(app_settings)
    while not (stop and stop.is_set()):
        try:
            processed = process_one(repository, pipeline)
            if not processed:
                processed = process_twin(repository, twin_compiler)
        except Exception:
            logger.exception("Queue backend unavailable; retrying after backoff")
            time.sleep(max(5, app_settings.worker_poll_seconds))
            continue
        if not processed:
            time.sleep(app_settings.worker_poll_seconds)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    run_worker(
        create_repository(
            settings.database_url, settings.postgrest_jwt_secret, settings.postgrest_role
        )
    )


if __name__ == "__main__":
    main()
