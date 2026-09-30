"""Regressioni per la policy OTP globale e la semantica dal login successivo."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.api.v1 import auth
from app.models.integrations import ApplicationSecuritySettings
from app.schemas.auth import LoginRequest
from app.security.jwt import TokenType, decode_token
from app.services.mfa_policy import session_requires_mfa_setup


def _policy(*, enabled: bool, since: datetime | None = None):
    return SimpleNamespace(mfa_required=enabled, mfa_required_since=since)


def _user(*, enrolled: bool = False, role: str = "viewer"):
    return SimpleNamespace(
        id=uuid.uuid4(),
        email="utente@example.com",
        password_hash="hash",
        role=role,
        is_active=True,
        totp_enabled=enrolled,
        totp_secret_encrypted=b"secret" if enrolled else None,
        security_stamp_at=datetime.now(UTC),
    )


def test_policy_is_off_by_default_and_applies_to_every_role() -> None:
    user = _user(role="viewer")
    assert session_requires_mfa_setup(None, user, {}) is False
    assert session_requires_mfa_setup(_policy(enabled=False), user, {}) is False
    assert session_requires_mfa_setup(_policy(enabled=True), user, {}) is True


def test_enrolled_and_exempt_sessions_do_not_require_setup() -> None:
    assert session_requires_mfa_setup(_policy(enabled=True), _user(enrolled=True), {}) is False
    assert session_requires_mfa_setup(
        _policy(enabled=True), _user(), {"mfa_exempt": True}
    ) is False


def test_legacy_session_opened_before_activation_is_preserved() -> None:
    enabled_at = datetime.now(UTC)
    user = _user()
    old_token = {"iat": int((enabled_at - timedelta(minutes=1)).timestamp())}
    new_token = {"iat": int((enabled_at + timedelta(minutes=1)).timestamp())}
    policy = _policy(enabled=True, since=enabled_at)
    assert session_requires_mfa_setup(policy, user, old_token) is False
    assert session_requires_mfa_setup(policy, user, new_token) is True


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _LoginDb:
    def __init__(self, user, policy):
        self.user = user
        self.policy = policy

    async def execute(self, _statement):
        return _ScalarResult(self.user)

    async def get(self, model, _key):
        if model is ApplicationSecuritySettings:
            return self.policy
        return None


@pytest.mark.asyncio
async def test_login_bypasses_existing_totp_when_global_policy_is_off(monkeypatch) -> None:
    user = _user(enrolled=True, role="admin")
    db = _LoginDb(user, _policy(enabled=False))
    monkeypatch.setattr(auth, "verify_password", lambda *_args: True)
    monkeypatch.setattr(auth, "is_locked_out", _async_value(None))
    monkeypatch.setattr(auth, "clear_attempts", _async_value(None))

    response = await auth.login(LoginRequest(email=user.email, password="password"), db)

    assert response.status == "authenticated"
    assert response.user is not None
    assert response.user.mfa_policy_enabled is False
    token = decode_token(response.access_token, expected_type=TokenType.ACCESS)
    assert token["mfa_exempt"] is True


@pytest.mark.asyncio
async def test_enabled_policy_requires_setup_for_viewers_too(monkeypatch) -> None:
    user = _user(role="viewer")
    db = _LoginDb(user, _policy(enabled=True, since=datetime.now(UTC)))
    monkeypatch.setattr(auth, "verify_password", lambda *_args: True)
    monkeypatch.setattr(auth, "is_locked_out", _async_value(None))
    monkeypatch.setattr(auth, "clear_attempts", _async_value(None))

    response = await auth.login(LoginRequest(email=user.email, password="password"), db)

    assert response.status == "mfa_setup_required"
    assert response.user is not None
    assert response.user.mfa_policy_enabled is True
    assert response.user.mfa_setup_required is True


def _async_value(value):
    async def _result(*_args, **_kwargs):
        return value

    return _result
