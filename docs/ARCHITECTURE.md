# Peekaboo — Architecture & Interview Notes

> Short, plain-language answers to the "explain your architecture and the decisions you made" questions, with an annotated data-flow diagram. Built for interview prep.

---

## What is Peekaboo?

A two-way chat widget. A **website visitor** types in a floating widget; the **site owner** replies from a **Telegram forum group**; the reply is pushed back to the widget in near-real time over WebSocket. Offline replies are queued and delivered when the visitor reconnects.

**Elevator pitch:** *"Peekaboo turns your existing Telegram group into a support inbox. Each visitor gets their own topic, so the owner replies where they already live, and the visitor sees the answer in the widget live — with offline delivery and no message history stored server-side."*

---

## Architecture decisions — asked & answered

### Q1. What is the end-to-end flow?

**A.**

1. Visitor opens the widget → sends a message via **HTTP `POST /v1/messages`**.
2. Server validates (size, schema, honeypot, origin), rate-limits, then forwards to Telegram via **`sendMessage`** into a per-visitor **forum topic** (`message_thread_id`).
3. Owner replies **inside that topic** in Telegram.
4. Telegram calls our **webhook** (`POST /v1/telegram/webhook`), which routes the reply back.
5. If the visitor's WebSocket is open → push `owner.message` instantly. If not → **enqueue** a pending reply.
6. On reconnect, the visitor socket replays pending replies and purges them.

**Why this split:** *send* over HTTP (client-initiated, fits rest APIs), *receive* over WebSocket (server-initiated push, no polling). Source: `server/routes/messages.py`, `server/integrations/telegram.py`, `server/routes/webhook.py`, `server/routes/websockets.py`.

---

### Q2. Why one Telegram forum topic per visitor, and why route by `(integration_id, thread_id)`?

**A.**

- A forum topic becomes the owner's **per-visitor inbox**. The topic **title carries the visitor's name** (`visitor_name`), so the owner knows who it is at a glance and the message body stays clean (just the raw text, no header boilerplate).
- Routing is keyed by the tuple **`(integration_id, thread_id)`**, never `thread_id` alone. Two different bots/groups can reuse the *same numeric* thread id; the tuple prevents cross-group collisions.
- If a topic is deleted (stale thread) the adapter **self-heals**: it recreates a fresh topic and retries the send once, instead of failing or emitting an unroutable threadless message.

Source: `server/integrations/telegram.py:67-133` (thread create + stale-thread recovery), `_create_thread` names from `visitor_name`.

---

### Q3. Why WebSocket instead of polling?

**A.**

- Replies are **server-initiated** events; WebSocket gives low-latency push without a poll loop.
- An earlier version **polled** owner status every 15s; we replaced it with a WebSocket/status push (commit `1a4d4b1`).
- The widget sends over **fetch**, receives over **WS** — each direction uses the simplest fitting mechanism.
- Reconnects use the signed `visitor_token` returned by the send endpoint, and pending replies are replayed on connect.

Source: `server/widget/pboo.js:208-252` (WS receive), `server/routes/websockets.py`.

---

### Q4. Why a storage abstraction with three backends?

**A.**

- One `Storage` ABC with **Memory** (tests / local dev), **SQLite** (self-host via docker-compose), and **Supabase** (hosted, Postgres + service-role).
- Benefits: **one shared test suite** runs against every backend; swapping persistence is a config change (`STORAGE_BACKEND` / env), not a rewrite.
- Selection resolves **per call** (`get_storage()`) so tests can hot-swap the client between requests.

Source: `server/services/base_storage.py` (interface), `server/services/storage.py:21-30` (selection), `memory_storage.py`, `sqlite_storage.py`, `supabase_storage.py`.

---

### Q5. How do offline replies work?

**A.**

- When the visitor's socket is **not** open, the webhook calls `enqueue_reply(conversation_id, text)` → stored in the **`pending_replies`** table.
- On **websocket connect**, the server selects pending replies for that conversation, pushes each as `owner.message`, and **deletes** the delivered rows.
- Expired rows are garbage-collected after a **7-day TTL** (`PENDING_TTL_SECONDS`), run opportunistically on webhook calls.

Source: `server/routes/webhook.py:66` (enqueue), `server/routes/websockets.py:84-90` (replay+purge), `webhook.py:107-115` (GC).

---

### Q6. Why a webhook instead of polling Telegram?

**A.**

- **Push not pull:** Telegram calls us the moment the owner replies (low latency, no long-poll loop).
- **Auth:** each integration has a random `webhook_secret`; Telegram sends it as `X-Telegram-Bot-Api-Secret-Token` and we verify with constant-time compare (`hmac.compare_digest`).
- **Dedup:** Telegram retries until acked, so we guard with the **`telegram_updates`** table keyed on `update_id` (a re-delivered update returns early). Supabase treats a concurrent duplicate insert as "already seen."

