"""API REST Flask du module Ponctualité (application factory + blueprints)."""

from __future__ import annotations

import json
import os
from datetime import datetime

import jwt
from flask import Blueprint, Flask, abort, current_app, jsonify, request, send_from_directory
from flask_cors import CORS
from sqlalchemy import create_engine, text

from .. import DISCLAIMER_FR, __version__
from ..config import Settings
from .model_service import ModelService, ValidationError

api = Blueprint("api", __name__, url_prefix="/api")
FIGURES = {"roc_pr.png", "calibration.png", "importance.png", "anomalies.png"}


def _engine():
    return current_app.config["ENGINE"]


def _rows(sql: str, **params) -> list[dict]:
    with _engine().connect() as c:
        return [dict(r) for r in c.execute(text(sql), params).mappings()]


def _filters(alias: str = "f") -> tuple[str, dict]:
    clauses, params = [], {}
    airport = request.args.get("airport")
    carrier = request.args.get("carrier")
    month = request.args.get("month")
    if airport:
        clauses.append(f"{alias}.origin = :airport"); params["airport"] = airport.upper()
    if carrier:
        clauses.append(f"{alias}.carrier = :carrier"); params["carrier"] = carrier.upper()
    if month:
        if not month.isdigit() or not 1 <= int(month) <= 12:
            raise ValidationError("month doit être un entier entre 1 et 12")
        clauses.append(f"CAST(substr({alias}.date_key, 6, 2) AS INTEGER) = :month"); params["month"] = int(month)
    return (" WHERE " + " AND ".join(clauses)) if clauses else "", params


KPI_SELECT = """COUNT(*) AS flights, SUM(cancelled) AS cancelled,
  ROUND(1.0 * SUM(cancelled) / COUNT(*), 4) AS cancel_rate,
  ROUND(AVG(CASE WHEN cancelled = 0 THEN CASE WHEN dep_delay < 15 THEN 1.0 ELSE 0.0 END END), 4) AS otp15,
  ROUND(AVG(CASE WHEN cancelled = 0 THEN dep_delay END), 2) AS avg_dep_delay,
  ROUND(AVG(target), 4) AS disruption_rate"""


@api.errorhandler(ValidationError)
def _bad_request(exc):
    return jsonify({"error": str(exc)}), 400


@api.get("/health")
def health():
    ok_db = True
    try:
        _rows("SELECT 1 AS x")
    except Exception:  # pragma: no cover - base absente
        ok_db = False
    svc: ModelService = current_app.config["MODEL"]
    return jsonify({"status": "ok" if ok_db else "degraded", "database": ok_db, "model": svc.ready,
                    "version": __version__, "disclaimer": DISCLAIMER_FR})


@api.get("/kpis")
def kpis():
    where, params = _filters()
    overall = _rows(f"SELECT {KPI_SELECT} FROM fact_flight f{where}", **params)[0]
    by_airport = _rows(f"SELECT f.origin AS airport, {KPI_SELECT} FROM fact_flight f{where} GROUP BY f.origin", **params)
    by_carrier = _rows(f"SELECT f.carrier, c.name, {KPI_SELECT} FROM fact_flight f JOIN dim_carrier c ON c.carrier=f.carrier"
                       f"{where} GROUP BY f.carrier ORDER BY flights DESC", **params)
    return jsonify({"overall": overall, "by_airport": by_airport, "by_carrier": by_carrier, "filters": params})


@api.get("/kpis/timeseries")
def timeseries():
    where, params = _filters()
    gran = request.args.get("granularity", "day")
    if gran not in ("day", "month"):
        raise ValidationError("granularity doit valoir day ou month")
    key = "f.date_key" if gran == "day" else "substr(f.date_key, 1, 7)"
    data = _rows(f"SELECT {key} AS period, {KPI_SELECT} FROM fact_flight f{where} GROUP BY period ORDER BY period", **params)
    if gran == "day":
        an_where = " WHERE origin = :airport" if "airport" in params else ""
        flagged = {r["date_key"] for r in _rows(f"SELECT DISTINCT date_key FROM anomalies{an_where}",
                                                **({"airport": params["airport"]} if "airport" in params else {}))}
        for d in data:
            d["anomaly"] = d["period"] in flagged
    return jsonify({"granularity": gran, "series": data})


@api.get("/delays/by-hour")
def delays_by_hour():
    where, params = _filters()
    data = _rows(f"SELECT f.sched_hour AS hour, {KPI_SELECT} FROM fact_flight f{where} GROUP BY f.sched_hour ORDER BY hour", **params)
    return jsonify({"series": data})


