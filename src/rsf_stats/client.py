"""Authenticated HTTP client for rallysimfans.hu.

Login is a plain form POST to `account2_login.php`:
- reCAPTCHA is disabled server-side (`reCAPTCHA_ENABLED_LOGIN_js = false`),
  so the `token` field can stay empty.
- a CSRF token (`token_account_login`) must be read from the login page and
  sent back in the POST body.
"""

from __future__ import annotations

import re

import httpx

from .config import BASE_URL, USER_AGENT, Settings
from .log import log_response, logger

LOGIN_PAGE = f"{BASE_URL}/account2.php?centerbox=bejelentkezes2"
LOGIN_ACTION = f"{BASE_URL}/account2_login.php"

# <input ... name="token_account_login" value="...">
_CSRF_RE = re.compile(r'name="token_account_login"\s+value="([0-9a-fA-F]+)"', re.IGNORECASE)


class LoginError(RuntimeError):
    """Login failed (wrong credentials, changed layout, or site down)."""


def _extract_csrf(html: str) -> str:
    match = _CSRF_RE.search(html)
    if not match:
        raise LoginError(
            "CSRF token 'token_account_login' not found on the login page (site layout changed?)."
        )
    return match.group(1)


def login(settings: Settings, *, timeout: float = 30.0) -> httpx.Client:
    """Open an authenticated session and return a ready-to-use `httpx.Client`.

    The client keeps the session cookies; the caller is responsible for closing
    it (preferably via try/finally).
    """
    logger.info("login: authenticating as %s", settings.username)
    client = httpx.Client(
        base_url=BASE_URL,
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
        timeout=timeout,
        event_hooks={"response": [log_response]},
    )

    try:
        page = client.get(LOGIN_PAGE)
        page.raise_for_status()
        csrf = _extract_csrf(page.text)

        payload = {
            "token_account_login": csrf,
            "login": "login",
            "token": "",  # reCAPTCHA disabled server-side
            "l_username": settings.username,
            "l_pass": settings.password,
            "l_remember_me": "1",
        }
        resp = client.post(LOGIN_ACTION, data=payload)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        client.close()
        logger.warning("login: network error (%s)", exc)
        raise LoginError(f"Network error during login: {exc}") from exc

    if not _is_logged_in(client):
        client.close()
        logger.warning("login: rejected for %s", settings.username)
        raise LoginError(
            "Login rejected: check RSF_USERNAME / RSF_PASSWORD (or unverified / locked account)."
        )
    logger.info("login: success")
    return client


def _is_logged_in(client: httpx.Client) -> bool:
    """Check whether the session is authenticated.

    Once logged in, the site shows a 'Profile' menu containing the links
    'Edit account' (`account2.php?centerbox=account_edit`) and 'Stats'
    (`usersstats.php?user_stats=<id>`), both absent when anonymous.
    """
    resp = client.get(f"{BASE_URL}/hotlap.php?centerbox=recent")
    if resp.status_code != 200:
        return False
    html = resp.text
    return "centerbox=account_edit" in html and "usersstats.php?user_stats=" in html
