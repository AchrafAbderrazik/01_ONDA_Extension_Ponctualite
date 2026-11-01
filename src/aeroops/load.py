"""Chargement transactionnel et idempotent dans l'entrepôt SQLite (schéma en étoile)."""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

DDL = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS dim_airport (
    faa TEXT PRIMARY KEY, name TEXT NOT NULL, lat REAL, lon REAL, alt REAL, tz REAL, tzone TEXT,
    is_unknown INTEGER NOT NULL DEFAULT 0 CHECK (is_unknown IN (0, 1)));
CREATE TABLE IF NOT EXISTS dim_carrier (carrier TEXT PRIMARY KEY, name TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS dim_aircraft (
    tailnum TEXT PRIMARY KEY, build_year INTEGER, type TEXT, manufacturer TEXT, model TEXT,
    engines INTEGER, seats INTEGER, engine TEXT, is_unknown INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS dim_date (
    date_key TEXT PRIMARY KEY, year INTEGER, month INTEGER, day INTEGER, weekday INTEGER, week INTEGER,
    is_weekend INTEGER, month_name_fr TEXT, weekday_name_fr TEXT);
CREATE TABLE IF NOT EXISTS fact_weather_hourly (
    origin TEXT NOT NULL REFERENCES dim_airport(faa), time_hour_utc TEXT NOT NULL, date_key TEXT, local_hour INTEGER,
    temp REAL, dewp REAL, humid REAL, wind_dir REAL, wind_speed REAL, wind_gust REAL, precip REAL,
    pressure REAL, visib REAL, PRIMARY KEY (origin, time_hour_utc));
CREATE TABLE IF NOT EXISTS fact_flight (
    flight_id INTEGER PRIMARY KEY, date_key TEXT NOT NULL REFERENCES dim_date(date_key),
    carrier TEXT NOT NULL REFERENCES dim_carrier(carrier), flight_no INTEGER NOT NULL,
    tailnum TEXT REFERENCES dim_aircraft(tailnum), origin TEXT NOT NULL REFERENCES dim_airport(faa),
    dest TEXT NOT NULL REFERENCES dim_airport(faa), sched_dep_local TEXT NOT NULL, sched_hour INTEGER NOT NULL,
    sched_minute INTEGER NOT NULL, dep_time REAL, dep_delay REAL, arr_delay REAL, air_time REAL, distance REAL,
    time_hour_utc TEXT, cancelled INTEGER NOT NULL CHECK (cancelled IN (0, 1)),
    delayed15 INTEGER NOT NULL CHECK (delayed15 IN (0, 1)), target INTEGER NOT NULL CHECK (target IN (0, 1)),
    weather_found INTEGER NOT NULL DEFAULT 0,
    UNIQUE (date_key, carrier, flight_no, origin, sched_dep_local));
CREATE INDEX IF NOT EXISTS ix_flight_date ON fact_flight(date_key);
CREATE INDEX IF NOT EXISTS ix_flight_origin_date ON fact_flight(origin, date_key);
CREATE INDEX IF NOT EXISTS ix_flight_carrier ON fact_flight(carrier);
CREATE TABLE IF NOT EXISTS etl_runs (
    run_id TEXT PRIMARY KEY, started_at TEXT NOT NULL, finished_at TEXT, status TEXT NOT NULL,
    rows_flight INTEGER, rows_weather INTEGER, source_fingerprint TEXT, message TEXT);
CREATE TABLE IF NOT EXISTS dq_results (
    run_id TEXT NOT NULL REFERENCES etl_runs(run_id), rule_id TEXT NOT NULL, tbl TEXT NOT NULL,
    description TEXT, severity TEXT, checked INTEGER, violations INTEGER, action TEXT,
    PRIMARY KEY (run_id, rule_id, tbl, description));
CREATE TABLE IF NOT EXISTS predictions (
    flight_id INTEGER PRIMARY KEY REFERENCES fact_flight(flight_id), split TEXT NOT NULL,
    proba REAL NOT NULL CHECK (proba >= 0 AND proba <= 1), risk_level TEXT NOT NULL, model_version TEXT NOT NULL,
    factors TEXT);
CREATE TABLE IF NOT EXISTS anomalies (
    origin TEXT NOT NULL, date_key TEXT NOT NULL, flights INTEGER, disruption_rate REAL, baseline REAL,
    robust_z REAL, direction TEXT, max_precip REAL, min_visib REAL, max_gust REAL, likely_cause TEXT,
    PRIMARY KEY (origin, date_key));
DROP VIEW IF EXISTS v_kpi_daily;
CREATE VIEW v_kpi_daily AS
SELECT origin, date_key, COUNT(*) AS flights, SUM(cancelled) AS cancelled,
       AVG(CASE WHEN cancelled = 0 THEN CASE WHEN dep_delay < 15 THEN 1.0 ELSE 0.0 END END) AS otp15,
       AVG(CASE WHEN cancelled = 0 THEN dep_delay END) AS avg_dep_delay,
       AVG(target) AS disruption_rate
FROM fact_flight GROUP BY origin, date_key;
"""

#: Ordre de chargement (dimensions avant faits) et de purge (inverse).
LOAD_ORDER = ["dim_airport", "dim_carrier", "dim_aircraft", "dim_date", "fact_weather_hourly", "fact_flight"]


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(DDL)


def _records(df: pd.DataFrame) -> list[tuple]:
    clean = df.astype(object).where(pd.notna(df), None)
    out = []
    for row in clean.itertuples(index=False, name=None):
        out.append(tuple(v.item() if isinstance(v, np.generic) else v for v in row))
    return out


def insert_df(conn: sqlite3.Connection, table: str, df: pd.DataFrame) -> int:
    cols = list(df.columns)
    sql = f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})"
    rows = _records(df)
    conn.executemany(sql, rows)
    return len(rows)


def load_star_schema(conn: sqlite3.Connection, tables: dict[str, pd.DataFrame]) -> dict[str, int]:
    """Rafraîchissement complet dans UNE transaction : purge puis insertion (idempotent)."""
    counts: dict[str, int] = {}
    with conn:  # commit si tout réussit, rollback sinon
        conn.execute("DELETE FROM predictions")
        conn.execute("DELETE FROM anomalies")
        for t in reversed(LOAD_ORDER):
            conn.execute(f"DELETE FROM {t}")
        for t in LOAD_ORDER:
            counts[t] = insert_df(conn, t, tables[t])
            log.info("Charge %s : %d lignes", t, counts[t])
        violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise RuntimeError(f"Violations de clés étrangères : {violations[:5]}")
    return counts


def table_counts(conn: sqlite3.Connection) -> dict[str, int]:
    return {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in LOAD_ORDER}
