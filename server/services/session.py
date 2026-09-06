"""Signed session cookie helpers for the owner dashboard.

The cookie carries the owner_id and is HMAC-signed with SIGNING_SECRET so
it cannot be forged. Cookies are httpOnly and SameSite=Lax. The session
itself is a no-op on the server: we resolve the owner purely from the
cookie payload.
"""

import base64
import hashlib
import hmac
import time

from server.config import SIGNING_SECRET

SESSION_COOKIE = "peekaboo_session"
SESSION_TTL_SECONDS = 60 * 60 * 24 * 14  # 14 days


def _sign(payload: str) -> str:
    return hmac.new(SIGNING_SECRET, payload.encode(), hashlib.sha256).hexdigest()


def make_session_cookie(owner_id: str) -> str:
    """Return a `Set-Cookie` header value for the given owner."""
    expires = int(time.time()) + SESSION_TTL_SECONDS
    raw = f"{owner_id}|{expires}"
    payload = base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")
    sig = _sign(payload)
    value = f"{payload}.{sig}"
    return (
        f"{SESSION_COOKIE}={value}; Path=/; HttpOnly; SameSite=Lax; "
        f"Max-Age={SESSION_TTL_SECONDS}"
    )


def clear_session_cookie() -> str:
    return f"{SESSION_COOKIE}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0"


def owner_from_request(request) -> str | None:
    """Return the owner_id carried by the session cookie, or None."""
    raw = request.cookies.get(SESSION_COOKIE)
    if not raw or "." not in raw:
        return None
    payload, sig = raw.rsplit(".", 1)
    if not hmac.compare_digest(sig, _sign(payload)):
        return None
    try:
        pad = "=" * (-len(payload) % 4)
        decoded = base64.urlsafe_b64decode((payload + pad).encode()).decode()
        owner_id, expires = decoded.split("|", 1)
        if int(expires) < time.time():
            return None
        return owner_id or None
    except Exception:
        return None
