"""Endpoint per la gestione delle fonti e l'avvio di scan on-demand."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.advertisement import Advertisement
from app.models.scrape_errors import ScrapeError
from app.models.scrape_runs import ScrapeRun
from app.models.sources import Source
from app.models.users import User
from app.schemas.sources import (
    RobotsCheckRead,
    ScanTriggerResponse,
    ScrapeErrorRead,
    ScrapeRunRead,
    SourceCreate,
    SourceDetailRead,
    SourceRead,
    SourcesSummaryRead,
    SourceUpdate,
    TestConfigResult,
)
from app.security.deps import get_current_user, require_role
from app.services.audit import log_action
from app.services.source_health import summarize_sources_by_status

# Numero massimo di run restituiti da GET /sources/{id}/runs: un drill-down
# "storico recente", non un archivio completo paginato (coerente con lo
# stesso limite pragmatico già usato per GET /exports, vedi
# app/api/v1/exports.py:_RECENT_EXPORTS_LIMIT).
_RECENT_RUNS_LIMIT = 50

# Quanti run recenti considerare per calcolare "consecutive_failures":
# sufficientemente ampio da rilevare un connettore rotto da un po', senza
# scandire l'intero storico di scrape_runs a ogni GET /sources.
_CONSECUTIVE_FAILURES_LOOKBACK = 10

# Soglia oltre la quale la UI mostra il badge "Connector broken?" (vedi
# frontend/src/routes/SourcesPage.tsx) — dashboard/alert per fonti che
# smettono di funzionare, PROGETTO.md § 4.
CONSECUTIVE_FAILURES_ALERT_THRESHOLD = 3

router = APIRouter()


def _source_user_agent(source: Source) -> str:
    scrape_config = source.scrape_config or {}
    configured_user_agent = scrape_config.get("user_agent") or scrape_config.get("userAgent")
    if configured_user_agent:
        return str(configured_user_agent).strip()

    from app.scrapers.base import Scraper

    return Scraper.user_agent


async def _compute_source_read(db: AsyncSession, source: Source, since: datetime) -> SourceRead:
    """Calcola le metriche derivate (`lastRunAt`, `itemsLast24h`,
    `errorRate`, `consecutiveFailures`) di UNA fonte da `scrape_runs`, non
    presenti come colonne dirette su `Source`. Condivisa da `GET /sources`
    (una fonte alla volta, N+1 accettato deliberatamente: il numero di
    fonti è tipicamente piccolo, decine non migliaia — vedi PROGETTO.md)
    e da `GET /sources/{id}` (una singola fonte, nessun N+1)."""
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
    # 0.0 se non c'è stata alcuna attività recente (evita divisione per 0 e
    # non è comunque un dato "in errore", solo assente).
    denominator = items_last_24h + errors_last_24h
    error_rate = (errors_last_24h / denominator) if denominator > 0 else 0.0

    last_statuses = (
        (
            await db.execute(
                select(ScrapeRun.status)
                .where(ScrapeRun.source_id == source.id)
                .order_by(ScrapeRun.started_at.desc())
                .limit(_CONSECUTIVE_FAILURES_LOOKBACK)
            )
        )
        .scalars()
        .all()
    )
    consecutive_failures = 0
    for run_status in last_statuses:
        if run_status != "failed":
            break
        consecutive_failures += 1

    return SourceRead(
        id=source.id,
        code=source.slug,
        name=source.name,
        status=source.status,
        priority=source.priority,
        last_run_at=last_run,
        items_last_24h=items_last_24h,
        error_rate=round(error_rate, 4),
        consecutive_failures=consecutive_failures,
        has_scrape_config=source.scrape_config is not None,
    )


@router.get("", response_model=list[SourceRead])
async def list_sources(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[SourceRead]:
    """Elenco fonti nella forma attesa dal frontend (`Source` type)."""
    sources = (await db.execute(select(Source).order_by(Source.name))).scalars().all()
    since = datetime.now(UTC) - timedelta(hours=24)
    return [await _compute_source_read(db, source, since) for source in sources]


# NOTA D'ORDINE ROUTE: "/summary" deve restare dichiarata prima di
# "/{source_id}" (route a singolo segmento, come "/summary"): FastAPI
# risolve le route nell'ordine di dichiarazione, quindi "/summary"
# andrebbe altrimenti intercettata da "/{source_id}" con
# source_id="summary" (422, UUID non valido) invece di raggiungere questo
# handler.
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


@router.post("", response_model=SourceRead, status_code=status.HTTP_201_CREATED)
async def create_source(
    payload: SourceCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
) -> SourceRead:
    """Crea una nuova fonte (solo Admin). Se `scrape_config` è valorizzato
    (già validato da `ScrapeConfigInput`), la fonte è immediatamente
    scrapabile dal motore generico tramite `POST /sources/{id}/scan`.
    """
    existing = (
        await db.execute(select(Source.id).where(Source.slug == payload.slug))
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Una fonte con slug '{payload.slug}' esiste già.",
        )

    source = Source(
        name=payload.name,
        slug=payload.slug,
        base_url=payload.base_url,
        priority=payload.priority,
        status="healthy",
        enabled=True,
        scrape_config=payload.scrape_config.model_dump() if payload.scrape_config else None,
        watermark_removal_enabled=payload.watermark_removal.enabled,
        watermark_authorization_reference=payload.watermark_removal.authorization_reference,
        watermark_regions=[region.model_dump() for region in payload.watermark_removal.regions],
    )
    db.add(source)
    await log_action(
        db,
        user_id=user.id,
        action="create_source",
        entity_type="source",
        details={"slug": payload.slug},
    )
    await db.commit()
    await db.refresh(source)

    return _to_minimal_source_read(source)


async def _get_source_or_404(db: AsyncSession, source_id: uuid.UUID) -> Source:
    source = await db.get(Source, source_id)
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fonte non trovata.")
    return source


def _to_minimal_source_read(source: Source) -> SourceRead:
    """`SourceRead` con le metriche derivate azzerate: usata subito dopo
    creazione/modifica di una fonte, quando non ha ancora `scrape_runs`
    (o non è comunque il caso di ricalcolarle per una singola risposta di
    scrittura — quella vista completa/aggregata resta `GET /sources`)."""
    return SourceRead(
        id=source.id,
        code=source.slug,
        name=source.name,
        status=source.status,
        priority=source.priority,
        last_run_at=None,
        items_last_24h=0,
        error_rate=0.0,
        consecutive_failures=0,
        has_scrape_config=source.scrape_config is not None,
    )


@router.get("/{source_id}", response_model=SourceDetailRead)
async def get_source(
    source_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> SourceDetailRead:
    """Dettaglio di una fonte, incluso `scrapeConfig` completo — usato per
    precompilare il form "Edit configuration" in UI (`GET /sources`, la
    lista, espone solo `hasScrapeConfig`, un booleano)."""
    source = await _get_source_or_404(db, source_id)
    since = datetime.now(UTC) - timedelta(hours=24)
    base = await _compute_source_read(db, source, since)
    return SourceDetailRead(
        **base.model_dump(by_alias=False),
        scrape_config=source.scrape_config,
        watermark_removal={
            "enabled": source.watermark_removal_enabled,
            "authorization_reference": source.watermark_authorization_reference,
            "regions": source.watermark_regions or [],
        },
    )


@router.patch("/{source_id}", response_model=SourceRead)
async def update_source(
    source_id: uuid.UUID,
    payload: SourceUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
) -> SourceRead:
    """Modifica `name`/`base_url`/`priority`/`scrape_config` di una fonte
    esistente (solo Admin). Non permette di cambiare `slug`: è la chiave
    stabile usata per collegare la fonte al connettore
    (`app/scrapers/registry.py`) o, se configurata, al motore generico."""
    source = await _get_source_or_404(db, source_id)

    updates = payload.model_dump(exclude_unset=True, exclude={"scrape_config", "watermark_removal"})
    for field_name, value in updates.items():
        setattr(source, field_name, value)
    if "scrape_config" in payload.model_fields_set:
        source.scrape_config = payload.scrape_config.model_dump() if payload.scrape_config else None
    if "watermark_removal" in payload.model_fields_set and payload.watermark_removal is not None:
        wm = payload.watermark_removal
        source.watermark_removal_enabled = wm.enabled
        source.watermark_authorization_reference = wm.authorization_reference
        source.watermark_regions = [region.model_dump() for region in wm.regions]

    db.add(source)
    await log_action(
        db,
        user_id=user.id,
        action="update_source",
        entity_type="source",
        entity_id=str(source_id),
        details={
            "watermark_removal_enabled": source.watermark_removal_enabled,
            "watermark_authorization_reference": source.watermark_authorization_reference,
        },
    )
    await db.commit()
    await db.refresh(source)

    return _to_minimal_source_read(source)


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_source(
    source_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
) -> None:
    """Rimuove una fonte (solo Admin). Bloccato con 409 se esistono
    `advertisement` collegati: preserva lo storico invece di lasciare
    annunci orfani o cancellarli silenziosamente."""
    source = await _get_source_or_404(db, source_id)

    has_ads = (
        await db.execute(
            select(Advertisement.id).where(Advertisement.source_id == source_id).limit(1)
        )
    ).scalar_one_or_none()
    if has_ads is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Impossibile eliminare: esistono annunci collegati a questa fonte.",
        )

    await log_action(
        db, user_id=user.id, action="delete_source", entity_type="source", entity_id=str(source_id)
    )
    await db.delete(source)
    await db.commit()


@router.get("/{source_id}/runs", response_model=list[ScrapeRunRead])
async def get_source_runs(
    source_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[ScrapeRunRead]:
    """Storico dei run di scraping per una fonte, con gli errori di
    ciascun run annidati — drill-down "visualizzazione errori scraping"
    della pagina Sources (`frontend/src/routes/SourcesPage.tsx`), che oggi
    mostra solo `errorRate` aggregato senza poter vedere i singoli errori.

    Sola lettura, aperto a qualunque ruolo autenticato (come `GET
    /sources`): non è un'azione operativa, solo consultazione.
    """
    await _get_source_or_404(db, source_id)

    runs = (
        (
            await db.execute(
                select(ScrapeRun)
                .where(ScrapeRun.source_id == source_id)
                .order_by(ScrapeRun.started_at.desc())
                .limit(_RECENT_RUNS_LIMIT)
            )
        )
        .scalars()
        .all()
    )
    if not runs:
        return []

    run_ids = [r.id for r in runs]
    errors = (
        (
            await db.execute(
                select(ScrapeError)
                .where(ScrapeError.scrape_run_id.in_(run_ids))
                .order_by(ScrapeError.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    errors_by_run: dict[uuid.UUID, list[ScrapeErrorRead]] = {}
    for err in errors:
        errors_by_run.setdefault(err.scrape_run_id, []).append(
            ScrapeErrorRead(
                id=err.id, url=err.url, error_message=err.error_message, created_at=err.created_at
            )
        )

    return [
        ScrapeRunRead(
            id=run.id,
            started_at=run.started_at,
            finished_at=run.finished_at,
            status=run.status,
            items_found=run.items_found,
            items_new=run.items_new,
            errors_count=run.errors_count,
            errors=errors_by_run.get(run.id, []),
        )
        for run in runs
    ]


@router.post("/{source_id}/pause", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
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


@router.post("/{source_id}/disable", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
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


@router.post("/{source_id}/check-robots", response_model=RobotsCheckRead)
async def check_source_robots(
    source_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> RobotsCheckRead:
    """Verifica live `robots.txt` per `base_url` della fonte (solo il file
    `robots.txt` stesso viene scaricato, pubblico per definizione — nessun
    altro contenuto della fonte). Utile per validare una configurazione
    prima di lanciare uno scan reale. Sola lettura, nessuna restrizione di
    ruolo oltre l'autenticazione."""
    source = await _get_source_or_404(db, source_id)

    from app.services.robots_check import check_robots

    result = await check_robots(source.base_url, user_agent=_source_user_agent(source))
    return RobotsCheckRead(
        allowed=result.allowed,
        robots_txt_found=result.robots_txt_found,
        checked_url=result.checked_url,
    )


