"""Schemi Pydantic per le fonti (Source) e l'avvio di uno scan."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.common import CamelModel


class SourceRead(CamelModel):
    """Riga della tabella fonti per `GET /sources` (`frontend/src/api/
    sources.ts:fetchSources`, tipo `Source` in `frontend/src/types/
    index.ts`), che chiama `apiRequest<Source[]>` direttamente: il backend
    deve rispondere già nella forma attesa dal frontend, non nella forma
    "grezza" del modello `Source` (che non ha `code`/`country`/`lastRunAt`/
    `itemsLast24h`/`errorRate`).

    Non è costruita con `model_validate(source_orm_instance)` da sola: questi
    campi derivati vengono calcolati nel router (`app/api/v1/sources.py`)
    con un'aggregazione su `scrape_runs`, perché non esistono come colonne
    dirette su `Source`.
    """

    id: uuid.UUID
    # "code" per il frontend corrisponde allo slug tecnico della fonte
    # (es. "bakeca_incontri"), usato anche per il registry degli scraper.
    code: str
    name: str
    # Nessuna colonna "country" sul modello Source: placeholder fisso finché
    # non viene introdotto un vero campo geografico per fonte (vedi
    # PROGETTO.md). Non blocca la UI, che lo mostra solo come etichetta.
    country: str = "N/D"
    status: str
    last_run_at: datetime | None
    items_last_24h: int
    error_rate: float


class ScanTriggerResponse(BaseModel):
    """Esito dell'accodamento di un task di scraping (non del suo completamento:
    lo scraping è asincrono, vedi app/workers/tasks_scraper.py)."""

    task_id: str
    source_id: uuid.UUID
    queued: bool = True


class SourcesSummaryRead(CamelModel):
    """Conteggio delle fonti per stato, per la card riepilogativa della
    pagina Sources (`frontend/src/api/sources.ts:SourcesSummary`).

    Nota: qui i nomi di stato restano quelli nativi del dominio
    (`active`/`degraded`/`offline`, da `Source.status`), a differenza di
    `GET /dashboard/source-health` che li rimappa su un vocabolario diverso
    ("healthy"/"rateLimited"/"error") per la card di dashboard — vedi
    `app/services/source_health.py` per il dettaglio di entrambe le
    mappature.
    """

    total: int
    active: int
    degraded: int
    offline: int
