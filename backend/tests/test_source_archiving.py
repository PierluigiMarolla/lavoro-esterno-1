"""Regressioni per l'archiviazione reversibile e parziale delle fonti."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.api.v1.sources import _archive_sources
from app.models.audit_log import AuditLog
from app.models.sources import Source
from app.schemas.sources import SourceArchiveRequest


class _Result:
    def __init__(self, values: list[object]) -> None:
        self.values = values

    def scalars(self) -> _Result:
        return self

    def all(self) -> list[object]:
        return self.values


class _ArchiveSession:
    def __init__(self, sources: list[Source], active_source_ids: list[uuid.UUID]) -> None:
        self.results = [_Result(sources), _Result(active_source_ids)]
        self.added: list[object] = []
        self.commits = 0

    async def execute(self, _statement: object) -> _Result:
        return self.results.pop(0)

    def add(self, value: object) -> None:
        self.added.append(value)

    async def commit(self) -> None:
        self.commits += 1


def _source(name: str, *, archived: bool = False) -> Source:
    return Source(
        id=uuid.uuid4(),
        name=name,
        slug=name.lower(),
        base_url=f"https://{name.lower()}.example",
        enabled=True,
        automatic_scraping_enabled=True,
        next_scrape_at=datetime.now(UTC),
        schedule_revision=4,
        archived_at=datetime.now(UTC) if archived else None,
    )


def test_archive_request_enforces_scope_contract() -> None:
    with pytest.raises(ValidationError):
        SourceArchiveRequest(scope="selected", source_ids=[])
    with pytest.raises(ValidationError):
        SourceArchiveRequest(scope="all", source_ids=[uuid.uuid4()])


@pytest.mark.asyncio
async def test_archive_sources_preserves_rows_and_skips_active_or_archived() -> None:
    available = _source("Disponibile")
    running = _source("InEsecuzione")
    archived = _source("Archiviata", archived=True)
    db = _ArchiveSession([available, running, archived], [running.id])
    admin = SimpleNamespace(id=uuid.uuid4())

    result = await _archive_sources(
        db,  # type: ignore[arg-type]
        SourceArchiveRequest(
            scope="selected", source_ids=[available.id, running.id, archived.id]
        ),
        admin,  # type: ignore[arg-type]
    )

    assert result.requested == 3
    assert result.archived == 1
    assert {item.reason for item in result.skipped} == {"active_scrape", "already_archived"}
    assert available.archived_at is not None
    assert available.archived_by_user_id == admin.id
    assert available.enabled is False
    assert available.automatic_scraping_enabled is False
    assert available.next_scrape_at is None
    assert available.schedule_revision == 5
    assert running.archived_at is None
    assert db.commits == 1
    audit = next(value for value in db.added if isinstance(value, AuditLog))
    assert audit.action == "archive_sources"
    assert audit.details_json["source_ids"] == [str(available.id)]
    assert "base_url" not in str(audit.details_json)
