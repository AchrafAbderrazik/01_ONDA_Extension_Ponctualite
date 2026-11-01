"""Lance l'API : ``python -m aeroops.api [--port 5050]``. Option ``--token`` : génère un jeton admin."""

from __future__ import annotations

import argparse
import os
from datetime import datetime, timedelta, timezone

import jwt

from ..logging_utils import setup_logging
from . import create_app


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="API du module Ponctualité")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5050)
    parser.add_argument("--token", action="store_true", help="Affiche un jeton admin (AEROOPS_ADMIN_SECRET requis).")
    args = parser.parse_args(argv)
    setup_logging()
    if args.token:
        secret = os.environ.get("AEROOPS_ADMIN_SECRET")
        if not secret:
            print("Définir d'abord la variable d'environnement AEROOPS_ADMIN_SECRET.")
            return 1
        exp = datetime.now(timezone.utc) + timedelta(hours=1)
        print(jwt.encode({"sub": "admin", "role": "admin", "exp": exp}, secret, algorithm="HS256"))
        return 0
    create_app().run(host=args.host, port=args.port, debug=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
