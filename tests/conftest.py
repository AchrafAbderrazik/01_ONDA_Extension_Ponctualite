"""Jeu de données synthétique au format des CSV sources, pour des tests rapides et isolés."""

from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from aeroops.config import Settings

ORIGINS = ["EWR", "JFK", "LGA"]
DESTS = ["ORD", "ATL", "SJU"]          # SJU volontairement absent du référentiel airports (règle R11)
TAILS = ["N100AA", "N200BB", "N999XX"]  # N999XX volontairement absent du référentiel planes (règle R12)


def make_raw(dirpath: Path, seed: int = 0) -> dict[str, int]:
    """Écrit les 5 CSV synthétiques et retourne les comptes attendus pour certaines règles."""
    rng = np.random.default_rng(seed)
    days = pd.date_range("2013-01-01", "2013-12-31", freq="D")
    rows, wrows, rid, wid = [], [], 1, 1
    for d in days:
        for origin in ORIGINS:
            for hour in range(6, 23):
                temp, visib = rng.normal(55, 15), (0.5 if rng.random() < 0.05 else 10.0)
                utc = (d + pd.Timedelta(hours=hour + 5)).strftime("%Y-%m-%dT%H:%M:%SZ")
                wrows.append([wid, origin, d.year, d.month, d.day, hour, round(temp, 1), 40.0, 60.0, 200, 8.0, "",
                              0.0 if visib > 1 else 0.2, 1015.0, visib, utc])
                wid += 1
            for hour in rng.choice(range(6, 23), size=2, replace=False):
                sched = int(hour) * 100 + 15
                late_prob = 0.15 + 0.03 * (hour - 6)
                cancelled = rng.random() < 0.02
                delay = None if cancelled else int(rng.integers(20, 120) if rng.random() < late_prob else rng.integers(-10, 10))
                dep = None if cancelled else (sched + (delay or 0)) % 2400
                rows.append([rid, d.year, d.month, d.day, dep, sched, delay, None, None, None,
                             rng.choice(["UA", "AA"]), int(rng.integers(100, 999)), rng.choice(TAILS),
                             origin, rng.choice(DESTS), None if cancelled else 120, 700, int(hour), 15,
                             (d + pd.Timedelta(hours=int(hour) + 5)).strftime("%Y-%m-%dT%H:%M:%SZ")])
                rid += 1
    # cas particuliers : départ réel 2400 et vent aberrant
    rows[0][4] = 2400
    wrows[1][10] = 1048.0
    fcols = ["rownames", "year", "month", "day", "dep_time", "sched_dep_time", "dep_delay", "arr_time", "sched_arr_time",
             "arr_delay", "carrier", "flight", "tailnum", "origin", "dest", "air_time", "distance", "hour", "minute", "time_hour"]
    flights = pd.DataFrame(rows, columns=fcols)
    wcols = ["rownames", "origin", "year", "month", "day", "hour", "temp", "dewp", "humid", "wind_dir", "wind_speed",
             "wind_gust", "precip", "pressure", "visib", "time_hour"]
    weather = pd.DataFrame(wrows, columns=wcols)
    airlines = pd.DataFrame({"rownames": [1, 2], "carrier": ["AA", "UA"], "name": ["American", "United"]})
    airports = pd.DataFrame({"rownames": range(1, 6), "faa": ORIGINS + ["ORD", "ATL"], "name": ["a"] * 5,
                             "lat": [40.0] * 5, "lon": [-74.0] * 5, "alt": [10] * 5, "tz": [-5] * 5, "dst": ["A"] * 5,
                             "tzone": ["America/New_York"] * 5})
    planes = pd.DataFrame({"rownames": [1, 2], "tailnum": ["N100AA", "N200BB"], "year": [2004, 1998],
                           "type": ["t", "t"], "manufacturer": ["m", "m"], "model": ["x", "y"], "engines": [2, 2],
                           "seats": [150, 180], "speed": ["", ""], "engine": ["Turbo-fan", "Turbo-fan"]})
    dirpath.mkdir(parents=True, exist_ok=True)
    for name, df in {"flights": flights, "weather": weather, "airlines": airlines, "airports": airports, "planes": planes}.items():
        df.to_csv(dirpath / f"{name}.csv", index=False)
    return {"flights": len(flights), "sju": int((flights["dest"] == "SJU").sum()),
            "unknown_tail": int((flights["tailnum"] == "N999XX").sum()),
            "cancelled": int(flights["dep_time"].isna().sum()), "dep2400": 1, "wind_outlier": 1}


@pytest.fixture(scope="session")
def synthetic_project(tmp_path_factory):
    """Projet isolé complet : CSV synthétiques -> ETL -> modèle -> anomalies (exécuté une fois)."""
    from aeroops.anomalies import run as run_anomalies
    from aeroops.etl import run_etl
    from aeroops.train import train_and_evaluate

    base = tmp_path_factory.mktemp("aeroops")
    settings = Settings.for_directory(base)
    expected = make_raw(settings.raw_dir)
    etl_summary = run_etl(settings, download_missing=False, verify_checksums=False)
    metrics = train_and_evaluate(settings, perm_sample=300)
    anomalies = run_anomalies(settings)
    return {"settings": settings, "expected": expected, "etl": etl_summary, "metrics": metrics, "anomalies": anomalies}


@pytest.fixture()
def fresh_dir(tmp_path):
    yield tmp_path
    shutil.rmtree(tmp_path, ignore_errors=True)
