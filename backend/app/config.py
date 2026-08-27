"""Configurazione centralizzata dell'applicazione.

Tutte le variabili sono lette dall'ambiente (o da un file .env, gestito da un
task separato che crea `.env.example` a livello di repository: qui definiamo
solo la struttura tipizzata e i default utili per lo sviluppo locale).
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Impostazioni applicative, validate a runtime da Pydantic Settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # --- Database -----------------------------------------------------
    # URL "canonico" in stile SQLAlchemy; il driver asyncpg viene forzato
    # a runtime in app.db se l'URL usa lo schema generico "postgresql://".
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://lavoro_esterno:lavoro_esterno@localhost:5432/lavoro_esterno",
        description="Connection string PostgreSQL (driver asyncpg per runtime async).",
    )
    # Variante sincrona usata da Alembic (psycopg2), che non supporta async.
    DATABASE_URL_SYNC: str | None = Field(
        default=None,
        description="Override opzionale per la connection string sincrona (Alembic).",
    )

    # --- Redis (broker/backend Celery e cache) -------------------------
    REDIS_URL: str = Field(
        default="redis://localhost:6379/0",
        description="URL di connessione a Redis, usato come broker/backend Celery.",
    )

    # --- MinIO (object storage per i media) -----------------------------
    MINIO_ENDPOINT: str = Field(
        default="localhost:9000", description="Host:porta dell'endpoint MinIO/S3."
    )
    MINIO_ACCESS_KEY: str = Field(default="minioadmin", description="Access key MinIO.")
    MINIO_SECRET_KEY: str = Field(default="minioadmin", description="Secret key MinIO.")
    MINIO_BUCKET: str = Field(
        default="lavoro-esterno-media", description="Bucket per i media raccolti."
    )
    MINIO_SECURE: bool = Field(
        default=False, description="Usa TLS per la connessione a MinIO (True in produzione)."
    )

    # --- JWT (autenticazione) -------------------------------------------
    JWT_SECRET_KEY: str = Field(
        default="dev-insecure-secret-change-me",
        description="Chiave simmetrica per firmare i JWT access/refresh (HS256).",
    )
    JWT_ALGORITHM: str = Field(default="HS256", description="Algoritmo di firma JWT.")
    JWT_ACCESS_TTL_MINUTES: int = Field(
        default=15, description="Durata di validità del token di accesso, in minuti."
    )
    JWT_REFRESH_TTL_DAYS: int = Field(
        default=14, description="Durata di validità del token di refresh, in giorni."
    )

    # --- Cifratura telefono (privacy / GDPR) ----------------------------
    # Chiave AES-256 (32 byte) codificata base64, usata per cifrare a riposo
    # il numero di telefono. Deve essere diversa da PHONE_HMAC_SECRET: la prima
    # cifra il dato (reversibile con la chiave), la seconda produce un hash di
    # lookup deterministico ma NON invertibile.
    PHONE_ENCRYPTION_KEY: str = Field(
        default="MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=",
        description="Chiave AES-256-GCM (32 byte, base64) per cifrare il numero di telefono.",
    )
    PHONE_HMAC_SECRET: str = Field(
        default="dev-insecure-hmac-secret-change-me",
        description="Chiave segreta HMAC-SHA256 per l'hash di lookup deterministico del telefono.",
    )

    # --- CORS -------------------------------------------------------------
    CORS_ORIGIN: str = Field(
        default="http://localhost:5173",
        description="Origin consentita per le richieste CORS del frontend (lista separata da virgole).",
    )

    # --- Applicazione -------------------------------------------------------
    APP_NAME: str = Field(default="Lavoro Esterno API", description="Nome applicazione.")
    ENVIRONMENT: str = Field(
        default="development", description="Ambiente di esecuzione (development/staging/production)."
    )

    @property
    def cors_origins(self) -> list[str]:
        """Espande CORS_ORIGIN (stringa CSV) in una lista di origin per FastAPI CORSMiddleware."""
        return [origin.strip() for origin in self.CORS_ORIGIN.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Restituisce un'istanza cacheata delle impostazioni (evita di ri-parsare l'ambiente)."""
    return Settings()


settings = get_settings()
