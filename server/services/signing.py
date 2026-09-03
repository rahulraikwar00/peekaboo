import base64
import hashlib
import hmac
import time

from server.config import SIGNING_SECRET, VISITOR_TOKEN_TTL_SECONDS


def sign_visitor_token(site_id: str, visitor_id: str, ttl: int = VISITOR_TOKEN_TTL_SECONDS) -> str:
    """Mint a short-lived token authorizing subscribe access to a visitor's conversation."""
    expires = int(time.time()) + ttl
    payload = _encode_payload(site_id, visitor_id, expires)
    signature = _sign(payload)
    return f"{payload}.{signature}"


def verify_visitor_token(site_id: str, token: str) -> str | None:
    """Verify a visitor token and return the visitor_id it authorizes, or None.

    The token is bound to `site_id`, so a token minted for one site cannot be
    replayed against another. `visitor_id` is an identifier resolved from the
    signed token — never trusted from a raw client field.
    """
    if not token or "." not in token:
        return None
    payload, signature = token.rsplit(".", 1)
    expected = _sign(payload)
    if not _constant_time_eq(signature, expected):
        return None
    try:
        site_id_part, visitor_id, expires = _decode_payload(payload)
    except Exception:
        return None
    if site_id_part != site_id:
        return None
    if int(expires) < time.time():
        return None
    if not visitor_id:
        return None
    return visitor_id


def _sign(payload: str) -> str:
    return hmac.new(
        SIGNING_SECRET, payload.encode(), hashlib.sha256
    ).hexdigest()


def _constant_time_eq(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


def _encode_payload(site_id: str, visitor_id: str, expires: int) -> str:
    raw = f"{site_id}|{visitor_id}|{expires}"
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def _decode_payload(payload: str) -> tuple:
    pad = "=" * (-len(payload) % 4)
    raw = base64.urlsafe_b64decode((payload + pad).encode()).decode()
    return tuple(raw.split("|"))