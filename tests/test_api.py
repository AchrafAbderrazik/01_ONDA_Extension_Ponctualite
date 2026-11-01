"""Tests de l'API Flask (client de test, base et modèle synthétiques isolés)."""

from datetime import datetime, timedelta, timezone

import jwt
import pytest

from aeroops.api import create_app


@pytest.fixture()
def client(synthetic_project):
    app = create_app(synthetic_project["settings"])
    app.config["TESTING"] = True
    return app.test_client()


VALID = {"carrier": "UA", "origin": "EWR", "dest": "ORD", "date": "2013-12-05", "time": "18:30"}


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200 and r.get_json()["model"] is True


def test_kpis_and_filters(client):
    body = client.get("/api/kpis?airport=JFK").get_json()
    assert set(body) >= {"overall", "by_airport", "by_carrier"}
    assert body["by_airport"][0]["airport"] == "JFK"
    assert client.get("/api/kpis?month=13").status_code == 400


def test_timeseries(client):
    r = client.get("/api/kpis/timeseries?granularity=month")
    assert r.status_code == 200 and len(r.get_json()["series"]) == 12
    assert client.get("/api/kpis/timeseries?granularity=week").status_code == 400


def test_flights_risk(client):
    assert client.get("/api/flights/risk").status_code == 400
    r = client.get("/api/flights/risk?date=2013-12-05&limit=5")
    assert r.status_code == 200
    flights = r.get_json()["flights"]
    assert flights and all(0 <= f["proba"] <= 1 for f in flights)
    assert flights == sorted(flights, key=lambda f: -f["proba"])
    assert client.get("/api/flights/risk?date=2013-03-01").status_code == 404


def test_predict_valid_and_invalid(client):
    r = client.post("/api/predict", json=VALID)
    body = r.get_json()
    assert r.status_code == 200 and 0 <= body["probability"] <= 1
    assert body["risk_level"] in {"faible", "modéré", "élevé"} and body["factors"]
    assert client.post("/api/predict", json={**VALID, "carrier": "ZZ"}).status_code == 400
    assert client.post("/api/predict", json={k: v for k, v in VALID.items() if k != "dest"}).status_code == 400
    assert client.post("/api/predict", json={**VALID, "time": "25:99"}).status_code == 400
    assert client.post("/api/predict", json={**VALID, "weather": {"visib": "foggy"}}).status_code == 400


def test_quality_and_metrics(client):
    q = client.get("/api/quality").get_json()
    assert q["rules"] and q["run"]["status"] == "SUCCESS"
    assert client.get("/api/model/metrics").status_code == 200
    assert client.get("/api/model/figures/secret.txt").status_code == 404


def test_admin_reload_requires_valid_admin_token(client, monkeypatch):
    monkeypatch.delenv("AEROOPS_ADMIN_SECRET", raising=False)
    assert client.post("/api/admin/reload-model").status_code == 503
    monkeypatch.setenv("AEROOPS_ADMIN_SECRET", "test-secret")
    assert client.post("/api/admin/reload-model").status_code == 401
    exp = datetime.now(timezone.utc) + timedelta(minutes=5)
    user = jwt.encode({"sub": "u", "role": "viewer", "exp": exp}, "test-secret", algorithm="HS256")
    assert client.post("/api/admin/reload-model", headers={"Authorization": f"Bearer {user}"}).status_code == 403
    admin = jwt.encode({"sub": "a", "role": "admin", "exp": exp}, "test-secret", algorithm="HS256")
    r = client.post("/api/admin/reload-model", headers={"Authorization": f"Bearer {admin}"})
    assert r.status_code == 200 and r.get_json()["reloaded"] is True
