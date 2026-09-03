import httpx

from server.integrations.telegram import TelegramAdapter
from server.services import storage


def build_adapter(integration: dict):
    """Return the adapter matching an integration's provider, or None if unknown."""
    provider = integration.get("provider")
    if provider == "telegram":
        return TelegramAdapter(integration)
    return None


async def deliver_to_site(site_id: str, event: dict, visitor_id: str) -> dict:
    """Forward a normalized message event to every enabled integration for a site.

    Returns a summary: {"delivered": int, "failed": int, "conversation_id": str}.
    """
    integrations = storage.list_integrations(site_id)
    delivered = 0
    failed = 0
    conversation = None

    # Conversation is shared across integrations for a site/visitor so the
    # thread-per-conversation identity is consistent.
    conversation = storage.get_or_create_conversation(site_id, visitor_id)
    event["conversation_id"] = conversation["conversation_id"]

    async with httpx.AsyncClient() as client:
        for record in integrations:
            if not record.get("enabled", True):
                continue
            adapter = build_adapter(record)
            if adapter is None:
                continue
            adapter._client = client
            try:
                ok = await adapter.deliver(event, conversation)
            except Exception:
                ok = False
            if ok:
                delivered += 1
            else:
                failed += 1

    return {
        "delivered": delivered,
        "failed": failed,
        "conversation_id": conversation["conversation_id"],
    }
