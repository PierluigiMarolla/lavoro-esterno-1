"""Entry point dell'applicazione FastAPI."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.config import settings

app = FastAPI(
    title=settings.APP_NAME,
    description=(
        "API per la raccolta e deduplicazione di annunci per numero di telefono, "
        "con gestione media e arricchimento AI."
    ),
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")


@app.get("/api/v1/healthz", tags=["health"])
async def healthz() -> dict[str, str]:
    """Endpoint di health-check, usato da orchestratori/load balancer."""
    return {"status": "ok", "environment": settings.ENVIRONMENT}
