"""Test del motore di scraping generico in modalità `render_js=True`
(Scrapling DynamicFetcher su Chromium headless), contro le stesse fixture HTML sintetiche
usate da `test_generic_scraper.py` (`tests/scrapers/conftest.py`) — nessuna
richiesta verso siti reali. Le fixture non richiedono JavaScript per
mostrare il proprio contenuto: qui si verifica che il percorso browser
produca esattamente gli stessi risultati del percorso HTTP sui casi
semplici, e che robots.txt/rate limit restino identici indipendentemente
dal motore di fetch usato.

Richiede i browser Playwright installati (`playwright install chromium`,
vedi `backend/Dockerfile`): se Chromium non è disponibile, i test di questo
modulo vengono saltati invece di fallire, per non bloccare run locali senza
browser installato.
"""

from __future__ import annotations

import pytest

pytest.importorskip("playwright")

from app.scrapers.generic import GenericScraper, RobotsDisallowedError

_BASE_CONFIG = {
    "ad_link_selector": "a.ad-link",
    "next_page_selector": "a.next",
    "max_pages": 5,
    "max_ads_per_run": 50,
    "rate_limit_seconds": 0,  # test rapidi: la validazione min=1.0 vive solo nello schema API
    "render_js": True,
    "fields": {
        "title": {"selector": "h1.ad-title", "attribute": "text"},
        "description": {"selector": "p.ad-description", "attribute": "text"},
        "phone": {"selector": "span.ad-phone", "attribute": "text"},
        "images": {"selector": "div.ad-gallery img", "attribute": "src", "multiple": True},
    },
}


@pytest.fixture
async def _chromium_ready() -> None:
    from playwright.async_api import async_playwright

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            await browser.close()
    except Exception as exc:  # noqa: BLE001 - qualunque fallimento di avvio => skip, non errore
        pytest.skip(f"Browser Playwright (Chromium) non disponibile: {exc}")


def _scraper(base_url: str, **overrides) -> GenericScraper:
    config = {**_BASE_CONFIG, "start_urls": [f"{base_url}/listing.html"], **overrides}
    return GenericScraper(slug="test_source", base_url=base_url, config=config)


async def test_discover_follows_pagination_and_collects_all_ad_links(
    _chromium_ready: None, open_site_url: str
) -> None:
    scraper = _scraper(open_site_url)
    try:
        urls = await scraper.discover()
    finally:
        await scraper.aclose()

    assert len(urls) == 3
    assert urls[0].endswith("/ad1.html")
    assert urls[1].endswith("/ad2.html")
    assert urls[2].endswith("/ad3.html")  # dalla pagina 2, raggiunta via next_page_selector


async def test_scrape_ad_extracts_configured_fields(
    _chromium_ready: None, open_site_url: str
) -> None:
    scraper = _scraper(open_site_url)
    try:
        raw = await scraper.scrape_ad(f"{open_site_url}/ad1.html")
    finally:
        await scraper.aclose()

    assert raw["title"] == "Synthetic Ad One"
    assert raw["description"] == "This is a synthetic test fixture, not real content."
    assert raw["phone"] == "+39 333 111 1111"
    assert raw["images"] == ["/img1.jpg", "/img2.jpg"]


async def test_download_media_uses_scrapling_http_regardless_of_render_js(
    _chromium_ready: None, open_site_url: str
) -> None:
    """I media (immagini) sono sempre scaricati via Scrapling HTTP, mai via
    browser, anche quando `render_js=True`: vedi
    `GenericScraper.download_media`."""
    from app.services.media_storage import sniff_mime_type

    scraper = _scraper(open_site_url)
    try:
        raw = await scraper.scrape_ad(f"{open_site_url}/ad1.html")
        normalized = scraper.normalize(raw)
        media = await scraper.download_media(normalized)
    finally:
        await scraper.aclose()

    assert len(media) == 2
    assert all(sniff_mime_type(blob) == "image/jpeg" for blob in media)


async def test_robots_disallow_blocks_discover_entirely(
    _chromium_ready: None, closed_site_url: str
) -> None:
    """`closed_site_url` ha un robots.txt con `Disallow: /`: anche in
    modalità browser, `discover()` deve rifiutarsi di navigare anche solo
    la pagina di elenco — l'enforcement robots.txt avviene prima della
    navigazione, non è specifico del motore HTTP."""
    scraper = _scraper(closed_site_url)
    try:
        with pytest.raises(RobotsDisallowedError):
            await scraper.discover()
    finally:
        await scraper.aclose()


async def test_robots_disallow_blocks_individual_ad_pages(
    _chromium_ready: None, closed_site_url: str
) -> None:
    scraper = _scraper(closed_site_url)
    try:
        with pytest.raises(RobotsDisallowedError):
            await scraper.scrape_ad(f"{closed_site_url}/ad1.html")
    finally:
        await scraper.aclose()
