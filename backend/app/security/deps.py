"""Dependency FastAPI per autenticazione (JWT) e autorizzazione (RBAC)."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.users import User
from app.security.jwt import TokenError, TokenType, decode_token
from app.security.redis_client import is_jti_blacklisted
from app.services.mfa_policy import get_mfa_policy, session_requires_mfa_setup

_bearer_scheme = HTTPBearer(auto_error=True)

_INVALID_CREDENTIALS = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Credenziali non valide o scadute.",
    headers={"WWW-Authenticate": "Bearer"},
)


@dataclass(frozen=True)
class AuthenticatedSession:
    """Utente autenticato e claim della sessione JWT corrente."""

    user: User
    token_payload: dict[str, Any]


async def _resolve_user_from_access_token(
    credentials: HTTPAuthorizationCredentials, db: AsyncSession
) -> AuthenticatedSession:
    """Decodifica l'access token, verifica che non sia stato revocato
    (blacklist del `jti` su logout, mismatch del `sst` su cambio password o
    reset 2FA) e carica l'utente corrispondente. Solleva 401 per qualsiasi
    problema di autenticazione, senza distinguere i casi nel messaggio per
    non facilitare enumerazioni."""
    try:
        payload = decode_token(credentials.credentials, expected_type=TokenType.ACCESS)
        user_id = uuid.UUID(payload["sub"])
    except (TokenError, KeyError, ValueError) as exc:
        raise _INVALID_CREDENTIALS from exc

    if await is_jti_blacklisted(payload.get("jti", "")):
        raise _INVALID_CREDENTIALS

    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise _INVALID_CREDENTIALS

    token_sst = payload.get("sst")
    current_sst = int(user.security_stamp_at.timestamp())
    if token_sst is None or int(token_sst) != current_sst:
        # Il token è stato emesso prima dell'ultimo logout globale/cambio
        # password/reset 2FA: trattarlo come qualsiasi altra credenziale
        # scaduta o invalida.
        raise _INVALID_CREDENTIALS

    return AuthenticatedSession(user=user, token_payload=payload)


async def get_current_session_allow_unenrolled(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> AuthenticatedSession:
    """Risolve la sessione senza imporre l'enrollment OTP."""

    return await _resolve_user_from_access_token(credentials, db)


async def get_current_user_allow_unenrolled(
    session: AuthenticatedSession = Depends(get_current_session_allow_unenrolled),
) -> User:
    """Come `get_current_user`, ma SENZA il controllo di enrollment 2FA
    obbligatoria: riservata agli endpoint che un utente ancora privo di 2FA
    deve poter comunque chiamare per completare il
    setup (`/auth/me`, `/auth/logout`, `/auth/setup-2fa`, `/auth/verify-2fa`,
    `/auth/2fa/backup-codes/regenerate`, `/auth/change-password`)."""
    return session.user


async def get_current_user(
    session: AuthenticatedSession = Depends(get_current_session_allow_unenrolled),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Applica la policy OTP globale alla sessione corrente.

    La policy riguarda tutti i ruoli ed è disattivata per default. Le
    sessioni nate prima dell'attivazione restano valide fino al successivo
    login completo.
    """
    user = session.user
    policy = await get_mfa_policy(db)
    if session_requires_mfa_setup(policy, user, session.token_payload):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error_code": "mfa_setup_required",
                "message": (
                    "L'applicazione richiede l'autenticazione a due fattori: completa il "
                    "setup 2FA (POST /auth/setup-2fa, poi /auth/verify-2fa) prima di "
                    "continuare."
                ),
            },
        )
    return user


def require_role(*roles: str) -> Callable:
    """Fabbrica di dependency FastAPI per il controllo RBAC: consente
    l'accesso solo agli utenti il cui ruolo è tra quelli passati.

    Uso tipico: `Depends(require_role("admin", "operator"))`. I tre ruoli del
    sistema sono "admin" (accesso completo), "operator" (operatività
    quotidiana: scraping, export, override canonico) e "viewer" (sola
    lettura).
    """

    async def _checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Ruolo '{user.role}' non autorizzato per questa operazione.",
            )
        return user

    return _checker


async def require_admin_with_2fa(user: User = Depends(get_current_user)) -> User:
    """Riserva l'operazione agli Admin e rispetta la policy OTP globale.

    Il nome storico resta stabile per i router esistenti; il secondo fattore
    è imposto da ``get_current_user`` solo quando la policy è abilitata.
    """
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Questa operazione richiede il ruolo 'admin'.",
        )
    return user
