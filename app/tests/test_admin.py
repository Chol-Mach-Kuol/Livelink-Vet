def test_pending_queue_approve_and_decline(client, make_user):
    admin, _ = make_user("admin")
    _, vet_id = make_user("veterinarian", verified=False)
    _, ahw_id = make_user("animal_health_worker", verified=False)
    make_user()  # verified keeper: not pending

    pending = client.get("/api/v1/users", params={"pending_verification": True}, headers=admin).json()
    assert {u["id"] for u in pending} == {vet_id, ahw_id}

    assert client.post(f"/api/v1/users/{vet_id}/verify-role/veterinarian", headers=admin).status_code == 200
    assert client.post(f"/api/v1/users/{ahw_id}/reject-role/animal_health_worker", headers=admin).status_code == 200
    assert client.get("/api/v1/users", params={"pending_verification": True}, headers=admin).json() == []

    # Declined person keeps a basic account as a cattle keeper.
    users = {u["id"]: u for u in client.get("/api/v1/users", params={"limit": 200}, headers=admin).json()}
    assert users[ahw_id]["roles"] == [{"role": "cattle_keeper", "verified": True}]

    actions = [e["action"] for e in client.get("/api/v1/users/audit-log", headers=admin).json()]
    assert "user.role_verified" in actions and "user.role_rejected" in actions


def test_decline_only_pending_claims(client, make_user):
    admin, _ = make_user("admin")
    _, vet_id = make_user("veterinarian")  # already verified
    assert client.post(f"/api/v1/users/{vet_id}/reject-role/veterinarian", headers=admin).status_code == 404


def test_search_and_reactivate(client, make_user):
    admin, _ = make_user("admin")
    headers, uid = make_user()
    phone = client.get("/api/v1/auth/me", headers=headers).json()["phone_number"]
    found = client.get("/api/v1/users", params={"q": phone[-6:]}, headers=admin).json()
    assert [u["id"] for u in found] == [uid]

    client.post(f"/api/v1/users/{uid}/deactivate", headers=admin)
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401
    client.post(f"/api/v1/users/{uid}/reactivate", headers=admin)
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200


def test_admin_endpoints_need_admin(client, make_user):
    vet, uid = make_user("veterinarian")
    assert client.get("/api/v1/users", headers=vet).status_code == 403
    assert client.post(f"/api/v1/users/{uid}/reactivate", headers=vet).status_code == 403


def test_lifecycle_endpoint(client, make_user):
    vet, _ = make_user("veterinarian")
    lc = client.get("/api/v1/cases/lifecycle", headers=vet).json()
    assert lc["open"] == ["awaiting_lab", "closed", "diagnosed", "investigating"]
    assert lc["closed"] == []
