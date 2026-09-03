from abc import ABC, abstractmethod


class Storage(ABC):
    """Storage abstraction shared by the hosted (Supabase) and self-hosted (SQLite) backends."""

    # --- owner api keys ---
    @abstractmethod
    def owner_id_from_api_key(self, api_key_hash):
        """Return owner_id for a hashed, non-revoked API key, or None."""

    @abstractmethod
    def insert_owner_api_key(self, owner_id, api_key_hash):
        ...

    @abstractmethod
    def revoke_owner_api_key(self, api_key_hash) -> bool:
        ...

    # --- sites ---
    @abstractmethod
    def site_exists(self, site_id) -> bool:
        ...

    @abstractmethod
    def get_site(self, site_id):
        ...

    @abstractmethod
    def insert_site(self, site_record):
        ...

    @abstractmethod
    def list_sites(self, owner_id):
        ...

    @abstractmethod
    def sites_for_owner(self, owner_id):
        ...

    @abstractmethod
    def increment_messages_received(self, site_id):
        ...

    @abstractmethod
    def increment_replies_sent(self, site_id):
        ...

    # --- integrations ---
    @abstractmethod
    def list_integrations(self, site_id):
        ...

    @abstractmethod
    def get_integration(self, site_id, integration_id):
        ...

    @abstractmethod
    def find_integration_by_webhook_secret(self, secret):
        ...

    @abstractmethod
    def insert_integration(self, record) -> str:
        """Insert and return the integration id."""

    @abstractmethod
    def update_integration(self, site_id, integration_id, fields) -> bool:
        """Update a subset of fields on an existing integration."""

    @abstractmethod
    def delete_integration(self, site_id, integration_id) -> bool:
        ...

    # --- conversations ---
    @abstractmethod
    def get_conversation(self, conversation_id):
        ...

    @abstractmethod
    def get_conversation_by_integration_thread(self, site_id, integration_id, thread_id):
        """Find the conversation bound to (integration_id, thread_id), else None."""

    @abstractmethod
    def get_or_create_conversation(self, site_id, visitor_id, integration_id) -> dict:
        """Return an existing (most recent) conversation for the visitor or create one.

        integration_id binds the conversation to the facing integration so its
        internal conversation handle (thread/topic/root message) routes correctly.
        """

    @abstractmethod
    def update_conversation_integration_ref(self, conversation_id, integration_id, thread_id):
        """Record the integration-bound handle (e.g. Telegram thread id) for a conversation."""

    @abstractmethod
    def create_conversation(self, conversation_id, site_id, visitor_id) -> str:
        ...

    # --- telegram update dedup ---
    @abstractmethod
    def webhook_update_seen(self, update_id) -> bool:
        """Return True if this Telegram update_id was already processed (dedup for retries)."""

    # --- pending replies ---
    @abstractmethod
    def enqueue_reply(self, conversation_id, reply):
        ...

    @abstractmethod
    def pending_replies(self, conversation_id):
        ...

    @abstractmethod
    def delete_pending_reply(self, reply_id):
        ...

    @abstractmethod
    def purge_expired_pending_replies(self, older_than_iso) -> int:
        ...
