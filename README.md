# LiveLink Vet

Collaborative veterinary intelligence and livestock disease surveillance platform.
Initial focus: pastoralist communities in South Sudan.

**Mission:** Make livestock disease predictable, not just treatable.

---

## What makes it different

Most livestock-health apps assume a smartphone, a data connection and a fixed farm.
Pastoral South Sudan has none of these reliably. LiveLink Vet is built for it:

| Problem in the field | What LiveLink Vet does |
| --- | --- |
| Most herders carry basic phones with no data | **USSD reporting** (`/ussd`, Africa's Talking): any handset, any network, under a minute. The account is created from the network-verified number and can be claimed later. |
| Field workers lose signal for days | **Offline batch sync** (`/reports/batch`): each report carries a device-generated `client_ref`, so retrying an upload never creates duplicates. |
| Anthrax, Rift Valley Fever and rabies kill people as well as animals | **Syndromic triage** on every report: ranks the 13 priority diseases (CBPP, FMD, PPR, anthrax, RVF, HS, ECF, LSD, …), flags zoonotic and WOAH-notifiable signals, suggests a review priority, and returns safety advice (e.g. *do not open the carcass*). |
| Urgent reports sit unread | **SMS alerts** to verified vets and animal health workers for urgent or zoonotic reports, with an outbox so every alert can be traced. |
| Outbreaks cross county lines with moving cattle camps | **Early warning**: EARS-C2 aberration detection (the CDC Early Aberration Reporting System method) per county, plus distance-based **spatial clusters** that ignore administrative borders. GeoJSON output plugs into any map. |
| Migration spreads disease | **Herd-movement advisory** (`/surveillance/advisory`, also on USSD menu 2): *clear / caution / danger* for a camp or a planned stop. |
| Research needs data; herders need privacy | **k-anonymised research export**: no identities, free text, GPS or sub-county places; week-level dates; small groups suppressed. Every export is audited. |
| Clinical accountability | **Case lifecycle state machine**, a per-case **timeline**, and an append-only **audit log**. |

> Triage output is decision support. It ranks what to rule in or out and how urgently a
> professional should look; it is never a diagnosis and never prescribes medication.
> The knowledge base is plain data in `app/services/triage.py`, so veterinarians can audit and extend it.

---

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

The app runs out of the box on SQLite. For PostgreSQL, create `.env`:

```dotenv
DATABASE_URL=postgresql+psycopg://postgres:password@localhost:5432/livelink_vet
SECRET_KEY=a-long-random-string
ENVIRONMENT=production          # refuses to start with the default SECRET_KEY

# Optional: real SMS via Africa's Talking (otherwise SMS is logged, not sent)
AT_USERNAME=your-username
AT_API_KEY=your-api-key
USSD_SHARED_SECRET=random-token # callback URL becomes /api/v1/ussd?token=...
```

### Database migrations

```bash
alembic upgrade head                        # new database
alembic stamp 0001 && alembic upgrade head  # database created by v0.1
```

### First admin and demo data

```bash
python -m app.cli create-admin --name "Your Name" --phone +2119XXXXXXXX
python -m app.cli seed-demo   # 6 locations, 29 reports including a suspected anthrax cluster
```

## Run

```bash
uvicorn app.main:app --reload
```

API docs: <http://127.0.0.1:8000/docs>

Surveillance dashboard: <http://127.0.0.1:8000/dashboard>. It shows a live map of reports and
outbreak clusters, early-warning alerts and an urgent-report feed, and refreshes every minute.
Sign in as a verified vet, animal health worker, researcher or admin. After `seed-demo`, the
demo login is `+211999000000` / `livelink-demo` (`seed-demo` refuses to run in production).

Try USSD locally:

```bash
curl -X POST localhost:8000/api/v1/ussd -d phoneNumber=+211900000001 -d text=1*1*1*6*3*1*1
```

## Test

```bash
pytest app/tests/
```

---

## Roles

| Role | Access |
| --- | --- |
| `cattle_keeper` | Submit and view own reports; see cases containing them; movement advisories |
| `animal_health_worker` | Submit field observations, see all reports and cases, early-warning alerts |
| `veterinarian` | Open and manage cases, record diagnoses and lab results |
| `student` | Access assigned cases only (supervised) |
| `researcher` | Anonymised exports, aggregate analytics, alerts |
| `admin` | Verify roles, deactivate users, audit log, SMS outbox |

Cattle keepers are active immediately. Every professional role grants **nothing** until an
administrator verifies it. Admins cannot self-register; use `python -m app.cli create-admin`.

## Key endpoints (`/api/v1`)

| Endpoint | Purpose |
| --- | --- |
| `GET /reports/signs` | Sign codes, species and the disease knowledge base, for building forms |
| `POST /reports/triage-preview` | See red flags while filling a form, without saving |
| `POST /reports` · `POST /reports/batch` | Submit online / sync offline reports |
| `POST /ussd` | Africa's Talking USSD callback |
| `GET /surveillance/alerts` | EARS-C2 county spikes plus spatial clusters |
| `GET /surveillance/clusters.geojson` | Clusters for maps |
| `GET /surveillance/advisory` | Herd-movement risk for a place |
| `POST /cases/from-reports` | Open one case for a cluster's reports |
| `PATCH /cases/{id}/status` · `GET /cases/{id}/timeline` | Lifecycle and history |
| `GET /analytics/research-export?format=csv` | De-identified dataset |

## Case lifecycle

```text
open ─► investigating ─► awaiting_lab ─► diagnosed ─► monitoring ─► resolved ─► closed
```

Only valid transitions are accepted (see `app/services/case_service.py`). A confirmed
diagnosis moves the case to `diagnosed` automatically. Closing a case closes its reports.

## Important

- The platform does not prescribe medication automatically.
- AI may support pattern detection but qualified professionals make all clinical decisions.
- A submitted report is not a confirmed diagnosis.
- USSD menus are English-only for now. Dinka, Nuer and Juba Arabic versions should be written
  and checked by native speakers, not machine-translated.
