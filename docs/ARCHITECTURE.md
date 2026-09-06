# Peekaboo — Architecture & Interview Notes

> Short, plain-language answers to the "explain your architecture and the decisions you made" questions, with an annotated data-flow diagram.

---

## What is Peekaboo?

A multi-channel chat widget. A **website visitor** types in a floating widget; the **site owner** replies from **Telegram**, **Discord**, or **Slack**; the reply is pushed back to the widget in near-real time over WebSocket. Offline replies are queued and delivered when the visitor reconnects.

**Elevator pitch:** *"Peekaboo turns your existing Telegram/Discord/Slack channels into a support inbox. Each visitor gets their own conversation, so the owner replies where they already live, and the visitor sees the answer in the widget live — with offline delivery and no message history stored server-side."*

---

## Architecture decisions — asked & answered

### Q1. What is the end-to-end flow?

**A.**

1. Visitor opens the widget → sends a message via **HTTP `POST /v1/messages`**.
2. Server validates (size, schema, honeypot, origin), rate-limits, then forwards to **all enabled channels** via the adapter registry:
   - **Telegram:** creates a forum topic, sends message.
   - **Discord:** sends message to channel via bot token.
   - **Slack:** sends message via bot token.
3. Owner replies in their preferred channel.
4. Channel webhook receives the reply and routes it back.
5. If the visitor's WebSocket is open → push `owner.message` instantly. If not → **enqueue** a pending reply.
6. On reconnect, the visitor socket replays pending replies and purges them.

**Why this split:** *send* over HTTP (client-initiated, fits REST APIs), *receive* over WebSocket (server-initiated push, no polling). Source: `server/routes/messages.py`, `server/integrations/router.py`, `server/routes/webhook.py`, `server/routes/websockets.py`.

---

### Q2. How does the channel abstraction work?

**A.**

- One `IntegrationAdapter` ABC with a single `deliver(event, conversation)` method.
- Adapters: `TelegramAdapter`, `DiscordAdapter`, `SlackAdapter`.
- Registry in `ADAPTERS` dict (keyed by provider name). Adding a new channel = one new adapter + registration.
- Router calls `build_adapter(integration)` to get the right adapter, then `deliver()`.
- Each adapter handles its own: token decryption, API calls, conversation routing.

Source: `server/integrations/base.py` (ABC), `server/integrations/router.py` (registry + dispatch).

---

### Q3. Why a storage abstraction with three backends?

**A.**

- One `Storage` ABC with **Memory** (tests / local dev), **SQLite** (self-host via docker-compose), and **Supabase** (hosted, Postgres + service-role).
- Benefits: **one shared test suite** runs against every backend; swapping persistence is a config change, not a rewrite.
- Conversation routing uses `conversations.config` jsonb for Discord/Slack (flexible), dedicated columns for Telegram (efficient).

Source: `server/services/base_storage.py` (interface), `server/services/storage.py` (selection), `memory_storage.py`, `sqlite_storage.py`, `supabase_storage.py`.

---

### Q4. How do offline replies work?

**A.**

- When the visitor's socket is **not** open, the webhook calls `enqueue_reply(conversation_id, text)` → stored in the **`pending_replies`** table.
- On **websocket connect**, the server selects pending replies for that conversation, pushes each as `owner.message`, and **deletes** the delivered rows.
- Expired rows are garbage-collected after a **7-day TTL** (`PENDING_TTL_SECONDS`).

Source: `server/routes/webhook.py` (enqueue), `server/routes/websockets.py` (replay+purge).

---

### Q5. How does the owner dashboard work?

**A.**

- **Web-only flow:** owner visits `/dashboard`, logs in with Google/GitHub/OAuth, creates sites, configures channels.
- **Session cookie:** signed HMAC token in `peekaboo_session` cookie, 14-day TTL, httpOnly.
- **No CLI:** the setup flow is entirely in the browser. Owner pastes the embed snippet, adds channels via forms.
- **First-time signup:** OAuth auto-creates an `owners` row, mints an API key shown once.