Source: `server/routes/webhook.py:16-44`, `server/services/supabase_storage.py:233-250`.

---

### Q7. How do you rate-limit and what's the scaling concern?

**A.**

- In-process **sliding-window limiter** (`defaultdict(deque)` of monotonic timestamps), three key types:
  - per-IP `20 / 10s`
  - per-site `120 / 3600s`
  - per-visitor `5 / 60s`
- The WebSocket path has its own inbound `20 / 10s` window and a per-site visitor cap (`1000`).
- **Scaling caveat (honest):** the limiter lives in one process (`server.state`). If we scaled to multiple workers we'd move it to **Redis** or a shared store — it's the first thing to move off-process. `pending_replies` stays DB-backed so it already survives restarts.

Source: `server/services/ratelimit.py`, `server/state.py`, `server/routes/messages.py:74-87`.

---

### Q8. What security controls exist?

**A.**

- **Signed visitor tokens:** `base64(payload).HMAC-SHA256(secret)` with 15-min TTL; binds token to `(site_id, visitor_id)` to prevent cross-site replay; verified constant-time.
- **Origin checks:** allowed-origin allowlist (exact, `*.subdomain` wildcards, dev localhost). Treated as a *convenience boundary*, not the sole control — Origin is spoofable by non-browser clients.
- **Encrypted credentials:** Telegram bot tokens encrypted with **Fernet** (`ENCRYPTION_KEY`) before storage; decrypted only at send time.
- **Hashed API keys:** only the SHA-256 hash of the owner API key is stored; revoked by setting `revoked_at`.
- **Honeypot:** hidden `website` field; bots that fill it are silently accepted (200) and dropped.
- **Headers:** HSTS + CSP `frame-ancestors 'none'` on every response.
- **RLS on by default** in Supabase with no public policies — only the service-role key touches data.
- **Privacy by design:** message bodies are **never stored** (`save_message` is a no-op); only counts in `site_stats`, and replies only in `pending_replies` until delivered/TTL.

Source: `server/services/signing.py`, `domain.py`, `crypto.py`, `security.py`, `server/routes/messages.py:58-60`, `server/app.py:43-55`, `supabase_schema.sql`.

---

### Q9. Why bundle the widget into one JS file + Shadow DOM?

**A.**

- **Single `<script>` install** (`<script src=".../widget/pboo.js" data-site="...">`) — trivial for any site.
- **Shadow DOM** isolates the widget's CSS/HTML from the host page → no style bleed, framework-independent.
- `build_widget.py` inlines `widget.html`, `styles.css`, and `pboo.js` into `pboo.bundle.js` as `WIDGET_MARKUP`/`WIDGET_STYLES` globals + loader. Edit sources → `python build_widget.py` to regenerate.

Source: `server/widget/pboo.js:33-39`, `build_widget.py`.

---

### Q10. Why did you retire the legacy operator socket in favor of Telegram?

**A.**

- Owners **already live in Telegram**, so replying there is zero new friction. The previous path had an operator WebSocket (`/ws/operator`) with a `/reply` relay and a `broadcast_owner_status` presence broadcast.
- We replaced that whole layer with the **Telegram webhook reply path** — fewer moving parts, real push, natural per-visitor inbox.
- Legacy remains only as dead schema (`operator_token_hash`) and vestigial WS-frame handling; the operator endpoint/tests keep the old response only to confirm it's gone.

---

### Q11. What were the recent fixes, and what did you learn?

**A.**

