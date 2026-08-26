import json
import os
import sys
import threading
import urllib.request
from urllib.parse import urlsplit

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(PROJECT_ROOT, ".peekaboo", "config.json")
SERVER_URL = os.getenv("PEEKABOO_SERVER_URL", "http://localhost:8000")

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


def create_site_with_spinner(origin):
    result = []
    failure = []
    finished = threading.Event()

    def request_site():
        try:
            result.append(create_site(origin))
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


def create_site(origin):
    payload = json.dumps({"origin": origin} if origin else {}).encode("utf-8")
    request = urllib.request.Request(
        f"{SERVER_URL}/sites",
        method="POST"
    )
    request.add_header("Content-Type", "application/json")

    with urllib.request.urlopen(request, data=payload) as response:
        return json.loads(response.read())


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

    data = create_site_with_spinner(origin)

    site_id = data["site_id"]
    operator_token = data["operator_token"]

    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)

    credentials = {
        "site_id": site_id,
        "operator_token": operator_token
    }

    with open(CONFIG_PATH, "w") as file:
        json.dump(credentials, file, indent=2)

    print(colorize(GREEN, "  ✨ Site created!"))
    print(f"  {colorize(DIM, 'Site ID:')} {site_id}")
    if origin:
        print(f"  {colorize(DIM, 'Website:')} {origin}")
    print(colorize(GREEN, "  🔐 Operator credentials saved locally"))
    print(colorize(BOLD + BLUE, "\n  ┌─ Add this one line to your website\n  │"))
    print(
        f'  │ <script '
        f'src="{SERVER_URL}/widget/pboo.js" '
        f'data-site="{site_id}">'
        f'</script>'
    )
    print(colorize(BOLD + BLUE, "\n  └─ Then open your inbox\n"))
    print(colorize(BOLD + YELLOW, "     $ peekaboo listen"))
    print(colorize(MAGENTA, "\n  Happy chatting! ✦\n"))


if __name__ == "__main__":
    main()
