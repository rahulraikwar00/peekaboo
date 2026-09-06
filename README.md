# Peekaboo

Peekaboo connects a website visitor to the website owner through a floating chat widget. Visitors chat with the owner directly from the widget; the owner replies from **Telegram**, **Discord**, or **Slack**.

## How it works

1. **Owner** visits the web dashboard, logs in with Google/GitHub/API key, creates a site, and configures one or more channels (Telegram/Discord/Slack).
2. **Visitor** opens the floating widget on the website, sends a message via `POST /v1/messages`.
3. Message is forwarded to all enabled channels (Telegram topic thread, Discord message, Slack message).
4. **Owner** replies in their preferred channel. A webhook routes the reply back and delivers it live to the visitor's open widget over WebSocket. If the visitor is offline, the reply is stored and delivered when they reconnect.

## Quick start

```bash
source .venv/bin/activate
pip install -r requirements.txt
uvicorn server.main:app --reload --port 8000
```

Open `http://localhost:8000` in your browser to access the dashboard.

### First-time setup

1. Open `http://localhost:8000`
2. Log in with Google, GitHub, or paste an API key
3. Create a site (enter your website origins)
4. Copy the embed snippet
5. Paste the snippet on your website
6. Add a channel (Telegram, Discord, or Slack) by entering the required credentials

### Embed your website

Paste this snippet in your HTML (before `</body>` or in `<head>`):

```html
<script src="http://localhost:8000/widget/pboo.js" data-site="YOUR_SITE_ID"></script>
```

## Channels

### Telegram

- **Bot token**: From [@BotFather](https://t.me/BotFather)
- **Chat ID**: A topics-enabled supergroup where the bot is added
- Webhook is automatically configured when you save the channel

### Discord

- **Bot token**: From the Discord Developer Portal
- **Channel ID**: The channel to receive messages
- **Public key**: From the bot's settings (for signature verification)
- After saving, paste the webhook URL in the Discord developer portal's "Interactions Endpoint URL"

### Slack

- **Bot token**: `xoxb-...` from your Slack app
- **Signing secret**: From the Slack app's "Basic Information"
- **Channel ID**: The channel to receive messages
- After saving, paste the webhook URL in your Slack app's "Event Subscriptions Request URL"

## Environment variables

| Variable | Description |
|----------|-------------|
| `ENCRYPTION_KEY` | Fernet key for encrypting credentials |
| `WIDGET_SIGNING_SECRET` | Secret for signing visitor tokens |
| `PEEKABOO_SERVER_URL` | Public URL of the server |
| `SUPABASE_URL` | Supabase project URL (optional, for hosted storage) |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service role key |
| `GOOGLE_CLIENT_ID` | Google OAuth client ID (optional) |
| `GOOGLE_CLIENT_SECRET` | Google OAuth client secret (optional) |
| `GITHUB_CLIENT_ID` | GitHub OAuth client ID (optional) |
| `GITHUB_CLIENT_SECRET` | GitHub OAuth client secret (optional) |

## Backend structure

- `server/main.py` — deployment entry point
- `server/app.py` — FastAPI app, routes, middleware
- `server/routes/` — HTTP and websocket endpoints
- `server/services/` — auth, persistence, security, signing
- `server/integrations/` — channel adapters (Telegram, Discord, Slack)
- `server/routes/dashboard.py` — owner web dashboard
- `server/site/dashboard/` — dashboard HTML templates
- `server/widget/` — embeddable widget files
- `server/state.py` — in-memory state (when Supabase is not configured)

## Privacy

Peekaboo collects minimal data. Message bodies are never stored server-side. See `PRIVACY.md` for details.
