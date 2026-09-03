# Peekaboo

Peekaboo connects a website visitor to the website owner through a floating chat widget. Visitors chat with the owner directly from the widget; the owner replies from Telegram.

## How it works

- A visitor opens the floating widget, which connects over WebSocket and is authenticated with a short-lived signed token scoped to their own conversation.
- The visitor's message is sent via `POST /v1/messages` and appears as a new thread in a Telegram group chat (each visitor gets their own topic thread).
- The owner replies in Telegram. A webhook routes the reply back and delivers it live to the visitor's open widget over WebSocket. If the visitor is offline, the reply is stored and delivered when they reconnect.

## Local setup

From the project directory, activate the virtual environment:

```bash
source .venv/bin/activate
```

Install the optional Python dependencies:

```bash
pip install -r requirements.txt
```

Start the Peekaboo server:

```bash
uvicorn server.main:app --reload --port 8000
```

In a second terminal, create a site:

```bash
python -m cli.peekaboo setup
```

The command first logs you in via OAuth (Google/GitHub) the first time, saves a per-owner API key in `.peekaboo/config.json`, then creates a site. Enter the website origin when prompted (for example `https://yourwebsite.com`). It prints an embed snippet and stores the site ID. Add that snippet to the website that should show the chat widget:

```html
<script
  src="http://localhost:8000/widget/pboo.js"
  data-site="YOUR_SITE_ID"
></script>
```

For local testing, serve the example website in another terminal:

```bash
python -m http.server 5000 --directory testweb
```

### Connect your Telegram bot

The owner replies to visitors from Telegram. `peekaboo connect` points a Telegram bot at your Peekaboo server and registers the destination group chat.

Run it and enter the credentials when prompted:

```bash
peekaboo connect
```

You will be asked for:

- **Bot API token** — from [@BotFather](https://t.me/BotFather).
- **Group chat ID** — the id of a topics-enabled group the bot was added to.

The values are sent to the server on connect (the bot token is encrypted and stored in the database; they are per-site credentials, not server environment variables).

Requirements:

- The bot token comes from [@BotFather](https://t.me/BotFather).
- The chat must be a **topics-enabled group** and the bot must be added to it, because Peekaboo deduplicates visitors into Telegram topic threads.
- The server must set `PUBLIC_BASE_URL` so Telegram knows where the webhook lives.

`peekaboo connect` calls `POST /sites/{site_id}/webhook/register` on the server, which validates ownership, saves the (encrypted) bot token, generates a webhook secret, and calls Telegram's `setWebhook`.

## CLI commands

```bash
peekaboo setup    # OAuth login (one time), then create a site and print its embed code
peekaboo connect  # register your Telegram bot + group with a site
peekaboo logout   # revoke the owner API key
```

## Production direction

The production website should install a published CLI package, run `setup` once, paste the generated HTTPS embed snippet into its HTML, and run `connect`. The widget should be served from the hosted Peekaboo server or a CDN. Use `https://` and `wss://` in production, and persist site credentials outside process memory.

### Render deployment

Create a Render Web Service from this repository. The included `render.yaml` uses:

```text
Build: pip install -r requirements.txt
Start: uvicorn server.main:app --host 0.0.0.0 --port $PORT
Health check: /health
```

After deployment, use the Render URL in the website embed:

```html
<script
  src="https://your-service.onrender.com/widget/pboo.js"
  data-site="YOUR_SITE_ID"
></script>
```

Set `PUBLIC_BASE_URL` to your public HTTPS URL so both the widget and the Telegram webhook use the correct host, then run `peekaboo connect` against the deployed server.

## Authentication & ownership

Peekaboo is multi-owner. Anyone can sign in with Google or GitHub and run their own separate chat site. Each owner:

- Has their own sites (`sites.owner_id`).
- Creates sites only with their own API key (minted after OAuth login and stored hashed in `owner_api_keys`), sent via the `X-API-Key` header.
- Registers Telegram integrations only for sites they own.

Per-owner isolation is enforced **server-side**: every site lookup is scoped by the owner id from the API key. Visitors remain anonymous (no account); they can only message an owner when their browser `Origin` matches the site's stored `allowed_origin`. Replies from Telegram are verified with the integration's `webhook_secret` token and routed by `(integration_id, telegram_thread_id)`.

## Secure chat controls

- Visitor websocket access requires a signed `visitor_token` and a matching browser `Origin`.
- Telegram webhook calls require the `X-Telegram-Bot-Api-Secret-Token` header.
- Messages are limited to 4 KB and visitor connections are rate limited and capped per site.
- Updates are deduplicated by Telegram `update_id`; the widget reconnects with bounded exponential backoff.
- The webhook register route encrypts the bot token before storage and requires `PUBLIC_BASE_URL` on the server.
- The server sends `Strict-Transport-Security` and a `frame-ancestors 'none'` Content-Security-Policy.

## Widget customization

The editable widget files live in `server/widget/`:

- `widget.html` contains the chat markup.
- `styles.css` contains the colors, spacing, and responsive layout.
- `pboo.js` loads those files, creates the Shadow DOM, and handles WebSocket messaging.
- `pboo.bundle.js` is the single-file bundle served to websites; regenerate it with `python build_widget.py` after editing the above.

Website owners still install the widget with only the generated `script` tag.

## Backend structure

- `server/main.py` keeps the deployment entry point (`server.main:app`) and compatibility exports for tests.
- `server/app.py` builds the FastAPI app, wires static assets + routes, and adds secure headers.
- `server/routes/` contains HTTP and websocket endpoints grouped by feature.
- `server/services/` contains auth, persistence, security, and signing helpers.
- `server/integrations/` wraps the Telegram Bot API.
- `server/state.py` contains in-memory runtime state used when Supabase is not configured.
- `server/site/` and `server/widget/` contain browser-facing HTML, CSS, and widget assets.

Configure the CLI for the deployed server if the installer is not used:

```bash
export PEEKABOO_SERVER_URL=https://your-service.onrender.com
peekaboo setup
```

### OAuth providers

To allow Google/GitHub sign-in, configure the providers in the Supabase dashboard (Auth → Providers) and add the server's `/auth/oauth/callback` URL as an authorized redirect. Set `PUBLIC_BASE_URL` on the server so the callback URLs use your public domain. The `SUPABASE_URL` and `SUPABASE_SECRET_KEY` env vars connect the server to Supabase; without them the server runs in an in-memory mode suitable for local testing only. In local mode, `peekaboo setup` uses a temporary in-memory owner key instead of a real OAuth provider.

The CLI defaults `PEEKABOO_SERVER_URL` to the deployed server at `https://peekaboo-477i.onrender.com`. Override it with `PEEKABOO_SERVER_URL` when running against a local instance.

### Which HTML is needed?

Website owners do not need to copy `server/widget/index.html`. That file is only a preview page. They only add the script tag printed by `peekaboo setup` to their own HTML:

```html
<script
  src="https://your-service.onrender.com/widget/pboo.js"
  data-site="YOUR_SITE_ID"
></script>
```

## Privacy

Peekaboo is designed to collect as little data as possible. See `PRIVACY.md` for details on what is stored.