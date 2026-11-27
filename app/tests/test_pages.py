import pytest


@pytest.mark.parametrize("path,marker", [
    ("/", "Make livestock disease"),
    ("/report", "Report sick animals"),
    ("/dashboard", "Livestock disease surveillance"),
    ("/cases", "Case management"),
    ("/admin", "People &amp; activity"),
])
def test_pages_served_with_security_headers(client, path, marker):
    resp = client.get(path)
    assert resp.status_code == 200 and marker in resp.text
    assert "frame-ancestors 'none'" in resp.headers["content-security-policy"]
    assert resp.headers["x-content-type-options"] == "nosniff"


def test_pwa_assets(client):
    sw = client.get("/sw.js")
    assert sw.status_code == 200 and "javascript" in sw.headers["content-type"]
    manifest = client.get("/manifest.webmanifest").json()
    assert manifest["start_url"] == "/report"
    for asset in ("/static/theme.css", "/static/common.js", "/static/logo.svg"):
        assert client.get(asset).status_code == 200


def test_health(client):
    assert client.get("/health").json()["status"] == "ok"


def test_public_stats_are_aggregate_only(client, make_user, location):
    from app.routes import public
    public._CACHE["data"] = None
    keeper, _ = make_user()
    client.post("/api/v1/reports", json={
        "location_id": location(cattle_camp="Secret camp"), "symptoms": "Owner John: found dead, bleeding",
        "signs": ["sudden_death", "bleeding_orifices"], "affected_count": 5, "death_count": 3,
    }, headers=keeper)
    stats = client.get("/api/v1/public/stats").json()
    assert stats["reports"] == 1 and stats["animals_reported"] == 5
    assert stats["counties_reporting"] == 1 and stats["zoonotic_alerts"] == 1
    assert "Secret" not in str(stats) and "John" not in str(stats)