Source: `server/routes/dashboard.py`, `server/services/session.py`, `server/routes/auth.py`.

---

### Q6. What security controls exist?

**A.**

- **Signed visitor tokens:** `base64(payload).HMAC-SHA256(secret)` with 15-min TTL; binds token to `(site_id, visitor_id)`.
- **Origin checks:** allowed-origin allowlist (exact, `*.subdomain` wildcards, dev localhost).
- **Encrypted credentials:** bot tokens encrypted with **Fernet** (`ENCRYPTION_KEY`) before storage; decrypted only at send time.
- **Hashed API keys:** only SHA-256 hash stored; revoked by setting `revoked_at`.
- **Session cookies:** HMAC-signed, httpOnly, SameSite=Lax.
- **Webhook verification:** Telegram `X-Telegram-Bot-Api-Secret-Token`, Discord Ed25519 signature, Slack `X-Slack-Signature` HMAC.
- **Rate limiting:** per-IP, per-site, per-visitor sliding windows.
- **Privacy by design:** message bodies are **never stored** server-side.

---

### Q7. Why bundle the widget into one JS file + Shadow DOM?

**A.**

- **Single `<script>` install** — trivial for any site.
- **Shadow DOM** isolates the widget's CSS/HTML from the host page → no style bleed.
- `build_widget.py` inlines HTML/CSS/JS into `pboo.bundle.js`. Edit sources → `python build_widget.py` to regenerate.

Source: `server/widget/pboo.js`, `build_widget.py`.

---

### Q8. How do you handle multiple channel types?

**A.**

- **Telegram:** Forum topic per visitor. Webhook with secret token. Dedup by `update_id`.
- **Discord:** Bot token + channel ID. Ed25519 signature verification. Two-way via interaction endpoint.
- **Slack:** Bot token + signing secret + channel ID. `X-Slack-Signature` HMAC verification. Events API webhook.
- **Extensibility:** new channels require one adapter class + registration. No changes to core logic.

---

## Data-flow diagram (annotated Mermaid)

```mermaid
flowchart TD
    subgraph VISITOR_SIDE["Visitor browser"]
        V[Widget in Shadow DOM<br/>server/widget/pboo.js] -->|1. visitor.connected w/ signed token| WS_SOCK
        V -->|2. HTTP POST /v1/messages| MSG_ROUTE
    end

    subgraph SERVER["Peekaboo server (FastAPI)"]
        MSG_ROUTE[POST /v1/messages<br/>server/routes/messages.py] -->|validate + origin + rate-limit| DELIVER
        DELIVER[deliver_to_site<br/>server/integrations/router.py] -->|get_or_create_conversation| CONV[(conversations<br/>Supabase/SQLite/Memory)]
        DELIVER --> TELEGRAM
        DELIVER --> DISCORD
        DELIVER --> SLACK
        
        TELEGRAM[TelegramAdapter<br/>server/integrations/telegram.py]
        DISCORD[DiscordAdapter<br/>server/integrations/discord.py]
        SLACK[SlackAdapter<br/>server/integrations/slack.py]

        WS_SOCK[WS /ws/visitor/{site}<br/>server/routes/websockets.py] -->|pending replay|-.|PENDING_BUF| PENDING[(pending_replies)]
        WS_SOCK -.->|deliver again to visitor| V

        WEBHOOK_T[POST /v1/telegram/webhook<br/>server/routes/webhook.py] -->|dedup update_id| UPD[(telegram_updates)]
        WEBHOOK_D[POST /v1/discord/webhook<br/>server/routes/webhook_discord.py]
        WEBHOOK_S[POST /v1/slack/webhook<br/>server/routes/webhook_slack.py]
        
        WEBHOOK_T -->|match integration + thread| CONV
        WEBHOOK_D -->|match integration + channel| CONV
        WEBHOOK_S -->|match integration + channel| CONV
    end

    subgraph EXTERNAL["External channels"]
        TG[Telegram<br/>Topics-enabled group]
        DC[Discord<br/>Bot channel]
        SL[Slack<br/>App channel]
    end

    TELEGRAM -->|3. createForumTopic / sendMessage| TG
    DISCORD -->|3. POST /channels/id/messages| DC
    SLACK -->|3. chat_postMessage| SL
    
    TG -.->|4. webhook callback| WEBHOOK_T
    DC -.->|4. interaction webhook| WEBHOOK_D
    SL -.->|4. events API| WEBHOOK_S
    
    WEBHOOK_T -->|5. owner.message to socket| WS_SOCK
    WEBHOOK_D -->|5. owner.message to socket| WS_SOCK
    WEBHOOK_S -->|5. owner.message to socket| WS_SOCK
    
    WEBHOOK_T -->|5b. enqueue if offline| PENDING
    WEBHOOK_D -->|5b. enqueue if offline| PENDING
    WEBHOOK_S -->|5b. enqueue if offline| PENDING

    classDef storage fill:#eef3f5,stroke:#8aa4b0;
    class CONV,PENDING,UPD storage;
    classDef ext fill:#fdf0ea,stroke:#d98a63;
    class TG,DC,SL ext;
```

