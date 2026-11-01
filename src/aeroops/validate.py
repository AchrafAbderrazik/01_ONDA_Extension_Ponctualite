"""Contrôles de qualité des données brutes (avant transformation).

Chaque règle produit un ``RuleResult`` : nombre de lignes contrôlées, nombre de
violations, gravité et action appliquée par la transformation. Les règles
CRITIQUES bloquent le chargement ; les autres sont corrigées ou signalées.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

CRITICAL, WARNING, INFO = "CRITIQUE", "AVERTISSEMENT", "INFO"

REQUIRED_COLUMNS = {
    "flights": ["year", "month", "day", "dep_time", "sched_dep_time", "dep_delay", "arr_delay", "carrier",
                "flight", "tailnum", "origin", "dest", "air_time", "distance", "hour", "minute", "time_hour"],
    "weather": ["origin", "year", "month", "day", "hour", "temp", "dewp", "humid", "wind_dir", "wind_speed",
                "wind_gust", "precip", "pressure", "visib", "time_hour"],
    "airlines": ["carrier", "name"],
    "airports": ["faa", "name", "lat", "lon", "alt", "tz", "dst", "tzone"],
    "planes": ["tailnum", "year", "type", "manufacturer", "model", "engines", "seats", "engine"],
}
FLIGHT_KEY = ["year", "month", "day", "carrier", "flight", "origin", "sched_dep_time"]
NUMERIC_COLUMNS = {
    "flights": ["year", "month", "day", "dep_time", "sched_dep_time", "dep_delay", "arr_delay", "flight",
                "air_time", "distance", "hour", "minute"],
    "weather": ["year", "month", "day", "hour", "temp", "dewp", "humid", "wind_dir", "wind_speed",
                "wind_gust", "precip", "pressure", "visib"],
    "planes": ["year", "engines", "seats"],
}
#: Vent > 150 mph impossible au sol à New York (valeur aberrante connue du jeu).
MAX_PLAUSIBLE_WIND_MPH = 150.0


@dataclass
class RuleResult:
    rule_id: str
    table: str
    description: str
    severity: str
    checked: int
    violations: int
    action: str

    @property
    def rate(self) -> float:
        return self.violations / self.checked if self.checked else 0.0


def _num(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _hhmm_invalid(values: pd.Series) -> pd.Series:
    """True si une heure HHMM non nulle est invalide (minutes ≥ 60 ou heure > 24)."""
    v = _num(values)
    hh, mm = v // 100, v % 100
    return v.notna() & ((mm >= 60) | (hh > 24) | (v < 0))


def run_rules(tables: dict[str, pd.DataFrame]) -> list[RuleResult]:
    """Applique toutes les règles et retourne leurs résultats (aucune modification des données)."""
    res: list[RuleResult] = []
    f, w = tables["flights"], tables["weather"]
    airlines, airports, planes = tables["airlines"], tables["airports"], tables["planes"]

    # R01 — schéma
    for name, cols in REQUIRED_COLUMNS.items():
        missing = [c for c in cols if c not in tables[name].columns]
        res.append(RuleResult("R01", name, f"Colonnes obligatoires présentes ({len(cols)})", CRITICAL,
                              len(cols), len(missing), "Arrêt du chargement si colonne absente" if missing else "Aucune"))
    if any(r.violations for r in res):
        return res

    # R02 — types numériques
    for name, cols in NUMERIC_COLUMNS.items():
        df = tables[name]
        bad = sum(int((df[c].notna() & _num(df[c]).isna()).sum()) for c in cols)
        res.append(RuleResult("R02", name, "Valeurs numériques non convertibles", WARNING,
                              int(len(df) * len(cols)), bad, "Valeur mise à NULL"))

    # R03 — clés métier non nulles
    nulls = int(f[["year", "month", "day", "carrier", "flight", "origin", "dest", "sched_dep_time"]].isna().any(axis=1).sum())
    res.append(RuleResult("R03", "flights", "Clés métier renseignées (date, compagnie, vol, origine, destination, horaire)",
                          CRITICAL, len(f), nulls, "Lignes exclues"))

    # R04 — doublons sur la clé naturelle
    dups = int(f.duplicated(subset=FLIGHT_KEY, keep="first").sum())
    res.append(RuleResult("R04", "flights", "Unicité de la clé naturelle " + "+".join(FLIGHT_KEY), WARNING,
                          len(f), dups, "Doublons exclus (première occurrence conservée)"))

    # R05 — format horaire HHMM
    bad_sched = int(_hhmm_invalid(f["sched_dep_time"]).sum())
    res.append(RuleResult("R05", "flights", "Horaire programmé HHMM valide", CRITICAL, len(f), bad_sched, "Lignes exclues"))
    n2400 = int((_num(f["dep_time"]) == 2400).sum())
    res.append(RuleResult("R06", "flights", "Heure réelle 2400 (minuit) normalisée", INFO, len(f), n2400,
                          "2400 converti en 0000 du jour suivant"))

    # R07 — vols annulés (heure de départ absente)
    cancelled = int(f["dep_time"].isna().sum())
    res.append(RuleResult("R07", "flights", "Vols sans heure de départ réelle (annulés)", INFO, len(f), cancelled,
                          "Conservés, marqués cancelled=1 (comptent comme perturbation)"))

    # R08 — plages de valeurs
    dist = _num(f["distance"])
    res.append(RuleResult("R08", "flights", "Distance strictement positive", WARNING, int(dist.notna().sum()),
                          int((dist <= 0).sum()), "Lignes exclues"))
    delay = _num(f["dep_delay"])
    res.append(RuleResult("R09", "flights", "Retard au départ dans [-120 ; 1 500] min", WARNING, int(delay.notna().sum()),
                          int(((delay < -120) | (delay > 1500)).sum()), "Conservé et signalé"))

    # R10–R12 — intégrité référentielle
    unknown_carrier = int((~f["carrier"].isin(airlines["carrier"])).sum())
    res.append(RuleResult("R10", "flights", "Compagnie présente dans le référentiel airlines", CRITICAL, len(f),
                          unknown_carrier, "Lignes exclues"))
    known_airports = set(airports["faa"])
    unknown_dest = ~f["dest"].isin(known_airports)
    res.append(RuleResult("R11", "flights",
                          f"Destination présente dans le référentiel airports ({int(f.loc[unknown_dest, 'dest'].nunique())} codes absents)",
                          WARNING, len(f), int(unknown_dest.sum()),
                          "Aéroport ajouté comme membre « inconnu » de dim_airport"))
    with_tail = f["tailnum"].notna()
    unknown_tail = with_tail & ~f["tailnum"].isin(planes["tailnum"])
    res.append(RuleResult("R12", "flights", "Immatriculation présente dans le référentiel planes", WARNING,
                          int(with_tail.sum()), int(unknown_tail.sum()),
                          "Avion ajouté comme membre « inconnu » de dim_aircraft (âge NULL)"))

    # R13 — couverture météo (jointure origine + heure programmée UTC)
    wkeys = set(zip(w["origin"], w["time_hour"]))
    covered = np.fromiter(((o, t) in wkeys for o, t in zip(f["origin"], f["time_hour"])), dtype=bool, count=len(f))
    res.append(RuleResult("R13", "flights", "Observation météo disponible à l'heure programmée", WARNING, len(f),
                          int((~covered).sum()), "Variables météo NULL (imputées au moment de l'entraînement)"))

    # R14 — doublons météo
    wd = int(w.duplicated(subset=["origin", "time_hour"], keep="first").sum())
    res.append(RuleResult("R14", "weather", "Unicité (origine, heure) des observations météo", WARNING, len(w), wd,
                          "Doublons exclus"))

    # R15 — vent plausible
    wind = _num(w["wind_speed"])
    res.append(RuleResult("R15", "weather", f"Vitesse du vent ≤ {MAX_PLAUSIBLE_WIND_MPH:.0f} mph", WARNING,
                          int(wind.notna().sum()), int((wind > MAX_PLAUSIBLE_WIND_MPH).sum()), "Valeur mise à NULL"))

    # R16 — année de construction des avions plausible
    py = _num(planes["year"])
    res.append(RuleResult("R16", "planes", "Année de construction entre 1950 et 2013", WARNING, int(py.notna().sum()),
                          int(((py < 1950) | (py > 2013)).sum()), "Valeur mise à NULL"))
    res.append(RuleResult("R17", "planes", "Année de construction renseignée", INFO, len(planes), int(py.isna().sum()),
                          "Âge de l'avion NULL"))
    return res


def blocking(results: list[RuleResult]) -> list[RuleResult]:
    """Règles critiques violées sur toutes les lignes ou sur le schéma (arrêt du pipeline)."""
    return [r for r in results if r.severity == CRITICAL and r.rule_id == "R01" and r.violations]


def write_report(results: list[RuleResult], reports_dir: Path, run_id: str) -> tuple[Path, Path]:
    """Écrit le rapport qualité en JSON (machine) et Markdown (humain)."""
    reports_dir.mkdir(parents=True, exist_ok=True)
    payload = {"run_id": run_id, "rules": [asdict(r) | {"rate": round(r.rate, 6)} for r in results]}
    jpath = reports_dir / "data_quality_report.json"
    jpath.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    lines = [
        "# Rapport de qualité des données",
        "",
        f"Exécution ETL : `{run_id}` — généré automatiquement par `python -m aeroops.etl`.",
        "",
        "| Règle | Table | Contrôle | Gravité | Lignes contrôlées | Violations | Taux | Action |",
        "|---|---|---|---|---:|---:|---:|---|",
    ]
    def fmt(n: int) -> str:
        return f"{n:,}".replace(",", "\u202f")

    for r in results:
        lines.append(f"| {r.rule_id} | {r.table} | {r.description} | {r.severity} | {fmt(r.checked)} | "
                     f"{fmt(r.violations)} | {r.rate:.2%} | {r.action} |")
    mpath = reports_dir / "data_quality_report.md"
    mpath.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return jpath, mpath
