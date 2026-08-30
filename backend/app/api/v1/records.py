"""Endpoint di lettura/ricerca per i Record e i loro dati collegati
(annunci, media, storico, riepilogo AI).

Il modulo espone due famiglie di endpoint:

1. Endpoint "legacy", allineati 1:1 al modello ORM (`GET /records/{id}` nella
   sua forma originaria, `POST /records/search`): risposte snake_case.
2. Endpoint "view", pensati per la UI (`frontend/src/routes/records/*`) e
   consumati da `frontend/src/api/records.ts` SENZA alcun mapping
   snake->camel lato client: rispondono quindi in camelCase (vedi
   `app/schemas/common.py:CamelModel`). `GET /records/{record_id}` è stato
   convertito in questa seconda famiglia (vedi `get_record_overview`),
   perché è quello che la UI usa davvero per la tab "Overview": il vecchio
   `RecordDetail` (annuncio-per-annuncio, snake_case) non copriva i campi
   che la UI mostra (titolo/descrizione canonici, confidence, tag...).
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import and_, false, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, selectinload

from app.db import get_db
from app.models.advertisement import Advertisement
from app.models.audit_log import AuditLog
from app.models.canonical_history import CanonicalHistory
from app.models.media import Media
from app.models.media_classification_history import MediaClassificationHistory
from app.models.record import Record
from app.models.sources import Source
from app.models.summary_versions import SummaryVersion
from app.models.users import User
from app.schemas.records import (
    RecordAiSummaryRead,
    RecordAiSummaryVersionRead,
    RecordDetail,
    RecordHistoryEventRead,
    RecordMediaRead,
    RecordOccurrenceRead,
    RecordOverviewRead,
    RecordSearchRequest,
    RecordSearchResponseRead,
    RecordSearchResultRead,
    SourceUsedRead,
)
from app.security.deps import get_current_user, require_role
from app.services.audit import log_action
from app.services.phone_crypto import decrypt_phone, phone_lookup_hash
from app.services.record_search import (
    VERIFIED_CONFIDENCE_THRESHOLD,
    confidence_to_status,
    looks_like_full_phone,
)
from app.services.summary_generator import TemplateSummaryGenerator

router = APIRouter()


def _safe_decrypt_phone(encrypted: bytes) -> str:
    """Decifra il telefono per la visualizzazione, senza far fallire
    l'intera risposta se un singolo record ha un blob corrotto/illeggibile
    (difesa in profondità: preferiamo mostrare un placeholder a un 500)."""
    try:
        return decrypt_phone(encrypted)
    except Exception:  # noqa: BLE001 - difesa deliberatamente ampia, vedi docstring
        return "N/D"


async def _get_record_or_404(db: AsyncSession, record_id: uuid.UUID) -> Record:
    record = await db.get(Record, record_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Record non trovato.")
    return record


# ---------------------------------------------------------------------------
# GET /records/search — ricerca paginata (usata da frontend/src/api/records.ts)
# ---------------------------------------------------------------------------
# NOTA D'ORDINE ROUTE: questa route deve essere registrata PRIMA di
# `GET /{record_id}` qui sotto. FastAPI risolve le route nell'ordine di
# dichiarazione: se "/{record_id}" precedesse "/search", una richiesta a
# "/records/search" verrebbe intercettata da "/{record_id}" con
# record_id="search", fallendo la validazione UUID con un 422 invece di
# raggiungere questo handler.
@router.get("/search", response_model=RecordSearchResponseRead)
async def search_records(
    phone: str | None = Query(None, description="Numero di telefono (intero) da cercare."),
    source: str | None = Query(None, description="Slug o nome della fonte."),
    status_filter: str | None = Query(
        None, alias="status", description="verified | unverified | flagged"
    ),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> RecordSearchResponseRead:
    """Ricerca paginata di record, con filtri combinabili.

    Sostituisce/estende il vecchio `POST /records/search` (lookup esatto per
    telefono, mantenuto sotto per compatibilità) con l'endpoint realmente
    atteso dalla UI: `frontend/src/api/records.ts:searchRecords` chiama
    `GET /records/search?phone=...&source=...&status=...&date_from=...
    &date_to=...&page=...&page_size=...` aspettandosi una lista paginata.
    """
    # Subquery di aggregazione per annuncio: occorrenze, fonti distinte,
    # prima/ultima apparizione. Un Record può avere zero annunci solo in una
    # finestra temporale transitoria (appena creato, prima dell'associazione
    # del primo annuncio): usiamo un JOIN (non LEFT JOIN) deliberatamente,
    # perché un record "vuoto" non ha comunque nulla di sensato da mostrare
    # nei risultati di ricerca (titolo canonico, date...).
    ad_agg = (
        select(
            Advertisement.record_id.label("record_id"),
            func.count(Advertisement.id).label("occurrences_count"),
            func.count(func.distinct(Advertisement.source_id)).label("sources_count"),
            func.min(Advertisement.first_seen_at).label("first_seen_at"),
            func.max(Advertisement.last_seen_at).label("last_seen_at"),
        )
        .group_by(Advertisement.record_id)
        .subquery()
    )

    canonical_ad = aliased(Advertisement)

    base_stmt = (
        select(
            Record.id,
            Record.phone_encrypted,
            canonical_ad.title,
            canonical_ad.confidence,
            ad_agg.c.occurrences_count,
            ad_agg.c.sources_count,
            ad_agg.c.first_seen_at,
            ad_agg.c.last_seen_at,
        )
        .join(ad_agg, ad_agg.c.record_id == Record.id)
        .outerjoin(canonical_ad, canonical_ad.id == Record.canonical_ad_id)
    )

    conditions = []

    if phone:
        # Vedi app/services/record_search.py:looks_like_full_phone per la
        # motivazione: un filtro "phone" che non sembra un numero completo
        # viene silenziosamente ignorato (non esiste modo di fare una
        # ricerca a prefisso sull'hash di lookup), la ricerca prosegue sugli
        # altri criteri invece di restituire un errore o un risultato vuoto.
        if looks_like_full_phone(phone):
            conditions.append(Record.phone_lookup_hash == phone_lookup_hash(phone))

    if source:
        source_exists = (
            select(Advertisement.id)
            .join(Source, Source.id == Advertisement.source_id)
            .where(
                Advertisement.record_id == Record.id,
                or_(Source.slug == source, Source.name == source),
            )
        )
        conditions.append(source_exists.exists())

    if date_from:
        conditions.append(ad_agg.c.last_seen_at >= date_from)
    if date_to:
        conditions.append(ad_agg.c.first_seen_at <= date_to)

    if status_filter == "verified":
        conditions.append(canonical_ad.confidence >= VERIFIED_CONFIDENCE_THRESHOLD)
    elif status_filter == "unverified":
        conditions.append(
            or_(
                canonical_ad.confidence < VERIFIED_CONFIDENCE_THRESHOLD,
                canonical_ad.confidence.is_(None),
            )
        )
    elif status_filter == "flagged":
        # Nessun meccanismo di segnalazione manuale è implementato oggi (vedi
        # app/services/record_search.py): nessun record può avere questo
        # status, quindi la query restituisce correttamente zero risultati
        # invece di ignorare il filtro.
        conditions.append(false())

    if conditions:
        base_stmt = base_stmt.where(and_(*conditions))

    total = (
        await db.execute(select(func.count()).select_from(base_stmt.subquery()))
    ).scalar_one()

    page_stmt = (
        base_stmt.order_by(ad_agg.c.last_seen_at.desc())
        .limit(page_size)
        .offset((page - 1) * page_size)
    )
    rows = (await db.execute(page_stmt)).all()

    results = [
        RecordSearchResultRead(
            id=row.id,
            phone=_safe_decrypt_phone(row.phone_encrypted),
            canonical_title=row.title or "(Senza titolo)",
            sources_count=row.sources_count or 0,
            occurrences_count=row.occurrences_count or 0,
            first_seen_at=row.first_seen_at,
            last_seen_at=row.last_seen_at,
            status=confidence_to_status(row.confidence),
        )
        for row in rows
    ]

    return RecordSearchResponseRead(results=results, total=total, page=page, page_size=page_size)


@router.post("/search", response_model=RecordDetail | None)
async def search_record_by_phone(
    payload: RecordSearchRequest,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> RecordDetail | None:
    """Lookup legacy: un Record esatto dato un numero di telefono completo.

    Non risulta usato da `frontend/src/api/*.ts` (che usa esclusivamente
    `GET /records/search`, sopra): lo lasciamo per compatibilità con
    eventuali altri consumatori dell'API (es. script interni, `/docs`) dato
    che resta un'operazione legittima e già correttamente implementata
    (hash di lookup, mai il numero in chiaro).
    """
    lookup_hash = phone_lookup_hash(payload.phone)

    result = await db.execute(
        select(Record)
        .options(selectinload(Record.advertisements))
        .where(Record.phone_lookup_hash == lookup_hash)
    )
    record = result.scalar_one_or_none()
    if record is None:
        return None
    return RecordDetail.model_validate(record)


@router.get("/{record_id}", response_model=RecordOverviewRead)
async def get_record_overview(
    record_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> RecordOverviewRead:
    """Dettaglio di un Record per la tab "Overview" (vedi
    `frontend/src/routes/records/RecordOverviewTab.tsx`)."""
    record = await _get_record_or_404(db, record_id)

    agg_row = (
        await db.execute(
            select(
                func.count(Advertisement.id),
                func.count(func.distinct(Advertisement.source_id)),
                func.min(Advertisement.first_seen_at),
                func.max(Advertisement.last_seen_at),
            ).where(Advertisement.record_id == record_id)
        )
    ).one()
    occurrences_count, sources_count, first_seen_at, last_seen_at = agg_row

    canonical_ad = (
        await db.get(Advertisement, record.canonical_ad_id) if record.canonical_ad_id else None
    )
    confidence = canonical_ad.confidence if canonical_ad else None

    return RecordOverviewRead(
        id=record.id,
        phone=_safe_decrypt_phone(record.phone_encrypted),
        canonical_title=(canonical_ad.title if canonical_ad else None) or "(Senza titolo)",
        canonical_description=(canonical_ad.description if canonical_ad else None) or "",
        confidence_score=round((confidence or 0.0) * 100, 1),
        sources_count=sources_count or 0,
        occurrences_count=occurrences_count or 0,
        # Fallback su created_at del Record se non ha ancora annunci (caso
        # limite: record appena creato, non dovrebbe normalmente accadere
        # dato che un record nasce sempre da almeno un annuncio scrapato).
        first_seen_at=first_seen_at or record.created_at,
        last_seen_at=last_seen_at or record.updated_at,
        status=confidence_to_status(confidence),
        # Nessun sistema di tag/etichette manuali è implementato lato
        # dominio (nessuna tabella dedicata): la UI gestisce già
        # correttamente una lista vuota (vedi RecordOverviewTab.tsx, la
        # sezione "Tags" è renderizzata solo se non vuota).
        tags=[],
    )


@router.get("/{record_id}/occurrences", response_model=list[RecordOccurrenceRead])
async def get_record_occurrences(
    record_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[RecordOccurrenceRead]:
    """Tutti gli annunci (`Advertisement`) collegati al record, con il flag
    `isCanonical` per l'annuncio attualmente selezionato come canonico."""
    record = await _get_record_or_404(db, record_id)

    stmt = (
        select(Advertisement, Source.name, Source.slug)
        .join(Source, Source.id == Advertisement.source_id)
        .where(Advertisement.record_id == record_id)
        .order_by(Advertisement.scraped_at.desc())
    )
    rows = (await db.execute(stmt)).all()

    return [
        RecordOccurrenceRead(
            id=ad.id,
            source_name=source_name,
            source_code=source_slug,
            title=ad.title or "(Senza titolo)",
            url=ad.source_url,
            scraped_at=ad.scraped_at,
            is_canonical=(ad.id == record.canonical_ad_id),
            match_confidence=round(ad.confidence * 100, 1),
        )
        for ad, source_name, source_slug in rows
    ]


