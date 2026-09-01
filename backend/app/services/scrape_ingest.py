"""Orchestrazione dello scraping reale: dalla configurazione di una fonte
(`Source.scrape_config`) alla persistenza di `Record`/`Advertisement`/
`Media`, passando per dedup e selezione canonica.

Prima pipeline di ingestione end-to-end del progetto: finora
`app/workers/tasks_scraper.py` si limitava a loggare un TODO. Divisa in
due fasi deliberatamente separate:

1. `collect_ads` — SOLO rete (async, via `GenericScraper`), nessuna
   scrittura su DB: testabile con fixture HTML locali, senza toccare
   Postgres (vedi `backend/tests/scrapers/`).
2. `persist_collected_ads` — SOLO scrittura su DB (sync, stessa sessione
   sincrona già usata da `tasks_scraper.py`), nessuna rete: riusa
   `app/services/dedup.py`, `phone_crypto.py`, `canonical.py`, già
   testati in isolamento.

Il worker Celery (`run_scrape_source`) chiama prima la fase 1 (dentro
`asyncio.run`), poi la fase 2.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.advertisement import Advertisement
from app.models.canonical_history import CanonicalHistory
from app.models.media import Media
from app.models.record import Record
from app.models.sources import Source
from app.scrapers.generic import GenericScraper, PageFetchError, RobotsDisallowedError
from app.services.canonical import (
    CandidateAdvertisement,
    CandidateSource,
    SourcePriority,
    build_history_entry,
    resolve_canonical,
)
from app.services.dedup import content_sha256
from app.services.media_processing import MediaValidationError, probe_video, validate_image
from app.services.media_storage import sniff_mime_type, upload_media_object
from app.services.phone_crypto import (
    PhoneCryptoError,
    encrypt_phone,
    normalize_phone,
    phone_lookup_hash,
)

logger = logging.getLogger(__name__)


@dataclass
class CollectedAd:
    normalized: dict
    media_bytes: list[bytes] = field(default_factory=list)


@dataclass
class ScrapeErrorDetail:
    url: str
    message: str


@dataclass
class CollectionResult:
    ads: list[CollectedAd]
    errors: list[ScrapeErrorDetail] = field(default_factory=list)

    @property
    def errors_count(self) -> int:
        return len(self.errors)


async def collect_ads(source: Source) -> CollectionResult:
    """Fase 1: esegue davvero `discover -> scrape_ad -> normalize ->
    download_media` per la fonte, senza toccare il database.

    Un URL vietato da robots.txt, o irraggiungibile, viene saltato e
    contato come errore — non interrompe l'intero run (a meno che sia
    `discover()` stesso a fallire, nel qual caso non c'è nulla da fare per
    questa fonte in questo run).
    """
    scraper = GenericScraper(
        slug=source.slug, base_url=source.base_url, config=source.scrape_config
    )

    try:
        try:
            ad_urls = await scraper.discover()
        except RobotsDisallowedError as exc:
            logger.warning(
                "robots.txt vieta l'accesso alla pagina di elenco per '%s': %s", source.slug, exc
            )
            return CollectionResult(
                ads=[], errors=[ScrapeErrorDetail(url=exc.url, message=str(exc))]
            )
        except (httpx.HTTPError, PageFetchError) as exc:
            logger.warning("Errore durante discover() per '%s': %s", source.slug, exc)
            return CollectionResult(
                ads=[], errors=[ScrapeErrorDetail(url=source.base_url, message=str(exc))]
            )

        collected: list[CollectedAd] = []
        errors: list[ScrapeErrorDetail] = []

        for url in ad_urls:
            try:
                raw = await scraper.scrape_ad(url)
            except (RobotsDisallowedError, httpx.HTTPError, PageFetchError) as exc:
                logger.info("Annuncio saltato (%s): %s", url, exc)
                errors.append(ScrapeErrorDetail(url=url, message=str(exc)))
                continue

            normalized = scraper.normalize(raw)
            if not normalized.get("phone_raw"):
                # Senza un telefono non c'è modo di deduplicare/collegare
                # l'annuncio a un Record: lo scartiamo esplicitamente invece di
                # crearne uno "orfano".
                errors.append(
                    ScrapeErrorDetail(url=url, message="Nessun numero di telefono estratto.")
                )
                continue

            media_bytes: list[bytes] = []
            try:
                media_bytes = await scraper.download_media(normalized)
            except Exception:  # noqa: BLE001 - il download media è "best effort"
                logger.exception(
                    "Download media fallito per l'annuncio %s (annuncio comunque salvato).", url
                )

            collected.append(CollectedAd(normalized=normalized, media_bytes=media_bytes))

        return CollectionResult(ads=collected, errors=errors)
    finally:
        await scraper.aclose()


def _get_or_create_record(session: Session, phone_lookup: str, phone_normalized: str) -> Record:
    record = session.execute(
        select(Record).where(Record.phone_lookup_hash == phone_lookup)
    ).scalar_one_or_none()
    if record is not None:
        return record

    record = Record(phone_encrypted=encrypt_phone(phone_normalized), phone_lookup_hash=phone_lookup)
    session.add(record)
    session.flush()  # popola record.id per l'uso immediato sotto
    return record


def _upsert_advertisement(
    session: Session, record: Record, source: Source, normalized: dict
) -> tuple[Advertisement, bool]:
    """Trova un Advertisement esistente per (record, fonte, URL) e lo
    aggiorna, o ne crea uno nuovo. Restituisce `(advertisement, is_new)`.

    L'idempotenza è per URL esatto: ri-scrapare lo stesso annuncio non
    duplica righe, aggiorna solo `last_seen_at`/`scraped_at`/contenuto.
    """
    now = datetime.now(UTC)
    source_url = normalized["source_url"]

    existing = session.execute(
        select(Advertisement).where(
            Advertisement.record_id == record.id,
            Advertisement.source_id == source.id,
            Advertisement.source_url == source_url,
        )
    ).scalar_one_or_none()

    content_hash = content_sha256(
        f"{normalized.get('title') or ''}\n{normalized.get('description') or ''}"
    )

    if existing is not None:
        existing.title = normalized.get("title")
        existing.description = normalized.get("description")
        existing.content_hash = content_hash
        existing.last_seen_at = now
        existing.scraped_at = now
        session.add(existing)
        return existing, False

    advertisement = Advertisement(
        record_id=record.id,
        source_id=source.id,
        source_url=source_url,
        title=normalized.get("title"),
        description=normalized.get("description"),
        content_hash=content_hash,
        confidence=1.0,
        status="active",
    )
    session.add(advertisement)
    session.flush()
    return advertisement, True


def _persist_media(
    session: Session,
    record_id: uuid.UUID,
    advertisement: Advertisement,
    media_bytes_list: list[bytes],
) -> list[uuid.UUID]:
    """Validate and persist originals; expensive processing starts after commit."""
    import hashlib

    media_ids: list[uuid.UUID] = []
    for data in media_bytes_list:
        sha256 = hashlib.sha256(data).hexdigest()
        already_exists = session.execute(
            select(Media.id).where(
                Media.advertisement_id == advertisement.id, Media.sha256 == sha256
            )
        ).scalar_one_or_none()
        if already_exists:
            continue

        mime_type = sniff_mime_type(data)
        try:
            metadata = (
                validate_image(data, mime_type)
                if mime_type.startswith("image/")
                else probe_video(data, mime_type)
            )
        except MediaValidationError:
            logger.warning("Media rifiutato dalla validazione per annuncio %s.", advertisement.id)
            continue
        try:
            object_key = upload_media_object(record_id, data, mime_type)
        except Exception:  # noqa: BLE001
            logger.exception(
                "Upload MinIO fallito per un media dell'annuncio %s.", advertisement.id
            )
            continue

        media = Media(
            advertisement_id=advertisement.id,
            original_object_key=object_key,
            sha256=sha256,
            mime_type=mime_type,
            classification="unclassified",
            processing_status="pending",
            review_status="required",
            safety_signals={},
            file_size_bytes=metadata.file_size_bytes,
            width=metadata.width,
            height=metadata.height,
            duration_seconds=metadata.duration_seconds,
        )
        session.add(media)
        session.flush()
        media_ids.append(media.id)
    return media_ids


def _recompute_canonical(session: Session, record: Record) -> None:
    rows = session.execute(
        select(Advertisement, Source)
        .join(Source, Source.id == Advertisement.source_id)
        .where(Advertisement.record_id == record.id)
    ).all()

    candidates = [
        CandidateAdvertisement(
            id=ad.id,
            source=CandidateSource(id=src.id, slug=src.slug, priority=SourcePriority[src.priority]),
            scraped_at=ad.scraped_at,
            status=ad.status,
            title=ad.title,
            description=ad.description,
            source_url=ad.source_url,
        )
        for ad, src in rows
    ]

    try:
        resolution = resolve_canonical(candidates)
    except ValueError:
        return  # nessun annuncio "active": nulla da fare (caso limite)

    if record.canonical_ad_id == resolution.chosen.id:
        return

    entry = build_history_entry(record.id, record.canonical_ad_id, resolution)
    session.add(CanonicalHistory(**entry))
    record.canonical_ad_id = resolution.chosen.id
    session.add(record)


def persist_collected_ads(session: Session, source: Source, result: CollectionResult) -> dict:
    """Fase 2: scrive su DB gli annunci raccolti dalla fase 1 (dedup per
    telefono, upsert per URL, upload media, ricalcolo canonico). Nessuna
    richiesta di rete qui: solo operazioni DB (+ upload MinIO, anch'esso
    locale/interno alla rete Docker, non verso la fonte scrapata)."""
    items_new = 0
    persist_errors: list[ScrapeErrorDetail] = []
    media_ids: list[uuid.UUID] = []

    for item in result.ads:
        phone_raw = item.normalized["phone_raw"]
        source_url = item.normalized.get("source_url") or source.base_url
        try:
            phone_normalized = normalize_phone(phone_raw)
        except PhoneCryptoError as exc:
            persist_errors.append(
                ScrapeErrorDetail(url=source_url, message=f"Telefono non valido: {exc}")
            )
            continue

        lookup_hash = phone_lookup_hash(phone_normalized)
        record = _get_or_create_record(session, lookup_hash, phone_normalized)

        advertisement, is_new = _upsert_advertisement(session, record, source, item.normalized)
        if is_new:
            items_new += 1

        if item.media_bytes:
            media_ids.extend(_persist_media(session, record.id, advertisement, item.media_bytes))

        _recompute_canonical(session, record)
        session.commit()

    all_errors = result.errors + persist_errors
    return {
        "items_found": len(result.ads) + result.errors_count,
        "items_new": items_new,
        "errors": all_errors,
        "errors_count": len(all_errors),
        "media_ids": [str(media_id) for media_id in media_ids],
    }
