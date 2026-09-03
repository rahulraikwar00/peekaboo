from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

router = APIRouter()

CLI_ROOT = Path(__file__).resolve().parents[2] / "cli"

_CLI_FILES = {
    "init.py": "init.py",
    "connect.py": "connect.py",
    "peekaboo.py": "peekaboo.py",
}


@router.get("/cli/{name}", response_class=PlainTextResponse)
async def get_cli_file(name: str):
    filename = _CLI_FILES.get(name)
    if filename is None:
        raise HTTPException(status_code=404, detail="Not Found")
    path = CLI_ROOT / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Not Found")
    return path.read_text(encoding="utf-8")