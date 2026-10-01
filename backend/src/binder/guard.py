"""Protects the local server against malicious web pages and other users of the machine.

The server only listens on the loopback interface, but a browser can still reach it:
- DNS rebinding: a rigged domain resolves to 127.0.0.1 and reads the API as if it were its
  origin. Defence: the Host header must designate the local machine;
- cross-site requests (CSRF): a form or a "simple" fetch from another site changes data.
  Defence: a request that changes something must come from the same origin;
- other accounts on the machine: the desktop app sets a random token per launch, passed once
  in the window URL and then kept in an HttpOnly cookie.
"""

import secrets
from collections.abc import Awaitable, Callable
from urllib.parse import urlencode, urlsplit

from fastapi import Request, Response
from fastapi.responses import JSONResponse, RedirectResponse

from binder import i18n

LOOPBACK = {"localhost", "127.0.0.1", "::1"}
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
COOKIE = "binder_session"
TOKEN_PARAM = "token"

CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'; "
    "object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
)

Handler = Callable[[Request], Awaitable[Response]]

T = i18n.catalog(
    "guard",
    {
        "bad_host": {"en": "Host not allowed", "fr": "Hôte non autorisé"},
        "cross_origin": {
            "en": "Request from another origin refused",
            "fr": "Requête d'une autre origine refusée",
        },
        "bad_token": {"en": "Invalid token", "fr": "Jeton invalide"},
        "no_session": {
            "en": "No session: restart Binder",
            "fr": "Session absente : relancez Binder",
        },
    },
)


def _hostname(host: str) -> str:
    """ "127.0.0.1:8765" → "127.0.0.1", "[::1]:8765" → "::1"."""
    return (urlsplit(f"//{host}").hostname or "").lower()


def _same_origin(request: Request) -> bool:
    origin = request.headers.get("origin")
    if origin is None:
        # No Origin: non-browser client, or same-origin navigation.
        return request.headers.get("sec-fetch-site", "same-origin") in {"same-origin", "none"}
    return origin.lower() == f"{request.url.scheme}://{request.headers.get('host', '')}".lower()


def _forbidden(detail: str, status: int = 403) -> Response:
    return JSONResponse({"detail": detail}, status_code=status)


def _harden(response: Response, path: str) -> Response:
    headers = response.headers
    headers.setdefault("X-Content-Type-Options", "nosniff")
    headers.setdefault("Referrer-Policy", "no-referrer")
    headers.setdefault("X-Frame-Options", "DENY")
    headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
    if path.startswith("/api/"):
        # A document opened in the browser (PDF) must not be able to run anything on the origin.
        headers.setdefault("Content-Security-Policy", "sandbox; default-src 'none'")
        headers.setdefault("Cache-Control", "no-store")
    else:
        headers.setdefault("Content-Security-Policy", CSP)
    return response


def middleware(
    token: Callable[[], str | None],
) -> Callable[[Request, Handler], Awaitable[Response]]:
    """HTTP middleware. `token` returns the current access token (None: no token)."""

    async def guard(request: Request, call_next: Handler) -> Response:
        path = request.url.path
        if _hostname(request.headers.get("host", "")) not in LOOPBACK:
            return _forbidden(T("bad_host"), 400)
        is_api = path.startswith("/api/") or path == "/api"
        if (
            is_api
            and not _same_origin(request)
            and (
                request.method not in SAFE_METHODS
                or request.headers.get("sec-fetch-site") == "cross-site"
            )
        ):
            return _forbidden(T("cross_origin"))

        expected = token()
        if expected:
            given = request.query_params.get(TOKEN_PARAM)
            if given is not None and not is_api:
                if not secrets.compare_digest(given, expected):
                    return _forbidden(T("bad_token"))
                # The token leaves the URL (history, logs) and moves to a cookie.
                rest = [(k, v) for k, v in request.query_params.multi_items() if k != TOKEN_PARAM]
                target = path + (f"?{urlencode(rest)}" if rest else "")
                redirect = RedirectResponse(target, status_code=303)
                redirect.set_cookie(COOKIE, expected, httponly=True, samesite="strict", path="/")
                return _harden(redirect, path)
            if is_api and not secrets.compare_digest(request.cookies.get(COOKIE, ""), expected):
                return _forbidden(T("no_session"), 401)

        return _harden(await call_next(request), path)

    return guard
