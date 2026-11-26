"""Case lifecycle: allowed status transitions and who can see which case."""
from sqlalchemy import or_
from sqlalchemy.orm import Query, Session

from app.models.case import Case, CaseAssignment, CaseReport
from app.models.disease_report import DiseaseReport
from app.permissions.access_control import verified_roles

TRANSITIONS: dict[str, set[str]] = {
    "open": {"investigating", "awaiting_lab", "diagnosed", "closed"},
    "investigating": {"awaiting_lab", "diagnosed", "monitoring", "closed"},
    "awaiting_lab": {"investigating", "diagnosed"},
    "diagnosed": {"monitoring", "resolved"},
    "monitoring": {"resolved", "investigating"},
    "resolved": {"closed", "investigating"},
    "closed": set(),
}

FULL_CASE_ACCESS = {"veterinarian", "admin", "animal_health_worker"}


def can_transition(current: str, new: str) -> bool:
    return new in TRANSITIONS.get(current, set())


def visible_cases(db: Session, user) -> Query:
    """Vets, AHWs and admins see every case; others only cases they are assigned to
    or that contain one of their own reports."""
    query = db.query(Case)
    if verified_roles(user) & FULL_CASE_ACCESS:
        return query
    assigned = db.query(CaseAssignment.case_id).filter(CaseAssignment.user_id == user.id)
    own_reports = (
        db.query(CaseReport.case_id)
        .join(DiseaseReport, DiseaseReport.id == CaseReport.report_id)
        .filter(DiseaseReport.reporter_id == user.id)
    )
    return query.filter(or_(Case.id.in_(assigned), Case.id.in_(own_reports)))
