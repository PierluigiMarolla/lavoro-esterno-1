"""Lettura e valutazione della policy OTP globale."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.integrations import ApplicationSecuritySettings
from app.models.users import User


async def get_mfa_policy(db: AsyncSession) -> ApplicationSecuritySettings | None:
    """Restituisce il singleton; l'assenza equivale al default sicuro "off".

    Il fallback mantiene utilizzabile il login durante un deploy in cui il
    codice parte pochi istanti prima dell'applicazione della migrazione.
    """

    return await db.get(ApplicationSecuritySettings, 1)


def session_requires_mfa_setup(
    policy: ApplicationSecuritySettings | None,
    user: User,
    token_payload: dict[str, Any],
) -> bool:
    """Indica se questa specifica sessione deve completare il setup OTP.

    Le sessioni emesse mentre la policy era spenta portano ``mfa_exempt``.
    Per i token legacy senza claim, il timestamp di attivazione preserva le
    sessioni aperte prima del cambio, realizzando la semantica "dal prossimo
    login" anche durante l'aggiornamento.
    """

    if policy is None or not policy.mfa_required or user.totp_enabled:
        return False
    if token_payload.get("mfa_exempt") is True:
        return False
    issued_at = token_payload.get("iat")
    enabled_at = policy.mfa_required_since
    if issued_at is not None and enabled_at is not None:
        if enabled_at.tzinfo is None:
            enabled_at = enabled_at.replace(tzinfo=UTC)
        if datetime.fromtimestamp(int(issued_at), UTC) < enabled_at:
            return False
    return True
