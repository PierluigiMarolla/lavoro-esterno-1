"""Motore di scraping generico, reale e configurabile.

`GenericScraper` non conosce alcun sito specifico: URL, selettori CSS per
link annunci/paginazione e campi da estrarre arrivano da
`Source.scrape_config` (JSONB, validato da
`app/schemas/sources.py:ScrapeConfigInput` prima di essere salvato).

Vincoli incorporati qui:
- `robots.txt` viene verificato PRIMA di ogni richiesta reale
  (`app/services/robots_check.py`); un URL vietato viene saltato.
- Rate limiting (`rate_limit_seconds`) applicato tra una richiesta e l'altra.
- `user_agent` viene letto dalla configurazione della fonte quando presente,
  con fallback al default di `Scraper`.
- Tetti di sicurezza (`max_pages`, `max_ads_per_run`) per evitare crawl
  incontrollati.

Il fetch delle pagine usa Scrapling:
- `fetch_mode="http"`: richiesta HTTP via `AsyncFetcher`.
- `fetch_mode="dynamic"`: browser headless via `DynamicFetcher`.
- `fetch_mode="stealth"`: browser headless via `StealthyFetcher` con opzioni
  anti-bot configurabili per fonte.

`render_js=True` resta supportato per retrocompatibilita e viene trattato come
`fetch_mode="dynamic"` quando `fetch_mode` non e presente.
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import socket
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from curl_cffi.requests import AsyncSession as CurlAsyncSession
from curl_cffi.requests.errors import RequestsError as CurlRequestsError
from lxml import html as lxml_html

from app.scrapers.base import MediaDownloadFailure, MediaDownloadResult, Scraper
from app.services.proxy_rotation import ProxyRuntimeConfig, ProxyRuntimeEvent

_DEFAULT_MAX_PAGES = 3
_DEFAULT_MAX_ADS_PER_RUN = 50
_REQUEST_TIMEOUT_SECONDS = 15.0
_BROWSER_NAVIGATION_TIMEOUT_MS = 20_000
_PAGINATION_CHANGE_TIMEOUT_MS = 15_000

logger = logging.getLogger(__name__)

_STANDARD_FIELDS = {"title", "description", "phone", "images", "videos", "source_url"}


class RobotsDisallowedError(Exception):
    """Sollevata quando `robots.txt` vieta l'accesso a un URL."""

    def __init__(self, url: str):
        super().__init__(f"robots.txt vieta l'accesso a: {url}")
        self.url = url


class PageFetchError(Exception):
    """Sollevata quando Scrapling non riesce a recuperare una pagina."""


class ProxyRetryableError(PageFetchError):
    """Failure that may be retried through another endpoint in the pool."""

    def __init__(self, category: str):
        super().__init__("Richiesta tramite proxy non riuscita.")
        self.category = category


class ProxyPoolExhaustedError(PageFetchError):
    """All candidates assigned to this run failed; direct access is forbidden."""


