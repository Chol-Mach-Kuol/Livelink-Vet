"""SMS alerts via Africa's Talking, with an outbox table for traceability.

Without AT_API_KEY configured, messages are recorded with status "logged"
instead of sent, so development and tests never hit the network.
"""
import logging

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.activity import Notification
from app.models.disease_report import DiseaseReport
from app.models.location import Location
from app.models.user import RoleAssignment, User

log = logging.getLogger("livelink.notifications")

RESPONDER_ROLES = ("veterinarian", "animal_health_worker")


def _at_endpoint() -> str:
    host = "api.sandbox.africastalking.com" if settings.AT_USERNAME == "sandbox" else "api.africastalking.com"
    return f"https://{host}/version1/messaging"


def send_sms(db: Session, phone: str, message: str, reason: str, recipient_id=None) -> Notification:
    note = Notification(recipient_id=recipient_id, phone_number=phone, message=message[:480], reason=reason)
    if not settings.AT_API_KEY:
        note.status = "logged"
        log.info("SMS (not sent, no API key) to %s: %s", phone, message)
    else:
        data = {"username": settings.AT_USERNAME, "to": phone, "message": note.message}
        if settings.AT_SENDER_ID:
            data["from"] = settings.AT_SENDER_ID
        try:
            resp = httpx.post(
                _at_endpoint(), data=data, timeout=10,
                headers={"apiKey": settings.AT_API_KEY, "Accept": "application/json"},
            )
            resp.raise_for_status()
            note.status = "sent"
        except httpx.HTTPError as exc:
            note.status = "failed"
            note.error = str(exc)[:500]
    db.add(note)
    return note


def responders_for(db: Session, location: Location) -> list[User]:
    """Verified vets and animal health workers.

    Users do not yet carry a home area, so every verified responder is alerted.
    `location` is accepted so area-based routing can be added without changing callers.
    """
    return (
        db.query(User)
        .join(RoleAssignment, RoleAssignment.user_id == User.id)
        .filter(
            RoleAssignment.role.in_(RESPONDER_ROLES),
            RoleAssignment.verified.is_(True),
            User.is_active.is_(True),
        )
        .distinct()
        .all()
    )


def alert_on_report(db: Session, report: DiseaseReport) -> int:
    """Notify responders about urgent or zoonotic reports. Returns messages queued."""
    if report.suggested_priority != "urgent" and not report.zoonotic_alert:
        return 0
    loc = report.location or db.get(Location, report.location_id)
    signals = (report.triage or {}).get("signals") or []
    top = signals[0]["name"] if signals else "unknown cause"
    place = ", ".join(p for p in (loc.cattle_camp, loc.payam, loc.county, loc.state) if p)
    tag = "ZOONOTIC RISK " if report.zoonotic_alert else ""
    msg = (
        f"LiveLink Vet {tag}ALERT: {report.affected_count} {report.species} sick, "
        f"{report.death_count} dead at {place}. Signal: {top} (unconfirmed). Ref {str(report.id)[:8]}"
    )
    users = [u for u in responders_for(db, loc) if u.id != report.reporter_id]
    for u in users:
        send_sms(db, u.phone_number, msg, reason="urgent_report", recipient_id=u.id)
    return len(users)
