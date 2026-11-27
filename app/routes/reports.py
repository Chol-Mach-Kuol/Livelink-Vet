from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.disease_report import DiseaseReport
from app.models.location import Location
from app.models.user import User
from app.permissions.access_control import get_current_user, verified_roles
from app.schemas.report import (
    BatchResultItem, ReportBatch, ReportCreate, ReportOut, TriageOut, TriagePreviewIn,
)
from app.services import report_service
from app.services.triage import DISEASES, SIGNS, SPECIES, triage

router = APIRouter(prefix="/reports", tags=["reports"])

# Roles that may read every report (all must be verified).
READ_ALL_ROLES = {"veterinarian", "animal_health_worker", "admin", "researcher"}


def _ensure_location(db: Session, location_id: UUID) -> None:
    if not db.get(Location, location_id):
        raise HTTPException(status_code=404, detail=f"Location {location_id} not found")


@router.get("/signs", tags=["reference"])
def list_signs():
    """Standard clinical sign codes, species and the disease knowledge base, for building report forms."""
    return {
        "signs": [{"code": c, "label": label} for c, (label, _) in SIGNS.items()],
        "species": list(SPECIES),
        "diseases": [
            {"code": d.code, "name": d.name, "species": list(d.species), "zoonotic": d.zoonotic,
             "woah_listed": d.woah_listed, "signs": d.signs, "min_signs": d.min_signs, "advice": d.advice}
            for d in DISEASES
        ],
    }


@router.post("/triage-preview", response_model=TriageOut)
def triage_preview(payload: TriagePreviewIn, current_user: User = Depends(get_current_user)):
    """Run syndromic triage without saving, so a field worker sees red flags while filling the form."""
    return triage(
        signs=payload.signs, free_text=payload.symptoms, species=payload.species,
        affected=payload.affected_count, deaths=payload.death_count,
    ).as_dict()


@router.post("", response_model=ReportOut, status_code=status.HTTP_201_CREATED)
def submit_report(
    payload: ReportCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_location(db, payload.location_id)
    report, _ = report_service.create_report(db, current_user, channel="app", **payload.model_dump())
    return report


@router.post("/batch", response_model=list[BatchResultItem])
def sync_offline_reports(
    payload: ReportBatch,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Upload reports captured offline. Safe to retry: reports already received (same client_ref) are skipped."""
    for loc_id in {r.location_id for r in payload.reports}:
        _ensure_location(db, loc_id)
    results = []
    for item in payload.reports:
        report, created = report_service.create_report(db, current_user, channel="offline_sync", **item.model_dump())
        results.append(BatchResultItem(client_ref=item.client_ref, id=report.id, created=created))
    return results


@router.get("", response_model=list[ReportOut])
def list_reports(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=200),
    priority: str | None = None,
    zoonotic_only: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(DiseaseReport)
    if not verified_roles(current_user) & READ_ALL_ROLES:
        query = query.filter(DiseaseReport.reporter_id == current_user.id)
    if priority:
        query = query.filter(DiseaseReport.suggested_priority == priority)
    if zoonotic_only:
        query = query.filter(DiseaseReport.zoonotic_alert.is_(True))
    return query.order_by(DiseaseReport.created_at.desc()).offset(skip).limit(limit).all()


@router.get("/{report_id}", response_model=ReportOut)
def get_report(
    report_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    report = db.get(DiseaseReport, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    if not verified_roles(current_user) & READ_ALL_ROLES and report.reporter_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    return report
