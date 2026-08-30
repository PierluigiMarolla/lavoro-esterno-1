"""Task Celery per l'esecuzione dello scraping delle fonti.

Celery esegue i task in modo sincrono (worker basati su thread/processi, non
async-native), quindi qui usiamo una sessione SQLAlchemy SINCRONA (psycopg2)
distinta da quella async usata da FastAPI (app.db). Sono due engine separati
che puntano allo stesso database.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime

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

    Il task:
    1. crea una riga `scrape_runs` con status "running";
    2. se `source.scrape_config` è valorizzato, esegue DAVVERO la pipeline
       del motore generico (`app/services/scrape_ingest.py`): raccolta via
       rete (fase async, dentro `asyncio.run`) poi persistenza su DB (fase
       sync, stessa sessione di questo task) — dedup per telefono, upsert
       annunci, upload media, ricalcolo canonico;
    3. se `scrape_config` è nullo, il run fallisce esplicitamente: l'unico
       motore di scraping esistente è quello generico configurabile
       (`app/scrapers/generic.py:GenericScraper`), che richiede una
       configurazione per sapere cosa fare — non esistono più connettori
       "stub" per-sito da poter anche solo tentare di risolvere;
    4. chiude la riga `scrape_runs` con status/conteggi reali e registra
       eventuali `ScrapeError` (usati dal drill-down `GET /sources/{id}/
       runs`, vedi `frontend/src/routes/SourcesPage.tsx`).
    """
    from app.models.scrape_errors import ScrapeError
    from app.models.scrape_runs import ScrapeRun  # import locale per evitare import circolari
    from app.models.sources import Source
    from app.services.scrape_ingest import collect_ads, persist_collected_ads

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

        if source.scrape_config:
            try:
                collection = asyncio.run(collect_ads(source))
                outcome = persist_collected_ads(session, source, collection)
            except Exception:
                logger.exception(
                    "Errore imprevisto durante lo scraping reale della fonte '%s'.", source.slug
                )
                run.status = "failed"
                run.errors_count += 1
            else:
                run.items_found = outcome["items_found"]
                run.items_new = outcome["items_new"]
                run.errors_count = outcome["errors_count"]
                # "completed" anche con alcuni errori parziali: solo un run
                # senza NESSUN annuncio trovato/nuovo e con errori è un
                # fallimento vero e proprio (es. robots.txt vieta tutto).
                run.status = "failed" if (outcome["items_new"] == 0 and outcome["errors"]) else "completed"
                for error in outcome["errors"]:
                    session.add(
                        ScrapeError(scrape_run_id=run.id, url=error.url, error_message=error.message)
                    )
        else:
            logger.warning(
                "Fonte '%s' (slug=%s) non ha uno scrape_config: impossibile eseguire uno "
                "scan, non esiste azione da compiere senza configurazione.",
                source.name,
                source.slug,
            )
            run.status = "failed"
            run.errors_count += 1
            session.add(
                ScrapeError(
                    scrape_run_id=run.id,
                    url=source.base_url,
                    error_message="Fonte non configurata: nessuno scrape_config impostato.",
                )
            )

        run.finished_at = datetime.now(UTC)
        session.add(run)
        session.commit()

        return {"status": run.status, "run_id": str(run.id)}
    finally:
        session.close()
