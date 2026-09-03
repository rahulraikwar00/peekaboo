import json

import pytest
from fastapi.testclient import TestClient

from server import main
from server.routes.webhook_register import TelegramAdapter


@pytest.fixture(autouse=True)
def reset_state():
    main.sites.clear()
    main.owner_api_keys.clear()
    main.site_creation_attempts.clear()
    main.integrations.clear()
    main.conversations.clear()
    main.pending_replies.clear()
    main.site_stats.clear()
    main.telegram_updates.clear()


def make_site(client, api_key):
    return client.post(
        "/sites",
        content=json.dumps({}),
        headers={"X-API-Key": api_key, "Content-Type": "application/json"},
    ).json()["site_id"]


def test_register_webhook_requires_owner():
    with TestClient(main.app) as client:
        r = client.post("/sites/site_x/webhook/register", json={})
        assert r.status_code == 401


def test_register_webhook_validates_body(monkeypatch):
    async def _ok(self, url, secret):
        return True
    monkeypatch.setattr(TelegramAdapter, "set_webhook", _ok)
    with TestClient(main.app) as client:
        api_key = main.mint_owner_api_key("owner")
        site_id = make_site(client, api_key)
        r = client.post(
            f"/sites/{site_id}/webhook/register",
            json={"token": "", "chat_id": ""},
            headers={"X-API-Key": api_key},
        )
        assert r.status_code == 400


def test_register_webhook_requires_public_url(monkeypatch):
    monkeypatch.setenv("PUBLIC_BASE_URL", "")
    async def _ok(self, url, secret):
        return True
    monkeypatch.setattr(TelegramAdapter, "set_webhook", _ok)
    with TestClient(main.app) as client:
        api_key = main.mint_owner_api_key("owner")
        site_id = make_site(client, api_key)
        r = client.post(
            f"/sites/{site_id}/webhook/register",
            json={"token": "bot-token", "chat_id": "-100123"},
            headers={"X-API-Key": api_key},
        )
        assert r.status_code == 500


def test_register_webhook_is_forbidden_for_other_owner(monkeypatch):
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://example.test")
    async def _ok(self, url, secret):
        return True
    monkeypatch.setattr(TelegramAdapter, "set_webhook", _ok)
    with TestClient(main.app) as client:
        owner_key = main.mint_owner_api_key("owner-a")
        site_id = make_site(client, owner_key)
        other_key = main.mint_owner_api_key("owner-b")
        r = client.post(
            f"/sites/{site_id}/webhook/register",
            json={"token": "bot-token", "chat_id": "-100123"},
            headers={"X-API-Key": other_key},
        )
        assert r.status_code == 403


def test_register_webhook_success_and_rollback_on_failure(monkeypatch):
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://example.test")
    monkeypatch.setenv(
        "ENCRYPTION_KEY",
        "M0gU7ZvT1wQ2fVz1rT2gB3jZ4lH5kL6mN7oP8qR9sT0=",
    )
    with TestClient(main.app) as client:
        api_key = main.mint_owner_api_key("owner")
        site_id = make_site(client, api_key)

        calls = []

        async def fake_set_webhook(self, url, secret):
            calls.append((url, secret))
            return True

        monkeypatch.setattr(TelegramAdapter, "set_webhook", fake_set_webhook)
        r = client.post(
            f"/sites/{site_id}/webhook/register",
            json={"token": "123:bot", "chat_id": "-100999"},
            headers={"X-API-Key": api_key},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["configured"] is True
        assert body["webhook_url"] == "https://example.test/v1/telegram/webhook"
        assert calls and calls[0][1]  # secret token passed through

        # Failure rolls back the stored integration.
        async def fake_fail_set_webhook(self, url, secret):
            return False

        monkeypatch.setattr(
            TelegramAdapter, "set_webhook", fake_fail_set_webhook
        )
        r2 = client.post(
            f"/sites/{site_id}/webhook/register",
            json={"token": "123:bot", "chat_id": "-100998"},
            headers={"X-API-Key": api_key},
        )
        assert r2.status_code == 502
        from server.services import storage

        remaining = storage.list_integrations(site_id)
        assert len(remaining) == 1
        assert remaining[0]["destination_id"] == "-100999"
        # the failed registration was rolled back, so -100998 must be absent
        assert all(i["destination_id"] != "-100998" for i in remaining)