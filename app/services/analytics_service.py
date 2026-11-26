"""Aggregates and anonymised research exports."""
from collections import Counter, defaultdict
from datetime import datetime, timezone

from sqlalchemy.orm import Session, joinedload

from app.models.disease_report import DiseaseReport


def _iso_week(dt: datetime) -> str:
    y, w, _ = dt.isocalendar()
    return f"{y}-W{w:02d}"


def weekly_trends(db: Session) -> list[dict]:
    """Reports, animals affected and deaths per ISO week (portable across databases)."""
    buckets: dict[str, Counter] = defaultdict(Counter)
    for created, affected, deaths in db.query(
        DiseaseReport.created_at, DiseaseReport.affected_count, DiseaseReport.death_count
    ):
        b = buckets[_iso_week(created)]
        b["reports"] += 1
        b["affected"] += affected or 0
        b["deaths"] += deaths or 0
    return [{"week": w, **dict(c)} for w, c in sorted(buckets.items())]


def anonymised_export(db: Session, k: int) -> dict:
    """De-identified report rows for researchers.

    - No reporter identity, free text, exact timestamps, payam/boma/camp or GPS.
    - Time is coarsened to ISO week, place to county.
    - k-anonymity: any (week, state, county) group with fewer than k reports has
      its county generalised to "suppressed" so small herds cannot be singled out.
    """
    reports = db.query(DiseaseReport).options(joinedload(DiseaseReport.location)).all()
    rows = []
    for r in reports:
        signals = (r.triage or {}).get("signals") or []
        rows.append({
            "week": _iso_week(r.created_at),
            "state": r.location.state,
            "county": r.location.county or "unknown",
            "species": r.species,
            "channel": r.channel,
            "signs": sorted(r.signs or []),
            "top_signal": signals[0]["disease"] if signals else None,
            "affected_count": r.affected_count,
            "death_count": r.death_count,
            "zoonotic_alert": bool(r.zoonotic_alert),
        })

    group_sizes = Counter((row["week"], row["state"], row["county"]) for row in rows)
    suppressed = 0
    for row in rows:
        if group_sizes[(row["week"], row["state"], row["county"])] < k:
            row["county"] = "suppressed"
            suppressed += 1

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "k_anonymity": k,
        "row_count": len(rows),
        "rows_with_suppressed_county": suppressed,
        "rows": rows,
    }
