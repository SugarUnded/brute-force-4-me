import asyncio
import json

import httpx
import pytest

from authprobe import PRESETS, get_preset, list_presets
from authprobe.cli import _apply_preset_path, _build_config, build_parser
from authprobe.engine import ProbeConfig, run_probe


def test_all_expected_presets_registered():
    assert set(PRESETS) == {
        "generic-form",
        "wp-login",
        "joomla-admin",
        "django-admin",
        "json-api",
    }


def test_get_preset_unknown_raises_with_hint():
    with pytest.raises(KeyError) as exc:
        get_preset("nope")
    assert "available" in str(exc.value)


def test_list_presets_sorted():
    names = [p.name for p in list_presets()]
    assert names == sorted(names)


def test_wp_preset_fields_and_path():
    p = get_preset("wp-login")
    assert (p.user_field, p.pass_field) == ("log", "pwd")
    assert p.path == "/wp-login.php"
    assert p.failure_body_contains == "login_error"


@pytest.mark.parametrize(
    "url,path,expected",
    [
        ("https://h", "/wp-login.php", "https://h/wp-login.php"),
        ("https://h/", "/wp-login.php", "https://h/wp-login.php"),
        ("https://h/custom/login", "/wp-login.php", "https://h/custom/login"),
    ],
)
def test_apply_preset_path(url, path, expected):
    assert _apply_preset_path(url, path) == expected


def test_build_config_from_preset_then_overridden_by_flags():
    args = build_parser().parse_args(
        ["https://h", "--preset", "wp-login", "-w", "x.txt", "--user-field", "custom_user"]
    )
    cfg = _build_config(args)
    assert cfg.url == "https://h/wp-login.php"
    assert cfg.username_field == "custom_user"  # explicit flag wins
    assert cfg.password_field == "pwd"          # preset wins over default
    assert cfg.failure_body_contains == "login_error"


def test_build_config_json_api_preset_sets_json_body():
    args = build_parser().parse_args(["https://h/api/login", "--preset", "json-api", "-w", "x.txt"])
    cfg = _build_config(args)
    assert cfg.json_body is True
    assert cfg.success_body_contains == '"token"'
    assert cfg.headers.get("Content-Type") == "application/json"


def test_json_body_is_sent_as_json():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["content_type"] = request.headers.get("content-type")
        seen["body"] = json.loads(request.content.decode())
        if seen["body"].get("password") == "hit":
            return httpx.Response(200, json={"token": "abc"})
        return httpx.Response(401, json={"error": "bad"})

    cfg = ProbeConfig(
        url="http://t/api/login",
        json_body=True,
        success_body_contains='"token"',
        concurrency=1,
    )
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=False)
    try:
        found = asyncio.run(run_probe(cfg, ["admin"], ["nope", "hit"], client=client))
    finally:
        asyncio.run(client.aclose())

    assert [a.password for a in found] == ["hit"]
    assert seen["content_type"].startswith("application/json")
    assert seen["body"] == {"username": "admin", "password": "hit"}
