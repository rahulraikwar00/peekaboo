"""public_base_url honors PEEKABOO_SERVER_URL then PUBLIC_BASE_URL."""

import pytest

from server.config import public_base_url


def test_prefers_peekaboo_server_url(monkeypatch):
    monkeypatch.setenv("PEEKABOO_SERVER_URL", "https://peekaboo.example")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://compose.example")
    assert public_base_url(None) == "https://peekaboo.example"


def test_falls_back_to_public_base_url(monkeypatch):
    monkeypatch.delenv("PEEKABOO_SERVER_URL", raising=False)
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://compose.example")
    assert public_base_url(None) == "https://compose.example"


def test_strips_trailing_slash(monkeypatch):
    monkeypatch.delenv("PEEKABOO_SERVER_URL", raising=False)
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://compose.example/")
    assert public_base_url(None) == "https://compose.example"


def test_raises_when_nothing_configured(monkeypatch):
    monkeypatch.delenv("PEEKABOO_SERVER_URL", raising=False)
    monkeypatch.delenv("PUBLIC_BASE_URL", raising=False)
    with pytest.raises(RuntimeError):
        public_base_url(None)