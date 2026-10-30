"""ASCII banner and boxed status panel for the CLI.

Everything here renders to a text stream. The logo falls back to a plain
7-bit ASCII font when the stream's encoding is not UTF-8, and colors are only
emitted to a TTY (or when ``FORCE_COLOR`` is set / suppressed by ``NO_COLOR``).
"""

from __future__ import annotations

import os
import sys
from typing import Iterable, Optional, TextIO

RESET = "\033[0m"
DIM = "\033[2m"
BGREEN = "\033[1;92m"
BYELLOW = "\033[1;93m"
BCYAN = "\033[1;96m"
BMAGENTA = "\033[1;95m"
BRED = "\033[1;91m"

# Banner palette. Change these two to restyle the whole banner.
LOGO_COLOR = BRED
TAGLINE_COLOR = BRED

# --- "SUGAR" logo, block font (Unicode) -----------------------------------
_BLOCK = [
    "███████╗██╗   ██╗ ██████╗  █████╗ ██████╗ ",
    "██╔════╝██║   ██║██╔════╝ ██╔══██╗██╔══██╗",
    "███████╗██║   ██║██║  ███╗███████║██████╔╝",
    "╚════██║██║   ██║██║   ██║██╔══██║██╔══██╗",
    "███████║╚██████╔╝╚██████╔╝██║  ██║██║  ██║",
    "╚══════╝ ╚═════╝  ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝",
]

# --- same word, plain 7-bit ASCII (fallback) ------------------------------
# Derived from the block font so the silhouette is identical and every row
# keeps the same width: any non-space cell becomes ``#``.
_PLAIN = ["".join("#" if ch != " " else " " for ch in row) for row in _BLOCK]

__all__ = [
    "supports_color",
    "use_unicode",
    "render_banner",
    "render_panel",
    "print_banner",
    "print_panel",
    "colorize",
    "RESET",
    "DIM",
    "BGREEN",
    "BYELLOW",
    "BCYAN",
    "BMAGENTA",
    "BRED",
]


def supports_color(stream: TextIO = sys.stderr) -> bool:
    """True when ANSI colors should be emitted to ``stream``."""
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("AUTHPROBE_FORCE_COLOR") or os.environ.get("FORCE_COLOR"):
        return True
    return bool(getattr(stream, "isatty", lambda: False)())


def use_unicode(stream: TextIO = sys.stderr) -> bool:
    """True when ``stream`` can render the block-art logo."""
    if os.environ.get("AUTHPROBE_ASCII", "").lower() in {"1", "plain", "ascii"}:
        return False
    enc = (getattr(stream, "encoding", None) or "").lower()
    if "utf" in enc:
        return True
    for var in ("LC_ALL", "LC_CTYPE", "LANG"):
        if "utf" in os.environ.get(var, "").lower():
            return True
    return False


def colorize(text: str, color: str, enabled: bool) -> str:
    return f"{color}{text}{RESET}" if enabled else text


def render_banner(
    *,
    unicode: bool = True,
    color: bool = False,
    tagline: str = "login auditor  //  brute-force by Sugar",
) -> str:
    """Return the full banner (logo + tagline) as a string."""
    logo = _BLOCK if unicode else _PLAIN
    width = max(len(row) for row in logo)

    lines = [colorize(row.ljust(width), LOGO_COLOR, color) for row in logo]
    pad = max(0, (width - len(tagline)) // 2)
    lines.append(colorize(" " * pad + tagline, TAGLINE_COLOR, color))
    lines.append("")
    return "\n".join(lines)


def render_panel(
    title: str,
    rows: Iterable[tuple[str, str]],
    *,
    color: bool = False,
    unicode: bool = True,
) -> str:
    """Return a bordered box: title header, then ``label : value`` rows."""
    rows = list(rows)
    if unicode:
        tl, tr, bl, br, h, v, mid_l, mid_r = "┌", "┐", "└", "┘", "─", "│", "├", "┤"
    else:
        tl, tr, bl, br, h, v, mid_l, mid_r = "+", "+", "+", "+", "-", "|", "+", "+"

    label_w = max((len(k) for k, _ in rows), default=0)
    body = [f"{k:<{label_w}} : {val}" for k, val in rows]
    inner = max([len(title)] + [len(b) for b in body]) + 2
    rule = h * inner

    out = [
        colorize(tl + rule + tr, DIM, color),
        colorize(v, DIM, color) + " " + colorize(title.ljust(inner - 1), BCYAN, color) + colorize(v, DIM, color),
        colorize(mid_l + rule + mid_r, DIM, color),
    ]
    for line in body:
        out.append(colorize(v, DIM, color) + " " + line.ljust(inner - 1) + colorize(v, DIM, color))
    out.append(colorize(bl + rule + br, DIM, color))
    return "\n".join(out)


def print_banner(
    stream: Optional[TextIO] = None,
    *,
    color: Optional[bool] = None,
    unicode: Optional[bool] = None,
    tagline: str = "login auditor  //  brute-force by Sugar",
) -> None:
    stream = stream or sys.stderr
    color = supports_color(stream) if color is None else color
    unicode = use_unicode(stream) if unicode is None else unicode
    stream.write(render_banner(unicode=unicode, color=color, tagline=tagline) + "\n")
    stream.flush()


def print_panel(
    title: str,
    rows: Iterable[tuple[str, str]],
    stream: Optional[TextIO] = None,
    *,
    color: Optional[bool] = None,
    unicode: Optional[bool] = None,
) -> None:
    stream = stream or sys.stderr
    color = supports_color(stream) if color is None else color
    unicode = use_unicode(stream) if unicode is None else unicode
    stream.write(render_panel(title, rows, color=color, unicode=unicode) + "\n")
    stream.flush()
