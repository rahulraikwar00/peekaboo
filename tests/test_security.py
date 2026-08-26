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


def create_site(client):
    response = client.post("/sites")
    assert response.status_code == 200
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

        site = create_site(client)
        with pytest.raises(WebSocketDisconnect) as error:
            with client.websocket_connect(
                f"/ws/visitor/{site['site_id']}",
            ) as websocket:
                websocket.receive_text()
        assert error.value.code == 1008


def test_visitor_message_is_scoped_and_size_limited():
    with TestClient(main.app) as client:
        site = create_site(client)
        with client.websocket_connect(
            f"/ws/operator/{site['site_id']}?token={site['operator_token']}",
        ) as operator:
            with client.websocket_connect(
                f"/ws/visitor/{site['site_id']}",
                headers={"origin": "https://example.test"},
            ) as visitor:
                connected = json.loads(operator.receive_text())
                conversation_id = connected["conversation_id"]
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
        site = create_site(client)
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
                operator.send_text(f"/reply {first_id} only first")
                assert json.loads(first.receive_text())[
                    "message"] == "only first"
                executor = ThreadPoolExecutor(max_workers=1)
                pending = executor.submit(second.receive_text)
                with pytest.raises(FutureTimeoutError):
                    pending.result(timeout=0.1)
                executor.shutdown(wait=False, cancel_futures=True)
                assert first_id != second_id
