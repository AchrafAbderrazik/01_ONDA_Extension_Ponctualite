"""Tests du modèle (absence de fuite, découpage, artefacts) et de la détection d'anomalies."""

import json
import sqlite3

import numpy as np
import pandas as pd
import pytest

from aeroops.anomalies import robust_z
from aeroops.config import TEST_START, TRAIN_END, VALID_END, VALID_START
from aeroops.features import CAT_FEATURES, FORBIDDEN, NUM_FEATURES, TargetEncoder, split_by_date


def test_no_post_departure_feature():
    assert not (set(CAT_FEATURES + NUM_FEATURES) & FORBIDDEN)


def test_split_is_temporal_and_disjoint():
    df = pd.DataFrame({"date": pd.date_range("2013-01-01", "2013-12-31", freq="D")})
    parts = split_by_date(df)
    assert parts["train"]["date"].max().date() == TRAIN_END
    assert parts["valid"]["date"].min().date() == VALID_START and parts["valid"]["date"].max().date() == VALID_END
    assert parts["test"]["date"].min().date() == TEST_START
    assert len(parts["train"]) + len(parts["valid"]) + len(parts["test"]) == len(df)


def test_target_encoder_uses_training_data_only():
    train = pd.DataFrame({"carrier": ["UA", "UA", "AA"], "sched_hour": [8, 8, 8], "origin": ["EWR"] * 3,
                          "dest": ["ORD"] * 3, "month": [1, 1, 1], "target": [1, 0, 0]})
    other = train.copy()
    enc = TargetEncoder().fit(train)
    a = enc.transform(other)["hist_rate_carrier_hour"].tolist()
    other["target"] = 1  # changer la cible hors entraînement ne doit rien changer
    b = enc.transform(other)["hist_rate_carrier_hour"].tolist()
    assert a == b


def test_training_outputs(synthetic_project):
    m = synthetic_project["metrics"]
    s = synthetic_project["settings"]
    for name, t in m["test"].items():
        assert 0.0 <= t["roc_auc"] <= 1.0 and 0.0 <= t["pr_auc"] <= 1.0
    assert s.model_path.exists() and s.metrics_path.exists()
    saved = json.loads(s.metrics_path.read_text(encoding="utf-8"))
    assert saved["model"] == m["model"]
    assert (s.reports_dir / "evaluation_report.md").exists()


def test_predictions_only_for_valid_and_test(synthetic_project):
    conn = sqlite3.connect(synthetic_project["settings"].db_path)
    rows = conn.execute("SELECT DISTINCT p.split, MIN(f.date_key), MAX(f.date_key) FROM predictions p "
                        "JOIN fact_flight f ON f.flight_id=p.flight_id GROUP BY p.split").fetchall()
    splits = {r[0]: (r[1], r[2]) for r in rows}
    assert set(splits) == {"valid", "test"}
    assert splits["valid"][0] >= "2013-10-01" and splits["test"][1] <= "2013-12-31"
    bad = conn.execute("SELECT COUNT(*) FROM predictions WHERE proba < 0 OR proba > 1 "
                       "OR risk_level NOT IN ('faible','modéré','élevé')").fetchone()[0]
    assert bad == 0
    conn.close()


def test_robust_z_flags_spike_without_future_leakage():
    s = pd.Series([0.2 + 0.01 * np.sin(i) for i in range(60)])
    s.iloc[50] = 0.9
    z, _ = robust_z(s)
    assert z.iloc[50] >= 3
    s2 = s.copy()
    s2.iloc[55:] = 0.99  # modifier le futur ne change pas le score passé
    z2, _ = robust_z(s2)
    assert z2.iloc[50] == pytest.approx(z.iloc[50])


def test_anomaly_run_writes_table(synthetic_project):
    a = synthetic_project["anomalies"]
    conn = sqlite3.connect(synthetic_project["settings"].db_path)
    n = conn.execute("SELECT COUNT(*) FROM anomalies").fetchone()[0]
    assert n == a["days_flagged"]
    assert 0 <= a["share_flagged_with_adverse_weather"] <= 1
    conn.close()
