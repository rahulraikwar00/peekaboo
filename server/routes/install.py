import shlex

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

router = APIRouter()


@router.get("/install.sh", response_class=PlainTextResponse)
async def install_script(request: Request):
    server_url = shlex.quote(str(request.base_url).rstrip("/"))

    return fr'''#!/bin/sh
set -eu

# ─────────────────────────────────────────────────────────────
#  Peekaboo CLI installer
#  Downloads the CLI, sets up a Python environment, and launches
#  `peekaboo setup` so you can go straight into onboarding.
# ─────────────────────────────────────────────────────────────

command -v curl >/dev/null 2>&1 || {{ echo "curl is required" >&2; exit 1; }}
command -v python3 >/dev/null 2>&1 || {{ echo "python3 is required" >&2; exit 1; }}

install_dir="$HOME/.local/bin"
app_dir="$HOME/.peekaboo"
cli_dir="$app_dir/cli"
mkdir -p "$install_dir"
mkdir -p "$cli_dir"

echo "  • Setting up the Peekaboo CLI environment..."

if [ ! -x "$app_dir/venv/bin/python" ]; then
    echo "  • Creating Python venv..."
    python3 -m venv "$app_dir/venv"
fi

echo "  • Installing dependencies..."
"$app_dir/venv/bin/pip" install --quiet --disable-pip-version-check --upgrade python-dotenv

echo "  • Downloading CLI..."
base_url="{server_url}/cli"
for name in peekaboo.py init.py connect.py; do
    curl -fsSL "$base_url/$name" -o "$cli_dir/$name"
done

cat > "$install_dir/peekaboo" <<'PEEKABOO_COMMAND'
#!/bin/sh
set -eu
app_dir="$HOME/.peekaboo"
server_url={server_url}
PEEKABOO_SERVER_URL="$server_url" PYTHONPATH="$app_dir" exec "$app_dir/venv/bin/python" -m cli.peekaboo "$@"
PEEKABOO_COMMAND
chmod +x "$install_dir/peekaboo"

if ! echo ":$PATH:" | grep -q ":$install_dir:"; then
    echo
    echo "  To use 'peekaboo' in this terminal, add it to your PATH:"
    echo "      export PATH=\"\$HOME/.local/bin:\$PATH\""
fi

echo
echo "✦ Peekaboo CLI is ready. Starting setup..."
exec "$install_dir/peekaboo" setup "$@"
'''