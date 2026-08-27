"""Selezione dell'annuncio "canonico" per un Record.

Regola deterministica (in quest'ordine di applicazione):

1. Se esistono annunci con status "active" provenienti dalla fonte con slug
   "bakeca_incontri" per il record, il canonico è il più RECENTE tra questi
   (per `scraped_at`). bakeca_incontri è trattata come fonte "di riferimento"
   privilegiata a prescindere dalla sua priorità configurata, perché nel
   dominio applicativo è la fonte più affidabile/aggiornata storicamente.
2. Altrimenti, il canonico è il più recente annuncio "active" tra TUTTE le
   fonti.
3. Tie-break (a parità di `scraped_at`, o quando serve un criterio
   aggiuntivo per scegliere in modo stabile):
   a. maggior numero di campi "informativi" non nulli/non vuoti
      (title, description, source_url + eventuali extra forniti);
   b. priorità della fonte (high > medium > low);
   c. come ultima risorsa, l'id dell'annuncio (per garantire determinismo
      assoluto anche a parità di tutto il resto).

Il modulo è volutamente privo di dipendenze da SQLAlchemy/DB: la funzione di
risoluzione opera su semplici dataclass, così è testabile in isolamento e
riusabile sia da un task Celery post-scraping sia da un endpoint di override
manuale.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum


class SourcePriority(IntEnum):
    """Priorità numerica crescente: usata per confrontare direttamente le
    priorità delle fonti nel tie-break (high vince su medium vince su low)."""

    low = 0
    medium = 1
    high = 2


BAKECA_INCONTRI_SLUG = "bakeca_incontri"


@dataclass(frozen=True)
class CandidateSource:
    """Rappresentazione minima di una fonte, sufficiente per la regola."""

    id: uuid.UUID
    slug: str
    priority: SourcePriority


@dataclass(frozen=True)
class CandidateAdvertisement:
    """Rappresentazione minima di un annuncio, sufficiente per la regola.

    `status` atteso: "active" | "removed" | "invalid" (solo "active" è
    eleggibile a canonico).
    """

    id: uuid.UUID
    source: CandidateSource
    scraped_at: datetime
    status: str
    title: str | None = None
    description: str | None = None
    source_url: str | None = None
    extra_non_empty_fields: int = 0
    """Conteggio aggiuntivo di campi "informativi" non vuoti oltre a
    title/description/source_url (es. prezzo, città, età dichiarata...),
    fornito dal chiamante per non dover conoscere qui l'intero schema
    Advertisement."""


@dataclass(frozen=True)
class CanonicalResolution:
    """Esito della risoluzione: l'annuncio scelto e la motivazione testuale
    pronta per essere salvata in `canonical_history.reason`."""

    chosen: CandidateAdvertisement
    reason: str


def _non_empty_field_count(ad: CandidateAdvertisement) -> int:
    core_fields = (ad.title, ad.description, ad.source_url)
    return sum(1 for f in core_fields if f and f.strip()) + ad.extra_non_empty_fields


def _tie_break_key(ad: CandidateAdvertisement) -> tuple:
    """Chiave di ordinamento per il tie-break, decrescente su tutti i criteri
    (usata con `max()`): più campi popolati, poi priorità fonte più alta,
    infine id come discriminante finale e deterministico."""
    return (
        ad.scraped_at,
        _non_empty_field_count(ad),
        int(ad.source.priority),
        str(ad.id),
    )


def resolve_canonical(
    advertisements: list[CandidateAdvertisement],
) -> CanonicalResolution:
    """Applica la regola di selezione del canonico a una lista di candidati
    (tutti relativi allo stesso Record) e restituisce l'esito.

    Solleva ValueError se non c'è nessun annuncio "active" tra i candidati:
    la chiamata a questa funzione presuppone che almeno un annuncio valido
    esista (il chiamante è responsabile di gestire il caso "nessun canonico
    possibile", es. record appena creato senza ancora annunci attivi).
    """
    active_ads = [ad for ad in advertisements if ad.status == "active"]
    if not active_ads:
        raise ValueError(
            "Nessun annuncio con status 'active' tra i candidati: impossibile scegliere "
            "un canonico."
        )

    bakeca_ads = [ad for ad in active_ads if ad.source.slug == BAKECA_INCONTRI_SLUG]

    if bakeca_ads:
        chosen = max(bakeca_ads, key=_tie_break_key)
        reason = (
            f"Selezionato come canonico l'annuncio più recente dalla fonte di riferimento "
            f"'{BAKECA_INCONTRI_SLUG}' (scraped_at={chosen.scraped_at.isoformat()})."
        )
        return CanonicalResolution(chosen=chosen, reason=reason)

    chosen = max(active_ads, key=_tie_break_key)
    reason = (
        f"Nessun annuncio attivo su '{BAKECA_INCONTRI_SLUG}'; selezionato il più recente "
        f"tra tutte le fonti disponibili (fonte='{chosen.source.slug}', "
        f"scraped_at={chosen.scraped_at.isoformat()})."
    )
    return CanonicalResolution(chosen=chosen, reason=reason)


def build_history_entry(
    record_id: uuid.UUID,
    previous_advertisement_id: uuid.UUID | None,
    resolution: CanonicalResolution,
    overridden_by_user_id: uuid.UUID | None = None,
) -> dict:
    """Costruisce il dict pronto per popolare una riga `canonical_history`,
    a partire dall'esito di `resolve_canonical` (o da un override manuale,
    nel qual caso `overridden_by_user_id` va valorizzato dal chiamante e la
    `reason` tipicamente sovrascritta con la motivazione fornita dall'operatore).
    """
    return {
        "record_id": record_id,
        "previous_advertisement_id": previous_advertisement_id,
        "new_advertisement_id": resolution.chosen.id,
        "reason": resolution.reason,
        "overridden_by_user_id": overridden_by_user_id,
    }
