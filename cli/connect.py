import json
import os
import sys
import urllib.request
from urllib.request import HTTPError

from cli.init import load_config, save_config

GREEN = "\033[32m"
CYAN = "\033[36m"
YELLOW = "\033[33m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


def colorize(code, text):
    if sys.stdout.isatty():
        return f"{code}{text}{RESET}"
    return text


def SERVER_URL():
    return (os.getenv("PEEKABOO_SERVER_URL") or
            "https://peekaboo-477i.onrender.com").rstrip("/")


def prompt_value(label, hint):
    print(colorize(BOLD, f"\n  {label}"))
    print(colorize(DIM, f"  {hint}"))
    try:
        value = input(colorize(CYAN, "  └─ ")).strip()
    except EOFError:
        value = ""
    return value


def register_webhook(site_id, api_key, token, chat_id):
    payload = json.dumps({"token": token, "chat_id": chat_id}).encode("utf-8")
    request = urllib.request.Request(
        f"{SERVER_URL()}/sites/{site_id}/webhook/register",
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-API-Key": api_key,
        },
    )
    try:
        with urllib.request.urlopen(request, data=payload) as response:
            return json.loads(response.read())
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace").strip()
        message = detail or error.reason
        raise RuntimeError(f"{error.code} {message}") from error


def main():
    config = load_config()
    site_id = config.get("site_id")
    if not site_id:
        print(colorize(YELLOW, "No site found. Run `peekaboo setup` first."))
        return

    api_key = config.get("owner_api_key")
    if not api_key:
        print(colorize(YELLOW, "Not logged in. Run `peekaboo setup` first."))
        return

    token = chat_id_value = None
    print(colorize(YELLOW,
                   "\n  Connect your Telegram bot to this site by entering its "
                   "credentials."))
    token = prompt_value(
        "Bot API token",
        "Get this from @BotFather, e.g. 123456789:ABCdef...")
    chat_id_value = prompt_value(
        "Group chat ID",
        "The id of a topics-enabled group where the bot was added, "
        "e.g. -1001234567890")
    print()
    if not token or not chat_id_value:
        print(colorize(YELLOW,
                       "  ✗ Both the bot token and chat id are required. "
                       "Nothing was changed."))
        return

    print(colorize(CYAN, f"  Registering webhook for site {site_id}..."))
    try:
        result = register_webhook(site_id, api_key, token, chat_id_value)
    except RuntimeError as error:
        print(colorize(YELLOW, f"  ✗ {error}"))
        print(colorize(DIM, "  Check the bot token and that the bot is in a "
                            "topics-enabled group."))
        return

    print(colorize(GREEN, "  ✅ Telegram connected."))
    print(f"  {colorize(DIM, 'Integration:')} {result['integration_id']}")


if __name__ == "__main__":
    main()