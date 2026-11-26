from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.location import Location
from app.models.user import User
from app.permissions.access_control import get_current_user, require_role
from app.services import surveillance

router = APIRouter(prefix="/surveillance", tags=["early warning"])

ANALYST_ROLES = ("veterinarian", "animal_health_worker", "admin", "researcher")


@router.get("/alerts")
def alerts(
    as_of: date | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*ANALYST_ROLES)),
):
    """Current early-warning signals: EARS-C2 county spikes and spatial clusters."""
    clusters = surveillance.spatial_clusters(db)
    aberrations = surveillance.county_aberrations(db, as_of)
    return {
        "temporal_aberrations": aberrations,
        "spatial_clusters": clusters,
        "summary": {
            "counties_spiking": len(aberrations),
            "active_clusters": len(clusters),
            "zoonotic_clusters": sum(c["zoonotic_alert"] for c in clusters),
        },
    }


@router.get("/clusters.geojson")
def clusters_geojson(
    radius_km: float | None = Query(None, gt=0, le=200),
    window_days: int | None = Query(None, ge=1, le=90),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*ANALYST_ROLES)),
):
    """Clusters as GeoJSON — drop straight into Leaflet, Mapbox, QGIS or Kobo dashboards."""
    return surveillance.to_geojson(surveillance.spatial_clusters(db, radius_km=radius_km, window_days=window_days))


@router.get("/advisory")
def advisory(
    location_id: UUID | None = None,
    latitude: float | None = Query(None, ge=-90, le=90),
    longitude: float | None = Query(None, ge=-180, le=180),
    radius_km: float | None = Query(None, gt=0, le=300),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Herd-movement advisory for any signed-in user: is there active disease near this place?

    Pass a location_id or a latitude/longitude pair (e.g. a planned migration stop).
    """
    if location_id:
        loc = db.get(Location, location_id)
        if not loc:
            raise HTTPException(status_code=404, detail="Location not found")
        if loc.latitude is None:
            raise HTTPException(status_code=422, detail="Location has no coordinates")
        latitude, longitude = float(loc.latitude), float(loc.longitude)
    if latitude is None or longitude is None:
        raise HTTPException(status_code=422, detail="Provide location_id or latitude and longitude")
    result = surveillance.movement_advisory(db, latitude, longitude, radius_km)
    # Non-professionals get the risk picture without report identifiers.
    for c in result["active_clusters"]:
        c.pop("report_ids", None)
    return result
