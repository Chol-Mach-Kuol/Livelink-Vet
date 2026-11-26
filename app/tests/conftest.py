import os

# Configure before the app is imported: isolated SQLite DB, no real SMS.
os.environ["DATABASE_URL"] = "sqlite:///./test_livelink.db"
os.environ["ENVIRONMENT"] = "test"
os.environ["AT_API_KEY"] = ""
os.environ.pop("USSD_SHARED_SECRET", None)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import app.models  # noqa: E402,F401
from app.core.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models.location import Location  # noqa: E402
from app.models.user import RoleAssignment, User  # noqa: E402


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()


_phone_counter = iter(range(100000, 999999))


@pytest.fixture
def make_user(client, db):
    """Register a user and return (auth headers, user id). verified=True approves the role."""
    def _make(role="cattle_keeper", verified=True):
        phone = f"+211900{next(_phone_counter)}"
        # Admins cannot self-register, so they start as keepers and get the role granted directly.
        resp = client.post("/api/v1/auth/register", json={
            "full_name": "Test User", "phone_number": phone, "password": "pass12345",
            "role": "cattle_keeper" if role == "admin" else role,
        })
        assert resp.status_code == 201, resp.text
        user_id = resp.json()["id"]
        user = db.query(User).filter(User.phone_number == phone).one()
        if role == "admin":
            db.query(RoleAssignment).filter_by(user_id=user.id).delete()
            db.add(RoleAssignment(user_id=user.id, role="admin", verified=verified))
        else:
            db.query(RoleAssignment).filter_by(user_id=user.id).one().verified = verified
        db.commit()
        token = client.post("/api/v1/auth/login", json={"phone_number": phone, "password": "pass12345"}).json()["access_token"]
        return {"Authorization": f"Bearer {token}"}, user_id
    return _make


@pytest.fixture
def location(db):
    def _make(state="Jonglei", county="Bor South", lat=6.21, lon=31.56, **kw):
        loc = Location(state=state, county=county, latitude=lat, longitude=lon, **kw)
        db.add(loc)
        db.commit()
        db.refresh(loc)
        return str(loc.id)
    return _make
