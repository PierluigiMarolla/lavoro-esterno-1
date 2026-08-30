"""Test del motore di scraping generico (`app/scrapers/generic.py`) contro
fixture HTML sintetiche servite da un server HTTP locale
(`tests/scrapers/conftest.py`) — nessuna richiesta verso siti reali.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from app.scrapers.base import Scraper
from app.scrapers.generic import GenericScraper, RobotsDisallowedError

_BASE_CONFIG = {
    "ad_link_selector": "a.ad-link",
    "next_page_selector": "a.next",
    "max_pages": 5,
    "max_ads_per_run": 50,
    "rate_limit_seconds": 0,  # test rapidi: la validazione min=1.0 vive solo nello schema API
    "fields": {
        "title": {"selector": "h1.ad-title", "attribute": "text"},
        "description": {"selector": "p.ad-description", "attribute": "text"},
        "phone": {"selector": "span.ad-phone", "attribute": "text"},
        "images": {"selector": "div.ad-gallery img", "attribute": "src", "multiple": True},
    },
}


def _scraper(base_url: str, **overrides) -> GenericScraper:
    config = {**_BASE_CONFIG, "start_urls": [f"{base_url}/listing.html"], **overrides}
    return GenericScraper(slug="test_source", base_url=base_url, config=config)


@pytest.fixture
def user_agent_site_url() -> Iterator[tuple[str, list[tuple[str, str | None]]]]:
    requests: list[tuple[str, str | None]] = []

    class RecordingHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            requests.append((self.path, self.headers.get("User-Agent")))
            if self.path == "/robots.txt":
                body = b"User-agent: *\nAllow: /\n"
            elif self.path == "/listing.html":
                body = b'<html><body><a class="ad-link" href="/ad1.html">Ad 1</a></body></html>'
            else:
                body = b"<html><body></body></html>"

            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, message_format: str, *args: object) -> None:
            return None

    server = ThreadingHTTPServer(("127.0.0.1", 0), RecordingHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    try:
        yield f"http://{host}:{port}", requests
    finally:
        server.shutdown()


def test_user_agent_falls_back_to_scraper_default(open_site_url: str) -> None:
    scraper = _scraper(open_site_url)

    assert scraper.user_agent == Scraper.user_agent


async def test_custom_user_agent_is_sent_in_http_requests(
    user_agent_site_url: tuple[str, list[tuple[str, str | None]]],
) -> None:
    base_url, requests = user_agent_site_url
    scraper = _scraper(base_url, user_agent="CustomScraper/2.0")
    try:
        await scraper.discover()
    finally:
        await scraper.aclose()

    assert ("/listing.html", "CustomScraper/2.0") in requests


async def test_custom_user_agent_is_used_for_robots_check(
    monkeypatch: pytest.MonkeyPatch, open_site_url: str
) -> None:
    seen_user_agents: list[str] = []

    def fake_is_allowed(robots_txt: str | None, url: str, user_agent: str) -> bool:
        seen_user_agents.append(user_agent)
        return True

    monkeypatch.setattr("app.services.robots_check.is_allowed", fake_is_allowed)
    scraper = _scraper(open_site_url, user_agent="RobotsCheckAgent/3.0")

    try:
        await scraper.discover()
    finally:
        await scraper.aclose()

    assert seen_user_agents
    assert all(user_agent == "RobotsCheckAgent/3.0" for user_agent in seen_user_agents)


async def test_legacy_render_js_routes_to_dynamic_fetcher(
    monkeypatch: pytest.MonkeyPatch, open_site_url: str
) -> None:
    calls: list[str] = []
    scraper = _scraper(open_site_url, render_js=True)

    async def skip_robots() -> None:
        return None

    async def fake_dynamic(url: str):
        calls.append(url)
        raise RuntimeError("stop after routing")

    monkeypatch.setattr(scraper, "_ensure_robots_loaded", skip_robots)
    monkeypatch.setattr("app.services.robots_check.is_allowed", lambda *args: True)
    monkeypatch.setattr(scraper, "_fetch_page_dynamic", fake_dynamic)

    with pytest.raises(Exception, match="stop after routing"):
        await scraper._fetch_page(f"{open_site_url}/listing.html")

    assert scraper.fetch_mode == "dynamic"
    assert calls == [f"{open_site_url}/listing.html"]


async def test_fetch_mode_stealth_routes_to_stealth_fetcher(
    monkeypatch: pytest.MonkeyPatch, open_site_url: str
) -> None:
    calls: list[str] = []
    scraper = _scraper(open_site_url, fetch_mode="stealth")

    async def skip_robots() -> None:
        return None

    async def fake_stealth(url: str):
        calls.append(url)
        raise RuntimeError("stop after routing")

    monkeypatch.setattr(scraper, "_ensure_robots_loaded", skip_robots)
    monkeypatch.setattr("app.services.robots_check.is_allowed", lambda *args: True)
    monkeypatch.setattr(scraper, "_fetch_page_stealth", fake_stealth)

    with pytest.raises(Exception, match="stop after routing"):
        await scraper._fetch_page(f"{open_site_url}/listing.html")

    assert calls == [f"{open_site_url}/listing.html"]


async def test_discover_follows_pagination_and_collects_all_ad_links(open_site_url: str) -> None:
    scraper = _scraper(open_site_url)
    urls = await scraper.discover()

    assert len(urls) == 3
    assert urls[0].endswith("/ad1.html")
    assert urls[1].endswith("/ad2.html")
    assert urls[2].endswith("/ad3.html")  # dalla pagina 2, raggiunta via next_page_selector


async def test_discover_stops_at_max_pages(open_site_url: str) -> None:
    scraper = _scraper(open_site_url, max_pages=1)
    urls = await scraper.discover()

    # Solo la prima pagina: i 2 annunci lì elencati, non il terzo (pagina 2).
    assert len(urls) == 2


async def test_discover_stops_at_max_ads_per_run(open_site_url: str) -> None:
    scraper = _scraper(open_site_url, max_ads_per_run=1)
    urls = await scraper.discover()

    assert len(urls) == 1


async def test_scrape_ad_extracts_configured_fields(open_site_url: str) -> None:
    scraper = _scraper(open_site_url)
    raw = await scraper.scrape_ad(f"{open_site_url}/ad1.html")

    assert raw["title"] == "Synthetic Ad One"
    assert raw["description"] == "This is a synthetic test fixture, not real content."
    assert raw["phone"] == "+39 333 111 1111"
    assert raw["images"] == ["/img1.jpg", "/img2.jpg"]


async def test_normalize_maps_raw_fields_to_common_shape(open_site_url: str) -> None:
    scraper = _scraper(open_site_url)
    raw = await scraper.scrape_ad(f"{open_site_url}/ad1.html")
    normalized = scraper.normalize(raw)

    assert normalized["title"] == "Synthetic Ad One"
    assert normalized["phone_raw"] == "+39 333 111 1111"
    assert normalized["images"] == ["/img1.jpg", "/img2.jpg"]


async def test_ad_without_phone_has_no_phone_raw(open_site_url: str) -> None:
    """ad3.html non ha un campo telefono: verifica che il motore non
    inventi nulla, lasciando alla pipeline di ingestione la decisione di
    scartare l'annuncio (vedi app/services/scrape_ingest.py:collect_ads)."""
    scraper = _scraper(open_site_url)
    raw = await scraper.scrape_ad(f"{open_site_url}/ad3.html")
    normalized = scraper.normalize(raw)

    assert normalized["phone_raw"] is None