def _media_object_url(media: Media, *, variant: str) -> str:
    """URL "placeholder" verso l'oggetto media in MinIO.

    TODO: la generazione di un vero URL firmato (presigned, con scadenza)
    richiede l'integrazione con il client MinIO (vedi le variabili
    `MINIO_*` in `app/config.py`), non ancora implementata in questo
    scaffold — lo stesso gap è documentato per `GET /exports/{id}/download`.
    Per ora restituiamo un path deterministico basato sulla object_key, così
    il frontend ha comunque un valore stabile da mostrare/collegare mentre
    la generazione reale viene implementata.
    """
    if variant == "derived" and media.derived_object_key:
        key = media.derived_object_key
    else:
        key = media.original_object_key
    return f"/media-objects/{key}"


@router.get("/{record_id}/media", response_model=list[RecordMediaRead])
async def get_record_media(
    record_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[RecordMediaRead]:
    """Tutti i media associati agli annunci del record."""
    await _get_record_or_404(db, record_id)

    stmt = (
        select(Media, Source.name)
        .join(Advertisement, Advertisement.id == Media.advertisement_id)
        .join(Source, Source.id == Advertisement.source_id)
        .where(Advertisement.record_id == record_id)
        .order_by(Media.created_at.desc())
    )
    rows = (await db.execute(stmt)).all()

    results: list[RecordMediaRead] = []
    for media, source_name in rows:
        # Scelta "fail-safe" deliberata: solo la classificazione "safe"
        # esplicita produce sensitivity="safe". Un media "unclassified" (non
        # ancora passato dal classificatore) viene trattato come "explicit"
        # anziché "safe": in un contesto sensibile come questo, è preferibile
        # sovra-proteggere un contenuto non ancora verificato piuttosto che
        # rischiare di mostrarlo come sicuro per default.
        sensitivity = "safe" if media.classification == "safe" else "explicit"
        media_type = "video" if media.mime_type.startswith("video/") else "image"
        results.append(
            RecordMediaRead(
                id=media.id,
                url=_media_object_url(media, variant="original"),
                thumbnail_url=_media_object_url(media, variant="derived"),
                type=media_type,
                sensitivity=sensitivity,
                source_name=source_name,
                added_at=media.created_at,
            )
        )
    return results


def _audit_detail(row: AuditLog) -> str:
    if row.details_json:
        return json.dumps(row.details_json, ensure_ascii=False)
    return f"{row.entity_type} {row.entity_id or ''}".strip()


@router.get("/{record_id}/history", response_model=list[RecordHistoryEventRead])
async def get_record_history(
    record_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[RecordHistoryEventRead]:
    """Storico "unificato" del record.

    Non esiste una singola tabella di storico per Record: uniamo tre fonti
    diverse, ciascuna già pensata per tracciare un aspetto specifico:

    - `canonical_history`: cambi dell'annuncio canonico (automatici o
      override manuale di un operatore).
    - `media_classification_history`: riclassificazioni dei media collegati
      agli annunci del record (automatiche dal classificatore o manuali).
    - `audit_log`: azioni generiche esplicitamente audit-loggate che
      referenziano questo record come entità (es. rigenerazione riepilogo
      AI, vedi `POST /records/{id}/ai-summary/regenerate`).

    I tre elenchi vengono normalizzati sulla stessa forma e poi ordinati
    insieme per data decrescente.
    """
    await _get_record_or_404(db, record_id)

    canonical_rows = (
        await db.execute(
            select(CanonicalHistory, User.email)
            .outerjoin(User, User.id == CanonicalHistory.overridden_by_user_id)
            .where(CanonicalHistory.record_id == record_id)
        )
    ).all()

    media_rows = (
        await db.execute(
            select(MediaClassificationHistory, User.email)
            .join(Media, Media.id == MediaClassificationHistory.media_id)
            .join(Advertisement, Advertisement.id == Media.advertisement_id)
            .outerjoin(User, User.id == MediaClassificationHistory.changed_by_user_id)
            .where(Advertisement.record_id == record_id)
        )
    ).all()

    audit_rows = (
        await db.execute(
            select(AuditLog, User.email)
            .outerjoin(User, User.id == AuditLog.user_id)
            .where(AuditLog.entity_type == "record", AuditLog.entity_id == str(record_id))
        )
    ).all()

    events: list[RecordHistoryEventRead] = []

    for row, overridden_by_email in canonical_rows:
        is_manual_override = row.overridden_by_user_id is not None
        actor = "admin" if is_manual_override else "system"
        actor_label = (
            overridden_by_email
            if (is_manual_override and overridden_by_email)
            else "Regola automatica"
        )
        events.append(
            RecordHistoryEventRead(
                id=f"canonical:{row.id}",
                actor=actor,
                actor_label=actor_label,
                action="Cambio annuncio canonico",
                detail=row.reason,
                occurred_at=row.created_at,
            )
        )

    for row, changed_by_email in media_rows:
        actor = "admin" if row.manual_override else "ai"
        actor_label = (
            changed_by_email
            if (row.manual_override and changed_by_email)
            else "Classificatore automatico"
        )
        detail = f"{row.previous_classification or 'n/d'} -> {row.new_classification}"
        if row.confidence is not None:
            detail += f" (confidence={row.confidence:.2f})"
        events.append(
            RecordHistoryEventRead(
                id=f"media:{row.id}",
                actor=actor,
                actor_label=actor_label,
                action="Riclassificazione media",
                detail=detail,
                occurred_at=row.created_at,
            )
        )

    for row, actor_email in audit_rows:
        actor = "admin" if actor_email else "system"
        actor_label = actor_email or "Sistema"
        events.append(
            RecordHistoryEventRead(
                id=f"audit:{row.id}",
                actor=actor,
                actor_label=actor_label,
                action=row.action,
                detail=_audit_detail(row),
                occurred_at=row.created_at,
            )
        )

    events.sort(key=lambda e: e.occurred_at, reverse=True)
    return events


def _summary_version_fields(version: SummaryVersion) -> dict:
    """Campi comuni tra `RecordAiSummaryRead` (ultima versione) e
    `RecordAiSummaryVersionRead` (voce di storico) — evita di duplicare il
    parsing di `summary_json` nei due endpoint che lo consumano."""
    payload = version.summary_json or {}
    forum_information = payload.get("forum_information", [])
    forum_chatter = [
        entry.get("snippet", "")
        for entry in forum_information
        if isinstance(entry, dict) and entry.get("snippet")
    ]
    # SummaryPayload.sources è una semplice lista di URL (vedi
    # app/services/summary_generator.py): non porta un "nome fonte"
    # separato. Usiamo l'URL anche come nome finché il generatore non
    # produrrà una struttura più ricca (es. {name, url}).
    sources_used = [
        SourceUsedRead(name=url, url=url) for url in payload.get("sources", []) if url
    ]
    return {
        "generated_at": version.created_at,
        "executive_synthesis": payload.get("summary", ""),
        "unverified_claims": payload.get("unverified_claims", []),
        "forum_chatter": forum_chatter,
        "sources_used": sources_used,
    }


def _summary_version_to_schema(version: SummaryVersion) -> RecordAiSummaryRead:
    return RecordAiSummaryRead(**_summary_version_fields(version))


def _summary_version_to_versioned_schema(version: SummaryVersion) -> RecordAiSummaryVersionRead:
    return RecordAiSummaryVersionRead(**_summary_version_fields(version), version=version.version)


@router.get("/{record_id}/ai-summary/versions", response_model=list[RecordAiSummaryVersionRead])
async def get_record_ai_summary_versions(
    record_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[RecordAiSummaryVersionRead]:
    """Storico COMPLETO delle versioni del riepilogo AI (a differenza di
    `GET /{record_id}/ai-summary`, che restituisce solo l'ultima): permette
    alla UI di offrire un selettore storico invece di mostrare solo il
    riepilogo più recente (`frontend/src/routes/records/
    RecordAiSummaryTab.tsx`). Ordinate dalla più recente alla più vecchia.
    """
    await _get_record_or_404(db, record_id)

    stmt = (
        select(SummaryVersion)
        .where(SummaryVersion.record_id == record_id)
        .order_by(SummaryVersion.version.desc())
    )
    versions = (await db.execute(stmt)).scalars().all()
    return [_summary_version_to_versioned_schema(v) for v in versions]


@router.get(
    "/{record_id}/ai-summary",
    response_model=RecordAiSummaryRead,
    responses={204: {"description": "Nessun riepilogo AI ancora generato per questo record."}},
)
async def get_record_ai_summary(
    record_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Ultima versione del riepilogo AI per il record.

    Se non è mai stato generato nessun riepilogo, rispondiamo 204 No
    Content invece di 404: `frontend/src/api/client.ts` mappa esplicitamente
    uno `status === 204` a `undefined`, e
    `frontend/src/routes/records/RecordAiSummaryTab.tsx` già gestisce
    `summary.data` falsy mostrando "No AI summary available" — un 404
    verrebbe invece trattato come errore di query (`summary.isError`),
    mostrando un messaggio di errore fuorviante per uno stato in realtà
    normale ("non ancora generato").
    """
    await _get_record_or_404(db, record_id)

    stmt = (
        select(SummaryVersion)
        .where(SummaryVersion.record_id == record_id)
        .order_by(SummaryVersion.version.desc())
        .limit(1)
    )
    version = (await db.execute(stmt)).scalar_one_or_none()
    if version is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return _summary_version_to_schema(version)


@router.post(
    "/{record_id}/ai-summary/regenerate",
    response_model=RecordAiSummaryRead,
    status_code=status.HTTP_201_CREATED,
)
async def regenerate_record_ai_summary(
    record_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin", "operator")),
) -> RecordAiSummaryRead:
    """Rigenera il riepilogo AI del record, salvando una nuova
    `SummaryVersion` (versionata, non sovrascrive le precedenti).

    Riservato ad admin/operator: rigenerare consuma risorse (in futuro,
    chiamate a un LLM reale) e va quindi avviato solo da chi ha
    responsabilità operativa, non dai soli viewer — stesso criterio già
    applicato a `POST /sources/{id}/scan`.

    Usa `TemplateSummaryGenerator` (vedi `app/services/summary_generator.py`):
    è l'implementazione placeholder, senza chiamata a un LLM reale — il
    punto di sostituzione futuro è documentato in quel modulo.
    """
    record = await _get_record_or_404(db, record_id)

    ads_result = await db.execute(select(Advertisement).where(Advertisement.record_id == record_id))
    advertisements = ads_result.scalars().all()

    generator = TemplateSummaryGenerator()
    # Nessuna pipeline di raccolta forum è implementata: passiamo una lista
    # vuota di snippet, coerente con lo stato attuale del resto del sistema.
    payload = generator.generate(record, advertisements, forum_snippets=[])

    last_version = (
        await db.execute(
            select(func.max(SummaryVersion.version)).where(SummaryVersion.record_id == record_id)
        )
    ).scalar_one()
    new_version_number = (last_version or 0) + 1

    version = SummaryVersion(
        record_id=record_id,
        version=new_version_number,
        summary_json=payload.as_dict(),
        model_name=TemplateSummaryGenerator.MODEL_NAME,
    )
    db.add(version)

    await log_action(
        db,
        user_id=user.id,
        action="regenerate_ai_summary",
        entity_type="record",
        entity_id=str(record_id),
        details={"version": new_version_number},
    )

    await db.commit()
    await db.refresh(version)

    return _summary_version_to_schema(version)
