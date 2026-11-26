"""USSD reporting for feature phones (Africa's Talking callback).

Most cattle keepers in pastoral South Sudan carry basic phones with no data.
USSD works on every handset and network without airtime for data, so a herder
can report sick animals from a cattle camp in under a minute.

Africa's Talking POSTs form fields (sessionId, serviceCode, phoneNumber, text)
where `text` is every answer so far joined by '*'. We reply with plain text
starting "CON " (expect more input) or "END " (close session).
"""
from fastapi import APIRouter, Depends, Form, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.disease_report import DiseaseReport
from app.models.location import Location
from app.models.user import RoleAssignment, User
from app.services import report_service
from app.services.surveillance import movement_advisory

router = APIRouter(prefix="/ussd", tags=["ussd"])

SPECIES_MENU = [("cattle", "Cattle"), ("goat", "Goats"), ("sheep", "Sheep"), ("camel", "Camels"), ("other", "Other")]
SIGN_MENU = [
    (["sudden_death"], "Sudden death"),
    (["bleeding_orifices"], "Bleeding nose/mouth"),
    (["cough", "difficult_breathing"], "Cough/hard breathing"),
    (["mouth_sores", "foot_lesions"], "Mouth/foot sores"),
    (["abortion"], "Abortions"),
    (["diarrhoea"], "Diarrhoea"),
    (["skin_nodules"], "Skin lumps"),
    (["weight_loss"], "Wasting"),
    ([], "Other"),
]
MAX_LOCATIONS = 5


def _menu(options: list[str]) -> str:
    return "\n".join(f"{i}. {o}" for i, o in enumerate(options, 1))


def _pick(value: str, options: list):
    if value.isdigit() and 1 <= int(value) <= len(options):
        return options[int(value) - 1]
    return None


def _count(value: str) -> int | None:
    return int(value) if value.isdigit() and int(value) <= 100_000 else None


def _place(loc: Location) -> str:
    parts = [p for p in (loc.cattle_camp or loc.payam or loc.boma, loc.county or loc.state) if p]
    return ", ".join(parts)[:24]


def _get_or_create_user(db: Session, phone: str) -> User:
    user = db.query(User).filter(User.phone_number == phone).first()
    if user:
        return user
    # The mobile network has verified the number; the person can claim the account later via /auth/register.
    user = User(full_name="USSD reporter", phone_number=phone, phone_verified=True)
    db.add(user)
    db.flush()
    db.add(RoleAssignment(user_id=user.id, role="cattle_keeper", verified=True))
    db.commit()
    return user


def _location_choices(db: Session, user: User) -> list[Location]:
    """The reporter's recent places first, then others — at most MAX_LOCATIONS to fit a USSD screen."""
    recent_ids = [
        lid for (lid,) in db.query(DiseaseReport.location_id)
        .filter(DiseaseReport.reporter_id == user.id)
        .order_by(DiseaseReport.created_at.desc())
        .limit(20)
    ]
    seen, choices = set(), []
    for lid in recent_ids:
        if lid not in seen and len(choices) < MAX_LOCATIONS:
            seen.add(lid)
            choices.append(db.get(Location, lid))
    if len(choices) < MAX_LOCATIONS:
        query = db.query(Location).order_by(Location.state, Location.county, Location.payam)
        if seen:
            query = query.filter(Location.id.notin_(seen))
        choices += query.limit(MAX_LOCATIONS - len(choices)).all()
    return choices


def handle(db: Session, phone: str, text: str) -> str:
    steps = [s.strip() for s in text.split("*")] if text else []
    if not steps:
        return "CON LiveLink Vet\n" + _menu(["Report sick animals", "Disease alerts near me"])

    user = _get_or_create_user(db, phone)
    choice, rest = steps[0], steps[1:]

    if choice == "2":
        locations = _location_choices(db, user)
        if not locations:
            return "END No places registered yet. Ask your animal health worker."
        if not rest:
            return "CON Where are your animals?\n" + _menu([_place(l) for l in locations])
        loc = _pick(rest[0], locations)
        if not loc:
            return "END Invalid choice. Please dial again."
        if loc.latitude is None:
            return "END No map position for this place yet. Ask your animal health worker."
        adv = movement_advisory(db, float(loc.latitude), float(loc.longitude))
        return f"END {adv['risk_level'].upper()}: {adv['guidance']}"[:182]

    if choice != "1":
        return "END Invalid choice. Please dial again."

    # 1 > species > sign > sick > dead > place > confirm
    if len(rest) == 0:
        return "CON Which animals?\n" + _menu([label for _, label in SPECIES_MENU])
    species = _pick(rest[0], SPECIES_MENU)
    if not species:
        return "END Invalid choice. Please dial again."
    if len(rest) == 1:
        return "CON Main sign?\n" + _menu([label for _, label in SIGN_MENU])
    sign = _pick(rest[1], SIGN_MENU)
    if not sign:
        return "END Invalid choice. Please dial again."
    if len(rest) == 2:
        return "CON How many animals are sick?"
    sick = _count(rest[2])
    if not sick:
        return "END Please enter a number above 0. Dial again."
    if len(rest) == 3:
        return "CON How many have died?"
    dead = _count(rest[3])
    if dead is None or dead > sick:
        return "END Deaths must be a number, not more than sick animals. Dial again."
    locations = _location_choices(db, user)
    if not locations:
        return "END No places registered yet. Ask your animal health worker."
    if len(rest) == 4:
        return "CON Where?\n" + _menu([_place(l) for l in locations])
    loc = _pick(rest[4], locations)
    if not loc:
        return "END Invalid choice. Please dial again."
    if len(rest) == 5:
        return f"CON {sick} {species[1].lower()} sick, {dead} dead, {sign[1].lower()}, at {_place(loc)}.\n1. Send\n2. Cancel"
    if rest[5] != "1":
        return "END Report cancelled."

    report, _ = report_service.create_report(
        db, user, channel="ussd",
        location_id=loc.id, species=species[0], signs=sign[0],
        symptoms=f"USSD: {sign[1]}", affected_count=sick, death_count=dead,
    )
    advice = report.triage["advice"][0] if report.triage["advice"] else "An animal health worker will review it."
    return f"END Report sent. Ref {str(report.id)[:8].upper()}. {advice}"[:182]


@router.post("", response_class=PlainTextResponse)
def ussd_callback(
    phoneNumber: str = Form(...),
    text: str = Form(""),
    sessionId: str = Form(""),
    serviceCode: str = Form(""),
    token: str | None = Query(None),
    db: Session = Depends(get_db),
):
    if settings.USSD_SHARED_SECRET and token != settings.USSD_SHARED_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")
    return handle(db, phoneNumber.strip(), text)
