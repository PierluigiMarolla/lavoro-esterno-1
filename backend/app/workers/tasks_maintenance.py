"""Task Celery di manutenzione periodica: pulizia dati secondo la retention
policy configurata (vedi `app/config.py`: `AUDIT_LOG_RETENTION_DAYS`,
`SCRAPE_ERROR_RETENTION_DAYS`, `EXPORT_RETENTION_DAYS`).

Nessuna scadenza automatica è applicata a `record`/`advertisement`/`media`
(dato "vivo", non di log): la loro retention resta sospesa a una validazione
legale/GDPR definitiva (vedi `docs/SICUREZZA.md`). Qui trattiamo solo dati
accessori il cui accumulo indefinito non porta valore (log di audit/errori
vecchi, pacchetti di export scaduti).

Come `tasks_scraper.py`, usa una sessione SQLAlchemy SINCRONA (Celery non è
async-native) verso lo stesso database dell'app.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from app.config import settings
from app.workers.celery_app import celery_app
from app.workers.tasks_scraper import SyncSessionLocal

logger = logging.getLogger(__name__)


def _delete_expired_export_object(object_key: str) -> None:
    """Rimuove da MinIO il pacchetto di un export scaduto.

    Nessun client MinIO è ancora usato altrove nel backend (l'upload/
    generazione reale dei pacchetti di export è un TODO aperto, vedi
    `app/api/v1/exports.py:_download_url`): qui ci limitiamo a tentare la
    rimozione in modo difensivo. In un ambiente di sviluppo senza export
    reali mai generati, `object_key` non punterà quasi mai a un oggetto
    davvero esistente: un errore qui non deve bloccare la pulizia degli
    altri export/log, quindi viene solo loggato.
    """
    try:
        from minio import Minio
        from minio.error import S3Error

        client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_SECURE,
        )
        client.remove_object(settings.MINIO_BUCKET, object_key)
    except S3Error as exc:
        logger.warning("Impossibile rimuovere l'oggetto MinIO '%s': %s", object_key, exc)
    except Exception:  # noqa: BLE001 - connessione MinIO assente/non raggiungibile in dev
        logger.exception(
            "Errore imprevisto rimuovendo l'oggetto MinIO '%s' (bucket non raggiungibile?).",
            object_key,
        )


@celery_app.task(name="app.workers.tasks_maintenance.cleanup_expired_data")
def cleanup_expired_data() -> dict:
    """Applica la retention policy: cancella audit_log/scrape_errors vecchi
    e libera i pacchetti di export scaduti.

    Restituisce un riepilogo (utile nei log/risultato Celery e nei test
    manuali via `celery ... call`)."""
    from sqlalchemy import delete, select

    from app.models.audit_log import AuditLog
    from app.models.export_jobs import ExportJob

    now = datetime.now(UTC)
    session = SyncSessionLocal()
    try:
        audit_cutoff = now - timedelta(days=settings.AUDIT_LOG_RETENTION_DAYS)
        deleted_audit = session.execute(
            delete(AuditLog).where(AuditLog.created_at < audit_cutoff)
        ).rowcount

        # scrape_errors non ha un modello importato qui sopra per evitare un
        # import inutilizzato quando la retention è disabilitata (valore <=0):
        # importato lazy, stesso pattern di app/workers/tasks_scraper.py.
        from app.models.scrape_errors import ScrapeError

        scrape_error_cutoff = now - timedelta(days=settings.SCRAPE_ERROR_RETENTION_DAYS)
        deleted_scrape_errors = session.execute(
            delete(ScrapeError).where(ScrapeError.created_at < scrape_error_cutoff)
        ).rowcount

        expired_jobs = (
            session.execute(
                select(ExportJob).where(
                    ExportJob.expires_at.is_not(None),
                    ExportJob.expires_at < now,
                    ExportJob.object_key.is_not(None),
                )
            )
            .scalars()
            .all()
        )
        purged_exports = 0
        for job in expired_jobs:
            _delete_expired_export_object(job.object_key)
            job.object_key = None
            session.add(job)
            purged_exports += 1

        if purged_exports:
            log_entry = AuditLog(
                user_id=None,
                action="cleanup_expired_exports",
                entity_type="export_job",
                entity_id=None,
                details_json={"purged_count": purged_exports},
            )
            session.add(log_entry)

        session.commit()

        result = {
            "deleted_audit_log": deleted_audit,
            "deleted_scrape_errors": deleted_scrape_errors,
            "purged_export_objects": purged_exports,
        }
        logger.info("cleanup_expired_data completato: %s", result)
        return result
    finally:
        session.close()


@celery_app.task(name="app.workers.tasks_maintenance.cleanup_orphan_media_objects")
def cleanup_orphan_media_objects() -> dict:
    """Delete only MinIO media objects not referenced by DB after a grace period."""
    from minio import Minio
    from sqlalchemy import select

    from app.models.media import Media

    session = SyncSessionLocal()
    deleted = 0
    try:
        rows = session.execute(
            select(
                Media.original_object_key,
                Media.display_object_key,
                Media.thumbnail_object_key,
                Media.derived_object_key,
            )
        ).all()
        referenced = {key for row in rows for key in row if key}
        cutoff = datetime.now(UTC) - timedelta(hours=settings.MEDIA_ORPHAN_GRACE_HOURS)
        client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_SECURE,
        )
        if not client.bucket_exists(settings.MINIO_BUCKET):
            return {"deleted_orphan_media_objects": 0}
        for item in client.list_objects(settings.MINIO_BUCKET, prefix="media/", recursive=True):
            if (
                item.object_name not in referenced
                and item.last_modified
                and item.last_modified < cutoff
            ):
                client.remove_object(settings.MINIO_BUCKET, item.object_name)
                deleted += 1
        return {"deleted_orphan_media_objects": deleted}
    finally:
        session.close()


@celery_app.task(name="app.workers.tasks_maintenance.configure_media_lifecycle")
def configure_media_lifecycle() -> dict:
    """Expire temporary objects and abort incomplete multipart uploads after one day."""
    from minio import Minio
    from minio.commonconfig import ENABLED, Filter
    from minio.lifecycleconfig import (
        AbortIncompleteMultipartUpload,
        Expiration,
        LifecycleConfig,
        Rule,
    )

    client = Minio(
        settings.MINIO_ENDPOINT,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=settings.MINIO_SECURE,
    )
    if not client.bucket_exists(settings.MINIO_BUCKET):
        client.make_bucket(settings.MINIO_BUCKET)
    rule = Rule(
        ENABLED,
        rule_filter=Filter(prefix="tmp/"),
        rule_id="temporary-media-one-day",
        expiration=Expiration(days=1),
        abort_incomplete_multipart_upload=AbortIncompleteMultipartUpload(days_after_initiation=1),
    )
    client.set_bucket_lifecycle(settings.MINIO_BUCKET, LifecycleConfig([rule]))
    return {"configured": True, "temporary_expiry_days": 1}
