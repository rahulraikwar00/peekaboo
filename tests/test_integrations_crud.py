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


def test_integrations_require_owner_api_key():
    with TestClient(main.app) as client:
        r = client.get("/sites/site_1/integrations")
        assert r.status_code == 401


def test_create_list_delete_integration(monkeypatch):
    monkeypatch.setenv(
        "ENCRYPTION_KEY",
        "M0gU7ZvT1wQ2fVz1rT2gB3jZ4lH5kL6mN7oP8qR9sT0=",
    )
    with TestClient(main.app) as client:
        api_key = main.mint_owner_api_key("owner")
        site_id = create_site(client, api_key)

        listing = client.get(
            f"/sites/{site_id}/integrations",
            headers={"X-API-Key": api_key},
        )
        assert listing.status_code == 200
        assert listing.json()["integrations"] == []

        created = client.post(
            f"/sites/{site_id}/integrations",
            json={"provider": "telegram", "token": "TELEGRAM-TOKEN", "chat_id": "-1001"},
            headers={"X-API-Key": api_key},
        )
        assert created.status_code == 200, created.text
        integration_id = created.json()["integration_id"]
        assert created.json()["webhook_secret"] and len(created.json()["webhook_secret"]) >= 32

        listing2 = client.get(
            f"/sites/{site_id}/integrations",
            headers={"X-API-Key": api_key},
        )
        rows = listing2.json()["integrations"]
        assert len(rows) == 1
        assert rows[0]["integration_id"] == integration_id
        assert rows[0]["credentials_stored"] is True
        assert "webhook_secret" not in rows[0]
        assert "token" not in rows[0]

        # Stored credential is the ciphertext, not the plaintext token.
        import server.state as _s; import json as _j; print("DBG keys:", list(_s.integrations.keys()), _j.dumps(_s.integrations)[:300]); print("DBG site_id:", site_id, "integration_id:", integration_id); stored = main.integrations[site_id][integration_id]
        assert stored["credentials"] != "TELEGRAM-TOKEN"

        deleted = client.delete(
            f"/sites/{site_id}/integrations/{integration_id}",
            headers={"X-API-Key": api_key},
        )
        assert deleted.status_code == 200
        assert main.integrations.get(site_id, {}) == {}


def test_integration_create_requires_token_and_chat_id():
    with TestClient(main.app) as client:
        api_key = main.mint_owner_api_key("owner")
        site_id = create_site(client, api_key)

        r = client.post(
            f"/sites/{site_id}/integrations",
            json={"provider": "telegram", "token": "T"},
            headers={"X-API-Key": api_key},
        )
        assert r.status_code == 400
        r = client.post(
            f"/sites/{site_id}/integrations",
            json={"provider": "telegram", "chat_id": "-1"},
            headers={"X-API-Key": api_key},
        )
        assert r.status_code == 400


def test_integration_ownership_enforced():
    with TestClient(main.app) as client:
        owner_a = main.mint_owner_api_key("owner-a")
        owner_b = main.mint_owner_api_key("owner-b")
        site_id = create_site(client, owner_a)

        r = client.post(
            f"/sites/{site_id}/integrations",
            json={"provider": "telegram", "token": "T", "chat_id": "-1"},
            headers={"X-API-Key": owner_b},
        )
        assert r.status_code == 401


def test_list_sites_returns_owner_sites():
    with TestClient(main.app) as client:
        owner = main.mint_owner_api_key("owner-list")
        s1 = create_site(client, owner)
        s2 = create_site(client, owner)
        r = client.get("/sites", headers={"X-API-Key": owner})
        assert r.status_code == 200
        site_ids = {s["site_id"] for s in r.json()["sites"]}
        assert site_ids == {s1, s2}