"""Training load metrics computed from data/garmin.db. Numbers only -- no coaching logic."""

import sqlite3
import time
from datetime import date, datetime, timedelta

from garminconnect import GarminConnectConnectionError, GarminConnectTooManyRequestsError

from config import FTP, HR_SHARE_FLAG_THRESHOLD, HR_ZONE_IF
from db import get_db

CTL_DAYS = 42
ATL_DAYS = 7


def connect() -> sqlite3.Connection:
    return get_db()


def compute_activity_tss(row: sqlite3.Row) -> tuple[float, str]:
    """(tss, load_source). Power-based TSS where has_power, hrTSS fallback otherwise."""
    if row["has_power"]:
        np = row["norm_power"] if row["norm_power"] is not None else row["avg_power"]
        duration_s = row["duration_s"] or 0
        if np and duration_s:
            intensity_factor = np / FTP
            tss = duration_s * np * intensity_factor / (FTP * 3600) * 100
            return tss, "power"

    tss = 0.0
    for zone, if_value in HR_ZONE_IF.items():
        secs = row[f"hr_time_in_zone_{zone}"] or 0
        tss += (secs / 3600) * if_value**2 * 100
    return tss, "hr"


def load_activities(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT * FROM activities ORDER BY start_local").fetchall()
    results = []
    for row in rows:
        tss, load_source = compute_activity_tss(row)
        results.append(
            {
                "activity_id": row["activity_id"],
                "date": row["start_local"][:10],
                "activity_type": row["activity_type"],
                "duration_s": row["duration_s"] or 0,
                "distance_m": row["distance_m"] or 0,
                "elevation_gain": row["elevation_gain"] or 0,
                "has_power": bool(row["has_power"]),
                "tss": tss,
                "load_source": load_source,
                "activity_training_load": row["activity_training_load"],
            }
        )
    return results


def calibration_report(conn: sqlite3.Connection) -> dict:
    """Relationship between power-derived TSS and Garmin's own activity_training_load,
    for activities that have both. Reports the fit and its spread -- does not apply
    any conversion, since a weak fit would make one unsafe."""
    rows = conn.execute(
        "SELECT norm_power, avg_power, duration_s, activity_training_load "
        "FROM activities WHERE has_power = 1 AND activity_training_load IS NOT NULL"
    ).fetchall()

    pairs = []
    for r in rows:
        np = r["norm_power"] if r["norm_power"] is not None else r["avg_power"]
        duration_s = r["duration_s"]
        if np and duration_s:
            intensity_factor = np / FTP
            tss = duration_s * np * intensity_factor / (FTP * 3600) * 100
            pairs.append((tss, r["activity_training_load"]))

    n = len(pairs)
    if n < 3:
        return {"n": n, "slope": None, "intercept": None, "r_squared": None, "residual_std": None}

    xs = [p[0] for p in pairs]
    ys = [p[1] for p in pairs]
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    var_x = sum((x - mean_x) ** 2 for x in xs)
    var_y = sum((y - mean_y) ** 2 for y in ys)
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))

    if var_x == 0:
        return {"n": n, "slope": None, "intercept": None, "r_squared": None, "residual_std": None}

    slope = cov / var_x
    intercept = mean_y - slope * mean_x
    residuals = [y - (slope * x + intercept) for x, y in zip(xs, ys)]
    ss_res = sum(e**2 for e in residuals)
    r_squared = 1 - ss_res / var_y if var_y else None
    residual_std = (ss_res / (n - 2)) ** 0.5 if n > 2 else None

    return {"n": n, "slope": slope, "intercept": intercept, "r_squared": r_squared, "residual_std": residual_std}


def daily_load_series(activities: list[dict]) -> dict[str, float]:
    """date-string -> summed TSS that day (0.0 for days with no activity, once expanded by ctl_atl_tsb)."""
    daily: dict[str, float] = {}
    for a in activities:
        daily[a["date"]] = daily.get(a["date"], 0.0) + a["tss"]
    return daily


