import json

import pytest
from fastapi.testclient import TestClient

from server import main
from server.services import storage


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


def make_site_with_integration(client):
    api_key = main.mint_owner_api_key("owner")
    payload = json.dumps({"origins": ["https://example.test"]}).encode()
    resp = client.post(
        "/sites",
        content=payload,
        headers={"X-API-Key": api_key, "Content-Type": "application/json"},
    )
    site_id = resp.json()["site_id"]

    # Insert a telegram integration directly (owner-route tested elsewhere).
    storage.insert_integration({
        "site_id": site_id,
        "provider": "telegram",
        "destination_id": "1000",
        "credentials": "enc-key",
        "webhook_secret": "secret-abc",
        "enabled": True,
    })
    return site_id


def test_webhook_requires_secret_token():
    with TestClient(main.app) as client:
        r = client.post("/v1/telegram/webhook", json={})
        assert r.status_code == 401


def test_webhook_rejects_unknown_secret():
    with TestClient(main.app) as client:
        make_site_with_integration(client)
        r = client.post(
            "/v1/telegram/webhook",
            json={"update_id": 1, "message": {}},
            headers={"X-Telegram-Bot-Api-Secret-Token": "wrong-secret"},
        )
        assert r.status_code == 401


def test_webhook_ignores_unknown_thread():
    with TestClient(main.app) as client:
        make_site_with_integration(client)
        r = client.post(
            "/v1/telegram/webhook",
            json={
                "update_id": 1,
                "message": {
                    "message_thread_id": 9999,
                    "text": "hi owner",
                },
            },
            headers={"X-Telegram-Bot-Api-Secret-Token": "secret-abc"},
        )
        assert r.status_code == 200


def test_webhook_ignores_non_message_updates():
    with TestClient(main.app) as client:
        make_site_with_integration(client)
        r = client.post(
            "/v1/telegram/webhook",
            json={"update_id": 1, "edited_message": {"text": "x"}},
            headers={"X-Telegram-Bot-Api-Secret-Token": "secret-abc"},
        )
        assert r.status_code == 200


def test_webhook_delivers_reply_to_live_visitor():
    with TestClient(main.app) as client:
        site_id = make_site_with_integration(client)
        with client.websocket_connect(
            f"/ws/visitor/{site_id}",
            headers={"origin": "https://example.test"},
        ) as visitor:
            visitor.send_text(json.dumps({
                "type": "visitor.connected",
                "visitor_id": "v-live",
            }))
            # Get the conversation_id assigned to this visitor.
            conv = storage.get_or_create_conversation(site_id, "v-live")
            storage.update_conversation_thread(conv["conversation_id"], "42")

            r = client.post(
                "/v1/telegram/webhook",
                json={
                    "update_id": 1,
                    "message": {
                        "message_thread_id": 42,
                        "text": "Sure, email me.",
                    },
                },
                headers={"X-Telegram-Bot-Api-Secret-Token": "secret-abc"},
            )
            assert r.status_code == 200

            event = json.loads(visitor.receive_text())
            assert event["type"] == "owner.message"
            assert event["message"] == "Sure, email me."


def test_webhook_enqueues_reply_when_visitor_offline_then_delivers(monkeypatch):
    monkeypatch.setenv(
        "ENCRYPTION_KEY",
        "M0gU7ZvT1wQ2fVz1rT2gB3jZ4lH5kL6mN7oP8qR9sT0=",
    )
    with TestClient(main.app) as client:
        site_id = make_site_with_integration(client)
        conv = storage.get_or_create_conversation(site_id, "v-offline")
        storage.update_conversation_thread(conv["conversation_id"], "7")

        # owner replies while visitor is offline
        r = client.post(
            "/v1/telegram/webhook",
            json={
                "update_id": 1,
                "message": {"message_thread_id": 7, "text": "offline reply"},
            },
            headers={"X-Telegram-Bot-Api-Secret-Token": "secret-abc"},
        )
        assert r.status_code == 200
        assert len(storage.pending_replies(conv["conversation_id"])) == 1

        # visitor comes back and connects -> receives pending reply, then purged
        with client.websocket_connect(
            f"/ws/visitor/{site_id}",
            headers={"origin": "https://example.test"},
        ) as visitor:
            visitor.send_text(json.dumps({
                "type": "visitor.connected",
                "visitor_id": "v-offline",
            }))
            event = json.loads(visitor.receive_text())
            assert event["type"] == "owner.message"
            assert event["message"] == "offline reply"
            assert event.get("pending") is True
            assert storage.pending_replies(conv["conversation_id"]) == []
