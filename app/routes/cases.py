import uuid
from collections import Counter
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.activity import AuditLog
from app.models.case import Case, CaseAssignment, CaseReport
from app.models.disease_report import DiseaseReport
from app.models.location import Location
from app.models.user import User
from app.permissions.access_control import get_current_user, require_role
from app.schemas.case import (
    CaseAssignmentCreate, CaseCreate, CaseFromCluster, CaseOut, CaseStatusUpdate, TimelineEvent,
)
from app.schemas.report import ReportOut
from app.services import audit, case_service
from app.services.triage import PRIORITY_ORDER

router = APIRouter(prefix="/cases", tags=["cases"])


def _generate_case_number() -> str:
    year = datetime.now(timezone.utc).year
    return f"LV-{year}-{uuid.uuid4().hex[:6].upper()}"


def get_visible_case(db: Session, case_id: UUID, user: User) -> Case:
    case = case_service.visible_cases(db, user).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return case


def _link(db: Session, case: Case, report: DiseaseReport, actor: User) -> None:
    if db.query(CaseReport).filter(CaseReport.report_id == report.id).first():
        raise HTTPException(status_code=409, detail=f"Report {report.id} already linked to a case")
    db.add(CaseReport(case_id=case.id, report_id=report.id))
    report.report_status = "linked_to_case"
    audit.record(db, actor, "case.report_linked", "case", case.id, report_id=report.id)


def _load_reports(db: Session, report_ids: list[UUID]) -> list[DiseaseReport]:
    reports = db.query(DiseaseReport).filter(DiseaseReport.id.in_(report_ids)).all()
    missing = set(report_ids) - {r.id for r in reports}
    if missing:
        raise HTTPException(status_code=404, detail=f"Reports not found: {', '.join(map(str, missing))}")
    return reports


def _open_case(db: Session, actor: User, location_id: UUID, priority: str, reports: list[DiseaseReport]) -> Case:
    case = Case(case_number=_generate_case_number(), location_id=location_id,
                assigned_vet_id=actor.id, priority=priority)
    db.add(case)
    db.flush()
    db.add(CaseAssignment(case_id=case.id, user_id=actor.id, assignment_role="lead_veterinarian", assigned_by=actor.id))
    audit.record(db, actor, "case.opened", "case", case.id, priority=priority)
    for r in reports:
        _link(db, case, r, actor)
    db.commit()
    db.refresh(case)
    return case


@router.post("", response_model=CaseOut, status_code=status.HTTP_201_CREATED)
def create_case(
    payload: CaseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("veterinarian", "admin")),
):
    if not db.get(Location, payload.location_id):
        raise HTTPException(status_code=404, detail="Location not found")
    reports = _load_reports(db, payload.report_ids) if payload.report_ids else []
    return _open_case(db, current_user, payload.location_id, payload.priority, reports)


@router.post("/from-reports", response_model=CaseOut, status_code=status.HTTP_201_CREATED)
def create_case_from_reports(
    payload: CaseFromCluster,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("veterinarian", "admin")),
):
    """Open one case for a group of reports — typically the report_ids of a surveillance cluster.
    Location is the most-reported one; priority defaults to the highest triage priority."""
    reports = _load_reports(db, payload.report_ids)
    location_id = Counter(r.location_id for r in reports).most_common(1)[0][0]
    priority = payload.priority or max((r.suggested_priority or "normal" for r in reports), key=PRIORITY_ORDER.index)
    return _open_case(db, current_user, location_id, priority, reports)


@router.get("", response_model=list[CaseOut])
def list_cases(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=200),
    case_status: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = case_service.visible_cases(db, current_user)
    if case_status:
        query = query.filter(Case.case_status == case_status)
    return query.order_by(Case.opened_at.desc()).offset(skip).limit(limit).all()


@router.get("/lifecycle")
def lifecycle(current_user: User = Depends(get_current_user)):
    """Allowed status transitions, so clients only offer valid next steps."""
    return {status: sorted(nxt) for status, nxt in case_service.TRANSITIONS.items()}


@router.get("/{case_id}", response_model=CaseOut)
def get_case(case_id: UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return get_visible_case(db, case_id, current_user)


@router.get("/{case_id}/reports", response_model=list[ReportOut])
def case_reports(case_id: UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    get_visible_case(db, case_id, current_user)
    return (
        db.query(DiseaseReport)
        .join(CaseReport, CaseReport.report_id == DiseaseReport.id)
        .filter(CaseReport.case_id == case_id)
        .order_by(DiseaseReport.created_at)
        .all()
    )


@router.patch("/{case_id}/status", response_model=CaseOut)
def update_status(
    case_id: UUID,
    payload: CaseStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("veterinarian", "admin")),
):
    case = get_visible_case(db, case_id, current_user)
    if not case_service.can_transition(case.case_status, payload.case_status):
        allowed = sorted(case_service.TRANSITIONS.get(case.case_status, ()))
        raise HTTPException(
            status_code=409,
            detail=f"Cannot move case from '{case.case_status}' to '{payload.case_status}'. Allowed: {allowed or 'none'}",
        )
    previous = case.case_status
    case.case_status = payload.case_status
    if payload.case_status == "closed":
        case.closed_at = datetime.now(timezone.utc)
        for link in db.query(CaseReport).filter(CaseReport.case_id == case.id):
            db.get(DiseaseReport, link.report_id).report_status = "closed"
    audit.record(db, current_user, "case.status_changed", "case", case.id,
                 **{"from": previous, "to": payload.case_status, "note": payload.note})
    db.commit()
    db.refresh(case)
    return case


@router.post("/{case_id}/reports/{report_id}", status_code=status.HTTP_201_CREATED)
def link_report(
    case_id: UUID,
    report_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("veterinarian", "admin")),
):
    case = get_visible_case(db, case_id, current_user)
    report = db.get(DiseaseReport, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    _link(db, case, report, current_user)
    db.commit()
    return {"message": "Report linked to case"}


@router.post("/{case_id}/assignments", status_code=status.HTTP_201_CREATED)
def assign_collaborator(
    case_id: UUID,
    payload: CaseAssignmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("veterinarian", "admin")),
):
    get_visible_case(db, case_id, current_user)
    if not db.get(User, payload.user_id):
        raise HTTPException(status_code=404, detail="User not found")
    if db.query(CaseAssignment).filter_by(case_id=case_id, user_id=payload.user_id).first():
        raise HTTPException(status_code=409, detail="User already assigned to this case")
    db.add(CaseAssignment(case_id=case_id, user_id=payload.user_id,
                          assignment_role=payload.assignment_role, assigned_by=current_user.id))
    audit.record(db, current_user, "case.collaborator_assigned", "case", case_id,
                 user_id=payload.user_id, role=payload.assignment_role)
    db.commit()
    return {"message": "Collaborator assigned"}


@router.get("/{case_id}/timeline", response_model=list[TimelineEvent])
def timeline(case_id: UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Everything that happened on a case, in order — from the audit trail."""
    get_visible_case(db, case_id, current_user)
    entries = (
        db.query(AuditLog)
        .filter(AuditLog.entity_type == "case", AuditLog.entity_id == str(case_id))
        .order_by(AuditLog.created_at)
        .all()
    )
    return [TimelineEvent(at=e.created_at, action=e.action, actor_id=e.actor_id, details=e.details) for e in entries]
