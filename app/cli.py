"""Admin tooling.

    python -m app.cli create-admin --name "Jane Doe" --phone +211900000000
    python -m app.cli seed-demo      # sample locations and reports for a demo
"""
import argparse
import getpass
import random
from datetime import datetime, timedelta, timezone

import app.models  # noqa: F401
from app.core.database import Base, SessionLocal, engine
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
    Base.metadata.create_all(bind=engine)
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


def seed_demo() -> None:
    Base.metadata.create_all(bind=engine)
    rng = random.Random(42)
    with SessionLocal() as db:
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
        db.commit()
    print(f"Seeded {len(locs)} locations and {created} reports (idempotent; re-running adds nothing).")


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
