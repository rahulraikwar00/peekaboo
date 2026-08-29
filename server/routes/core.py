from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from server.config import SITE_ROOT

router = APIRouter()


@router.get("/")
async def root():
    page = (SITE_ROOT / "index.html").read_text()
    return HTMLResponse(page)


@router.get("/health")
async def health():
    return {"status": "ok"}
