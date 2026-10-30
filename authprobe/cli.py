"""Command-line interface for authprobe."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from . import banner
from .engine import Attempt, ProbeConfig, run_probe
from .presets import get_preset, list_presets


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


def _kv(items: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for item in items:
        if ":" not in item:
            raise SystemExit(f"expected K:V, got {item!r}")
        key, val = item.split(":", 1)
        out[key.strip()] = val.strip()
    return out


def _apply_preset_path(url: str, path: str | None) -> str:
    """Append a preset's path only when the given URL has no path of its own."""
    if not path:
        return url
    parts = urlsplit(url)
    if parts.path in ("", "/"):
        return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))
    return url


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="authprobe",
        description="Probe an HTTP login endpoint with candidate credentials.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("url", nargs="?", help="login endpoint URL (or base URL when using --preset)")
    p.add_argument("-m", "--method", choices=["POST", "GET"], default="POST")
    p.add_argument("--list-presets", action="store_true", help="print detection presets and exit")
    p.add_argument("--preset", help="detection preset (see --list-presets)")
    p.add_argument("--user-field", help="form field holding the username")
    p.add_argument("--pass-field", help="form field holding the password")
    p.add_argument("--user", help="single username to test")
    p.add_argument("--users", help="file with usernames (one per line)")
    p.add_argument("-w", "--wordlist", help="password wordlist file")
    p.add_argument("--success-status", help="comma-separated status codes meaning success")
    p.add_argument("--success-body", help="success marker substring in response body")
    p.add_argument("--failure-body", help="failure marker substring in response body")
    p.add_argument("--json-body", action="store_true", help="send credentials as a JSON body")
    p.add_argument("-H", "--header", action="append", default=[], metavar="K:V",
                   help="extra request header (repeatable)")
    p.add_argument("-d", "--data", action="append", default=[], metavar="K:V",
                   help="extra static form field (repeatable)")
    p.add_argument("-c", "--concurrency", type=int, default=0,
                   help="in-flight requests; 0 (default) = unlimited, one task per candidate")
    p.add_argument("-t", "--timeout", type=float, default=10.0)
    p.add_argument("--user-agent")
    p.add_argument("--follow-redirects", action="store_true")
    p.add_argument("--no-stop", action="store_true", help="keep going after a hit")
    p.add_argument("-q", "--quiet", action="store_true")
    p.add_argument("--no-banner", action="store_true", help="hide the ASCII banner")
    p.add_argument("--json", help="write results to this JSON file")
    return p


def _print_presets() -> None:
    print("Available presets:\n")
    for preset in list_presets():
        print(f"  {preset.name:<14} {preset.description}")
        print(f"  {'':<14} url: {preset.recommended_url()}")
        print(f"  {'':<14} fields: {preset.user_field} / {preset.pass_field}\n")


def _collect_usernames(args: argparse.Namespace) -> list[str]:
    users: list[str] = []
    if args.users:
        users.extend(_read_lines(args.users))
    if args.user:
        users.append(args.user)
    if not users:
        raise SystemExit("provide --user or --users")
    return users


def _build_config(args: argparse.Namespace) -> ProbeConfig:
    preset = get_preset(args.preset) if args.preset else None

    user_field = args.user_field or (preset.user_field if preset else "username")
    pass_field = args.pass_field or (preset.pass_field if preset else "password")
    success_status = (
        _parse_status(args.success_status)
        if args.success_status
        else (preset.success_status if preset else (301, 302, 303, 307, 308))
    )
    success_body = args.success_body or (preset.success_body_contains if preset else None)
    failure_body = args.failure_body or (preset.failure_body_contains if preset else None)
    json_body = args.json_body or (preset.json_body if preset else False)

    headers = dict(preset.headers) if preset else {}
    headers.update(_kv(args.header))

    return ProbeConfig(
        url=_apply_preset_path(args.url, preset.path if preset else None),
        method=args.method,
        username_field=user_field,
        password_field=pass_field,
        headers=headers,
        extra_data=_kv(args.data),
        success_status=success_status,
        success_body_contains=success_body,
        failure_body_contains=failure_body,
        timeout=args.timeout,
        concurrency=args.concurrency,
        follow_redirects=args.follow_redirects,
        stop_on_success=not args.no_stop,
        json_body=json_body,
        user_agent=args.user_agent,
    )


