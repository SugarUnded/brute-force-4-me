"""Detection presets for common login flows.

A preset only describes *how a login behaves* - field names, the URL path, and
the signal that separates success from failure. It never carries a target host:
you supply that. Presets are starting points, and every value they set can be
overridden on the command line.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

__all__ = ["Preset", "PRESETS", "get_preset", "list_presets"]


@dataclass(frozen=True)
class Preset:
    name: str
    description: str
    path: Optional[str] = None
    user_field: str = "username"
    pass_field: str = "password"
    success_status: tuple[int, ...] = (301, 302, 303, 307, 308)
    success_body_contains: Optional[str] = None
    failure_body_contains: Optional[str] = None
    json_body: bool = False
    headers: dict[str, str] = field(default_factory=dict)

    def recommended_url(self) -> str:
        return f"https://<your-host>{self.path}" if self.path else "https://<your-host>/<login-path>"


PRESETS: dict[str, Preset] = {
    "generic-form": Preset(
        name="generic-form",
        description="Standard POST form; a redirect (3xx) means success.",
    ),
    "wp-login": Preset(
        name="wp-login",
        description="WordPress wp-login.php; failure renders a #login_error box.",
        path="/wp-login.php",
        user_field="log",
        pass_field="pwd",
        failure_body_contains="login_error",
    ),
    "joomla-admin": Preset(
        name="joomla-admin",
        description="Joomla administrator; failure says credentials do not match.",
        path="/administrator/index.php",
        user_field="username",
        pass_field="passwd",
        failure_body_contains="Username and password do not match",
    ),
    "django-admin": Preset(
        name="django-admin",
        description="Django admin; failure is the 'correct username and password' notice.",
        path="/admin/login/",
        user_field="username",
        pass_field="password",
        failure_body_contains="Please enter the correct",
    ),
    "json-api": Preset(
        name="json-api",
        description="JSON login endpoint; success response carries a token.",
        json_body=True,
        success_body_contains='"token"',
        headers={"Content-Type": "application/json"},
    ),
}


def get_preset(name: str) -> Preset:
    try:
        return PRESETS[name]
    except KeyError:
        valid = ", ".join(sorted(PRESETS))
        raise KeyError(f"unknown preset {name!r}; available: {valid}") from None


def list_presets() -> list[Preset]:
    return [PRESETS[k] for k in sorted(PRESETS)]
