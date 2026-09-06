"""Tests for the Discord channel adapter."""

import json

import httpx

from server.integrations.discord import (
    DiscordAdapter,
    format_discord_message,
)
from server.integrations import router


class FakeResponse:
    def __init__(self, status_code, json_data=None):
        self.status_code = status_code
        self._json = json_data or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}",
                request=httpx.Request("POST", "http://fake"),
                response=self,
            )

    def json(self):
        return self._json


class FakeClient:
    def __init__(self):
        self.requests = []

    async def post(self, url, json=None, headers=None):
        self.requests.append((url, json, headers))
        return FakeResponse(200, {"id": "12345", "content": json.get("content", "")})

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


def _run(coro):
    import asyncio
    return asyncio.get_event_loop().run_until_complete(coro)


def test_format_discord_message():
    event = {"message": "Hello from visitor", "visitor_name": "Bob"}
    assert format_discord_message(event) == "Hello from visitor"
    assert format_discord_message({"message": ""}) == ""


def test_build_adapter_returns_discord():
    adapter = router.build_adapter({"provider": "discord"})
    assert adapter is not None
    assert isinstance(adapter, DiscordAdapter)


def test_discord_adapter_deliver(monkeypatch):
    monkeypatch.setenv(
        "ENCRYPTION_KEY",
        "M0gU7ZvT1wQ2fVz1rT2gB3jZ4lH5kL6mN7oP8qR9sT0=",
    )
    from server.services.crypto import encrypt_credentials

    client = FakeClient()
    creds = {"bot_token": "fake-bot-token", "public_key": "abcd1234"}
    integration = {
        "integration_id": "int_discord_1",
        "site_id": "site_1",
        "provider": "discord",
        "destination_id": "987654321",
        "credentials": encrypt_credentials(json.dumps(creds)),
    }
    adapter = DiscordAdapter(integration, client=client)
    conversation = {"conversation_id": "conv_discord_1"}

    ref = _run(adapter.deliver(
        {"message": "Hello Discord", "visitor_name": "Test"},
        conversation,
    ))
    assert ref is not None
    assert ref.conversation_id == "conv_discord_1"
    assert ref.destination_id == "987654321"
    assert ref.thread_id == "12345"
    assert ref.provider == "discord"

    # Verify the API call
    assert len(client.requests) == 1
    url, body, headers = client.requests[0]
    assert "/channels/987654321/messages" in url
    assert body["content"] == "Hello Discord"
    assert "Authorization" in headers
    assert headers["Authorization"].startswith("Bot ")


def test_discord_adapter_deliver_empty_message():
    from server.services.crypto import encrypt_credentials

    creds = {"bot_token": "token", "public_key": "key"}
    integration = {
        "integration_id": "int_d",
        "site_id": "s1",
        "provider": "discord",
        "destination_id": "ch1",
        "credentials": encrypt_credentials(json.dumps(creds)),
    }
    adapter = DiscordAdapter(integration)
    # Empty message should return None
    result = _run(adapter.deliver({"message": ""}, {"conversation_id": "c1"}))
    assert result is None


def test_discord_adapter_handles_api_error(monkeypatch):
    monkeypatch.setenv(
        "ENCRYPTION_KEY",
        "M0gU7ZvT1wQ2fVz1rT2gB3jZ4lH5kL6mN7oP8qR9sT0=",
    )
    from server.services.crypto import encrypt_credentials

    class ErrorClient(FakeClient):
        async def post(self, url, json=None, headers=None):
            self.requests.append((url, json, headers))
            return FakeResponse(403, {"message": "Forbidden"})

    creds = {"bot_token": "token", "public_key": "key"}
    integration = {
        "integration_id": "int_d2",
        "site_id": "s2",
        "provider": "discord",
        "destination_id": "ch2",
        "credentials": encrypt_credentials(json.dumps(creds)),
    }
    adapter = DiscordAdapter(integration, client=ErrorClient())
    result = _run(adapter.deliver({"message": "hi"}, {"conversation_id": "c2"}))
    assert result is None


def test_discord_signature_verification():
    # verify_signature is a static method on DiscordAdapter
    # Just test that the function doesn't crash with invalid data
    assert DiscordAdapter.verify_signature("bad-key", "bad-sig", "ts", b"body") is False
    assert DiscordAdapter.verify_signature("", "", "", b"") is False
