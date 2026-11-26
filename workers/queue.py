"""Production Celery dispatch; development jobs share the API's async event loop."""
import asyncio
import logging
from pathlib import Path
from backend.config import settings
from backend.observability import redact

tasks: set[asyncio.Task] = set()
logger = logging.getLogger(__name__)

def enqueue_run(run_id: str, zip_path: str | None = None) -> None:
    if settings.app_env.lower() in {'development', 'dev', 'test'} or settings.celery_task_always_eager:
        from .runner import advance_run
        async def execute():
            try:
                await advance_run(run_id, zip_path)
            finally:
                if zip_path:
                    Path(zip_path).unlink(missing_ok=True)
        task = asyncio.get_running_loop().create_task(execute(), name='migrationguard-' + run_id)
        tasks.add(task)
        def finished(task):
            tasks.discard(task)
            if not task.cancelled() and task.exception():
                logger.error('Local verification failed: %s', redact(str(task.exception())))
        task.add_done_callback(finished)
        return
    from .celery_app import run_pipeline
    run_pipeline.delay(run_id, zip_path)

async def shutdown():
    pending = list(tasks)
    for task in pending:
        task.cancel()
    await asyncio.gather(*pending, return_exceptions=True)
