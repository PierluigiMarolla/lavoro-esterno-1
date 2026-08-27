"""Dependency FastAPI per autenticazione (JWT) e autorizzazione (RBAC)."""

from __future__ import annotations

import uuid
from collections.abc import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.users import User
from app.security.jwt import TokenError, TokenType, decode_token

_bearer_scheme = HTTPBearer(auto_error=True)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Decodifica l'access token nell'header Authorization e carica l'utente
    corrispondente dal DB. Solleva 401 per qualsiasi problema di
    autenticazione (token invalido/scaduto, utente inesistente o disattivato),
    senza distinguere i casi nel messaggio per non facilitare enumerazioni."""
    try:
        payload = decode_token(credentials.credentials, expected_type=TokenType.ACCESS)
        user_id = uuid.UUID(payload["sub"])
    except (TokenError, KeyError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenziali non valide o scadute.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenziali non valide o scadute.",
            headers={"WWW-Authenticate": "Bearer"},
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
    """Dependency per operazioni sensibili riservate agli admin, con
    l'ulteriore vincolo che l'admin abbia la 2FA attiva.

    Un account admin senza 2FA è un singolo punto di debolezza troppo
    critico (accesso completo al sistema, inclusi i dati cifrati e le
    operazioni di export "complete_media"): blocchiamo esplicitamente
    queste operazioni finché l'admin non attiva il TOTP, invece di limitarci
    a raccomandarlo.
    """
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Questa operazione richiede il ruolo 'admin'.",
        )
    if not user.totp_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Operazione sensibile bloccata: attiva l'autenticazione a due fattori (2FA) "
                "sul tuo account admin prima di procedere."
            ),
        )
    return user
