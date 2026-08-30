"""Configurazione dell'app Celery: broker/backend Redis, code separate per
dominio (scraping/media/ai) e scheduling via Celery Beat.

Code separate per dominio permettono di scalare/limitare la concorrenza in
modo indipendente (es. lo scraping va rate-limitato per non violare i ToS
delle fonti, la classificazione media può essere CPU/GPU-bound, l'AI può
dipendere da rate limit di un provider esterno).
"""

from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from app.config import settings

celery_app = Celery(
    "lavoro_esterno",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "app.workers.tasks_scraper",
        "app.workers.tasks_media",
        "app.workers.tasks_ai",
        "app.workers.tasks_maintenance",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_routes={
        "app.workers.tasks_scraper.*": {"queue": "scraping"},
        "app.workers.tasks_media.*": {"queue": "media"},
        "app.workers.tasks_ai.*": {"queue": "ai"},
        # I task di manutenzione (pulizia retention) sono leggeri e poco
        # frequenti (una volta al giorno): li instradiamo sulla coda
        # "scraping" già esistente invece di introdurre un servizio Celery
        # dedicato solo per questo in docker-compose.yml (vedi
        # worker-scraper: `-Q scraping,maintenance`).
        "app.workers.tasks_maintenance.*": {"queue": "maintenance"},
    },
)

# Celery Beat schedule: un solo task periodico per ora (pulizia retention
# dati, vedi app/workers/tasks_maintenance.py). Orario notturno per non
# competere con eventuale traffico di scraping/uso interattivo dell'API.
celery_app.conf.beat_schedule = {
    "cleanup-expired-data-nightly": {
        "task": "app.workers.tasks_maintenance.cleanup_expired_data",
        "schedule": crontab(hour=3, minute=0),
    },
}
