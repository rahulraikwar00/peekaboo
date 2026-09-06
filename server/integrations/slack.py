"""Slack channel adapter.

Uses a bot token + signing secret. The owner configures the Slack app's
"Event Subscriptions Request URL" to point at /v1/slack/webhook so we
receive owner replies and route them to the matching conversation.

Credentials (Fernet-encrypted JSON blob):
    {
        "bot_token": "xoxb-...",
        "signing_secret": "...",
        "channel_id": "C123456"
    }

Note: channel_id is also stored in the credentials so a single integration
maps to one Slack channel. `destination_id` on the integration record
mirrors it for parity with the schema.
"""

import hashlib
import hmac
import json
import logging
import time

from server.integrations.base import ConversationRef, IntegrationAdapter
from server.services.crypto import decrypt_credentials

logger = logging.getLogger("peekaboo.slack")


def format_slack_message(event: dict) -> str:
    return event.get("message", "").strip()


def _decoded_credentials(creds: str) -> dict:
    raw = decrypt_credentials(creds)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"bot_token": raw}


def verify_slack_signature(signing_secret: str, timestamp: str, body: bytes, signature: str) -> bool:
    """Verify X-Slack-Signature: HMAC-SHA256 of `v0:{ts}:{body}`."""
    if not signing_secret or not timestamp or not signature:
        return False
    try:
        ts_int = int(timestamp)
    except ValueError:
        return False
    # Reject replays older than 5 minutes.
    if abs(time.time() - ts_int) > 60 * 5:
        return False
    base = b"v0:" + timestamp.encode() + body
    digest = hmac.new(
        signing_secret.encode(), base, hashlib.sha256
    ).hexdigest()
    expected = f"v0={digest}"
    return hmac.compare_digest(expected, signature or "")


class SlackAdapter(IntegrationAdapter):
    provider = "slack"

    def __init__(self, integration: dict):
        super().__init__(integration)
        raw = self.integration.get("credentials", "")
        self._creds = _decoded_credentials(raw) if raw else {}
        self._client = None  # lazy

    def _client_instance(self):
        if self._client is None:
            from slack_sdk import WebClient
            self._client = WebClient(token=self._creds["bot_token"])
        return self._client

    async def deliver(self, event: dict, conversation: dict) -> ConversationRef | None:
        text = format_slack_message(event)
        if not text:
            return None
        channel_id = self.integration.get("destination_id") or self._creds.get("channel_id")
        if not channel_id:
            return None
        # Run the (sync) slack client in a thread so the async event loop is unblocked.
        import asyncio
        try:
            kwargs = {"channel": channel_id, "text": text[:4000]}
            # Outbound idempotency: Slack's chat_postMessage supports a
            # `client_id_postfix` to dedupe across retries.
            idem = (event.get("idempotency_key") or "")[:8]
            if idem:
                kwargs["client_id_postfix"] = idem
            response = await asyncio.to_thread(
                self._client_instance().chat_postMessage, **kwargs
            )
        except Exception as exc:
            logger.warning("Slack chat_postMessage failed: %s", exc)
            return None
        ok = bool(getattr(response, "ok", False) or (isinstance(response, dict) and response.get("ok")))
        if not ok:
            return None
        data = response.data if hasattr(response, "data") else (response or {})
        ts = str(data.get("ts", "")) if isinstance(data, dict) else ""
        return ConversationRef(
            site_id=self.integration["site_id"],
            conversation_id=conversation["conversation_id"],
            integration_id=self.integration.get("integration_id"),
            provider=self.provider,
            destination_id=channel_id,
            thread_id=ts,
        )
