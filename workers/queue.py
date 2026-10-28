def enqueue_run(run_id: str) -> None:
    from .celery_app import run_pipeline
    run_pipeline.delay(run_id)
