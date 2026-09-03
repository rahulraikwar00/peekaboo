import json

import httpx

from server.integrations.base import ConversationRef, IntegrationAdapter
from server.services import storage
from server.services.crypto import decrypt_credentials

TELEGRAM_API = "https://api.telegram.org"


def format_telegram_message(event: dict) -> str:
    """Build the Telegram notification body from a normalized message event."""
    lines = ["💬 New website message"]
    name = event.get("visitor_name")
    if name:
        lines.append(f"From: {name}")
    page = event.get("page")
    if page:
        lines.append(f"Page: {page}")
    referrer = event.get("referrer")
    if referrer:
        lines.append(f"Referrer: {referrer}")
    lines.append("")
    message = event.get("message", "")
    lines.append(f'"{message}"')
    return "\n".join(lines)


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
        resp.raise_for_status()
        payload = resp.json()
        if not payload.get("ok"):
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
        title = event.get("visitor_name") or "New conversation"
        try:
            result = await self._request(
                "createForumTopic",
                chat_id=chat_id,
                name=title[:128],
            )
        except Exception:
            return None
        return result.get("message_thread_id")

    async def deliver(self, event: dict, conversation: dict) -> ConversationRef | None:
        integration_id = self.integration.get("integration_id")
        chat_id = self.integration["destination_id"]
        text = format_telegram_message(event)

        conversation_id = conversation["conversation_id"]
        thread_id = conversation.get("telegram_thread_id")

        if not thread_id:
            thread_id = await self._create_thread(event)
            if thread_id:
                storage.update_conversation_integration_ref(
                    conversation_id, integration_id, thread_id
                )

        params = {
            "chat_id": chat_id,
            "text": text,
        }
        if thread_id:
            params["message_thread_id"] = thread_id

        try:
            await self._request("sendMessage", **params)
        except Exception:
            return None

        return ConversationRef(
            site_id=self.integration["site_id"],
            conversation_id=conversation_id,
            integration_id=integration_id,
            provider=self.provider,
            destination_id=chat_id,
            thread_id=str(thread_id or ""),
        )
