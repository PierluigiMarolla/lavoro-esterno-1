"""Fail-closed text moderation and faithful rewriting through local Gemma."""

from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.ai_settings import AIProviderConfig
from app.services.ai_config import runtime_config
from app.services.integration_crypto import encrypt_json

_SYSTEM_PROMPT = """Sei un filtro editoriale italiano. Valuta ogni campo. Se contiene
linguaggio scurrile, pornografico o sessualmente esplicito riscrivilo con linguaggio pulito,
preservando fatti, significato, numeri e nomi senza aggiungere informazioni. Se è pulito
restituiscilo IDENTICO e changed=false. Restituisci esclusivamente JSON conforme allo schema."""
_NUMERIC_TOKEN_RE = re.compile(r"\d+(?:[.,]\d+)?")


class ContentSanitizationError(RuntimeError):
    pass


@dataclass
class SanitizedContent:
    normalized: dict[str, Any]
    original_encrypted: bytes
    metadata: dict[str, Any]


def _selected_paths(normalized: dict[str, Any], scrape_config: dict[str, Any]) -> dict[str, str]:
    values: dict[str, str] = {}
    for name in ("title", "description"):
        value = normalized.get(name)
        if isinstance(value, str) and value:
            values[name] = value
    custom = normalized.get("custom_fields", {})
    for name, spec in scrape_config.get("fields", {}).items():
        value = custom.get(name)
        enabled = spec.get("sanitize_with_ai", spec.get("sanitizeWithAi", False))
        if enabled and isinstance(value, str):
            values[f"custom_fields.{name}"] = value
        item_fields = spec.get("item_fields", spec.get("itemFields", {}))
        if isinstance(value, list):
            for index, item in enumerate(value):
                if not isinstance(item, dict):
                    continue
                for child, child_spec in item_fields.items():
                    child_value = item.get(child)
                    child_enabled = child_spec.get(
                        "sanitize_with_ai", child_spec.get("sanitizeWithAi", False)
                    )
                    if child_enabled and isinstance(child_value, str):
                        values[f"custom_fields.{name}.{index}.{child}"] = child_value
    return values


def _set_path(target: dict[str, Any], path: str, value: str) -> None:
    parts = path.split(".")
    current: Any = target
    for part in parts[:-1]:
        current = current[int(part)] if isinstance(current, list) else current[part]
    current[parts[-1]] = value


def sanitize_normalized(
    session: Session, normalized: dict[str, Any], scrape_config: dict[str, Any]
) -> SanitizedContent:
    fields = _selected_paths(normalized, scrape_config)
    original = {"fields": fields}
    if not fields:
        return SanitizedContent(copy.deepcopy(normalized), encrypt_json(original), {"changed": []})
    provider = session.execute(
        select(AIProviderConfig).where(AIProviderConfig.provider == "ollama")
    ).scalar_one_or_none()
    if provider is None or not provider.enabled or "gemma" not in provider.model_name.lower():
        raise ContentSanitizationError("Gemma locale non configurato o non abilitato.")
    config = runtime_config(provider)
    field_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "changed": {"type": "boolean"},
            "value": {"type": "string"},
        },
        "required": ["path", "changed", "value"],
    }
    schema = {
        "type": "object",
        "properties": {"fields": {"type": "array", "items": field_schema}},
        "required": ["fields"],
    }
    body = {
        "model": config.model,
        "stream": False,
        "think": False,
        "format": schema,
        "options": {"temperature": 0, "num_predict": settings.AI_MAX_OUTPUT_TOKENS},
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {"fields": [{"path": key, "value": value} for key, value in fields.items()]},
                    ensure_ascii=False,
                ),
            },
        ],
    }
    last_error: Exception | None = None
    for _attempt in range(3):
        try:
            response = httpx.post(
                f"{config.base_url.rstrip('/')}/api/chat",
                json=body,
                timeout=settings.AI_PROVIDER_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            rows = json.loads(response.json()["message"]["content"]).get("fields")
            if (
                not isinstance(rows, list)
                or len(rows) != len(fields)
                or {row.get("path") for row in rows} != set(fields)
            ):
                raise ValueError("Risposta Gemma incompleta.")
            cleaned = copy.deepcopy(normalized)
            changed: list[str] = []
            for row in rows:
                path, value = row["path"], row["value"]
                if not isinstance(value, str) or not value.strip():
                    raise ValueError("Gemma ha restituito un testo vuoto.")
                if not isinstance(row.get("changed"), bool):
                    raise ValueError("Indicatore changed non valido.")
                if not row["changed"] and value != fields[path]:
                    raise ValueError("Gemma ha modificato un testo dichiarato invariato.")
                if row["changed"] and _NUMERIC_TOKEN_RE.findall(value) != _NUMERIC_TOKEN_RE.findall(
                    fields[path]
                ):
                    raise ValueError("Gemma ha alterato dati numerici del testo originale.")
                _set_path(cleaned, path, value)
                if row["changed"]:
                    changed.append(path)
            return SanitizedContent(
                cleaned,
                encrypt_json(original),
                {"changed": changed, "model": config.model, "revision": provider.revision},
            )
        except Exception as exc:
            last_error = exc
    raise ContentSanitizationError("Pulizia Gemma non riuscita.") from last_error
