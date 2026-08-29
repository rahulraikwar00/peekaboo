# Peekaboo

Peekaboo connects a website visitor to the website owner through a floating chat widget and a terminal client.

## Local setup

From the project directory, activate the virtual environment:

```bash
source .venv/bin/activate
```

Once the server is running, the CLI can be installed from the same server:

```bash
curl -fsSL http://localhost:8000/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
peekaboo setup
```

The installer creates a local `peekaboo` command. It does not automatically start a chat session; run `peekaboo listen` when you are ready to receive visitor messages.

Start the Peekaboo server:

```bash
uvicorn server.main:app --reload --port 8000
```

In a second terminal, create a site:

```bash
python -m cli.peekaboo setup
```

The command first logs you in via OAuth (Google/GitHub) the first time, saves a per-owner API key in `.peekaboo/config.json`, then creates a site. It prints an embed snippet and stores the site ID and operator token. Add that snippet to the website that should show the chat widget:

During setup, enter the website origin when prompted, for example `https://yourwebsite.com`. This is stored for that site and used to authorize its widget connection.

```html
<script
  src="http://localhost:8000/widget/pboo.js"
  data-site="YOUR_SITE_ID"
></script>
```

In a third terminal, start the owner client:

```bash
python -m cli.peekaboo listen
```

For local testing, serve the example website in another terminal:

```bash
python -m http.server 5000 --directory testweb
```

Open http://localhost:5000, click the floating chat button, and send a message. The owner can reply from the terminal.

## Production direction

The production website should install a published CLI package, run `setup` once, paste the generated HTTPS embed snippet into its HTML, and run `listen`. The widget should be served from the hosted Peekaboo server or a CDN. Use `https://` and `wss://` in production, and persist site credentials outside process memory.

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

## Authentication & ownership

Peekaboo is multi-owner. Anyone can sign in with Google or GitHub and run their own separate chat site. Each owner:

- Has their own sites (`sites.owner_id`).
- Creates sites only with their own API key (minted after OAuth login and stored hashed in `owner_api_keys`).
- Runs `listen` using the per-site `operator_token` generated at setup.

Per-owner isolation is enforced **server-side**: every site lookup is scoped by the owner id from the API key. Visitors remain anonymous (no account); they can only message an owner when their browser `Origin` matches the site's stored `allowed_origin`.

CLI commands:

```bash
peekaboo setup    # OAuth login (one time), then create a site
peekaboo listen   # receive visitor messages as the owner
peekaboo logout   # revoke the owner API key
```

## Secure chat controls

The owner CLI displays a conversation ID for each visitor. Reply to one visitor with:

```text
/reply CONVERSATION_ID MESSAGE
```

Messages are limited to 4 KB, visitor connections are rate limited, terminal control characters are removed, and the widget reconnects with bounded exponential backoff.

## Widget customization

The editable widget files live in `server/widget/`:

- `widget.html` contains the chat markup.
- `styles.css` contains the colors, spacing, and responsive layout.
- `pboo.js` loads those files, creates the Shadow DOM, and handles WebSocket messaging.

Website owners still install the widget with only the generated `script` tag.

## Backend structure

The server is split by responsibility:

- `server/main.py` keeps the deployment entry point (`server.main:app`) and compatibility exports for tests.
- `server/app.py` builds the FastAPI app and wires static assets plus routes.
- `server/routes/` contains HTTP and websocket endpoints grouped by feature.
- `server/services/` contains auth, persistence, and security helpers.
- `server/state.py` contains in-memory runtime state used when Supabase is not configured.
- `server/site/` and `server/widget/` contain browser-facing HTML, CSS, and widget assets.

Configure the CLI for the deployed server if the installer is not used:

```bash
export PEEKABOO_SERVER_URL=https://your-service.onrender.com
peekaboo setup
```

For the listener, use the WebSocket scheme:

```bash
export PEEKABOO_SERVER_URL=wss://your-service.onrender.com
peekaboo listen
```

### OAuth providers

To allow Google/GitHub sign-in, configure the providers in the Supabase dashboard (Auth → Providers) and add the server's `/auth/oauth/callback` URL as an authorized redirect. Set `PUBLIC_BASE_URL` on the server so the callback URLs use your public domain. The `SUPABASE_URL` and `SUPABASE_SECRET_KEY` env vars connect the server to Supabase; without them the server runs in an in-memory mode suitable for local testing only. In local mode, `peekaboo setup` uses a temporary in-memory owner key instead of a real OAuth provider.

The CLI defaults `PEEKABOO_SERVER_URL` (and the listen WebSocket URL) to the deployed server at `https://peekaboo-477i.onrender.com`. Override it with `PEEKABOO_SERVER_URL` when running against a local instance.

The sign-in flow routes through an authorization UI served at `/oauth/consent` (the "Authorization path" you may need to set in the Supabase provider config) which forwards the user to the selected provider. After a successful login the browser lands on a success page at `/auth/success`, telling the user to return to their terminal.

### Which HTML is needed?

Website owners do not need to copy `server/widget/index.html`. That file is only a preview page. They only add the script tag printed by `peekaboo setup` to their own HTML:

```html
<script
  src="https://your-service.onrender.com/widget/pboo.js"
  data-site="YOUR_SITE_ID"
></script>
```
