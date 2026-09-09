"""Public contracts for the Admin proxy-pool console."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from app.schemas.common import CamelModel

ProxyScheme = Literal["http", "https", "socks4", "socks5"]


class ProxyEndpointCreate(CamelModel):
    name: str = Field(min_length=1, max_length=120)
    scheme: ProxyScheme
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(ge=1, le=65535)
    username: str | None = Field(default=None, max_length=500)
    password: str | None = Field(default=None, max_length=1000)
    enabled: bool = True

    @model_validator(mode="after")
    def credentials_are_a_pair(self):
        if (self.username is None) != (self.password is None):
            raise ValueError("Username e password devono essere configurati insieme.")
        return self


class ProxyEndpointUpdate(CamelModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    scheme: ProxyScheme | None = None
    host: str | None = Field(default=None, min_length=1, max_length=255)
    port: int | None = Field(default=None, ge=1, le=65535)
    username: str | None = Field(default=None, max_length=500)
    password: str | None = Field(default=None, max_length=1000)
    clear_credential: bool = False
    enabled: bool | None = None

    @model_validator(mode="after")
    def credentials_are_consistent(self):
        supplied = self.username is not None or self.password is not None
        if supplied and (self.username is None or self.password is None):
            raise ValueError("Username e password devono essere configurati insieme.")
        if supplied and self.clear_credential:
            raise ValueError("Credenziali e clearCredential sono mutuamente esclusivi.")
        return self


class ProxyEndpointRead(CamelModel):
    id: uuid.UUID
    name: str
    scheme: ProxyScheme
    host: str
    port: int
    enabled: bool
    credential_configured: bool
    health: str
    consecutive_failures: int
    cooldown_until: datetime | None
    last_used_at: datetime | None
    last_success_at: datetime | None
    last_failure_at: datetime | None


class ProxyPoolCreate(CamelModel):
    name: str = Field(min_length=1, max_length=120)
    enabled: bool = True
    proxy_ids: list[uuid.UUID] = Field(default_factory=list)


class ProxyPoolUpdate(CamelModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    enabled: bool | None = None
    proxy_ids: list[uuid.UUID] | None = None


class ProxyPoolRead(CamelModel):
    id: uuid.UUID
    name: str
    enabled: bool
    proxy_ids: list[uuid.UUID]
    healthy_count: int
    total_count: int


class ProxyTestInput(CamelModel):
    source_id: uuid.UUID


class ProxyTestRead(CamelModel):
    success: bool
    latency_ms: int
    status_category: str
    message: str
