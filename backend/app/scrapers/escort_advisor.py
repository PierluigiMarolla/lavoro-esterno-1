"""Connettore scraper stub per la fonte "EscortAdvisor".

Nessuna richiesta HTTP reale viene effettuata: tutti i metodi sollevano
`NotImplementedError` con un messaggio esplicito. L'implementazione reale
andra' scritta rispettando i Termini di Servizio della fonte e il rate limit
dichiarato in `rate_limit_seconds`.
"""

from __future__ import annotations

from typing import Any

from app.scrapers.base import Scraper


class EscortAdvisorScraper(Scraper):
    slug = "escort_advisor"
    base_url = "https://www.escortadvisor.com"
    rate_limit_seconds = 2.0

    async def discover(self) -> list[str]:
        raise NotImplementedError(
            "TODO: implementare scraping reale per EscortAdvisor, rispettando ToS e rate limit"
        )

    async def scrape_ad(self, url: str) -> dict[str, Any]:
        raise NotImplementedError(
            "TODO: implementare scraping reale per EscortAdvisor, rispettando ToS e rate limit"
        )

    async def download_media(self, ad: dict[str, Any]) -> list[bytes]:
        raise NotImplementedError(
            "TODO: implementare scraping reale per EscortAdvisor, rispettando ToS e rate limit"
        )

    def normalize(self, data: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError(
            "TODO: implementare scraping reale per EscortAdvisor, rispettando ToS e rate limit"
        )
