"""Configuration centralisée : chemins, constantes métier et découpage temporel.

Tous les chemins peuvent être surchargés par variables d'environnement, ce qui
permet aux tests d'utiliser des répertoires temporaires sans toucher aux
artefacts du projet.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

# --- Constantes métier -----------------------------------------------------

#: Seuil standard (DOT américain) : un vol est « à l'heure » s'il part moins de
#: 15 minutes après l'horaire programmé.
DELAY_THRESHOLD_MIN = 15

#: Aéroports d'origine présents dans le jeu de données.
NYC_ORIGINS = ("EWR", "JFK", "LGA")

#: Fuseau horaire local des données (heures locales, sans conversion UTC).
LOCAL_TZ = "America/New_York"

#: Année des données.
DATA_YEAR = 2013

# --- Découpage temporel du modèle (aucun mélange aléatoire) -----------------
TRAIN_START = date(2013, 1, 1)
TRAIN_END = date(2013, 9, 30)
VALID_START = date(2013, 10, 1)
VALID_END = date(2013, 10, 31)
TEST_START = date(2013, 11, 1)
TEST_END = date(2013, 12, 31)


def _detect_root() -> Path:
    """Retourne la racine du projet (dossier contenant ``pyproject.toml``)."""
    env = os.environ.get("AEROOPS_HOME")
    if env:
        return Path(env).resolve()
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").exists() and (parent / "src").exists():
            return parent
    return Path.cwd().resolve()


PROJECT_ROOT = _detect_root()


@dataclass(frozen=True)
class Settings:
    """Ensemble des chemins utilisés par l'ETL, l'entraînement et l'API."""

    root: Path
    raw_dir: Path
    db_path: Path
    models_dir: Path
    reports_dir: Path
    dashboard_dist: Path

    @classmethod
    def from_env(cls, root: Path | str | None = None) -> "Settings":
        base = Path(root).resolve() if root else PROJECT_ROOT

        def _p(var: str, default: Path) -> Path:
            value = os.environ.get(var)
            return Path(value).resolve() if value else default

        return cls(
            root=base,
            raw_dir=_p("AEROOPS_RAW_DIR", base / "data" / "raw"),
            db_path=_p("AEROOPS_DB_PATH", base / "data" / "warehouse" / "aeroops.db"),
            models_dir=_p("AEROOPS_MODELS_DIR", base / "models"),
            reports_dir=_p("AEROOPS_REPORTS_DIR", base / "reports"),
            dashboard_dist=_p("AEROOPS_DASHBOARD_DIST", base / "dashboard" / "dist"),
        )

    @classmethod
    def for_directory(cls, base: Path | str) -> "Settings":
        """Construit une configuration isolée dans ``base`` (utilisé par les tests)."""
        base = Path(base).resolve()
        return cls(
            root=base,
            raw_dir=base / "data" / "raw",
            db_path=base / "data" / "warehouse" / "aeroops.db",
            models_dir=base / "models",
            reports_dir=base / "reports",
            dashboard_dist=base / "dashboard" / "dist",
        )

    @property
    def figures_dir(self) -> Path:
        return self.reports_dir / "figures"

    @property
    def model_path(self) -> Path:
        return self.models_dir / "model.joblib"

    @property
    def metrics_path(self) -> Path:
        return self.models_dir / "metrics.json"

    def ensure_dirs(self) -> None:
        for path in (self.raw_dir, self.db_path.parent, self.models_dir, self.figures_dir):
            path.mkdir(parents=True, exist_ok=True)