async def test_download_media_fetches_real_bytes_and_sniffs_as_jpeg(open_site_url: str) -> None:
    from app.services.media_storage import sniff_mime_type

    scraper = _scraper(open_site_url)
    raw = await scraper.scrape_ad(f"{open_site_url}/ad1.html")
    normalized = scraper.normalize(raw)

    media = await scraper.download_media(normalized)

    assert len(media) == 2
    assert all(sniff_mime_type(blob) == "image/jpeg" for blob in media)


async def test_robots_disallow_blocks_discover_entirely(closed_site_url: str) -> None:
    """`closed_site_url` ha un robots.txt con `Disallow: /`: `discover()`
    deve rifiutarsi di scaricare anche solo la pagina di elenco, non solo
    i singoli annunci — il divieto non è un'opzione aggirabile."""
    scraper = _scraper(closed_site_url)

    with pytest.raises(RobotsDisallowedError):
        await scraper.discover()


async def test_robots_disallow_blocks_individual_ad_pages(closed_site_url: str) -> None:
    """Anche chiamando `scrape_ad` direttamente su un URL noto (bypassando
    `discover`), il divieto robots.txt deve comunque applicarsi: non è solo
    un controllo "all'ingresso" del crawl."""
    scraper = _scraper(closed_site_url)

    with pytest.raises(RobotsDisallowedError):
        await scraper.scrape_ad(f"{closed_site_url}/ad1.html")
