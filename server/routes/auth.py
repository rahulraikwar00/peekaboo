import os
import secrets
from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from supabase import create_client
from supabase_auth.helpers import generate_pkce_challenge, generate_pkce_verifier

from server.config import get_supabase_client, logger, public_base_url
from server.services.auth import mint_owner_api_key, revoke_owner_api_key
from server.state import pending_oauth
from server.templates import render_site_page

router = APIRouter()


@router.get("/oauth/consent", response_class=HTMLResponse)
async def oauth_consent_page(request: Request):
    base_url = public_base_url(request)
    provider = request.query_params.get("provider", "")
    state = request.query_params.get("state", "")
    redirect_to = request.query_params.get("redirect_to", "")

    start_url = f"{base_url}/auth/oauth/start?provider={provider or 'github'}"
    if state:
        start_url += f"&state={state}"
    if redirect_to:
        start_url += f"&redirect_to={redirect_to}"

    provider_label = {"google": "Google", "github": "GitHub"}.get(
        provider, "your account"
    )
    return render_site_page(
        "oauthConsent.html",
        provider_label=provider_label,
        start_url=start_url,
    )


@router.get("/auth/login", response_class=HTMLResponse)
async def auth_login_page():
    return render_site_page("login.html", base_url=os.getenv("PUBLIC_BASE_URL", ""))


@router.get("/auth/oauth/start")
async def oauth_start(request: Request, provider: str):
    if provider not in {"google", "github"}:
        return PlainTextResponse("Unsupported provider", status_code=400)

    state = request.query_params.get("state") or secrets.token_urlsafe(24)
    base_url = public_base_url(request, request.query_params.get("server_url"))
    redirect_to = base_url + f"/auth/oauth/callback?state={state}"
    db = get_supabase_client()
    if db is None:
        pending_oauth[state] = {
            "api_key": mint_owner_api_key("local-owner"),
            "redirect_to": redirect_to,
        }
        return {"url": f"{base_url}/auth/success", "state": state}

    existing = pending_oauth.get(state)
    if existing and "code_verifier" in existing:
        code_verifier = existing["code_verifier"]
    else:
        code_verifier = generate_pkce_verifier()
        pending_oauth[state] = {
            "api_key": None,
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
    return {"url": auth_url, "state": state}


@router.get("/auth/oauth/callback")
async def oauth_callback(request: Request):
    db = get_supabase_client()
    if db is None:
        return PlainTextResponse("Server not configured", status_code=500)
    state = request.query_params.get("state")
    code = request.query_params.get("code")
    if not code:
        return PlainTextResponse("Missing authorization code", status_code=400)
    entry = pending_oauth.get(state or "")
    if not entry:
        return PlainTextResponse("Unknown or expired login attempt", status_code=400)
    if "code_verifier" not in entry:
        return PlainTextResponse("Code verifier missing", status_code=400)
    code_verifier = entry["code_verifier"]
    redirect_to = entry.get("redirect_to") or (
        public_base_url(request) + f"/auth/oauth/callback?state={state}"
    )
    try:
        # 1. Exchange code using an isolated auth-only client
        auth_client = create_client(
            os.environ["SUPABASE_URL"],
            os.environ["SUPABASE_ANON_KEY"],
        )
        session = auth_client.auth.exchange_code_for_session({
            "auth_code": code,
            "code_verifier": code_verifier,
        })
        owner_id = session.user.id
    except Exception as exc:
        logger.exception("OAuth token exchange failed")
        return PlainTextResponse(f"OAuth callback error: {exc}", status_code=400)

    try:
        # 2. Mint the API key using a separate dedicated service client
        # that has never touched user sessions or .auth.exchange_code_for_session()
        db_client = create_client(
            os.environ["SUPABASE_URL"],
            os.environ["SUPABASE_SERVICE_ROLE_KEY"],
        )
        api_key = mint_owner_api_key(owner_id, db_client=db_client)
    except Exception as exc:
        logger.exception(
            "Failed to mint owner API key for owner_id=%r", owner_id)
        return PlainTextResponse(
            f"Login failed: could not save account ({exc})", status_code=500
        )

    if state and state in pending_oauth:
        pending_oauth[state]["api_key"] = api_key

    return RedirectResponse(url="/auth/success", status_code=303)


@router.get("/auth/success", response_class=HTMLResponse)
async def auth_success_page():
    return render_site_page("returnToCli.html")


@router.get("/auth/cli/status")
async def auth_cli_status(request: Request):
    state = request.query_params.get("state")
    if not state or state not in pending_oauth:
        return PlainTextResponse("Invalid state", status_code=404)
    api_key = pending_oauth[state].get("api_key")
    if api_key:
        del pending_oauth[state]
        return {"owner_api_key": api_key}
    return {"pending": True}


@router.post("/auth/logout")
async def auth_logout(request: Request):
    api_key = request.headers.get("X-API-Key")
    if not api_key:
        return PlainTextResponse("Missing API key", status_code=401)
    if not revoke_owner_api_key(api_key):
        return PlainTextResponse("API key not found", status_code=404)
    return {"status": "revoked"}