def ctl_atl_tsb(daily: dict[str, float]) -> list[dict]:
    """Exponentially weighted CTL(42d)/ATL(7d)/TSB, one row per calendar day, full history.

    Seeded from the mean load over the first CTL_DAYS/ATL_DAYS of the series (rather than
    from zero) so the ramp reflects steady-state training already under way before the
    recorded window starts, not an artificial build from an empty bank.

    TSB[t] = CTL[t-1] - ATL[t-1] (form heading into day t, the standard PMC convention --
    yesterday's fitness minus yesterday's fatigue).
    """
    if not daily:
        return []

    dates = sorted(daily.keys())
    start = datetime.strptime(dates[0], "%Y-%m-%d").date()
    end = datetime.strptime(dates[-1], "%Y-%m-%d").date()

    all_days = []
    d = start
    while d <= end:
        all_days.append(d)
        d += timedelta(days=1)
    loads = [daily.get(d.isoformat(), 0.0) for d in all_days]

    seed_ctl = sum(loads[:CTL_DAYS]) / min(CTL_DAYS, len(loads))
    seed_atl = sum(loads[:ATL_DAYS]) / min(ATL_DAYS, len(loads))

    ctl_prev, atl_prev = seed_ctl, seed_atl
    rows = []
    for d, load in zip(all_days, loads):
        tsb = ctl_prev - atl_prev
        ctl = ctl_prev + (load - ctl_prev) / CTL_DAYS
        atl = atl_prev + (load - atl_prev) / ATL_DAYS
        rows.append({"date": d.isoformat(), "load": load, "ctl": ctl, "atl": atl, "tsb": tsb})
        ctl_prev, atl_prev = ctl, atl

    return rows


def weekly_aggregates(activities: list[dict]) -> list[dict]:
    """One row per calendar week (Monday start), oldest first."""
    weeks: dict[date, dict] = {}
    for a in activities:
        d = datetime.strptime(a["date"], "%Y-%m-%d").date()
        week_start = d - timedelta(days=d.weekday())
        w = weeks.setdefault(
            week_start,
            {
                "week_start": week_start.isoformat(),
                "total_tss": 0.0,
                "hr_tss": 0.0,
                "hours": 0.0,
                "distance_km": 0.0,
                "elevation_m": 0.0,
                "n_rides": 0,
                "n_with_power": 0,
                "n_without_power": 0,
            },
        )
        w["total_tss"] += a["tss"]
        if a["load_source"] == "hr":
            w["hr_tss"] += a["tss"]
        w["hours"] += a["duration_s"] / 3600
        w["distance_km"] += a["distance_m"] / 1000
        w["elevation_m"] += a["elevation_gain"]
        w["n_rides"] += 1
        if a["has_power"]:
            w["n_with_power"] += 1
        else:
            w["n_without_power"] += 1

    result = []
    for week_start in sorted(weeks.keys()):
        w = weeks[week_start]
        w["hr_share"] = w["hr_tss"] / w["total_tss"] if w["total_tss"] else 0.0
        w["flagged"] = w["hr_share"] > HR_SHARE_FLAG_THRESHOLD
        del w["hr_tss"]
        result.append(w)
    return result


DURABILITY_MIN_DURATION_S = 7200  # 2h -- "rides over 2h" per plan section 8


def _normalized_power_from_stream(times: list[float], powers: list[float]) -> float | None:
    """Standard Coggan NP: 30s rolling average power, mean of the 4th power, 4th root.
    Source samples from Garmin's chart-resolution stream are unevenly spaced (~1-3s apart),
    so this resamples onto a 1Hz grid by linear interpolation first."""
    import pandas as pd

    if len(times) < 30:
        return None
    s = pd.Series(powers, index=times).groupby(level=0).mean().sort_index()
    grid = range(int(s.index.min()), int(s.index.max()) + 1)
    s = s.reindex(s.index.union(grid)).interpolate("index").reindex(grid)
    rolling = s.rolling(30, min_periods=1).mean()
    return float((rolling.pow(4).mean()) ** 0.25)