@dataclass
class DiscoveryDiagnostics:
    pages_visited: int = 0
    configured_max_pages: int = 1
    pagination_mode: str = "none"
    stop_reason: str = "not_started"
    unique_ads_found: int = 0
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class GenericScraper(Scraper):
    """Connettore generico guidato da configurazione."""

    def __init__(
        self,
        slug: str,
        base_url: str,
        config: dict[str, Any],
        proxy_candidates: list[ProxyRuntimeConfig] | None = None,
    ):
        self.slug = slug
        self.base_url = base_url
        self.config = config
        self.render_js = bool(self._config_value("render_js", "renderJs", False))
        self.fetch_mode = str(
            self._config_value("fetch_mode", "fetchMode")
            or ("dynamic" if self.render_js else "http")
        )
        if self.fetch_mode not in {"http", "dynamic", "stealth"}:
            raise ValueError(f"fetch_mode non valido: {self.fetch_mode!r}")

        configured_user_agent = self._config_value("user_agent", "userAgent")
        if configured_user_agent:
            self.user_agent = str(configured_user_agent).strip()

        configured_rate_limit = self._config_value("rate_limit_seconds", "rateLimitSeconds")
        self.rate_limit_seconds = (
            self.rate_limit_seconds
            if configured_rate_limit is None
            else float(configured_rate_limit)
        )

        self._robots_txt: str | None = None
        self._robots_fetched = False
        self._client: httpx.AsyncClient | None = None
        self._proxy_candidates = list(proxy_candidates or [])
        self._proxy_index = 0
        self.proxy_events: list[ProxyRuntimeEvent] = []
        self.discovery_diagnostics = DiscoveryDiagnostics()

    def _config_value(self, snake_case_key: str, camel_case_key: str, default: Any = None) -> Any:
        return self.config.get(snake_case_key, self.config.get(camel_case_key, default))

    def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            proxy = self._active_proxy()
            self._client = httpx.AsyncClient(
                follow_redirects=True, proxy=proxy.httpx_url() if proxy else None
            )
        return self._client

    def _active_proxy(self) -> ProxyRuntimeConfig | None:
        if not self._proxy_candidates:
            return None
        if self._proxy_index >= len(self._proxy_candidates):
            raise ProxyPoolExhaustedError("Nessun proxy sano rimasto per questa operazione.")
        return self._proxy_candidates[self._proxy_index]

    @staticmethod
    def _proxy_failure_category(exc: Exception) -> str | None:
        if isinstance(exc, ProxyRetryableError):
            return exc.category
        if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in {
            403,
            407,
            429,
        }:
            return f"http_{exc.response.status_code}"
        if isinstance(exc, (httpx.TimeoutException, TimeoutError)):
            return "timeout"
        if "timeout" in type(exc).__name__.lower():
            return "timeout"
        if isinstance(exc, httpx.ProxyError):
            return "proxy_connection"
        if isinstance(exc, (httpx.ConnectError, httpx.NetworkError)):
            return "network"
        if isinstance(exc, CurlRequestsError):
            return "proxy_connection"
        if isinstance(exc, PageFetchError) and str(exc).startswith("Fetch Scrapling fallito"):
            return "browser_network"
        return None

    async def _rotate_proxy(self) -> bool:
        if self._proxy_index + 1 >= len(self._proxy_candidates):
            return False
        self._proxy_index += 1
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        return True

    async def _with_proxy_rotation(self, operation: str, callback: Any) -> Any:
        """Run one bounded network operation and rotate without direct fallback."""
        if not self._proxy_candidates:
            return await callback()
        while True:
            proxy = self._active_proxy()
            started = time.monotonic()
            try:
                value = await callback()
            except Exception as exc:
                category = self._proxy_failure_category(exc)
                if category is None:
                    raise
                self.proxy_events.append(
                    ProxyRuntimeEvent(
                        endpoint_id=proxy.endpoint_id,
                        operation=operation,
                        outcome="failed",
                        latency_ms=int((time.monotonic() - started) * 1000),
                        failure_category=category,
                    )
                )
                if not await self._rotate_proxy():
                    raise ProxyPoolExhaustedError(
                        "Tutti i proxy disponibili hanno fallito; accesso diretto bloccato."
                    ) from exc
                continue
            self.proxy_events.append(
                ProxyRuntimeEvent(
                    endpoint_id=proxy.endpoint_id,
                    operation=operation,
                    outcome="success",
                    latency_ms=int((time.monotonic() - started) * 1000),
                )
            )
            return value

    async def _ensure_robots_loaded(self) -> None:
        if not self._robots_fetched:
            from app.services.robots_check import fetch_robots_txt

            async def fetch() -> str | None:
                return await fetch_robots_txt(self.base_url, client=self._ensure_client())

            self._robots_txt = await self._with_proxy_rotation("robots", fetch)
            self._robots_fetched = True

    async def _fetch_page(self, url: str) -> Any:
        """Fetch unico per pagine HTML: robots.txt + rate limit + Scrapling."""
        await self._ensure_robots_loaded()
        from app.services.robots_check import is_allowed

        if not is_allowed(self._robots_txt, url, self.user_agent):
            raise RobotsDisallowedError(url)

        await asyncio.sleep(self.rate_limit_seconds)

        async def fetch() -> Any:
            try:
                if self.fetch_mode == "http":
                    return await self._fetch_page_http(url)
                if self.fetch_mode == "dynamic":
                    return await self._fetch_page_dynamic(url)
                return await self._fetch_page_stealth(url)
            except Exception as exc:
                if isinstance(exc, PageFetchError):
                    raise
                raise PageFetchError(f"Fetch Scrapling fallito per {url}: {exc}") from exc

        return await self._with_proxy_rotation("page", fetch)

    async def _fetch_page_http(self, url: str) -> Any:
        from scrapling.fetchers import AsyncFetcher

        proxy = self._active_proxy()
        response = await AsyncFetcher.get(
            url,
            headers={"User-Agent": self.user_agent},
            stealthy_headers=False,
            timeout=_REQUEST_TIMEOUT_SECONDS,
            proxy=proxy.scrapling_value() if proxy else None,
        )
        self._raise_for_status(response, url)
        return response

    async def _fetch_page_dynamic(self, url: str) -> Any:
        from scrapling.fetchers import DynamicFetcher

        response = await DynamicFetcher.async_fetch(url, **self._browser_fetch_kwargs())
        self._raise_for_status(response, url)
        return response

    async def _fetch_page_stealth(self, url: str) -> Any:
        from scrapling.fetchers import StealthyFetcher

        response = await StealthyFetcher.async_fetch(
            url,
            solve_cloudflare=bool(self._config_value("solve_cloudflare", "solveCloudflare", False)),
            block_webrtc=bool(self._config_value("block_webrtc", "blockWebrtc", False)),
            hide_canvas=bool(self._config_value("hide_canvas", "hideCanvas", False)),
            real_chrome=bool(self._config_value("real_chrome", "realChrome", False)),
            block_ads=bool(self._config_value("block_ads", "blockAds", False)),
            **self._browser_fetch_kwargs(),
        )
        self._raise_for_status(response, url)
        return response

    def _browser_fetch_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "headless": True,
            "network_idle": True,
            "timeout": _BROWSER_NAVIGATION_TIMEOUT_MS,
            "useragent": self.user_agent,
        }
        proxy = self._active_proxy()
        if proxy:
            kwargs["proxy"] = proxy.scrapling_value()
        if wait_selector := self._config_value("wait_selector", "waitSelector"):
            kwargs["wait_selector"] = str(wait_selector)
        if wait_ms := self._config_value("wait_ms", "waitMs"):
            kwargs["wait"] = int(wait_ms)
        return kwargs

    def _raise_for_status(self, response: Any, url: str) -> None:
        status = getattr(response, "status", None)
        if status is not None and not 200 <= int(status) < 300:
            if self._proxy_candidates and int(status) in {403, 407, 429}:
                raise ProxyRetryableError(f"http_{int(status)}")
            raise PageFetchError(f"Risposta HTTP {status} per {url}")

    @staticmethod
    def _extract_all(page: Any, selector: str, attribute: str) -> list[str]:
        if attribute == "text":
            # `selector::text` restituisce un valore per ciascun nodo testuale:
            # con <p>prima<br>seconda</p> il consumer non-multiple prendeva
            # quindi soltanto "prima". Selezioniamo invece gli elementi e ne
            # ricostruiamo il testo completo, conservando i <br> come newline.
            values = [GenericScraper._element_text(element) for element in page.css(selector)]
        else:
            values = page.css(f"{selector}::attr({attribute})").getall()
        return [str(value).strip() for value in values if str(value).strip()]

    @staticmethod
    def _element_text(element: Any) -> str:
        """Estrae il testo visibile preservando solo i break HTML espliciti.

        Scrapling espone l'HTML serializzato dell'elemento; ripercorrerlo evita
        di inserire newline artificiali attorno a tag inline come ``strong`` o
        ``span``. ``None`` è usato internamente come marcatore di ``br``.
        """
        root = lxml_html.fragment_fromstring(str(element.html_content), create_parent="div")
        tokens: list[str | None] = []

        def visit(node: Any) -> None:
            if node.text:
                tokens.append(str(node.text))
            for child in node:
                tag = child.tag.lower() if isinstance(child.tag, str) else ""
                if tag == "br":
                    tokens.append(None)
                elif tag not in {"script", "style"}:
                    visit(child)
                if child.tail:
                    tokens.append(str(child.tail))

        visit(root)
        lines: list[str] = []
        current: list[str] = []
        for token in tokens:
            if token is None:
                lines.append(" ".join("".join(current).split()))
                current = []
            else:
                current.append(token)
        lines.append(" ".join("".join(current).split()))

        # Mantiene le righe vuote tra <br> consecutivi, ma replica il vecchio
        # `.strip()` eliminando whitespace/break soltanto ai bordi.
        while lines and not lines[0]:
            lines.pop(0)
        while lines and not lines[-1]:
            lines.pop()
        return "\n".join(lines)

    async def discover(self) -> list[str]:
        max_pages = int(self._config_value("max_pages", "maxPages") or _DEFAULT_MAX_PAGES)
        max_ads = int(
            self._config_value("max_ads_per_run", "maxAdsPerRun") or _DEFAULT_MAX_ADS_PER_RUN
        )
        ad_link_selector = self._config_value("ad_link_selector", "adLinkSelector")
        next_page_selector = self._config_value("next_page_selector", "nextPageSelector")

        self.discovery_diagnostics = DiscoveryDiagnostics(configured_max_pages=max_pages)
        if next_page_selector and max_pages == 1:
            self.discovery_diagnostics.warnings.append(
                "Il selettore di paginazione e configurato, ma maxPages=1 limita lo scan "
                "alla prima pagina."
            )

        if self.fetch_mode == "http":
            urls = await self._discover_http(
                max_pages=max_pages,
                max_ads=max_ads,
                ad_link_selector=ad_link_selector,
                next_page_selector=next_page_selector,
            )
        else:
            urls = await self._discover_browser(
                max_pages=max_pages,
                max_ads=max_ads,
                ad_link_selector=ad_link_selector,
                next_page_selector=next_page_selector,
            )
        self.discovery_diagnostics.unique_ads_found = len(urls)
        return urls

    @staticmethod
    def _same_origin(first: str, second: str) -> bool:
        def origin(url: str) -> tuple[str, str, int | None]:
            parsed = urlparse(url)
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            return parsed.scheme.lower(), (parsed.hostname or "").lower(), port

        return origin(first) == origin(second)

    def _add_ad_urls(
        self, urls: list[str], seen_urls: set[str], page_url: str, hrefs: list[str], max_ads: int
    ) -> bool:
        for href in hrefs:
            absolute = urljoin(page_url, href)
            if absolute in seen_urls:
                continue
            seen_urls.add(absolute)
            urls.append(absolute)
            if len(urls) >= max_ads:
                self.discovery_diagnostics.stop_reason = "max_ads"
                return True
        return False

    async def _discover_http(
        self,
        *,
        max_pages: int,
        max_ads: int,
        ad_link_selector: str,
        next_page_selector: str | None,
    ) -> list[str]:
        urls: list[str] = []
        seen_urls: set[str] = set()
        for start_url in self._config_value("start_urls", "startUrls"):
            page_url = start_url
            visited_pages: set[str] = set()
            for page_index in range(max_pages):
                if page_url in visited_pages:
                    self.discovery_diagnostics.stop_reason = "repeated_page"
                    self.discovery_diagnostics.errors.append(
                        "La paginazione ha prodotto una pagina gia visitata."
                    )
                    break
                visited_pages.add(page_url)
                page = await self._fetch_page(page_url)
                self.discovery_diagnostics.pages_visited += 1
                if self._add_ad_urls(
                    urls,
                    seen_urls,
                    page_url,
                    self._extract_all(page, ad_link_selector, "href"),
                    max_ads,
                ):
                    return urls
                if not next_page_selector:
                    self.discovery_diagnostics.stop_reason = "no_pagination_configured"
                    break
                if page_index + 1 >= max_pages:
                    self.discovery_diagnostics.stop_reason = "max_pages"
                    break
                controls = list(page.css(next_page_selector))
                if not controls:
                    self.discovery_diagnostics.stop_reason = "end_of_pagination"
                    if page_index == 0:
                        self.discovery_diagnostics.errors.append(
                            "Il selettore di paginazione non ha trovato il controllo Next."
                        )
                    break
                if len(controls) != 1:
                    self.discovery_diagnostics.stop_reason = "ambiguous_next_control"
                    self.discovery_diagnostics.errors.append(
                        "Il selettore di paginazione deve identificare esattamente un "
                        "controllo Next."
                    )
                    break
                next_hrefs = self._extract_all(page, next_page_selector, "href")
                if not next_hrefs:
                    self.discovery_diagnostics.stop_reason = "click_requires_browser"
                    self.discovery_diagnostics.errors.append(
                        "Il controllo Next non ha href: usare il mode dynamic o stealth."
                    )
                    break
                next_url = urljoin(page_url, next_hrefs[0])
                if not self._same_origin(start_url, next_url):
                    self.discovery_diagnostics.stop_reason = "cross_origin_blocked"
                    self.discovery_diagnostics.errors.append(
                        "La paginazione verso un'origine diversa e stata bloccata."
                    )
                    break
                self.discovery_diagnostics.pagination_mode = "href"
                page_url = next_url
        if self.discovery_diagnostics.stop_reason == "not_started":
            self.discovery_diagnostics.stop_reason = "completed"
        return urls

    async def _discover_browser(
        self,
        *,
        max_pages: int,
        max_ads: int,
        ad_link_selector: str,
        next_page_selector: str | None,
    ) -> list[str]:
        from app.services.robots_check import is_allowed

        await self._ensure_robots_loaded()
        urls: list[str] = []
        seen_urls: set[str] = set()
        stop_all = False

        for start_url in self._config_value("start_urls", "startUrls"):
            if stop_all:
                break
            if not is_allowed(self._robots_txt, start_url, self.user_agent):
                raise RobotsDisallowedError(start_url)
            await asyncio.sleep(self.rate_limit_seconds)
            seen_pages: set[str] = set()

            async def paginate_pages(
                browser_page: Any,
                *,
                start_url: str = start_url,
                seen_pages: set[str] = seen_pages,
            ) -> None:
                nonlocal stop_all
                for page_index in range(max_pages):
                    current_url = str(browser_page.url)
                    ad_locator = browser_page.locator(ad_link_selector)
                    hrefs = await ad_locator.evaluate_all(
                        "(elements) => elements.map((element) => "
                        "element.getAttribute('href')).filter(Boolean)"
                    )
                    absolute_hrefs = [urljoin(current_url, str(href)) for href in hrefs]
                    fingerprint = json.dumps(
                        [current_url, absolute_hrefs], ensure_ascii=False, separators=(",", ":")
                    )
                    if fingerprint in seen_pages:
                        self.discovery_diagnostics.stop_reason = "repeated_page"
                        self.discovery_diagnostics.errors.append(
                            "La paginazione ha prodotto contenuti gia visitati."
                        )
                        break
                    seen_pages.add(fingerprint)
                    self.discovery_diagnostics.pages_visited += 1
                    if self._add_ad_urls(
                        urls, seen_urls, current_url, [str(href) for href in hrefs], max_ads
                    ):
                        stop_all = True
                        break
                    if not next_page_selector:
                        self.discovery_diagnostics.stop_reason = "no_pagination_configured"
                        break
                    if page_index + 1 >= max_pages:
                        self.discovery_diagnostics.stop_reason = "max_pages"
                        break

                    controls = browser_page.locator(next_page_selector)
                    control_count = await controls.count()
                    if control_count == 0:
                        self.discovery_diagnostics.stop_reason = "end_of_pagination"
                        if page_index == 0:
                            self.discovery_diagnostics.errors.append(
                                "Il selettore di paginazione non ha trovato il controllo Next."
                            )
                        break
                    if control_count != 1:
                        self.discovery_diagnostics.stop_reason = "ambiguous_next_control"
                        self.discovery_diagnostics.errors.append(
                            "Il selettore di paginazione deve identificare esattamente un "
                            "controllo Next."
                        )
                        break

                    control = controls.first
                    if not await control.is_visible() or not await control.is_enabled():
                        self.discovery_diagnostics.stop_reason = "next_control_unavailable"
                        self.discovery_diagnostics.errors.append(
                            "Il controllo Next non e visibile o abilitato."
                        )
                        break
                    href = await control.get_attribute("href")
                    before_url = current_url
                    before_links = json.dumps(absolute_hrefs, separators=(",", ":"))
                    await asyncio.sleep(self.rate_limit_seconds)
                    if href:
                        next_url = urljoin(current_url, href)
                        if not self._same_origin(start_url, next_url):
                            self.discovery_diagnostics.stop_reason = "cross_origin_blocked"
                            self.discovery_diagnostics.errors.append(
                                "La paginazione verso un'origine diversa e stata bloccata."
                            )
                            break
                        if not is_allowed(self._robots_txt, next_url, self.user_agent):
                            raise RobotsDisallowedError(next_url)
                        self.discovery_diagnostics.pagination_mode = "href"
                        await browser_page.goto(
                            next_url,
                            wait_until="domcontentloaded",
                            timeout=_BROWSER_NAVIGATION_TIMEOUT_MS,
                        )
                    else:
                        self.discovery_diagnostics.pagination_mode = "click"
                        # Il selettore e univoco, visibile e abilitato. Il click DOM
                        # evita che un overlay puramente visuale intercetti il comando.
                        await control.evaluate("(element) => element.click()")

                    try:
                        await browser_page.wait_for_function(
                            "({selector, beforeUrl, beforeLinks}) => {"
                            "const links = Array.from(document.querySelectorAll(selector))"
                            ".map((element) => element.getAttribute('href'))"
                            ".filter(Boolean).map((href) => new URL(href, location.href).href);"
                            "return location.href !== beforeUrl || "
                            "JSON.stringify(links) !== beforeLinks;"
                            "}",
                            arg={
                                "selector": ad_link_selector,
                                "beforeUrl": before_url,
                                "beforeLinks": before_links,
                            },
                            timeout=_PAGINATION_CHANGE_TIMEOUT_MS,
                        )
                    except Exception:  # noqa: BLE001 - convertito in diagnostica sicura
                        self.discovery_diagnostics.stop_reason = "page_did_not_change"
                        self.discovery_diagnostics.errors.append(
                            "Il controllo Next non ha modificato URL o annunci entro il timeout."
                        )
                        break
                    if not self._same_origin(start_url, str(browser_page.url)):
                        self.discovery_diagnostics.stop_reason = "cross_origin_blocked"
                        self.discovery_diagnostics.errors.append(
                            "La paginazione verso un'origine diversa e stata bloccata."
                        )
                        break

            action_errors: list[Exception] = []

            async def paginate(
                browser_page: Any, *, action_errors: list[Exception] = action_errors
            ) -> None:
                try:
                    await paginate_pages(browser_page)
                except RobotsDisallowedError as exc:
                    action_errors.append(exc)
                except Exception:  # noqa: BLE001 - il dettaglio puo contenere URL/dati pagina
                    self.discovery_diagnostics.stop_reason = "browser_pagination_failed"
                    self.discovery_diagnostics.errors.append(
                        "Errore browser durante la paginazione."
                    )

            await self._with_proxy_rotation(
                "discovery",
                lambda start_url=start_url, paginate=paginate: self._fetch_browser_for_discovery(
                    start_url, paginate
                ),
            )
            if action_errors:
                raise action_errors[0]

        if self.discovery_diagnostics.stop_reason == "not_started":
            self.discovery_diagnostics.stop_reason = "completed"
        return urls

    async def _fetch_browser_for_discovery(self, url: str, page_action: Any) -> None:
        kwargs = self._browser_fetch_kwargs()
        kwargs["page_action"] = page_action
        if self.fetch_mode == "dynamic":
            from scrapling.fetchers import DynamicFetcher

            response = await DynamicFetcher.async_fetch(url, **kwargs)
        else:
            from scrapling.fetchers import StealthyFetcher

            response = await StealthyFetcher.async_fetch(
                url,
                solve_cloudflare=bool(
                    self._config_value("solve_cloudflare", "solveCloudflare", False)
                ),
                block_webrtc=bool(self._config_value("block_webrtc", "blockWebrtc", False)),
                hide_canvas=bool(self._config_value("hide_canvas", "hideCanvas", False)),
                real_chrome=bool(self._config_value("real_chrome", "realChrome", False)),
                block_ads=bool(self._config_value("block_ads", "blockAds", False)),
                **kwargs,
            )
        self._raise_for_status(response, url)

    async def scrape_ad(self, url: str) -> dict[str, Any]:
        page = await self._fetch_page(url)

        raw: dict[str, Any] = {"source_url": url}
        for field_name, spec in self._config_value("fields", "fields", {}).items():
            raw[field_name] = self._extract_field(page, spec)
        return raw

    def _extract_field(self, page: Any, spec: dict[str, Any]) -> Any:
        selector = spec["selector"]
        attribute = spec.get("attribute", "text")
        multiple = bool(spec.get("multiple", False))
        values = self._extract_all(page, selector, attribute)
        if multiple:
            return values
        return values[0] if values else None

    def media_extraction_warnings(self, ad: dict[str, Any]) -> list[str]:
        """Segnala campi media configurati che non hanno estratto URL."""
        fields = self._config_value("fields", "fields", {})
        warnings: list[str] = []
        for field_name, label in (("images", "immagine"), ("videos", "video")):
            if field_name in fields and not ad.get(field_name):
                warnings.append(
                    f"Nessun URL {label} trovato dal selettore configurato per '{field_name}'."
                )
        return warnings

    @staticmethod
    def _safe_media_error(exc: Exception) -> str:
        if isinstance(exc, RobotsDisallowedError):
            return "Download media vietato da robots.txt."
        if isinstance(exc, httpx.HTTPStatusError):
            return f"Il server media ha risposto HTTP {exc.response.status_code}."
        if isinstance(exc, httpx.TimeoutException):
            return "Timeout durante il download media."
        if isinstance(exc, httpx.HTTPError):
            return "Errore HTTP durante il download media."
        if isinstance(exc, PageFetchError):
            safe_messages = (
                "URL media non HTTP(S).",
                "Host media non risolvibile.",
                "URL media verso rete privata o riservata bloccato.",
                "Redirect media senza Location.",
                "Media oltre il limite massimo.",
                "Risposta media troncata rispetto a Content-Length.",
                "Troppi redirect durante il download media.",
            )
            message = str(exc)
            return message if message in safe_messages else "Download media non riuscito."
        return "Errore inatteso durante il download media."

    async def download_media(self, ad: dict[str, Any]) -> MediaDownloadResult:
        media_urls = [*(ad.get("images") or []), *(ad.get("videos") or [])]
        result = MediaDownloadResult(attempted_count=len(media_urls))
        for media_url in media_urls:
            try:
                await self._ensure_robots_loaded()
                from app.services.robots_check import is_allowed

                absolute_url = urljoin(self.base_url, media_url)
                if not is_allowed(self._robots_txt, absolute_url, self.user_agent):
                    raise RobotsDisallowedError(absolute_url)

                await asyncio.sleep(self.rate_limit_seconds)
                result.media_bytes.append(
                    await self._with_proxy_rotation(
                        "media",
                        lambda absolute_url=absolute_url: self._download_media_stream(absolute_url),
                    )
                )
            except Exception as exc:  # noqa: BLE001 - download best-effort per singolo media
                # Non loggare l'eccezione o l'URL media: possono contenere token.
                logger.warning(
                    "Download media fallito per la fonte '%s' (%s).",
                    self.slug,
                    type(exc).__name__,
                )
                result.failures.append(MediaDownloadFailure(self._safe_media_error(exc)))
        return result

    @staticmethod
    async def _assert_public_url(url: str) -> None:
        from app.config import settings

        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise PageFetchError("URL media non HTTP(S).")
        loop = asyncio.get_running_loop()
        try:
            addresses = await loop.run_in_executor(
                None, lambda: socket.getaddrinfo(parsed.hostname, parsed.port or 443)
            )
        except socket.gaierror as exc:
            raise PageFetchError("Host media non risolvibile.") from exc
        for address in addresses:
            ip = ipaddress.ip_address(address[4][0])
            if not ip.is_global and settings.ENVIRONMENT != "test":
                raise PageFetchError("URL media verso rete privata o riservata bloccato.")

    async def _download_media_stream(self, url: str) -> bytes:
        """Bounded streaming download with DNS/redirect SSRF checks."""
        from app.config import settings
        from app.services.media_storage import sniff_mime_type

        current = url
        limit = settings.MEDIA_VIDEO_MAX_BYTES
        proxy = self._active_proxy()
        if proxy is not None and proxy.scheme == "socks4":
            return await self._download_media_stream_socks4(current, limit, proxy)
        async with httpx.AsyncClient(
            follow_redirects=False,
            timeout=_REQUEST_TIMEOUT_SECONDS,
            proxy=proxy.httpx_url() if proxy else None,
        ) as client:
            for _ in range(6):
                await self._assert_public_url(current)
                async with client.stream(
                    "GET",
                    current,
                    headers={"User-Agent": self.user_agent, "Accept-Encoding": "identity"},
                ) as response:
                    if response.is_redirect:
                        location = response.headers.get("location")
                        if not location:
                            raise PageFetchError("Redirect media senza Location.")
                        current = urljoin(current, location)
                        continue
                    response.raise_for_status()
                    declared = int(response.headers.get("content-length") or 0)
                    if declared > limit:
                        raise PageFetchError("Media oltre il limite massimo.")
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)
                        if len(body) >= 12:
                            if sniff_mime_type(body).startswith("image/"):
                                limit = settings.MEDIA_IMAGE_MAX_BYTES
                        if len(body) > limit:
                            raise PageFetchError("Media oltre il limite massimo.")
                    if declared and len(body) != declared:
                        raise PageFetchError("Risposta media troncata rispetto a Content-Length.")
                    return bytes(body)
        raise PageFetchError("Troppi redirect durante il download media.")

    async def _download_media_stream_socks4(
        self, url: str, limit: int, proxy: ProxyRuntimeConfig
    ) -> bytes:
        """Bounded SOCKS4 download using libcurl (unsupported by httpx)."""
        from app.services.media_storage import sniff_mime_type

        current = url
        async with CurlAsyncSession() as client:
            for _ in range(6):
                await self._assert_public_url(current)
                state: dict[str, Any] = {
                    "body": bytearray(),
                    "limit": limit,
                    "exceeded": False,
                }

                def receive(chunk: bytes, state: dict[str, Any] = state) -> None:
                    body = state["body"]
                    body.extend(chunk)
                    if len(body) >= 12 and sniff_mime_type(body).startswith("image/"):
                        from app.config import settings

                        state["limit"] = settings.MEDIA_IMAGE_MAX_BYTES
                    if len(body) > state["limit"]:
                        state["exceeded"] = True
                        raise RuntimeError("bounded_media_limit")

                try:
                    response = await client.get(
                        current,
                        headers={"User-Agent": self.user_agent, "Accept-Encoding": "identity"},
                        allow_redirects=False,
                        timeout=_REQUEST_TIMEOUT_SECONDS,
                        proxy=proxy.httpx_url(),
                        content_callback=receive,
                    )
                except Exception as exc:
                    if state["exceeded"]:
                        raise PageFetchError("Media oltre il limite massimo.") from exc
                    raise
                body = state["body"]
                limit = state["limit"]
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location")
                    if not location:
                        raise PageFetchError("Redirect media senza Location.")
                    current = urljoin(current, location)
                    continue
                if response.status_code in {403, 407, 429}:
                    raise ProxyRetryableError(f"http_{response.status_code}")
                if response.status_code >= 400:
                    synthetic = httpx.Response(
                        response.status_code,
                        request=httpx.Request("GET", current),
                    )
                    synthetic.raise_for_status()
                declared = int(response.headers.get("content-length") or 0)
                if declared > limit:
                    raise PageFetchError("Media oltre il limite massimo.")
                if declared and len(body) != declared:
                    raise PageFetchError("Risposta media troncata rispetto a Content-Length.")
                return bytes(body)
        raise PageFetchError("Troppi redirect durante il download media.")

    def normalize(self, data: dict[str, Any]) -> dict[str, Any]:
        configured_fields = self._config_value("fields", "fields", {})
        custom_fields = {
            field_name: data.get(field_name)
            for field_name in configured_fields
            if field_name not in _STANDARD_FIELDS
        }
        return {
            "title": (data.get("title") or "").strip() or None,
            "description": (data.get("description") or "").strip() or None,
            "phone_raw": data.get("phone"),
            "source_url": data.get("source_url"),
            "images": data.get("images") or [],
            "videos": data.get("videos") or [],
            # Missing selectors remain explicit null values so consumers can
            # distinguish "configured but absent" from "not configured".
            "custom_fields": custom_fields,
        }

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
