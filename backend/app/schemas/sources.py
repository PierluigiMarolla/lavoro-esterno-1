"""Schemi Pydantic per le fonti (Source), la loro configurazione di
scraping (motore generico, vedi `app/scrapers/generic.py`) e l'avvio di
uno scan."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.common import CamelModel


def _validate_http_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError(f"URL non valido (richiesto http/https assoluto): {value!r}")
    return value


class ScrapeFieldConfig(CamelModel):
    """Un singolo campo da estrarre da una pagina annuncio: selettore CSS +
    dove prendere il valore (testo del nodo, o un suo attributo HTML come
    `src`/`href`)."""

    selector: str = Field(min_length=1)
    attribute: str = "text"
    multiple: bool = False


class WatermarkRegion(CamelModel):
    """Rectangle expressed as normalized 0..1 coordinates."""

    x: float = Field(ge=0, lt=1)
    y: float = Field(ge=0, lt=1)
    width: float = Field(gt=0, le=1)
    height: float = Field(gt=0, le=1)

    @model_validator(mode="after")
    def contained_in_frame(self):
        if self.x + self.width > 1 or self.y + self.height > 1:
            raise ValueError("La regione watermark deve essere contenuta nel frame.")
        return self


class WatermarkRemovalConfig(CamelModel):
    enabled: bool = False
    authorization_reference: str | None = Field(default=None, max_length=2000)
    regions: list[WatermarkRegion] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def require_authorization(self):
        if self.enabled and (
            not self.authorization_reference or not self.authorization_reference.strip()
        ):
            raise ValueError("authorizationReference e obbligatorio per rimuovere watermark.")
        if self.enabled and not self.regions:
            raise ValueError("Almeno una regione e obbligatoria per rimuovere watermark.")
        return self


class ScrapeConfigInput(CamelModel):
    """Configurazione del motore di scraping generico per una fonte
    (`Source.scrape_config`). Validata qui prima di essere salvata: il
    motore (`app/scrapers/generic.py:GenericScraper`) si fida di leggerla
    già corretta.

    Eredita da `CamelModel` (non solo per le risposte, anche qui come
    corpo di richiesta): il frontend invia le chiavi in camelCase
    (`startUrls`, `adLinkSelector`, ...) coerenti con `frontend/src/types/
    index.ts:ScrapeConfig`, e `populate_by_name=True` accetta comunque
    anche i nomi snake_case se costruita lato Python (es. nei test).
    """

    start_urls: list[str] = Field(min_length=1)
    ad_link_selector: str = Field(min_length=1)
    next_page_selector: str | None = None
    max_pages: int = Field(default=3, ge=1, le=20)
    max_ads_per_run: int = Field(default=50, ge=1, le=500)
    # Minimo 1s: rate limiting non disattivabile da configurazione (vedi
    # PROGETTO.md § 4) — un operatore può rallentare ulteriormente una
    # fonte sensibile, non può azzerare la pausa tra le richieste.
    rate_limit_seconds: float = Field(default=2.0, ge=1.0, le=60.0)
    fetch_mode: Literal["http", "dynamic", "stealth"] = "http"
    # Retrocompatibilita: le configurazioni precedenti usavano solo
    # `renderJs`; il motore lo traduce in `fetchMode="dynamic"` quando
    # `fetchMode` non e esplicitamente presente.
    render_js: bool = False
    user_agent: str | None = Field(default=None, min_length=1, max_length=300)
    solve_cloudflare: bool = False
    block_webrtc: bool = False
    hide_canvas: bool = False
    real_chrome: bool = False
    block_ads: bool = False
    wait_selector: str | None = Field(default=None, min_length=1, max_length=500)
    wait_ms: int | None = Field(default=None, ge=0, le=120_000)
    fields: dict[str, ScrapeFieldConfig] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _derive_fetch_mode_from_render_js(cls, data):
        if isinstance(data, dict):
            if data.get("proxy") is not None:
                raise ValueError(
                    "Il proxy testuale non e piu supportato: assegnare un proxyPoolId alla fonte."
                )
            has_fetch_mode = "fetch_mode" in data or "fetchMode" in data
            render_js = data.get("render_js", data.get("renderJs"))
            if not has_fetch_mode and render_js is True:
                return {**data, "fetch_mode": "dynamic"}
        return data

    @field_validator("start_urls")
    @classmethod
    def _validate_start_urls(cls, value: list[str]) -> list[str]:
        return [_validate_http_url(url) for url in value]

    @field_validator("user_agent")
    @classmethod
    def _validate_user_agent(cls, value: str | None) -> str | None:
        return cls._strip_optional_string(value, "user_agent")

    @field_validator("wait_selector")
    @classmethod
    def _validate_wait_selector(cls, value: str | None) -> str | None:
        return cls._strip_optional_string(value, "wait_selector")

    @staticmethod
    def _strip_optional_string(value: str | None, field_name: str) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError(f"{field_name} non puo essere vuoto.")
        return stripped

    @field_validator("fields")
    @classmethod
    def _require_phone_field(
        cls, value: dict[str, ScrapeFieldConfig]
    ) -> dict[str, ScrapeFieldConfig]:
        if "image" in value:
            raise ValueError("Il campo media deve chiamarsi 'images' (plurale), non 'image'.")
        if "phone" not in value:
            raise ValueError(
                "La configurazione deve includere un selettore per il campo 'phone': "
                "senza un numero di telefono estratto, un annuncio non può essere "
                "collegato a nessun Record (vedi app/services/scrape_ingest.py)."
            )
        for field_name in ("images", "videos"):
            media_field = value.get(field_name)
            if media_field is None:
                continue
            if not media_field.multiple:
                raise ValueError(f"Il campo media '{field_name}' deve avere multiple=true.")
            if media_field.attribute not in {"src", "href"}:
                raise ValueError(
                    f"Il campo media '{field_name}' deve usare l'attributo 'src' o 'href'."
                )
        return value


class SourceCreate(CamelModel):
    """Body di `POST /sources` (solo Admin). CamelModel per coerenza con
    `scrapeConfig` annidato (vedi `ScrapeConfigInput`) — l'intero corpo
    della richiesta usa camelCase, non solo i campi interni."""

    name: str = Field(min_length=1, max_length=200)
    slug: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9_]+$")
    base_url: str
    priority: str = "medium"
    scrape_config: ScrapeConfigInput | None = None
    proxy_pool_id: uuid.UUID | None = None
    watermark_removal: WatermarkRemovalConfig = Field(default_factory=WatermarkRemovalConfig)

    @field_validator("base_url")
    @classmethod
    def _validate_base_url(cls, value: str) -> str:
        return _validate_http_url(value)


class SourceUpdate(CamelModel):
    """Body di `PATCH /sources/{id}`. Tutti i campi opzionali: solo quelli
    forniti vengono aggiornati. Non include `slug` (chiave di collegamento
    stabile, non modificabile dopo la creazione)."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    base_url: str | None = None
    priority: str | None = None
    scrape_config: ScrapeConfigInput | None = None
    proxy_pool_id: uuid.UUID | None = None
    watermark_removal: WatermarkRemovalConfig | None = None

    @field_validator("base_url")
    @classmethod
    def _validate_base_url(cls, value: str | None) -> str | None:
        return _validate_http_url(value) if value is not None else None


