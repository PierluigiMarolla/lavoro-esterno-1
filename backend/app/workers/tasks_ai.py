"""Asynchronous, budget-gated OpenAI summary generation."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from datetime import UTC, datetime

import redis
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.models.advertisement import Advertisement
from app.models.audit_log import AuditLog
from app.models.sources import Source
from app.models.summary_generation_jobs import SummaryGenerationJob
from app.models.summary_versions import SummaryVersion
from app.services.summary_generator import OpenAISummaryGenerator
from app.workers.celery_app import celery_app
from app.workers.tasks_scraper import SyncSessionLocal

logger = logging.getLogger(__name__)

_URL_RE = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)
_PHONE_RE = re.compile(r"(?<!\w)(?:\+?\d[\s().-]*){8,15}(?!\w)")


class AIDisabledError(RuntimeError):
    pass


def _redis() -> redis.Redis:
    return redis.from_url(settings.REDIS_URL, decode_responses=True)


def _reserve_budget(user_id: uuid.UUID, estimated_tokens: int) -> tuple[str, int]:
    if (
        not settings.OPENAI_API_KEY
        or settings.AI_USER_DAILY_REQUEST_LIMIT <= 0
        or settings.AI_GLOBAL_DAILY_TOKEN_BUDGET <= 0
        or settings.AI_PROVIDER_REQUESTS_PER_MINUTE <= 0
    ):
        raise AIDisabledError("OpenAI disabilitata: configurare chiave e budget AI.")
    client = _redis()
    day = datetime.now(UTC).strftime("%Y%m%d")
    minute = datetime.now(UTC).strftime("%Y%m%d%H%M")
    user_key = f"ai:user:{user_id}:{day}"
    rpm_key = f"ai:rpm:{minute}"
    token_key = f"ai:tokens:{day}"
    user_count = client.incr(user_key)
    client.expire(user_key, 172800)
    rpm_count = client.incr(rpm_key)
    client.expire(rpm_key, 120)
    if user_count > settings.AI_USER_DAILY_REQUEST_LIMIT:
        raise AIDisabledError("Limite giornaliero per utente esaurito.")
    if rpm_count > settings.AI_PROVIDER_REQUESTS_PER_MINUTE:
        raise AIDisabledError("Rate limit OpenAI applicativo raggiunto.")
    reserved = client.incrby(token_key, estimated_tokens)
    client.expire(token_key, 172800)
    if reserved > settings.AI_GLOBAL_DAILY_TOKEN_BUDGET:
        client.decrby(token_key, estimated_tokens)
        raise AIDisabledError("Budget token AI giornaliero esaurito.")
    return token_key, estimated_tokens


def _release_reservation(reservation: tuple[str, int] | None) -> None:
    if reservation:
        _redis().decrby(reservation[0], reservation[1])


def _is_retryable_provider_error(exc: Exception) -> bool:
    """Retry only transient OpenAI transport, timeout, 429 and 5xx failures."""
    try:
        from openai import APIConnectionError, APIStatusError, APITimeoutError, RateLimitError
    except ImportError:  # pragma: no cover - dependency is mandatory in production
        return False
    if isinstance(exc, (APIConnectionError, APITimeoutError, RateLimitError)):
        return True
    return isinstance(exc, APIStatusError) and exc.status_code >= 500


def _sanitized_input(rows: list[tuple[Advertisement, Source]]) -> tuple[dict, dict[str, str]]:
    source_refs: dict[uuid.UUID, str] = {}
    source_urls: dict[str, str] = {}
    advertisements = []
    for advertisement, source in rows:
        ref = source_refs.setdefault(source.id, f"source-{len(source_refs) + 1}")
        source_urls[ref] = advertisement.source_url
        advertisements.append(
            {
                "source_ref": ref,
                "title": _redact_external_identifiers(advertisement.title or "")[:500],
                "description": _redact_external_identifiers(advertisement.description or "")[:4000],
                "scraped_at": advertisement.scraped_at.isoformat(),
            }
        )
    payload = {"advertisements": advertisements, "forum_snippets": []}
    encoded = json.dumps(payload, ensure_ascii=False)
    if len(encoded) > settings.AI_MAX_INPUT_CHARS:
        raise ValueError("Input riepilogo oltre AI_MAX_INPUT_CHARS.")
    return payload, source_urls


def _redact_external_identifiers(value: str) -> str:
    value = _URL_RE.sub("[URL REDACTED]", value)
    return _PHONE_RE.sub("[PHONE REDACTED]", value)


def summary_input_hash(payload: dict) -> str:
    envelope = {
        "model": settings.OPENAI_MODEL,
        "prompt_version": settings.OPENAI_PROMPT_VERSION,
        "payload": payload,
    }
    return hashlib.sha256(
        json.dumps(envelope, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


@celery_app.task(name="app.workers.tasks_ai.generate_summary", bind=True, max_retries=3)
def generate_summary(self, job_id: str) -> dict:
    session = SyncSessionLocal()
    job_uuid = uuid.UUID(job_id)
    token_reservation: tuple[str, int] | None = None
    try:
        job = session.get(SummaryGenerationJob, job_uuid)
        if job is None:
            return {"status": "failed", "reason": "job_not_found"}
        if job.status == "completed":
            return {"status": "completed", "job_id": job_id, "idempotent": True}
        job.status = "processing"
        job.started_at = datetime.now(UTC)
        job.error_message = None
        session.commit()

        rows = session.execute(
            select(Advertisement, Source)
            .join(Source, Source.id == Advertisement.source_id)
            .where(Advertisement.record_id == job.record_id)
            .order_by(Advertisement.scraped_at, Advertisement.id)
        ).all()
        payload, source_urls = _sanitized_input(rows)
        input_hash = summary_input_hash(payload)
        job.input_hash = input_hash

        cached = session.execute(
            select(SummaryVersion).where(
                SummaryVersion.record_id == job.record_id,
                SummaryVersion.input_hash == input_hash,
                SummaryVersion.model_name == settings.OPENAI_MODEL,
                SummaryVersion.prompt_version == settings.OPENAI_PROMPT_VERSION,
            )
        ).scalar_one_or_none()
        if cached is not None:
            job.status = "completed"
            job.result_version = cached.version
            job.cache_hit = True
            job.completed_at = datetime.now(UTC)
            session.commit()
            return {"status": "completed", "job_id": job_id, "cache_hit": True}

        estimated_tokens = max(1, len(json.dumps(payload, ensure_ascii=False)) // 4) + 2000
        token_reservation = _reserve_budget(job.requested_by_user_id, estimated_tokens)
        generated = OpenAISummaryGenerator().generate_structured(payload)
        result_payload = generated.payload.as_dict()
        result_payload["sources"] = [
            source_urls[ref] for ref in generated.payload.sources if ref in source_urls
        ]

        version_number = (
            session.execute(
                select(func.max(SummaryVersion.version)).where(
                    SummaryVersion.record_id == job.record_id
                )
            ).scalar_one()
            or 0
        ) + 1
        version = SummaryVersion(
            record_id=job.record_id,
            version=version_number,
            summary_json=result_payload,
            model_provider="openai",
            model_name=settings.OPENAI_MODEL,
            prompt_version=settings.OPENAI_PROMPT_VERSION,
            input_hash=input_hash,
            input_tokens=generated.input_tokens,
            output_tokens=generated.output_tokens,
            cached_input_tokens=generated.cached_input_tokens,
            generation_job_id=job.id,
        )
        session.add(version)
        job.status = "completed"
        job.result_version = version_number
        job.completed_at = datetime.now(UTC)
        session.add(
            AuditLog(
                user_id=job.requested_by_user_id,
                action="regenerate_ai_summary",
                entity_type="record",
                entity_id=str(job.record_id),
                details_json={
                    "version": version_number,
                    "model": settings.OPENAI_MODEL,
                    "prompt_version": settings.OPENAI_PROMPT_VERSION,
                    "input_tokens": generated.input_tokens,
                    "output_tokens": generated.output_tokens,
                },
            )
        )
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            cached = session.execute(
                select(SummaryVersion).where(
                    SummaryVersion.record_id == job.record_id,
                    SummaryVersion.input_hash == input_hash,
                    SummaryVersion.model_name == settings.OPENAI_MODEL,
                    SummaryVersion.prompt_version == settings.OPENAI_PROMPT_VERSION,
                )
            ).scalar_one()
            job = session.get(SummaryGenerationJob, job_uuid)
            job.status, job.cache_hit = "completed", True
            job.result_version, job.completed_at = cached.version, datetime.now(UTC)
            session.commit()
        if token_reservation:
            actual = generated.input_tokens + generated.output_tokens
            _redis().incrby(token_reservation[0], actual - token_reservation[1])
        return {"status": "completed", "job_id": job_id, "version": job.result_version}
    except AIDisabledError as exc:
        _release_reservation(token_reservation)
        session.rollback()
        job = session.get(SummaryGenerationJob, job_uuid)
        if job:
            job.status, job.error_message = "failed", str(exc)
            job.completed_at = datetime.now(UTC)
            session.commit()
        return {"status": "failed", "job_id": job_id, "reason": str(exc)}
    except Exception as exc:
        _release_reservation(token_reservation)
        session.rollback()
        if _is_retryable_provider_error(exc) and self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=2 ** (self.request.retries + 1)) from exc
        job = session.get(SummaryGenerationJob, job_uuid)
        if job:
            job.status = "failed"
            job.error_message = "Generazione AI non riuscita; consultare i log del worker."
            job.completed_at = datetime.now(UTC)
            session.commit()
        logger.exception("Generazione riepilogo fallita per job %s", job_id)
        return {"status": "failed", "job_id": job_id}
    finally:
        session.close()
