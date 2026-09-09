"""Admin-only CRUD and safe connectivity tests for scraper proxy pools."""

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import UTC, datetime, timedelta

import httpx
from curl_cffi.requests import AsyncSession as CurlAsyncSession
from curl_cffi.requests.errors import RequestsError as CurlRequestsError
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.proxies import ProxyEndpoint, ProxyPool, ProxyPoolMember, ScrapeRunProxyAttempt
from app.models.sources import Source
from app.models.users import User
from app.schemas.proxies import (
    ProxyEndpointCreate,
    ProxyEndpointRead,
    ProxyEndpointUpdate,
    ProxyPoolCreate,
    ProxyPoolRead,
    ProxyPoolUpdate,
    ProxyTestInput,
    ProxyTestRead,
)
from app.security.deps import require_admin_with_2fa, require_role
from app.services.audit import log_action
from app.services.proxy_credentials import decrypt_proxy_credentials, encrypt_proxy_credentials
from app.services.proxy_rotation import ProxyRuntimeConfig, proxy_host_is_allowed

router = APIRouter()


def _endpoint_read(row: ProxyEndpoint) -> ProxyEndpointRead:
    now = datetime.now(UTC)
    health = (
        "disabled"
        if not row.enabled
        else ("cooldown" if row.cooldown_until and row.cooldown_until > now else "healthy")
    )
    return ProxyEndpointRead(
        id=row.id,
        name=row.name,
        scheme=row.scheme,
        host=row.host,
        port=row.port,
        enabled=row.enabled,
        credential_configured=row.credentials_encrypted is not None,
        health=health,
        consecutive_failures=row.consecutive_failures,
        cooldown_until=row.cooldown_until,
        last_used_at=row.last_used_at,
        last_success_at=row.last_success_at,
        last_failure_at=row.last_failure_at,
    )


async def _pool_read(db: AsyncSession, row: ProxyPool) -> ProxyPoolRead:
    members = (
        await db.execute(
            select(ProxyEndpoint.id, ProxyEndpoint.enabled, ProxyEndpoint.cooldown_until)
            .join(ProxyPoolMember, ProxyPoolMember.proxy_id == ProxyEndpoint.id)
            .where(ProxyPoolMember.pool_id == row.id)
            .order_by(ProxyEndpoint.name)
        )
    ).all()
    now = datetime.now(UTC)
    return ProxyPoolRead(
        id=row.id,
        name=row.name,
        enabled=row.enabled,
        proxy_ids=[item.id for item in members],
        total_count=len(members),
        healthy_count=sum(
            1
            for item in members
            if item.enabled and (item.cooldown_until is None or item.cooldown_until <= now)
        ),
    )


async def _validate_host(host: str) -> str:
    value = host.strip().rstrip(".")
    if not value or "://" in value or "@" in value or "/" in value:
        raise HTTPException(422, "Inserire soltanto hostname o indirizzo IP del proxy.")
    if not await asyncio.to_thread(proxy_host_is_allowed, value):
        raise HTTPException(422, "Host proxy non pubblico o non consentito dall'allowlist.")
    return value


async def _replace_members(db: AsyncSession, pool_id: uuid.UUID, ids: list[uuid.UUID]) -> None:
    unique_ids = list(dict.fromkeys(ids))
    if unique_ids:
        found = set(
            (await db.execute(select(ProxyEndpoint.id).where(ProxyEndpoint.id.in_(unique_ids))))
            .scalars()
            .all()
        )
        if found != set(unique_ids):
            raise HTTPException(422, "Uno o piu proxy selezionati non esistono.")
    await db.execute(delete(ProxyPoolMember).where(ProxyPoolMember.pool_id == pool_id))
    db.add_all([ProxyPoolMember(pool_id=pool_id, proxy_id=item) for item in unique_ids])


@router.get("/proxy-pools", response_model=list[ProxyPoolRead])
async def list_proxy_pools(
    db: AsyncSession = Depends(get_db), _admin: User = Depends(require_role("admin"))
) -> list[ProxyPoolRead]:
    rows = (await db.execute(select(ProxyPool).order_by(ProxyPool.name))).scalars().all()
    return [await _pool_read(db, row) for row in rows]


