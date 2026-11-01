"""Détection des journées de perturbation anormale par aéroport (non supervisée).

Indicateur : taux de perturbation journalier (retard ≥ 15 min ou annulation). Référence :
médiane des 28 jours PRÉCÉDENTS (fenêtre glissante, aucune information future) ; écart
mesuré par un z-score robuste (médiane / MAD). Une journée est signalée si z ≥ 3. Chaque
alerte est accompagnée d'un résumé météo et d'une cause probable fondée sur des règles.

Usage : ``python -m aeroops.anomalies``
"""

from __future__ import annotations

import argparse
import json
import logging

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from .config import Settings  # noqa: E402
from .load import connect  # noqa: E402
from .logging_utils import setup_logging  # noqa: E402

log = logging.getLogger(__name__)
WINDOW, MIN_PERIODS, Z_THRESHOLD = 28, 14, 3.0
ADVERSE = {"min_visib": 2.0, "max_precip": 0.10, "max_gust": 35.0}


def robust_z(series: pd.Series, window: int = WINDOW, min_periods: int = MIN_PERIODS) -> tuple[pd.Series, pd.Series]:
    """z-score robuste de chaque point par rapport aux ``window`` points précédents."""
    prev = series.shift(1)
    med = prev.rolling(window, min_periods=min_periods).median()
    mad = (prev - med).abs().rolling(window, min_periods=min_periods).median()
    scale = 1.4826 * mad
    scale = scale.where(scale > 1e-6, np.nan)
    return (series - med) / scale, med


def daily_frame(conn) -> pd.DataFrame:
    kpi = pd.read_sql_query("SELECT origin, date_key, flights, disruption_rate FROM v_kpi_daily", conn)
    wx = pd.read_sql_query(
        "SELECT origin, date_key, MAX(precip) AS max_precip, MIN(visib) AS min_visib, "
        "MAX(COALESCE(wind_gust, wind_speed)) AS max_gust FROM fact_weather_hourly GROUP BY origin, date_key", conn)
    return kpi.merge(wx, on=["origin", "date_key"], how="left").sort_values(["origin", "date_key"])


def is_adverse(row) -> bool:
    return bool((row["min_visib"] is not None and row["min_visib"] < ADVERSE["min_visib"])
                or (row["max_precip"] is not None and row["max_precip"] >= ADVERSE["max_precip"])
                or (row["max_gust"] is not None and row["max_gust"] >= ADVERSE["max_gust"]))


def likely_cause(row) -> str:
    if is_adverse(row):
        parts = []
        if pd.notna(row["min_visib"]) and row["min_visib"] < ADVERSE["min_visib"]:
            parts.append(f"visibilité {row['min_visib']:.1f} mi")
        if pd.notna(row["max_precip"]) and row["max_precip"] >= ADVERSE["max_precip"]:
            parts.append(f"précipitations {row['max_precip']:.2f} in/h")
        if pd.notna(row["max_gust"]) and row["max_gust"] >= ADVERSE["max_gust"]:
            parts.append(f"rafales {row['max_gust']:.0f} mph")
        return "Météo défavorable probable (" + ", ".join(parts) + ")"
    return "Cause non météorologique probable (congestion, incident, compagnie) — à investiguer"


def detect(df: pd.DataFrame) -> pd.DataFrame:
    out = []
    for origin, g in df.groupby("origin"):
        g = g.copy()
        g["robust_z"], g["baseline"] = robust_z(g["disruption_rate"])
        out.append(g)
    res = pd.concat(out)
    res["adverse_weather"] = res.apply(lambda r: is_adverse(r.where(pd.notna(r), None)), axis=1)
    res["flag"] = res["robust_z"] >= Z_THRESHOLD
    res["likely_cause"] = np.where(res["flag"], res.apply(likely_cause, axis=1), None)
    return res


def run(settings: Settings) -> dict:
    conn = connect(settings.db_path)
    res = detect(daily_frame(conn))
    flagged = res[res["flag"]].copy()
    flagged["direction"] = "hausse"
    with conn:
        conn.execute("DELETE FROM anomalies")
        conn.executemany(
            "INSERT INTO anomalies VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            [(r.origin, r.date_key, int(r.flights), float(r.disruption_rate), float(r.baseline), float(r.robust_z),
              r.direction, None if pd.isna(r.max_precip) else float(r.max_precip),
              None if pd.isna(r.min_visib) else float(r.min_visib),
              None if pd.isna(r.max_gust) else float(r.max_gust), r.likely_cause)
             for r in flagged.itertuples()])
    conn.close()
    scored = res[res["robust_z"].notna()]
    share_flag_adverse = float(flagged["adverse_weather"].mean()) if len(flagged) else 0.0
    share_all_adverse = float(scored["adverse_weather"].mean())
    events = {d: sorted(flagged.loc[flagged["date_key"] == d, "origin"].tolist())
              for d in ("2013-02-08", "2013-02-09")}
    summary = {"days_scored": int(len(scored)), "days_flagged": int(len(flagged)),
               "share_flagged_with_adverse_weather": share_flag_adverse,
               "share_all_days_with_adverse_weather": share_all_adverse,
               "lift": share_flag_adverse / share_all_adverse if share_all_adverse else None,
               "blizzard_2013_02_08_09_flagged_airports": events,
               "z_threshold": Z_THRESHOLD, "window_days": WINDOW}
    settings.reports_dir.mkdir(parents=True, exist_ok=True)
    flagged.sort_values("robust_z", ascending=False)[
        ["origin", "date_key", "flights", "disruption_rate", "baseline", "robust_z", "max_precip", "min_visib",
         "max_gust", "likely_cause"]].to_csv(settings.reports_dir / "anomalies.csv", index=False)
    (settings.reports_dir / "anomalies_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False),
                                                                encoding="utf-8")
    plot(res, settings)
    log.info("Anomalies : %d journees signalees sur %d ; %.0f%% avec meteo defavorable (base %.0f%%)",
             len(flagged), len(scored), 100 * share_flag_adverse, 100 * share_all_adverse)
    return summary


def plot(res: pd.DataFrame, settings: Settings) -> None:
    fig, axes = plt.subplots(3, 1, figsize=(11, 7.5), sharex=True)
    for ax, (origin, g) in zip(axes, res.groupby("origin")):
        d = pd.to_datetime(g["date_key"])
        ax.plot(d, g["disruption_rate"], lw=0.8, color="#0B4A6F", label="Taux de perturbation")
        ax.plot(d, g["baseline"], lw=0.8, color="grey", ls="--", label="Référence (médiane 28 j)")
        f = g[g["flag"]]
        ax.scatter(pd.to_datetime(f["date_key"]), f["disruption_rate"], color="#C0392B", s=18, zorder=3, label="Anomalie")
        ax.set_ylabel(origin)
        ax.set_ylim(0, 1)
    axes[0].legend(fontsize=8, loc="upper right")
    axes[0].set_title("Journées de perturbation anormale par aéroport (2013)")
    fig.tight_layout()
    (settings.figures_dir).mkdir(parents=True, exist_ok=True)
    fig.savefig(settings.figures_dir / "anomalies.png", dpi=130)
    plt.close(fig)


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description="Détecte les journées de perturbation anormale.").parse_args(argv)
    setup_logging()
    s = run(Settings.from_env())
    print(json.dumps(s, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
