"""Async login probe: fire credential pairs at one endpoint, flag the hits."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Iterable, Optional

import httpx

__all__ = ["ProbeConfig", "Attempt", "is_success", "run_probe"]


@dataclass
class ProbeConfig:
    url: str
    method: str = "POST"
    username_field: str = "username"
    password_field: str = "password"
    headers: dict[str, str] = field(default_factory=dict)
    extra_data: dict[str, str] = field(default_factory=dict)

    # first match wins: success_body, then failure_body, then status
    success_body_contains: Optional[str] = None
    failure_body_contains: Optional[str] = None
    success_status: tuple[int, ...] = (301, 302, 303, 307, 308)

    timeout: float = 10.0
    concurrency: int = 0  # 0 or less = unlimited (one task per candidate)
    follow_redirects: bool = False
    stop_on_success: bool = True
    json_body: bool = False
    user_agent: Optional[str] = None


@dataclass(frozen=True)
class Attempt:
    username: str
    password: str
    status: int
    success: bool
    elapsed: float

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        tag = "HIT" if self.success else "miss"
        return f"<Attempt {tag} {self.username!r}:{self.password!r} status={self.status}>"


def is_success(cfg: ProbeConfig, status: int, body: str) -> bool:
    if cfg.success_body_contains is not None:
        return cfg.success_body_contains in body
    if cfg.failure_body_contains is not None:
        return cfg.failure_body_contains not in body
    return status in cfg.success_status


AttemptHook = Callable[[Attempt], Optional[Awaitable[None]]]


async def run_probe(
    cfg: ProbeConfig,
    usernames: Iterable[str],
    passwords: Iterable[str],
    *,
    client: Optional[httpx.AsyncClient] = None,
    transport: Optional[httpx.AsyncBaseTransport] = None,
    on_attempt: Optional[AttemptHook] = None,
    cancel_event: Optional[asyncio.Event] = None,
) -> list[Attempt]:
    """Run the probe, return every accepted pair. client/transport are for tests."""
    stop = asyncio.Event()
    found: list[Attempt] = []
    unlimited = cfg.concurrency <= 0

    def _halted() -> bool:
        return stop.is_set() or (cancel_event is not None and cancel_event.is_set())

    owns_client = client is None
    if client is None:
        headers = dict(cfg.headers)
        if cfg.user_agent:
            headers.setdefault("User-Agent", cfg.user_agent)
        # httpx caps the pool at 100 connections by default, which would kneecap
        # us no matter how high concurrency is, so open it wide.
        limits = (
            httpx.Limits(max_connections=None, max_keepalive_connections=None)
            if unlimited
            else httpx.Limits(
                max_connections=cfg.concurrency + 64,
                max_keepalive_connections=cfg.concurrency,
            )
        )
        client = httpx.AsyncClient(
            timeout=cfg.timeout,
            follow_redirects=cfg.follow_redirects,
            headers=headers or None,
            transport=transport,
            limits=limits,
        )

    async def probe_one(username: str, password: str) -> None:
        data = dict(cfg.extra_data)
        data[cfg.username_field] = username
        data[cfg.password_field] = password

        start = time.perf_counter()
        try:
            if cfg.method.upper() == "GET":
                resp = await client.get(cfg.url, params=data)
            elif cfg.json_body:
                resp = await client.post(cfg.url, json=data)
            else:
                resp = await client.post(cfg.url, data=data)
            status, body = resp.status_code, resp.text
        except httpx.HTTPError as exc:
            status, body = -1, f"<error: {exc!r}>"
        elapsed = time.perf_counter() - start

        attempt = Attempt(username, password, status, is_success(cfg, status, body), elapsed)
        if on_attempt is not None:
            result = on_attempt(attempt)
            if asyncio.iscoroutine(result):
                await result

        if attempt.success:
            found.append(attempt)
            if cfg.stop_on_success:
                stop.set()

    combos = ((u, p) for u in usernames for p in passwords)

    try:
        if unlimited:
            # no cap: a task per candidate, all in flight at once
            tasks = []
            for username, password in combos:
                if _halted():
                    break
                tasks.append(asyncio.create_task(probe_one(username, password)))
            if tasks:
                await asyncio.gather(*tasks)
        else:
            sentinel = object()
            pick_lock = asyncio.Lock()

            async def pick():
                async with pick_lock:
                    return next(combos, sentinel)

            async def worker() -> None:
                while not _halted():
                    item = await pick()
                    if item is sentinel or _halted():
                        return
                    await probe_one(*item)

            workers = [asyncio.create_task(worker()) for _ in range(cfg.concurrency)]
            await asyncio.gather(*workers)
    finally:
        if owns_client:
            await client.aclose()

    return found
