"""SQLite schema and connection helper for the Garmin data store."""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "garmin.db"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS activities (
    activity_id INTEGER PRIMARY KEY,
    activity_name TEXT,
    start_local TEXT NOT NULL,
    start_gmt TEXT,
    activity_type TEXT,
    duration_s REAL,
    distance_m REAL,
    elevation_gain REAL,
    avg_hr REAL,
    max_hr REAL,
    avg_power REAL,
    norm_power REAL,
    max_power REAL,
    max_20min_power REAL,
    avg_cadence REAL,
    calories REAL,
    activity_training_load REAL,
    aerobic_te REAL,
    anaerobic_te REAL,
    training_effect_label TEXT,
    hr_time_in_zone_1 REAL,
    hr_time_in_zone_2 REAL,
    hr_time_in_zone_3 REAL,
    hr_time_in_zone_4 REAL,
    hr_time_in_zone_5 REAL,
    power_time_in_zone_1 REAL,
    power_time_in_zone_2 REAL,
    power_time_in_zone_3 REAL,
    power_time_in_zone_4 REAL,
    power_time_in_zone_5 REAL,
    power_time_in_zone_6 REAL,
    power_time_in_zone_7 REAL,
    has_power BOOLEAN NOT NULL
);

CREATE TABLE IF NOT EXISTS power_curve (
    activity_id INTEGER NOT NULL REFERENCES activities(activity_id),
    duration_s INTEGER NOT NULL,
    watts REAL NOT NULL,
    PRIMARY KEY (activity_id, duration_s)
);

CREATE TABLE IF NOT EXISTS training_status (
    date TEXT PRIMARY KEY,
    vo2max_generic REAL,
    vo2max_cycling REAL,
    training_status INTEGER,
    training_status_label TEXT,
    fitness_trend INTEGER,
    acwr REAL,
    load_balance_aerobic_low REAL,
    load_balance_aerobic_high REAL,
    load_balance_anaerobic REAL,
    load_balance_feedback TEXT
);

CREATE TABLE IF NOT EXISTS ftp_history (
    date TEXT PRIMARY KEY,
    ftp REAL
);

CREATE TABLE IF NOT EXISTS durability (
    activity_id INTEGER PRIMARY KEY REFERENCES activities(activity_id),
    np_first_third REAL,
    np_final_third REAL,
    retention_ratio REAL
);
"""


def get_db(path: Path = DB_PATH) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_SQL)
    return conn
