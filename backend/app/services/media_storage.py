"""Upload dei media scaricati durante lo scraping su MinIO/S3.

Prima pipeline del progetto che scrive DAVVERO su MinIO (finora il client
MinIO era usato solo per rimuovere oggetti scaduti, vedi
`app/workers/tasks_maintenance.py`): qui creiamo anche il bucket se non
esiste ancora, dato che nessun altro punto del codice lo fa.
"""

from __future__ import annotations

import io
import uuid

from minio import Minio

from app.config import settings

# Firme "magic bytes" per i formati immagine più comuni: evitiamo il modulo
# `imghdr` della stdlib (rimosso in Python 3.13) e non abbiamo l'URL
# originale a disposizione qui per un guess-by-extension affidabile.
_MAGIC_BYTES: list[tuple[bytes, str]] = [
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"RIFF", "image/webp"),  # nota: RIFF è anche l'header di WAV/AVI, ma nel
    # contesto media-annuncio ci aspettiamo solo immagini/webp.
]


def sniff_mime_type(data: bytes) -> str:
    """Indovina il MIME type dai byte del file. Fallback generico se nessuna
    firma nota corrisponde: meglio un MIME type onesto ma poco specifico che
    una diagnosi sbagliata sul contenuto."""
    for signature, mime_type in _MAGIC_BYTES:
        if data.startswith(signature):
            return mime_type
    return "application/octet-stream"


_EXTENSION_BY_MIME = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/gif": "gif",
    "image/webp": "webp",
}


def _client() -> Minio:
    return Minio(
        settings.MINIO_ENDPOINT,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=settings.MINIO_SECURE,
    )


def _ensure_bucket(client: Minio) -> None:
    if not client.bucket_exists(settings.MINIO_BUCKET):
        client.make_bucket(settings.MINIO_BUCKET)


def upload_media_object(record_id: uuid.UUID, data: bytes, mime_type: str) -> str:
    """Carica un media originale scaricato durante lo scraping, seguendo la
    convenzione di path documentata in `docs/DATABASE.md`:
    `media/{record_uuid}/{media_uuid}/original.<ext>`. Restituisce
    l'`object_key` da salvare in `media.original_object_key`.
    """
    client = _client()
    _ensure_bucket(client)

    extension = _EXTENSION_BY_MIME.get(mime_type, "bin")
    media_id = uuid.uuid4()
    object_key = f"media/{record_id}/{media_id}/original.{extension}"

    client.put_object(
        settings.MINIO_BUCKET,
        object_key,
        io.BytesIO(data),
        length=len(data),
        content_type=mime_type,
    )
    return object_key
