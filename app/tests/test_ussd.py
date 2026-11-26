PHONE = "+211912345678"


def _dial(client, text):
    resp = client.post("/api/v1/ussd", data={"sessionId": "s1", "serviceCode": "*384#", "phoneNumber": PHONE, "text": text})
    assert resp.status_code == 200
    return resp.text


def test_full_ussd_report_flow(client, make_user, location):
    location(cattle_camp="Malek camp")
    vet, _ = make_user("veterinarian")

    assert _dial(client, "").startswith("CON LiveLink Vet")
    assert "Cattle" in _dial(client, "1")
    assert "Sudden death" in _dial(client, "1*1")
    assert _dial(client, "1*1*1") == "CON How many animals are sick?"
    assert _dial(client, "1*1*1*6") == "CON How many have died?"
    assert "Malek camp" in _dial(client, "1*1*1*6*3")
    assert "1. Send" in _dial(client, "1*1*1*6*3*1")
    final = _dial(client, "1*1*1*6*3*1*1")
    assert final.startswith("END Report sent.")
    assert len(final) <= 182

    reports = client.get("/api/v1/reports", headers=vet).json()
    assert len(reports) == 1
    assert reports[0]["channel"] == "ussd"
    assert reports[0]["suggested_priority"] == "urgent"


def test_ussd_rejects_bad_input(client, location):
    location()
    assert _dial(client, "9").startswith("END Invalid")
    assert _dial(client, "1*1*1*0").startswith("END")
    assert _dial(client, "1*1*1*3*5").startswith("END Deaths")


def test_ussd_cancel(client, location):
    location()
    assert _dial(client, "1*1*1*3*0*1*2") == "END Report cancelled."


def test_ussd_alerts_menu(client, location):
    location()
    assert "Where" in _dial(client, "2")
    assert _dial(client, "2*1").startswith("END CLEAR")
