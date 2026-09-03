import os
from urllib.parse import urlsplit


def origin_allowed(origin: str, allowed_origins) -> bool:
    """Whether a browser Origin is permitted to post messages for a site.

    Allowed entries may be:
      - Exact origins: "https://example.test"
      - Subdomain wildcards: "https://*.example.test"
      - Dev hosts: "http://localhost:3000", "http://127.0.0.1:5000"

    NOTE (security): this is a convenience boundary, not a hard security control.
    `Origin` headers are spoofable by non-browser clients. Real abuse protection is
    provided by rate limiting, honeypots, and per-site quotas.
    """
    if not origin or not allowed_origins:
        return False
    if origin in ("null", "file://"):
        # file:// pages send an opaque Origin of "null"; only allow if configured.
        return any(entry and entry.startswith("file://") for entry in allowed_origins)
    parsed = urlsplit(origin)
    origin_host = parsed.netloc  # host[:port]
    if not origin_host:
        return False

    for entry in allowed_origins:
        if not entry:
            continue
        if _matches_entry(entry, parsed.scheme, origin_host):
            return True
    return False


def _matches_entry(entry: str, origin_scheme: str, origin_host: str) -> bool:
    entry = entry.strip().rstrip("/")
    if entry.startswith("file://"):
        return True
    scheme = None
    host = entry
    if "://" in entry:
        scheme, host = entry.split("://", 1)
    if scheme is not None and scheme != origin_scheme:
        return False
    host = host.rstrip("/")
    if host.startswith("*."):
        suffix = host[2:]
        return _is_valid_subdomain(origin_host, suffix)
    return origin_host == host


def _is_valid_subdomain(host: str, suffix: str) -> bool:
    # host must be suffix or a strict subdomain; also allow localhost suffix
    if host == suffix:
        return True
    if host.endswith("." + suffix):
        return True
    if suffix == "localhost":
        # allow any localhost:port in dev
        hostname = host.split(":")[0]
        return hostname in {"localhost", "127.0.0.1"}
    return False


def dev_mode() -> bool:
    return os.getenv("ENV", "development").lower() in {
        "development", "dev", "test",
    }
