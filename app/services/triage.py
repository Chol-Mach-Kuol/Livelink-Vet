"""Syndromic triage: decision support for incoming disease reports.

Maps reported clinical signs to the priority transboundary and zoonotic diseases of
pastoral South Sudan, flags public-health risk, and suggests a review priority.

This is NOT a diagnosis. It ranks what a veterinarian should rule in or out first,
and decides how urgently a qualified professional should look at the report.
The knowledge base is deliberately transparent (plain data, no black box) so that
veterinarians can audit and extend it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# --------------------------------------------------------------------------- signs
# Standardised sign codes -> (label, free-text keywords that imply the sign).
SIGNS: dict[str, tuple[str, tuple[str, ...]]] = {
    "fever": ("Fever / hot body", ("fever", "hot body", "high temperature")),
    "cough": ("Coughing", ("cough",)),
    "difficult_breathing": ("Difficult or fast breathing", ("difficult breathing", "difficulty breathing", "breathing fast", "laboured", "labored", "gasping", "panting", "extended neck")),
    "nasal_discharge": ("Discharge from the nose", ("nasal discharge", "runny nose", "discharge from nose", "nose discharge", "frothy nose")),
    "eye_discharge": ("Discharge or tears from the eyes", ("eye discharge", "watery eyes", "tears", "lacrimation")),
    "mouth_sores": ("Sores or blisters in the mouth", ("mouth sore", "mouth lesion", "blister", "ulcer", "vesicle", "sores in mouth")),
    "drooling": ("Drooling / excess saliva", ("drool", "saliva", "salivat", "foam at mouth", "foaming")),
    "lameness": ("Lameness / limping", ("lame", "limp", "cannot walk", "difficulty walking")),
    "foot_lesions": ("Sores between the hooves", ("foot sore", "hoof", "foot lesion", "sores on feet")),
    "diarrhoea": ("Diarrhoea", ("diarrh", "loose dung", "watery dung", "scour")),
    "sudden_death": ("Sudden death without prior illness", ("sudden death", "died suddenly", "found dead", "dead without", "died quickly")),
    "bleeding_orifices": ("Dark blood from nose, mouth or anus", ("bleeding from", "blood from nose", "blood from mouth", "blood from anus", "bleeding orifices", "unclotted blood")),
    "abortion": ("Abortions", ("abort", "lost calf", "lost pregnancy", "miscarr")),
    "young_deaths": ("Many deaths among newborn / young animals", ("calves dying", "young dying", "newborn", "kids dying", "lambs dying")),
    "swollen_lymph_nodes": ("Swollen glands (lymph nodes)", ("swollen gland", "lymph node", "swollen node")),
    "skin_nodules": ("Lumps or nodules on the skin", ("lump", "nodule", "skin swelling", "pox", "skin lesion")),
    "weight_loss": ("Wasting / weight loss", ("weight loss", "wasting", "thin", "losing weight", "emaciat")),
    "throat_swelling": ("Swelling of throat, jaw or brisket", ("swollen throat", "throat swelling", "swollen neck", "brisket", "swollen jaw")),
    "crackling_swelling": ("Hot swelling of a leg muscle that crackles", ("crackl", "crepitus", "gas under skin", "swollen leg", "swollen muscle")),
    "abnormal_behaviour": ("Aggression or abnormal behaviour", ("aggress", "attacking", "abnormal behav", "mad", "restless", "bellowing")),
    "paralysis": ("Paralysis / cannot stand", ("paralys", "cannot stand", "down and cannot rise", "recumbent")),
    "pale_gums": ("Pale gums or eyes (anaemia)", ("pale gum", "pale eye", "anaemi", "anemi")),
    "ticks": ("Heavy tick burden", ("tick",)),
    "reduced_milk": ("Sudden drop in milk", ("less milk", "milk drop", "reduced milk", "no milk")),
    "swollen_joints": ("Swollen joints or testicles", ("swollen joint", "swollen testic", "hygroma", "orchitis")),
}

SPECIES = ("cattle", "goat", "sheep", "camel", "donkey", "poultry", "dog", "other")


@dataclass(frozen=True)
class Disease:
    code: str
    name: str
    species: tuple[str, ...]
    signs: dict[str, float]  # sign -> weight (key signs weigh more)
    zoonotic: bool = False
    woah_listed: bool = False  # notifiable to WOAH (World Organisation for Animal Health)
    advice: str = ""
    min_signs: int = 2  # matched signs needed before the signal is shown


# Weights: 3 = highly characteristic, 2 = typical, 1 = supportive.
DISEASES: tuple[Disease, ...] = (
    Disease(
        "anthrax", "Anthrax", ("cattle", "goat", "sheep", "camel", "donkey"),
        {"sudden_death": 3, "bleeding_orifices": 3, "fever": 1, "throat_swelling": 1},
        zoonotic=True, woah_listed=True, min_signs=1,
        advice="Do NOT open, butcher, eat or sell carcasses. Keep people and animals away and alert a veterinarian and health authorities immediately.",
    ),
    Disease(
        "rvf", "Rift Valley Fever", ("cattle", "goat", "sheep", "camel"),
        {"abortion": 3, "young_deaths": 3, "fever": 1, "bleeding_orifices": 1, "diarrhoea": 1},
        zoonotic=True, woah_listed=True,
        advice="Avoid contact with aborted material, blood and raw milk. Use gloves. Report people with fever to the nearest health facility.",
    ),
    Disease(
        "rabies", "Rabies", ("cattle", "goat", "sheep", "camel", "donkey", "dog"),
        {"abnormal_behaviour": 3, "drooling": 2, "paralysis": 2},
        zoonotic=True, woah_listed=True,
        advice="Isolate the animal without handling it. Anyone bitten or exposed to saliva must wash the wound for 15 minutes and seek medical care urgently.",
    ),
    Disease(
        "brucellosis", "Brucellosis", ("cattle", "goat", "sheep", "camel"),
        {"abortion": 3, "swollen_joints": 2, "reduced_milk": 1},
        zoonotic=True, woah_listed=True,
        advice="Do not handle aborted material with bare hands. Boil milk before drinking.",
    ),
    Disease(
        "cbpp", "Contagious Bovine Pleuropneumonia (CBPP)", ("cattle",),
        {"cough": 3, "difficult_breathing": 3, "fever": 1, "nasal_discharge": 1, "weight_loss": 1},
        woah_listed=True,
        advice="Separate coughing animals from the herd and avoid moving the herd until examined.",
    ),
    Disease(
        "fmd", "Foot-and-Mouth Disease (FMD)", ("cattle", "goat", "sheep"),
        {"mouth_sores": 3, "foot_lesions": 3, "drooling": 2, "lameness": 2, "fever": 1, "reduced_milk": 1},
        woah_listed=True,
        advice="Restrict herd movement and contact with other herds, markets and water points.",
    ),
    Disease(
        "ppr", "Peste des Petits Ruminants (PPR)", ("goat", "sheep"),
        {"fever": 1, "nasal_discharge": 2, "eye_discharge": 2, "mouth_sores": 2, "diarrhoea": 2, "cough": 1, "difficult_breathing": 1},
        woah_listed=True,
        advice="Isolate sick goats and sheep and avoid taking the flock to markets.",
    ),
    Disease(
        "hs", "Haemorrhagic Septicaemia", ("cattle",),
        {"throat_swelling": 3, "fever": 2, "difficult_breathing": 2, "sudden_death": 1},
        woah_listed=True,
        advice="Rapidly fatal — seek a veterinarian today. Isolate affected animals.",
    ),
    Disease(
        "blackleg", "Blackleg", ("cattle",),
        {"crackling_swelling": 3, "lameness": 2, "sudden_death": 1, "fever": 1},
        advice="Mostly affects young cattle (6 months – 2 years). Do not open carcasses.",
    ),
    Disease(
        "ecf", "East Coast Fever (Theileriosis)", ("cattle",),
        {"swollen_lymph_nodes": 3, "ticks": 2, "fever": 1, "difficult_breathing": 1, "nasal_discharge": 1},
        woah_listed=True,
        advice="Check the herd for ticks and contact an animal health worker.",
    ),
    Disease(
        "lsd", "Lumpy Skin Disease", ("cattle",),
        {"skin_nodules": 3, "fever": 1, "swollen_lymph_nodes": 1, "reduced_milk": 1},
        woah_listed=True,
        advice="Isolate animals with skin lumps; biting insects spread the disease.",
    ),
    Disease(
        "sgp", "Sheep and Goat Pox", ("goat", "sheep"),
        {"skin_nodules": 3, "fever": 1, "nasal_discharge": 1, "difficult_breathing": 1},
        woah_listed=True,
        advice="Isolate affected animals and avoid markets.",
    ),
    Disease(
        "tryps", "Trypanosomiasis", ("cattle", "goat", "sheep", "camel", "donkey"),
        {"weight_loss": 3, "pale_gums": 2, "fever": 1, "eye_discharge": 1},
        woah_listed=True,
        advice="Note whether the herd grazed near tsetse/fly areas and contact an animal health worker.",
    ),
)

DISCLAIMER = (
    "Decision support only. Signals rank diseases to rule in or out; they are not a diagnosis. "
    "A qualified veterinarian makes all clinical decisions."
)

PRIORITY_ORDER = ("low", "normal", "high", "urgent")


@dataclass
class TriageResult:
    signals: list[dict] = field(default_factory=list)
    red_flags: list[str] = field(default_factory=list)
    suggested_priority: str = "normal"
    zoonotic_alert: bool = False
    detected_signs: list[str] = field(default_factory=list)
    advice: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "signals": self.signals,
            "red_flags": self.red_flags,
            "suggested_priority": self.suggested_priority,
            "zoonotic_alert": self.zoonotic_alert,
            "detected_signs": self.detected_signs,
            "advice": self.advice,
            "disclaimer": DISCLAIMER,
        }


def extract_signs(text: str | None) -> set[str]:
    """Pick standard sign codes out of free text (English keywords)."""
    if not text:
        return set()
    lowered = re.sub(r"\s+", " ", text.lower())
    return {code for code, (_, keywords) in SIGNS.items() if any(k in lowered for k in keywords)}


def _raise(current: str, to: str) -> str:
    return to if PRIORITY_ORDER.index(to) > PRIORITY_ORDER.index(current) else current


def triage(
    *,
    signs: list[str] | None,
    free_text: str | None,
    species: str = "cattle",
    affected: int = 0,
    deaths: int = 0,
) -> TriageResult:
    observed = set(signs or []) | extract_signs(free_text)
    result = TriageResult(detected_signs=sorted(observed))

    for disease in DISEASES:
        matched = [s for s in disease.signs if s in observed]
        if len(matched) < disease.min_signs:
            continue
        strength = sum(disease.signs[s] for s in matched) / sum(disease.signs.values())
        if species not in disease.species:
            strength *= 0.3  # wrong host species: keep visible but heavily down-weighted
        if strength < 0.25:
            continue
        result.signals.append({
            "disease": disease.code,
            "name": disease.name,
            "match_strength": round(strength, 2),
            "matched_signs": matched,
            "zoonotic": disease.zoonotic,
            "woah_listed": disease.woah_listed,
        })

    result.signals.sort(key=lambda s: s["match_strength"], reverse=True)
    result.signals = result.signals[:3]

    priority = "normal"
    for sig in result.signals:
        disease = next(d for d in DISEASES if d.code == sig["disease"])
        if disease.advice:
            result.advice.append(disease.advice)
        if sig["zoonotic"] and sig["match_strength"] >= 0.5:
            result.zoonotic_alert = True
            result.red_flags.append(f"Possible zoonosis ({disease.name}) — human health risk")
            priority = _raise(priority, "urgent")
        elif sig["woah_listed"] and sig["match_strength"] >= 0.5:
            result.red_flags.append(f"Possible notifiable disease ({disease.name})")
            priority = _raise(priority, "high")

    mortality = deaths / affected if affected else 0
    if deaths >= 5 or (deaths >= 2 and mortality >= 0.2):
        result.red_flags.append(f"High mortality: {deaths} of {affected} affected animals died")
        priority = _raise(priority, "urgent")
    elif deaths >= 1:
        priority = _raise(priority, "high" if mortality >= 0.1 else "normal")
    if affected >= 20:
        result.red_flags.append(f"Large number affected ({affected})")
        priority = _raise(priority, "high")
    if "sudden_death" in observed and "bleeding_orifices" in observed:
        priority = _raise(priority, "urgent")

    result.suggested_priority = priority
    return result
