"""Owner dashboard: web-only setup, channel management, snippet copy.

The dashboard is server-rendered HTML with one route per action. Every
action requires a valid session cookie (set on /auth/login or after OAuth).
The dashboard never returns a CLI token or expects an X-API-Key header —
it always uses the signed session cookie.
"""

import json
import os
import secrets

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse

from server.config import INTEGRATION_ID_BYTES, SITE_ID_BYTES, public_base_url
from server.integrations import router as adapter_router
from server.services import storage
from server.services.crypto import encrypt_credentials
from server.services.session import owner_from_request
from server.templates import render_site_page

router = APIRouter()

FLASH_MESSAGES = {
    "site_created": ("success", "Site created. Add a channel to start receiving messages."),
    "missing_telegram_fields": ("error", "Bot token and chat ID are required for Telegram."),
    "telegram_setup_failed": ("error", "Telegram webhook setup failed. Check your bot token."),
    "telegram_added": ("success", "Telegram webhook registered. Send a test message to verify."),
    "missing_discord_fields": ("error", "Bot token, channel ID, and public key are required for Discord."),
    "discord_added": ("success", "Discord channel added. Set your Interactions Endpoint URL in the developer portal."),
    "missing_slack_fields": ("error", "Bot token, signing secret, and channel ID are required for Slack."),
    "slack_added": ("success", "Slack channel added. Set your Event Subscriptions Request URL in the Slack app settings."),
    "channel_toggled": ("success", "Channel status updated."),
    "channel_removed": ("success", "Channel removed."),
}


def _require_session(request: Request):
    owner_id = owner_from_request(request)
    if not owner_id:
        return None
    return owner_id


def _site_or_404(owner_id: str, site_id: str):
    site = storage.get_site(site_id)
    if not site or site.get("owner_id") != owner_id:
        return None
    return site


def _render_sites_list(sites: list) -> str:
    if not sites:
        return '<p class="empty">No sites yet. Create one above.</p>'
    rows = []
    for s in sites:
        sid = s.get("site_id", "")
        rows.append(
            f'<a class="site-card" href="/dashboard/sites/{sid}">'
            f'<span class="site-id">{sid}</span>'
            f'<span class="arrow">&rarr;</span></a>'
        )
    return '<div class="site-list">' + "".join(rows) + "</div>"


def _render_channels_list(integrations: list, site_id: str) -> str:
    if not integrations:
        return '<p class="empty">No channels yet. Add one above.</p>'
    rows = []
    for ch in integrations:
        iid = ch.get("integration_id", "")
        provider = ch.get("provider", "unknown")
        enabled = ch.get("enabled", False)
        dest = ch.get("destination_id", "")
        status_class = "active" if enabled else "paused"
        status_label = "Active" if enabled else "Paused"
        toggle_val = "0" if enabled else "1"
        toggle_label = "Pause" if enabled else "Resume"
        dest_display = _mask_id(dest)
        rows.append(
            f'<div class="channel-row">'
            f'<span class="status-dot {status_class}" aria-label="{status_label}"></span>'
            f'<span class="provider">{provider}</span>'
            f'<span class="channel-dest">{dest_display}</span>'
            f'<span class="status">{status_label}</span>'
            f'<form method="post" action="/dashboard/sites/{site_id}/channels/{iid}/enable">'
            f'<input type="hidden" name="enabled" value="{toggle_val}" />'
            f'<button type="submit">{toggle_label}</button>'
            f'</form>'
            f'<form method="post" action="/dashboard/sites/{site_id}/channels/{iid}/remove">'
            f'<button type="submit" class="danger" onclick="return confirm(\'Remove this channel?\')">Remove</button>'
            f'</form>'
            f'</div>'
        )
    return '<div class="channel-list">' + "".join(rows) + "</div>"


