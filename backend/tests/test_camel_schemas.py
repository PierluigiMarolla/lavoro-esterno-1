"""Verifica che gli schemi di risposta "view" (quelli che ereditano da
`CamelModel`, vedi app/schemas/common.py) serializzino davvero in camelCase.

È un dettaglio facile da rompere per errore (basta dimenticare
`CamelModel` come base, o un typo nel nome campo) e critico: i moduli
`frontend/src/api/dashboard.ts`, `records.ts`, `sources.ts`, `exports.ts` e
`admin.ts` chiamano `apiRequest<T>` con il tipo TypeScript camelCase
DIRETTAMENTE, senza alcun mapping snake->camel lato client (a differenza di
`auth.ts`). Se il backend rispondesse in snake_case, il frontend leggerebbe
semplicemente `undefined` per ogni campo, silenziosamente.

Testiamo qui la sola serializzazione Pydantic (`model_dump(mode="json",
by_alias=True)`, lo stesso meccanismo che FastAPI usa di default per i
response_model, vedi APIRoute.response_model_by_alias=True) — senza
coinvolgere il layer DB/router, per gli stessi motivi di
tests/test_dashboard_metrics.py.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.schemas.dashboard import DashboardKpisRead, SourceHealthBreakdownRead
from app.schemas.exports import ExportJobOut
from app.schemas.records import RecordSearchResultRead
from app.schemas.sources import SourcesSummaryRead


def test_dashboard_kpis_serializes_camel_case() -> None:
    kpis = DashboardKpisRead(
        total_records=10,
        total_records_delta_pct=5.0,
        active_sources=3,
        active_sources_healthy_pct=100.0,
        new_records_today=2,
        scraping_errors=0,
        scraping_errors_delta=0,
        active_exports=1,
    )
    dumped = kpis.model_dump(mode="json", by_alias=True)
    assert dumped["totalRecords"] == 10
    assert dumped["totalRecordsDeltaPct"] == 5.0
    assert dumped["activeSourcesHealthyPct"] == 100.0
    assert dumped["scrapingErrorsDelta"] == 0
    assert "total_records" not in dumped


def test_source_health_breakdown_serializes_camel_case() -> None:
    breakdown = SourceHealthBreakdownRead(healthy=1, rate_limited=2, error=3, total=6)
    dumped = breakdown.model_dump(mode="json", by_alias=True)
    assert dumped == {"healthy": 1, "rateLimited": 2, "error": 3, "total": 6}


def test_sources_summary_serializes_camel_case() -> None:
    summary = SourcesSummaryRead(total=4, active=2, degraded=1, offline=1)
    dumped = summary.model_dump(mode="json", by_alias=True)
    assert dumped == {"total": 4, "active": 2, "degraded": 1, "offline": 1}


def test_record_search_result_serializes_camel_case() -> None:
    now = datetime.now(UTC)
    result = RecordSearchResultRead(
        id=uuid.uuid4(),
        phone="+393331234567",
        canonical_title="Titolo",
        sources_count=2,
        occurrences_count=5,
        first_seen_at=now,
        last_seen_at=now,
        status="verified",
    )
    dumped = result.model_dump(mode="json", by_alias=True)
    expected_keys = {
        "id",
        "phone",
        "canonicalTitle",
        "sourcesCount",
        "occurrencesCount",
        "firstSeenAt",
        "lastSeenAt",
        "status",
    }
    assert expected_keys <= set(dumped.keys())
    assert "canonical_title" not in dumped


def test_export_job_out_serializes_camel_case() -> None:
    job = ExportJobOut(
        id=uuid.uuid4(),
        type="text_only",
        status="pending",
        progress_pct=0,
        requested_by="analyst@example.com",
        requested_at=datetime.now(UTC),
        record_count=1,
        download_url=None,
    )
    dumped = job.model_dump(mode="json", by_alias=True)
    assert dumped["progressPct"] == 0
    assert dumped["requestedBy"] == "analyst@example.com"
    assert dumped["recordCount"] == 1
    assert dumped["downloadUrl"] is None
