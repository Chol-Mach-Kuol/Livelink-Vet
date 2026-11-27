"""Admin tooling.

    python -m app.cli create-admin --name "Jane Doe" --phone +211900000000
    python -m app.cli seed-demo      # sample data + a demo vet login (not in production)
"""
import argparse
import getpass
import random
from datetime import datetime, timedelta, timezone

import app.models  # noqa: F401
from app.core.config import settings
from app.core.database import SessionLocal
from app.core.migrations import upgrade_db
from app.core.security import hash_password
from app.models.disease_report import DiseaseReport
from app.models.location import Location
from app.models.user import RoleAssignment, User
from app.services import report_service

# Approximate coordinates for demo data only.
DEMO_LOCATIONS = [
    dict(state="Jonglei", county="Bor South", payam="Makuach", cattle_camp="Malek camp", latitude=6.21, longitude=31.56),
    dict(state="Jonglei", county="Bor South", payam="Anyidi", cattle_camp="Anyidi camp", latitude=6.30, longitude=31.62),
    dict(state="Jonglei", county="Twic East", payam="Kongor", latitude=7.16, longitude=31.35),
    dict(state="Lakes", county="Rumbek Centre", payam="Rumbek", latitude=6.81, longitude=29.69),
    dict(state="Unity", county="Rubkona", payam="Bentiu", latitude=9.23, longitude=29.79),
    dict(state="Upper Nile", county="Malakal", payam="Malakal", latitude=9.53, longitude=31.65),
]


def create_admin(name: str, phone: str) -> None:
    password = getpass.getpass("Password (min 8 chars): ")
    if len(password) < 8:
        raise SystemExit("Password too short.")
    upgrade_db()
    with SessionLocal() as db:
        user = db.query(User).filter(User.phone_number == phone).first()
        if not user:
            user = User(full_name=name, phone_number=phone)
            db.add(user)
            db.flush()
        user.password_hash = hash_password(password)
        role = db.query(RoleAssignment).filter_by(user_id=user.id, role="admin").first()
        if role:
            role.verified = True
        else:
            db.add(RoleAssignment(user_id=user.id, role="admin", verified=True))
        db.commit()
    print(f"Admin ready: {phone}")


DEMO_VET_PHONE = "+211999000000"
DEMO_ADMIN_PHONE = "+211999000001"
DEMO_VET_PASSWORD = "livelink-demo"
# People waiting for an admin to approve their professional role (no password: demo only).
DEMO_PENDING = [("Achol Deng", "+211999000101", "veterinarian"), ("Gatluak Ruach", "+211999000102", "animal_health_worker")]


def _demo_user(db, name, phone, role, verified=True, password=DEMO_VET_PASSWORD):
    user = db.query(User).filter(User.phone_number == phone).first()
    if user:
        return user
    user = User(full_name=name, phone_number=phone, password_hash=hash_password(password) if password else None)
    db.add(user)
    db.flush()
    db.add(RoleAssignment(user_id=user.id, role=role, verified=verified))
    return user


def _demo_case(db, vet, reports):
    """One case already under investigation, so the cases page has something to show."""
    from app.models.case import Case, CaseAssignment, CaseReport
    from app.models.diagnosis import Diagnosis, LabResult
    from app.services import audit

    if db.query(Case).filter(Case.case_number == "LV-DEMO-0001").first() or not reports:
        return
    case = Case(case_number="LV-DEMO-0001", location_id=reports[0].location_id, assigned_vet_id=vet.id,
                priority="high", case_status="investigating")
    db.add(case)
    db.flush()
    db.add(CaseAssignment(case_id=case.id, user_id=vet.id, assignment_role="lead_veterinarian", assigned_by=vet.id))
    audit.record(db, vet, "case.opened", "case", case.id, priority="high")
    for r in reports:
        db.add(CaseReport(case_id=case.id, report_id=r.id))
        r.report_status = "linked_to_case"
        audit.record(db, vet, "case.report_linked", "case", case.id, report_id=r.id)
    audit.record(db, vet, "case.status_changed", "case", case.id,
                 **{"from": "open", "to": "investigating", "note": "Field visit planned"})
    diag = Diagnosis(case_id=case.id, veterinarian_id=vet.id, disease_name="Contagious Bovine Pleuropneumonia (CBPP)",
                     diagnosis_status="suspected", diagnostic_method="clinical_examination",
                     clinical_notes="Coughing and laboured breathing in several animals; extended neck posture.")
    lab = LabResult(case_id=case.id, laboratory_name="Central Veterinary Laboratory", test_name="CBPP cELISA",
                    sample_type="Serum", result="Samples sent; result pending.", verified_by=vet.id)
    db.add_all([diag, lab])
    db.flush()
    audit.record(db, vet, "case.diagnosis_recorded", "case", case.id, diagnosis_id=diag.id,
                 disease=diag.disease_name, status="suspected")
    audit.record(db, vet, "case.lab_result_added", "case", case.id, lab_result_id=lab.id, test=lab.test_name)


