import logging

import httpx

from server.integrations.base import ConversationRef, IntegrationAdapter
from server.services import storage
from server.services.crypto import decrypt_credentials

logger = logging.getLogger("peekaboo.telegram")

TELEGRAM_API = "https://api.telegram.org"


def format_telegram_message(event: dict) -> str:
    """Build the Telegram notification body from a normalized message event."""
    return event.get("message", "").strip()


class TelegramAdapter(IntegrationAdapter):
    provider = "telegram"

    def __init__(self, integration: dict, client: httpx.AsyncClient | None = None):
        super().__init__(integration)
        self._client = client

    def _api(self, method: str) -> str:
        token = decrypt_credentials(self.integration["credentials"])
        return f"{TELEGRAM_API}/bot{token}/{method}"

    async def _request(self, method: str, **params) -> dict:
        url = self._api(method)
        if self._client is not None:
            resp = await self._client.post(url, data=params)
        else:
            async with httpx.AsyncClient() as client:
                resp = await client.post(url, data=params)
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            desc = ""
            try:
                desc = exc.response.json().get("description", "")
            except Exception:
                desc = exc.response.text[:200]
            logger.warning("Telegram %s HTTP %s: %s", method, exc.response.status_code, desc)
            raise
        payload = resp.json()
        if not payload.get("ok"):
            desc = payload.get("description", "")
            logger.warning("Telegram %s failed: %s", method, desc or payload)
            raise RuntimeError(f"Telegram {method} failed: {payload}")
        return payload.get("result") or {}

    async def set_webhook(self, url: str, secret: str) -> bool:
        """Point Telegram to our webhook endpoint with the secret token."""
        try:
            await self._request(
                "setWebhook",
                url=url,
                secret_token=secret,
                allowed_updates='["message"]',
            )
        except Exception:
            return False
        return True

    async def _create_thread(self, event: dict) -> str | None:
        """Create a per-conversation forum topic and return the thread id."""
        chat_id = self.integration["destination_id"]
        name = (event.get("visitor_name") or "").strip() or "New conversation"
        try:
            result = await self._request(
                "createForumTopic",
                chat_id=chat_id,
                name=name[:128],
            )
        except Exception:
            return None
        return result.get("message_thread_id")

    async def _send(self, chat_id: str, text: str, thread_id: str | None) -> bool:
        params = {"chat_id": chat_id, "text": text}
        if thread_id:
            params["message_thread_id"] = thread_id
        try:
            await self._request("sendMessage", **params)
            return True
        except Exception:
            return False

    async def deliver(self, event: dict, conversation: dict) -> ConversationRef | None:
        integration_id = self.integration.get("integration_id")
        chat_id = self.integration["destination_id"]
        text = format_telegram_message(event)
        conversation_id = conversation["conversation_id"]
        thread_id = conversation.get("telegram_thread_id")
        new_thread = False

        if not thread_id:
            thread_id = await self._create_thread(event)
            if not thread_id:
                return None
            new_thread = True

        if not await self._send(chat_id, text, thread_id):
            if new_thread:
                return None
            # Stale thread — the topic was deleted or is inaccessible.
            # Recreate a fresh topic for this visitor and retry once.
            logger.info(
                "Stale thread %s for conversation %s, recreating",
                thread_id, conversation_id,
            )
            thread_id = await self._create_thread(event)
            if not thread_id:
                return None
            new_thread = True
            if not await self._send(chat_id, text, thread_id):
                return None

        if new_thread:
            storage.update_conversation_integration_ref(
                conversation_id, integration_id, thread_id
            )

        return ConversationRef(
            site_id=self.integration["site_id"],
            conversation_id=conversation_id,
            integration_id=integration_id,
            provider=self.provider,
            destination_id=chat_id,
            thread_id=str(thread_id),
        )
