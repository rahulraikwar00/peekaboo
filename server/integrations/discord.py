"""Discord channel adapter.

Uses a bot token (NOT a webhook URL) so that the owner can reply back to
the visitor. The owner configures the bot's "Interactions Endpoint URL" in
the Discord developer portal to point at /v1/discord/webhook so we receive
owner replies and route them to the matching conversation.

Credentials (Fernet-encrypted JSON blob):
    {
        "bot_token": "...",
        "public_key": "<hex ed25519 public key, used to verify signatures>"
    }
"""

import json
import logging

import httpx

from server.integrations.base import ConversationRef, IntegrationAdapter
from server.services.crypto import decrypt_credentials

logger = logging.getLogger("peekaboo.discord")

DISCORD_API = "https://discord.com/api/v10"


def format_discord_message(event: dict) -> str:
    """Build the Discord notification body from a normalized message event."""
    return event.get("message", "").strip()


def _decoded_credentials(creds: str) -> dict:
    raw = decrypt_credentials(creds)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Tolerate legacy plaintext tokens.
        return {"bot_token": raw}


class DiscordAdapter(IntegrationAdapter):
    provider = "discord"

    def __init__(self, integration: dict, client: httpx.AsyncClient | None = None):
        super().__init__(integration)
        self._client = client
        raw = self.integration.get("credentials", "")
        self._creds = _decoded_credentials(raw) if raw else {}

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bot {self._creds['bot_token']}",
            "Content-Type": "application/json",
        }

    async def _post(self, method: str, body: dict) -> dict:
        url = f"{DISCORD_API}{method}"
        if self._client is not None:
            resp = await self._client.post(url, json=body, headers=self._headers())
        else:
            async with httpx.AsyncClient() as client:
                resp = await client.post(url, json=body, headers=self._headers())
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            try:
                desc = exc.response.json()
            except Exception:
                desc = exc.response.text[:200]
            logger.warning(
                "Discord %s HTTP %s: %s", method, exc.response.status_code, desc
            )
            raise
        return resp.json()

    async def deliver(self, event: dict, conversation: dict) -> ConversationRef | None:
        channel_id = self.integration["destination_id"]
        text = format_discord_message(event)
        if not text:
            return None
        try:
            data = await self._post(
                f"/channels/{channel_id}/messages",
                {"content": text[:2000]},
            )
        except Exception:
            return None
        return ConversationRef(
            site_id=self.integration["site_id"],
            conversation_id=conversation["conversation_id"],
            integration_id=self.integration.get("integration_id"),
            provider=self.provider,
            destination_id=channel_id,
            thread_id=str(data.get("id", "")),
        )

    @staticmethod
    def verify_signature(public_key_hex: str, signature_hex: str, timestamp: str, body: bytes) -> bool:
        """Verify a Discord interaction signature using the bot's public key.

        Discord sends X-Signature-Ed25519 + X-Signature-Timestamp; the body to
        verify is `timestamp + body`.
        """
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import (
                Ed25519PublicKey,
            )
        except ImportError:
            logger.warning("cryptography not installed; cannot verify Discord signatures")
            return False
        try:
            from cryptography.exceptions import InvalidSignature
        except ImportError:
            InvalidSignature = Exception  # type: ignore[misc,assignment]
        try:
            pub = Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key_hex))
            pub.verify(bytes.fromhex(signature_hex), timestamp.encode() + body)
            return True
        except (InvalidSignature, ValueError, TypeError):
            return False
