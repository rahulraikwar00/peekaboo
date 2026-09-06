from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from server.config import SITE_ROOT
from server.routes.spa import spa_index_html

router = APIRouter()


@router.get("/")
async def root(request: Request):
    from server.services.session import owner_from_request

    html = spa_index_html()
    if html is not None:
        # SPA handles auth-awareness client-side (/api/me).
        return HTMLResponse(html)
    if owner_from_request(request):
        from fastapi.responses import RedirectResponse

        return RedirectResponse(url="/dashboard", status_code=303)
    page = (SITE_ROOT / "index.html").read_text()
    return HTMLResponse(page)


@router.get("/health")
async def health():
    return {"status": "ok"}
