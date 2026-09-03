import json

import pytest
from fastapi.testclient import TestClient

from server import main


@pytest.fixture(autouse=True)
def reset_state():
    main.sites.clear()
    main.owner_api_keys.clear()
    main.site_creation_attempts.clear()
    main.conversations.clear()
    main.integrations.clear()
    main.pending_replies.clear()
    main.site_stats.clear()
    from server.state import limiter
    limiter.reset()


def make_owner():
    api_key = main.mint_owner_api_key("owner-test")
    return api_key


def create_site(client, api_key, origins=("https://example.test",)):
    payload = json.dumps({"origins": list(origins)}).encode()
    resp = client.post(
        "/sites",
        content=payload,
        headers={"X-API-Key": api_key, "Content-Type": "application/json"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["site_id"]


def test_message_requires_site_and_origin(monkeypatch, ):
    monkeypatch.setenv("ENCRYPTION_KEY", "M0gU7ZvT1wQ2fVz1rT2gB3jZ4lH5kL6mN7oP8qR9sT0=")
    from server.routes import messages as messages_route

    async def fake_deliver(site_id, event, visitor_id):
        return {"delivered": 1, "failed": 0, "conversation_id": "conv_x"}
    monkeypatch.setattr(messages_route, "deliver_to_site", fake_deliver)

    with TestClient(main.app) as client:
        api_key = make_owner()
        site = create_site(client, api_key)

        # unknown site -> 404
        r = client.post(
            "/v1/messages",
            json={"site_id": "nope", "message": "hi"},
            headers={"origin": "https://example.test"},
        )
        assert r.status_code == 404

        # wrong origin -> 403
        r = client.post(
            "/v1/messages",
            json={"site_id": site, "message": "hi"},
            headers={"origin": "https://evil.test"},
        )
        assert r.status_code == 403

        # no origin -> 403
        r = client.post(
            "/v1/messages",
            json={"site_id": site, "message": "hi"},
        )
        assert r.status_code == 403

        # valid -> 200, and never echoes message content
        r = client.post(
            "/v1/messages",
            json={"site_id": site, "message": "hello there", "visitor_name": "Ann"},
            headers={"origin": "https://example.test"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body.get("message") is None
        assert "hello there" not in r.text


def test_message_honeypot_is_accepted_but_not_forwarded(monkeypatch):
    monkeypatch.setenv("ENCRYPTION_KEY", "M0gU7ZvT1wQ2fVz1rT2gB3jZ4lH5kL6mN7oP8qR9sT0=")
    from server.routes import messages as messages_route

    calls = []

    async def fake_deliver(site_id, event, visitor_id):
        calls.append(event)
        return {"delivered": 1, "failed": 0, "conversation_id": "conv_x"}
    monkeypatch.setattr(messages_route, "deliver_to_site", fake_deliver)

    with TestClient(main.app) as client:
        api_key = make_owner()
        site = create_site(client, api_key)
        r = client.post(
            "/v1/messages",
            json={"site_id": site, "message": "hi", "website": "http://honeypot"},
            headers={"origin": "https://example.test"},
        )
        assert r.status_code == 200
        assert calls == []


def test_message_oversized_payload_rejected():
    with TestClient(main.app) as client:
        api_key = make_owner()
        site = create_site(client, api_key)
        r = client.post(
            "/v1/messages",
            content='{"message": "' + "x" * 9000 + '"}',
            headers={"origin": "https://example.test", "Content-Type": "application/json"},
        )
        assert r.status_code == 413


def test_rate_limit_per_ip(monkeypatch):
    monkeypatch.setenv("ENCRYPTION_KEY", "M0gU7ZvT1wQ2fVz1rT2gB3jZ4lH5kL6mN7oP8qR9sT0=")
    from server.routes import messages as messages_route

    async def fake_deliver(site_id, event, visitor_id):
        return {"delivered": 1, "failed": 0, "conversation_id": "conv_x"}
    monkeypatch.setattr(messages_route, "deliver_to_site", fake_deliver)

    from server.services.ratelimit import MSG_PER_IP, MSG_IP_WINDOW
    from server.state import limiter

    with TestClient(main.app) as client:
        api_key = make_owner()
        site = create_site(client, api_key)
        headers = {"origin": "https://example.test"}
        statuses = []
        for _ in range(MSG_PER_IP + 5):
            r = client.post(
                "/v1/messages",
                json={"site_id": site, "message": "x"},
                headers=headers,
            )
            statuses.append(r.status_code)
        assert 429 in statuses
