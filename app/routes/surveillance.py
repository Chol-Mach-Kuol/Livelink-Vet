from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.models.disease_report import DiseaseReport
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


@router.get("/reports.geojson")
def reports_geojson(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*ANALYST_ROLES)),
):
    """Recent reports as map points (device GPS, else the location's coordinates)."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    reports = (
        db.query(DiseaseReport)
        .options(joinedload(DiseaseReport.location))
        .filter(DiseaseReport.created_at >= since)
        .order_by(DiseaseReport.created_at.desc())
        .all()
    )
    features = []
    for r in reports:
        coords = surveillance.report_coords(r)
        if not coords:
            continue
        loc = r.location
        signals = (r.triage or {}).get("signals") or []
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [coords[1], coords[0]]},
            "properties": {
                "id": str(r.id),
                "created_at": r.created_at.isoformat(),
                "species": r.species,
                "affected": r.affected_count,
                "deaths": r.death_count,
                "priority": r.suggested_priority,
                "zoonotic": bool(r.zoonotic_alert),
                "status": r.report_status,
                "channel": r.channel,
                "top_signal": signals[0]["name"] if signals else None,
                "place": ", ".join(p for p in (loc.cattle_camp, loc.payam, loc.county, loc.state) if p),
            },
        })
    return {"type": "FeatureCollection", "features": features}


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
