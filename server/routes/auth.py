"""OAuth + API-key authentication for the owner dashboard.

The dashboard uses a signed session cookie (see server.services.session)
instead of the per-request X-API-Key header. The API key is still useful
for self-hosters and CLI tools, so the login page also offers an API-key
form that mints the session cookie directly.

First-time OAuth logins auto-create an `owners` row keyed by the provider's
email. The dashboard then mints a single API key for the owner and shows
it ONCE on a "save your key" interstitial.
"""

import os
import secrets
from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from supabase import create_client
from supabase_auth.helpers import generate_pkce_challenge, generate_pkce_verifier

from server.config import get_supabase_client, logger, public_base_url
from server.services.session import make_session_cookie, owner_from_request
from server.services.storage import (
    get_owner_id_from_api_key,
    insert_owner_api_key,
)
from server.templates import render_site_page

router = APIRouter()


def _pending_oauth():
    from server.state import pending_oauth
    return pending_oauth


def _persist_owner(provider: str, email: str) -> str:
    """Create or look up an owner by email; return owner_id."""
    from server.services.storage import get_storage

    return get_storage().upsert_owner(email=email, provider=provider)


def _mint_api_key(owner_id: str) -> str:
    from server.config import OPERATOR_TOKEN_BYTES
    from server.services.security import hash_token

    api_key = secrets.token_urlsafe(OPERATOR_TOKEN_BYTES)
    insert_owner_api_key(owner_id, hash_token(api_key))
    return api_key


@router.get("/auth/login", response_class=HTMLResponse)
async def auth_login_page(request: Request):
    providers = []
    if os.getenv("GOOGLE_CLIENT_ID") and os.getenv("GOOGLE_CLIENT_SECRET"):
        providers.append("google")
    if os.getenv("GITHUB_CLIENT_ID") and os.getenv("GITHUB_CLIENT_SECRET"):
        providers.append("github")
    return render_site_page(
        "dashboard/login.html",
        base_url=public_base_url(request),
        providers=",".join(providers),
    )


@router.post("/auth/login")
async def auth_login_submit(request: Request):
    """API-key login path. Sets the session cookie and redirects to /dashboard."""
    form = await request.form()
    api_key = str(form.get("api_key") or "").strip()
    if not api_key:
        return PlainTextResponse("API key is required", status_code=400)
    owner_id = get_owner_id_from_api_key(api_key)
    if not owner_id:
        return PlainTextResponse("Invalid API key", status_code=401)
    response = RedirectResponse(url="/dashboard", status_code=303)
    response.headers.append("Set-Cookie", make_session_cookie(owner_id))
    return response


@router.get("/auth/oauth/start")
async def oauth_start(request: Request, provider: str):
    if provider not in {"google", "github"}:
        return PlainTextResponse("Unsupported provider", status_code=400)
    state = secrets.token_urlsafe(24)
    base_url = public_base_url(request)
    redirect_to = base_url + f"/auth/oauth/callback?state={state}"

    # If Supabase is not configured we can't do real OAuth. Fall back to a
    # developer-mode flow that creates a local owner immediately.
    if get_supabase_client() is None:
        owner_id = _persist_owner(provider, f"{provider}-local@peekaboo.local")
        api_key = _mint_api_key(owner_id)
        response = RedirectResponse(
            url=f"/auth/welcome?state={state}&key={api_key}", status_code=303
        )
        response.headers.append("Set-Cookie", make_session_cookie(owner_id))
        return response

    code_verifier = generate_pkce_verifier()
    _pending_oauth()[state] = {
        "code_verifier": code_verifier,
        "redirect_to": redirect_to,
    }
    code_challenge = generate_pkce_challenge(code_verifier)
    auth_url = (
        f"{os.environ['SUPABASE_URL'].rstrip('/')}/auth/v1/authorize"
        + "?"
        + urlencode({
            "provider": provider,
            "redirect_to": redirect_to,
            "code_challenge": code_challenge,
            "code_challenge_method": "s256",
        })
    )
    return RedirectResponse(url=auth_url, status_code=303)


@router.get("/auth/oauth/callback")
async def oauth_callback(request: Request):
    state = request.query_params.get("state")
    code = request.query_params.get("code")
    if not code:
        return PlainTextResponse("Missing authorization code", status_code=400)
    entry = _pending_oauth().get(state or "")
    if not entry or "code_verifier" not in entry:
        return PlainTextResponse("Unknown or expired login attempt", status_code=400)
    code_verifier = entry["code_verifier"]
    try:
        auth_client = create_client(
            os.environ["SUPABASE_URL"],
            os.environ["SUPABASE_SERVICE_ROLE_KEY"],
        )
        session = auth_client.auth.exchange_code_for_session({
            "auth_code": code,
            "code_verifier": code_verifier,
        })
        user = session.user
        email = getattr(user, "email", None) or f"{user.id}@unknown.local"
    except Exception as exc:
        logger.exception("OAuth token exchange failed")
        return PlainTextResponse(f"OAuth callback error: {exc}", status_code=400)

    owner_id = _persist_owner("google" if "google" in (state or "") else "github", email)
    api_key = _mint_api_key(owner_id)
    response = RedirectResponse(
        url=f"/auth/welcome?key={api_key}", status_code=303
    )
    response.headers.append("Set-Cookie", make_session_cookie(owner_id))
    return response


@router.get("/auth/welcome", response_class=HTMLResponse)
async def auth_welcome(request: Request):
    """Interstitial: shows the freshly-minted API key exactly once."""
    if owner_from_request(request) is None:
        return RedirectResponse(url="/auth/login", status_code=303)
    key = request.query_params.get("key", "")
    return render_site_page("dashboard/welcome.html", api_key=key)


@router.post("/auth/logout")
async def auth_logout(request: Request):
    from server.services.session import clear_session_cookie

    response = RedirectResponse(url="/auth/login", status_code=303)
    response.headers.append("Set-Cookie", clear_session_cookie())
    return response
