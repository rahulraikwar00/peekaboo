import json
import os
import urllib.request

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(PROJECT_ROOT, ".peekaboo", "config.json")
SERVER_URL = os.getenv("PEEKABOO_SERVER_URL", "http://localhost:8000")


def create_site():
    request = urllib.request.Request(
        f"{SERVER_URL}/sites",
        method="POST"
    )

    with urllib.request.urlopen(request) as response:
        return json.loads(response.read())


def main():
    print("🐰 Peekaboo")
    print()
    print("Creating your Peekaboo site...")

    data = create_site()

    site_id = data["site_id"]
    operator_token = data["operator_token"]

    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)

    credentials = {
        "site_id": site_id,
        "operator_token": operator_token
    }

    with open(CONFIG_PATH, "w") as file:
        json.dump(credentials, file, indent=2)

    print()
    print("✓ Site created")
    print(f"✓ Site ID: {site_id}")
    print("✓ Operator token saved")
    print()
    print("Add this to your website:")
    print()
    print(
        f'<script '
        f'src="{SERVER_URL}/widget/pboo.js" '
        f'data-site="{site_id}">'
        f'</script>'
    )
    print()
    print("Start the services in parallel:")
    print()
    print("  uvicorn server.main:app --reload --port 8000")
    print()
    print("Then, in another terminal, run:")
    print()
    print("  peekaboo listen")


if __name__ == "__main__":
    main()
