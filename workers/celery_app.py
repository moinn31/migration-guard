from celery import Celery
from backend.config import settings

celery_app = Celery("migrationguard", broker=settings.redis_url, backend=settings.redis_url)

@celery_app.task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def run_pipeline(self, run_id: str, zip_path: str | None = None) -> None:
    import asyncio
    import os
    from .runner import advance_run
    try:
        asyncio.run(advance_run(run_id, zip_path))
    finally:
        if zip_path and os.path.exists(zip_path):
            os.unlink(zip_path)
