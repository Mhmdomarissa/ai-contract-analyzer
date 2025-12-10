from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "contract_review",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.task_routes = {"app.tasks.*": {"queue": "contract-tasks"}}
celery_app.autodiscover_tasks(["app.tasks"])

