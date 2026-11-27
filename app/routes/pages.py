"""Web pages: landing, field reporting app (installable, works offline) and dashboard."""
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

STATIC = Path(__file__).resolve().parents[1] / "static"

router = APIRouter(include_in_schema=False)


def _page(name: str) -> FileResponse:
    return FileResponse(STATIC / name, media_type="text/html", headers={"Cache-Control": "no-cache"})


@router.get("/")
def landing():
    return _page("index.html")


@router.get("/report")
def field_app():
    return _page("report.html")


@router.get("/dashboard")
def dashboard():
    return _page("dashboard.html")


@router.get("/sw.js")
def service_worker():
    # Served from the root so it can control /report.
    return FileResponse(STATIC / "sw.js", media_type="text/javascript", headers={"Cache-Control": "no-cache"})


@router.get("/favicon.ico")
def favicon():
    return FileResponse(STATIC / "logo.svg", media_type="image/svg+xml")


@router.get("/manifest.webmanifest")
def manifest():
    return FileResponse(STATIC / "manifest.webmanifest", media_type="application/manifest+json")
