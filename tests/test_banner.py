import io

import pytest

from authprobe import banner


# --- logo geometry ----------------------------------------------------------

def test_block_logo_rows_are_equal_width():
    widths = {len(row) for row in banner._BLOCK}
    assert len(widths) == 1


def test_plain_logo_derives_from_block_and_is_aligned():
    assert len(banner._PLAIN) == len(banner._BLOCK)
    widths = {len(row) for row in banner._PLAIN}
    assert len(widths) == 1
    # plain fallback must not contain the box-drawing / block glyphs
    assert all(ch in "# " for row in banner._PLAIN for ch in row)


# --- render_banner ----------------------------------------------------------

def test_banner_has_six_logo_lines_and_tagline():
    text = banner.render_banner(unicode=True, color=False)
    lines = text.splitlines()
    assert lines[:6] == banner._BLOCK
    assert "Sugar" in text


def test_banner_plain_fallback_used_when_not_unicode():
    text = banner.render_banner(unicode=False, color=False)
    assert banner._PLAIN[0] in text
    assert banner._BLOCK[0] not in text


def test_banner_color_wraps_rows():
    colored = banner.render_banner(unicode=True, color=True)
    assert "\033[" in colored
    assert banner.RESET in colored


# --- render_panel -----------------------------------------------------------

def test_panel_ascii_borders():
    out = banner.render_panel("t", [("a", "1")], unicode=False, color=False)
    assert out.splitlines()[0].startswith("+")
    assert "| a : 1" in out


def test_panel_unicode_borders():
    out = banner.render_panel("t", [("a", "1")], unicode=True, color=False)
    assert out.splitlines()[0].startswith("┌")
    assert out.splitlines()[-1].startswith("└")


def test_panel_rows_are_padded_to_same_width():
    out = banner.render_panel("title", [("short", "1"), ("muchlonger", "2")], unicode=False)
    widths = {len(line) for line in out.splitlines()}
    assert len(widths) == 1


# --- environment switches ---------------------------------------------------

def test_colorize_respects_flag():
    assert banner.colorize("x", banner.BGREEN, True).startswith("\033[")
    assert banner.colorize("x", banner.BGREEN, False) == "x"


def test_no_color_env_disables_color(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.delenv("FORCE_COLOR", raising=False)
    monkeypatch.delenv("AUTHPROBE_FORCE_COLOR", raising=False)
    assert banner.supports_color(io.StringIO()) is False


def test_force_color_env_enables_color(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("FORCE_COLOR", "1")
    assert banner.supports_color(io.StringIO()) is True


def test_ascii_env_forces_plain_logo(monkeypatch):
    monkeypatch.setenv("AUTHPROBE_ASCII", "plain")
    assert banner.use_unicode(io.StringIO()) is False
