import shlex

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

router = APIRouter()


@router.get("/install.sh", response_class=PlainTextResponse)
async def install_script(request: Request):
    server_url = shlex.quote(str(request.base_url).rstrip("/"))

    return fr'''#!/bin/sh
set -eu

command -v curl >/dev/null 2>&1 || {{ echo "curl is required" >&2; exit 1; }}
command -v python3 >/dev/null 2>&1 || {{ echo "python3 is required" >&2; exit 1; }}

install_dir="$HOME/.local/bin"
app_dir="$HOME/.peekaboo"
echo "Installing Peekaboo CLI..."
mkdir -p "$install_dir"
mkdir -p "$app_dir/cli"

if [ ! -x "$app_dir/venv/bin/python" ]; then
    echo "Creating local environment..."
    python3 -m venv "$app_dir/venv"
fi
if ! "$app_dir/venv/bin/python" -c 'import websockets' >/dev/null 2>&1; then
    echo "Installing dependencies..."
    "$app_dir/venv/bin/python" -m pip install --disable-pip-version-check --quiet websockets
fi

echo "Downloading CLI files..."
base_url="https://raw.githubusercontent.com/rahulraikwar00/peekaboo/master/cli"
curl -fsSL "$base_url/init.py" -o "$app_dir/cli/init.py" &
pid_one=$!
curl -fsSL "$base_url/main.py" -o "$app_dir/cli/main.py" &
pid_two=$!
curl -fsSL "$base_url/peekaboo.py" -o "$app_dir/cli/peekaboo.py" &
pid_three=$!
wait "$pid_one" "$pid_two" "$pid_three"
echo "CLI ready."

cat > "$install_dir/peekaboo" <<'PEEKABOO_COMMAND'
#!/bin/sh
set -eu
app_dir="$HOME/.peekaboo"
server_url={server_url}
case "${{1:-}}" in
    listen) server_url="wss://${{server_url#https://}}" ;;
    *) server_url="$server_url" ;;
esac
PEEKABOO_SERVER_URL="$server_url" PYTHONPATH="$app_dir" exec "$app_dir/venv/bin/python" -m cli.peekaboo "$@"
PEEKABOO_COMMAND

chmod +x "$install_dir/peekaboo"
echo "Peekaboo CLI installed at $install_dir/peekaboo"
case ":$PATH:" in
    *":$install_dir:"*) ;;
    *) echo "Add it to PATH with: export PATH=\$HOME/.local/bin:\$PATH" ;;
esac
'''