@router.post("/proxy-pools", response_model=ProxyPoolRead, status_code=status.HTTP_201_CREATED)
async def create_proxy_pool(
    payload: ProxyPoolCreate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin_with_2fa),
) -> ProxyPoolRead:
    row = ProxyPool(name=payload.name.strip(), enabled=payload.enabled)
    db.add(row)
    try:
        await db.flush()
        await _replace_members(db, row.id, payload.proxy_ids)
        await log_action(
            db,
            user_id=admin.id,
            action="create_proxy_pool",
            entity_type="proxy_pool",
            entity_id=str(row.id),
            details={"member_count": len(set(payload.proxy_ids))},
        )
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(409, "Esiste gia un pool con questo nome.") from exc
    await db.refresh(row)
    return await _pool_read(db, row)


async def _pool_or_404(db: AsyncSession, pool_id: uuid.UUID) -> ProxyPool:
    row = await db.get(ProxyPool, pool_id)
    if row is None:
        raise HTTPException(404, "Pool proxy non trovato.")
    return row


@router.patch("/proxy-pools/{pool_id}", response_model=ProxyPoolRead)
async def update_proxy_pool(
    pool_id: uuid.UUID,
    payload: ProxyPoolUpdate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin_with_2fa),
) -> ProxyPoolRead:
    row = await _pool_or_404(db, pool_id)
    if payload.name is not None:
        row.name = payload.name.strip()
    if payload.enabled is not None:
        row.enabled = payload.enabled
    if payload.proxy_ids is not None:
        await _replace_members(db, row.id, payload.proxy_ids)
    await log_action(
        db,
        user_id=admin.id,
        action="update_proxy_pool",
        entity_type="proxy_pool",
        entity_id=str(row.id),
        details={"membership_changed": payload.proxy_ids is not None},
    )
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(409, "Esiste gia un pool con questo nome.") from exc
    await db.refresh(row)
    return await _pool_read(db, row)


@router.delete("/proxy-pools/{pool_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_proxy_pool(
    pool_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin_with_2fa),
) -> None:
    row = await _pool_or_404(db, pool_id)
    references = await db.scalar(
        select(func.count()).select_from(Source).where(Source.proxy_pool_id == pool_id)
    )
    if references:
        raise HTTPException(409, "Il pool e assegnato a una o piu fonti; disabilitarlo invece.")
    await log_action(
        db,
        user_id=admin.id,
        action="delete_proxy_pool",
        entity_type="proxy_pool",
        entity_id=str(row.id),
    )
    await db.delete(row)
    await db.commit()


@router.get("/proxies", response_model=list[ProxyEndpointRead])
async def list_proxies(
    db: AsyncSession = Depends(get_db), _admin: User = Depends(require_role("admin"))
) -> list[ProxyEndpointRead]:
    rows = (await db.execute(select(ProxyEndpoint).order_by(ProxyEndpoint.name))).scalars().all()
    return [_endpoint_read(row) for row in rows]


@router.post("/proxies", response_model=ProxyEndpointRead, status_code=status.HTTP_201_CREATED)
async def create_proxy(
    payload: ProxyEndpointCreate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin_with_2fa),
) -> ProxyEndpointRead:
    host = await _validate_host(payload.host)
    try:
        encrypted = (
            encrypt_proxy_credentials(payload.username, payload.password or "")
            if payload.username is not None
            else None
        )
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    row = ProxyEndpoint(
        name=payload.name.strip(),
        scheme=payload.scheme,
        host=host,
        port=payload.port,
        credentials_encrypted=encrypted,
        enabled=payload.enabled,
    )
    db.add(row)
    try:
        await db.flush()
        await log_action(
            db,
            user_id=admin.id,
            action="create_proxy",
            entity_type="proxy_endpoint",
            entity_id=str(row.id),
            details={"scheme": row.scheme, "credential_configured": encrypted is not None},
        )
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(409, "Esiste gia un proxy con questo nome.") from exc
    await db.refresh(row)
    return _endpoint_read(row)


async def _proxy_or_404(db: AsyncSession, proxy_id: uuid.UUID) -> ProxyEndpoint:
    row = await db.get(ProxyEndpoint, proxy_id)
    if row is None:
        raise HTTPException(404, "Proxy non trovato.")
    return row