class SourceScheduleUpdate(CamelModel):
    enabled: bool
    interval_value: int | None = Field(default=None, ge=1)
    interval_unit: Literal["minutes", "hours", "days"] | None = None
    revision: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_interval(self):
        if self.enabled and (self.interval_value is None or self.interval_unit is None):
            raise ValueError("Intervallo e unita sono obbligatori quando lo schedule e attivo.")
        if self.interval_value is not None and self.interval_unit is not None:
            factors = {"minutes": 1, "hours": 60, "days": 1440}
            minutes = self.interval_value * factors[self.interval_unit]
            if not 15 <= minutes <= 43_200:
                raise ValueError("L'intervallo deve essere compreso tra 15 minuti e 30 giorni.")
        return self

    def normalized_minutes(self) -> int | None:
        if self.interval_value is None or self.interval_unit is None:
            return None
        return self.interval_value * {"minutes": 1, "hours": 60, "days": 1440}[
            self.interval_unit
        ]


class SourceDuplicate(CamelModel):
    """Nuova identita per una copia; la configurazione arriva dalla fonte originale."""

    name: str = Field(min_length=1, max_length=200)
    slug: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9_]+$")


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
    # Separato dallo stato di salute: una fonte healthy/degraded puo essere
    # volontariamente in pausa e quindi non abilitata allo scraping.
    enabled: bool
    # Bug corretto: prima non esposta dall'API affatto, il frontend
    # fabbricava un'etichetta "High/Medium/Low" derivata da `errorRate` per
    # la colonna "Priority" della tabella (vedi
    # frontend/src/routes/SourcesPage.tsx) — mostrava quindi il tasso di
    # errore travestito da priorità, non la vera priorità configurata.
    priority: str
    last_run_at: datetime | None
    # Alias esplicito: l'alias_generator `to_camel` di CamelModel converte
    # "items_last_24h" in "itemsLast24H" (H maiuscola) per via del confine
    # cifra/lettera — bug osservato dal vivo confrontando la risposta reale
    # con `frontend/src/types/index.ts:Source.itemsLast24h` (h minuscola).
    # Override esplicito invece di rinominare il campo Python.
    items_last_24h: int = Field(alias="itemsLast24h")
    error_rate: float
    # Numero di run consecutivi falliti (i più recenti, fino al primo
    # "completed"): alimenta il badge "Connector broken?" in UI quando >= 3
    # (vedi app/api/v1/sources.py). 0 se l'ultimo run è andato bene o se
    # non esiste ancora alcun run.
    consecutive_failures: int
    # Indica se la fonte è già configurata per il motore di scraping
    # generico (Source.scrape_config valorizzato) — la UI la usa per
    # decidere se mostrare "Configure" o "Edit configuration".
    has_scrape_config: bool
    proxy_pool_id: uuid.UUID | None = None
    proxy_pool_status: str = "direct"
    automatic_scraping_enabled: bool = False
    scrape_interval_minutes: int | None = None
    next_scrape_at: datetime | None = None
    last_scheduled_at: datetime | None = None
    last_completed_scrape_at: datetime | None = None
    last_schedule_skip_reason: str | None = None
    schedule_revision: int = 1
    automatic_scraping_state: Literal["waiting", "pending", "running", "paused", "disabled"] = (
        "paused"
    )


