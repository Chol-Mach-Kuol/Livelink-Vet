"""Single ingestion path for disease reports, shared by the app, offline sync and USSD."""
from sqlalchemy.orm import Session

from app.models.disease_report import DiseaseReport
from app.services import audit, notification_service
from app.services.triage import triage


def create_report(db: Session, reporter, *, channel: str = "app", **fields) -> tuple[DiseaseReport, bool]:
    """Create a triaged report. Returns (report, created); idempotent on client_ref."""
    client_ref = fields.get("client_ref")
    if client_ref:
        existing = db.query(DiseaseReport).filter(DiseaseReport.client_ref == client_ref).first()
        if existing:
            return existing, False

    result = triage(
        signs=fields.get("signs"),
        free_text=" ".join(filter(None, (fields.get("symptoms"), fields.get("description")))),
        species=fields.get("species") or "cattle",
        affected=fields.get("affected_count") or 0,
        deaths=fields.get("death_count") or 0,
    )
    report = DiseaseReport(
        reporter_id=getattr(reporter, "id", None),
        channel=channel,
        triage=result.as_dict(),
        suggested_priority=result.suggested_priority,
        zoonotic_alert=result.zoonotic_alert,
        **{**fields, "signs": result.detected_signs},
    )
    db.add(report)
    db.flush()
    audit.record(db, reporter, "report.submitted", "disease_report", report.id,
                 channel=channel, priority=result.suggested_priority)
    notification_service.alert_on_report(db, report)
    db.commit()
    db.refresh(report)
    return report, True
