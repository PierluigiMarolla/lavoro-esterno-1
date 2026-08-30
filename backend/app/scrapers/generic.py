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
from typing import Any
from urllib.parse import urljoin

import httpx

from app.scrapers.base import Scraper

_DEFAULT_MAX_PAGES = 3
_DEFAULT_MAX_ADS_PER_RUN = 50
_REQUEST_TIMEOUT_SECONDS = 15.0
_BROWSER_NAVIGATION_TIMEOUT_MS = 20_000


class RobotsDisallowedError(Exception):
    """Sollevata quando `robots.txt` vieta l'accesso a un URL."""

    def __init__(self, url: str):
        super().__init__(f"robots.txt vieta l'accesso a: {url}")
        self.url = url


class PageFetchError(Exception):
    """Sollevata quando Scrapling non riesce a recuperare una pagina."""


class GenericScraper(Scraper):
    """Connettore generico guidato da configurazione."""

    def __init__(self, slug: str, base_url: str, config: dict[str, Any]):
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

    def _config_value(self, snake_case_key: str, camel_case_key: str, default: Any = None) -> Any:
        return self.config.get(snake_case_key, self.config.get(camel_case_key, default))

    def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(follow_redirects=True)
        return self._client

    async def _ensure_robots_loaded(self) -> None:
        if not self._robots_fetched:
            from app.services.robots_check import fetch_robots_txt

            self._robots_txt = await fetch_robots_txt(self.base_url, client=self._ensure_client())
            self._robots_fetched = True

    async def _fetch_page(self, url: str) -> Any:
        """Fetch unico per pagine HTML: robots.txt + rate limit + Scrapling."""
        await self._ensure_robots_loaded()
        from app.services.robots_check import is_allowed

        if not is_allowed(self._robots_txt, url, self.user_agent):
            raise RobotsDisallowedError(url)

        await asyncio.sleep(self.rate_limit_seconds)

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

    async def _fetch_page_http(self, url: str) -> Any:
        from scrapling.fetchers import AsyncFetcher

        response = await AsyncFetcher.get(
            url,
            headers={"User-Agent": self.user_agent},
            stealthy_headers=False,
            timeout=_REQUEST_TIMEOUT_SECONDS,
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
        if proxy := self._config_value("proxy", "proxy"):
            kwargs["proxy"] = str(proxy)
        if wait_selector := self._config_value("wait_selector", "waitSelector"):
            kwargs["wait_selector"] = str(wait_selector)
        if wait_ms := self._config_value("wait_ms", "waitMs"):
            kwargs["wait"] = int(wait_ms)
        return kwargs

    @staticmethod
    def _raise_for_status(response: Any, url: str) -> None:
        status = getattr(response, "status", None)
        if status is not None and not 200 <= int(status) < 300:
            raise PageFetchError(f"Risposta HTTP {status} per {url}")

    @staticmethod
    def _extract_all(page: Any, selector: str, attribute: str) -> list[str]:
        scrapling_selector = (
            f"{selector}::text" if attribute == "text" else f"{selector}::attr({attribute})"
        )
        values = page.css(scrapling_selector).getall()
        return [str(value).strip() for value in values if str(value).strip()]

    async def discover(self) -> list[str]:
        max_pages = int(self._config_value("max_pages", "maxPages") or _DEFAULT_MAX_PAGES)
        max_ads = int(
            self._config_value("max_ads_per_run", "maxAdsPerRun") or _DEFAULT_MAX_ADS_PER_RUN
        )
        ad_link_selector = self._config_value("ad_link_selector", "adLinkSelector")
        next_page_selector = self._config_value("next_page_selector", "nextPageSelector")

        urls: list[str] = []
        for start_url in self._config_value("start_urls", "startUrls"):
            page_url = start_url
            for _ in range(max_pages):
                page = await self._fetch_page(page_url)

                for href in self._extract_all(page, ad_link_selector, "href"):
                    urls.append(urljoin(page_url, href))
                    if len(urls) >= max_ads:
                        return urls[:max_ads]

                if not next_page_selector:
                    break
                next_hrefs = self._extract_all(page, next_page_selector, "href")
                if not next_hrefs:
                    break
                page_url = urljoin(page_url, next_hrefs[0])
        return urls[:max_ads]

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

    async def download_media(self, ad: dict[str, Any]) -> list[bytes]:
        image_urls = ad.get("images") or []
        results: list[bytes] = []
        for image_url in image_urls:
            try:
                await self._ensure_robots_loaded()
                from app.services.robots_check import is_allowed

                absolute_url = urljoin(self.base_url, image_url)
                if not is_allowed(self._robots_txt, absolute_url, self.user_agent):
                    raise RobotsDisallowedError(absolute_url)

                await asyncio.sleep(self.rate_limit_seconds)
                response = await self._fetch_page_http(absolute_url)
                results.append(response.body)
            except (RobotsDisallowedError, PageFetchError, Exception):  # noqa: BLE001
                continue
        return results

    def normalize(self, data: dict[str, Any]) -> dict[str, Any]:
        return {
            "title": (data.get("title") or "").strip() or None,
            "description": (data.get("description") or "").strip() or None,
            "phone_raw": data.get("phone"),
            "source_url": data.get("source_url"),
            "images": data.get("images") or [],
        }

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