@api.get("/anomalies")
def anomalies():
    params, where = {}, ""
    if request.args.get("airport"):
        where, params["airport"] = " WHERE origin = :airport", request.args["airport"].upper()
    limit = request.args.get("limit", "50")
    if not limit.isdigit():
        raise ValidationError("limit doit être un entier")
    params["limit"] = min(int(limit), 500)
    data = _rows(f"SELECT * FROM anomalies{where} ORDER BY robust_z DESC LIMIT :limit", **params)
    return jsonify({"count": len(data), "anomalies": data})


@api.get("/flights/risk")
def flights_risk():
    day = request.args.get("date")
    try:
        datetime.strptime(day or "", "%Y-%m-%d")
    except ValueError as exc:
        raise ValidationError("Paramètre date obligatoire au format AAAA-MM-JJ") from exc
    params = {"d": day, "limit": min(int(request.args.get("limit", "100")), 1000)}
    extra = ""
    if request.args.get("airport"):
        extra, params["airport"] = " AND f.origin = :airport", request.args["airport"].upper()
    data = _rows("""SELECT f.flight_id, f.sched_dep_local, f.carrier, f.flight_no, f.origin, f.dest, p.proba, p.risk_level,
                   p.factors, p.split, f.target AS observed_disruption
                   FROM predictions p JOIN fact_flight f ON f.flight_id = p.flight_id
                   WHERE f.date_key = :d""" + extra + " ORDER BY p.proba DESC LIMIT :limit", **params)
    if not data:
        rng = _rows("SELECT MIN(f.date_key) AS start, MAX(f.date_key) AS end FROM predictions p JOIN fact_flight f ON f.flight_id=p.flight_id")[0]
        return jsonify({"date": day, "flights": [], "message": f"Prédictions disponibles du {rng['start']} au {rng['end']}"}), 404
    for d in data:
        d["factors"] = json.loads(d["factors"] or "[]")
    return jsonify({"date": day, "count": len(data), "flights": data})


@api.post("/predict")
def predict():
    svc: ModelService = current_app.config["MODEL"]
    if not svc.ready:
        return jsonify({"error": "Modèle non disponible"}), 503
    return jsonify(svc.predict(request.get_json(silent=True)))


@api.get("/quality")
def quality():
    run = _rows("SELECT * FROM etl_runs WHERE status='SUCCESS' ORDER BY started_at DESC LIMIT 1")
    if not run:
        return jsonify({"error": "Aucune exécution ETL réussie"}), 404
    rules = _rows("SELECT rule_id, tbl AS table_name, description, severity, checked, violations, action FROM dq_results "
                  "WHERE run_id = :r ORDER BY rule_id", r=run[0]["run_id"])
    return jsonify({"run": run[0], "rules": rules})


@api.get("/model/metrics")
def model_metrics():
    path = current_app.config["SETTINGS"].metrics_path
    if not path.exists():
        return jsonify({"error": "Métriques indisponibles"}), 404
    return jsonify(json.loads(path.read_text(encoding="utf-8")))


@api.get("/model/figures/<name>")
def model_figure(name: str):
    if name not in FIGURES:
        abort(404)
    return send_from_directory(current_app.config["SETTINGS"].figures_dir, name)


@api.post("/admin/reload-model")
def reload_model():
    secret = os.environ.get("AEROOPS_ADMIN_SECRET")
    if not secret:
        return jsonify({"error": "Administration désactivée (AEROOPS_ADMIN_SECRET non défini)"}), 503
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return jsonify({"error": "Jeton manquant"}), 401
    try:
        claims = jwt.decode(auth[7:], secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        return jsonify({"error": "Jeton invalide ou expiré"}), 401
    if claims.get("role") != "admin":
        return jsonify({"error": "Rôle administrateur requis"}), 403
    ok = current_app.config["MODEL"].reload()
    return jsonify({"reloaded": ok})


def create_app(settings: Settings | None = None) -> Flask:
    settings = settings or Settings.from_env()
    dist = settings.dashboard_dist
    app = Flask(__name__, static_folder=str(dist), static_url_path="/")
    app.config["SETTINGS"] = settings
    app.config["ENGINE"] = create_engine(f"sqlite:///{settings.db_path}", future=True)
    app.config["MODEL"] = ModelService(settings.model_path, app.config["ENGINE"])
    app.json.ensure_ascii = False
    CORS(app, resources={r"/api/*": {"origins": ["http://localhost:5173", "http://127.0.0.1:5173"]}})
    app.register_blueprint(api)

    @app.get("/")
    def index():
        if (dist / "index.html").exists():
            return send_from_directory(dist, "index.html")
        return ("<p>Tableau de bord non construit : lancer <code>npm run build</code> dans <code>dashboard/</code>. "
                "L'API est disponible sous <code>/api</code>.</p>"), 200

    return app
