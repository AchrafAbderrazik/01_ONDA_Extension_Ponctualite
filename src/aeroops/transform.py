"""Transformation : typage, nettoyage selon les règles qualité et construction du schéma en étoile."""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from .config import DELAY_THRESHOLD_MIN
from .validate import FLIGHT_KEY, MAX_PLAUSIBLE_WIND_MPH, NUMERIC_COLUMNS

log = logging.getLogger(__name__)

MONTHS_FR = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre",
             "octobre", "novembre", "décembre"]
WEEKDAYS_FR = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


def _to_numeric(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    df = df.copy()
    for c in cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def clean_flights(flights: pd.DataFrame, airlines: pd.DataFrame) -> pd.DataFrame:
    """Applique les exclusions (R03, R04, R05, R08, R10) et dérive les indicateurs de ponctualité."""
    f = _to_numeric(flights, NUMERIC_COLUMNS["flights"] + ["rownames"])
    n0 = len(f)
    keys_ok = f[["year", "month", "day", "carrier", "flight", "origin", "dest", "sched_dep_time"]].notna().all(axis=1)
    hh, mm = f["sched_dep_time"] // 100, f["sched_dep_time"] % 100
    sched_ok = (mm < 60) & (hh <= 24) & (f["sched_dep_time"] >= 0)
    dist_ok = f["distance"].isna() | (f["distance"] > 0)
    carrier_ok = f["carrier"].isin(airlines["carrier"])
    f = f[keys_ok & sched_ok & dist_ok & carrier_ok]
    f = f.drop_duplicates(subset=FLIGHT_KEY, keep="first")
    log.info("Vols conserves : %d / %d (exclus : %d)", len(f), n0, n0 - len(f))

    hh = (f["sched_dep_time"] // 100).astype(int)
    mm = (f["sched_dep_time"] % 100).astype(int)
    base = pd.to_datetime(dict(year=f["year"].astype(int), month=f["month"].astype(int), day=f["day"].astype(int)))
    sched = base + pd.to_timedelta(hh * 60 + mm, unit="m")  # 2400 -> minuit du jour suivant

    out = pd.DataFrame({
        "flight_id": f["rownames"].astype(int).to_numpy(),
        "date_key": base.dt.strftime("%Y-%m-%d").to_numpy(),
        "carrier": f["carrier"].to_numpy(),
        "flight_no": f["flight"].astype(int).to_numpy(),
        "tailnum": f["tailnum"].to_numpy(),
        "origin": f["origin"].to_numpy(),
        "dest": f["dest"].to_numpy(),
        "sched_dep_local": sched.dt.strftime("%Y-%m-%d %H:%M").to_numpy(),
        "sched_hour": hh.clip(upper=23).to_numpy(),
        "sched_minute": mm.to_numpy(),
        "dep_time": f["dep_time"].replace(2400, 0).to_numpy(),
        "dep_delay": f["dep_delay"].to_numpy(),
        "arr_delay": f["arr_delay"].to_numpy(),
        "air_time": f["air_time"].to_numpy(),
        "distance": f["distance"].to_numpy(),
        "time_hour_utc": f["time_hour"].to_numpy(),
    })
    out["cancelled"] = out["dep_time"].isna().astype(int)
    out["delayed15"] = (out["dep_delay"] >= DELAY_THRESHOLD_MIN).astype(int)
    out["target"] = ((out["cancelled"] == 1) | (out["delayed15"] == 1)).astype(int)
    return out.sort_values(["sched_dep_local", "carrier", "flight_no"]).reset_index(drop=True)


def clean_weather(weather: pd.DataFrame) -> pd.DataFrame:
    w = _to_numeric(weather, NUMERIC_COLUMNS["weather"])
    w = w.drop_duplicates(subset=["origin", "time_hour"], keep="first")
    w.loc[w["wind_speed"] > MAX_PLAUSIBLE_WIND_MPH, "wind_speed"] = np.nan
    return pd.DataFrame({
        "origin": w["origin"], "time_hour_utc": w["time_hour"],
        "date_key": pd.to_datetime(dict(year=w["year"].astype(int), month=w["month"].astype(int),
                                        day=w["day"].astype(int))).dt.strftime("%Y-%m-%d"),
        "local_hour": w["hour"].astype(int),
        "temp": w["temp"], "dewp": w["dewp"], "humid": w["humid"], "wind_dir": w["wind_dir"],
        "wind_speed": w["wind_speed"], "wind_gust": w["wind_gust"], "precip": w["precip"],
        "pressure": w["pressure"], "visib": w["visib"],
    }).reset_index(drop=True)


def build_dimensions(f: pd.DataFrame, airlines: pd.DataFrame, airports: pd.DataFrame,
                     planes: pd.DataFrame) -> dict[str, pd.DataFrame]:
    ap = _to_numeric(airports, ["lat", "lon", "alt", "tz"])
    dim_airport = ap[["faa", "name", "lat", "lon", "alt", "tz", "tzone"]].drop_duplicates("faa").copy()
    dim_airport["is_unknown"] = 0
    missing = sorted(set(f["origin"]).union(f["dest"]) - set(dim_airport["faa"]))
    if missing:
        dim_airport = pd.concat([dim_airport, pd.DataFrame({
            "faa": missing, "name": ["Inconnu (absent du référentiel)"] * len(missing),
            "lat": np.nan, "lon": np.nan, "alt": np.nan, "tz": np.nan, "tzone": None, "is_unknown": 1})],
            ignore_index=True)

    dim_carrier = airlines[["carrier", "name"]].drop_duplicates("carrier").reset_index(drop=True)

    pl = _to_numeric(planes, ["year", "engines", "seats"])
    pl.loc[(pl["year"] < 1950) | (pl["year"] > 2013), "year"] = np.nan
    dim_aircraft = pl[["tailnum", "year", "type", "manufacturer", "model", "engines", "seats", "engine"]].copy()
    dim_aircraft = dim_aircraft.rename(columns={"year": "build_year"}).drop_duplicates("tailnum")
    dim_aircraft["is_unknown"] = 0
    unknown_tails = sorted(set(f["tailnum"].dropna()) - set(dim_aircraft["tailnum"]))
    if unknown_tails:
        dim_aircraft = pd.concat([dim_aircraft, pd.DataFrame({"tailnum": unknown_tails, "is_unknown": 1})],
                                 ignore_index=True)

    dates = pd.to_datetime(pd.Series(sorted(f["date_key"].unique())))
    dim_date = pd.DataFrame({
        "date_key": dates.dt.strftime("%Y-%m-%d"), "year": dates.dt.year, "month": dates.dt.month,
        "day": dates.dt.day, "weekday": dates.dt.dayofweek, "week": dates.dt.isocalendar().week.astype(int).to_numpy(),
        "is_weekend": (dates.dt.dayofweek >= 5).astype(int),
        "month_name_fr": [MONTHS_FR[m - 1] for m in dates.dt.month],
        "weekday_name_fr": [WEEKDAYS_FR[d] for d in dates.dt.dayofweek],
    })
    return {"dim_airport": dim_airport.reset_index(drop=True), "dim_carrier": dim_carrier,
            "dim_aircraft": dim_aircraft.reset_index(drop=True), "dim_date": dim_date}


def transform(tables: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Retourne les 6 tables du schéma en étoile prêtes à charger."""
    flights = clean_flights(tables["flights"], tables["airlines"])
    weather = clean_weather(tables["weather"])
    wkeys = set(zip(weather["origin"], weather["time_hour_utc"]))
    flights["weather_found"] = [int((o, t) in wkeys) for o, t in zip(flights["origin"], flights["time_hour_utc"])]
    dims = build_dimensions(flights, tables["airlines"], tables["airports"], tables["planes"])
    return {**dims, "fact_weather_hourly": weather, "fact_flight": flights}
