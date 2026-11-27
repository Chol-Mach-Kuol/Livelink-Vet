"""Public, aggregate-only figures for the landing page. No identities, places or report details."""
import time
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.disease_report import DiseaseReport
from app.models.location import Location
from app.services import surveillance
from app.services.triage import DISEASES

router = APIRouter(prefix="/public", tags=["public"])

_CACHE: dict = {"at": 0.0, "data": None}
CACHE_SECONDS = 60


@router.get("/stats")
def public_stats(db: Session = Depends(get_db)):
    """Headline numbers for the last 30 days, cached for a minute."""
    if _CACHE["data"] is not None and time.monotonic() - _CACHE["at"] < CACHE_SECONDS:
        return _CACHE["data"]
    since = datetime.now(timezone.utc) - timedelta(days=30)
    recent = db.query(DiseaseReport).filter(DiseaseReport.created_at >= since)
    data = {
        "window_days": 30,
        "reports": recent.count(),
        "animals_reported": recent.with_entities(func.coalesce(func.sum(DiseaseReport.affected_count), 0)).scalar(),
        "counties_reporting": (
            recent.join(Location, Location.id == DiseaseReport.location_id)
            .with_entities(func.count(func.distinct(Location.county))).scalar()
        ),
        "zoonotic_alerts": recent.filter(DiseaseReport.zoonotic_alert.is_(True)).count(),
        "active_clusters": len(surveillance.spatial_clusters(db)),
        "diseases_monitored": len(DISEASES),
    }
    _CACHE.update(at=time.monotonic(), data=data)
    return data
