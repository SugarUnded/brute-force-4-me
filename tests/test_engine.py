import asyncio
import urllib.parse

import httpx
import pytest

from authprobe.engine import Attempt, ProbeConfig, is_success, run_probe


# --- is_success -------------------------------------------------------------

def test_success_by_status():
    cfg = ProbeConfig(url="http://x", success_status=(302,))
    assert is_success(cfg, 302, "whatever") is True
    assert is_success(cfg, 200, "whatever") is False


def test_success_by_body_marker():
    cfg = ProbeConfig(url="http://x", success_body_contains="Dashboard")
    assert is_success(cfg, 200, "<h1>Dashboard</h1>") is True
    assert is_success(cfg, 200, "<h1>Login</h1>") is False


def test_success_by_absence_of_failure_marker():
    cfg = ProbeConfig(url="http://x", failure_body_contains="Invalid credentials")
    assert is_success(cfg, 200, "Welcome back") is True
    assert is_success(cfg, 200, "Invalid credentials") is False


def test_body_marker_takes_priority_over_status():
    cfg = ProbeConfig(
        url="http://x",
        success_status=(302,),
        success_body_contains="ok",
    )
    # status matches but body marker says no -> failure (marker wins)
    assert is_success(cfg, 302, "nope") is False


def test_default_is_unlimited():
    # max power: unlimited concurrency by default, no rate limiter field at all
    cfg = ProbeConfig(url="http://x")
    assert cfg.concurrency <= 0
    assert not hasattr(cfg, "rate")


def test_unlimited_mode_finds_hits():
    def handler(request: httpx.Request) -> httpx.Response:
        form = dict(urllib.parse.parse_qsl(request.content.decode()))
        if form.get("password") == "hit":
            return httpx.Response(302)
        return httpx.Response(200, text="Invalid")

    cfg = ProbeConfig(url="http://target/login", success_status=(302,), concurrency=0)
    client = _mock_client(handler)
    try:
        found = asyncio.run(
            run_probe(cfg, ["admin"], ["a", "b", "hit", "c", "d"], client=client)
        )
    finally:
        asyncio.run(client.aclose())

    assert [a.password for a in found] == ["hit"]


# --- run_probe --------------------------------------------------------------

def _mock_client(handler):
    return httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        follow_redirects=False,
        timeout=5.0,
    )


def test_run_probe_finds_the_password():
    def handler(request: httpx.Request) -> httpx.Response:
        form = dict(urllib.parse.parse_qsl(request.content.decode()))
        if form.get("password") == "s3cret":
            return httpx.Response(302, headers={"location": "/admin"})
        return httpx.Response(200, text="Invalid credentials")

    cfg = ProbeConfig(
        url="http://target/login",
        success_status=(302,),
        concurrency=2,
    )
    client = _mock_client(handler)
    try:
        found = asyncio.run(
            run_probe(cfg, ["admin"], ["wrong", "s3cret", "other"], client=client)
        )
    finally:
        asyncio.run(client.aclose())

    assert [a.password for a in found] == ["s3cret"]
    assert all(isinstance(a, Attempt) for a in found)


def test_run_probe_reports_nothing_when_no_match():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="Invalid credentials")

    cfg = ProbeConfig(url="http://target/login", success_status=(302,))
    client = _mock_client(handler)
    try:
        found = asyncio.run(run_probe(cfg, ["admin"], ["a", "b"], client=client))
    finally:
        asyncio.run(client.aclose())

    assert found == []


def test_on_attempt_hook_sees_every_probe():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="nope")

    seen: list[Attempt] = []
    cfg = ProbeConfig(url="http://target/login", concurrency=1)
    client = _mock_client(handler)
    try:
        asyncio.run(
            run_probe(cfg, ["u1", "u2"], ["p1"], client=client, on_attempt=seen.append)
        )
    finally:
        asyncio.run(client.aclose())

    assert {a.username for a in seen} == {"u1", "u2"}


def test_stop_on_success_halts_early():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        form = dict(urllib.parse.parse_qsl(request.content.decode()))
        if form.get("password") == "first":
            return httpx.Response(302)
        return httpx.Response(200, text="Invalid")

    cfg = ProbeConfig(
        url="http://target/login",
        success_status=(302,),
        concurrency=1,
        stop_on_success=True,
    )
    client = _mock_client(handler)
    try:
        found = asyncio.run(
            run_probe(cfg, ["admin"], ["first"] + [f"p{i}" for i in range(50)], client=client)
        )
    finally:
        asyncio.run(client.aclose())

    assert len(found) == 1
    assert calls["n"] == 1  # never probed the rest


def test_stop_on_success_does_not_deadlock_under_concurrency():
    """Regression: draining sentinels used to starve sibling workers."""

    def handler(request: httpx.Request) -> httpx.Response:
        form = dict(urllib.parse.parse_qsl(request.content.decode()))
        if form.get("password") == "hit":
            return httpx.Response(302)
        return httpx.Response(200, text="Invalid")

    cfg = ProbeConfig(
        url="http://target/login",
        success_status=(302,),
        concurrency=8,
        stop_on_success=True,
    )
    client = _mock_client(handler)
    try:
        found = asyncio.run(
            run_probe(cfg, ["admin"], ["a", "b", "hit", "c", "d", "e", "f"], client=client)
        )
    finally:
        asyncio.run(client.aclose())

    assert "hit" in [a.password for a in found]


def test_http_error_does_not_crash():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    cfg = ProbeConfig(url="http://target/login", success_status=(302,))
    client = _mock_client(handler)
    try:
        found = asyncio.run(run_probe(cfg, ["admin"], ["x"], client=client))
    finally:
        asyncio.run(client.aclose())

    assert found == []
