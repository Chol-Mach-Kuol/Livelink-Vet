def _submit(client, headers, location_id, **kw):
    payload = {"location_id": location_id, "symptoms": "fever", "affected_count": 3, **kw}
    return client.post("/api/v1/reports", json=payload, headers=headers).json()["id"]


def test_vet_can_create_case(client, make_user, location):
    vet, _ = make_user("veterinarian")
    response = client.post("/api/v1/cases", json={"location_id": location(), "priority": "high"}, headers=vet)
    assert response.status_code == 201
    assert response.json()["case_status"] == "open"


def test_cattle_keeper_cannot_create_case(client, make_user, location):
    keeper, _ = make_user()
    response = client.post("/api/v1/cases", json={"location_id": location()}, headers=keeper)
    assert response.status_code == 403


def test_unverified_vet_cannot_create_case(client, make_user, location):
    vet, _ = make_user("veterinarian", verified=False)
    assert client.post("/api/v1/cases", json={"location_id": location()}, headers=vet).status_code == 403


def test_invalid_priority_rejected(client, make_user, location):
    vet, _ = make_user("veterinarian")
    response = client.post("/api/v1/cases", json={"location_id": location(), "priority": "whenever"}, headers=vet)
    assert response.status_code == 422


def test_case_lifecycle_and_timeline(client, make_user, location):
    vet, _ = make_user("veterinarian")
    keeper, _ = make_user()
    loc = location()
    report_id = _submit(client, keeper, loc)
    case = client.post("/api/v1/cases", json={"location_id": loc, "report_ids": [report_id]}, headers=vet).json()
    cid = case["id"]

    assert client.get(f"/api/v1/reports/{report_id}", headers=vet).json()["report_status"] == "linked_to_case"

    # Illegal jump is refused with the allowed next steps.
    bad = client.patch(f"/api/v1/cases/{cid}/status", json={"case_status": "resolved"}, headers=vet)
    assert bad.status_code == 409

    client.patch(f"/api/v1/cases/{cid}/status", json={"case_status": "investigating"}, headers=vet)
    diag = client.post(f"/api/v1/cases/{cid}/diagnoses", json={
        "disease_name": "CBPP", "diagnosis_status": "confirmed", "diagnostic_method": "laboratory_test",
    }, headers=vet)
    assert diag.status_code == 201
    assert client.get(f"/api/v1/cases/{cid}", headers=vet).json()["case_status"] == "diagnosed"

    for step in ("resolved", "closed"):
        assert client.patch(f"/api/v1/cases/{cid}/status", json={"case_status": step}, headers=vet).status_code == 200
    assert client.get(f"/api/v1/reports/{report_id}", headers=vet).json()["report_status"] == "closed"

    actions = [e["action"] for e in client.get(f"/api/v1/cases/{cid}/timeline", headers=vet).json()]
    assert actions[0] == "case.opened"
    assert "case.diagnosis_recorded" in actions
    assert actions.count("case.status_changed") == 4


def test_keeper_sees_only_cases_with_their_reports(client, make_user, location):
    vet, _ = make_user("veterinarian")
    keeper, _ = make_user()
    other, _ = make_user()
    loc = location()
    rid = _submit(client, keeper, loc)
    client.post("/api/v1/cases", json={"location_id": loc, "report_ids": [rid]}, headers=vet)
    client.post("/api/v1/cases", json={"location_id": loc}, headers=vet)

    assert len(client.get("/api/v1/cases", headers=vet).json()) == 2
    assert len(client.get("/api/v1/cases", headers=keeper).json()) == 1
    assert client.get("/api/v1/cases", headers=other).json() == []


def test_student_sees_assigned_case_only(client, make_user, location):
    vet, _ = make_user("veterinarian")
    student, student_id = make_user("student")
    cid = client.post("/api/v1/cases", json={"location_id": location()}, headers=vet).json()["id"]
    assert client.get(f"/api/v1/cases/{cid}", headers=student).status_code == 404
    client.post(f"/api/v1/cases/{cid}/assignments",
                json={"user_id": student_id, "assignment_role": "student"}, headers=vet)
    assert client.get(f"/api/v1/cases/{cid}", headers=student).status_code == 200
    assert client.get(f"/api/v1/cases/{cid}/diagnoses", headers=student).status_code == 200


def test_report_cannot_be_linked_twice(client, make_user, location):
    vet, _ = make_user("veterinarian")
    loc = location()
    rid = _submit(client, vet, loc)
    c1 = client.post("/api/v1/cases", json={"location_id": loc}, headers=vet).json()["id"]
    c2 = client.post("/api/v1/cases", json={"location_id": loc}, headers=vet).json()["id"]
    assert client.post(f"/api/v1/cases/{c1}/reports/{rid}", headers=vet).status_code == 201
    assert client.post(f"/api/v1/cases/{c2}/reports/{rid}", headers=vet).status_code == 409


def test_case_from_reports_takes_highest_priority(client, make_user, location):
    vet, _ = make_user("veterinarian")
    loc = location()
    r1 = _submit(client, vet, loc)
    r2 = _submit(client, vet, loc, signs=["sudden_death", "bleeding_orifices"], death_count=2)
    case = client.post("/api/v1/cases/from-reports", json={"report_ids": [r1, r2]}, headers=vet).json()
    assert case["priority"] == "urgent"
    assert len(client.get(f"/api/v1/cases/{case['id']}/reports", headers=vet).json()) == 2
