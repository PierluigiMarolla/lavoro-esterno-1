"""Contratto di pubblicazione incrementale degli annunci raccolti."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

from app.services import scrape_ingest
from app.services.scrape_ingest import (
    CollectedAd,
    CollectionResult,
    ScrapeErrorDetail,
    persist_collected_ads,
)


class _NestedTransaction:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


class _Result:
    def scalar_one_or_none(self):
        return None


class _Session:
    def __init__(self, run=None) -> None:
        self.commits = 0
        self.run = run
        self.added = []

    def begin_nested(self):
        return _NestedTransaction()

    def execute(self, _statement):
        return _Result()

    def flush(self) -> None:
        return None

    def commit(self) -> None:
        self.commits += 1

    def get(self, _model, _identifier):
        return self.run

    def add(self, value) -> None:
        self.added.append(value)


def _invalid_ad(index: int) -> CollectedAd:
    return CollectedAd(
        normalized={
            "phone_raw": "numero-non-valido",
            "source_url": f"https://example.test/ad/{index}",
        }
    )


def test_batch_one_commits_every_completed_ad() -> None:
    session = _Session()
    items = [_invalid_ad(index) for index in range(3)]

    result = persist_collected_ads(
        session,  # type: ignore[arg-type]
        SimpleNamespace(base_url="https://example.test", country_code="IT", slug="test"),
        CollectionResult(ads=items),
        batch_size=1,
    )

    assert session.commits == 3
    assert result["errors_count"] == 3
    assert all(item.persistence_outcome == "rejected_invalid_phone" for item in items)


def test_larger_batch_commits_full_groups_and_final_remainder() -> None:
    session = _Session()

    persist_collected_ads(
        session,  # type: ignore[arg-type]
        SimpleNamespace(base_url="https://example.test", country_code="IT", slug="test"),
        CollectionResult(ads=[_invalid_ad(index) for index in range(3)]),
        batch_size=2,
    )

    assert session.commits == 2


def test_run_progress_is_committed_with_each_batch() -> None:
    run = SimpleNamespace(
        items_found=0,
        items_new=0,
        items_updated=0,
        items_unchanged=0,
        errors_count=0,
        warnings_count=0,
        id=uuid.uuid4(),
    )
    session = _Session(run)

    persist_collected_ads(
        session,  # type: ignore[arg-type]
        SimpleNamespace(base_url="https://example.test", country_code="IT", slug="test"),
        CollectionResult(ads=[_invalid_ad(index) for index in range(2)]),
        run_id=run.id,
        batch_size=1,
    )

    assert session.commits == 2
    assert run.items_found == 2
    assert run.errors_count == 2
    assert len(session.added) == 2


def test_warning_is_committed_without_incrementing_errors_or_items_found() -> None:
    run = SimpleNamespace(
        items_found=0,
        items_new=0,
        items_updated=0,
        items_unchanged=0,
        errors_count=0,
        warnings_count=0,
        id=uuid.uuid4(),
    )
    session = _Session(run)
    warning = ScrapeErrorDetail(
        url="https://example.test/ad/1",
        message="Testo originale conservato.",
        code="content_sanitization_timeout",
        severity="warning",
    )

    result = persist_collected_ads(
        session,  # type: ignore[arg-type]
        SimpleNamespace(base_url="https://example.test", country_code="IT", slug="test"),
        CollectionResult(ads=[], errors=[warning]),
        run_id=run.id,
        batch_size=1,
    )

    assert run.items_found == 0
    assert run.errors_count == 0
    assert run.warnings_count == 1
    assert result["errors_count"] == 0
    assert result["warnings_count"] == 1


def test_unexpected_item_failure_is_isolated_and_next_item_is_processed(monkeypatch) -> None:
    session = _Session()
    first = CollectedAd(
        normalized={
            "phone_raw": "+393331234567",
            "source_url": "https://example.test/ad/first",
        }
    )
    second = _invalid_ad(2)

    def fail_record_creation(*_args, **_kwargs):
        raise RuntimeError("database detail that must not be exposed")

    monkeypatch.setattr(scrape_ingest, "_get_or_create_record", fail_record_creation)

    result = persist_collected_ads(
        session,  # type: ignore[arg-type]
        SimpleNamespace(base_url="https://example.test", country_code="IT", slug="test"),
        CollectionResult(ads=[first, second]),
        batch_size=1,
    )

    assert session.commits == 2
    assert first.persistence_outcome == "persistence_failed"
    assert second.persistence_outcome == "rejected_invalid_phone"
    assert result["errors"][0].code == "persistence_failed"
    assert "database detail" not in result["errors"][0].message
