import json
import os
import sys
import termios
import threading
import time
import tty
import webbrowser
import urllib.request
from contextlib import redirect_stderr, redirect_stdout
from urllib.request import HTTPError
from urllib.parse import urlsplit

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(PROJECT_ROOT, ".peekaboo", "config.json")
SERVER_URL = os.getenv("PEEKABOO_SERVER_URL", "http://localhost:8000")


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


def _read_key():
    ch = sys.stdin.read(1)
    if ch == "\x1b":
        _ = sys.stdin.read(2)
        return {"[A": "up", "[B": "down"}.get(_)
    if ch in ("\r", "\n"):
        return "enter"
    return ch


def select_option(prompt, options):
    """Interactive arrow-key menu. Falls back to a numbered prompt when not a TTY."""
    if not sys.stdin.isatty():
        print(colorize(BLUE, f"  └─ {prompt}"))
        for i, opt in enumerate(options, 1):
            print(colorize(DIM, f"     {i}) {opt[0]}"))
        while True:
            choice = input("  └─ Select [1]: ").strip() or "1"
            if choice.isdigit() and 1 <= int(choice) <= len(options):
                return options[int(choice) - 1][1]
            print(colorize(YELLOW, "     Invalid choice. Try again."))

    index = 0
    old_attrs = termios.tcgetattr(sys.stdin)
    try:
        tty.setcbreak(sys.stdin.fileno())
        print(colorize(BOLD + BLUE, f"  ┌─ {prompt}"))
        while True:
            for i, (label, _) in enumerate(options):
                if i == index:
                    line = f"  │ {colorize(BOLD + CYAN, '▶ ' + label)}"
                else:
                    line = f"  │   {colorize(DIM, label)}"
                sys.stdout.write("\x1b[K" + line + "\n")
            sys.stdout.write("\x1b[" + str(len(options)) + "A")
            sys.stdout.flush()

            key = _read_key()
            if key == "up":
                index = (index - 1) % len(options)
            elif key == "down":
                index = (index + 1) % len(options)
            elif key == "enter":
                print("\n", end="")
                break
    finally:
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_attrs)

    return options[index][1]


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

    with urllib.request.urlopen(request, data=payload) as response:
        return json.loads(response.read())


def get_oauth_url(provider="github"):
    with urllib.request.urlopen(
        f"{SERVER_URL}/auth/oauth/start?provider={provider}"
    ) as response:
        return json.loads(response.read())


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


def open_browser(url):
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
    provider = select_option(
        "How would you like to log in?",
        [
            ("GitHub", "github"),
            ("Google", "google"),
        ],
    )
    oauth = get_oauth_url(provider)
    url, state = oauth["url"], oauth["state"]
    print(colorize(BLUE, f"  ┌─ {provider.title()} — open this URL in your browser to log in:\n  │"))
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

    config = load_config()
    api_key = ensure_api_key(config)

    data = create_site_with_spinner(origin, api_key)

    site_id = data["site_id"]
    operator_token = data["operator_token"]

    config["site_id"] = site_id
    config["operator_token"] = operator_token
    save_config(config)

    print(colorize(GREEN, "  ✨ Site created!"))
    print(f"  {colorize(DIM, 'Site ID:')} {site_id}")
    if origin:
        print(f"  {colorize(DIM, 'Website:')} {origin}")
    print(colorize(GREEN, "  🔐 Operator credentials saved locally"))
    print(colorize(BOLD + BLUE, "\n  ┌─ Add this one line to your website\n  │"))
    print(
        f'  │ <script '
        f'src="{SERVER_URL}/widget/pboo.bundle.js" '
        f'data-site="{site_id}">'
        f'</script>'
    )
    print(colorize(BOLD + BLUE, "\n  └─ Then open your inbox\n"))
    print(colorize(BOLD + YELLOW, "     $ peekaboo listen"))
    print(colorize(MAGENTA, "\n  Happy chatting! ✦\n"))


if __name__ == "__main__":
    main()