def _mask_id(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return value
    return value[:4] + "..." + value[-4:]


def _render_flash(flash_code: str) -> str:
    if not flash_code:
        return ""
    entry = FLASH_MESSAGES.get(flash_code)
    if not entry:
        return f'<div class="flash info">{flash_code}</div>'
    level, msg = entry
    return f'<div class="flash {level}">{msg}</div>'


def _render_stats(stats: dict) -> str:
    if not stats:
        return ""
    msgs = stats.get("messages_received", 0)
    replies = stats.get("replies_sent", 0)
    last = stats.get("last_message_at")
    last_display = _format_time(last) if last else "Never"
    return (
        f'<div class="stats-row">'
        f'<div class="stat"><span class="stat-value">{msgs}</span><span class="stat-label">Messages</span></div>'
        f'<div class="stat"><span class="stat-value">{replies}</span><span class="stat-label">Replies</span></div>'
        f'<div class="stat"><span class="stat-value">{last_display}</span><span class="stat-label">Last message</span></div>'
        f'</div>'
    )


def _format_time(iso_str: str) -> str:
    from datetime import datetime, timezone
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        diff = now - dt
        if diff.total_seconds() < 60:
            return "Just now"
        if diff.total_seconds() < 3600:
            return f"{int(diff.total_seconds() // 60)}m ago"
        if diff.total_seconds() < 86400:
            return f"{int(diff.total_seconds() // 3600)}h ago"
        return dt.strftime("%b %d")
    except Exception:
        return str(iso_str)[:10]


@router.get("/", response_class=HTMLResponse)
async def root_redirect(request: Request):
    if _require_session(request):
        return RedirectResponse(url="/dashboard", status_code=303)
    return RedirectResponse(url="/auth/login", status_code=303)


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_index(request: Request):
    owner_id = _require_session(request)
    if not owner_id:
        return RedirectResponse(url="/auth/login", status_code=303)
    sites = storage.list_sites(owner_id)
    return render_site_page(
        "dashboard/index.html",
        sites_list=_render_sites_list(sites),
    )


@router.post("/dashboard/sites")
async def dashboard_create_site(request: Request):
    owner_id = _require_session(request)
    if not owner_id:
        return RedirectResponse(url="/auth/login", status_code=303)
    form = await request.form()
    origins_raw = str(form.get("origins") or "").strip()
    origins = [o.strip() for o in origins_raw.replace("\n", ",").split(",") if o.strip()]
    site_id = "site_" + secrets.token_urlsafe(SITE_ID_BYTES)
    storage.insert_site({
        "site_id": site_id,
        "owner_id": owner_id,
        "allowed_origins": origins or None,
    })
    return RedirectResponse(url=f"/dashboard/sites/{site_id}", status_code=303)


@router.get("/dashboard/sites/{site_id}", response_class=HTMLResponse)
async def dashboard_site_detail(site_id: str, request: Request):
    owner_id = _require_session(request)
    if not owner_id:
        return RedirectResponse(url="/auth/login", status_code=303)
    site = _site_or_404(owner_id, site_id)
    if not site:
        return PlainTextResponse("Site not found", status_code=404)
    integrations = storage.list_integrations(site_id)
    stats = storage.get_site_stats(site_id)
    base = public_base_url(request)
    snippet = (
        f'<script src="{base}/widget/pboo.bundle.js" '
        f'data-site="{site_id}"></script>'
    )
    flash_code = request.query_params.get("flash", "")
    stats_html = _render_stats(stats)
    return render_site_page(
        "dashboard/site.html",
        site_id=site_id,
        channels_list=_render_channels_list(integrations, site_id),
        snippet=snippet,
        base_url=base,
        flash=_render_flash(flash_code),
        stats=stats_html,
    )


@router.post("/dashboard/sites/{site_id}/channels")
async def dashboard_add_channel(site_id: str, request: Request):
    owner_id = _require_session(request)
    if not owner_id:
        return RedirectResponse(url="/auth/login", status_code=303)
    site = _site_or_404(owner_id, site_id)
    if not site:
        return PlainTextResponse("Site not found", status_code=404)

    form = await request.form()
    provider = str(form.get("provider") or "").strip().lower()
    if provider not in adapter_router.ADAPTERS:
        return PlainTextResponse("Unsupported provider", status_code=400)

    if provider == "telegram":
        token = str(form.get("bot_token") or "").strip()
        chat_id = str(form.get("chat_id") or "").strip()
        if not token or not chat_id:
            return RedirectResponse(
                url=f"/dashboard/sites/{site_id}?flash=missing_telegram_fields",
                status_code=303,
            )
        base = public_base_url(request)
        integration_id = "int_" + secrets.token_urlsafe(INTEGRATION_ID_BYTES)
        webhook_secret = secrets.token_urlsafe(32)
        record = {
            "integration_id": integration_id,
            "site_id": site_id,
            "provider": "telegram",
            "destination_id": chat_id,
            "credentials": encrypt_credentials(token),
            "webhook_secret": webhook_secret,
            "enabled": True,
        }
        adapter = adapter_router.build_adapter(record)
        configured = await adapter.set_webhook(
            f"{base}/v1/telegram/webhook", webhook_secret
        )
        if not configured:
            return RedirectResponse(
                url=f"/dashboard/sites/{site_id}?flash=telegram_setup_failed",
                status_code=303,
            )
        storage.insert_integration(record)
        return RedirectResponse(url=f"/dashboard/sites/{site_id}?flash=telegram_added", status_code=303)

    if provider == "discord":
        bot_token = str(form.get("bot_token") or "").strip()
        channel_id = str(form.get("channel_id") or "").strip()
        public_key = str(form.get("public_key") or "").strip()
        if not bot_token or not channel_id or not public_key:
            return RedirectResponse(
                url=f"/dashboard/sites/{site_id}?flash=missing_discord_fields",
                status_code=303,
            )
        creds = encrypt_credentials(json.dumps({
            "bot_token": bot_token,
            "public_key": public_key,
        }))
        integration_id = "int_" + secrets.token_urlsafe(INTEGRATION_ID_BYTES)
        base = public_base_url(request)
        record = {
            "integration_id": integration_id,
            "site_id": site_id,
            "provider": "discord",
            "destination_id": channel_id,
            "credentials": creds,
            "webhook_secret": secrets.token_urlsafe(32),
            "enabled": True,
        }
        storage.insert_integration(record)
        return RedirectResponse(
            url=f"/dashboard/sites/{site_id}?flash=discord_added",
            status_code=303,
        )

    if provider == "slack":
        bot_token = str(form.get("bot_token") or "").strip()
        signing_secret = str(form.get("signing_secret") or "").strip()
        channel_id = str(form.get("channel_id") or "").strip()
        if not bot_token or not signing_secret or not channel_id:
            return RedirectResponse(
                url=f"/dashboard/sites/{site_id}?flash=missing_slack_fields",
                status_code=303,
            )
        creds = encrypt_credentials(json.dumps({
            "bot_token": bot_token,
            "signing_secret": signing_secret,
            "channel_id": channel_id,
        }))
        integration_id = "int_" + secrets.token_urlsafe(INTEGRATION_ID_BYTES)
        record = {
            "integration_id": integration_id,
            "site_id": site_id,
            "provider": "slack",
            "destination_id": channel_id,
            "credentials": creds,
            "webhook_secret": "",
            "enabled": True,
        }
        storage.insert_integration(record)
        return RedirectResponse(
            url=f"/dashboard/sites/{site_id}?flash=slack_added",
            status_code=303,
        )

    return PlainTextResponse("Unsupported provider", status_code=400)


@router.post("/dashboard/sites/{site_id}/channels/{integration_id}/enable")
async def dashboard_toggle_channel(site_id: str, integration_id: str, request: Request):
    owner_id = _require_session(request)
    if not owner_id:
        return RedirectResponse(url="/auth/login", status_code=303)
    site = _site_or_404(owner_id, site_id)
    if not site:
        return PlainTextResponse("Site not found", status_code=404)
    form = await request.form()
    enabled = str(form.get("enabled") or "").lower() in {"1", "true", "on"}
    storage.update_integration(site_id, integration_id, {"enabled": enabled})
    return RedirectResponse(url=f"/dashboard/sites/{site_id}?flash=channel_toggled", status_code=303)


@router.post("/dashboard/sites/{site_id}/channels/{integration_id}/remove")
async def dashboard_remove_channel(site_id: str, integration_id: str, request: Request):
    owner_id = _require_session(request)
    if not owner_id:
        return RedirectResponse(url="/auth/login", status_code=303)
    site = _site_or_404(owner_id, site_id)
    if not site:
        return PlainTextResponse("Site not found", status_code=404)
    storage.delete_integration(site_id, integration_id)
    return RedirectResponse(url=f"/dashboard/sites/{site_id}?flash=channel_removed", status_code=303)
