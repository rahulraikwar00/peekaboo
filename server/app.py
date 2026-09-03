from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.requests import Request

from server.config import SITE_ROOT, WIDGET_ROOT
from server.routes import (
    auth,
    core,
    install,
    integrations_crud,
    messages,
    sites,
    webhook,
    webhook_register,
    websockets,
)


def create_app():
    app = FastAPI()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    app.mount("/widget", StaticFiles(directory=WIDGET_ROOT), name="widget")
    app.mount("/site", StaticFiles(directory=SITE_ROOT), name="site")
    for router in (
        core.router,
        install.router,
        auth.router,
        sites.router,
        messages.router,
        webhook.router,
        websockets.router,
        integrations_crud.router,
        webhook_register.router,
    ):
        app.router.routes.extend(router.routes)

    @app.middleware("http")
    async def secure_headers(request: Request, call_next):
        response = await call_next(request)
        not_set = response.headers.setdefault
        not_set(
            "Strict-Transport-Security",
            "max-age=63072000; includeSubDomains; preload",
        )
        not_set(
            "Content-Security-Policy",
            "frame-ancestors 'none'",
        )
        return response

    return app
