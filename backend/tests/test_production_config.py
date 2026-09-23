from __future__ import annotations

import base64

import pytest
from pydantic import ValidationError

from app.config import Settings


def _production_values() -> dict[str, object]:
    encoded = [base64.b64encode(bytes([value]) * 32).decode() for value in range(1, 5)]
    return {
        "ENVIRONMENT": "production",
        "APP_DOMAIN": "app.example.com",
        "PUBLIC_IP": "8.8.8.8",
        "PUBLIC_BASE_URL": "https://app.example.com",
        "MINIO_PUBLIC_ENDPOINT": "https://app.example.com",
        "MINIO_SECURE": False,
        "ALLOW_INSECURE_IP_ACCESS": True,
        "CORS_ORIGIN": "https://app.example.com,http://8.8.8.8",
        "ALLOWED_HOSTS": "app.example.com,8.8.8.8,localhost,127.0.0.1",
        "JWT_SECRET_KEY": "a" * 64,
        "PHONE_HMAC_SECRET": "b" * 32,
        "MINIO_SECRET_KEY": "c" * 32,
        "POSTGRES_PASSWORD": "d" * 32,
        "MINIO_ROOT_PASSWORD": "e" * 32,
        "GF_SECURITY_ADMIN_PASSWORD": "f" * 32,
        "PHONE_ENCRYPTION_KEY": encoded[0],
        "AI_CREDENTIAL_ENCRYPTION_KEY": encoded[1],
        "PROXY_CREDENTIAL_ENCRYPTION_KEY": encoded[2],
        "INTEGRATION_ENCRYPTION_KEY": encoded[3],
    }


def test_valid_production_configuration_is_accepted() -> None:
    settings = Settings(**_production_values())
    assert settings.PUBLIC_BASE_URL == "https://app.example.com"
    assert settings.allowed_hosts == ["app.example.com", "8.8.8.8", "localhost", "127.0.0.1"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("PUBLIC_BASE_URL", "http://app.example.com"),
        ("MINIO_PUBLIC_ENDPOINT", "https://media.example.com"),
        ("PUBLIC_IP", "127.0.0.1"),
        ("JWT_SECRET_KEY", "change-me"),
        ("ALLOW_INSECURE_IP_ACCESS", False),
        ("ALLOWED_HOSTS", "*"),
    ],
)
def test_invalid_production_configuration_fails_fast(field: str, value: object) -> None:
    values = _production_values()
    values[field] = value
    with pytest.raises(ValidationError, match="Configurazione production non valida"):
        Settings(**values)


def test_production_encryption_keys_must_be_distinct() -> None:
    values = _production_values()
    values["AI_CREDENTIAL_ENCRYPTION_KEY"] = values["PHONE_ENCRYPTION_KEY"]
    with pytest.raises(ValidationError, match="tutte differenti"):
        Settings(**values)
