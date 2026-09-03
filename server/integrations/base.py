from abc import ABC, abstractmethod


class IntegrationAdapter(ABC):
    """Base class for turning a normalized message event into an outbound delivery.

    The core application never needs to know provider internals; it only calls
    `deliver(event)` through the router. Each provider implements its own transport.
    """

    #: Provider key, e.g. "telegram". Matches the `integrations.provider` column.
    provider = "base"

    def __init__(self, integration: dict):
        # `integration` is the raw record for this site's configured integration
        # (id, site_id, provider, destination_id, credentials, enabled, config).
        self.integration = integration

    @abstractmethod
    async def deliver(self, event: dict, conversation: dict) -> bool:
        """Deliver a normalized message event for a conversation.

        Returns True on successful (accepted) delivery, False otherwise.
        """
        raise NotImplementedError
