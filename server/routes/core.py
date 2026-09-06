from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from server.routes.spa import spa_index_response

router = APIRouter()


@router.get("/")
async def root():
    # The SPA is the only frontend now (served from frontend/dist build).
    return spa_index_response()


@router.get("/health")
async def health():
    return {"status": "ok"}