def seed_demo() -> None:
    if settings.ENVIRONMENT == "production":
        raise SystemExit("seed-demo is disabled in production (it creates a known demo login).")
    upgrade_db()
    rng = random.Random(42)
    with SessionLocal() as db:
        vet = _demo_user(db, "Demo Veterinarian", DEMO_VET_PHONE, "veterinarian")
        _demo_user(db, "Demo Administrator", DEMO_ADMIN_PHONE, "admin")
        for name, phone, role in DEMO_PENDING:
            _demo_user(db, name, phone, role, verified=False, password=None)
        locs = []
        for data in DEMO_LOCATIONS:
            loc = db.query(Location).filter_by(state=data["state"], county=data["county"], payam=data["payam"]).first()
            if not loc:
                loc = Location(**data)
                db.add(loc)
                db.flush()
            locs.append(loc)
        db.commit()

        scenarios = [
            ("cattle", ["cough", "difficult_breathing", "fever"], "Coughing, breathing hard with extended neck"),
            ("cattle", ["mouth_sores", "drooling", "lameness"], "Drooling and limping, blisters in mouth"),
            ("goat", ["nasal_discharge", "eye_discharge", "diarrhoea"], "Goats with runny nose and diarrhoea"),
            ("cattle", ["swollen_lymph_nodes", "ticks"], "Swollen glands, many ticks"),
        ]
        created = 0
        # Background reports spread over a month.
        for i in range(25):
            species, signs, text = rng.choice(scenarios)
            report, new = report_service.create_report(
                db, None, channel=rng.choice(["app", "ussd", "offline_sync"]), client_ref=f"demo-bg-{i:04d}",
                location_id=rng.choice(locs).id, species=species, signs=signs, symptoms=text,
                affected_count=rng.randint(1, 12), death_count=rng.randint(0, 1),
            )
            if new:
                report.created_at = datetime.now(timezone.utc) - timedelta(days=rng.randint(10, 30))
                created += 1
        # A suspected anthrax cluster in Bor South this week.
        for i in range(4):
            report, new = report_service.create_report(
                db, None, channel="ussd", client_ref=f"demo-anthrax-{i:04d}",
                location_id=locs[i % 2].id, species="cattle", signs=["sudden_death", "bleeding_orifices"],
                symptoms="Cattle found dead with blood from the nose", affected_count=6, death_count=3 + i % 2,
            )
            created += new
        cbpp = [r for r in db.query(DiseaseReport).filter(DiseaseReport.client_ref.like("demo-bg-%"))
                if (r.triage or {}).get("signals") and r.triage["signals"][0]["disease"] == "cbpp"][:2]
        _demo_case(db, vet, cbpp)
        db.commit()
    print(f"Seeded {len(locs)} locations and {created} reports (idempotent; re-running adds nothing).")
    print(f"Demo logins (password {DEMO_VET_PASSWORD}): vet {DEMO_VET_PHONE}, admin {DEMO_ADMIN_PHONE}")
    print("Open http://127.0.0.1:8000  (dashboard, cases, admin)")


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("create-admin")
    p.add_argument("--name", required=True)
    p.add_argument("--phone", required=True)
    sub.add_parser("seed-demo")
    args = parser.parse_args()
    if args.command == "create-admin":
        create_admin(args.name, args.phone)
    else:
        seed_demo()


if __name__ == "__main__":
    main()
