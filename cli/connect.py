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


def bot_token():
    return (os.getenv("PEEKABOO_TELEGRAM_BOT_TOKEN") or "").strip()


def chat_id():
    return (os.getenv("PEEKABOO_TELEGRAM_CHAT_ID") or "").strip()


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

    token = bot_token()
    chat_id_value = chat_id()
    if not token or not chat_id_value:
        print(colorize(BOLD, "Telegram bot credentials are read from the "
                             "environment.\n"))
        print("  " + colorize(CYAN, "PEEKABOO_TELEGRAM_BOT_TOKEN") +
              "  the bot token from @BotFather")
        print("  " + colorize(CYAN, "PEEKABOO_TELEGRAM_CHAT_ID") +
              "  the id of a topics-enabled group where the bot was added\n")
        print(colorize(DIM, "Example:\n"))
        print(colorize(DIM,
                       "  export PEEKABOO_TELEGRAM_BOT_TOKEN=123:abc...\n"
                       "  export PEEKABOO_TELEGRAM_CHAT_ID=-1001234567890\n"
                       "  peekaboo connect"))
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