- **Duplicate sends:** repeated `peekaboo connect` runs created multiple identical Telegram integrations, so a message was forwarded once per integration (the "5+ texts" bug). **Fix:** `webhook_register` now **upserts** — one Telegram integration per site — and configures Telegram *before* persisting so a failed setup neither wipes a working integration nor leaves a half-written row.
- **Stale-thread 502:** a deleted topic left a stale `telegram_thread_id`; `deliver` failed instead of recovering. **Fix:** auto-recreate the topic and retry once.
- **Topic naming:** `visitor_name` was empty-string from Pydantic, so `or "New conversation"` always fell back. **Fix:** strip the name; fall back only when truly empty. The message body now shows just the raw text; the identity lives in the topic title.
- **UI glitch + lost transcript:** duplicate send/submit handlers caused jank, and reload wiped the chat. **Fix:** cleaned to a single handler with an animated (non-flicker) name prompt; persisted `visitor_id`, `name`, and the **chat log in `localStorage`** so reloads restore the conversation.

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
        DELIVER --> TELEG_ADAPTER
        TELEG_ADAPTER[TelegramAdapter<br/>server/integrations/telegram.py]

        WS_SOCK[WS /ws/visitor/{site}\nserver/routes/websockets.py] -->|pending replay|-.|PENDING_BUF| PENDING[(pending_replies)]
        WS_SOCK -.->|deliver again to visitor| V

        WEBHOOK[POST /v1/telegram/webhook<br/>server/routes/webhook.py] -->|dedup update_id| UPD[(telegram_updates)]
        WEBHOOK -->|match integration_id + thread_id| CONV
    end

    subgraph TELEGRAM["Telegram (external)"]
        TG_GROUP[Topics-enabled group<br/>one forum topic per visitor]
        OWNER[Owner replies in topic]
    end

    TELEG_ADAPTER -->|3. createForumTopic / sendMessage<br/>message_thread_id| TG_GROUP
    OWNER -->|4. reply| TELEG_ADAPTER_2[Telegram push]
    TELEGRAM -.->|5. X-Telegram-Bot-Api-Secret-Token| WEBHOOK
    WEBHOOK -->|6. owner.message to open socket| WS_SOCK
    WEBHOOK -->|6b. enqueue if offline| PENDING

    classDef storage fill:#eef3f5,stroke:#8aa4b0;
    class CONV,PENDING,UPD storage;
    classDef ext fill:#fdf0ea,stroke:#d98a63;
    class TG_GROUP,OWNER ext;
```

**Annotations (step by step):**

| # | What | Where | Why it matters |
|---|------|-------|----------------|
| 1 | `visitor.connected` with signed token | `websockets.py:71-79` | Token binds socket to a real `visitor_id`; no raw client-id trust. |
| 2 | `POST /v1/messages` | `messages.py:39-110` | Size cap, Pydantic + honeypot, origin check, rate limit, delivery, token mint. Body never stored. |
| 3 | `createForumTopic` + `sendMessage` | `telegram.py:91-133` | One topic per visitor; stale-thread self-heal recreates + retries. |
| 4 | Owner replies in-topic | `telegram.py` / `webhook.py` | Owner identity = topic title; body is raw text only. |
| 5 | Webhook callback w/ secret token | `webhook.py:16-44` | Constant-time secret check + `update_id` dedup. |
| 6 | Push `owner.message` to open socket | `webhook.py:84-104` | Matches only sockets for the correct `conversation_id`. |
| 6b | Enqueue if offline | `webhook.py:66`, `websockets.py:84-90` | Durable offline delivery; purged on delivery or 7-day TTL. |

---

## Key file map

| Concern | File | Purpose |
|---------|------|---------|
| Visitor widget | `server/widget/pboo.js`, `widget.html`, `styles.css` | Send via fetch, receive via WS, localStorage persistence, Shadow DOM |
| Widget bundle | `build_widget.py` | Inline HTML/CSS/JS → `pboo.bundle.js` |
| Receive message | `server/routes/messages.py` | Validate, honeypot, origin, rate-limit, deliver, mint token |
| Delivery router | `server/integrations/router.py` | Dispatch to adapters; one conversation per site/visitor/integration |
| Telegram adapter | `server/integrations/telegram.py` | Token decrypt, webhook set, topic create, send, stale-thread heal |
| Telegram webhook | `server/routes/webhook.py` | Secret auth, dedup, route reply back, offline enqueue, GC |
| Visitor WebSocket | `server/routes/websockets.py` | Token auth, socket registry, pending replay, WS rate limit |
| Owner webhook register | `server/routes/webhook_register.py` | Upsert one integration per site; configure-before-persist |
| Storage interface | `server/services/base_storage.py`, `storage.py` | Pluggable backends + facade |
| Backends | `memory_storage.py`, `sqlite_storage.py`, `supabase_storage.py` | Memory / SQLite / Supabase |
| Auth | `server/routes/auth.py`, `services/auth.py` | OAuth (PKCE) + hashed API keys |
| Schema | `supabase_schema.sql` | sites, integrations, conversations, telegram_updates, pending_replies, site_stats, RLS |
| Security | `services/signing.py`, `domain.py`, `crypto.py`, `security.py` | Tokens, origins, Fernet, key hashing |
| Rate limit | `services/ratelimit.py`, `server/state.py` | Sliding-window limiter |

---

## Gotchas / things I'd improve (for depth)

- **Rate limiter is process-local** — first thing to move to Redis before scaling workers.
- **Message bodies are never stored** (privacy win) — the trade-off is there's **no server-side history**, so a brand-new device can't fetch old conversations; only the browser's `localStorage` holds them.
- **Topic is named "New conversation"** whenever a visitor skips the optional name prompt — by design (non-blocking), but the owner can rename the topic in Telegram.
- **Requires a topics-enabled supergroup** and the bot as a member — `createForumTopic` fails cleanly otherwise (we fail closed rather than emit a stray threadless message).
