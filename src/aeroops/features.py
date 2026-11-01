"""Construction des variables du modèle — uniquement des informations connues AVANT le départ.

Variables interdites (connues seulement après le vol) : dep_time, dep_delay, arr_*, air_time,
cancelled, delayed15. Les taux historiques (encodage de la cible) sont appris sur la période
d'entraînement uniquement, puis appliqués tels quels à la validation et au test.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .config import TEST_END, TEST_START, TRAIN_END, TRAIN_START, VALID_END, VALID_START

CAT_FEATURES = ["carrier", "origin", "dest"]
BASE_NUM_FEATURES = ["sched_hour", "weekday", "month", "distance", "plane_age", "congestion_origin_hour",
                     "temp", "humid", "wind_speed", "wind_gust", "precip", "visib", "pressure"]
ENCODED_KEYS = {
    "hist_rate_carrier_hour": ["carrier", "sched_hour"],
    "hist_rate_origin_hour": ["origin", "sched_hour"],
    "hist_rate_route": ["origin", "dest"],
    "hist_rate_carrier_month": ["carrier", "month"],
}
NUM_FEATURES = BASE_NUM_FEATURES + list(ENCODED_KEYS)
FORBIDDEN = {"dep_time", "dep_delay", "arr_delay", "air_time", "cancelled", "delayed15", "target"}
SMOOTHING = 50.0

BASE_QUERY = """
SELECT f.flight_id, f.date_key, f.carrier, f.origin, f.dest, f.sched_dep_local, f.sched_hour, f.distance,
       f.target, f.cancelled, f.delayed15, f.dep_delay, d.weekday, d.month, a.build_year,
       w.temp, w.humid, w.wind_speed, w.wind_gust, w.precip, w.visib, w.pressure
FROM fact_flight f
JOIN dim_date d ON d.date_key = f.date_key
LEFT JOIN dim_aircraft a ON a.tailnum = f.tailnum
LEFT JOIN fact_weather_hourly w ON w.origin = f.origin AND w.time_hour_utc = f.time_hour_utc
"""


def load_base(conn: sqlite3.Connection) -> pd.DataFrame:
    df = pd.read_sql_query(BASE_QUERY, conn)
    df["plane_age"] = 2013 - df["build_year"]
    # Rafale non déclarée : on retient la vitesse moyenne du vent (borne basse physique)
    df["wind_gust"] = df["wind_gust"].fillna(df["wind_speed"])
    # Charge programmée : nombre de départs prévus à la même origine, même jour, même heure
    df["congestion_origin_hour"] = df.groupby(["origin", "date_key", "sched_hour"])["flight_id"].transform("count")
    df["date"] = pd.to_datetime(df["date_key"])
    return df


def split_by_date(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    d = df["date"].dt.date
    return {
        "train": df[(d >= TRAIN_START) & (d <= TRAIN_END)].copy(),
        "valid": df[(d >= VALID_START) & (d <= VALID_END)].copy(),
        "test": df[(d >= TEST_START) & (d <= TEST_END)].copy(),
    }


@dataclass
class TargetEncoder:
    """Taux de perturbation historique lissé (m-estimate) appris sur l'entraînement seulement."""

    prior: float = 0.0
    tables: dict[str, dict[tuple, float]] = field(default_factory=dict)

    def fit(self, train: pd.DataFrame) -> "TargetEncoder":
        self.prior = float(train["target"].mean())
        for name, keys in ENCODED_KEYS.items():
            g = train.groupby(keys)["target"].agg(["sum", "count"])
            rate = (g["sum"] + SMOOTHING * self.prior) / (g["count"] + SMOOTHING)
            self.tables[name] = {(k if isinstance(k, tuple) else (k,)): float(v) for k, v in rate.items()}
        return self

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        for name, keys in ENCODED_KEYS.items():
            table = self.tables[name]
            out[name] = [table.get(tuple(row), self.prior) for row in out[keys].itertuples(index=False, name=None)]
        return out


def feature_frame(df: pd.DataFrame) -> pd.DataFrame:
    cols = CAT_FEATURES + NUM_FEATURES
    assert not (set(cols) & FORBIDDEN), "variable postérieure au départ dans les features"
    return df[cols]
