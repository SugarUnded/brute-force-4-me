"""Command-line interface for authprobe."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from .engine import Attempt, ProbeConfig, run_probe


def _read_lines(path: str) -> list[str]:
    lines = []
    for raw in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        lines.append(line)
    return lines


def _parse_status(value: str) -> tuple[int, ...]:
    return tuple(int(x.strip()) for x in value.split(",") if x.strip())


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="authprobe",
        description="Probe an HTTP login endpoint with candidate credentials (authorized testing only).",
    )
    p.add_argument("url", help="login endpoint URL")
    p.add_argument("-m", "--method", default="POST", choices=["POST", "GET"])
    p.add_argument("--user-field", default="username")
    p.add_argument("--pass-field", default="password")
    p.add_argument("--user", help="single username to test")
    p.add_argument("--users", help="file with usernames (one per line)")
    p.add_argument("-w", "--wordlist", required=True, help="password wordlist file")
    p.add_argument("--success-status", default="301,302,303,307,308",
                   help="comma-separated status codes meaning success")
    p.add_argument("--success-body", help="success marker substring in response body")
    p.add_argument("--failure-body", help="failure marker substring in response body")
    p.add_argument("-H", "--header", action="append", default=[], metavar="K:V",
                   help="extra request header (repeatable)")
    p.add_argument("-d", "--data", action="append", default=[], metavar="K:V",
                   help="extra static form field (repeatable)")
    p.add_argument("-c", "--concurrency", type=int, default=10)
    p.add_argument("-r", "--rate", type=float, default=0.0, help="requests/sec cap (0 = unlimited)")
    p.add_argument("-t", "--timeout", type=float, default=10.0)
    p.add_argument("--user-agent")
    p.add_argument("--follow-redirects", action="store_true")
    p.add_argument("--no-stop", action="store_true", help="keep going after a hit")
    p.add_argument("-q", "--quiet", action="store_true")
    p.add_argument("--json", help="write results to this JSON file")
    return p


def _kv(items: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for item in items:
        if ":" not in item:
            raise SystemExit(f"expected K:V, got {item!r}")
        key, val = item.split(":", 1)
        out[key.strip()] = val.strip()
    return out


def _collect_usernames(args: argparse.Namespace) -> list[str]:
    users: list[str] = []
    if args.users:
        users.extend(_read_lines(args.users))
    if args.user:
        users.append(args.user)
    if not users:
        raise SystemExit("provide --user or --users")
    return users


async def _run(args: argparse.Namespace) -> int:
    cfg = ProbeConfig(
        url=args.url,
        method=args.method,
        username_field=args.user_field,
        password_field=args.pass_field,
        headers=_kv(args.header),
        extra_data=_kv(args.data),
        success_status=_parse_status(args.success_status),
        success_body_contains=args.success_body,
        failure_body_contains=args.failure_body,
        timeout=args.timeout,
        concurrency=args.concurrency,
        rate=args.rate,
        follow_redirects=args.follow_redirects,
        stop_on_success=not args.no_stop,
        user_agent=args.user_agent,
    )

    usernames = _collect_usernames(args)
    passwords = _read_lines(args.wordlist)
    if not passwords:
        raise SystemExit(f"wordlist {args.wordlist!r} is empty")

    total = len(usernames) * len(passwords)
    state = {"done": 0}

    def on_attempt(attempt: Attempt) -> None:
        state["done"] += 1
        if args.quiet:
            return
        marker = "HIT " if attempt.success else "    "
        sys.stderr.write(
            f"\r{marker}{state['done']}/{total} "
            f"{attempt.username}:{attempt.password} -> {attempt.status}   "
        )
        sys.stderr.flush()

    if not args.quiet:
        sys.stderr.write(f"probing {args.url}  ({total} candidates, c={cfg.concurrency})\n")

    found = await run_probe(cfg, usernames, passwords, on_attempt=on_attempt)

    if not args.quiet:
        sys.stderr.write("\n")

    if found:
        print(f"\n[+] {len(found)} valid credential(s):")
        for hit in found:
            print(f"    {hit.username}:{hit.password}  (status {hit.status})")
    else:
        print("[-] no valid credentials found")

    if args.json:
        payload = {
            "url": cfg.url,
            "attempted": state["done"],
            "found": [h.__dict__ for h in found],
        }
        Path(args.json).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        if not args.quiet:
            print(f"[i] results written to {args.json}")

    return 0 if found else 1


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return asyncio.run(_run(args))
    except KeyboardInterrupt:
        print("\n[!] interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
