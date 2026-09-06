from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from server.config import SITE_ROOT

router = APIRouter()


@router.get("/")
async def root(request: Request):
    from server.services.session import owner_from_request

    if owner_from_request(request):
        return RedirectResponse(url="/dashboard", status_code=303)
    page = (SITE_ROOT / "index.html").read_text()
    return HTMLResponse(page)


@router.get("/health")
async def health():
    return {"status": "ok"}
