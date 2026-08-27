"""Schemi Pydantic per i media associati agli annunci."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class MediaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    advertisement_id: uuid.UUID
    original_object_key: str
    derived_object_key: str | None
    sha256: str
    perceptual_hash: str | None
    mime_type: str
    classification: str
    classification_confidence: float | None
    classifier_version: str | None
    created_at: datetime
