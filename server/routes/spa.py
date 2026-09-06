"""SPA serving: fall back to the built frontend (frontend/dist) for any
non-API path, so client-side routes like /login and /dashboard work.

Registered last in app.py so API/widget/site routes match first.
"""

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, HTMLResponse

router = APIRouter()

FRONTEND_DIST = (
    Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
)


def spa_index_html() -> str | None:
    index = FRONTEND_DIST / "index.html"
    if index.is_file():
        return index.read_text()
    return None


def spa_index_response() -> HTMLResponse:
    html = spa_index_html()
    if html is not None:
        return HTMLResponse(html)
    return HTMLResponse(
        "Frontend not built yet. Run `npm run build` in frontend/, "
        "or use /auth/login for the classic dashboard.",
        status_code=404,
    )


@router.get("/{full_path:path}")
async def spa_fallback(full_path: str):
    dist = FRONTEND_DIST.resolve()
    if full_path:
        candidate = (FRONTEND_DIST / full_path).resolve()
        try:
            candidate.relative_to(dist)
        except ValueError:
            candidate = Path()
        if candidate.is_file():
            return FileResponse(candidate)
    return spa_index_response()