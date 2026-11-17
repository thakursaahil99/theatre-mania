from pathlib import Path

from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "cineverse",
    broker=settings.celery_broker,
    backend=settings.celery_backend,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    result_expires=24 * 3600,
    timezone="UTC",
    enable_utc=True,
    # Long transcodes: only ack once finished, never prefetch more than one job per process.
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    broker_transport_options={"visibility_timeout": 8 * 3600},
    task_routes={
        "app.workers.tasks.transcode_asset": {"queue": "transcode"},
        "app.workers.tasks.*": {"queue": "default"},
    },
    beat_schedule={
        "enforce-license-windows": {
            "task": "app.workers.tasks.enforce_license_windows",
            "schedule": crontab(minute="*/15"),
        },
    },
)

if settings.celery_filesystem_broker:
    # Native dev without Redis: messages are files in a shared folder (works on Windows).
    _queue_dir = Path(settings.LOCAL_DATA_DIR).resolve() / "celery" / "queue"
    _done_dir = Path(settings.LOCAL_DATA_DIR).resolve() / "celery" / "processed"
    _queue_dir.mkdir(parents=True, exist_ok=True)
    _done_dir.mkdir(parents=True, exist_ok=True)
    celery_app.conf.update(
        broker_transport_options={
            "data_folder_in": str(_queue_dir),
            "data_folder_out": str(_queue_dir),
            "processed_folder": str(_done_dir),
            "store_processed": False,
        },
        task_ignore_result=True,
        broker_connection_retry_on_startup=True,
    )