@router.post("/{source_id}/test-config", response_model=TestConfigResult)
async def test_source_config(
    source_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("admin", "operator")),
) -> TestConfigResult:
    """Prova la configurazione di scraping della fonte su UN solo annuncio
    (non salvato su DB): permette di verificare che i selettori CSS
    configurati estraggano davvero i campi attesi, prima di lanciare uno
    scan reale che scriverebbe su Postgres/MinIO. Richiede `scrape_config`
    già salvato (vedi `PATCH /sources/{id}`).

    Come `POST /sources/{id}/scan`, richiede admin/operator: esegue comunque
    richieste HTTP reali verso la fonte (rispettando robots.txt/rate-limit
    come ogni altra chiamata del motore).
    """
    source = await _get_source_or_404(db, source_id)
    if not source.scrape_config:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Questa fonte non ha ancora una configurazione di scraping (scrape_config).",
        )

    from app.scrapers.generic import GenericScraper, RobotsDisallowedError

    scraper = GenericScraper(
        slug=source.slug, base_url=source.base_url, config=source.scrape_config
    )
    try:
        ad_urls = await scraper.discover()
        if not ad_urls:
            return TestConfigResult(
                ad_urls_found=0, error="Nessun link annuncio trovato con 'ad_link_selector'."
            )
        raw = await scraper.scrape_ad(ad_urls[0])
        return TestConfigResult(
            ad_urls_found=len(ad_urls), sample_url=ad_urls[0], extracted_fields=raw
        )
    except RobotsDisallowedError as exc:
        return TestConfigResult(ad_urls_found=0, error=f"robots.txt vieta l'accesso: {exc}")
    except Exception as exc:  # noqa: BLE001 - risposta diagnostica per l'operatore, non un 500
        return TestConfigResult(ad_urls_found=0, error=str(exc))
