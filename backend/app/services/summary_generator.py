"""Generazione del riepilogo (summary) AI di un Record.

Come per `media_classifier.py`, definiamo un'interfaccia astratta in modo che
l'implementazione reale (chiamata a un LLM) sia intercambiabile con
l'implementazione placeholder di questo scaffold, senza impattare i
chiamanti (endpoint records, task Celery `tasks_ai.py`).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SummaryPayload:
    """Struttura del riepilogo, persistita in `summary_versions.summary_json`.

    Rispecchia lo schema Pydantic in `app/schemas/records.py`
    (`SummaryPayloadSchema`), qui espresso come dataclass per non introdurre
    una dipendenza da Pydantic nel layer di servizio.
    """

    summary: str
    advertisement_information: list[dict[str, Any]] = field(default_factory=list)
    forum_information: list[dict[str, Any]] = field(default_factory=list)
    unverified_claims: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "advertisement_information": self.advertisement_information,
            "forum_information": self.forum_information,
            "unverified_claims": self.unverified_claims,
            "sources": self.sources,
        }


class SummaryGenerator(ABC):
    """Interfaccia per un generatore di riepiloghi a partire dai dati raccolti
    su un Record (i suoi annunci e, opzionalmente, snippet da forum)."""

    @abstractmethod
    def generate(
        self,
        record: Any,
        advertisements: list[Any],
        forum_snippets: list[str],
    ) -> SummaryPayload:
        """Genera un `SummaryPayload` a partire dai dati grezzi del record.

        `record`/`advertisements` sono lasciati tipizzati `Any` deliberatamente:
        l'implementazione concreta decide se accettare i modelli ORM, DTO
        Pydantic o semplici dict, per non accoppiare l'interfaccia al layer DB.
        """
        raise NotImplementedError


class TemplateSummaryGenerator(SummaryGenerator):
    """Implementazione PLACEHOLDER, senza alcuna chiamata a un modello LLM.

    Produce un riepilogo "meccanico" concatenando i dati disponibili in un
    template testuale fisso, così che l'intera pipeline (record -> annunci ->
    riepilogo -> versione salvata) sia funzionante ed esercitabile end-to-end
    fin da subito. Il punto di sostituzione futuro è: implementare una nuova
    classe che rispetti `SummaryGenerator` e chiami un LLM reale (con prompt,
    citazioni delle fonti, e gestione esplicita delle affermazioni non
    verificabili in `unverified_claims`).
    """

    MODEL_NAME = "template-placeholder-v0"

    def generate(
        self,
        record: Any,
        advertisements: list[Any],
        forum_snippets: list[str],
    ) -> SummaryPayload:
        ad_count = len(advertisements)
        summary_text = (
            f"Riepilogo generato automaticamente (placeholder, nessuna analisi AI reale). "
            f"Trovati {ad_count} annunci associati a questo numero."
        )

        advertisement_information = [
            {
                "source_url": getattr(ad, "source_url", None),
                "title": getattr(ad, "title", None),
            }
            for ad in advertisements
        ]

        forum_information = [{"snippet": snippet} for snippet in forum_snippets]

        # Il generatore placeholder non può verificare nulla: marchiamo
        # esplicitamente ogni fonte come "non verificata" per evitare che un
        # consumatore dell'API scambi questo output per un'analisi affidabile.
        unverified_claims = [
            "Questo riepilogo è generato da un template placeholder e non costituisce "
            "un'analisi verificata dei contenuti."
        ]

        sources = [
            getattr(ad, "source_url", None)
            for ad in advertisements
            if getattr(ad, "source_url", None)
        ]

        return SummaryPayload(
            summary=summary_text,
            advertisement_information=advertisement_information,
            forum_information=forum_information,
            unverified_claims=unverified_claims,
            sources=sources,
        )
