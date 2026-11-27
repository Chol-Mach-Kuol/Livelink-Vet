from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

import app.models  # noqa: F401  (registers all tables)
from app.core.config import settings
from app.core.migrations import upgrade_db
from app.routes import (
    analytics, auth, cases, diagnoses, locations, pages, public, reports, surveillance, ussd, users,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.AUTO_MIGRATE:
        upgrade_db()
    yield


app = FastAPI(
    title="LiveLink Vet",
    description=(
        "Collaborative veterinary intelligence and livestock disease surveillance for pastoral "
        "communities in South Sudan.\n\n"
        "**Make livestock disease predictable, not just treatable.**\n\n"
        "- Report from a smartphone, offline (batch sync), or any feature phone over USSD\n"
        "- Syndromic triage flags notifiable and zoonotic diseases the moment a report arrives\n"
        "- Early warning: EARS-C2 county spikes and spatial clusters across moving cattle camps\n"
        "- Herd-movement advisories before migration\n"
        "- k-anonymised research exports and a full audit trail\n\n"
        "_Triage output is decision support only. Qualified veterinarians make all clinical decisions._"
    ),
    version="0.2.0",
    lifespan=lifespan,
)

PREFIX = "/api/v1"
for module in (auth, locations, reports, cases, diagnoses, surveillance, analytics, users, ussd, public):
    app.include_router(module.router, prefix=PREFIX)
app.include_router(pages.router)
app.mount("/static", StaticFiles(directory=pages.STATIC), name="static")

# The web pages only load code from this server, unpkg (Leaflet) and Google Fonts,
# and map tiles from OpenStreetMap. /docs keeps FastAPI's defaults (it uses a CDN).
PAGE_CSP = "; ".join([
    "default-src 'self'",
    "script-src 'self' 'unsafe-inline' https://unpkg.com",
    "style-src 'self' 'unsafe-inline' https://unpkg.com https://fonts.googleapis.com",
    "font-src 'self' https://fonts.gstatic.com",
    "img-src 'self' data: https://tile.openstreetmap.org https://*.tile.openstreetmap.org",
    "connect-src 'self'",
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
])
PAGES = {"/", "/report", "/dashboard", "/cases", "/admin"}


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "geolocation=(self), camera=(), microphone=()")
    if request.url.path in PAGES:
        response.headers["Content-Security-Policy"] = PAGE_CSP
        response.headers["X-Frame-Options"] = "DENY"
    if request.url.scheme == "https":
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
    return response


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok", "docs": "/docs", "dashboard": "/dashboard", "field_app": "/report"}
