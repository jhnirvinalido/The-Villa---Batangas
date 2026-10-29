"""Serve the optional production React build after all API routes."""
from pathlib import Path

from fastapi import FastAPI
from starlette.exceptions import HTTPException
from starlette.staticfiles import StaticFiles


class FrontendFiles(StaticFiles):
    async def get_response(self, path, scope):
        try:
            return await super().get_response(path, scope)
        except HTTPException as error:
            # Only browser routes get the SPA entry point. Missing API routes
            # and assets retain their 404 instead of returning HTML.
            browser_routes = {
                "feedback", "maintenance-response", "book", "register",
                "dashboard", "admin-login", "admin-dashboard", "admin", "staff",
            }
            if error.status_code != 404 or path.strip("/") not in browser_routes:
                raise
            return await super().get_response("index.html", scope)


def mount_frontend(app: FastAPI, directory: str) -> None:
    if not directory:
        return
    build = Path(directory).resolve()
    if not (build / "index.html").is_file():
        raise RuntimeError(f"Frontend build is missing: {build / 'index.html'}")
    app.mount("/", FrontendFiles(directory=build, html=True), name="frontend")
