"""Endpoint di autenticazione: login (con eventuale 2FA), refresh, setup TOTP."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.users import User
from app.schemas.auth import (
    Login2FARequest,
    LoginRequest,
    LoginResponse,
    RefreshRequest,
    TokenPairResponse,
    TOTPSetupResponse,
    TOTPVerifyRequest,
    UserPublic,
)
from app.security.deps import get_current_user
from app.security.jwt import (
    TokenError,
    TokenType,
    create_access_token,
    create_login_ticket,
    create_refresh_token,
    decode_token,
)
from app.security.password import verify_password
from app.security.totp import (
    build_provisioning_uri,
    decrypt_totp_secret,
    encrypt_totp_secret,
    generate_backup_codes,
    generate_qr_code_base64,
    generate_totp_secret,
    hash_backup_codes,
    verify_and_consume_backup_code,
    verify_totp_code,
)
from app.services.audit import log_action

router = APIRouter()


@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)) -> LoginResponse:
    """Prima fase del login: verifica email+password.

    Se l'utente ha la 2FA attiva, NON emette token di accesso: restituisce
    invece un `mfa_token` effimero (internamente è un "login ticket" JWT di
    breve durata) che il client deve inviare, insieme a un codice TOTP o a
    un backup code, a `POST /auth/login-2fa`.
    """
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()

    # Messaggio identico per email inesistente e password errata: evita di
    # rivelare quali email sono registrate (enumeration attack).
    invalid_credentials = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="Email o password non validi."
    )
    if user is None or not user.is_active:
        raise invalid_credentials
    if not verify_password(payload.password, user.password_hash):
        raise invalid_credentials

    if user.totp_enabled:
        ticket = create_login_ticket(user.id, user.role)
        return LoginResponse(status="mfa_required", mfa_token=ticket)

    access = create_access_token(user.id, user.role)
    refresh = create_refresh_token(user.id, user.role)
    return LoginResponse(
        status="authenticated",
        access_token=access,
        refresh_token=refresh,
        user=UserPublic.from_user(user),
    )


@router.post("/login-2fa", response_model=TokenPairResponse)
async def login_2fa(payload: Login2FARequest, db: AsyncSession = Depends(get_db)) -> TokenPairResponse:
    """Seconda fase del login per utenti con 2FA attiva: completa
    l'autenticazione verificando un codice TOTP a 6 cifre oppure un backup
    code monouso."""
    try:
        ticket_payload = decode_token(payload.mfa_token, expected_type=TokenType.LOGIN_2FA)
    except TokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Login ticket non valido o scaduto."
        ) from exc

    import uuid

    user = await db.get(User, uuid.UUID(ticket_payload["sub"]))
    if user is None or not user.is_active or not user.totp_enabled or not user.totp_secret_encrypted:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Login non valido.")

    code_is_valid = False

    if len(payload.code) == 6 and payload.code.isdigit():
        secret = decrypt_totp_secret(user.totp_secret_encrypted)
        code_is_valid = verify_totp_code(secret, payload.code)

    if not code_is_valid and user.backup_codes_hash:
        remaining = verify_and_consume_backup_code(payload.code, user.backup_codes_hash)
        if remaining is not None:
            code_is_valid = True
            user.backup_codes_hash = remaining
            db.add(user)
            await db.commit()

    if not code_is_valid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Codice 2FA non valido.")

    access = create_access_token(user.id, user.role)
    refresh = create_refresh_token(user.id, user.role)
    return TokenPairResponse(
        access_token=access, refresh_token=refresh, user=UserPublic.from_user(user)
    )


@router.post("/refresh", response_model=TokenPairResponse)
async def refresh_token(payload: RefreshRequest, db: AsyncSession = Depends(get_db)) -> TokenPairResponse:
    """Scambia un refresh token valido con una nuova coppia access+refresh."""
    import uuid

    try:
        token_payload = decode_token(payload.refresh_token, expected_type=TokenType.REFRESH)
    except TokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token non valido o scaduto."
        ) from exc

    user = await db.get(User, uuid.UUID(token_payload["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token non valido.")

    access = create_access_token(user.id, user.role)
    refresh = create_refresh_token(user.id, user.role)
    return TokenPairResponse(access_token=access, refresh_token=refresh)


@router.get("/me", response_model=UserPublic)
async def read_current_user(user: User = Depends(get_current_user)) -> UserPublic:
    return UserPublic.from_user(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> None:
    """Logout lato server.

    I JWT emessi da questa API sono stateless (nessuna tabella di sessione):
    un access/refresh token già emesso resta tecnicamente valido fino alla
    sua scadenza naturale anche dopo questa chiamata. Questo endpoint quindi
    NON revoca davvero il token: si limita a (1) registrare l'evento in
    `audit_log`, utile per la tracciabilità degli accessi, e (2) dare al
    frontend (`frontend/src/api/auth.ts:logout`) una risposta 204 da
    attendere prima di cancellare i token da `localStorage`
    (`tokenStorage.clear()`, vedi `frontend/src/api/client.ts`) e reindirizzare
    al login.

    Una revoca lato server effettiva richiederebbe una blacklist dei JWT
    (o il passaggio a refresh token persistiti in DB, invalidabili
    singolarmente): è una nota aperta, vedi `docs/SICUREZZA.md` e
    `PROGETTO.md`.
    """
    await log_action(
        db, user_id=user.id, action="logout", entity_type="user", entity_id=str(user.id)
    )
    await db.commit()


@router.post("/setup-2fa", response_model=TOTPSetupResponse)
async def setup_2fa(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> TOTPSetupResponse:
    """Avvia il setup della 2FA: genera un nuovo secret TOTP e 10 backup
    codes, mostrati UNA SOLA VOLTA nella risposta.

    Il secret viene salvato cifrato ma `totp_enabled` resta False finché
    l'utente non conferma di aver configurato correttamente l'app
    authenticator tramite `POST /auth/verify-2fa`: evita di "attivare" una
    2FA che l'utente non è di fatto in grado di usare.
    """
    secret = generate_totp_secret()
    provisioning_uri = build_provisioning_uri(secret, account_email=user.email)
    qr_code = generate_qr_code_base64(provisioning_uri)

    backup_codes = generate_backup_codes()

    user.totp_secret_encrypted = encrypt_totp_secret(secret)
    user.backup_codes_hash = hash_backup_codes(backup_codes)
    user.totp_enabled = False
    db.add(user)
    await db.commit()

    return TOTPSetupResponse(secret=secret, qr_code_base64=qr_code, backup_codes=backup_codes)


@router.post("/verify-2fa", response_model=UserPublic)
async def verify_2fa(
    payload: TOTPVerifyRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserPublic:
    """Conferma il setup 2FA: se il codice è valido, attiva definitivamente
    `totp_enabled`."""
    if not user.totp_secret_encrypted:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nessun setup 2FA in corso: chiama prima POST /auth/setup-2fa.",
        )

    secret = decrypt_totp_secret(user.totp_secret_encrypted)
    if not verify_totp_code(secret, payload.code):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Codice TOTP non valido.")

    user.totp_enabled = True
    db.add(user)
    await db.commit()

    return UserPublic.from_user(user)
