"""Configuration du logging commune aux commandes en ligne."""

from __future__ import annotations

import logging
import os

_FORMAT = "%(asctime)s %(levelname)-7s %(name)s - %(message)s"


def setup_logging(level: str | int | None = None) -> None:
    """Configure le logging racine (niveau via ``AEROOPS_LOG_LEVEL``, INFO par défaut).

    Les messages de log restent en ASCII/latin-1 (pas de flèches ni de symboles
    mathématiques) pour éviter les erreurs d'encodage des consoles Windows.
    """
    chosen = level or os.environ.get("AEROOPS_LOG_LEVEL", "INFO")
    logging.basicConfig(level=chosen, format=_FORMAT, datefmt="%H:%M:%S", force=True)
    # Bibliothèques bavardes
    logging.getLogger("matplotlib").setLevel(logging.WARNING)
    logging.getLogger("PIL").setLevel(logging.WARNING)