@router.patch("/proxies/{proxy_id}", response_model=ProxyEndpointRead)
async def update_proxy(
    proxy_id: uuid.UUID,
    payload: ProxyEndpointUpdate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin_with_2fa),
) -> ProxyEndpointRead:
    row = await _proxy_or_404(db, proxy_id)
    connection_changed = any(
        value is not None
        for value in (payload.scheme, payload.host, payload.port, payload.username)
    ) or payload.clear_credential
    if payload.name is not None:
        row.name = payload.name.strip()
    if payload.scheme is not None:
        row.scheme = payload.scheme
    if payload.host is not None:
        row.host = await _validate_host(payload.host)
    if payload.port is not None:
        row.port = payload.port
    if payload.username is not None:
        try:
            row.credentials_encrypted = encrypt_proxy_credentials(
                payload.username, payload.password or ""
            )
        except RuntimeError as exc:
            raise HTTPException(503, str(exc)) from exc
    elif payload.clear_credential:
        row.credentials_encrypted = None
    if payload.enabled is not None:
        row.enabled = payload.enabled
    if connection_changed:
        row.consecutive_failures = 0
        row.cooldown_until = None
        row.last_success_at = None
        row.last_failure_at = None
    await log_action(
        db,
        user_id=admin.id,
        action="update_proxy",
        entity_type="proxy_endpoint",
        entity_id=str(row.id),
        details={"credential_changed": payload.username is not None or payload.clear_credential},
    )
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(409, "Esiste gia un proxy con questo nome.") from exc
    await db.refresh(row)
    return _endpoint_read(row)


@router.delete("/proxies/{proxy_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_proxy(
    proxy_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin_with_2fa),
) -> None:
    row = await _proxy_or_404(db, proxy_id)
    member_count = await db.scalar(
        select(func.count())
        .select_from(ProxyPoolMember)
        .where(ProxyPoolMember.proxy_id == proxy_id)
    )
    history_count = await db.scalar(
        select(func.count())
        .select_from(ScrapeRunProxyAttempt)
        .where(ScrapeRunProxyAttempt.proxy_endpoint_id == proxy_id)
    )
    if member_count or history_count:
        raise HTTPException(409, "Il proxy e referenziato da pool o storico; disabilitarlo invece.")
    await log_action(
        db,
        user_id=admin.id,
        action="delete_proxy",
        entity_type="proxy_endpoint",
        entity_id=str(row.id),
    )
    await db.delete(row)
    await db.commit()


@router.post("/proxies/{proxy_id}/test", response_model=ProxyTestRead)
async def test_proxy(
    proxy_id: uuid.UUID,
    payload: ProxyTestInput,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin_with_2fa),
) -> ProxyTestRead:
    row = await _proxy_or_404(db, proxy_id)
    source = await db.get(Source, payload.source_id)
    if source is None:
        raise HTTPException(404, "Fonte non trovata.")
    if not await asyncio.to_thread(proxy_host_is_allowed, row.host):
        raise HTTPException(422, "Host proxy non pubblico o non consentito dall'allowlist.")
    try:
        credentials = decrypt_proxy_credentials(row.credentials_encrypted)
    except RuntimeError as exc:
        raise HTTPException(503, "Credenziali proxy non disponibili.") from exc
    runtime = ProxyRuntimeConfig(
        row.id,
        row.scheme,
        row.host,
        row.port,
        credentials[0] if credentials else None,
        credentials[1] if credentials else None,
    )
    started = time.monotonic()
    success = False
    category = "network_error"
    try:
        if runtime.scheme == "socks4":
            async with CurlAsyncSession() as client:
                curl_response = await client.get(
                    source.base_url,
                    headers={"User-Agent": "LavoroEsterno-ProxyTest/1.0"},
                    allow_redirects=False,
                    timeout=15,
                    proxy=runtime.httpx_url(),
                )
            response_status = curl_response.status_code
        else:
            async with httpx.AsyncClient(
                proxy=runtime.httpx_url(), timeout=15, follow_redirects=False
            ) as client:
                response = await client.get(
                    source.base_url, headers={"User-Agent": "LavoroEsterno-ProxyTest/1.0"}
                )
            response_status = response.status_code
        success = 200 <= response_status < 400
        category = f"http_{response_status // 100}xx"
    except (httpx.TimeoutException, httpx.TransportError, CurlRequestsError):
        success = False
    latency = int((time.monotonic() - started) * 1000)
    now = datetime.now(UTC)
    if success:
        row.consecutive_failures = 0
        row.cooldown_until = None
        row.last_success_at = now
    else:
        row.consecutive_failures += 1
        row.last_failure_at = now
        steps = (5, 15, 30, 60)
        row.cooldown_until = now + timedelta(minutes=steps[min(row.consecutive_failures - 1, 3)])
    await log_action(
        db,
        user_id=admin.id,
        action="test_proxy",
        entity_type="proxy_endpoint",
        entity_id=str(row.id),
        details={"success": success, "status_category": category},
    )
    await db.commit()
    return ProxyTestRead(
        success=success,
        latency_ms=latency,
        status_category=category,
        message="Connessione riuscita." if success else "Connessione proxy non riuscita.",
    )
