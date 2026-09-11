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

import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

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


@pytest.fixture
def browser_cookie_site_url() -> Iterator[str]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == "/robots.txt":
                body = b"User-agent: *\nAllow: /\n"
                cookie = None
            elif self.path == "/seed":
                body = b"<html><body>seeded</body></html>"
                cookie = "cf_clearance=synthetic; Path=/; HttpOnly"
            else:
                has_cookie = "cf_clearance=synthetic" in (self.headers.get("Cookie") or "")
                body = (
                    b'<html><body><span class="cookie-ok">yes</span></body></html>'
                    if has_cookie
                    else b'<html><body><span class="cookie-missing">no</span></body></html>'
                )
                cookie = None
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            if cookie:
                self.send_header("Set-Cookie", cookie)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, message_format: str, *args: object) -> None:
            return None

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    try:
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()


@pytest.fixture
def javascript_pagination_site_url() -> Iterator[str]:
    listing = b"""<!doctype html><html><body>
    <div id="overlay" style="position:fixed;inset:0;z-index:20"></div>
    <div id="ads"></div><a class="next" aria-label="Next">Next</a>
    <script>
      const pages = [
        ['/ad1.html', '/ad2.html'],
        ['/ad2.html', '/ad3.html'],
        ['/ad4.html']
      ];
      let pageIndex = 0;
      function render() {
        document.querySelector('#ads').innerHTML = pages[pageIndex]
          .map((href) => `<a class="ad-link" href="${href}">${href}</a>`).join('');
        if (pageIndex === pages.length - 1) document.querySelector('.next')?.remove();
      }
      document.querySelector('.next').addEventListener('click', () => {
        pageIndex += 1;
        render();
      });
      render();
    </script></body></html>"""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            body = b"User-agent: *\nAllow: /\n" if self.path == "/robots.txt" else listing
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, message_format: str, *args: object) -> None:
            return None

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    try:
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()


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
    assert scraper.discovery_diagnostics.pages_visited == 2
    assert scraper.discovery_diagnostics.pagination_mode == "href"
    assert scraper.discovery_diagnostics.stop_reason == "end_of_pagination"


async def test_discover_clicks_javascript_next_under_overlay_and_deduplicates(
    _chromium_ready: None, javascript_pagination_site_url: str
) -> None:
    scraper = _scraper(
        javascript_pagination_site_url,
        start_urls=[f"{javascript_pagination_site_url}/listing.html"],
        next_page_selector='a.next[aria-label="Next"]',
        max_pages=3,
    )
    try:
        urls = await scraper.discover()
    finally:
        await scraper.aclose()

    assert [url.rsplit("/", 1)[-1] for url in urls] == [
        "ad1.html",
        "ad2.html",
        "ad3.html",
        "ad4.html",
    ]
    assert scraper.discovery_diagnostics.pages_visited == 3
    assert scraper.discovery_diagnostics.pagination_mode == "click"
    assert scraper.discovery_diagnostics.stop_reason == "max_pages"
    assert scraper.discovery_diagnostics.unique_ads_found == 4


async def test_http_mode_reports_javascript_only_pagination(
    javascript_pagination_site_url: str,
) -> None:
    scraper = _scraper(
        javascript_pagination_site_url,
        start_urls=[f"{javascript_pagination_site_url}/listing.html"],
        render_js=False,
        fetch_mode="http",
        next_page_selector='a.next[aria-label="Next"]',
        max_pages=3,
    )
    try:
        await scraper.discover()
    finally:
        await scraper.aclose()

    assert scraper.discovery_diagnostics.pages_visited == 1
    assert scraper.discovery_diagnostics.stop_reason == "click_requires_browser"
    assert scraper.discovery_diagnostics.errors == [
        "Il controllo Next non ha href: usare il mode dynamic o stealth."
    ]


async def test_browser_reports_click_that_does_not_change_page(
    _chromium_ready: None,
    javascript_pagination_site_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.scrapers.generic._PAGINATION_CHANGE_TIMEOUT_MS", 200)
    scraper = _scraper(
        javascript_pagination_site_url,
        start_urls=[f"{javascript_pagination_site_url}/listing.html"],
        next_page_selector="#overlay",
        max_pages=2,
    )
    try:
        await scraper.discover()
    finally:
        await scraper.aclose()

    assert scraper.discovery_diagnostics.pages_visited == 1
    assert scraper.discovery_diagnostics.stop_reason == "page_did_not_change"
    assert scraper.discovery_diagnostics.errors == [
        "Il controllo Next non ha modificato URL o annunci entro il timeout."
    ]


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


async def test_browser_session_preserves_cookies_between_pages(
    _chromium_ready: None, browser_cookie_site_url: str
) -> None:
    scraper = _scraper(browser_cookie_site_url)
    try:
        await scraper._fetch_page(f"{browser_cookie_site_url}/seed")
        response = await scraper._fetch_page(f"{browser_cookie_site_url}/check")
    finally:
        await scraper.aclose()

    assert response.css(".cookie-ok::text").get() == "yes"


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

    assert len(media.media_bytes) == 2
    assert media.failed_count == 0
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