def compute_durability(conn: sqlite3.Connection, garmin, min_duration_s: int = DURABILITY_MIN_DURATION_S) -> int:
    """Fetch + cache normalized power in the first third vs final third of moving time,
    for rides over 2h with power (plan section 8's key metric, not yet tracked anywhere
    else). Requires a live Garmin client -- the per-activity power stream isn't part of
    the synced summary data. Results are cached in the `durability` table keyed by
    activity_id, so repeat calls only fetch newly-qualifying rides. Returns the count of
    rides newly computed this call.

    Splits are by moving time (sumDuration), not clock time, so rest stops in multi-day
    rides don't distort what counts as the "final third."
    """
    candidates = conn.execute(
        "SELECT activity_id FROM activities WHERE has_power = 1 AND duration_s >= ? ORDER BY start_local",
        (min_duration_s,),
    ).fetchall()

    n_computed = 0
    for c in candidates:
        activity_id = c["activity_id"]
        already = conn.execute(
            "SELECT 1 FROM durability WHERE activity_id = ?", (activity_id,)
        ).fetchone()
        if already is not None:
            continue

        detail = None
        for attempt in range(2):
            try:
                detail = garmin.get_activity_details(str(activity_id))
                break
            except (GarminConnectConnectionError, GarminConnectTooManyRequestsError) as e:
                if attempt == 0:
                    time.sleep(5)
                    continue
                print(f"  WARNING: failed to fetch stream for activity {activity_id}: {e}, skipping")
        if detail is None:
            continue

        descriptors = {d["key"]: d["metricsIndex"] for d in detail.get("metricDescriptors", [])}
        power_idx = descriptors.get("directPower")
        time_idx = descriptors.get("sumDuration", descriptors.get("sumElapsedDuration"))
        if power_idx is None or time_idx is None:
            continue

        samples = [
            (m["metrics"][time_idx], m["metrics"][power_idx])
            for m in detail.get("activityDetailMetrics", [])
            if m["metrics"][time_idx] is not None and m["metrics"][power_idx] is not None
        ]
        if not samples:
            continue

        total_duration = samples[-1][0]
        first_cut = total_duration / 3
        final_cut = total_duration * 2 / 3
        first_third = [p for t, p in samples if t <= first_cut]
        first_times = [t for t, p in samples if t <= first_cut]
        final_third = [p for t, p in samples if t >= final_cut]
        final_times = [t for t, p in samples if t >= final_cut]

        np_first = _normalized_power_from_stream(first_times, first_third)
        np_final = _normalized_power_from_stream(final_times, final_third)
        ratio = np_final / np_first if np_first else None

        conn.execute(
            "INSERT INTO durability (activity_id, np_first_third, np_final_third, retention_ratio) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(activity_id) DO UPDATE SET np_first_third=excluded.np_first_third, "
            "np_final_third=excluded.np_final_third, retention_ratio=excluded.retention_ratio",
            (activity_id, np_first, np_final, ratio),
        )
        conn.commit()
        n_computed += 1
        time.sleep(0.2)

    return n_computed


def durability_series(conn: sqlite3.Connection) -> list[dict]:
    """Cached durability results joined back to activity date/name, oldest first."""
    rows = conn.execute(
        """
        SELECT a.activity_id, date(a.start_local) AS date, a.activity_name, a.duration_s,
               d.np_first_third, d.np_final_third, d.retention_ratio
        FROM durability d
        JOIN activities a ON a.activity_id = d.activity_id
        ORDER BY a.start_local
        """
    ).fetchall()
    return [dict(r) for r in rows]