---

## Key file map

| Concern | File | Purpose |
|---------|------|---------|
| Visitor widget | `server/widget/pboo.js`, `widget.html`, `styles.css` | Send via fetch, receive via WS, localStorage persistence, Shadow DOM |
| Widget bundle | `build_widget.py` | Inline HTML/CSS/JS → `pboo.bundle.js` |
| Receive message | `server/routes/messages.py` | Validate, honeypot, origin, rate-limit, deliver, mint token + idempotency key |
| Delivery router | `server/integrations/router.py` | ADAPTERS registry, dispatch to adapters |
| Telegram adapter | `server/integrations/telegram.py` | Token decrypt, webhook set, topic create, send, stale-thread heal |
| Discord adapter | `server/integrations/discord.py` | Bot token delivery, Ed25519 signature verification |
| Slack adapter | `server/integrations/slack.py` | Bot token delivery, HMAC signature verification |
| Telegram webhook | `server/routes/webhook.py` | Secret auth, dedup, route reply back, offline enqueue, GC |
| Discord webhook | `server/routes/webhook_discord.py` | Ed25519 verification, route replies |
| Slack webhook | `server/routes/webhook_slack.py` | HMAC verification, route replies |
| Visitor WebSocket | `server/routes/websockets.py` | Token auth, socket registry, pending replay, WS rate limit |
| Owner dashboard | `server/routes/dashboard.py` | Web-only setup, channel management, snippet copy |
| Dashboard templates | `server/site/dashboard/` | login, welcome, index, site HTML |
| Session cookies | `server/services/session.py` | HMAC-signed cookies for owner auth |
| Storage interface | `server/services/base_storage.py`, `storage.py` | Pluggable backends + facade |
| Backends | `memory_storage.py`, `sqlite_storage.py`, `supabase_storage.py` | Memory / SQLite / Supabase |
| Auth | `server/routes/auth.py` | OAuth (PKCE) + API key login + session cookies |
| Schema | `supabase_schema.sql` | sites, owners, integrations, conversations, pending_replies, RLS |
| Security | `services/signing.py`, `domain.py`, `crypto.py`, `security.py`, `session.py` | Tokens, origins, Fernet, key hashing, session cookies |
| Rate limit | `services/ratelimit.py`, `server/state.py` | Sliding-window limiter |

---

## Gotchas / things to improve

- **Rate limiter is process-local** — first thing to move to Redis before scaling workers.
- **Message bodies are never stored** (privacy win) — the trade-off is there's **no server-side history**, so a brand-new device can't fetch old conversations; only the browser's `localStorage` holds them.
- **Telegram requires a topics-enabled supergroup** — `createForumTopic` fails cleanly otherwise.
- **Discord interactions endpoint** — bot owner must manually paste the webhook URL in the Discord developer portal after saving the integration.
- **Slack events URL** — bot owner must manually paste the webhook URL in the Slack app config after saving the integration.
