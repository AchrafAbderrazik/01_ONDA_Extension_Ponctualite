#!/usr/bin/env bash
# Chaîne complète : ETL -> entraînement -> anomalies -> tests -> API (http://127.0.0.1:5050)
set -euo pipefail
cd "$(dirname "$0")"
export PYTHONPATH=src
python -m aeroops.etl
python -m aeroops.train
python -m aeroops.anomalies
python -m pytest -q | tee reports/test_results.txt
echo "Tableau de bord : http://127.0.0.1:5050  (Ctrl+C pour arrêter)"
python -m aeroops.api
