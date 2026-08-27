"""Configurazione dell'app Celery: broker/backend Redis, code separate per
dominio (scraping/media/ai) e scheduling via Celery Beat.

Code separate per dominio permettono di scalare/limitare la concorrenza in
modo indipendente (es. lo scraping va rate-limitato per non violare i ToS
delle fonti, la classificazione media può essere CPU/GPU-bound, l'AI può
dipendere da rate limit di un provider esterno).
"""

from __future__ import annotations

from celery import Celery

from app.config import settings

celery_app = Celery(
    "lavoro_esterno",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "app.workers.tasks_scraper",
        "app.workers.tasks_media",
        "app.workers.tasks_ai",
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
    },
)

# Celery Beat schedule: intenzionalmente vuoto in questo scaffold. Popolarlo
# in futuro con voci del tipo:
#
# celery_app.conf.beat_schedule = {
#     "scan-all-sources-every-hour": {
#         "task": "app.workers.tasks_scraper.run_scrape_all_sources",
#         "schedule": crontab(minute=0),
#     },
# }
celery_app.conf.beat_schedule = {}
