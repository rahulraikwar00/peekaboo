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

    async with httpx.AsyncClient() as client:
        for record in integrations:
            if not record.get("enabled", True):
                continue
            adapter = build_adapter(record)
            if adapter is None:
                continue
            adapter._client = client
            integration_id = record.get("integration_id")

            # One conversation per site/visitor, bound to the facing integration so
            # its internal handle (Telegram thread) routes replies back correctly.
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
            else:
                failed += 1

    if conversation is None:
        conversation = storage.get_or_create_conversation(site_id, visitor_id, None)

    return {
        "delivered": delivered,
        "failed": failed,
        "conversation_id": conversation["conversation_id"],
    }
