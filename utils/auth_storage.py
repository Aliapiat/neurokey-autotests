"""
Helpers for working with Нейроключ sessionStorage auth state.

Frontend (`src/utils/authStorage.ts`) stores auth keys with a custom
base64-over-encodeURIComponent scheme:

    btoa(encodeURIComponent(value))

Keys used in sessionStorage:
    nk_token, nk_user, nk_password, nk_refresh
"""

from __future__ import annotations

import json
from playwright.sync_api import Page


def seed_fake_auth(page: Page, email: str = "e2e@example.com") -> None:
    """Seed sessionStorage with a fake token to bypass the PrivateRoute guard.

    Must be called BEFORE `page.goto(...)` — uses `add_init_script` so
    the token is present on first navigation.
    """
    user_payload = json.dumps(
        {
            "id": "e2e-user-id",
            "email": email,
            "role": "user",
            "name": "E2E User",
        }
    )
    script = (
        "(() => {\n"
        "  const encode = (v) => btoa(encodeURIComponent(v));\n"
        "  sessionStorage.setItem('nk_token', encode('e2e-fake-token'));\n"
        f"  sessionStorage.setItem('nk_user', encode({json.dumps(user_payload)}));\n"
        "})();"
    )
    page.add_init_script(script)


def read_token(page: Page) -> str | None:
    """Decode the real nk_token from sessionStorage (after real login)."""
    return page.evaluate(
        """() => {
            const raw = sessionStorage.getItem('nk_token');
            if (!raw) return null;
            try { return decodeURIComponent(atob(raw)); } catch { return null; }
        }"""
    )
