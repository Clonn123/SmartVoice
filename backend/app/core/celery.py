from celery import Celery
import os

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
REDIS_BACKEND_URL = os.getenv("REDIS_BACKEND_URL", "redis://redis:6379/1")

celery = Celery(
    "smartvoice",
    broker=REDIS_URL,
    backend=REDIS_BACKEND_URL,
    include=[
        "app.modules.calls.tasks",
    ],
)

celery.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_track_started=True,
    timezone="UTC",
)
