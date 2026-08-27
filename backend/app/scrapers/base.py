"""Interfaccia comune per i connettori di scraping.

Ogni fonte (sito di annunci) implementa questa classe. Lo `slug` DEVE
corrispondere alla colonna `sources.slug` nel database e alla chiave usata in
`registry.py`, così che il worker Celery possa risolvere "source_id -> classe
scraper" passando per lo slug.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Scraper(ABC):
    """Contratto che ogni connettore di scraping deve rispettare.

    Nessun metodo qui esegue realmente richieste HTTP: sono tutti stub che
    definiscono la forma dell'interfaccia, da implementare nel rispetto dei
    Termini di Servizio della fonte e dei rate limit dichiarati.
    """

    slug: str
    base_url: str
    rate_limit_seconds: float = 2.0
    """Intervallo minimo, in secondi, tra due richieste consecutive verso la
    stessa fonte. Valore di default prudenziale; ogni connettore concreto può
    sovrascriverlo in base alle policy della fonte specifica."""

    @abstractmethod
    async def discover(self) -> list[str]:
        """Individua gli URL dei singoli annunci da visitare (es. tramite le
        pagine di elenco/categoria della fonte). Restituisce una lista di URL
        assoluti."""
        raise NotImplementedError

    @abstractmethod
    async def scrape_ad(self, url: str) -> dict[str, Any]:
        """Scarica ed estrae i dati grezzi di un singolo annuncio dato il suo URL."""
        raise NotImplementedError

    @abstractmethod
    async def download_media(self, ad: dict[str, Any]) -> list[bytes]:
        """Scarica i file media (immagini/video) referenziati da un annuncio già estratto."""
        raise NotImplementedError

    @abstractmethod
    def normalize(self, data: dict[str, Any]) -> dict[str, Any]:
        """Normalizza i dati grezzi estratti nel formato comune atteso dal
        resto della pipeline (campi coerenti con `app.models.advertisement.Advertisement`:
        title, description, source_url, phone, ecc.)."""
        raise NotImplementedError