def _describe_detection(cfg: ProbeConfig) -> str:
    if cfg.success_body_contains is not None:
        return f"body has {cfg.success_body_contains!r}"
    if cfg.failure_body_contains is not None:
        return f"body lacks {cfg.failure_body_contains!r}"
    return "status in " + ",".join(str(s) for s in cfg.success_status)


async def _run(args: argparse.Namespace) -> int:
    cfg = _build_config(args)

    usernames = _collect_usernames(args)
    passwords = _read_lines(args.wordlist)
    if not passwords:
        raise SystemExit(f"wordlist {args.wordlist!r} is empty")

    total = len(usernames) * len(passwords)
    color = banner.supports_color(sys.stderr)
    state = {"done": 0}

    def on_attempt(attempt: Attempt) -> None:
        state["done"] += 1
        if args.quiet:
            return
        marker = banner.colorize("HIT ", banner.BGREEN, color) if attempt.success else "----"
        sys.stderr.write(
            f"\r{marker} {state['done']}/{total} "
            f"{attempt.username}:{attempt.password} -> {attempt.status}   "
        )
        sys.stderr.flush()

    if not args.quiet and not args.no_banner:
        banner.print_banner(sys.stderr, color=color)
        banner.print_panel(
            "authprobe",
            [
                ("target", cfg.url),
                ("method", cfg.method),
                ("fields", f"{cfg.username_field} / {cfg.password_field}"),
                ("candidates", f"{total}  ({len(usernames)} user x {len(passwords)} pass)"),
                ("mode", "MAX POWER (no rate limit)"),
                ("concurrency", "unlimited" if cfg.concurrency <= 0 else str(cfg.concurrency)),
                ("detect", _describe_detection(cfg)),
                ("stop", "first hit" if cfg.stop_on_success else "scan all"),
            ],
            sys.stderr,
            color=color,
        )
        sys.stderr.write("\n")

    found = await run_probe(cfg, usernames, passwords, on_attempt=on_attempt)

    if not args.quiet:
        sys.stderr.write("\n")

    out_color = banner.supports_color(sys.stdout)
    if found:
        header = f"[+] {len(found)} valid credential(s):"
        print("\n" + banner.colorize(header, banner.BGREEN, out_color))
        for hit in found:
            line = f"    {hit.username}:{hit.password}  (status {hit.status})"
            print(banner.colorize(line, banner.BGREEN, out_color))
    else:
        print(banner.colorize("[-] no valid credentials found", banner.BYELLOW, out_color))

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


def _print_welcome() -> None:
    """Bare `authprobe` opens the interface: banner plus a short cheat-sheet."""
    out = sys.stdout
    banner.print_banner(out, color=banner.supports_color(out))
    print("usage: authprobe <url> --user NAME -w WORDS [options]")
    print("       authprobe --list-presets")
    print()
    print("examples:")
    print("  authprobe https://host/login --user admin -w words.txt --success-status 302")
    print("  authprobe https://host --preset wp-login -w words.txt")
    print("  authprobe https://host/api/login --preset json-api --user admin -w words.txt")
    print()
    print("run `authprobe --help` for every flag")


def main(argv: list[str] | None = None) -> int:
    raw = sys.argv[1:] if argv is None else list(argv)
    if not raw:
        _print_welcome()
        return 0

    args = build_parser().parse_args(raw)

    if args.list_presets:
        _print_presets()
        return 0

    if not args.url:
        raise SystemExit("error: a target URL is required (or use --list-presets)")
    if not args.wordlist:
        raise SystemExit("error: -w/--wordlist is required")

    try:
        return asyncio.run(_run(args))
    except KeyboardInterrupt:
        print("\n[!] interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
