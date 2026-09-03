# Peekaboo Privacy

Peekaboo is designed to collect the minimum amount of data required to connect a
website visitor with the website owner.

## What we store

**Visitors**

- A signed visitor token with a short TTL. It is generated client-side and proves
  which conversation a visitor belongs to; it is not tied to a personal account.
- Message bodies sent by visitors via `POST /v1/messages`.
- Reconnect batching so visitors receive replies they missed while offline.
- Privacy-safe per-site counters (messages received, replies sent,
  last-message timestamp) — never message content.

**Owners**

- An owner id and a per-owner API key (stored hashed).
- Sites the owner creates, including the allowed website origin(s) and any widget
  configuration.
- Telegram integrations: a bot token (encrypted with `ENCRYPTION_KEY`), the
  destination chat id, and a webhook secret.

## What we do not store

- No visitor name, email, IP-address logs, or persistent tracking identifiers.
- No message history retained after delivery beyond the pending-reply mechanism
  that is purged once the visitor reconnects.
- Site stats are aggregate and never contain chat content.

## Network behavior

- The visitor widget sends messages over HTTPS and listens on WebSocket `wss://`.
- Replies are delivered from your Telegram group chat back to the widget through
  the server; the server only relays the reply text to the matching conversation.
- Webhook requests are verified with a per-integration secret token; server
  responses and the widget honor rate limits and size caps noted in the README.

## Retention

Pending replies are held only until the visitor is reachable again and are then
deleted. Aggregate per-site counters are retained for display as long as the site
exists.

For any data-deletion or privacy request, contact the operator of the Peekaboo
instance you use.