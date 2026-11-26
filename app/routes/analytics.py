import csv
import io

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.case import Case
from app.models.diagnosis import Diagnosis
from app.models.disease_report import DiseaseReport
from app.models.user import User
from app.permissions.access_control import require_role
from app.services import analytics_service, audit

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/summary")
def summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("veterinarian", "admin", "researcher")),
):
    by_channel = dict(db.query(DiseaseReport.channel, func.count(DiseaseReport.id)).group_by(DiseaseReport.channel))
    by_priority = dict(
        db.query(DiseaseReport.suggested_priority, func.count(DiseaseReport.id)).group_by(DiseaseReport.suggested_priority)
    )
    return {
        "total_reports": db.query(func.count(DiseaseReport.id)).scalar(),
        "open_cases": db.query(func.count(Case.id)).filter(Case.case_status.notin_(["resolved", "closed"])).scalar(),
        "confirmed_diagnoses": db.query(func.count(Diagnosis.id)).filter(Diagnosis.diagnosis_status == "confirmed").scalar(),
        "reports_with_deaths": db.query(func.count(DiseaseReport.id)).filter(DiseaseReport.death_count > 0).scalar(),
        "zoonotic_alerts": db.query(func.count(DiseaseReport.id)).filter(DiseaseReport.zoonotic_alert.is_(True)).scalar(),
        "animals_affected": db.query(func.coalesce(func.sum(DiseaseReport.affected_count), 0)).scalar(),
        "animal_deaths": db.query(func.coalesce(func.sum(DiseaseReport.death_count), 0)).scalar(),
        "reports_by_channel": by_channel,
        "reports_by_priority": by_priority,
    }


@router.get("/trends")
def trends(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("veterinarian", "admin", "researcher")),
):
    return analytics_service.weekly_trends(db)


@router.get("/research-export")
def research_export(
    format: str = Query("json", pattern="^(json|csv)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("researcher", "admin")),
):
    """De-identified dataset with k-anonymity suppression. Every export is audited."""
    data = analytics_service.anonymised_export(db, settings.RESEARCH_EXPORT_K)
    audit.record(db, current_user, "research.exported", "dataset", None, rows=data["row_count"], format=format)
    db.commit()
    if format == "json":
        return data
    buf = io.StringIO()
    fields = list(data["rows"][0].keys()) if data["rows"] else ["week"]
    writer = csv.DictWriter(buf, fieldnames=fields)
    writer.writeheader()
    for row in data["rows"]:
        writer.writerow({**row, "signs": ";".join(row["signs"])})
    return StreamingResponse(
        iter([buf.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=livelink_vet_research_export.csv"},
    )
