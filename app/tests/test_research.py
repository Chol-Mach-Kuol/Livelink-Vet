def test_research_export_is_anonymised(client, make_user, location):
    keeper, _ = make_user()
    researcher, _ = make_user("researcher")
    admin, _ = make_user("admin")
    busy = location(county="Bor South", payam="Makuach", cattle_camp="Secret camp")
    quiet = location(state="Unity", county="Rubkona")
    for _ in range(5):
        client.post("/api/v1/reports", json={"location_id": busy, "symptoms": "Owner John says cough",
                                             "affected_count": 2}, headers=keeper)
    client.post("/api/v1/reports", json={"location_id": quiet, "symptoms": "fever", "affected_count": 1}, headers=keeper)

    data = client.get("/api/v1/analytics/research-export", headers=researcher).json()
    assert data["row_count"] == 6
    assert data["rows_with_suppressed_county"] == 1  # the single Rubkona report falls below k=5
    flat = str(data["rows"])
    for leaked in ("John", "Secret camp", "Makuach", "reporter", "latitude"):
        assert leaked not in flat

    csv = client.get("/api/v1/analytics/research-export", params={"format": "csv"}, headers=researcher)
    assert csv.headers["content-type"].startswith("text/csv")
    assert csv.text.count("\n") == 7

    log = client.get("/api/v1/users/audit-log", params={"entity_type": "dataset"}, headers=admin).json()
    assert len(log) == 2


def test_keeper_cannot_export(client, make_user):
    keeper, _ = make_user()
    assert client.get("/api/v1/analytics/research-export", headers=keeper).status_code == 403


def test_summary_and_trends(client, make_user, location):
    vet, _ = make_user("veterinarian")
    client.post("/api/v1/reports", json={"location_id": location(), "symptoms": "fever",
                                         "affected_count": 3, "death_count": 1}, headers=vet)
    summary = client.get("/api/v1/analytics/summary", headers=vet).json()
    assert summary["total_reports"] == 1 and summary["animal_deaths"] == 1
    assert summary["reports_by_channel"] == {"app": 1}
    trends = client.get("/api/v1/analytics/trends", headers=vet).json()
    assert trends[0]["reports"] == 1