def best_power_curve(conn: sqlite3.Connection, start: date, end: date) -> list[dict]:
    """Best mean-maximal power at each stored duration within [start, end]."""
    bests = conn.execute(
        """
        SELECT pc.duration_s, MAX(pc.watts) AS watts
        FROM power_curve pc
        JOIN activities a ON a.activity_id = pc.activity_id
        WHERE date(a.start_local) BETWEEN ? AND ?
        GROUP BY pc.duration_s
        ORDER BY pc.duration_s
        """,
        (start.isoformat(), end.isoformat()),
    ).fetchall()

    result = []
    for b in bests:
        detail = conn.execute(
            """
            SELECT a.activity_id, date(a.start_local) AS date, a.activity_name
            FROM power_curve pc
            JOIN activities a ON a.activity_id = pc.activity_id
            WHERE pc.duration_s = ? AND pc.watts = ? AND date(a.start_local) BETWEEN ? AND ?
            LIMIT 1
            """,
            (b["duration_s"], b["watts"], start.isoformat(), end.isoformat()),
        ).fetchone()
        result.append(
            {
                "duration_s": b["duration_s"],
                "watts": b["watts"],
                "activity_id": detail["activity_id"] if detail else None,
                "date": detail["date"] if detail else None,
                "activity_name": detail["activity_name"] if detail else None,
            }
        )
    return result


def main() -> None:
    conn = connect()
    activities = load_activities(conn)

    calib = calibration_report(conn)
    print("=== Calibration: power-TSS vs Garmin activity_training_load ===")
    if calib["n"] < 3 or calib["slope"] is None:
        print(f"  n={calib['n']} -- not enough paired data to fit a relationship.")
    else:
        print(
            f"  n={calib['n']}  slope={calib['slope']:.3f}  intercept={calib['intercept']:.2f}  "
            f"R2={calib['r_squared']:.3f}  residual_std={calib['residual_std']:.2f}"
        )
        if calib["r_squared"] < 0.7:
            print(
                "  WEAK fit -- activity_training_load should NOT be treated as a common scale "
                "across power and non-power rides. Kept unmodified alongside TSS instead."
            )
        else:
            print("  Fit is reasonably tight -- see report for whether this is usable as a common scale.")

    daily = daily_load_series(activities)
    pmc = ctl_atl_tsb(daily)
    weekly = weekly_aggregates(activities)

    print("\n=== Last 12 weeks ===")
    header = f"{'week':<12}{'TSS':>8}{'hours':>8}{'km':>8}{'elev_m':>8}{'rides':>7}{'w/pwr':>7}{'w/o':>6}{'hr_share':>10}"
    print(header)
    for w in weekly[-12:]:
        flag = "  [HR-heavy, not comparable to power weeks]" if w["flagged"] else ""
        print(
            f"{w['week_start']:<12}{w['total_tss']:>8.0f}{w['hours']:>8.1f}{w['distance_km']:>8.0f}"
            f"{w['elevation_m']:>8.0f}{w['n_rides']:>7}{w['n_with_power']:>7}{w['n_without_power']:>6}"
            f"{w['hr_share'] * 100:>9.0f}%{flag}"
        )

    if pmc:
        last = pmc[-1]
        print(f"\n=== Current fitness (as of {last['date']}) ===")
        print(f"  CTL (42d fitness): {last['ctl']:.1f}")
        print(f"  ATL (7d fatigue):  {last['atl']:.1f}")
        print(f"  TSB (form):        {last['tsb']:.1f}")

    durability = durability_series(conn)
    print(f"\n=== Durability: NP final third vs first third, rides >2h (n={len(durability)}) ===")
    if not durability:
        print("  No cached rides yet -- run sync.py to populate (fetches the power stream per qualifying ride).")
    else:
        for d in durability:
            if d["retention_ratio"] is None:
                continue
            print(
                f"  {d['date']}  {d['activity_name'][:40]:<40}  "
                f"1st={d['np_first_third']:.0f}W  final={d['np_final_third']:.0f}W  "
                f"retention={d['retention_ratio'] * 100:.0f}%"
            )

    conn.close()


if __name__ == "__main__":
    main()
