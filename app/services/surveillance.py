"""Early-warning surveillance.

Two complementary signals:

1. Temporal aberration (EARS C2, as used by the US CDC Early Aberration Reporting
   System): flags a county when today's report count is far above its recent
   7-day baseline, with a 2-day guard band so a growing outbreak does not hide
   inside its own baseline.

2. Spatial clusters: groups recent reports that lie within CLUSTER_RADIUS_KM of
   each other (single-linkage), which is how outbreaks look among mobile cattle
   camps that cross county lines.
"""
from __future__ import annotations

import math
import statistics
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.models.disease_report import DiseaseReport

EARTH_RADIUS_KM = 6371.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def report_coords(report: DiseaseReport) -> tuple[float, float] | None:
    """Device GPS if present, else the location's coordinates."""
    if report.latitude is not None and report.longitude is not None:
        return float(report.latitude), float(report.longitude)
    loc = report.location
    if loc is not None and loc.latitude is not None and loc.longitude is not None:
        return float(loc.latitude), float(loc.longitude)
    return None


def _as_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _top_signal(report: DiseaseReport) -> str | None:
    signals = (report.triage or {}).get("signals") or []
    return signals[0]["disease"] if signals else None


# ----------------------------------------------------------------- EARS C2

def ears_c2(series: list[int], threshold: float = 3.0, min_count: int = 2) -> tuple[bool, float]:
    """Return (alert, score) for the last value in a daily count series.

    Baseline is days t-9..t-3 (7 days, 2-day guard band). The SD floor keeps a
    silent baseline from turning one report into an alert.
    """
    if len(series) < 10:
        series = [0] * (10 - len(series)) + series
    today, baseline = series[-1], series[-10:-3]
    mean = statistics.fmean(baseline)
    sd = max(statistics.pstdev(baseline), 0.5)
    score = (today - mean) / sd
    return (score > threshold and today >= min_count), round(score, 2)


def county_aberrations(db: Session, as_of: date | None = None) -> list[dict]:
    as_of = as_of or datetime.now(timezone.utc).date()
    start = datetime.combine(as_of - timedelta(days=9), datetime.min.time(), tzinfo=timezone.utc)
    reports = (
        db.query(DiseaseReport)
        .options(joinedload(DiseaseReport.location))
        .filter(DiseaseReport.created_at >= start)
        .all()
    )
    days = [as_of - timedelta(days=i) for i in range(9, -1, -1)]
    counts: dict[tuple[str, str], Counter] = defaultdict(Counter)
    for r in reports:
        key = (r.location.state, r.location.county or "unknown")
        counts[key][_as_utc(r.created_at).date()] += 1

    alerts = []
    for (state, county), by_day in counts.items():
        series = [by_day.get(d, 0) for d in days]
        alert, score = ears_c2(series)
        if alert:
            alerts.append({
                "type": "temporal_aberration",
                "method": "EARS-C2",
                "state": state,
                "county": county,
                "date": as_of.isoformat(),
                "reports_today": series[-1],
                "baseline_mean": round(statistics.fmean(series[:7]), 2),
                "score": score,
            })
    return sorted(alerts, key=lambda a: a["score"], reverse=True)


# ----------------------------------------------------------- spatial clusters

def spatial_clusters(
    db: Session,
    radius_km: float | None = None,
    window_days: int | None = None,
    min_reports: int | None = None,
) -> list[dict]:
    radius_km = radius_km or settings.CLUSTER_RADIUS_KM
    window_days = window_days or settings.CLUSTER_WINDOW_DAYS
    min_reports = min_reports or settings.CLUSTER_MIN_REPORTS

    since = datetime.now(timezone.utc) - timedelta(days=window_days)
    reports = (
        db.query(DiseaseReport)
        .options(joinedload(DiseaseReport.location))
        .filter(DiseaseReport.created_at >= since)
        .all()
    )
    points = [(r, c) for r in reports if (c := report_coords(r))]

    # Single-linkage clustering with union-find; O(n²) is fine at surveillance volumes.
    parent = list(range(len(points)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(points)):
        for j in range(i + 1, len(points)):
            if haversine_km(*points[i][1], *points[j][1]) <= radius_km:
                parent[find(i)] = find(j)

    groups: dict[int, list[int]] = defaultdict(list)
    for i in range(len(points)):
        groups[find(i)].append(i)

    clusters = []
    for members in groups.values():
        rs = [points[i][0] for i in members]
        deaths = sum(r.death_count or 0 for r in rs)
        if len(rs) < min_reports and not (len(rs) >= 2 and deaths > 0):
            continue
        lats = [points[i][1][0] for i in members]
        lons = [points[i][1][1] for i in members]
        signals = Counter(s for r in rs if (s := _top_signal(r)))
        clusters.append({
            "type": "spatial_cluster",
            "centroid": {"latitude": round(statistics.fmean(lats), 5), "longitude": round(statistics.fmean(lons), 5)},
            "radius_km": round(max(haversine_km(statistics.fmean(lats), statistics.fmean(lons), la, lo)
                                   for la, lo in zip(lats, lons)), 1),
            "report_count": len(rs),
            "animals_affected": sum(r.affected_count or 0 for r in rs),
            "deaths": deaths,
            "dominant_signal": signals.most_common(1)[0][0] if signals else None,
            "zoonotic_alert": any(r.zoonotic_alert for r in rs),
            "counties": sorted({f"{r.location.county or '?'}, {r.location.state}" for r in rs}),
            "first_report": min(_as_utc(r.created_at) for r in rs).isoformat(),
            "last_report": max(_as_utc(r.created_at) for r in rs).isoformat(),
            "report_ids": [str(r.id) for r in rs],
        })
    return sorted(clusters, key=lambda c: (c["zoonotic_alert"], c["deaths"], c["report_count"]), reverse=True)


def movement_advisory(db: Session, latitude: float, longitude: float, radius_km: float | None = None) -> dict:
    """What a herder or AHW needs before moving a herd: active clusters nearby."""
    radius_km = radius_km or settings.ADVISORY_RADIUS_KM
    nearby = []
    for c in spatial_clusters(db):
        dist = haversine_km(latitude, longitude, c["centroid"]["latitude"], c["centroid"]["longitude"])
        if dist - c["radius_km"] <= radius_km:
            nearby.append({**c, "distance_km": round(dist, 1)})
    nearby.sort(key=lambda c: c["distance_km"])
    level = "clear"
    if nearby:
        level = "danger" if any(c["distance_km"] <= c["radius_km"] + 10 or c["zoonotic_alert"] for c in nearby) else "caution"
    return {
        "risk_level": level,
        "search_radius_km": radius_km,
        "active_clusters": nearby,
        "guidance": {
            "clear": "No active disease clusters reported nearby.",
            "caution": "Disease activity reported in the wider area. Avoid shared water points and markets with herds from affected areas.",
            "danger": "Active outbreak nearby. Avoid moving the herd into or through the affected area and contact an animal health worker.",
        }[level],
    }


def to_geojson(clusters: list[dict]) -> dict:
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [c["centroid"]["longitude"], c["centroid"]["latitude"]]},
                "properties": {k: v for k, v in c.items() if k not in ("centroid", "report_ids")},
            }
            for c in clusters
        ],
    }
