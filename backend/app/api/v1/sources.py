"""Endpoint per la gestione delle fonti e l'avvio di scan on-demand."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.scrape_runs import ScrapeRun
from app.models.sources import Source
from app.models.users import User
from app.schemas.sources import ScanTriggerResponse, SourceRead, SourcesSummaryRead
from app.security.deps import get_current_user, require_role
from app.services.audit import log_action
from app.services.source_health import summarize_sources_by_status

router = APIRouter()


@router.get("", response_model=list[SourceRead])
async def list_sources(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[SourceRead]:
    """Elenco fonti nella forma attesa dal frontend (`Source` type), che
    include metriche derivate (`lastRunAt`, `itemsLast24h`, `errorRate`) non
    presenti come colonne dirette su `Source`: le calcoliamo qui da
    `scrape_runs`, una fonte alla volta.

    Approssimazione N+1 accettata deliberatamente in questa fase (il numero
    di fonti è tipicamente piccolo, decine non migliaia): se il volume di
    fonti crescesse andrebbe sostituita con un'unica query aggregata
    (subquery/GROUP BY per source_id) — vedi PROGETTO.md.
    """
    sources = (await db.execute(select(Source).order_by(Source.name))).scalars().all()
    since = datetime.now(timezone.utc) - timedelta(hours=24)

    reads: list[SourceRead] = []
    for source in sources:
        last_run = (
            await db.execute(
                select(ScrapeRun.started_at)
                .where(ScrapeRun.source_id == source.id)
                .order_by(ScrapeRun.started_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

        recent_runs = (
            await db.execute(
                select(ScrapeRun.items_found, ScrapeRun.errors_count).where(
                    ScrapeRun.source_id == source.id, ScrapeRun.started_at >= since
                )
            )
        ).all()
        items_last_24h = sum(r.items_found for r in recent_runs)
        errors_last_24h = sum(r.errors_count for r in recent_runs)
        # Error rate = errori / (item processati + errori) nelle ultime 24h;
        # 0.0 se non c'è stata alcuna attività recente (evita divisione per 0
        # e non è comunque un dato "in errore", solo assente).
        denominator = items_last_24h + errors_last_24h
        error_rate = (errors_last_24h / denominator) if denominator > 0 else 0.0

        reads.append(
            SourceRead(
                id=source.id,
                code=source.slug,
                name=source.name,
                status=source.status,
                last_run_at=last_run,
                items_last_24h=items_last_24h,
                error_rate=round(error_rate, 4),
            )
        )
    return reads


# NOTA D'ORDINE ROUTE: "/summary" deve restare dichiarata prima di eventuali
# route "/{source_id}" a singolo segmento (oggi non ce ne sono: le route
# esistenti hanno tutte un secondo segmento fisso come "/scan", "/pause",
# "/disable", quindi non c'è ambiguità di routing con l'id — la teniamo qui
# in cima comunque per coerenza con l'analogo caso in app/api/v1/records.py).
@router.get("/summary", response_model=SourcesSummaryRead)
async def get_sources_summary(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> SourcesSummaryRead:
    """Conteggio delle fonti per stato, per la card riepilogativa della
    pagina Sources (`GET /sources/summary`, mancante nel backend
    originario: la pagina Sources del frontend la chiama al primo
    caricamento insieme a `GET /sources`)."""
    statuses = (await db.execute(select(Source.status))).scalars().all()
    return SourcesSummaryRead(**summarize_sources_by_status(statuses))


async def _get_source_or_404(db: AsyncSession, source_id: uuid.UUID) -> Source:
    source = await db.get(Source, source_id)
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fonte non trovata.")
    return source


@router.post("/{source_id}/pause", status_code=status.HTTP_204_NO_CONTENT)
async def pause_source(
    source_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin", "operator")),
) -> None:
    """Mette in pausa una fonte: `enabled=False` senza cambiarne lo `status`
    di salute (una fonte in pausa non è "offline", è semplicemente ferma su
    decisione di un operatore — lo status di salute torna rilevante quando
    verrà riattivata).

    Riservato ad admin/operator, come `POST /sources/{id}/scan`: mettere in
    pausa una fonte è un'azione operativa che impatta la raccolta dati.
    """
    source = await _get_source_or_404(db, source_id)
    source.enabled = False
    db.add(source)
    await log_action(
        db, user_id=user.id, action="pause_source", entity_type="source", entity_id=str(source_id)
    )
    await db.commit()


@router.post("/{source_id}/disable", status_code=status.HTTP_204_NO_CONTENT)
async def disable_source(
    source_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin", "operator")),
) -> None:
    """Disabilita definitivamente una fonte: `enabled=False` e
    `status="offline"`, a differenza della pausa che lascia lo status di
    salute invariato (vedi `pause_source`)."""
    source = await _get_source_or_404(db, source_id)
    source.enabled = False
    source.status = "offline"
    db.add(source)
    await log_action(
        db, user_id=user.id, action="disable_source", entity_type="source", entity_id=str(source_id)
    )
    await db.commit()


@router.post("/{source_id}/scan", response_model=ScanTriggerResponse)
async def scan_source(
    source_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("admin", "operator")),
) -> ScanTriggerResponse:
    """Accoda un task Celery di scraping per la fonte indicata.

    Riservato a admin/operator: uno scan può generare traffico verso siti
    terzi e va quindi avviabile solo da chi ha responsabilità operativa,
    non dai soli viewer.
    """
    source = await db.get(Source, source_id)
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fonte non trovata.")
    if not source.enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="La fonte è disabilitata."
        )

    # Import locale per evitare che l'intero modulo Celery (e le sue
    # dipendenze, es. connessione Redis) venga caricato all'avvio di ogni
    # richiesta API che non ne ha bisogno.
    from app.workers.tasks_scraper import run_scrape_source

    async_result = run_scrape_source.delay(str(source.id))

    return ScanTriggerResponse(task_id=async_result.id, source_id=source.id)
