"""Incremental, idempotent sync of Garmin activities + training status into SQLite."""

import argparse
import os
import sqlite3
import time
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv
from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)

from db import get_db
from metrics import compute_durability

TOKEN_STORE = Path.home() / ".garminconnect"
DEFAULT_LOOKBACK_DAYS = 14  # used only when the db is empty and --backfill wasn't given

POWER_CURVE_DURATIONS = [1, 2, 5, 10, 20, 30, 60, 120, 300, 600, 1200, 1800, 3600]


def safe_get(d, *path, default="N/A"):
    for key in path:
        if isinstance(d, dict):
            d = d.get(key)
        elif isinstance(d, list) and isinstance(key, int) and -len(d) <= key < len(d):
            d = d[key]
        else:
            return default
        if d is None:
            return default
    return d


def prompt_mfa() -> str:
    return input("Enter Garmin MFA code: ")


def login() -> Garmin:
    load_dotenv()
    email = os.getenv("GARMIN_EMAIL")
    password = os.getenv("GARMIN_PASSWORD")
    if not email or not password:
        raise SystemExit("GARMIN_EMAIL / GARMIN_PASSWORD not set (check .env)")

    garmin = Garmin(email, password, prompt_mfa=prompt_mfa)
    try:
        garmin.login(str(TOKEN_STORE))
    except (
        GarminConnectAuthenticationError,
        GarminConnectConnectionError,
        GarminConnectTooManyRequestsError,
    ) as e:
        raise SystemExit(f"Garmin login failed: {e}") from e
    return garmin


def determine_start_date(conn: sqlite3.Connection, backfill_days: int | None) -> date:
    if backfill_days is not None:
        return date.today() - timedelta(days=backfill_days)
    row = conn.execute("SELECT MAX(start_local) FROM activities").fetchone()
    if row and row[0]:
        return date.fromisoformat(row[0][:10])
    return date.today() - timedelta(days=DEFAULT_LOOKBACK_DAYS)


def upsert_activity(conn: sqlite3.Connection, a: dict) -> None:
    activity_id = safe_get(a, "activityId", default=None)
    if activity_id is None:
        return

    avg_power = safe_get(a, "avgPower", default=None)
    fields = {
        "activity_id": activity_id,
        "activity_name": safe_get(a, "activityName", default=None),
        "start_local": safe_get(a, "startTimeLocal", default=None),
        "start_gmt": safe_get(a, "startTimeGMT", default=None),
        "activity_type": safe_get(a, "activityType", "typeKey", default=None),
        "duration_s": safe_get(a, "duration", default=None),
        "distance_m": safe_get(a, "distance", default=None),
        "elevation_gain": safe_get(a, "elevationGain", default=None),
        "avg_hr": safe_get(a, "averageHR", default=None),
        "max_hr": safe_get(a, "maxHR", default=None),
        "avg_power": avg_power,
        "norm_power": safe_get(a, "normPower", default=None),
        "max_power": safe_get(a, "maxPower", default=None),
        "max_20min_power": safe_get(a, "max20MinPower", default=None),
        "avg_cadence": safe_get(a, "averageBikingCadenceInRevPerMinute", default=None),
        "calories": safe_get(a, "calories", default=None),
        "activity_training_load": safe_get(a, "activityTrainingLoad", default=None),
        "aerobic_te": safe_get(a, "aerobicTrainingEffect", default=None),
        "anaerobic_te": safe_get(a, "anaerobicTrainingEffect", default=None),
        "training_effect_label": safe_get(a, "trainingEffectLabel", default=None),
        "has_power": 1 if avg_power is not None else 0,
    }
    for i in range(1, 6):
        fields[f"hr_time_in_zone_{i}"] = safe_get(a, f"hrTimeInZone_{i}", default=None)
    for i in range(1, 8):
        fields[f"power_time_in_zone_{i}"] = safe_get(a, f"powerTimeInZone_{i}", default=None)

    columns = ", ".join(fields.keys())
    placeholders = ", ".join(f":{k}" for k in fields.keys())
    updates = ", ".join(f"{k}=excluded.{k}" for k in fields if k != "activity_id")
    conn.execute(
        f"INSERT INTO activities ({columns}) VALUES ({placeholders}) "
        f"ON CONFLICT(activity_id) DO UPDATE SET {updates}",
        fields,
    )

    conn.execute("DELETE FROM power_curve WHERE activity_id = ?", (activity_id,))
    curve_rows = []
    for d in POWER_CURVE_DURATIONS:
        watts = safe_get(a, f"maxAvgPower_{d}", default=None)
        if watts is not None:
            curve_rows.append((activity_id, d, watts))
    if curve_rows:
        conn.executemany(
            "INSERT INTO power_curve (activity_id, duration_s, watts) VALUES (?, ?, ?)",
            curve_rows,
        )


