"""Entraînement et évaluation du modèle de risque de retard (découpage temporel strict).

Cible : retard au départ ≥ 15 min OU vol annulé. Entraînement janv.–sept., sélection sur
octobre (validation), évaluation finale unique sur nov.–déc. (test).

Usage : ``python -m aeroops.train``
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from datetime import datetime, timezone

import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.calibration import calibration_curve  # noqa: E402
from sklearn.compose import ColumnTransformer  # noqa: E402
from sklearn.ensemble import HistGradientBoostingClassifier  # noqa: E402
from sklearn.impute import SimpleImputer  # noqa: E402
from sklearn.inspection import permutation_importance  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score, roc_curve, precision_recall_curve  # noqa: E402
from sklearn.pipeline import Pipeline  # noqa: E402
from sklearn.preprocessing import OneHotEncoder, OrdinalEncoder, StandardScaler  # noqa: E402

from .config import Settings  # noqa: E402
from .factors import context_factors  # noqa: E402
from .features import CAT_FEATURES, NUM_FEATURES, TargetEncoder, feature_frame, load_base, split_by_date  # noqa: E402
from .load import connect  # noqa: E402
from .logging_utils import setup_logging  # noqa: E402

log = logging.getLogger(__name__)
SEED = 42
MODEL_VERSION = "1.0.0"


def make_logreg() -> Pipeline:
    pre = ColumnTransformer([
        ("cat", OneHotEncoder(handle_unknown="ignore", min_frequency=50), CAT_FEATURES),
        ("num", Pipeline([("imp", SimpleImputer(strategy="median")), ("sc", StandardScaler())]), NUM_FEATURES),
    ])
    return Pipeline([("pre", pre), ("clf", LogisticRegression(max_iter=3000, C=1.0))])


def make_hgb() -> Pipeline:
    pre = ColumnTransformer([
        ("cat", OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1, encoded_missing_value=-1), CAT_FEATURES),
        ("num", "passthrough", NUM_FEATURES),
    ])
    clf = HistGradientBoostingClassifier(learning_rate=0.06, max_iter=500, max_leaf_nodes=31, min_samples_leaf=200,
                                         l2_regularization=1.0, categorical_features=list(range(len(CAT_FEATURES))),
                                         early_stopping=True, validation_fraction=0.1, n_iter_no_change=30,
                                         random_state=SEED)
    return Pipeline([("pre", pre), ("clf", clf)])


def top_k_stats(y: np.ndarray, p: np.ndarray, frac: float = 0.10) -> dict:
    k = max(1, int(round(len(p) * frac)))
    idx = np.argsort(-p)[:k]
    prec = float(y[idx].mean())
    rec = float(y[idx].sum() / max(1, y.sum()))
    return {"precision": prec, "recall": rec, "lift": prec / float(y.mean())}


def evaluate(y: np.ndarray, p: np.ndarray) -> dict:
    return {"roc_auc": float(roc_auc_score(y, p)), "pr_auc": float(average_precision_score(y, p)),
            "brier": float(brier_score_loss(y, p)), "base_rate": float(y.mean()), "n": int(len(y)),
            "top10": top_k_stats(y, p, 0.10)}


def _fig_dir(settings: Settings):
    d = settings.figures_dir
    d.mkdir(parents=True, exist_ok=True)
    return d


def plot_curves(y: np.ndarray, preds: dict[str, np.ndarray], settings: Settings) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    for name, p in preds.items():
        fpr, tpr, _ = roc_curve(y, p)
        axes[0].plot(fpr, tpr, label=f"{name} (AUC {roc_auc_score(y, p):.3f})")
        pr, rc, _ = precision_recall_curve(y, p)
        axes[1].plot(rc, pr, label=f"{name} (AP {average_precision_score(y, p):.3f})")
    axes[0].plot([0, 1], [0, 1], ls="--", c="grey", lw=0.8)
    axes[0].set(title="Courbe ROC — test (nov.–déc.)", xlabel="Taux de faux positifs", ylabel="Taux de vrais positifs")
    axes[1].axhline(y.mean(), ls="--", c="grey", lw=0.8)
    axes[1].set(title="Précision–rappel — test", xlabel="Rappel", ylabel="Précision")
    for a in axes:
        a.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(_fig_dir(settings) / "roc_pr.png", dpi=130)
    plt.close(fig)


def plot_calibration(y: np.ndarray, p: np.ndarray, name: str, settings: Settings) -> None:
    frac_pos, mean_pred = calibration_curve(y, p, n_bins=10, strategy="quantile")
    fig, ax = plt.subplots(figsize=(4.8, 4.2))
    ax.plot([0, 1], [0, 1], ls="--", c="grey", lw=0.8, label="Calibration parfaite")
    ax.plot(mean_pred, frac_pos, marker="o", label=name)
    ax.set(title="Calibration — test", xlabel="Probabilité prédite", ylabel="Fréquence observée")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(_fig_dir(settings) / "calibration.png", dpi=130)
    plt.close(fig)


def plot_importance(imp: pd.Series, settings: Settings) -> None:
    fig, ax = plt.subplots(figsize=(6.5, 4.6))
    imp.sort_values().plot.barh(ax=ax, color="#0B4A6F")
    ax.set(title="Importance par permutation (baisse de PR-AUC, test)", xlabel="Baisse moyenne de PR-AUC")
    fig.tight_layout()
    fig.savefig(_fig_dir(settings) / "importance.png", dpi=130)
    plt.close(fig)


def risk_level(p: float, t_mod: float, t_high: float) -> str:
    return "élevé" if p >= t_high else ("modéré" if p >= t_mod else "faible")


def train_and_evaluate(settings: Settings, *, perm_sample: int = 20000) -> dict:
    t0 = time.time()
    conn = connect(settings.db_path)
    base = load_base(conn)
    parts = split_by_date(base)
    enc = TargetEncoder().fit(parts["train"])
    data = {k: enc.transform(v) for k, v in parts.items()}
    X = {k: feature_frame(v) for k, v in data.items()}
    y = {k: v["target"].to_numpy() for k, v in data.items()}
    log.info("Effectifs : train=%d valid=%d test=%d ; taux de perturbation train=%.3f",
             len(y["train"]), len(y["valid"]), len(y["test"]), y["train"].mean())

    models = {"Régression logistique": make_logreg(), "Gradient boosting (HGB)": make_hgb()}
    valid_scores, test_preds = {}, {}
    # Référence naïve : taux historique compagnie × heure
    valid_scores["Référence historique"] = average_precision_score(y["valid"], X["valid"]["hist_rate_carrier_hour"])
    test_preds["Référence historique"] = X["test"]["hist_rate_carrier_hour"].to_numpy()
    for name, m in models.items():
        t = time.time()
        m.fit(X["train"], y["train"])
        pv = m.predict_proba(X["valid"])[:, 1]
        valid_scores[name] = average_precision_score(y["valid"], pv)
        test_preds[name] = m.predict_proba(X["test"])[:, 1]
        log.info("%s : PR-AUC validation=%.4f (%.1fs)", name, valid_scores[name], time.time() - t)

    best_name = max(models, key=lambda n: valid_scores[n])
    best = models[best_name]
    test_metrics = {n: evaluate(y["test"], p) for n, p in test_preds.items()}
    valid_metrics = {n: float(s) for n, s in valid_scores.items()}

    # Seuils de niveau de risque fixés sur la validation (déciles)
    pv_best = best.predict_proba(X["valid"])[:, 1]
    t_mod, t_high = float(np.quantile(pv_best, 0.70)), float(np.quantile(pv_best, 0.90))

    # Importance par permutation sur un échantillon du test
    rng = np.random.RandomState(SEED)
    idx = rng.choice(len(y["test"]), size=min(perm_sample, len(y["test"])), replace=False)
    pi = permutation_importance(best, X["test"].iloc[idx], y["test"][idx], scoring="average_precision",
                                n_repeats=3, random_state=SEED, n_jobs=1)
    importance = pd.Series(pi.importances_mean, index=CAT_FEATURES + NUM_FEATURES).sort_values(ascending=False)

    plot_curves(y["test"], test_preds, settings)
    plot_calibration(y["test"], test_preds[best_name], best_name, settings)
    plot_importance(importance.head(12), settings)

    # Prédictions stockées pour la validation et le test (servies par l'API)
    congestion_p90 = float(np.quantile(data["train"]["congestion_origin_hour"], 0.90))
    rows = []
    fac_cols = ["hist_rate_carrier_hour", "hist_rate_route", "sched_hour", "congestion_origin_hour", "visib", "precip", "wind_gust"]
    for split in ("valid", "test"):
        p = best.predict_proba(X[split])[:, 1]
        recs = data[split][fac_cols].to_dict("records")
        for fid, pr, rec in zip(data[split]["flight_id"].to_numpy(), p, recs):
            fac = json.dumps(context_factors(rec, enc.prior, congestion_p90), ensure_ascii=False)
            rows.append((int(fid), split, float(pr), risk_level(float(pr), t_mod, t_high), MODEL_VERSION, fac))
    with conn:
        conn.execute("DELETE FROM predictions")
        conn.executemany("INSERT INTO predictions VALUES (?,?,?,?,?,?)", rows)
    conn.close()

    trained_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    artifact = {"model": best, "model_name": best_name, "version": MODEL_VERSION, "trained_at": trained_at,
                "encoder": enc, "cat_features": CAT_FEATURES, "num_features": NUM_FEATURES,
                "thresholds": {"modere": t_mod, "eleve": t_high}, "prior": enc.prior,
                "congestion_p90": congestion_p90,
                "train_medians": data["train"][NUM_FEATURES].median(numeric_only=True).to_dict()}
    settings.models_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, settings.model_path)
    metrics = {"model": best_name, "version": MODEL_VERSION, "trained_at": trained_at,
               "split": {"train": "2013-01-01..2013-09-30", "valid": "2013-10-01..2013-10-31", "test": "2013-11-01..2013-12-31"},
               "n": {k: int(len(v)) for k, v in y.items()}, "base_rate": {k: float(v.mean()) for k, v in y.items()},
               "valid_pr_auc": valid_metrics, "test": test_metrics, "thresholds": artifact["thresholds"],
               "permutation_importance_top": {k: float(v) for k, v in importance.head(12).items()},
               "duration_s": round(time.time() - t0, 1)}
    settings.metrics_path.write_text(json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8")
    write_report(metrics, settings)
    log.info("Modele retenu : %s — test ROC-AUC=%.3f PR-AUC=%.3f", best_name,
             test_metrics[best_name]["roc_auc"], test_metrics[best_name]["pr_auc"])
    return metrics


def _n(x: int) -> str:
    return f"{x:,}".replace(",", "\u202f")


def write_report(m: dict, settings: Settings) -> None:
    best = m["model"]
    L = ["# Rapport d'évaluation — modèle de risque de retard", "",
         "Projet personnel sur données publiques (nycflights13, US BTS 2013). Non affilié à l'ONDA.", "",
         "## Protocole", "",
         "- Cible : retard au départ ≥ 15 min **ou** vol annulé (« perturbation »).",
         "- Variables : uniquement des informations connues avant le départ (programme, compagnie, origine, "
         "destination, distance, âge de l'avion, charge programmée de l'heure, météo à l'heure programmée "
         "utilisée comme proxy d'une prévision à court terme, taux historiques appris sur l'entraînement).",
         f"- Découpage temporel : entraînement {m['split']['train']} ({_n(m['n']['train'])} vols), validation "
         f"{m['split']['valid']} ({_n(m['n']['valid'])}), test {m['split']['test']} ({_n(m['n']['test'])}).",
         "- Sélection du modèle sur la PR-AUC de validation ; le test n'est utilisé qu'une fois.", "",
         "## Résultats sur le test (nov.–déc. 2013)", "",
         "| Modèle | ROC-AUC | PR-AUC | Brier | Précision top 10 % | Rappel top 10 % | Lift top 10 % |",
         "|---|---:|---:|---:|---:|---:|---:|"]
    for name, t in m["test"].items():
        mark = " **(retenu)**" if name == best else ""
        L.append(f"| {name}{mark} | {t['roc_auc']:.3f} | {t['pr_auc']:.3f} | {t['brier']:.4f} | "
                 f"{t['top10']['precision']:.1%} | {t['top10']['recall']:.1%} | {t['top10']['lift']:.2f} |")
    br = m["base_rate"]
    L += ["", f"Taux de perturbation : entraînement {br['train']:.1%}, validation {br['valid']:.1%}, test {br['test']:.1%}.",
          "", "## Lecture", "",
          "- La ROC-AUC mesure la capacité à classer un vol perturbé avant un vol à l'heure ; la PR-AUC est plus "
          "exigeante car la classe positive est minoritaire.",
          "- Le « top 10 % » correspond à l'usage opérationnel : surveiller en priorité les 10 % de vols les plus risqués.",
          "- Les niveaux de risque (faible / modéré / élevé) sont fixés sur les déciles de la validation "
          f"(seuils {m['thresholds']['modere']:.3f} et {m['thresholds']['eleve']:.3f}).",
          "", "## Variables les plus utiles (importance par permutation, PR-AUC, test)", "",
          "| Variable | Baisse de PR-AUC |", "|---|---:|"]
    for k, v in m["permutation_importance_top"].items():
        L.append(f"| {k} | {v:.4f} |")
    L += ["", "## Limites", "",
          "- La météo observée à l'heure programmée sert de proxy d'une prévision : en production, il faudrait des "
          "prévisions réelles (risque d'optimisme si la prévision est moins précise).",
          "- Une seule année (2013) et trois aéroports : la saisonnalité de fin d'année (test) diffère de l'été "
          "(entraînement) ; un ré-entraînement régulier serait nécessaire.",
          "- Les causes réelles des retards (contrôle aérien, rotation de l'avion précédent) ne sont pas disponibles.",
          "", "Figures : `reports/figures/roc_pr.png`, `calibration.png`, `importance.png`."]
    (settings.reports_dir / "evaluation_report.md").write_text("\n".join(L) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description="Entraîne et évalue le modèle de risque de retard.").parse_args(argv)
    setup_logging()
    m = train_and_evaluate(Settings.from_env())
    t = m["test"][m["model"]]
    print(f"Modèle retenu : {m['model']} — test ROC-AUC {t['roc_auc']:.3f}, PR-AUC {t['pr_auc']:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
