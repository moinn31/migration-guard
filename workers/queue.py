def enqueue_run(run_id: str, zip_path: str | None = None) -> None:
    from .celery_app import run_pipeline
    from backend.config import settings
    if settings.app_env.lower() in {"development", "dev", "test"} or settings.celery_task_always_eager:
        import threading
        threading.Thread(
            target=lambda: run_pipeline.apply(args=[run_id, zip_path]).get(),
            name=f"migrationguard-local-{run_id[:8]}",
            daemon=True,
        ).start()
        return
    run_pipeline.delay(run_id, zip_path)
