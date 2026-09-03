import json
import os
import sys
import threading
import time
import webbrowser
import urllib.request
from contextlib import redirect_stderr, redirect_stdout
from urllib.request import HTTPError
from urllib.parse import urlsplit


# ADD THIS LINE: thsi is for development purpose only
# from dotenv import load_dotenv

# PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# # ADD THIS LINE - load .env from project root:
# load_dotenv(os.path.join(PROJECT_ROOT, '.env'))

# CONFIG_PATH = os.path.join(PROJECT_ROOT, ".peekaboo", "config.json")
# SERVER_URL = os.getenv("PEEKABOO_SERVER_URL")

# print(PROJECT_ROOT, CONFIG_PATH, SERVER_URL)

# ADD THIS LINE: thsi is for development purpose only

CONFIG_PATH = os.path.join(os.path.dirname(
    os.path.abspath(__file__)), ".peekaboo", "config.json")

SERVER_URL = (os.getenv("PEEKABOO_SERVER_URL") or
              "https://peekaboo-477i.onrender.com").rstrip("/")


def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            return json.load(f)
    return {}


def save_config(config):
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w") as file:
        json.dump(config, file, indent=2)


GREEN = "\033[32m"
CYAN = "\033[36m"
YELLOW = "\033[33m"
MAGENTA = "\033[35m"
BLUE = "\033[34m"
DIM = "\033[2m"
BOLD = "\033[1m"
RESET = "\033[0m"


def colorize(code, text):
    if sys.stdout.isatty():
        return f"{code}{text}{RESET}"
    return text


def create_site_with_spinner(origin, api_key):
    result = []
    failure = []
    finished = threading.Event()

    def request_site():
        try:
            result.append(create_site(origin, api_key))
        except Exception as error:
            failure.append(error)
        finally:
            finished.set()

    threading.Thread(target=request_site, daemon=True).start()
    spinner = "|/-\\"
    index = 0
    while not finished.wait(0.1):
        if sys.stdout.isatty():
            print(
                f"\r  {CYAN}{spinner[index % len(spinner)]}{RESET} Creating your site...", end="", flush=True)
            index += 1
    if sys.stdout.isatty():
        print("\r\033[2K", end="")
    if failure:
        raise failure[0]
    return result[0]


def create_site(origin, api_key):
    payload = json.dumps({"origin": origin} if origin else {}).encode("utf-8")
    request = urllib.request.Request(
        f"{SERVER_URL}/sites",
        method="POST"
    )
    request.add_header("Content-Type", "application/json")
    request.add_header("X-API-Key", api_key)

    try:
        with urllib.request.urlopen(request, data=payload) as response:
            return json.loads(response.read())
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace").strip()
        message = detail or error.reason
        raise RuntimeError(
            f"Could not create site: {error.code} {message}"
        ) from error


def get_oauth_url(provider="google", server_url=SERVER_URL):
    from urllib.parse import quote
    try:
        with urllib.request.urlopen(
            f"{SERVER_URL}/auth/oauth/start?provider={provider}"
            f"&server_url={quote(server_url, safe='')}"
        ) as response:
            return json.loads(response.read())
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace").strip()
        message = detail or error.reason
        raise RuntimeError(
            f"Could not start login: {error.code} {message}"
        ) from error


def poll_oauth_callback(state, timeout=120):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(
                f"{SERVER_URL}/auth/cli/status?state={state}"
            ) as response:
                data = json.loads(response.read())
                if data.get("owner_api_key"):
                    return data["owner_api_key"]
        except HTTPError:
            pass
        time.sleep(2)
    raise RuntimeError("Timed out waiting for browser login.")


