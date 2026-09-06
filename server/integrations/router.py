"""Channel adapter registry and outbound delivery router.

Adapters are registered through the `ADAPTERS` map keyed by provider name.
The router looks up an adapter by the integration's provider and delegates
`deliver(event, conversation)` to it. Adding a new channel = writing a new
`IntegrationAdapter` subclass and registering it here.
"""

import httpx

from server.integrations.discord import DiscordAdapter
from server.integrations.slack import SlackAdapter
from server.integrations.telegram import TelegramAdapter
from server.services import storage


ADAPTERS: dict[str, type] = {
    "telegram": TelegramAdapter,
    "discord": DiscordAdapter,
    "slack": SlackAdapter,
}


def register(provider: str, adapter_cls: type) -> None:
    """Register a new channel adapter. Idempotent: last write wins."""
    ADAPTERS[provider] = adapter_cls


def build_adapter(integration: dict):
    """Return the adapter matching an integration's provider, or None if unknown."""
    provider = integration.get("provider")
    cls = ADAPTERS.get(provider)
    if cls is None:
        return None
    return cls(integration)


async def deliver_to_site(site_id: str, event: dict, visitor_id: str) -> dict:
    """Forward a normalized message event to every enabled integration for a site.

    Returns a summary: {"delivered": int, "failed": int, "conversation_id": str}.
    """
    integrations = storage.list_integrations(site_id)
    delivered = 0
    failed = 0
    conversation = None

    async with httpx.AsyncClient() as client:
        for record in integrations:
            if not record.get("enabled", True):
                continue
            adapter = build_adapter(record)
            if adapter is None:
                continue
            adapter._client = client
            integration_id = record.get("integration_id")

            conversation = storage.get_or_create_conversation(
                site_id, visitor_id, integration_id
            )
            event["conversation_id"] = conversation["conversation_id"]

            try:
                ref = await adapter.deliver(event, conversation)
            except Exception:
                ref = None
            if ref is not None:
                delivered += 1
                # Telegram uses dedicated columns; everything else uses config jsonb.
                provider = record.get("provider")
                if provider == "telegram":
                    storage.update_conversation_integration_ref(
                        conversation["conversation_id"],
                        integration_id,
                        ref.thread_id,
                    )
                else:
                    cfg = {}
                    existing_cfg = conversation.get("config") or {}
                    if isinstance(existing_cfg, dict):
                        cfg = dict(existing_cfg)
                    if ref.destination_id:
                        cfg["destination_id"] = ref.destination_id
                    if ref.thread_id:
                        cfg["thread_id"] = ref.thread_id
                    storage.update_conversation_provider_config(
                        conversation["conversation_id"], **cfg
                    )
            else:
                failed += 1

    if conversation is None:
        conversation = storage.get_or_create_conversation(site_id, visitor_id, None)

    return {
        "delivered": delivered,
        "failed": failed,
        "conversation_id": conversation["conversation_id"],
    }
