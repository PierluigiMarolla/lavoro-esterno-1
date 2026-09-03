"""Test di validazione per gli schemi di configurazione delle fonti
(`app/schemas/sources.py`), in particolare `ScrapeConfigInput` — la
validazione qui è l'unica barriera prima che una configurazione venga
salvata su `Source.scrape_config` e usata da `GenericScraper` per
eseguire richieste HTTP reali (vedi PROGETTO.md § 4)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.sources import ScrapeConfigInput, SourceCreate

_VALID_FIELDS = {
    "phone": {"selector": ".phone", "attribute": "text"},
    "title": {"selector": ".title", "attribute": "text"},
}


def test_scrape_config_requires_phone_field() -> None:
    with pytest.raises(ValidationError, match="phone"):
        ScrapeConfigInput(
            start_urls=["https://example.com/listing"],
            ad_link_selector=".ad",
            fields={"title": {"selector": ".title"}},
        )


def test_scrape_config_accepts_valid_input() -> None:
    config = ScrapeConfigInput(
        start_urls=["https://example.com/listing"],
        ad_link_selector=".ad",
        fields=_VALID_FIELDS,
    )
    assert config.max_pages == 3  # default
    assert config.rate_limit_seconds == 2.0  # default
    assert config.fetch_mode == "http"


def test_scrape_config_rejects_singular_image_field() -> None:
    with pytest.raises(ValidationError, match="images.*plurale"):
        ScrapeConfigInput(
            start_urls=["https://example.com/listing"],
            ad_link_selector=".ad",
            fields={
                **_VALID_FIELDS,
                "image": {"selector": "img", "attribute": "src", "multiple": True},
            },
        )


@pytest.mark.parametrize(
    "media_field",
    [
        {"selector": "img", "attribute": "src", "multiple": False},
        {"selector": "img", "attribute": "text", "multiple": True},
    ],
)
def test_scrape_config_rejects_invalid_media_field(media_field: dict) -> None:
    with pytest.raises(ValidationError):
        ScrapeConfigInput(
            start_urls=["https://example.com/listing"],
            ad_link_selector=".ad",
            fields={**_VALID_FIELDS, "images": media_field},
        )


def test_scrape_config_maps_legacy_render_js_to_dynamic_fetch_mode() -> None:
    config = ScrapeConfigInput(
        start_urls=["https://example.com/listing"],
        ad_link_selector=".ad",
        fields=_VALID_FIELDS,
        render_js=True,
    )

    assert config.fetch_mode == "dynamic"


def test_scrape_config_accepts_stealth_options() -> None:
    config = ScrapeConfigInput(
        start_urls=["https://example.com/listing"],
        ad_link_selector=".ad",
        fields=_VALID_FIELDS,
        fetch_mode="stealth",
        solve_cloudflare=True,
        block_webrtc=True,
        hide_canvas=True,
        real_chrome=True,
        block_ads=True,
        proxy="http://proxy.example:8080",
        wait_selector=".loaded",
        wait_ms=500,
    )

    assert config.fetch_mode == "stealth"
    assert config.solve_cloudflare is True
    assert config.proxy == "http://proxy.example:8080"
    assert config.wait_selector == ".loaded"
    assert config.wait_ms == 500


def test_scrape_config_rejects_invalid_fetch_mode() -> None:
    with pytest.raises(ValidationError):
        ScrapeConfigInput(
            start_urls=["https://example.com/listing"],
            ad_link_selector=".ad",
            fields=_VALID_FIELDS,
            fetch_mode="invalid",
        )


def test_scrape_config_rejects_invalid_proxy() -> None:
    with pytest.raises(ValidationError):
        ScrapeConfigInput(
            start_urls=["https://example.com/listing"],
            ad_link_selector=".ad",
            fields=_VALID_FIELDS,
            proxy="not-a-proxy-url",
        )


def test_scrape_config_accepts_optional_user_agent() -> None:
    config = ScrapeConfigInput(
        start_urls=["https://example.com/listing"],
        ad_link_selector=".ad",
        fields=_VALID_FIELDS,
        user_agent="  CustomScraper/2.0  ",
    )

    assert config.user_agent == "CustomScraper/2.0"


def test_scrape_config_rejects_blank_user_agent() -> None:
    with pytest.raises(ValidationError):
        ScrapeConfigInput(
            start_urls=["https://example.com/listing"],
            ad_link_selector=".ad",
            fields=_VALID_FIELDS,
            user_agent="   ",
        )


def test_scrape_config_rejects_non_http_start_url() -> None:
    with pytest.raises(ValidationError):
        ScrapeConfigInput(
            start_urls=["ftp://example.com/listing"],
            ad_link_selector=".ad",
            fields=_VALID_FIELDS,
        )


def test_scrape_config_rejects_relative_start_url() -> None:
    with pytest.raises(ValidationError):
        ScrapeConfigInput(
            start_urls=["/listing"],
            ad_link_selector=".ad",
            fields=_VALID_FIELDS,
        )


def test_scrape_config_rate_limit_has_a_safety_floor() -> None:
    """Il rate limit non è disattivabile dalla configurazione (vedi
    PROGETTO.md § 4): un operatore non può azzerare la pausa tra le
    richieste, solo aumentarla."""
    with pytest.raises(ValidationError):
        ScrapeConfigInput(
            start_urls=["https://example.com/listing"],
            ad_link_selector=".ad",
            fields=_VALID_FIELDS,
            rate_limit_seconds=0,
        )


def test_scrape_config_caps_max_pages_and_max_ads() -> None:
    with pytest.raises(ValidationError):
        ScrapeConfigInput(
            start_urls=["https://example.com/listing"],
            ad_link_selector=".ad",
            fields=_VALID_FIELDS,
            max_pages=1000,
        )


def test_source_create_rejects_invalid_slug_characters() -> None:
    with pytest.raises(ValidationError):
        SourceCreate(
            name="Test Source",
            slug="Not A Valid Slug!",
            base_url="https://example.com",
        )


def test_source_create_accepts_valid_slug_without_scrape_config() -> None:
    source = SourceCreate(name="Test Source", slug="test_source", base_url="https://example.com")
    assert source.scrape_config is None
    assert source.priority == "medium"
