"""Schemi Pydantic per le operazioni amministrative."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr

from app.schemas.common import CamelModel


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    role: str
    totp_enabled: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    role: str = "viewer"


class AdminUserRead(CamelModel):
    """Rappresentazione di un utente per la pagina Admin > Users, rispecchia
    `frontend/src/types/index.ts:AdminUser` (consumata senza mapping
    esplicito lato client: vedi `app/schemas/common.py:CamelModel`).

    Due campi non hanno un corrispettivo diretto nel modello `User` (vedi
    `app/models/users.py`), e sono quindi approssimati qui invece di
    richiedere una migrazione dello schema DB in questa fase:

    - `name`: non esiste una colonna "nome visualizzato" — deriviamo un
      nome leggibile dalla parte locale dell'email (es. "mario.rossi@..."
      -> "Mario Rossi"). TODO: se in futuro serve un nome reale, aggiungere
      una colonna `users.display_name`.
    - `last_login_at`: non esiste tracciamento degli accessi — restituiamo
      sempre `None`. TODO: valorizzarlo richiederebbe che
      `POST /auth/login`/`login-2fa` aggiornino un campo `users.last_login_at`
      (non implementato in questo passaggio, per non estendere lo schema di
      autenticazione oltre lo scope di questo lavoro).
    """

    id: uuid.UUID
    name: str
    email: EmailStr
    role: str
    status: Literal["active", "suspended", "invited"]
    mfa_enabled: bool
    last_login_at: datetime | None


class AdminUserUpdate(CamelModel):
    """Body di `PATCH /admin/users/{id}`: oggi supporta solo il cambio
    ruolo (`frontend/src/api/admin.ts:updateAdminUserRole`)."""

    role: str


class AuditLogEntryRead(CamelModel):
    """Rispecchia `frontend/src/api/admin.ts:AuditLogEntry`."""

    id: uuid.UUID
    actor: str
    action: str
    target: str
    occurred_at: datetime


def display_name_from_email(email: str) -> str:
    """Deriva un nome "visualizzabile" dalla parte locale di un'email
    (euristica documentata in `AdminUserRead`, non un vero nome utente)."""
    local_part = email.split("@", 1)[0]
    normalized = local_part.replace(".", " ").replace("_", " ").replace("-", " ")
    words = [w for w in normalized.split(" ") if w]
    return " ".join(w.capitalize() for w in words) or email


def status_from_is_active(is_active: bool) -> Literal["active", "suspended", "invited"]:
    """Deriva lo status "vista" dal solo flag `is_active` disponibile oggi.

    Non esiste un flusso di invito utenti (nessun utente può trovarsi nello
    stato "invited" nel dominio attuale): il valore letterale resta comunque
    nel tipo per compatibilità col contratto frontend, in previsione di un
    futuro flusso di invito."""
    return "active" if is_active else "suspended"
