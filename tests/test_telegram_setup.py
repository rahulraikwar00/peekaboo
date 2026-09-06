"""Telegram webhook setup failure surfaces an actionable reason."""

import json

import pytest
from fastapi.testclient import TestClient

import server.main as main
from server.services import storage
from server.services.session import make_session_cookie


@pytest.fixture(autouse=True)
def reset_state():
    main.sites.clear()
    main.owner_api_keys.clear()
    main.site_creation_attempts.clear()
    main.conversations.clear()
    main.integrations.clear()
    main.pending_replies.clear()
    main.site_stats.clear()
    main.visitors.clear()
    main.visitor_info.clear()
    from server.state import limiter

    limiter.reset()


def create_site(client, api_key):
    resp = client.post(
        "/sites",
        content=json.dumps({"origins": ["https://example.test"]}),
        headers={"X-API-Key": api_key, "Content-Type": "application/json"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["site_id"]


def log_in(client, owner_id="owner"):
    header = make_session_cookie(owner_id)
    value = header.split(";", 1)[0].split("=", 1)[1]
    client.cookies.set("peekaboo_session", value)


def test_http_base_rejected_before_calling_telegram(monkeypatch):
    monkeypatch.setenv("PEEKABOO_SERVER_URL", "http://localhost:8000")
    with TestClient(main.app) as client:
        api_key = main.mint_owner_api_key("owner")
        site_id = create_site(client, api_key)
        log_in(client)

        from server.integrations.telegram import TelegramAdapter

        calls = []

        async def spy_set_webhook(self, url, secret):
            calls.append(url)
            return True

        monkeypatch.setattr(TelegramAdapter, "set_webhook", spy_set_webhook)

        r = client.post(
            f"/api/sites/{site_id}/integrations",
            json={"provider": "telegram", "token": "123:bot", "chat_id": "-100999"},
        )
        assert r.status_code == 400
        assert "HTTPS" in r.json()["error"]
        assert "PEEKABOO_SERVER_URL" in r.json()["error"]
        assert calls == []
        assert storage.list_integrations(site_id) == []


def test_webhook_error_hint_mapping():
    from server.integrations.telegram import webhook_error_hint

    assert "HTTPS" in webhook_error_hint("webhook URL must use HTTPS")
    assert "invalid" in webhook_error_hint("Not Found")
    assert "invalid" in webhook_error_hint("Unauthorized")
    assert "could not be validated" in webhook_error_hint("")
    assert webhook_error_hint(None)
    assert "rejected" in webhook_error_hint("some other error")