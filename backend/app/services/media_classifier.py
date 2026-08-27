"""Classificazione dei media (esplicito / safe / non classificato).

Definiamo un'interfaccia astratta (`MediaClassifier`) in modo che
l'implementazione reale (es. un modello ONNX per la rilevazione di contenuti
espliciti) possa essere sostituita senza toccare i chiamanti (worker Celery,
endpoint media). L'implementazione fornita di default in questo scaffold è un
PLACEHOLDER che non fa alcuna inferenza reale.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class ClassificationResult:
    """Esito di una classificazione media."""

    classification: str
    """Uno tra "explicit", "safe", "unclassified" (vedi app.models.media.MediaClassification)."""

    confidence: float
    """Confidenza del modello nell'intervallo [0, 1]."""

    model_version: str
    """Identificatore della versione del modello/euristica usata, salvato in
    `media.classifier_version` per tracciabilità e riproducibilità."""


class MediaClassifier(ABC):
    """Interfaccia per un classificatore di contenuti media."""

    @abstractmethod
    def classify(self, file_bytes: bytes, mime_type: str) -> ClassificationResult:
        """Classifica il contenuto di un file media (immagine o frame video)."""
        raise NotImplementedError


class RuleBasedMediaClassifier(MediaClassifier):
    """Implementazione PLACEHOLDER.

    Non esegue alcuna analisi reale del contenuto: restituisce sempre
    "unclassified" con confidenza 0.0. Serve a:
    - permettere che l'intera pipeline (upload -> media row -> task Celery di
      classificazione -> aggiornamento DB) sia end-to-end funzionante fin da
      subito, senza dipendere dalla disponibilità di un modello ML;
    - definire chiaramente il punto di sostituzione: rimpiazzare questa
      classe con un classificatore ONNX/reale (es. basato su un modello di
      content-moderation) mantenendo la stessa interfaccia `MediaClassifier`.
    """

    MODEL_VERSION = "placeholder-unclassified-v0"

    def classify(self, file_bytes: bytes, mime_type: str) -> ClassificationResult:
        return ClassificationResult(
            classification="unclassified",
            confidence=0.0,
            model_version=self.MODEL_VERSION,
        )
