"""Task Celery per l'arricchimento AI (generazione riepiloghi)."""

from __future__ import annotations

import logging

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.workers.tasks_ai.generate_summary")
def generate_summary(record_id: str) -> dict:
    """Placeholder: in futuro caricherà il Record con i suoi Advertisement
    (ed eventuali snippet da forum), chiamerà un `SummaryGenerator` reale
    (vedi app/services/summary_generator.py, oggi solo `TemplateSummaryGenerator`)
    e salverà il risultato come nuova riga in `summary_versions`.

    TODO: sostituire `TemplateSummaryGenerator` con un generatore basato su
    un LLM reale e collegare qui il caricamento dei dati dal DB.
    """
    logger.info(
        "TODO: generazione riepilogo AI non ancora implementata per record_id=%s", record_id
    )
    return {"status": "skipped", "record_id": record_id}
