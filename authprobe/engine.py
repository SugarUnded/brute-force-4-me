"""Async HTTP login probe engine.

Sends candidate credential pairs to a single HTTP endpoint and detects which
ones are accepted. Detection is configurable because every login flow signals
success differently: a 302 redirect, a disappearing error string, an appearing
welcome banner, a cookie being set, etc.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Iterable, Optional

import httpx

__all__ = ["ProbeConfig", "Attempt", "RateLimiter", "is_success", "run_probe"]


@dataclass
class ProbeConfig:
    """Everything needed to probe one login endpoint."""

    url: str
    method: str = "POST"
    username_field: str = "username"
    password_field: str = "password"
    headers: dict[str, str] = field(default_factory=dict)
    extra_data: dict[str, str] = field(default_factory=dict)

    # Detection, checked in this order:
    #   1. success_body_contains  -> body contains marker
    #   2. failure_body_contains  -> body does NOT contain marker
    #   3. success_status         -> status code in set
    success_body_contains: Optional[str] = None
    failure_body_contains: Optional[str] = None
    success_status: tuple[int, ...] = (301, 302, 303, 307, 308)

    timeout: float = 10.0
    concurrency: int = 10
    rate: float = 0.0  # requests/sec, 0 == unlimited
    follow_redirects: bool = False
    stop_on_success: bool = True
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
    """Decide whether a response means the credentials were accepted."""
    if cfg.success_body_contains is not None:
        return cfg.success_body_contains in body
    if cfg.failure_body_contains is not None:
        return cfg.failure_body_contains not in body
    return status in cfg.success_status


class RateLimiter:
    """Token-free spacing limiter: enforces a minimum gap between acquires."""

    def __init__(self, rate: float) -> None:
        self.rate = rate
        self._lock = asyncio.Lock()
        self._next_at = 0.0

    async def acquire(self) -> None:
        if self.rate <= 0:
            return
        async with self._lock:
            now = time.monotonic()
            wait = self._next_at - now
            if wait > 0:
                await asyncio.sleep(wait)
                now = time.monotonic()
            self._next_at = now + (1.0 / self.rate)


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
    """Run the probe and return every successful attempt.

    ``client``/``transport`` exist mainly for tests; when omitted a fresh
    client is created and closed internally.
    """
    limiter = RateLimiter(cfg.rate)
    stop = asyncio.Event()
    found: list[Attempt] = []

    # One shared, lazily-consumed stream of credential pairs. Workers pull a
    # single pair at a time under a lock; when ``stop`` is set they simply stop
    # pulling, so there is no producer/queue to deadlock on.
    sentinel = object()
    combo_iter = ((u, p) for u in usernames for p in passwords)
    pick_lock = asyncio.Lock()

    async def pick():
        async with pick_lock:
            return next(combo_iter, sentinel)

    owns_client = client is None
    if client is None:
        headers = dict(cfg.headers)
        if cfg.user_agent:
            headers.setdefault("User-Agent", cfg.user_agent)
        client = httpx.AsyncClient(
            timeout=cfg.timeout,
            follow_redirects=cfg.follow_redirects,
            headers=headers or None,
            transport=transport,
        )

    def _halted() -> bool:
        return stop.is_set() or (cancel_event is not None and cancel_event.is_set())

    async def worker() -> None:
        while not _halted():
            item = await pick()
            if item is sentinel or _halted():
                return
            username, password = item
            await limiter.acquire()

            data = dict(cfg.extra_data)
            data[cfg.username_field] = username
            data[cfg.password_field] = password

            start = time.perf_counter()
            try:
                if cfg.method.upper() == "GET":
                    resp = await client.get(cfg.url, params=data)
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
                    return

    workers = [asyncio.create_task(worker()) for _ in range(max(1, cfg.concurrency))]
    try:
        await asyncio.gather(*workers)
    finally:
        if owns_client:
            await client.aclose()

    return found
