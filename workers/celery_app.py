from celery import Celery
from backend.config import settings

celery_app = Celery("migrationguard", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    task_always_eager=settings.celery_task_always_eager
    or settings.app_env.lower() in {"development", "dev", "test"}
)

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
    from backend.db import get_async_database_url
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from sqlalchemy.pool import NullPool
    async def execute():
        engine = create_async_engine(get_async_database_url(settings.database_url), poolclass=NullPool)
        try:
            await advance_run(run_id, zip_path, session_factory=async_sessionmaker(engine, expire_on_commit=False))
        finally:
            await engine.dispose()
    try:
        asyncio.run(execute())
    finally:
        if zip_path and os.path.exists(zip_path):
            os.unlink(zip_path)
