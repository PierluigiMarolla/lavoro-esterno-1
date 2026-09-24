"""Diagnostica di raccolta e persistenza dei risultati dello scraper."""

from __future__ import annotations

from app.models.sources import Source
from app.scrapers.base import MediaDownloadResult
from app.scrapers.generic import DiscoveryDiagnostics, ScrapeCancelledError
from app.services.scrape_ingest import (
    collect_ads,
    decode_scrape_error_message,
    encode_scrape_error_message,
)


def test_scrape_error_code_round_trip_and_legacy_compatibility() -> None:
    encoded = encode_scrape_error_message("anti_bot_blocked", "Blocco Cloudflare.")

    assert decode_scrape_error_message(encoded) == (
        "anti_bot_blocked",
        "Blocco Cloudflare.",
    )
    assert decode_scrape_error_message("Errore precedente.") == (None, "Errore precedente.")
    partial = encode_scrape_error_message(
        "field_pagination_incomplete", "Paginazione incompleta per il campo 'reviews'."
    )
    assert decode_scrape_error_message(partial) == (
        "field_pagination_incomplete",
        "Paginazione incompleta per il campo 'reviews'.",
    )
    persistence = encode_scrape_error_message(
        "persistence_failed", "Salvataggio dell'annuncio non riuscito."
    )
    assert decode_scrape_error_message(persistence) == (
        "persistence_failed",
        "Salvataggio dell'annuncio non riuscito.",
    )


async def test_collect_ads_surfaces_empty_media_selector_and_keeps_ad(
    open_site_url: str,
) -> None:
    source = Source(
        name="Synthetic source",
        slug="synthetic_source",
        base_url=open_site_url,
        scrape_config={
            "start_urls": [f"{open_site_url}/listing.html"],
            "ad_link_selector": "a.ad-link",
            "next_page_selector": "a.next",
            "max_pages": 5,
            "max_ads_per_run": 50,
            "rate_limit_seconds": 0,
            "fields": {
                "title": {"selector": "h1.ad-title", "attribute": "text"},
                "phone": {"selector": "span.ad-phone", "attribute": "text"},
                "images": {
                    "selector": "div.ad-gallery img",
                    "attribute": "src",
                    "multiple": True,
                },
            },
        },
    )

    result = await collect_ads(source)

    # ad1 e ad2 hanno un telefono e vengono mantenuti; ad2 non ha immagini.
    assert len(result.ads) == 2
    assert any(
        error.url.endswith("/ad2.html") and "Nessun URL immagine trovato" in error.message
        for error in result.errors
    )
    assert any(
        error.url.endswith("/ad3.html") and error.message == "Nessun numero di telefono estratto."
        for error in result.errors
    )


async def test_collect_ads_surfaces_ambiguous_pagination_selector(
    open_site_url: str,
) -> None:
    source = Source(
        name="Synthetic source",
        slug="synthetic_source",
        base_url=open_site_url,
        scrape_config={
            "start_urls": [f"{open_site_url}/listing.html"],
            "ad_link_selector": "a.ad-link",
            "next_page_selector": "a",
            "max_pages": 2,
            "max_ads_per_run": 50,
            "rate_limit_seconds": 0,
            "fields": {
                "phone": {"selector": "span.ad-phone", "attribute": "text"},
            },
        },
    )

    result = await collect_ads(source)

    assert len(result.ads) == 2
    assert result.discovery_diagnostics.stop_reason == "ambiguous_next_control"
    assert any("controlli Next non equivalenti" in error.message for error in result.errors)


async def test_collect_ads_stops_after_source_is_paused_and_keeps_completed_items(
    monkeypatch,
) -> None:
    """La pausa ferma il prossimo annuncio senza perdere quello gia completato."""

    paused = False
    scraped_urls: list[str] = []

    class FakeScraper:
        def __init__(self, **_kwargs) -> None:
            self.should_stop = None
            self.discovery_diagnostics = DiscoveryDiagnostics()
            self.proxy_events = []
            self.field_pagination_warnings = []
            self.discovered_page_numbers = {
                "https://example.test/ad/1": 1,
                "https://example.test/ad/2": 1,
            }

        def _raise_if_cancelled(self) -> None:
            if self.should_stop is not None and self.should_stop():
                self.discovery_diagnostics.stop_reason = "source_paused"
                raise ScrapeCancelledError("source_paused")

        async def discover(self) -> list[str]:
            return ["https://example.test/ad/1", "https://example.test/ad/2"]

        async def scrape_ad(self, url: str) -> dict:
            scraped_urls.append(url)
            return {"phone": "+393331234567", "source_url": url}

        def normalize(self, raw: dict) -> dict:
            return {**raw, "phone_raw": raw["phone"]}

        def media_extraction_warnings(self, _raw: dict) -> list[str]:
            return []

        async def download_media(self, _normalized: dict) -> MediaDownloadResult:
            return MediaDownloadResult()

        async def aclose(self) -> None:
            return None

    monkeypatch.setattr("app.services.scrape_ingest.GenericScraper", FakeScraper)
    source = Source(
        name="Synthetic source",
        slug="synthetic_source",
        base_url="https://example.test",
        scrape_config={},
    )

    def publish_first(_item) -> bool:
        nonlocal paused
        paused = True
        return True

    result = await collect_ads(
        source,
        on_ad=publish_first,
        should_stop=lambda: paused,
    )

    assert result.cancelled is True
    assert result.discovery_diagnostics.stop_reason == "source_paused"
    assert scraped_urls == ["https://example.test/ad/1"]
    assert len(result.ads) == 1
