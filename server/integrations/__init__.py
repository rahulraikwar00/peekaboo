"""Imported by server.app so all built-in adapters register on startup.

Adding a new channel = write the adapter class, import it here, and add a
`router.register("provider", ClassName)` line. No other plumbing needed.
"""

from server.integrations import router
from server.integrations.discord import DiscordAdapter
from server.integrations.slack import SlackAdapter

router.register("discord", DiscordAdapter)
router.register("slack", SlackAdapter)
