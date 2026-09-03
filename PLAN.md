# Peekaboo v2 — Implementation Plan

Two-way chat widget: visitors message a website owner, the owner replies from Telegram, and
the reply is delivered back to the visitor's widget in near-real-time (with offline delivery
when the visitor reconnects).

## Resolved product model

- **Visitor → Owner:** visitor POSTs a message (HTTP); the server forwards it to the owner's
  Telegram using a **thread-per-conversation** inbox (per-visitor inbox).
- **Owner → Visitor:** owner replies in Telegram; the server receives the reply via a
  **Telegram webhook**, routes it by `thread_id → conversation`, and pushes it to the visitor's
  widget over a **receiving WebSocket**.
- **Offline replies:** if the visitor's socket is closed, the reply is persisted in a
  `pending_replies` queue and **delivered + purged** when the visitor reconnects.

## Architecture

```
VISITOR (browser)
   │  POST /v1/messages (send)                      WS receive replies ─► widget
   ▼                                                                          ▲
┌──────────────────┐   sendMessage    ┌──────────────────┐   createForumTopic ┌┴──────────┐
│ Message API      │ ───────────────▶ │ Telegram Bot API │ ◀─────────────────│ Telegram  │
│ validate/origin/ │                  └────────┬─────────┘                    │ OWNER     │
│ ratelimit/honeypot│                          │                              └───────────┘
└────────┬─────────┘                           ▼      reply in thread
         │ create conversation + thread        │
         ▼                                     ▼
┌─────────────────────────────┐       ┌───────────────────┐
│ Telegram Webhook endpoint   │ ◀──── │ webhook message   │
│ /v1/telegram/webhook        │       │ (thread_id)       │
│ secret-token verify         │       └───────────────────┘
│ thread→conversation map     │
│ deliver to socket / enqueue pending
└─────────────────────────────┘
```

Monolith for the MVP. No queue / Redis / K8s until scaling triggers are hit (see below).

## DB schema

**Deprecated:** `messages` table (stop writing). `conversations` re-scoped to metadata only.

- **sites** — expand: `allowed_origins jsonb` (array), `widget_config jsonb`.
- **integrations** (new):
  `id, site_id (FK), provider ('telegram'), destination_id (group chat_id),
   credentials (Fernet-encrypted bot token), webhook_secret, enabled,
   config jsonb, created_at, updated_at`
- **conversations** (re-scoped, metadata only):
  `conversation_id, site_id, visitor_id, telegram_thread_id, created_at, last_activity_at`
- **site_stats** (new, privacy-safe counts):
  `site_id, messages_received, replies_sent, last_message_at`
