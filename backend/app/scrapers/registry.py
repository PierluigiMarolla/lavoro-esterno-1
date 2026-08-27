"""Registro slug -> classe scraper.

Il worker Celery (`app/workers/tasks_scraper.py`) risolve la classe da
istanziare a partire dallo `slug` salvato su `sources.slug`, senza dover
conoscere staticamente quale fonte sta processando.
"""

from __future__ import annotations

from app.scrapers.bakeca_incontri import BakecaIncontriScraper
from app.scrapers.base import Scraper
from app.scrapers.escort_advisor import EscortAdvisorScraper
from app.scrapers.escortacom import EscortacomScraper
from app.scrapers.escortforumit import EscortforumitScraper
from app.scrapers.megaescort import MegaescortScraper
from app.scrapers.moscarossa import MoscarossaScraper
from app.scrapers.punterforum import PunterforumScraper
from app.scrapers.rosa_rossa import RosaRossaScraper
from app.scrapers.torino_erotica import TorinoEroticaScraper

SCRAPER_REGISTRY: dict[str, type[Scraper]] = {
    "escort_advisor": EscortAdvisorScraper,
    "bakeca_incontri": BakecaIncontriScraper,
    "moscarossa": MoscarossaScraper,
    "megaescort": MegaescortScraper,
    "escortforumit": EscortforumitScraper,
    "escortacom": EscortacomScraper,
    "rosa_rossa": RosaRossaScraper,
    "torino_erotica": TorinoEroticaScraper,
    "punterforum": PunterforumScraper,
}


def get_scraper_class(slug: str) -> type[Scraper]:
    """Restituisce la classe scraper registrata per lo slug dato.

    Solleva KeyError (con messaggio esplicito) se lo slug non è registrato,
    tipicamente segno di una `Source` configurata nel DB senza un connettore
    corrispondente nel codice.
    """
    try:
        return SCRAPER_REGISTRY[slug]
    except KeyError as exc:
        raise KeyError(f"Nessuno scraper registrato per lo slug '{slug}'.") from exc
