import httpx
from server.integrations.telegram import TelegramAdapter, format_telegram_message
from server.integrations import router


def test_format_telegram_message_with_context():
    event = {
        "visitor_name": "John",
        "page": "/projects",
        "message": "Are you available for freelance work?",
        "referrer": "https://twitter.com",
    }
    text = format_telegram_message(event)
    # Only the visitor's raw text is shown in the body; the visitor's identity
    # lives in the forum topic title, so no boilerplate header is emitted.
    assert text == "Are you available for freelance work?"
    assert "New website message" not in text
    assert "From:" not in text
    assert "Page:" not in text


def test_format_telegram_message_minimal():
    text = format_telegram_message({"message": "hi"})
    assert "hi" in text
    assert "From:" not in text


class FakeResponse:
    def __init__(self, json):
        self._json = json

    def raise_for_status(self):
        pass

    def json(self):
        return self._json


class FakeClient:
    def __init__(self):
        self.requests = []
        self._closed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, data):
        self.requests.append((url, data))
        method = url.rsplit("/", 1)[-1]
        if method == "createForumTopic":
            return FakeResponse({"ok": True, "result": {"message_thread_id": 42}})
        return FakeResponse({"ok": True, "result": {}})


def _run(coro):
    import asyncio
    return asyncio.get_event_loop().run_until_complete(coro)


def test_telegram_adapter_creates_thread_then_sends(monkeypatch):
    monkeypatch.setenv(
        "ENCRYPTION_KEY",
        "M0gU7ZvT1wQ2fVz1rT2gB3jZ4lH5kL6mN7oP8qR9sT0=",
    )
    from server.services.crypto import encrypt_credentials

    client = FakeClient()
    integration = {
        "integration_id": "int_1",
        "site_id": "site_1",
        "provider": "telegram",
        "destination_id": "12345",
        "credentials": encrypt_credentials("TOKEN:secret"),
    }
    adapter = TelegramAdapter(integration, client=client)
    conversation = {"conversation_id": "conv_1", "telegram_thread_id": None}

    ref = _run(adapter.deliver(
        {"message": "hello", "visitor_name": "Ann"},
        conversation,
    ))
    assert ref is not None
    assert ref.conversation_id == "conv_1"
    assert ref.thread_id == "42"
    methods = [url.rsplit("/", 1)[-1] for url, _ in client.requests]
    assert methods == ["createForumTopic", "sendMessage"]
    send = client.requests[1][1]
    assert send["chat_id"] == "12345"
    assert send["message_thread_id"] == 42
    assert "hello" in send["text"]


def test_telegram_adapter_reuses_existing_thread(monkeypatch):
    monkeypatch.setenv(
        "ENCRYPTION_KEY",
        "M0gU7ZvT1wQ2fVz1rT2gB3jZ4lH5kL6mN7oP8qR9sT0=",
    )
    from server.services.crypto import encrypt_credentials

    client = FakeClient()
    integration = {
        "integration_id": "int_1",
        "site_id": "site_1",
        "provider": "telegram",
        "destination_id": "12345",
        "credentials": encrypt_credentials("TOKEN:secret"),
    }
    adapter = TelegramAdapter(integration, client=client)
    conversation = {"conversation_id": "conv_1", "telegram_thread_id": "7"}

    ref = _run(adapter.deliver({"message": "hi"}, conversation))
    assert ref is not None
    assert ref.thread_id == "7"
    methods = [url.rsplit("/", 1)[-1] for url, _ in client.requests]
    assert methods == ["sendMessage"]
    assert client.requests[0][1]["message_thread_id"] == "7"


def test_telegram_adapter_recreates_stale_thread(monkeypatch):
    monkeypatch.setenv(
        "ENCRYPTION_KEY",
        "M0gU7ZvT1wQ2fVz1rT2gB3jZ4lH5kL6mN7oP8qR9sT0=",
    )
    from server.services.crypto import encrypt_credentials

    class StaleClient(FakeClient):
        async def post(self, url, data):
            self.requests.append((url, data))
            method = url.rsplit("/", 1)[-1]
            if method == "sendMessage":
                # First send to the stale thread fails; the retry to a new
                # thread succeeds.
                if not getattr(self, "_failed_once", False):
                    self._failed_once = True
                    return FakeResponse(
                        {"ok": False, "description": "message thread not found"}
                    )
            if method == "createForumTopic":
                return FakeResponse({"ok": True, "result": {"message_thread_id": 42}})
            return FakeResponse({"ok": True, "result": {}})

    client = StaleClient()
    integration = {
        "integration_id": "int_1",
        "site_id": "site_1",
        "provider": "telegram",
        "destination_id": "12345",
        "credentials": encrypt_credentials("TOKEN:secret"),
    }
    adapter = TelegramAdapter(integration, client=client)
    conversation = {"conversation_id": "conv_1", "telegram_thread_id": "7"}

    ref = _run(adapter.deliver({"message": "hi", "visitor_name": "Bo"}, conversation))
    assert ref is not None
    assert ref.thread_id == "42"
    methods = [url.rsplit("/", 1)[-1] for url, _ in client.requests]
    # stale send fails -> recreate topic -> retry send
    assert methods == ["sendMessage", "createForumTopic", "sendMessage"]
    # final send goes to the fresh thread
    assert client.requests[2][1]["message_thread_id"] == 42


def test_build_adapter_mapping():
    assert router.build_adapter({"provider": "telegram"}) is not None
    assert router.build_adapter({"provider": "discord"}) is None