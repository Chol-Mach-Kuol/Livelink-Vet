VALID_USER = {
    "full_name": "Test Keeper",
    "phone_number": "+211900000001",
    "password": "securepass123",
    "role": "cattle_keeper",
}


def test_register_success(client):
    response = client.post("/api/v1/auth/register", json=VALID_USER)
    assert response.status_code == 201
    body = response.json()
    assert body["phone_number"] == VALID_USER["phone_number"]
    assert body["roles"] == [{"role": "cattle_keeper", "verified": True}]


def test_register_duplicate_phone(client):
    client.post("/api/v1/auth/register", json=VALID_USER)
    assert client.post("/api/v1/auth/register", json=VALID_USER).status_code == 400


def test_cannot_self_register_as_admin(client):
    response = client.post("/api/v1/auth/register", json={**VALID_USER, "role": "admin"})
    assert response.status_code == 422


def test_professional_role_starts_unverified(client):
    response = client.post("/api/v1/auth/register", json={**VALID_USER, "role": "veterinarian"})
    assert response.json()["roles"] == [{"role": "veterinarian", "verified": False}]


def test_short_password_rejected(client):
    assert client.post("/api/v1/auth/register", json={**VALID_USER, "password": "short"}).status_code == 422


def test_login_success(client):
    client.post("/api/v1/auth/register", json=VALID_USER)
    response = client.post("/api/v1/auth/login", json={
        "phone_number": VALID_USER["phone_number"], "password": VALID_USER["password"],
    })
    assert response.status_code == 200
    token = response.json()["access_token"]
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.json()["phone_number"] == VALID_USER["phone_number"]


def test_login_wrong_password(client):
    client.post("/api/v1/auth/register", json=VALID_USER)
    response = client.post("/api/v1/auth/login", json={
        "phone_number": VALID_USER["phone_number"], "password": "wrongpassword",
    })
    assert response.status_code == 401


def test_garbage_token_rejected(client):
    assert client.get("/api/v1/auth/me", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_ussd_user_can_claim_account(client):
    client.post("/api/v1/ussd", data={"phoneNumber": VALID_USER["phone_number"], "text": "1"})
    response = client.post("/api/v1/auth/register", json=VALID_USER)
    assert response.status_code == 201
    assert response.json()["full_name"] == "Test Keeper"
