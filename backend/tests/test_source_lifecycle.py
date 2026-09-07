"""Regressioni per duplicazione e riabilitazione delle fonti."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import main
from app.api.v1.sources import duplicate_source, enable_source
from app.db import get_db
from app.models.audit_log import AuditLog
from app.models.sources import Source
from app.schemas.sources import SourceDuplicate
from app.security.deps import get_current_user


class _ScalarResult:
    def __init__(self, value: object | None) -> None:
        self.value = value

    def scalar_one_or_none(self) -> object | None:
        return self.value


class _FakeSession:
    def __init__(self, source: Source | None, *, conflicting_slug: bool = False) -> None:
        self.source = source
        self.conflicting_slug = conflicting_slug
        self.added: list[object] = []
        self.commits = 0
        self.rollbacks = 0

    async def get(self, model: type, item_id: uuid.UUID) -> Source | None:
        assert model is Source
        if self.source is not None and self.source.id == item_id:
            return self.source
        return None

    async def execute(self, _statement: object) -> _ScalarResult:
        return _ScalarResult(uuid.uuid4() if self.conflicting_slug else None)

    def add(self, value: object) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        for value in self.added:
            if isinstance(value, Source) and value.id is None:
                value.id = uuid.uuid4()

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1

    async def refresh(self, _value: object) -> None:
        return None


def _source(*, enabled: bool = True, status: str = "healthy") -> Source:
    return Source(
        id=uuid.uuid4(),
        name="Original",
        slug="original",
        base_url="https://example.test/path",
        priority="high",
        status=status,
        enabled=enabled,
        scrape_config={
            "start_urls": ["https://example.test/list"],
            "fetch_mode": "stealth",
            "user_agent": "Configured agent",
            "proxy": "http://proxy.internal:8080",
            "fields": {"phone": {"selector": ".phone", "attribute": "text", "multiple": False}},
        },
        watermark_removal_enabled=True,
        watermark_authorization_reference="authorization-ticket-42",
        watermark_regions=[{"x": 0.7, "y": 0.8, "width": 0.2, "height": 0.1}],
    )


@pytest.mark.asyncio
async def test_duplicate_source_copies_configuration_but_starts_disabled() -> None:
    original = _source()
    db = _FakeSession(original)
    user = SimpleNamespace(id=uuid.uuid4())

    result = await duplicate_source(
        original.id,
        SourceDuplicate(name="Original (copy)", slug="original_copy"),
        db=db,  # type: ignore[arg-type]
        user=user,  # type: ignore[arg-type]
    )

    duplicate = next(item for item in db.added if isinstance(item, Source))
    audit = next(item for item in db.added if isinstance(item, AuditLog))
    assert duplicate.id != original.id
    assert duplicate.name == "Original (copy)"
    assert duplicate.slug == "original_copy"
    assert duplicate.base_url == original.base_url
    assert duplicate.priority == original.priority
    assert duplicate.scrape_config == original.scrape_config
    assert duplicate.scrape_config is not original.scrape_config
    assert duplicate.watermark_removal_enabled is True
    assert duplicate.watermark_authorization_reference == original.watermark_authorization_reference
    assert duplicate.watermark_regions == original.watermark_regions
    assert duplicate.watermark_regions is not original.watermark_regions
    assert duplicate.enabled is False
    assert duplicate.status == "offline"
    assert result.enabled is False
    assert result.has_scrape_config is True
    assert db.commits == 1
    assert len(db.added) == 2  # Solo nuova fonte e audit: nessuna riga storica viene copiata.
    assert audit.action == "duplicate_source"
    assert audit.entity_id == str(duplicate.id)
    assert audit.details_json == {
        "original_source_id": str(original.id),
        "duplicate_slug": "original_copy",
    }
    assert "authorization-ticket-42" not in str(audit.details_json)


@pytest.mark.asyncio
async def test_duplicate_source_rejects_missing_source_and_slug_collision() -> None:
    user = SimpleNamespace(id=uuid.uuid4())
    payload = SourceDuplicate(name="Copy", slug="copy")
    with pytest.raises(HTTPException) as missing:
        await duplicate_source(
            uuid.uuid4(), payload, db=_FakeSession(None), user=user  # type: ignore[arg-type]
        )
    assert missing.value.status_code == 404

    original = _source()
    with pytest.raises(HTTPException) as conflict:
        await duplicate_source(
            original.id,
            payload,
            db=_FakeSession(original, conflicting_slug=True),  # type: ignore[arg-type]
            user=user,  # type: ignore[arg-type]
        )
    assert conflict.value.status_code == 409

    with pytest.raises(HTTPException) as unchanged_name:
        await duplicate_source(
            original.id,
            SourceDuplicate(name="Original", slug="otherwise_valid"),
            db=_FakeSession(original),  # type: ignore[arg-type]
            user=user,  # type: ignore[arg-type]
        )
    assert unchanged_name.value.status_code == 409


@pytest.mark.asyncio
@pytest.mark.parametrize("previous_status", ["offline", "degraded", "healthy"])
async def test_enable_source_reactivates_disabled_or_paused_source(previous_status: str) -> None:
    source = _source(enabled=False, status=previous_status)
    db = _FakeSession(source)
    await enable_source(
        source.id,
        db=db,  # type: ignore[arg-type]
        user=SimpleNamespace(id=uuid.uuid4()),  # type: ignore[arg-type]
    )
    assert source.enabled is True
    assert source.status == "healthy"
    assert db.commits == 1
    assert any(isinstance(item, AuditLog) and item.action == "enable_source" for item in db.added)


@pytest.mark.asyncio
async def test_enable_source_is_idempotent_when_already_enabled() -> None:
    source = _source(enabled=True, status="degraded")
    db = _FakeSession(source)
    await enable_source(
        source.id,
        db=db,  # type: ignore[arg-type]
        user=SimpleNamespace(id=uuid.uuid4()),  # type: ignore[arg-type]
    )
    assert source.status == "degraded"
    assert db.commits == 0
    assert db.added == []


@pytest.mark.parametrize("path", ["duplicate", "enable"])
def test_source_write_routes_reject_viewers(path: str) -> None:
    source = _source(enabled=False, status="offline")
    db = _FakeSession(source)

    async def fake_db() -> _FakeSession:
        return db

    async def viewer() -> SimpleNamespace:
        return SimpleNamespace(id=uuid.uuid4(), role="viewer")

    main.app.dependency_overrides[get_db] = fake_db
    main.app.dependency_overrides[get_current_user] = viewer
    try:
        with TestClient(main.app) as client:
            response = client.post(
                f"/api/v1/sources/{source.id}/{path}",
                json={"name": "Copy", "slug": "copy"} if path == "duplicate" else None,
            )
        assert response.status_code == 403
    finally:
        main.app.dependency_overrides.clear()


def test_enable_route_allows_operator() -> None:
    source = _source(enabled=False, status="offline")
    db = _FakeSession(source)

    async def fake_db() -> _FakeSession:
        return db

    async def operator() -> SimpleNamespace:
        return SimpleNamespace(id=uuid.uuid4(), role="operator")

    main.app.dependency_overrides[get_db] = fake_db
    main.app.dependency_overrides[get_current_user] = operator
    try:
        with TestClient(main.app) as client:
            response = client.post(f"/api/v1/sources/{source.id}/enable")
        assert response.status_code == 204
        assert source.enabled is True
        assert source.status == "healthy"
    finally:
        main.app.dependency_overrides.clear()
