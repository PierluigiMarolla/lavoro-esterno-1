"""Schemi Pydantic per le richieste di esportazione (ExportJob)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import CamelModel

ExportTypeLiteral = Literal["text_only", "complete_media", "safe_complete"]


class ExportJobCreate(BaseModel):
    """Richiesta di creazione di un export.

    Il body atteso da `frontend/src/api/exports.ts:createExportJob` è
    `{ type, record_ids }` (lista, eventualmente assente per un export
    "bulk" descritto invece via `filters" lato futuro worker) — non il
    singolo `record_id` che questo schema esponeva in origine, incompatibile
    col contratto frontend. Se `record_ids` contiene un solo elemento lo
    trattiamo come export "a singolo record" (valorizzando la FK
    `ExportJob.record_id`, utile per query/filtri futuri); altrimenti
    l'elenco viene conservato in `manifest_json["record_ids"]` (export
    "bulk", coerente con la nota già presente su `ExportJob.record_id`
    nullable in `app/models/export_jobs.py`).
    """

    type: ExportTypeLiteral
    record_ids: list[uuid.UUID] | None = None
    filters: dict[str, Any] | None = Field(
        default=None,
        description="Filtri opzionali per un export bulk (usati solo se record_ids è assente).",
    )


class ExportJobRead(BaseModel):
    """Rappresentazione "grezza" (snake_case) di un ExportJob, 1:1 con le
    colonne del modello ORM. Non più usata dagli endpoint REST (sostituita
    da `ExportJobOut` sotto, che è quella attesa dal frontend): la teniamo
    per eventuali usi interni/di debug."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    record_id: uuid.UUID | None
    type: str
    status: str
    progress_percent: int
    requested_by_user_id: uuid.UUID
    requested_at: datetime
    completed_at: datetime | None
    object_key: str | None
    error_message: str | None


class ExportJobOut(CamelModel):
    """Rappresentazione di un ExportJob per l'API REST, rispecchia
    `frontend/src/types/index.ts:ExportJob` (consumata senza mapping
    esplicito lato client, vedi `app/schemas/common.py:CamelModel`)."""

    id: uuid.UUID
    type: str
    status: str
    progress_pct: int
    requested_by: str
    requested_at: datetime
    record_count: int
    download_url: str | None


class DownloadUrlResponse(BaseModel):
    """Risposta di `GET /exports/{id}/download`: rispecchia
    `{ url: string }` atteso da
    `frontend/src/api/exports.ts:getExportDownloadUrl`."""

    url: str