class SourceDetailRead(SourceRead):
    """`SourceRead` più `scrapeConfig` completo — usata solo da `GET
    /sources/{id}` per precompilare il form "Edit configuration" in UI
    (`SourceRead`/`GET /sources` restituisce solo `hasScrapeConfig`,
    un booleano, non la configurazione intera: non serve a chi mostra solo
    la tabella)."""

    scrape_config: ScrapeConfigInput | None = None
    watermark_removal: WatermarkRemovalConfig = Field(default_factory=WatermarkRemovalConfig)


class ScanTriggerResponse(BaseModel):
    """Esito dell'accodamento di un task di scraping (non del suo completamento:
    lo scraping è asincrono, vedi app/workers/tasks_scraper.py)."""

    task_id: str
    source_id: uuid.UUID
    run_id: uuid.UUID
    queued: bool = True


class ScrapeErrorRead(CamelModel):
    """Singolo errore verificatosi durante un run (`GET /sources/{id}/runs`,
    drill-down "visualizzazione errori scraping" nella pagina Sources)."""

    id: uuid.UUID
    url: str
    error_message: str
    created_at: datetime


class ScrapeRunRead(CamelModel):
    """Un'esecuzione di scraping per una fonte, con i suoi errori annidati
    (tipicamente pochi per run: nessuna paginazione separata necessaria)."""

    id: uuid.UUID
    started_at: datetime | None
    finished_at: datetime | None
    status: str
    items_found: int
    items_new: int
    items_updated: int = 0
    items_unchanged: int = 0
    errors_count: int
    pages_visited: int = 0
    pagination_mode: str = "none"
    pagination_stop_reason: str | None = None
    proxy_attempts_count: int = 0
    proxy_rotations_count: int = 0
    proxy_stop_reason: str | None = None
    queued_at: datetime
    trigger_type: Literal["manual", "scheduled"] = "manual"
    scheduled_for: datetime | None = None
    errors: list[ScrapeErrorRead] = Field(default_factory=list)


class RobotsCheckRead(CamelModel):
    """Esito di `POST /sources/{id}/check-robots`."""

    allowed: bool
    robots_txt_found: bool
    checked_url: str


class TestConfigInput(CamelModel):
    """Bozza opzionale da provare senza aggiornare la fonte."""

    scrape_config: ScrapeConfigInput
    proxy_pool_id: uuid.UUID | None = None


class TestConfigResult(CamelModel):
    """Esito di `POST /sources/{id}/test-config`: prova UN solo annuncio
    (non salvato su DB) per verificare che i selettori configurati
    estraggano davvero qualcosa, prima di lanciare uno scan reale."""

    ad_urls_found: int
    sample_url: str | None = None
    extracted_fields: dict | None = None
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None
    pages_visited: int = 0
    configured_max_pages: int = 1
    pagination_mode: str = "none"
    pagination_stop_reason: str = "not_started"
    unique_ads_found: int = 0


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
