"""Tests for the Slack channel adapter."""

import hashlib
import hmac
import json
import time

from server.integrations.slack import (
    SlackAdapter,
    format_slack_message,
    verify_slack_signature,
)
from server.integrations import router


def test_format_slack_message():
    event = {"message": "Hello from Slack visitor"}
    assert format_slack_message(event) == "Hello from Slack visitor"
    assert format_slack_message({"message": ""}) == ""


def test_build_adapter_returns_slack():
    adapter = router.build_adapter({"provider": "slack"})
    assert adapter is not None
    assert isinstance(adapter, SlackAdapter)


def test_slack_signature_verification():
    secret = "test-signing-secret"
    ts = str(int(time.time()))
    body = b'{"event":{"message":{"text":"hi"}}}'
    base = b"v0:" + ts.encode() + body
    sig = hmac.new(secret.encode(), base, hashlib.sha256).hexdigest()
    expected = f"v0={sig}"

    assert verify_slack_signature(secret, ts, body, expected) is True
    assert verify_slack_signature(secret, ts, body, "v0=bad") is False
    assert verify_slack_signature("", ts, body, expected) is False
    assert verify_slack_signature(secret, "", body, expected) is False
    assert verify_slack_signature(secret, ts, body, "") is False


def test_slack_signature_expired_timestamp():
    secret = "test-signing-secret"
    ts = str(int(time.time()) - 600)  # 10 minutes ago
    body = b"test"
    base = b"v0:" + ts.encode() + body
    sig = hmac.new(secret.encode(), base, hashlib.sha256).hexdigest()
    expected = f"v0={sig}"
    # Timestamp too old should fail
    assert verify_slack_signature(secret, ts, body, expected) is False


def test_slack_signature_invalid_timestamp():
    assert verify_slack_signature("secret", "not-a-number", b"body", "v0=bad") is False


def test_slack_adapter_deliver(monkeypatch):
    monkeypatch.setenv(
        "ENCRYPTION_KEY",
        "M0gU7ZvT1wQ2fVz1rT2gB3jZ4lH5kL6mN7oP8qR9sT0=",
    )
    from server.services.crypto import encrypt_credentials

    creds = {
        "bot_token": "xoxb-fake-token",
        "signing_secret": "fake-secret",
        "channel_id": "C123456",
    }
    integration = {
        "integration_id": "int_slack_1",
        "site_id": "site_1",
        "provider": "slack",
        "destination_id": "C123456",
        "credentials": encrypt_credentials(json.dumps(creds)),
    }
    adapter = SlackAdapter(integration)

    # Mock the slack_sdk.WebClient
    class FakeSlackResponse:
        ok = True
        data = {"ts": "1234567890.123456"}

        def __getattr__(self, name):
            if name == "data":
                return self.data
            raise AttributeError(name)

    class FakeWebClient:
        def chat_postMessage(self, **kwargs):
            self.kwargs = kwargs
            return FakeSlackResponse()

    adapter._client = FakeWebClient()
    conversation = {"conversation_id": "conv_slack_1"}

    ref = _run(adapter.deliver(
        {"message": "Hello Slack", "visitor_name": "Test"},
        conversation,
    ))
    assert ref is not None
    assert ref.conversation_id == "conv_slack_1"
    assert ref.destination_id == "C123456"
    assert ref.thread_id == "1234567890.123456"
    assert ref.provider == "slack"


def test_slack_adapter_deliver_empty_message():
    from server.services.crypto import encrypt_credentials

    creds = {"bot_token": "xoxb-token", "signing_secret": "s", "channel_id": "C1"}
    integration = {
        "integration_id": "int_s",
        "site_id": "s1",
        "provider": "slack",
        "destination_id": "C1",
        "credentials": encrypt_credentials(json.dumps(creds)),
    }
    adapter = SlackAdapter(integration)
    result = _run(adapter.deliver({"message": ""}, {"conversation_id": "c1"}))
    assert result is None


def test_slack_adapter_deliver_no_channel_id():
    from server.services.crypto import encrypt_credentials

    creds = {"bot_token": "xoxb-token", "signing_secret": "s"}
    integration = {
        "integration_id": "int_s2",
        "site_id": "s2",
        "provider": "slack",
        "destination_id": "",  # No channel_id
        "credentials": encrypt_credentials(json.dumps(creds)),
    }
    adapter = SlackAdapter(integration)
    result = _run(adapter.deliver({"message": "hi"}, {"conversation_id": "c2"}))
    assert result is None


def _run(coro):
    import asyncio
    return asyncio.get_event_loop().run_until_complete(coro)
