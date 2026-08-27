"""Task Celery per l'elaborazione dei media (classificazione, hash, derivati)."""

from __future__ import annotations

import logging

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.workers.tasks_media.classify_media")
def classify_media(media_id: str) -> dict:
    """Placeholder: in futuro scaricherà il file da MinIO tramite
    `original_object_key`, lo passerà a un `MediaClassifier` reale (vedi
    app/services/media_classifier.py) e aggiornerà `media.classification`,
    `classification_confidence`, `classifier_version`, oltre a scrivere una
    riga in `media_classification_history`.

    TODO: implementare download da MinIO + chiamata al classificatore reale.
    """
    logger.info("TODO: classificazione reale non ancora implementata per media_id=%s", media_id)
    return {"status": "skipped", "media_id": media_id}


@celery_app.task(name="app.workers.tasks_media.compute_perceptual_hash")
def compute_perceptual_hash(media_id: str) -> dict:
    """Placeholder: calcolerà il perceptual hash (pHash) di un'immagine con
    la libreria `imagehash` (basata su Pillow), per il rilevamento di
    duplicati quasi-identici (vedi app/services/dedup.py:image_phash_similarity).

    TODO: implementare `imagehash.phash(Image.open(...))` sul file scaricato
    da MinIO e salvare il risultato in `media.perceptual_hash`.
    """
    logger.info("TODO: calcolo pHash non ancora implementato per media_id=%s", media_id)
    return {"status": "skipped", "media_id": media_id}


@celery_app.task(name="app.workers.tasks_media.transcode_video")
def transcode_video(media_id: str) -> dict:
    """Placeholder: transcodifica/normalizzazione video tramite un wrapper
    FFmpeg (invocazione di `ffmpeg` come processo esterno).

    TODO: implementare l'invocazione FFmpeg reale e il caricamento del
    risultato come `media.derived_object_key`.
    """
    logger.info("TODO: transcodifica video non ancora implementata per media_id=%s", media_id)
    return {"status": "skipped", "media_id": media_id}