- **pending_replies** (new — offline reply queue):
  `id, conversation_id, reply text, created_at, delivered_at NULL`
  Owner-reply bodies live here only until delivered (or GC'd after TTL), never as history.

Storage backend: a `Storage` interface with `SqliteStorage` (self-host) + `SupabaseStorage`
(hosted), sharing one test suite.

## API

**Public (visitor):**
- `POST /v1/messages` — send visitor message
- `GET /v1/widget/config/{site_id}` — non-secret widget config
- `WS /ws/visitor/{site_id}` — receive owner replies

**Integration (Telegram → us):**
- `POST /v1/telegram/webhook` — verify `X-Telegram-Bot-Api-Secret-Token`; route reply

**Owner (X-API-Key):**
- `POST/GET /v1/sites`, `GET /v1/sites/{id}` (+ stats)
- `POST/GET/DELETE /v1/sites/{id}/integrations`
- `POST /v1/sites/{id}/webhook/register` — set webhook + secret token

## Widget

- Shadow DOM + single bundle (`build_widget.py`), framework-independent.
- **Send:** `fetch(POST /v1/messages)` with `{site_id, visitor_id, name?, message, page?, referrer?}`.
- **Receive:** open WS `/ws/visitor/{site_id}`; on open send `visitor.connected {visitor_id, conversation_id?}`;
  handle `owner.message`, `pending.delivered`; reconnect with bounded backoff.
- `conversation_id` kept client-side (localStorage, keyed by site) so a returning visitor resumes
  the same conversation and picks up pending replies.
- Trim bundle (drop simulation/preview bloat) toward <= ~30 KB gzip.
- localStorage: visitor_id, conversation_id, draft, ui prefs only.

## Offline reply delivery sequence

1. Webhook receives owner reply → map `message_thread_id` → conversation.
2. If visitor socket open → push `owner.message`, `replies_sent++`, done.
3. If closed → `INSERT pending_replies` (reply, conversation_id, ttl).
4. Visitor later reconnects → WS `visitor.connected` carries conversation_id → server
   `SELECT pending_replies` for it → push each over socket → **DELETE delivered rows**.
5. GC clears `pending_replies` older than TTL (default 7 days) — runs on write + periodic.

## Telegram integration + webhook

- **Setup (owner):** BotFather create bot → create **topics-enabled supergroup**, add bot as
  admin → `peekaboo connect` submits bot token + **group chat_id**.
  - Server calls `setWebhook{url, secret_token}`, stores encrypted token + secret.
  - Credential encryption: **Fernet**, key from `ENCRYPTION_KEY` env; never in widget/logs/responses.
- **Forward:** on first message of a conversation call `createForumTopic` → `telegram_thread_id`;
  send message into thread.
- **Reply:** parse webhook update; owner message in known thread → map → deliver.
- **Fallback:** if topics unavailable, fall back to `reply_to_message` mapping. Documented.

## Security (MVP)

Origin allowlist + suffix matcher (exact / `*.subdomain` / localhost-dev); per-IP + per-site +
per-visitor rate limits; honeypot; size limits; Fernet credential encryption; webhook
secret-token verification; thread-id integrity (only threads we created); no message-body
logging; secure headers (HSTS, frame-ancestors → allowed origins); HTTPS.
Defer: CAPTCHA, AI spam, WAF, multi-region abuse detection.

## Privacy model

- **Visitor messages: never stored** (memory only, dropped after forwarding).
- **Owner replies: held ONLY when undelivered**, in `pending_replies`, purged on delivery or after
  TTL (7 days). Never a history.
- `site_stats`: counts/timestamps only.
- PRIVACY.md states this honestly — distinguishing "no message history storage" from
  "the server never receives messages."

## Self-host + Docker

- `docker-compose.yml` with a SQLite volume + `ENCRYPTION_KEY` env.
- Storage interface shared between hosted (Supabase) and self-hosted (SQLite).

## Testing + CI/CD

- pytest + FastAPI TestClient with in-memory resets; mocked-`httpx` adapter tests; shared
  backend test suite (SQLite vs Supabase).
- Add tests for: webhook auth, thread→conversation mapping, concurrent routing,
  offline enqueue→deliver→purge, privacy (no body persisted/logged), TTL GC.
- GitHub Actions: ruff, pytest → deploy Render.

## Scaling triggers (defer infrastructure)

Monolith is correct for thousands of messages/day. Add Redis rate-limit + a queue (RQ/arq) for
async delivery **only when**: outbound latency/failures block the request path, retries are
needed, or API workers scale horizontally. DB-backed `pending_replies` already survives
restarts/scaling; the in-memory rate-limiter is the first thing to move off-process.

## Milestones

- **M1 — PoC (two-way loop):** `POST /v1/messages` → Telegram thread; owner reply via webhook →
  pushed to open socket; hardcoded site.
- **M2 — Rep MVP:** Storage interface (SQLite + Supabase), sites/integrations CRUD, origin
  verification, webhook secret auth, credential encryption, rate limits, honeypot,
  offline pending-replies + purge + GC, widget trimming, `peekaboo connect`, tests, docs.
- **M3–M5:** beta (5–20 devs) → open source → optional Product Hunt.

## Explicitly NOT built now

Webhooks-for-owner beyond Telegram's own, Discord/Slack/Email, web dashboard, analytics beyond
counts, multi-destination routing, team inbox, AI spam/summaries/auto-replies, CRM, routing rules.