def _has_display():
    if os.name == "nt" or sys.platform == "darwin":
        return True
    if os.environ.get("BROWSER"):
        return True
    if not (
        os.environ.get("DISPLAY")
        or os.environ.get("WAYLAND_DISPLAY")
    ):
        return False
    known = (
        "google-chrome", "chromium", "chromium-browser", "firefox",
        "iceweasel", "mozilla", "epiphany", "konqueror", "brave-browser",
        "microsoft-edge", "opera", "links", "links2", "elinks", "lynx",
        "w3m",
    )
    for binary in known:
        for path_dir in os.getenv("PATH", "").split(os.pathsep):
            if path_dir and os.path.isfile(os.path.join(path_dir, binary)):
                return True
    return False


def open_browser(url):
    if not _has_display():
        return False
    try:
        with open(os.devnull, "w") as devnull:
            with redirect_stderr(devnull), redirect_stdout(devnull):
                return webbrowser.open(url)
    except Exception:
        return False


def ensure_api_key(config):
    api_key = config.get("owner_api_key")
    if api_key:
        return api_key

    print(colorize(CYAN, "     Log in to your Peekaboo account to continue.\n"))
    oauth = get_oauth_url("google", server_url=SERVER_URL)
    url, state = oauth["url"], oauth["state"]
    print(colorize(BLUE, "  ┌─ Google — open this URL in your browser to log in:\n  │"))
    print(colorize(BLUE, f"  │ {url}"))
    print(colorize(BLUE, "  │"))
    print(colorize(DIM, "  │ If the browser didn't open, copy and paste the URL manually."))
    if not open_browser(url):
        print(colorize(YELLOW, "  │ (No browser detected — open the URL above.)"))
    print(colorize(BLUE, "\n  └─ Waiting for you to finish logging in..."))
    new_key = poll_oauth_callback(state)
    config["owner_api_key"] = new_key
    save_config(config)
    print(colorize(GREEN, "  ✅ Logged in. Account key saved locally."))
    return new_key


def ask_for_origin():
    while True:
        origin = input("  └─ Website URL (required): ").strip()
        parsed = urlsplit(origin)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}"
        print(
            colorize(YELLOW, "     Please enter a full URL, like https://yourwebsite.com"))


def main():
    print(colorize(BOLD + GREEN, """
      (\_/)      
      (o.o)      P E E K A B O O
      > ^ <     ──────────────────
    
"""))
    print(colorize(CYAN, "     ✦ Your tiny chat portal is almost ready. ✦\n"))
    print(colorize(BOLD + BLUE, "  ┌─ Create your site"))
    print("  │ Tell us where the widget will live.")
    print(colorize(DIM, "  │ Example: https://yourwebsite.com"))
    origin = ask_for_origin()
    print("origin", origin)

    config = load_config()

    data = None
    for attempt in range(2):
        api_key = ensure_api_key(config)
        try:
            data = create_site_with_spinner(origin, api_key)
            break
        except RuntimeError as error:
            if attempt == 0 and "401" in str(error):
                print(colorize(YELLOW,
                               "  └─ Saved API key is no longer valid. "
                               "Logging in again..."))
                config["owner_api_key"] = None
                save_config(config)
                continue
            raise
    assert data is not None

    site_id = data["site_id"]

    config["site_id"] = site_id
    save_config(config)

    print(colorize(GREEN, "  ✨ Site created!"))
    print(f"  {colorize(DIM, 'Site ID:')} {site_id}")
    if origin:
        print(f"  {colorize(DIM, 'Website:')} {origin}")
    print(colorize(BOLD + BLUE, "\n  ┌─ Add this one line to your website\n  │"))
    print(
        f'  │ <script '
        f'src="{SERVER_URL}/widget/pboo.bundle.js" '
        f'data-site="{site_id}">'
        f'</script>'
    )
    print(colorize(BOLD + BLUE, "\n  └─ Then wire up your Telegram inbox\n"))
    print(colorize(BOLD + YELLOW, "     $ peekaboo connect"))
    print(colorize(MAGENTA, "\n  Happy chatting! ✦\n"))


if __name__ == "__main__":
    main()
