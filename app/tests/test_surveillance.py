import uuid
from datetime import datetime, timedelta, timezone

from app.models.disease_report import DiseaseReport
from app.services.surveillance import ears_c2, haversine_km


def test_haversine_bor_to_juba():
    # Bor to Juba is roughly 170 km.
    assert 150 < haversine_km(6.21, 31.56, 4.85, 31.58) < 170


def test_ears_c2_flags_spike_not_noise():
    assert ears_c2([1, 0, 2, 1, 1, 0, 1, 0, 0, 7])[0] is True
    assert ears_c2([1, 0, 2, 1, 1, 0, 1, 0, 0, 2])[0] is False
    assert ears_c2([0] * 9 + [1])[0] is False  # one report is never an alert


def _submit(client, headers, loc, **kw):
    payload = {"location_id": loc, "symptoms": "fever", "affected_count": 4, **kw}
    assert client.post("/api/v1/reports", json=payload, headers=headers).status_code == 201


def test_cluster_detection_and_advisory(client, make_user, location):
    vet, _ = make_user("veterinarian")
    keeper, _ = make_user()
    near_a = location(county="Bor South", lat=6.21, lon=31.56)
    near_b = location(county="Bor South", lat=6.30, lon=31.62)  # ~12 km away
    far = location(state="Unity", county="Rubkona", lat=9.23, lon=29.79)
    for loc in (near_a, near_b, near_a):
        _submit(client, keeper, loc, signs=["sudden_death", "bleeding_orifices"], death_count=2)
    _submit(client, keeper, far)

    alerts = client.get("/api/v1/surveillance/alerts", headers=vet).json()
    clusters = alerts["spatial_clusters"]
    assert len(clusters) == 1
    assert clusters[0]["report_count"] == 3
    assert clusters[0]["dominant_signal"] == "anthrax"
    assert clusters[0]["zoonotic_alert"] is True
    assert alerts["summary"]["zoonotic_clusters"] == 1

    geo = client.get("/api/v1/surveillance/clusters.geojson", headers=vet).json()
    assert geo["type"] == "FeatureCollection" and len(geo["features"]) == 1

    # Any signed-in herder can check before moving; no report ids leak.
    adv = client.get("/api/v1/surveillance/advisory", params={"latitude": 6.4, "longitude": 31.6}, headers=keeper).json()
    assert adv["risk_level"] == "danger"
    assert "report_ids" not in adv["active_clusters"][0]
    clear = client.get("/api/v1/surveillance/advisory", params={"location_id": far}, headers=keeper).json()
    assert clear["risk_level"] == "clear"


def test_alerts_require_verified_role(client, make_user):
    keeper, _ = make_user()
    assert client.get("/api/v1/surveillance/alerts", headers=keeper).status_code == 403


def test_county_spike_detected(client, make_user, location, db):
    vet, _ = make_user("veterinarian")
    loc = location()
    for _ in range(6):
        _submit(client, vet, loc)
    # One background report a week earlier.
    old = DiseaseReport(location_id=uuid.UUID(loc), symptoms="x", affected_count=1,
                        created_at=datetime.now(timezone.utc) - timedelta(days=6))
    db.add(old)
    db.commit()
    spikes = client.get("/api/v1/surveillance/alerts", headers=vet).json()["temporal_aberrations"]
    assert spikes and spikes[0]["county"] == "Bor South" and spikes[0]["reports_today"] == 6
