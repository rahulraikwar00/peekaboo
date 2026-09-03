from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from server.config import SITE_ROOT, WIDGET_ROOT
from server.routes import auth, core, install, messages, sites, websockets


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
        websockets.router,
    ):
        app.router.routes.extend(router.routes)
    return app
