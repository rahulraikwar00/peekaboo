import os

import pytest

from server.services.crypto import decrypt_credentials, encrypt_credentials
from server.services.sqlite_storage import SqliteStorage


def test_encrypt_decrypt_roundtrip(monkeypatch):
    monkeypatch.setenv(
        "ENCRYPTION_KEY",
        "M0gU7ZvT1wQ2fVz1rT2gB3jZ4lH5kL6mN7oP8qR9sT0=",
    )
    token = "123456:ABC-bot-token"
    enc = encrypt_credentials(token)
    assert enc != token
    assert decrypt_credentials(enc) == token


def test_decrypt_with_wrong_key_raises(monkeypatch):
    monkeypatch.setenv(
        "ENCRYPTION_KEY",
        "M0gU7ZvT1wQ2fVz1rT2gB3jZ4lH5kL6mN7oP8qR9sT0=",
    )
    enc = encrypt_credentials("secret")
    monkeypatch.setenv(
        "ENCRYPTION_KEY",
        "X0gU7ZvT1wQ2fVz1rT2gB3jZ4lH5kL6mN7oP8qR9sT1=",
    )
    with pytest.raises(ValueError):
        decrypt_credentials(enc)


@pytest.fixture
def store(tmp_path):
    return SqliteStorage(str(tmp_path / "test.db"))


def test_site_insert_and_get(store):
    store.insert_site({"site_id": "s1", "owner_id": "o1", "operator_token_hash": "h"})
    assert store.site_exists("s1")
    site = store.get_site("s1")
    assert site["owner_id"] == "o1"


def test_integration_lifecycle(store):
    store.insert_site({"site_id": "s1", "owner_id": "o1"})
    iid = store.insert_integration({
        "site_id": "s1",
        "provider": "telegram",
        "credentials": "encrypted",
        "destination_id": "12345",
    })
    integrations = store.list_integrations("s1")
    assert len(integrations) == 1
    assert integrations[0]["provider"] == "telegram"
    assert store.get_integration("s1", iid)["destination_id"] == "12345"
    assert store.delete_integration("s1", iid)
    assert store.list_integrations("s1") == []


def test_conversation_get_or_create(store):
    conv = store.get_or_create_conversation("s1", "visitor-1", "int-1")
    assert conv["visitor_id"] == "visitor-1"
    again = store.get_or_create_conversation("s1", "visitor-1", "int-1")
    assert again["conversation_id"] == conv["conversation_id"]


def test_conversation_thread_mapping(store):
    conv = store.get_or_create_conversation("s1", "visitor-1", "int-1")
    store.update_conversation_integration_ref(conv["conversation_id"], "int-1", "thread-9")
    found = store.get_conversation_by_integration_thread("s1", "int-1", "thread-9")
    assert found["conversation_id"] == conv["conversation_id"]
    # A different integration sharing the same thread id must not match.
    assert store.get_conversation_by_integration_thread("s1", "int-2", "thread-9") is None


def test_webhook_update_dedup(store):
    assert store.webhook_update_seen("100") is False
    assert store.webhook_update_seen("100") is True
    assert store.webhook_update_seen("101") is False


def test_pending_reply_enqueue_deliver_purge(store):
    conv = store.get_or_create_conversation("s1", "visitor-1", "int-1")["conversation_id"]
    store.enqueue_reply(conv, "reply one")
    store.enqueue_reply(conv, "reply two")
    replies = store.pending_replies(conv)
    assert [r["reply"] for r in replies] == ["reply one", "reply two"]
    store.delete_pending_reply(replies[0]["id"])
    assert [r["reply"] for r in store.pending_replies(conv)] == ["reply two"]
    purged = store.purge_expired_pending_replies("2999-01-01 00:00:00")
    assert purged >= 1
    assert store.pending_replies(conv) == []
