from __future__ import annotations

from app.models.sources import Source
from app.services.scrape_ingest import collect_ads


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
