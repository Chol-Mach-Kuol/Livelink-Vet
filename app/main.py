from contextlib import asynccontextmanager

from fastapi import FastAPI

import app.models  # noqa: F401  (registers all tables)
from app.core.database import Base, engine
from app.routes import analytics, auth, cases, diagnoses, locations, reports, surveillance, ussd, users


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Dev convenience; use Alembic migrations for production schema changes.
    Base.metadata.create_all(bind=engine)
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
for module in (auth, locations, reports, cases, diagnoses, surveillance, analytics, users, ussd):
    app.include_router(module.router, prefix=PREFIX)


@app.get("/", tags=["health"])
def root():
    return {"message": "LiveLink Vet API is running.", "docs": "/docs"}
