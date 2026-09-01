"""Aggrega tutti i modelli ORM sotto un unico registry (`Base`).

Importare questo pacchetto (invece dei singoli moduli) garantisce che
`Base.metadata` contenga TUTTE le tabelle: è quello che Alembic usa come
`target_metadata` in migrations/env.py per l'autogenerate.

L'ordine di import qui non è rilevante per le FK grazie a `use_alter=True`
sulla FK circolare record<->advertisement (vedi app/models/record.py); lo
manteniamo comunque in un ordine "logico" (entità base prima, entità di
audit/derivate dopo) per leggibilità.
"""

from app.models.advertisement import Advertisement
from app.models.audit_log import AuditLog
from app.models.base import Base
from app.models.canonical_history import CanonicalHistory
from app.models.export_jobs import ExportJob
from app.models.media import Media
from app.models.media_classification_history import MediaClassificationHistory
from app.models.record import Record
from app.models.scrape_errors import ScrapeError
from app.models.scrape_runs import ScrapeRun
from app.models.sources import Source
from app.models.summary_generation_jobs import SummaryGenerationJob
from app.models.summary_versions import SummaryVersion
from app.models.users import User

__all__ = [
    "Base",
    "User",
    "Source",
    "Record",
    "Advertisement",
    "Media",
    "CanonicalHistory",
    "ScrapeRun",
    "ScrapeError",
    "MediaClassificationHistory",
    "SummaryVersion",
    "SummaryGenerationJob",
    "ExportJob",
    "AuditLog",
]
