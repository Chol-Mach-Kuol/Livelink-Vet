from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.location import Location
from app.models.user import User
from app.permissions.access_control import get_current_user
from app.schemas.location import LocationCreate, LocationOut
from app.services import audit

router = APIRouter(prefix="/locations", tags=["locations"])


@router.post("", response_model=LocationOut, status_code=status.HTTP_201_CREATED)
def create_location(
    payload: LocationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Register a place (state → county → payam → boma → cattle camp). Cattle camps move
    seasonally, so any signed-in user can add the camp they are reporting from.
    An identical existing record is returned instead of a duplicate."""
    data = payload.model_dump()
    match = {k: data[k] for k in ("state", "county", "payam", "boma", "cattle_camp")}
    existing = db.query(Location).filter_by(**match).first()
    if existing:
        return existing
    loc = Location(**data)
    db.add(loc)
    db.flush()
    audit.record(db, current_user, "location.created", "location", loc.id)
    db.commit()
    db.refresh(loc)
    return loc


@router.get("", response_model=list[LocationOut])
def search_locations(
    q: str | None = Query(None, description="Search across state, county, payam, boma and camp names"),
    state: str | None = None,
    county: str | None = None,
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Location)
    if state:
        query = query.filter(Location.state.ilike(state))
    if county:
        query = query.filter(Location.county.ilike(county))
    if q:
        like = f"%{q}%"
        query = query.filter(
            Location.state.ilike(like) | Location.county.ilike(like) | Location.payam.ilike(like)
            | Location.boma.ilike(like) | Location.cattle_camp.ilike(like)
        )
    return query.order_by(Location.state, Location.county).limit(limit).all()
