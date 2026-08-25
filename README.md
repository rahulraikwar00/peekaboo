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

The command creates a unique site ID and operator token in `.peekaboo/config.json`, then prints an embed snippet. Add that snippet to the website that should show the chat widget:

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

Configure the CLI for the deployed server:

```bash
export PEEKABOO_SERVER_URL=https://your-service.onrender.com
peekaboo setup
```

For the listener, use the WebSocket scheme:

```bash
export PEEKABOO_SERVER_URL=wss://your-service.onrender.com
peekaboo listen
```

The current site store is in memory, so site credentials are lost whenever the Render service restarts. Add a database before production use.

### Which HTML is needed?

Website owners do not need to copy `server/widget/index.html`. That file is only a preview page. They only add the script tag printed by `peekaboo setup` to their own HTML:

```html
<script
  src="https://your-service.onrender.com/widget/pboo.js"
  data-site="YOUR_SITE_ID"
></script>
```
