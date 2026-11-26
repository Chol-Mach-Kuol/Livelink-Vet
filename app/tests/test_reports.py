def _report(location_id, **kw):
    return {"location_id": location_id, "symptoms": "Fever and loss of appetite",
            "affected_count": 10, "death_count": 1, **kw}


def test_submit_report_is_triaged(client, make_user, location):
    headers, _ = make_user()
    response = client.post("/api/v1/reports", json=_report(
        location(), symptoms="Cattle coughing badly, difficult breathing", affected_count=8, death_count=0,
    ), headers=headers)
    assert response.status_code == 201
    body = response.json()
    assert body["report_status"] == "submitted"
    assert body["triage"]["signals"][0]["disease"] == "cbpp"
    assert body["suggested_priority"] == "high"
    assert "disclaimer" in body["triage"]


def test_anthrax_signs_raise_zoonotic_alert_and_notify(client, make_user, location):
    vet_headers, _ = make_user("veterinarian")
    admin_headers, _ = make_user("admin")
    headers, _ = make_user()
    body = client.post("/api/v1/reports", json=_report(
        location(), signs=["sudden_death", "bleeding_orifices"], symptoms="Found dead", death_count=3, affected_count=4,
    ), headers=headers).json()
    assert body["zoonotic_alert"] is True
    assert body["suggested_priority"] == "urgent"
    assert any("Do NOT open" in a for a in body["triage"]["advice"])

    notes = client.get("/api/v1/users/notifications", headers=admin_headers).json()
    assert len(notes) == 1 and "ZOONOTIC" in notes[0]["message"]


def test_death_count_exceeds_affected(client, make_user, location):
    headers, _ = make_user()
    response = client.post("/api/v1/reports", json=_report(location(), affected_count=5, death_count=10), headers=headers)
    assert response.status_code == 422


def test_unknown_sign_rejected(client, make_user, location):
    headers, _ = make_user()
    response = client.post("/api/v1/reports", json=_report(location(), signs=["glowing"]), headers=headers)
    assert response.status_code == 422


def test_unknown_location_404(client, make_user):
    headers, _ = make_user()
    response = client.post("/api/v1/reports", json=_report("00000000-0000-0000-0000-000000000000"), headers=headers)
    assert response.status_code == 404


def test_submit_report_unauthenticated(client, location):
    assert client.post("/api/v1/reports", json=_report(location())).status_code == 403


def test_unverified_researcher_cannot_read_others_reports(client, make_user, location):
    keeper, _ = make_user()
    report_id = client.post("/api/v1/reports", json=_report(location()), headers=keeper).json()["id"]
    snoop, _ = make_user("researcher", verified=False)
    assert client.get("/api/v1/reports", headers=snoop).json() == []
    assert client.get(f"/api/v1/reports/{report_id}", headers=snoop).status_code == 403


def test_verified_vet_reads_all(client, make_user, location):
    keeper, _ = make_user()
    client.post("/api/v1/reports", json=_report(location()), headers=keeper)
    vet, _ = make_user("veterinarian")
    assert len(client.get("/api/v1/reports", headers=vet).json()) == 1


def test_offline_batch_sync_is_idempotent(client, make_user, location):
    headers, _ = make_user("animal_health_worker")
    loc = location()
    batch = {"reports": [_report(loc, client_ref="device1-0001"), _report(loc, client_ref="device1-0002")]}
    first = client.post("/api/v1/reports/batch", json=batch, headers=headers).json()
    assert [r["created"] for r in first] == [True, True]
    retry = client.post("/api/v1/reports/batch", json=batch, headers=headers).json()
    assert [r["created"] for r in retry] == [False, False]
    assert [r["id"] for r in retry] == [r["id"] for r in first]


def test_batch_requires_client_ref(client, make_user, location):
    headers, _ = make_user()
    response = client.post("/api/v1/reports/batch", json={"reports": [_report(location())]}, headers=headers)
    assert response.status_code == 422


def test_triage_preview_does_not_save(client, make_user):
    headers, _ = make_user()
    preview = client.post("/api/v1/reports/triage-preview", json={
        "species": "goat", "symptoms": "runny nose, watery eyes, diarrhoea and mouth sores",
    }, headers=headers).json()
    assert preview["signals"][0]["disease"] == "ppr"
    vet, _ = make_user("veterinarian")
    assert client.get("/api/v1/reports", headers=vet).json() == []


def test_reference_data(client):
    data = client.get("/api/v1/reports/signs").json()
    assert {"signs", "species", "diseases"} <= data.keys()
