from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class ConversationRef:
    """Provider-neutral handle to the remote conversation.

    Each integration adapter maps its own back-channel (Webhook, SDK, etc.)
    to and from this handle so the core routing stays provider-agnostic.
    """

    site_id: str
    conversation_id: str
    integration_id: str
    provider: str
    #: Provider-specific routing key, e.g. Telegram "chat_id".
    destination_id: str = ""
    #: Provider-specific conversation handle, e.g. Telegram "message_thread_id".
    thread_id: str = ""
    #: Provider-specific fallback, e.g. Telegram root message id for reply_to routing.
    root_message_id: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)

    @property
    def routing_key(self) -> tuple:
        """Tuple used to uniquely identify the remote conversation on this integration."""
        return (self.integration_id, self.destination_id, self.thread_id)


class IntegrationAdapter(ABC):
    """Base class for turning a normalized message event into an outbound delivery.

    The core application never needs to know provider internals; it only calls
    `deliver(event, conversation)` through the router. Each provider implements its
    own transport and returns the `ConversationRef` used to route replies back.
    """

    #: Provider key, e.g. "telegram". Matches the `integrations.provider` column.
    provider = "base"

    def __init__(self, integration: dict):
        # `integration` is the raw record for this site's configured integration
        # (id, site_id, provider, destination_id, credentials, enabled, config).
        self.integration = integration

    @abstractmethod
    async def deliver(self, event: dict, conversation: dict) -> ConversationRef:
        """Deliver a normalized message event for a conversation.

        Returns the `ConversationRef` to route replies back through this provider,
        or raises/returns None on failure.
        """
        raise NotImplementedError