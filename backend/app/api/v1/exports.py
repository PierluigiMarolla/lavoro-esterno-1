"""Endpoint per la richiesta e gestione di esportazioni (ExportJob)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_db
from app.models.export_jobs import ExportJob
from app.models.users import User
from app.schemas.exports import DownloadUrlResponse, ExportJobCreate, ExportJobOut
from app.security.deps import require_role
from app.services.audit import log_action

router = APIRouter()

# Numero massimo di job restituiti da GET /exports: il frontend
# (`fetchExportJobs`) non passa parametri di paginazione, quindi
# restituiamo semplicemente gli N più recenti invece di ogni job mai creato.
_RECENT_EXPORTS_LIMIT = 100


def _record_count(job: ExportJob) -> int:
    """Numero di record coperti dal job, per il campo `recordCount` atteso
    dal frontend. Un job "singolo" ha `record_id` valorizzato (1 record); un
    job "bulk" conserva l'elenco in `manifest_json["record_ids"]` (vedi
    `ExportJobCreate`); un bulk basato solo su `filters` (ricerca, non lista
    esplicita di id) non ha un conteggio noto finché il worker non lo
    processa: restituiamo 0 in quel caso."""
    if job.record_id is not None:
        return 1
    manifest = job.manifest_json or {}
    record_ids = manifest.get("record_ids")
    if isinstance(record_ids, list):
        return len(record_ids)
    return 0


def _download_url(job: ExportJob) -> str | None:
    """URL di download "placeholder" per un export pronto.

    TODO: la generazione di un vero URL firmato (presigned URL MinIO con
    scadenza) richiede l'integrazione col client MinIO (vedi le variabili
    `MINIO_*` in `app/config.py`) e, a monte, un worker che genera
    effettivamente il pacchetto e valorizza `object_key` — nessuno dei due è
    ancora implementato in questo scaffold (vedi PROGETTO.md). Qui ci
    limitiamo a costruire un path deterministico verso l'endpoint MinIO
    configurato quando `object_key` è già valorizzato, così l'endpoint
    dedicato (`GET /exports/{id}/download`) ha comunque un comportamento
    coerente da subito.
    """
    if not job.object_key:
        return None
    scheme = "https" if settings.MINIO_SECURE else "http"
    return f"{scheme}://{settings.MINIO_ENDPOINT}/{settings.MINIO_BUCKET}/{job.object_key}"


def _to_export_job_out(job: ExportJob, requested_by_email: str) -> ExportJobOut:
    return ExportJobOut(
        id=job.id,
        type=job.type,
        status=job.status,
        progress_pct=job.progress_percent,
        requested_by=requested_by_email,
        requested_at=job.requested_at,
        record_count=_record_count(job),
        download_url=_download_url(job),
    )


@router.post("", response_model=ExportJobOut, status_code=201)
async def create_export(
    payload: ExportJobCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin", "operator")),
) -> ExportJobOut:
    """Crea una richiesta di export in stato "pending".

    L'elaborazione effettiva (raccolta dei dati/media, scrittura su MinIO) è
    delegata a un worker asincrono non ancora implementato in questo
    scaffold (da aggiungere in app/workers/, analogamente a
    tasks_media.py/tasks_ai.py); qui ci limitiamo a persistere la richiesta
    in modo che l'API sia già utilizzabile end-to-end dal punto di vista del
    client.
    """
    record_ids = payload.record_ids or []
    single_record_id = record_ids[0] if len(record_ids) == 1 else None

    manifest: dict | None = None
    if len(record_ids) > 1:
        manifest = {"record_ids": [str(rid) for rid in record_ids]}
    if payload.filters:
        manifest = {**(manifest or {}), "filters": payload.filters}

    job = ExportJob(
        record_id=single_record_id,
        type=payload.type,
        status="pending",
        progress_percent=0,
        requested_by_user_id=user.id,
        manifest_json=manifest,
    )
    db.add(job)
    await log_action(
        db,
        user_id=user.id,
        action="create_export",
        entity_type="export_job",
        details={"type": payload.type, "record_count": len(record_ids)},
    )
    await db.commit()
    await db.refresh(job)

    return _to_export_job_out(job, requested_by_email=user.email)


@router.get("", response_model=list[ExportJobOut])
async def list_exports(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("admin", "operator")),
) -> list[ExportJobOut]:
    """Storico dei job di esportazione (i più recenti per primi).

    Riservato ad admin/operator, come la creazione: gli export possono
    contenere dati personali (numeri di telefono in chiaro nei formati
    "complete_media") e non sono quindi visibili ai soli viewer.
    """
    stmt = (
        select(ExportJob, User.email)
        .join(User, User.id == ExportJob.requested_by_user_id)
        .order_by(ExportJob.requested_at.desc())
        .limit(_RECENT_EXPORTS_LIMIT)
    )
    rows = (await db.execute(stmt)).all()
    return [_to_export_job_out(job, requested_by_email=email) for job, email in rows]


async def _get_export_or_404(db: AsyncSession, job_id: uuid.UUID) -> ExportJob:
    job = await db.get(ExportJob, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export non trovato.")
    return job


@router.post("/{job_id}/retry", response_model=ExportJobOut)
async def retry_export(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin", "operator")),
) -> ExportJobOut:
    """Reimposta un export fallito a "pending", pronto per essere
    ripreso dal worker (non ancora implementato, vedi `create_export`)."""
    job = await _get_export_or_404(db, job_id)
    if job.status != "failed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Solo un export in stato 'failed' può essere ripetuto.",
        )

    job.status = "pending"
    job.progress_percent = 0
    job.error_message = None
    job.completed_at = None
    db.add(job)
    await log_action(
        db, user_id=user.id, action="retry_export", entity_type="export_job", entity_id=str(job_id)
    )
    await db.commit()
    await db.refresh(job)

    requester = await db.get(User, job.requested_by_user_id)
    requested_by_email = requester.email if requester else "N/D"
    return _to_export_job_out(job, requested_by_email=requested_by_email)


@router.get("/{job_id}/download", response_model=DownloadUrlResponse)
async def get_export_download_url(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("admin", "operator")),
) -> DownloadUrlResponse:
    """URL di download del pacchetto di export.

    La generazione reale del pacchetto (worker + upload su MinIO) non è
    ancora implementata (vedi `_download_url` sopra e PROGETTO.md): finché
    `object_key` non è valorizzato non esiste alcun pacchetto da scaricare,
    quindi rispondiamo 409 Conflict con un messaggio esplicito invece di un
    URL rotto/finto.
    """
    job = await _get_export_or_404(db, job_id)
    url = _download_url(job)
    if url is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Il pacchetto di export non è ancora pronto per il download.",
        )
    return DownloadUrlResponse(url=url)
