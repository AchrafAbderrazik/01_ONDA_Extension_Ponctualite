"""Tests de l'ETL : règles de qualité, transformations, chargement idempotent, intégrité."""

import sqlite3

import pandas as pd

from aeroops.config import Settings
from aeroops.etl import run_etl
from aeroops.extract import read_raw_tables
from aeroops.load import connect, table_counts
from aeroops.transform import clean_flights, transform
from aeroops.validate import blocking, run_rules
from conftest import make_raw


def _rule(results, rule_id, table="flights"):
    return next(r for r in results if r.rule_id == rule_id and r.table == table)


def test_rules_detect_known_issues(tmp_path):
    expected = make_raw(tmp_path)
    results = run_rules(read_raw_tables(tmp_path))
    assert _rule(results, "R11").violations == expected["sju"]
    assert _rule(results, "R12").violations == expected["unknown_tail"]
    assert _rule(results, "R07").violations == expected["cancelled"]
    assert _rule(results, "R06").violations == expected["dep2400"]
    assert _rule(results, "R15", "weather").violations == expected["wind_outlier"]
    assert not blocking(results)


def test_missing_column_blocks_pipeline(tmp_path):
    make_raw(tmp_path)
    tables = read_raw_tables(tmp_path)
    tables["flights"] = tables["flights"].drop(columns=["carrier"])
    results = run_rules(tables)
    assert blocking(results), "une colonne obligatoire absente doit bloquer le chargement"


def test_flags_and_scheduled_datetime():
    flights = pd.DataFrame({
        "rownames": ["1", "2", "3"], "year": ["2013"] * 3, "month": ["1"] * 3, "day": ["1"] * 3,
        "dep_time": ["517", None, "2400"], "sched_dep_time": ["515", "600", "2359"], "dep_delay": ["2", None, "1"],
        "arr_delay": ["11", None, "0"], "carrier": ["UA"] * 3, "flight": ["1", "2", "3"], "tailnum": ["N1", None, "N3"],
        "origin": ["EWR"] * 3, "dest": ["ORD"] * 3, "air_time": ["100", None, "90"], "distance": ["700"] * 3,
        "hour": ["5", "6", "23"], "minute": ["15", "0", "59"], "time_hour": ["t1", "t2", "t3"]})
    out = clean_flights(flights, pd.DataFrame({"carrier": ["UA"], "name": ["United"]})).set_index("flight_id")
    assert out.loc[1, "sched_dep_local"] == "2013-01-01 05:15"
    assert out.loc[2, "cancelled"] == 1 and out.loc[2, "target"] == 1
    assert out.loc[1, "delayed15"] == 0 and out.loc[1, "target"] == 0
    assert out.loc[3, "dep_time"] == 0  # 2400 normalisé


def test_unknown_members_added(tmp_path):
    make_raw(tmp_path)
    star = transform(read_raw_tables(tmp_path))
    ap = star["dim_airport"].set_index("faa")
    assert ap.loc["SJU", "is_unknown"] == 1
    ac = star["dim_aircraft"].set_index("tailnum")
    assert ac.loc["N999XX", "is_unknown"] == 1


def test_etl_is_idempotent_and_consistent(tmp_path):
    settings = Settings.for_directory(tmp_path)
    make_raw(settings.raw_dir)
    run_etl(settings, download_missing=False, verify_checksums=False)
    conn = connect(settings.db_path)
    first = table_counts(conn)
    conn.close()
    run_etl(settings, download_missing=False, verify_checksums=False)
    conn = connect(settings.db_path)
    assert table_counts(conn) == first
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    runs = conn.execute("SELECT COUNT(*) FROM etl_runs WHERE status='SUCCESS'").fetchone()[0]
    assert runs == 2
    conn.close()


def test_dq_results_persisted(synthetic_project):
    s = synthetic_project["settings"]
    conn = sqlite3.connect(s.db_path)
    run_id = synthetic_project["etl"]["run_id"]
    n = conn.execute("SELECT COUNT(*) FROM dq_results WHERE run_id=?", (run_id,)).fetchone()[0]
    assert n == synthetic_project["etl"]["rules"]
    assert (s.reports_dir / "data_quality_report.md").exists()
    conn.close()


def test_kpi_view_matches_manual_computation(synthetic_project):
    conn = sqlite3.connect(synthetic_project["settings"].db_path)
    day = "2013-03-15"
    view = conn.execute("SELECT SUM(flights), AVG(otp15) FROM v_kpi_daily WHERE date_key=? AND origin='JFK'", (day,)).fetchone()
    df = pd.read_sql_query("SELECT * FROM fact_flight WHERE date_key=? AND origin='JFK'", conn, params=(day,))
    kept = df[df["cancelled"] == 0]
    manual = (kept["dep_delay"] < 15).mean() if len(kept) else None
    assert view[0] == len(df)
    if manual is not None:
        assert abs(view[1] - manual) < 1e-9
    conn.close()
