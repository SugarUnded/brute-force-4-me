"""Interactive panel for authprobe.

Everything above `run_tui()` is plain Python on purpose: the field cycles, the
validation and the argv builder are testable without a terminal. `curses` is
imported at module level with a graceful fallback on platforms without it
(Windows without `windows-curses`); the screen functions then use it freely,
and the CLI fallback (no TTY, or Windows without curses) prints the cheat-sheet
instead.

Modules
-------
- `tui.py`: pure `PanelState` logic, `run_tui()` (curses UI), colour helpers.
- `test_tui.py`: 20+ tests (preset cycles, concurrency/timeout cycles, edit,
  validation, argv build, logo geometry, wordlist count).
- `cli.py`: `main()` delegates to `_run_tui()` when called with no args on a TTY;
  otherwise prints the cheat-sheet.

Dependencies
------------
- ``httpx>=0.27`` (for the HTTP probe engine).
- ``pytest`` + ``pytest-asyncio`` only in ``dev`` extra (for the test suite).
- ``windows-curses`` (optional; on Windows it provides the `curses` package,
  otherwise the TUI silently falls back to the cheat-sheet).

"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

try:                                   # windows-curses makes this importable on Windows
    import curses as _curses
    _HAVE_CURSES = True
except ImportError:                    # Windows without windows-curses
    _curses = None                     # type: ignore[assignment]
    _HAVE_CURSES = False

from . import banner
from .presets import PRESETS, Preset

__all__ = [
    "PanelState",
    "TuiUnavailable",
    "run_tui",
    "logo_lines",
    "LOGO_WIDTH",
    "PRESET_ORDER",
    "PRESET_CYCLE",
    "CONCURRENCY_CYCLE",
    "TIMEOUT_CYCLE",
    "FIELD_ORDER",
]

LOGO_WIDTH = max(len(row) for row in banner._BLOCK)   # 41
TAGLINE = " login auditor  //  brute-force by Sugar"

# generic-form first, then the rest; the panel cycles in this order
PRESET_ORDER = ["generic-form", "wp-login", "joomla-admin", "django-admin", "json-api"]
PRESET_CYCLE: list[Preset] = [PRESETS[name] for name in PRESET_ORDER]

# 0 = one task per candidate (unlimited)
CONCURRENCY_CYCLE = [0, 500, 200, 50, 10, 1]
TIMEOUT_CYCLE = [30, 10, 20, 60]

DEFAULT_STATUS = "301,302,303,307,308"

FIELD_ORDER = [
    "target",
    "preset",
    "user_field",
    "pass_field",
    "user",
    "wordlist",
    "concurrency",
    "timeout",
    "success_status",
    "failure_body",
    "success_body",
]

TEXT_FIELDS = {"target", "user", "wordlist", "success_status", "failure_body", "success_body"}
CYCLE_FIELDS = {"preset", "concurrency", "timeout"}

try:                                   # some terminals may not support unicode block chars
    "█".encode("utf-8")
    _UNICODE_OK = True
except (UnicodeEncodeError, LookupError):
    _UNICODE_OK = False


class TuiUnavailable(RuntimeError):
    """Raised when curses is not importable on this platform."""


def wordlist_count(path: str) -> Optional[int]:
    """Number of usable lines in a wordlist, or None if it cannot be read."""
    try:
        text = Path(path).expanduser().read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    return sum(1 for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#"))


class PanelState:
    """Values behind the panel. No terminal involved."""

    def __init__(
        self,
        target: str = "",
        preset_index: int = 0,
        user: str = "",
        wordlist: str = "",
        concurrency_index: int = 0,
        timeout_index: int = 1,
        success_status: str = DEFAULT_STATUS,
        failure_body: str = "",
        success_body: str = "",
    ) -> None:
        self.target = target
        self.preset_index = preset_index
        self.user = user
        self.wordlist = wordlist
        self.concurrency_index = concurrency_index
        self.timeout_index = timeout_index
        self.success_status = success_status
        self.failure_body = failure_body
        self.success_body = success_body
        self._cursors: dict[str, int] = {}
        self._apply_preset_defaults()

    # --- presets ----------------------------------------------------------

    def _apply_preset_defaults(self) -> None:
        preset = PRESET_CYCLE[self.preset_index]
        self.user_field = preset.user_field
        self.pass_field = preset.pass_field

    def cycle_preset(self, direction: int) -> None:
        self.preset_index = (self.preset_index + direction) % len(PRESET_CYCLE)

    def cycle_concurrency(self, direction: int) -> None:
        self.concurrency_index = (self.concurrency_index + direction) % len(CONCURRENCY_CYCLE)

    def cycle_timeout(self, direction: int) -> None:
        self.timeout_index = (self.timeout_index + direction) % len(TIMEOUT_CYCLE)

    def apply_preset(self) -> None:
        """Fill the fields from the selected preset (editable afterwards)."""
        preset = PRESET_CYCLE[self.preset_index]
        self.user_field = preset.user_field
        self.pass_field = preset.pass_field
        self.success_status = ",".join(str(s) for s in preset.success_status)
        self.failure_body = preset.failure_body_contains or ""
        self.success_body = preset.success_body_contains or ""
        self._cursors.clear()

    @property
    def preset(self) -> Preset:
        return PRESET_CYCLE[self.preset_index]

    # --- text editing -----------------------------------------------------

    def edit_field(self, name: str, ch: str) -> None:
        """Apply one keystroke to a text field.

        Printable characters insert at the cursor; ``\\x7f`` / ``\\b`` deletes
        behind it; ``\\x01`` jumps to start; ``\\x05`` jumps to end; ``\\x15`` clears.
        """
        text = getattr(self, name) or ""
        cur = min(self._cursors.get(name, len(text)), len(text))

        if ch in ("\x7f", "\b"):
            if cur > 0:
                text = text[: cur - 1] + text[cur:]
                cur -= 1
        elif ch == "\x01":
            cur = 0
        elif ch == "\x05":
            cur = len(text)
        elif ch == "\x15":
            text, cur = "", 0
        elif len(ch) == 1 and ch.isprintable():
            text = text[:cur] + ch + text[cur:]
            cur += 1

        self._cursors[name] = cur
        setattr(self, name, text)

    def cursor(self, name: str) -> int:
        return min(self._cursors.get(name, len(getattr(self, name) or "")), len(getattr(self, name) or ""))

    # --- values, validation, argv ----------------------------------------

    def concurrency(self) -> int:
        return CONCURRENCY_CYCLE[self.concurrency_index]

    def timeout(self) -> int:
        return TIMEOUT_CYCLE[self.timeout_index]

    def display(self, key: str) -> str:
        if key == "preset":
            return self.preset.name
        if key == "concurrency":
            value = self.concurrency()
            return "unlimited" if value <= 0 else str(value)
        if key == "timeout":
            return f"{self.timeout()}s"
        return getattr(self, key) or ""

    def validate(self) -> list[str]:
        errs: list[str] = []
        if not self.target:
            errs.append("target URL is required")
        elif "://" not in self.target:
            errs.append("target needs a scheme (http:// or https://)")

        if not self.wordlist.strip():
            errs.append("wordlist file is required")
        else:
            path = Path(self.wordlist).expanduser()
            if not path.exists():
                errs.append(f"wordlist not found: {path}")
            else:
                count = wordlist_count(str(path))
                if count is None:
                    errs.append(f"cannot read wordlist: {path}")
                elif count == 0:
                    errs.append(f"wordlist is empty: {path}")
        return errs

    def build_argv(self) -> list[str]:
        argv: list[str] = []
        if self.target:
            argv.append(self.target)
        argv.extend(["--preset", self.preset.name])
        if self.user:
            argv.extend(["--user", self.user])
        if self.wordlist:
            argv.extend(["-w", str(Path(self.wordlist).expanduser())])
        if self.concurrency() > 0:
            argv.extend(["-c", str(self.concurrency())])
        if self.timeout() != 10:
            argv.extend(["-t", str(self.timeout())])
        if self.success_status and self.success_status != DEFAULT_STATUS:
            argv.extend(["--success-status", self.success_status])
        if self.failure_body:
            argv.extend(["--failure-body", self.failure_body])
        if self.success_body:
            argv.extend(["--success-body", self.success_body])
        return argv


# --- curses layer ---------------------------------------------------------

def _put(stdscr, y: int, x: int, text: str, attr: int = 0, width: Optional[int] = None) -> None:
    """Write a line, clipped, swallowing the bottom-right corner error."""
    try:
        if width is not None:
            text = text[: max(0, width - x - 1)]
        stdscr.addstr(y, x, text, attr)
    except curses.error:
        pass


def _put_label(stdscr, y: int, label: str, value: str, attr: int, width: int) -> None:
    _put(stdscr, y, 2, f"{label:<12}", curses.color_pair(1) | curses.A_BOLD, width)
    _put(stdscr, y, 14, value, attr, width)


def _stdout_supports_unicode() -> bool:
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    try:
        "█".encode(encoding)
        return True
    except (UnicodeEncodeError, LookupError):
        return False


def logo_lines(width: int, height: int, unicode_ok: bool = True) -> Optional[list[str]]:
    """The SUGAR logo rows when the terminal has room for them, else None."""
    if width < LOGO_WIDTH + 4 or height < 14:
        return None
    return banner._BLOCK if unicode_ok else banner._PLAIN


def _draw_logo(stdscr, width: int, height: int) -> int:
    """Draw the SUGAR logo + tagline at the top. Returns the next free row."""
    rows = logo_lines(width, height, _stdout_supports_unicode())
    attr = _curses.color_pair(1) | _curses.A_BOLD if _HAVE_CURSES else 0
    if rows is None:
        _put(stdscr, 0, 2, "authprobe", attr, width)
        return 2
    for i, line in enumerate(rows):
        _put(stdscr, i, 2, line, attr, width)
    _put(stdscr, len(rows), 2, TAGLINE, _curses.A_DIM, width) if _HAVE_CURSES else None
    return len(rows) + 2


def _config_screen(stdscr, state: Optional[PanelState] = None) -> Optional[PanelState]:
    _curses.curs_set(0)
    _curses.stdscr.keypad(True)
    _init_colors(_curses)

    if state is None:
        state = PanelState()
    focus = "target"
    errors: list[str] = []

    rows = [
        ("Target", "target"),
        ("Preset", "preset"),
        ("User field", "user_field"),
        ("Pass field", "pass_field"),
        ("User", "user"),
        ("Wordlist", "wordlist"),
        ("Concurrency", "concurrency"),
        ("Timeout", "timeout"),
        ("OK status", "success_status"),
        ("Fail body", "failure_body"),
        ("Hit body", "success_body"),
    ]
    keys = [k for _, k in rows]

    while True:
        h, w = _curses.stdscr.getmaxyx()
        _curses.stdscr.erase()
        top = _draw_logo(_curses.stdscr, w, h)

        for i, (label, key) in enumerate(rows):
            value = state.display(key)
            extra = ""

            if key == "wordlist" and value:
                count = wordlist_count(str(Path(value).expanduser()))
                extra = f"   {count} passwords" if count is not None else "   (not found)"

            if key in CYCLE_FIELDS:
                extra = "   ◄ ►"

            if key not in CYCLE_FIELDS and key in TEXT_FIELDS:
                cur = state.cursor(key)
                if key == focus:
                    value = value[:cur] + "▏" + value[cur:]

            attr = _curses.color_pair(2) if key == focus else _curses.A_NORMAL
            _put_label(_curses.stdscr, 2 + i, label, f"{value}{extra}", attr, w)

        y = 2 + len(rows) + 1
        if errors:
            for i, err in enumerate(errors[:3]):
                _put(_curses.stdscr, y + i, 2, "x " + err, _curses.color_pair(3) | _curses.A_BOLD, w)
            y += min(3, len(errors)) + 1

        _put(_curses.stdscr, y, 2, "[ Start ]", _curses.color_pair(4) | _curses.A_BOLD, w)
        _put(_curses.stdscr, y, 13, "[ Quit ]", _curses.A_DIM, w)

        footer = " Tab/↑↓ navega · ◄► gira · digite pra editar · Enter roda · Esc sai "
        _put(_curses.stdscr, h - 1, 0, footer, _curses.color_pair(5), w)

        _curses.stdscr.refresh()
        key = _curses.stdscr.getch()

        if key == _curses.KEY_RESIZE:
            continue
        if key in (27,):                      # Esc
            return None
        if key in (10, 13, _curses.KEY_ENTER):
            errors = state.validate()
            if not errors:
                return state
            continue
        if key == _curses.KEY_TAB:
            focus = keys[(keys.index(focus) + 1) % len(keys)]
            errors = []
            continue
        if key == _curses.KEY_BTAB:
            focus = keys[(keys.index(focus) - 1) % len(keys)]
            errors = []
            continue
        if key == _curses.KEY_UP:
            focus = keys[(keys.index(focus) - 1) % len(keys)]
            errors = []
            continue
        if key == _curses.KEY_DOWN:
            focus = keys[(keys.index(focus) + 1) % len(keys)]
            errors = []
            continue

        if focus in CYCLE_FIELDS:
            if key == _curses.KEY_RIGHT:
                getattr(state, f"cycle_{focus}")(1)
                if focus == "preset":
                    state.apply_preset()
            elif key == _curses.KEY_LEFT:
                getattr(state, f"cycle_{focus}")(-1)
                if focus == "preset":
                    state.apply_preset()
            elif key in (ord("q"), ord("Q")):
                return None
            continue

        # text field
        if key in (_curses.KEY_BACKSPACE, 127, 8):
            state.edit_field(focus, "\x7f")
        elif key == _curses.KEY_DC:
            state.edit_field(focus, "\x7f")
        elif key == _curses.KEY_HOME or key == 1:
            state.edit_field(focus, "\x01")
        elif key == _curses.KEY_END or key == 5:
            state.edit_field(focus, "\x05")
        elif key == 21:                        # ctrl-u
            state.edit_field(focus, "\x15")
        elif 32 <= key <= 126:
            state.edit_field(focus, chr(key))


def _progress_screen(stdscr, state: PanelState) -> Optional[list]:
    import asyncio
    import threading
    import time

    from .cli import _build_config, _collect_usernames, _read_lines, build_parser
    from .engine import Attempt, run_probe

    args = build_parser().parse_args(state.build_argv())
    cfg = _build_config(args)
    users = _collect_usernames(args)
    passwords = _read_lines(args.wordlist)
    total = len(users) * len(passwords)

    class Progress:
        def __init__(self) -> None:
            self.total = total
            self.done = 0
            self.hits: list[Attempt] = []
            self.last = ""
            self.started = time.monotonic()
            self.finished = False
            self.error = ""

        def record(self, attempt: Attempt) -> None:
            self.done += 1
            self.last = f"{attempt.username}:{attempt.password} -> {attempt.status}"
            if attempt.success:
                self.hits.append(attempt)

    prog = Progress()
    cancel = threading.Event()

    def worker() -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        cancel_ev = asyncio.Event()

        async def watch() -> None:
            while not cancel.is_set():
                await asyncio.sleep(0.05)
            cancel_ev.set()

        async def main() -> None:
            watcher = loop.create_task(watch())
            try:
                prog.hits = await run_probe(
                    cfg, users, passwords, on_attempt=prog.record, cancel_event=cancel_ev
                )
            except Exception as exc:  # surfaced on screen, not a traceback
                prog.error = f"{type(exc).__name__}: {exc}"
            finally:
                watcher.cancel()
                prog.finished = True

        loop.run_until_complete(main())
        loop.close()

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    _curses.curs_set(0)
    _curses.stdscr.nodelay(True)
    _curses.stdscr.keypad(True)
    _init_colors(_curses)

    while not prog.finished:
        ch = _curses.stdscr.getch()
        if ch in (27, ord("q"), ord("Q")):
            cancel.set()

        h, w = _curses.stdscr.getmaxyx()
        _curses.stdscr.erase()
        top = _draw_logo(_curses.stdscr, w, h)
        _put(_curses.stdscr, top, 2, cfg.url, _curses.A_DIM, w)
        base = top + 2

        elapsed = max(time.monotonic() - prog.started, 1e-6)
        rate = prog.done / elapsed
        bar_w = max(10, min(60, w - 30))
        filled = 0 if not prog.total else int(bar_w * prog.done / prog.total)
        bar = "#" * filled + "-" * (bar_w - filled)
        _put(_curses.stdscr, base, 2, f"[{bar}]", _curses.color_pair(4), w)
        _put(_curses.stdscr, base + 1, 2, f"{prog.done}/{prog.total}   {len(prog.hits)} hit(s)   {rate:.0f} req/s", 0, w)
        _put(_curses.stdscr, base + 2, 2, f"concurrency: {state.display('concurrency')}   timeout: {state.display('timeout')}", _curses.A_DIM, w)
        _put(_curses.stdscr, base + 4, 2, prog.last, _curses.A_DIM, w)

        for i, hit in enumerate(prog.hits[-5:]):
            _put(_curses.stdscr, base + 6 + i, 2, f"HIT  {hit.username}:{hit.password} -> {hit.status}",
                 _curses.color_pair(4) | _curses.A_BOLD, w)

        _put(_curses.stdscr, _curses.LINES - 1, 0, " Esc cancela ", _curses.color_pair(5), w)
        _curses.stdscr.refresh()
        _curses.napms(80)

    thread.join(timeout=1.0)
    _curses.stdscr.nodelay(False)

    if cancel.is_set():
        return None
    if prog.error:
        _curses.curs_set(0)
        _curses.stdscr.erase()
        _put(_curses.stdscr, 1, 2, "the run failed:", _curses.color_pair(5) | _curses.A_BOLD)
        _put(_curses.stdscr, 3, 2, prog.error[:500])
        _put(_curses.stdscr, 5, 2, "press any key", _curses.A_DIM)
        _curses.stdscr.refresh()
        _curses.stdscr.nodelay(False)
        _curses.stdscr.getch()
        return None
    return prog.hits


def _results_screen(stdscr, state: PanelState, hits: list) -> str:
    import json

    _curses.curs_set(0)
    _curses.stdscr.keypad(True)
    _init_colors(_curses)
    save_note = ""

    while True:
        h, w = _curses.stdscr.getmaxyx()
        _curses.stdscr.erase()
        top = _draw_logo(_curses.stdscr, w, h)
        _put(_curses.stdscr, top, 2, state.target, _curses.A_DIM, w)

        if hits:
            _put(_curses.stdscr, 2, 2, f"{len(hits)} valid credential(s)", _curses.color_pair(4) | _curses.A_BOLD, w)
            for i, hit in enumerate(hits[: _curses.LINES - 9]):
                _put(_curses.stdscr, 4 + i, 2, f"{hit.username}:{hit.password}   ({hit.status})", 0, w)
        else:
            _put(_curses.stdscr, 2, 2, "no valid credentials found", _curses.color_pair(5) | _curses.A_BOLD, w)

        if save_note:
            _put(_curses.stdscr, h - 3, 2, save_note, _curses.color_pair(4), w)
        _put(_curses.stdscr, _curses.LINES - 1, 0, " Enter roda de novo · s salva JSON · q sai ", _curses.color_pair(5), w)
        _curses.stdscr.refresh()

        key = _curses.stdscr.getch()
        if key in (10, 13, _curses.KEY_ENTER):
            return "again"
        if key in (27, ord("q"), ord("Q")):
            return "quit"
        if key in (ord("s"), ord("S")):
            path = "authprobe-results.json"
            try:
                with open(path, "w", encoding="utf-8") as fh:
                    json.dump(
                        [
                            {"username": x.username, "password": x.password, "status": x.status}
                            for x in hits
                        ],
                        fh,
                        indent=2,
                    )
                save_note = f"saved {len(hits)} result(s) to {path}"
            except OSError as exc:
                save_note = f"could not write {path}: {exc}"


# --- public entry point ---------------------------------------------------

def run_tui() -> int:
    """Open the panel, run the probe, print the results. Returns an exit code."""
    if not _HAVE_CURSES:
        raise TuiUnavailable("this platform does not have the curses module; "
                             "install windows-curses on Windows, or run on a real "
                             "terminal (Linux/macOS/Termux).")

    try:
        state = _curses.wrapper(_config_screen)
        if state is None:
            return 0

        while True:
            hits = _curses.wrapper(_progress_screen, state)
            if hits is None:
                state = _curses.wrapper(_config_screen, state)
                if state is None:
                    return 0
                continue

            action = _curses.wrapper(_results_screen, state, hits)
            if action != "again":
                return 0 if hits else 1
            state = _curses.wrapper(_config_screen, state)
            if state is None:
                return 0
    except KeyboardInterrupt:
        return 130


def _init_colors(curses) -> None:
    curses.start_color()
    try:
        curses.use_default_colors()
        bg = -1
    except curses.error:  # pragma: no cover - exotic terminals
        bg = curses.COLOR_BLACK
    curses.init_pair(1, curses.COLOR_CYAN, bg)    # focus
    curses.init_pair(2, curses.COLOR_WHITE, bg)   # label
    curses.init_pair(3, curses.COLOR_RED, bg)     # error
    curses.init_pair(4, curses.COLOR_GREEN, bg)    # ok / progress
    curses.init_pair(5, curses.COLOR_YELLOW, bg)   # dim / footer