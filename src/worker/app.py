import celery

from ..core import conf


settings = conf.get_settings()

celery_app = celery.Celery(
    'sync-service',
    broker=settings.celery_broker_url,
    include=['src.worker.tasks'],
)
celery_app.conf.update(
    accept_content=['json'],
    beat_schedule={
        'scheduled-employee-sync': {
            'task': 'sync.schedule',
            'schedule': settings.schedule_interval_seconds,
        },
    }
    if settings.schedule_enabled
    else {},
    enable_utc=True,
    result_backend=None,
    task_acks_late=True,
    task_ignore_result=True,
    task_serializer='json',
    timezone='UTC',
    worker_prefetch_multiplier=1,
)
