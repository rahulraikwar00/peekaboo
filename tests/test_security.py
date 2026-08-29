import json
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from server import main


@pytest.fixture(autouse=True)
def reset_state():
    main.sites.clear()
    main.visitors.clear()
    main.operators.clear()
    main.visitor_info.clear()
    main.site_creation_attempts.clear()
    main.owner_api_keys.clear()
    main.pending_oauth.clear()


def make_owner():
    api_key = main.mint_owner_api_key("owner-test")
    return {"owner_id": "owner-test", "api_key": api_key}


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
        assert len(site["operator_token"]) > 60


def test_invalid_operator_token_is_rejected():
    with TestClient(main.app) as client:
        site = create_site(client)
        with pytest.raises(WebSocketDisconnect) as error:
            with client.websocket_connect(
                f"/ws/operator/{site['site_id']}?token=forged",
            ):
                pass
        assert error.value.code == 1008


def test_owner_status_reflects_listener_connection():
    with TestClient(main.app) as client:
        site = create_site(client)
        assert client.get(f"/sites/{site['site_id']}/status").json() == {
            "operator_online": False
        }
        with client.websocket_connect(
            f"/ws/operator/{site['site_id']}?token={site['operator_token']}"
        ):
            assert client.get(f"/sites/{site['site_id']}/status").json() == {
                "operator_online": True
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
            f"/ws/operator/{site['site_id']}?token={site['operator_token']}",
        ) as operator:
            with client.websocket_connect(
                f"/ws/visitor/{site['site_id']}",
                headers={"origin": "https://example.test"},
            ) as visitor:
                connected = json.loads(operator.receive_text())
                conversation_id = connected["conversation_id"]
                # Drain initial owner.status message
                json.loads(visitor.receive_text())
                visitor.send_text("<script>alert(1)</script>")
                event = json.loads(operator.receive_text())
                assert event["conversation_id"] == conversation_id
                assert event["message"] == "<script>alert(1)</script>"
                operator.send_text(f"/reply {conversation_id} private reply")
                response = json.loads(visitor.receive_text())
                assert response["message"] == "private reply"

                visitor.send_text("x" * (main.MAX_MESSAGE_BYTES + 1))
                with pytest.raises(WebSocketDisconnect) as error:
                    visitor.receive_text()
                assert error.value.code == 1009


def test_operator_reply_does_not_cross_conversations():
    with TestClient(main.app) as client:
        site = create_site(client, origin="https://example.test")
        with client.websocket_connect(
            f"/ws/operator/{site['site_id']}?token={site['operator_token']}",
        ) as operator:
            with client.websocket_connect(
                f"/ws/visitor/{site['site_id']}",
                headers={"origin": "https://example.test"},
            ) as first, client.websocket_connect(
                f"/ws/visitor/{site['site_id']}",
                headers={"origin": "https://example.test"},
            ) as second:
                first_id = json.loads(operator.receive_text())[
                    "conversation_id"]
                second_id = json.loads(operator.receive_text())[
                    "conversation_id"]
                # Drain initial owner.status messages
                # first visitor gets 2 (one on connect, one when second connects)
                # second visitor gets 1 (when it connects)
                json.loads(first.receive_text())
                json.loads(first.receive_text())
                json.loads(second.receive_text())
                operator.send_text(f"/reply {first_id} only first")
                assert json.loads(first.receive_text())[
                    "message"] == "only first"
                executor = ThreadPoolExecutor(max_workers=1)
                pending = executor.submit(second.receive_text)
                with pytest.raises(FutureTimeoutError):
                    pending.result(timeout=0.1)
                executor.shutdown(wait=False, cancel_futures=True)
                assert first_id != second_id


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
