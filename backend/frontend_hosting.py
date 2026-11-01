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
                "villas", "about", "location", "faqs", "reviews", "policies",
                "feedback", "maintenance-response", "book", "register",
                "dashboard", "login", "admin-login", "admin-dashboard", "admin", "staff", "maintenance", "front-desk", "front-desk-login",
                "front-desk/bookings", "front-desk/walkIns", "front-desk/newWalkIn",
                "front-desk/lifecycle", "front-desk/payments", "front-desk/receipts", "front-desk/staff",
            }
            route = path.strip("/")
            # Villa detail pages have one identifier, never an asset/API suffix.
            parts = route.split("/")
            villa_detail = len(parts) == 2 and parts[0] == "villas" and bool(parts[1]) and "." not in parts[1]
            if error.status_code != 404 or (route not in browser_routes and not villa_detail):
                raise
            return await super().get_response("index.html", scope)


def mount_frontend(app: FastAPI, directory: str) -> None:
    if not directory:
        return
    build = Path(directory).resolve()
    if not (build / "index.html").is_file():
        raise RuntimeError(f"Frontend build is missing: {build / 'index.html'}")
    app.mount("/", FrontendFiles(directory=build, html=True), name="frontend")