def _primary_device_entry(mapping) -> dict:
    if not isinstance(mapping, dict) or not mapping:
        return {}
    for v in mapping.values():
        if isinstance(v, dict) and v.get("primaryTrainingDevice"):
            return v
    return next(iter(mapping.values()), {})


def upsert_training_status(conn: sqlite3.Connection, day: date, ts: dict) -> None:
    if not ts:
        return

    generic = safe_get(ts, "mostRecentVO2Max", "generic", default=None) or {}
    cycling = safe_get(ts, "mostRecentVO2Max", "cycling", default=None) or {}
    status_map = safe_get(ts, "mostRecentTrainingStatus", "latestTrainingStatusData", default=None)
    device_status = _primary_device_entry(status_map)
    load_map = safe_get(ts, "mostRecentTrainingLoadBalance", "metricsTrainingLoadBalanceDTOMap", default=None)
    device_load = _primary_device_entry(load_map)
    acute = device_status.get("acuteTrainingLoadDTO") or {}

    fields = {
        "date": day.isoformat(),
        "vo2max_generic": generic.get("vo2MaxValue"),
        "vo2max_cycling": cycling.get("vo2MaxValue"),
        "training_status": device_status.get("trainingStatus"),
        "training_status_label": device_status.get("trainingStatusFeedbackPhrase"),
        "fitness_trend": device_status.get("fitnessTrend"),
        "acwr": acute.get("dailyAcuteChronicWorkloadRatio"),
        "load_balance_aerobic_low": device_load.get("monthlyLoadAerobicLow"),
        "load_balance_aerobic_high": device_load.get("monthlyLoadAerobicHigh"),
        "load_balance_anaerobic": device_load.get("monthlyLoadAnaerobic"),
        "load_balance_feedback": device_load.get("trainingBalanceFeedbackPhrase"),
    }
    if all(v is None for k, v in fields.items() if k != "date"):
        return

    columns = ", ".join(fields.keys())
    placeholders = ", ".join(f":{k}" for k in fields.keys())
    updates = ", ".join(f"{k}=excluded.{k}" for k in fields if k != "date")
    conn.execute(
        f"INSERT INTO training_status ({columns}) VALUES ({placeholders}) "
        f"ON CONFLICT(date) DO UPDATE SET {updates}",
        fields,
    )


def upsert_ftp(conn: sqlite3.Connection, garmin: Garmin) -> None:
    ftp_data = garmin.get_cycling_ftp()
    if isinstance(ftp_data, list):
        ftp_data = ftp_data[0] if ftp_data else {}
    ftp = safe_get(ftp_data, "functionalThresholdPower", default=None)
    cal_date = safe_get(ftp_data, "calendarDate", default=None)
    if ftp is None or cal_date is None:
        return
    conn.execute(
        "INSERT INTO ftp_history (date, ftp) VALUES (?, ?) "
        "ON CONFLICT(date) DO UPDATE SET ftp=excluded.ftp",
        (cal_date[:10], ftp),
    )


def sync_activities(conn: sqlite3.Connection, garmin: Garmin, start: date, end: date) -> int:
    activities = garmin.get_activities_by_date(start.isoformat(), end.isoformat())
    for a in activities:
        upsert_activity(conn, a)
    conn.commit()
    return len(activities)


def sync_training_status(conn: sqlite3.Connection, garmin: Garmin, start: date, end: date) -> int:
    count = 0
    d = start
    while d <= end:
        for attempt in range(2):
            try:
                ts = garmin.get_training_status(d.isoformat())
                upsert_training_status(conn, d, ts)
                count += 1
                break
            except GarminConnectTooManyRequestsError:
                if attempt == 0:
                    time.sleep(5)
                    continue
                print(f"  WARNING: rate-limited fetching training_status for {d.isoformat()}, skipping")
            except GarminConnectConnectionError as e:
                print(f"  WARNING: connection error fetching training_status for {d.isoformat()}: {e}, skipping")
                break
        time.sleep(0.2)
        d += timedelta(days=1)
    conn.commit()
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync Garmin activities + training status into SQLite.")
    parser.add_argument("--backfill", type=int, metavar="N", help="Fetch the last N days regardless of what's already stored.")
    args = parser.parse_args()

    garmin = login()
    conn = get_db()

    today = date.today()
    start = determine_start_date(conn, args.backfill)

    print(f"Syncing activities from {start.isoformat()} to {today.isoformat()}...")
    n_activities = sync_activities(conn, garmin, start, today)
    print(f"  {n_activities} activities upserted.")

    print(f"Syncing training status from {start.isoformat()} to {today.isoformat()}...")
    n_days = sync_training_status(conn, garmin, start, today)
    print(f"  {n_days} days processed.")

    print("Syncing FTP...")
    upsert_ftp(conn, garmin)
    conn.commit()

    print("Computing durability (NP first/final third) for newly-qualifying rides >2h...")
    n_durability = compute_durability(conn, garmin)
    print(f"  {n_durability} rides newly computed.")

    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()
