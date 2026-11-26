from app.services.triage import extract_signs, triage


def test_extract_signs_from_free_text():
    assert extract_signs("Cows drooling and limping with blisters") == {"drooling", "lameness", "mouth_sores"}


def test_fmd_pattern():
    result = triage(signs=["mouth_sores", "foot_lesions", "drooling"], free_text=None, species="cattle")
    assert result.signals[0]["disease"] == "fmd"
    assert result.suggested_priority == "high"
    assert not result.zoonotic_alert


def test_species_matters():
    # PPR is a small-ruminant disease; the same signs in cattle rank it far lower.
    signs = ["nasal_discharge", "eye_discharge", "mouth_sores", "diarrhoea"]
    goat = triage(signs=signs, free_text=None, species="goat")
    cow = triage(signs=signs, free_text=None, species="cattle")
    assert goat.signals[0]["disease"] == "ppr"
    assert all(s["disease"] != "ppr" or s["match_strength"] < 0.3 for s in cow.signals)


def test_rvf_abortion_storm_is_zoonotic():
    result = triage(signs=["abortion", "young_deaths"], free_text=None, species="sheep")
    assert result.signals[0]["disease"] == "rvf"
    assert result.zoonotic_alert and result.suggested_priority == "urgent"


def test_high_mortality_escalates_without_signals():
    result = triage(signs=[], free_text="sick", species="cattle", affected=10, deaths=6)
    assert result.signals == []
    assert result.suggested_priority == "urgent"


def test_vague_report_stays_normal():
    result = triage(signs=["fever"], free_text=None, species="cattle", affected=2)
    assert result.suggested_priority == "normal"
    assert result.signals == []
