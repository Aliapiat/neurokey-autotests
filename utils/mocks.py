"""
Playwright-level API mocks for the Нейроключ backend.

Ported from `neurokey-react/e2e/mocks/api.ts`. Keep responses minimal and
deterministic so the authed UI renders without a real server.

Handlers are additive — register specific routes BEFORE the catch-all
(`mock_api_fallback`).
"""

from __future__ import annotations

import json
import re

from playwright.sync_api import Page, Route


API_URL_RE = re.compile(r"^https?://[^/]+/api/")


def mock_auth_endpoints(page: Page) -> None:
    def handler(route: Route) -> None:
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "token": "e2e-fake-token",
                    "refreshToken": "e2e-fake-refresh",
                    "id": "e2e-user-id",
                    "email": "e2e@example.com",
                    "role": "user",
                    "name": "E2E User",
                }
            ),
        )

    page.route(re.compile(r"/api/v1/auths/signin$"), handler)


def block_socket_io(page: Page) -> None:
    page.route(re.compile(r"/socket\.io/"), lambda route: route.fulfill(status=404, body=""))


def mock_api_fallback(page: Page) -> None:
    def handler(route: Route) -> None:
        method = route.request.method
        url = route.request.url

        if method == "OPTIONS":
            route.fulfill(status=204)
            return

        if re.search(r"/chat(/|$)", url, re.I) and method == "POST":
            route.fulfill(
                status=200,
                headers={"content-type": "text/event-stream"},
                body="data: [DONE]\n\n",
            )
            return

        if (
            re.search(r"/(models|chats|companies|users|memories|groups|group-chats)(/?\?|/?$)", url, re.I)
            and method == "GET"
        ):
            route.fulfill(
                status=200,
                content_type="application/json",
                body="[]",
            )
            return

        if re.search(r"/(balance|credits|tokens)(/|$|\?)", url, re.I):
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"credits_remaining": None, "organization_id": None}),
            )
            return

        route.fulfill(status=200, content_type="application/json", body="{}")

    page.route(API_URL_RE, handler)


def mock_all_api(page: Page) -> None:
    block_socket_io(page)
    mock_auth_endpoints(page)
    mock_api_fallback(page)
