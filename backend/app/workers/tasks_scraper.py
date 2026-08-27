"""Task Celery per l'esecuzione dello scraping delle fonti.

Celery esegue i task in modo sincrono (worker basati su thread/processi, non
async-native), quindi qui usiamo una sessione SQLAlchemy SINCRONA (psycopg2)
distinta da quella async usata da FastAPI (app.db). Sono due engine separati
che puntano allo stesso database.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def _sync_database_url() -> str:
    """Deriva la connection string sincrona (psycopg2) da DATABASE_URL,
    permettendo comunque un override esplicito via DATABASE_URL_SYNC."""
    if settings.DATABASE_URL_SYNC:
        return settings.DATABASE_URL_SYNC
    return settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql+psycopg2://")


_sync_engine = create_engine(_sync_database_url(), pool_pre_ping=True)
SyncSessionLocal = sessionmaker(bind=_sync_engine, class_=Session, expire_on_commit=False)


@celery_app.task(name="app.workers.tasks_scraper.run_scrape_source", bind=True)
def run_scrape_source(self, source_id: str) -> dict:
    """Esegue uno scraping per una singola fonte, identificata da `source_id`.

    In questo scaffold, il task:
    1. crea una riga `scrape_runs` con status "running";
    2. risolve il connettore scraper dallo slug della fonte (registry);
    3. TODO: invoca realmente `discover` -> `scrape_ad` -> `normalize` ->
       (dedup + persistenza Advertisement/Media) per ogni URL scoperto;
    4. chiude la riga `scrape_runs` con status "completed" o "failed".

    Il passo 3 è deliberatamente non implementato (i connettori in
    app/scrapers/*.py sono stub che sollevano NotImplementedError): qui ci
    limitiamo a loggare e a lasciare la riga scrape_runs in uno stato
    coerente, così che l'endpoint `POST /sources/{id}/scan` sia già
    end-to-end funzionante (accoda il task, il task aggiorna lo stato) anche
    prima che lo scraping reale sia implementato.
    """
    from app.models.scrape_runs import ScrapeRun  # import locale per evitare import circolari
    from app.models.sources import Source
    from app.scrapers.registry import get_scraper_class

    source_uuid = uuid.UUID(source_id)
    session = SyncSessionLocal()
    try:
        source = session.get(Source, source_uuid)
        if source is None:
            logger.error("Source %s non trovata: impossibile avviare lo scraping.", source_id)
            return {"status": "failed", "reason": "source_not_found"}

        run = ScrapeRun(source_id=source.id, status="running")
        session.add(run)
        session.commit()
        session.refresh(run)

        try:
            get_scraper_class(source.slug)
            logger.info(
                "TODO: implementare l'esecuzione reale dello scraping per la fonte '%s' "
                "(slug=%s, run_id=%s). Il connettore è registrato ma i suoi metodi sono stub.",
                source.name,
                source.slug,
                run.id,
            )
            run.status = "completed"
        except KeyError:
            logger.exception("Nessun connettore scraper registrato per la fonte '%s'.", source.slug)
            run.status = "failed"
            run.errors_count += 1

        from datetime import datetime

        run.finished_at = datetime.now(UTC)
        session.add(run)
        session.commit()

        return {"status": run.status, "run_id": str(run.id)}
    finally:
        session.close()
