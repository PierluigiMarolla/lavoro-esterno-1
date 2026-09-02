"""Celery worker that builds bounded ZIP exports without buffering media in RAM."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import tempfile
import uuid
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select, update

from app.config import settings
from app.models.advertisement import Advertisement
from app.models.export_jobs import ExportJob, ExportJobRecord
from app.models.media import Media
from app.models.record import Record
from app.models.sources import Source
from app.models.users import User
from app.services.media_storage import download_object_to_file, upload_file
from app.services.phone_crypto import decrypt_phone, mask_phone
from app.workers.celery_app import celery_app
from app.workers.tasks_scraper import SyncSessionLocal


def _csv_bytes(rows: list[dict], fieldnames: list[str]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8-sig")


def _safe_error(exc: Exception) -> str:
    if isinstance(exc, (ValueError, PermissionError)):
        return str(exc)[:500]
    return "Generazione export non riuscita; consultare i log del worker."


@celery_app.task(name="app.workers.tasks_exports.generate_export")
def generate_export(job_id: str) -> dict:
    job_uuid = uuid.UUID(job_id)
    session = SyncSessionLocal()
    claimed = session.execute(
        update(ExportJob)
        .where(ExportJob.id == job_uuid, ExportJob.status == "pending")
        .values(status="processing", progress_percent=1, started_at=datetime.now(UTC))
        .returning(ExportJob.id)
    ).scalar_one_or_none()
    session.commit()
    if claimed is None:
        existing = session.get(ExportJob, job_uuid)
        session.close()
        return {"status": existing.status if existing else "missing", "idempotent": True}

    archive_path: str | None = None
    try:
        job = session.get(ExportJob, job_uuid)
        requester = session.get(User, job.requested_by_user_id)
        if requester is None or not requester.is_active:
            raise PermissionError("Il richiedente non è più attivo.")
        can_clear = requester.role == "admin" or requester.can_view_clear_phone
        if job.include_clear_phone and not can_clear:
            raise PermissionError("Il permesso di esportare telefoni in chiaro è stato revocato.")

        record_ids = list(
            session.execute(
                select(ExportJobRecord.record_id)
                .where(ExportJobRecord.export_job_id == job.id)
                .order_by(ExportJobRecord.record_id)
            ).scalars()
        )
        if not record_ids or len(record_ids) > settings.EXPORT_MAX_RECORDS:
            raise ValueError("Scope export vuoto o oltre il limite configurato.")

        records_rows: list[dict] = []
        advertisement_rows: list[dict] = []
        media_manifest: list[dict] = []
        excluded_media: list[dict] = []
        file_manifest: list[dict] = []
        bytes_added = 0

        fd, archive_path = tempfile.mkstemp(prefix=f"export-{job.id}-", suffix=".zip")
        os.close(fd)
        with zipfile.ZipFile(
            archive_path, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True
        ) as archive:
            for index, record_id in enumerate(record_ids, start=1):
                record = session.get(Record, record_id)
                if record is None:
                    continue
                phone = decrypt_phone(record.phone_encrypted)
                records_rows.append(
                    {
                        "id": str(record.id),
                        "phone": phone if job.include_clear_phone else mask_phone(phone),
                        "canonical_ad_id": str(record.canonical_ad_id)
                        if record.canonical_ad_id
                        else None,
                        "created_at": record.created_at.isoformat(),
                        "updated_at": record.updated_at.isoformat(),
                    }
                )
                ad_rows = session.execute(
                    select(Advertisement, Source)
                    .join(Source, Source.id == Advertisement.source_id)
                    .where(Advertisement.record_id == record.id)
                    .order_by(Advertisement.scraped_at)
                ).all()
                for ad, source in ad_rows:
                    advertisement_rows.append(
                        {
                            "id": str(ad.id),
                            "record_id": str(record.id),
                            "source_id": str(source.id),
                            "source_name": source.name,
                            "source_url": ad.source_url,
                            "title": ad.title,
                            "description": ad.description,
                            "status": ad.status,
                            "confidence": ad.confidence,
                            "first_seen_at": ad.first_seen_at.isoformat(),
                            "last_seen_at": ad.last_seen_at.isoformat(),
                            "scraped_at": ad.scraped_at.isoformat(),
                        }
                    )
                    if job.type == "text_only":
                        continue
                    media_rows = session.execute(
                        select(Media).where(Media.advertisement_id == ad.id)
                    ).scalars()
                    for media in media_rows:
                        safe = (
                            media.processing_status == "ready"
                            and media.classification == "safe"
                            and media.review_status != "required"
                        )
                        if job.type == "safe_complete" and not safe:
                            excluded_media.append(
                                {"id": str(media.id), "reason": "not_definitively_safe"}
                            )
                            continue
                        keys = [
                            ("display", media.display_object_key),
                            ("thumbnail", media.thumbnail_object_key),
                        ]
                        included: list[str] = []
                        for variant, object_key in keys:
                            if not object_key:
                                continue
                            suffix = Path(object_key).suffix.lower() or ".bin"
                            arcname = f"media/{record.id}/{media.id}/{variant}{suffix}"
                            with tempfile.NamedTemporaryFile(
                                prefix="export-media-", delete=False
                            ) as tmp:
                                tmp_path = tmp.name
                            try:
                                download_object_to_file(object_key, tmp_path)
                                size = os.path.getsize(tmp_path)
                                if bytes_added + size > settings.EXPORT_MAX_UNCOMPRESSED_BYTES:
                                    raise ValueError(
                                        "Dimensione massima superata durante la generazione."
                                    )
                                archive.write(tmp_path, arcname)
                                bytes_added += size
                                included.append(arcname)
                                digest = hashlib.sha256()
                                with open(tmp_path, "rb") as media_file:
                                    for chunk in iter(lambda: media_file.read(1024 * 1024), b""):
                                        digest.update(chunk)
                                file_manifest.append(
                                    {"path": arcname, "size": size, "sha256": digest.hexdigest()}
                                )
                            finally:
                                Path(tmp_path).unlink(missing_ok=True)
                        if included:
                            media_manifest.append(
                                {
                                    "id": str(media.id),
                                    "advertisement_id": str(ad.id),
                                    "classification": media.classification,
                                    "review_status": media.review_status,
                                    "sha256": media.sha256,
                                    "files": included,
                                }
                            )
                        else:
                            excluded_media.append(
                                {"id": str(media.id), "reason": "display_variant_unavailable"}
                            )
                job.progress_percent = min(90, 5 + int(index / len(record_ids) * 80))
                session.commit()

            records_json = json.dumps(records_rows, ensure_ascii=False, indent=2).encode()
            ads_json = json.dumps(advertisement_rows, ensure_ascii=False, indent=2).encode()
            record_fields = ["id", "phone", "canonical_ad_id", "created_at", "updated_at"]
            ad_fields = [
                "id",
                "record_id",
                "source_id",
                "source_name",
                "source_url",
                "title",
                "description",
                "status",
                "confidence",
                "first_seen_at",
                "last_seen_at",
                "scraped_at",
            ]
            payloads = {
                "records.json": records_json,
                "records.csv": _csv_bytes(records_rows, record_fields),
                "advertisements.json": ads_json,
                "advertisements.csv": _csv_bytes(advertisement_rows, ad_fields),
            }
            for name, payload in payloads.items():
                if bytes_added + len(payload) > settings.EXPORT_MAX_UNCOMPRESSED_BYTES:
                    raise ValueError(
                        "Dimensione massima dell'export superata durante la generazione."
                    )
                archive.writestr(name, payload)
                bytes_added += len(payload)
                file_manifest.append(
                    {
                        "path": name,
                        "size": len(payload),
                        "sha256": hashlib.sha256(payload).hexdigest(),
                    }
                )

            manifest = {
                "schema_version": "export-v1",
                "job_id": str(job.id),
                "type": job.type,
                "generated_at": datetime.now(UTC).isoformat(),
                "phone_visibility": "clear" if job.include_clear_phone else "masked",
                "filters": (job.manifest_json or {}).get("filters"),
                "records": [row["id"] for row in records_rows],
                "record_count": len(records_rows),
                "advertisement_count": len(advertisement_rows),
                "media": media_manifest,
                "excluded_media": excluded_media,
                "files": file_manifest,
                "uncompressed_bytes": bytes_added,
            }
            manifest_bytes = json.dumps(manifest, ensure_ascii=False, indent=2).encode()
            if bytes_added + len(manifest_bytes) > settings.EXPORT_MAX_UNCOMPRESSED_BYTES:
                raise ValueError("Dimensione massima dell'export superata dal manifest.")
            archive.writestr("manifest.json", manifest_bytes)
            bytes_added += len(manifest_bytes)

        object_key = f"exports/{job.id}/package.zip"
        upload_file(object_key, archive_path, "application/zip")
        now = datetime.now(UTC)
        job.object_key = object_key
        job.status = "ready"
        job.progress_percent = 100
        job.completed_at = now
        job.expires_at = (
            now + timedelta(days=settings.EXPORT_RETENTION_DAYS)
            if settings.EXPORT_RETENTION_DAYS > 0
            else None
        )
        job.archive_size_bytes = os.path.getsize(archive_path)
        job.estimated_uncompressed_bytes = bytes_added
        job.manifest_json = manifest
        session.commit()
        return {"status": "ready", "record_count": len(records_rows), "bytes": bytes_added}
    except Exception as exc:
        session.rollback()
        job = session.get(ExportJob, job_uuid)
        if job:
            job.status = "failed"
            job.progress_percent = 0
            job.error_message = _safe_error(exc)
            job.completed_at = datetime.now(UTC)
            session.commit()
        raise
    finally:
        if archive_path:
            Path(archive_path).unlink(missing_ok=True)
        session.close()
