import asyncio
import sys

from cli.init import main as setup
from cli.main import main as listen


def main():
    command = sys.argv[1] if len(sys.argv) > 1 else "help"

    if command == "setup":
        setup()
    elif command == "listen":
        asyncio.run(listen())
    else:
        print("Peekaboo commands:")
        print("  peekaboo setup   Create a site and print the embed code")
        print("  peekaboo listen  Connect to the site as its operator")


if __name__ == "__main__":
    main()
