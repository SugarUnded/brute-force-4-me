"""Tests for the TUI PanelState logic (pure, no curses)."""

import tempfile
from pathlib import Path

from authprobe.tui import PanelState, PRESET_CYCLE, CONCURRENCY_CYCLE, TIMEOUT_CYCLE


def test_panel_defaults_match_cli_defaults():
    s = PanelState()
    assert s.target == ""
    assert s.preset_index == 0
    assert s.user == ""
    assert s.wordlist == ""
    assert s.concurrency_index == 0          # unlimited
    assert s.timeout_index == 1              # 10s (TIMEOUT_CYCLE[1] == 10)
    assert s.success_status == "301,302,303,307,308"
    assert s.failure_body == ""
    assert s.success_body == ""


def test_preset_cycle_wraps():
    s = PanelState()
    # default generic-form is index 0
    assert PRESET_CYCLE[0].name == "generic-form"
    s.cycle_preset(1)
    assert s.preset_index == 1
    assert PRESET_CYCLE[1].name == "wp-login"
    # wrap forward
    for _ in range(len(PRESET_CYCLE) - 1):
        s.cycle_preset(1)
    assert s.preset_index == 0
    # wrap backward
    s.cycle_preset(-1)
    assert s.preset_index == len(PRESET_CYCLE) - 1


def test_concurrency_cycle_values():
    s = PanelState()
    assert CONCURRENCY_CYCLE[s.concurrency_index] == 0       # unlimited
    s.cycle_concurrency(1)
    assert CONCURRENCY_CYCLE[s.concurrency_index] == 500
    s.cycle_concurrency(1)
    assert CONCURRENCY_CYCLE[s.concurrency_index] == 200
    # a full turn of the wheel comes back to the same value
    before = s.concurrency_index
    for _ in range(len(CONCURRENCY_CYCLE)):
        s.cycle_concurrency(1)
    assert s.concurrency_index == before
    s.cycle_concurrency(-1)
    assert CONCURRENCY_CYCLE[s.concurrency_index] == 500


def test_timeout_cycle_values():
    s = PanelState()
    assert TIMEOUT_CYCLE[s.timeout_index] == 10
    s.cycle_timeout(1)
    assert TIMEOUT_CYCLE[s.timeout_index] == 20
    s.cycle_timeout(-1)
    assert TIMEOUT_CYCLE[s.timeout_index] == 10
    # wrap backward
    s.cycle_timeout(-1)
    assert TIMEOUT_CYCLE[s.timeout_index] == 30


def test_build_argv_produces_expected_cli_args():
    s = PanelState(
        target="https://example.test/login",
        preset_index=1,              # wp-login
        user="admin",
        wordlist="/home/user/words.txt",
        concurrency_index=2,         # 200
        timeout_index=2,             # 20
        success_status="302",
        failure_body="Invalid credentials",
        success_body="",
    )
    argv = s.build_argv()
    assert argv == [
        "https://example.test/login",
        "--preset", "wp-login",
        "--user", "admin",
        "-w", "/home/user/words.txt",
        "-c", "200",
        "-t", "20",
        "--success-status", "302",
        "--failure-body", "Invalid credentials",
    ]


def test_build_argv_omits_optional_empty_fields():
    s = PanelState(
        target="https://example.test/login",
        preset_index=0,
        user="admin",
        wordlist="/home/user/words.txt",
        concurrency_index=0,
        timeout_index=1,
        success_status="301,302,303,307,308",
        failure_body="",           # empty -> omitted
        success_body="",           # empty -> omitted
    )
    argv = s.build_argv()
    # no --failure-body, --success-body
    assert "--failure-body" not in argv
    assert "--success-body" not in argv


def test_validate_missing_target():
    s = PanelState(target="", wordlist="/tmp/words.txt")
    errs = s.validate()
    assert any("target" in e.lower() for e in errs)


def test_validate_missing_wordlist():
    s = PanelState(target="https://example.test", wordlist="")
    errs = s.validate()
    assert any("wordlist" in e.lower() for e in errs)


def test_validate_wordlist_not_found():
    s = PanelState(target="https://example.test", wordlist="/nonexistent/path/words.txt")
    errs = s.validate()
    assert any("not found" in e.lower() for e in errs)


def test_validate_wordlist_empty():
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        f.write("# only comments\n\n")
        path = f.name
    try:
        s = PanelState(target="https://example.test", wordlist=path)
        errs = s.validate()
        assert any("empty" in e.lower() for e in errs)
    finally:
        Path(path).unlink(missing_ok=True)


def test_validate_passes_for_valid_state():
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        f.write("pass1\npass2\n")
        path = f.name
    try:
        s = PanelState(target="https://example.test", wordlist=path)
        errs = s.validate()
        assert errs == []
    finally:
        Path(path).unlink(missing_ok=True)


def test_wordlist_expands_tilde():
    # validation should expand ~ in path
    import os
    home = os.path.expanduser("~")
    with tempfile.NamedTemporaryFile(mode="w", dir=home, delete=False) as f:
        f.write("p1\n")
        path = f.name
    try:
        tilde = path.replace(home, "~", 1)
        s = PanelState(target="https://example.test", wordlist=tilde)
        errs = s.validate()
        assert errs == []
    finally:
        Path(path).unlink(missing_ok=True)


def test_preset_selection_prefills_fields():
    s = PanelState()
    s.preset_index = PRESET_CYCLE.index(next(p for p in PRESET_CYCLE if p.name == "wp-login"))
    s.apply_preset()
    assert s.user_field == "log"
    assert s.pass_field == "pwd"
    # preset also sets recommended path for empty target
    # but target is separate; path is appended inside cli


def test_edit_text_field():
    s = PanelState(target="https://a")
    s.edit_field("target", "b")           # insert at cursor
    s.edit_field("target", "c")
    assert s.target == "https://abc"
    # backspace
    s.edit_field("target", "\x7f")        # DEL/Backspace
    assert s.target == "https://ab"
    s.edit_field("target", "\x01")        # home
    s.edit_field("target", "X")
    assert s.target == "Xhttps://ab"
    s.edit_field("target", "\x15")        # clear
    assert s.target == ""


def test_wordlist_count_skips_comments_and_blanks(tmp_path):
    from authprobe.tui import wordlist_count

    wl = tmp_path / "w.txt"
    wl.write_text("# comment\n\npass1\n  pass2  \n")
    assert wordlist_count(str(wl)) == 2
    assert wordlist_count(str(tmp_path / "missing.txt")) is None


def test_build_argv_parses_into_expected_config(tmp_path):
    from authprobe.cli import _build_config, build_parser

    wl = tmp_path / "w.txt"
    wl.write_text("a\nb\n")
    s = PanelState(
        target="https://example.test/login",
        preset_index=4,                  # json-api
        user="admin",
        wordlist=str(wl),
        concurrency_index=3,             # 50
        timeout_index=0,                 # 30
        success_status="200",
        success_body='"token"',
    )
    args = build_parser().parse_args(s.build_argv())
    cfg = _build_config(args)
    assert cfg.url == "https://example.test/login"
    assert cfg.concurrency == 50
    assert cfg.timeout == 30
    assert cfg.success_status == (200,)
    assert cfg.success_body_contains == '"token"'
    assert cfg.json_body is True