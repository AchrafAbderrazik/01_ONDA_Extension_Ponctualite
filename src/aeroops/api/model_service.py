"""Chargement du modèle et prédiction unitaire (utilisés par l'endpoint POST /api/predict)."""

from __future__ import annotations

import math
from datetime import date, datetime
from typing import Any

import joblib
import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from ..factors import context_factors
from ..features import CAT_FEATURES, NUM_FEATURES

WEATHER_FIELDS = ["temp", "humid", "wind_speed", "wind_gust", "precip", "visib", "pressure"]


class ValidationError(ValueError):
    """Entrée invalide : renvoyée au client en HTTP 400."""


class ModelService:
    def __init__(self, model_path, engine: Engine):
        self.model_path = model_path
        self.engine = engine
        self.artifact: dict[str, Any] | None = None
        self.reload()

    def reload(self) -> bool:
        try:
            self.artifact = joblib.load(self.model_path)
        except FileNotFoundError:
            self.artifact = None
        return self.artifact is not None

    @property
    def ready(self) -> bool:
        return self.artifact is not None

    def _known(self, table: str, col: str, value: str) -> bool:
        with self.engine.connect() as c:
            return c.execute(text(f"SELECT 1 FROM {table} WHERE {col} = :v"), {"v": value}).first() is not None

    def _route_distance(self, origin: str, dest: str) -> float | None:
        with self.engine.connect() as c:
            row = c.execute(text("SELECT AVG(distance) FROM fact_flight WHERE origin=:o AND dest=:d"),
                            {"o": origin, "d": dest}).first()
        return None if row is None or row[0] is None else float(row[0])

    def _congestion(self, origin: str, weekday: int, hour: int) -> float | None:
        q = """SELECT AVG(n) FROM (SELECT f.date_key, COUNT(*) AS n FROM fact_flight f JOIN dim_date d ON d.date_key=f.date_key
               WHERE f.origin=:o AND f.sched_hour=:h AND d.weekday=:w GROUP BY f.date_key)"""
        with self.engine.connect() as c:
            row = c.execute(text(q), {"o": origin, "h": hour, "w": weekday}).first()
        return None if row is None or row[0] is None else float(row[0])

    def _weather_at(self, origin: str, day: date, hour: int) -> dict | None:
        q = "SELECT temp, humid, wind_speed, wind_gust, precip, visib, pressure FROM fact_weather_hourly WHERE origin=:o AND date_key=:d AND local_hour=:h"
        with self.engine.connect() as c:
            row = c.execute(text(q), {"o": origin, "d": day.isoformat(), "h": hour}).mappings().first()
        return dict(row) if row else None

    def validate(self, payload: dict) -> dict:
        if not isinstance(payload, dict):
            raise ValidationError("Le corps de la requête doit être un objet JSON.")
        missing = [k for k in ("carrier", "origin", "dest", "date", "time") if not payload.get(k)]
        if missing:
            raise ValidationError(f"Champs obligatoires manquants : {', '.join(missing)}")
        carrier, origin, dest = (str(payload[k]).strip().upper() for k in ("carrier", "origin", "dest"))
        try:
            day = datetime.strptime(str(payload["date"]), "%Y-%m-%d").date()
            hh, mm = (int(x) for x in str(payload["time"]).split(":"))
            if not (0 <= hh <= 23 and 0 <= mm <= 59):
                raise ValueError
        except ValueError as exc:
            raise ValidationError("Format attendu : date AAAA-MM-JJ et time HH:MM.") from exc
        if not self._known("dim_carrier", "carrier", carrier):
            raise ValidationError(f"Compagnie inconnue : {carrier}")
        for code in (origin, dest):
            if not self._known("dim_airport", "faa", code):
                raise ValidationError(f"Aéroport inconnu : {code}")
        weather = payload.get("weather") or {}
        if not isinstance(weather, dict):
            raise ValidationError("« weather » doit être un objet.")
        for k, v in weather.items():
            if k not in WEATHER_FIELDS or not isinstance(v, (int, float)):
                raise ValidationError(f"Variable météo invalide : {k}")
        return {"carrier": carrier, "origin": origin, "dest": dest, "date": day, "hour": hh, "minute": mm,
                "distance": payload.get("distance"), "weather": weather}

    def predict(self, payload: dict) -> dict:
        if not self.ready:
            raise RuntimeError("Modèle non disponible : lancer python -m aeroops.train")
        v = self.validate(payload)
        a = self.artifact
        med = a["train_medians"]
        assumptions = []
        row = {"carrier": v["carrier"], "origin": v["origin"], "dest": v["dest"], "sched_hour": v["hour"],
               "weekday": v["date"].weekday(), "month": v["date"].month}
        dist = v["distance"] if isinstance(v["distance"], (int, float)) else self._route_distance(v["origin"], v["dest"])
        if dist is None:
            dist = med["distance"]; assumptions.append("distance : médiane d'entraînement (liaison inconnue)")
        row["distance"] = float(dist)
        row["plane_age"] = med["plane_age"]; assumptions.append("âge de l'avion : médiane d'entraînement")
        cong = self._congestion(v["origin"], row["weekday"], v["hour"])
        row["congestion_origin_hour"] = cong if cong is not None else med["congestion_origin_hour"]
        assumptions.append("charge programmée : moyenne historique (origine, jour de semaine, heure)")
        wx = dict(v["weather"])
        if len(wx) < len(WEATHER_FIELDS):
            stored = self._weather_at(v["origin"], v["date"], v["hour"]) or {}
            for f in WEATHER_FIELDS:
                if f not in wx:
                    val = stored.get(f)
                    wx[f] = val if val is not None else med.get(f)
            assumptions.append("météo : observation stockée à cette heure si disponible, sinon médiane d'entraînement")
        if wx.get("wind_gust") is None:
            wx["wind_gust"] = wx.get("wind_speed")
        row.update(wx)
        frame = a["encoder"].transform(pd.DataFrame([row]))
        proba = float(a["model"].predict_proba(frame[CAT_FEATURES + NUM_FEATURES])[:, 1][0])
        t = a["thresholds"]
        level = "élevé" if proba >= t["eleve"] else ("modéré" if proba >= t["modere"] else "faible")
        rec = frame.iloc[0].to_dict()
        rec = {k: (None if isinstance(x, float) and math.isnan(x) else x) for k, x in rec.items()}
        return {"probability": round(proba, 4), "risk_level": level,
                "factors": context_factors(rec, a["prior"], a["congestion_p90"]),
                "assumptions": assumptions, "model": a["model_name"], "model_version": a["version"]}
