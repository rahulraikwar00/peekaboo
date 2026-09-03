import json

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from server import main
from server.services.signing import sign_visitor_token


@pytest.fixture(autouse=True)
def reset_state():
    main.sites.clear()
    main.visitors.clear()
    main.visitor_info.clear()
    main.site_creation_attempts.clear()
    main.owner_api_keys.clear()
    main.pending_oauth.clear()
    main.conversations.clear()
    main.integrations.clear()
    main.pending_replies.clear()
    main.site_stats.clear()
    main.telegram_updates.clear()


def make_owner(owner_id="owner-test"):
    api_key = main.mint_owner_api_key(owner_id)
    return {"owner_id": owner_id, "api_key": api_key}


def create_site(client, api_key=None, origin=None):
    if api_key is None:
        api_key = make_owner()["api_key"]
    payload = json.dumps({"origin": origin} if origin else {}).encode()
    response = client.post(
        "/sites",
        content=payload,
        headers={"X-API-Key": api_key, "Content-Type": "application/json"},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_generated_credentials_have_strong_entropy():
    with TestClient(main.app) as client:
        site = create_site(client)
        assert len(site["site_id"]) > 30


def test_invalid_operator_token_is_rejected():
    # The operator websocket was retired in favor of the Telegram reply path; the
    # legacy /ws/operator endpoint no longer exists.
    with TestClient(main.app) as client:
        site = create_site(client)
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(
                f"/ws/operator/{site['site_id']}?token=forged",
            ):
                pass


def test_site_status_reflects_existence():
    with TestClient(main.app) as client:
        site = create_site(client)
        assert client.get(f"/sites/{site['site_id']}/status").json() == {
            "exists": True
        }


def test_visitor_requires_origin_and_valid_site():
    with TestClient(main.app) as client:
        with pytest.raises(WebSocketDisconnect) as error:
            with client.websocket_connect("/ws/visitor/site_missing"):
                pass
        assert error.value.code == 1008

        site = create_site(client, origin="https://example.test")
        with pytest.raises(WebSocketDisconnect) as error:
            with client.websocket_connect(
                f"/ws/visitor/{site['site_id']}",
            ) as websocket:
                websocket.receive_text()
        assert error.value.code == 1008

        with pytest.raises(WebSocketDisconnect) as error:
            with client.websocket_connect(
                f"/ws/visitor/{site['site_id']}",
                headers={"origin": "https://evil.example"},
            ) as websocket:
                websocket.receive_text()
        assert error.value.code == 1008


def test_visitor_from_allowed_origin_is_accepted():
    with TestClient(main.app) as client:
        site = create_site(client, origin="https://example.test")
        with client.websocket_connect(
            f"/ws/visitor/{site['site_id']}",
            headers={"origin": "https://example.test"},
        ):
            pass


def test_visitor_message_is_scoped_and_size_limited():
    with TestClient(main.app) as client:
        site = create_site(client, origin="https://example.test")
        with client.websocket_connect(
            f"/ws/visitor/{site['site_id']}",
            headers={"origin": "https://example.test"},
        ) as visitor:
            visitor.send_text(json.dumps({
                "type": "visitor.connected",
                "visitor_token": sign_visitor_token(site["site_id"], "v-1"),
            }))
            # Right-sized visitor frame is fine.
            visitor.send_text("hello")
            # Oversized frame is rejected.
            visitor.send_text("x" * (main.MAX_MESSAGE_BYTES + 1))
            with pytest.raises(WebSocketDisconnect) as error:
                visitor.receive_text()
            assert error.value.code == 1009


def test_visitor_cannot_connect_without_valid_signed_token():
    with TestClient(main.app) as client:
        site_a = create_site(client, origin="https://example.test")
        site_b = create_site(client, origin="https://example.test")
        with client.websocket_connect(
            f"/ws/visitor/{site_a['site_id']}",
            headers={"origin": "https://example.test"},
        ) as visitor:
            # A raw visitor_id (no token) must be rejected.
            visitor.send_text(json.dumps({
                "type": "visitor.connected",
                "visitor_id": "attacker",
            }))
            with pytest.raises(WebSocketDisconnect) as error:
                visitor.receive_text()
            assert error.value.code == 1008

        # A token minted for one site cannot be replayed against another site.
        with client.websocket_connect(
            f"/ws/visitor/{site_a['site_id']}",
            headers={"origin": "https://example.test"},
        ) as visitor:
            visitor.send_text(json.dumps({
                "type": "visitor.connected",
                "visitor_token": sign_visitor_token(site_b["site_id"], "x"),
            }))
            with pytest.raises(WebSocketDisconnect) as error:
                visitor.receive_text()
            assert error.value.code == 1008


def test_site_detail_requires_owner_and_returns_stats():
    with TestClient(main.app) as client:
        api_key = make_owner()["api_key"]
        site = create_site(client, api_key)
        # valid owner -> 200 with stats
        r = client.get(f"/sites/{site['site_id']}", headers={"X-API-Key": api_key})
        assert r.status_code == 200
        body = r.json()
        assert body["site_id"] == site["site_id"]
        assert "stats" in body
        # no auth -> 401
        assert client.get(f"/sites/{site['site_id']}").status_code == 401
        # another owner -> 403
        other_key = make_owner(owner_id="owner-other")["api_key"]
        assert (
            client.get(
                f"/sites/{site['site_id']}", headers={"X-API-Key": other_key}
            ).status_code
            == 403
        )


def test_create_site_requires_valid_api_key():
    with TestClient(main.app) as client:
        response = client.post("/sites")
        assert response.status_code == 401

        response = client.post(
            "/sites",
            headers={"X-API-Key": "forged-key"},
        )
        assert response.status_code == 401


def test_revoked_api_key_is_rejected():
    with TestClient(main.app) as client:
        owner = make_owner()
        response = client.post(
            "/auth/logout",
            headers={"X-API-Key": owner["api_key"]},
        )
        assert response.status_code == 200

        response = client.post(
            "/sites",
            headers={"X-API-Key": owner["api_key"]},
        )
        assert response.status_code == 401


def test_sites_are_scoped_to_owner():
    with TestClient(main.app) as client:
        owner_a = make_owner()
        site = create_site(client, api_key=owner_a["api_key"])

        stored_owner = main.sites[site["site_id"]]["owner_id"]
        assert stored_owner == owner_a["owner_id"]


class FakeQuery:
    def __init__(self, table_name):
        self.table_name = table_name
        self.filters = []
        self.data = []

    def select(self, *columns):
        self.columns = columns
        return self

    def eq(self, column, value):
        self.filters.append(("eq", column, value))
        return self

    def is_(self, column, value):
        self.filters.append(("is_", column, value))
        return self

    def update(self, values):
        self.update_values = values
        return self

    def limit(self, count):
        self.limit_count = count
        return self

    def execute(self):
        type(self).result_data = self.data
        return self


class FakeSupabase:
    def __init__(self):
        self.tables = {}

    def table(self, name):
        if name not in self.tables:
            self.tables[name] = FakeQuery(name)
        return self.tables[name]


def test_owner_api_key_lookup_uses_null_filter_not_eq():
    fake = FakeSupabase()
    main.supabase = fake
    try:
        assert main.get_owner_id_from_api_key("some-key") is None
        query = fake.tables["owner_api_keys"]
        assert ("is_", "revoked_at", None) in query.filters
        assert ("eq", "revoked_at", None) not in query.filters
    finally:
        main.supabase = None


def test_logout_with_unknown_key_returns_404_not_500():
    fake = FakeSupabase()
    main.supabase = fake
    try:
        with TestClient(main.app) as client:
            response = client.post(
                "/auth/logout",
                headers={"X-API-Key": "some-key"},
            )
        assert response.status_code == 404
    finally:
        main.supabase = None


def test_oauth_callback_exchanges_code_on_isolated_client(monkeypatch):
    from server.routes import auth as auth_routes

    fake_shared = FakeSupabase()
    fake_shared.auth = None
    original = main.supabase
    main.supabase = fake_shared
    main.pending_oauth["state-1"] = {
        "code_verifier": "cv-123",
        "redirect_to": "http://server/cb",
    }

    class FakeUser:
        id = "owner-uuid"

    class FakeSession:
        user = FakeUser()

    class FakeAuth:
        def exchange_code_for_session(self, params):
            return FakeSession()

    class FakeThrowawayClient:
        def __init__(self, *args, **kwargs):
            self.auth = FakeAuth()

    monkeypatch.setattr(
        auth_routes, "create_client", lambda *a, **k: FakeThrowawayClient()
    )
    monkeypatch.setattr(
        auth_routes, "mint_owner_api_key",
        lambda owner_id, db_client=None: "minted-key",
    )
    monkeypatch.setattr(
        auth_routes, "get_supabase_client", lambda: fake_shared
    )

    with TestClient(main.app) as client:
        response = client.get(
            "/auth/oauth/callback?state=state-1&code=code-1",
            follow_redirects=False,
        )

    assert response.status_code == 303
    assert main.pending_oauth["state-1"]["api_key"] == "minted-key"

    try:
        if "pending_oauth" in main.__dict__:
            main.pending_oauth.clear()
    finally:
        main.supabase = original


def test_secure_headers_on_html_response():
    with TestClient(main.app) as client:
        r = client.get("/")
        assert r.headers.get("Strict-Transport-Security") == (
            "max-age=63072000; includeSubDomains; preload"
        )
        assert r.headers.get("Content-Security-Policy") == "frame-ancestors 'none'"
