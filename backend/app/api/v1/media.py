"""Endpoint di lettura per i media associati agli annunci."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.media import Media
from app.models.users import User
from app.schemas.media import MediaRead
from app.security.deps import get_current_user

router = APIRouter()


@router.get("/by-advertisement/{advertisement_id}", response_model=list[MediaRead])
async def list_media_for_advertisement(
    advertisement_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[MediaRead]:
    result = await db.execute(select(Media).where(Media.advertisement_id == advertisement_id))
    return [MediaRead.model_validate(m) for m in result.scalars().all()]


@router.get("/{media_id}", response_model=MediaRead)
async def get_media(
    media_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> MediaRead:
    media = await db.get(Media, media_id)
    if media is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media non trovato.")
    return MediaRead.model_validate(media)
