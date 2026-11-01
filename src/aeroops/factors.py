"""Facteurs de contexte lisibles accompagnant un score de risque.

Ce ne sont PAS des contributions exactes du modèle : ce sont des règles transparentes qui
signalent les conditions associées, dans l'historique d'entraînement, à plus de retards.
"""

from __future__ import annotations

import math


def _isnum(x) -> bool:
    return x is not None and not (isinstance(x, float) and math.isnan(x))


def context_factors(row: dict, prior: float, congestion_p90: float) -> list[str]:
    out: list[str] = []
    r = row.get("hist_rate_carrier_hour")
    if _isnum(r) and r >= 1.3 * prior:
        out.append(f"Créneau compagnie × heure historiquement perturbé ({r:.0%} contre {prior:.0%} en moyenne)")
    r = row.get("hist_rate_route")
    if _isnum(r) and r >= 1.3 * prior:
        out.append(f"Liaison historiquement perturbée ({r:.0%})")
    h = row.get("sched_hour")
    if _isnum(h) and h >= 17:
        out.append("Départ en fin de journée (accumulation des retards)")
    c = row.get("congestion_origin_hour")
    if _isnum(c) and c >= congestion_p90:
        out.append(f"Créneau très chargé à l'origine ({int(c)} départs programmés dans l'heure)")
    v = row.get("visib")
    if _isnum(v) and v < 3:
        out.append(f"Visibilité réduite ({v:.1f} mi)")
    p = row.get("precip")
    if _isnum(p) and p > 0:
        out.append(f"Précipitations ({p:.2f} in/h)")
    g = row.get("wind_gust")
    if _isnum(g) and g >= 30:
        out.append(f"Rafales de vent ({g:.0f} mph)")
    if not out:
        out.append("Aucun facteur de contexte défavorable marqué")
    return out[:4]
