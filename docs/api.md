# API REST — référence

Base : `http://127.0.0.1:5050/api` (lancer `python -m aeroops.api`). Réponses JSON en UTF-8.
Erreurs : `400` (entrée invalide, message explicite), `404` (ressource absente), `401/403` (jeton), `503` (service indisponible).

| Méthode | Chemin | Paramètres | Rôle |
|---|---|---|---|
| GET | `/health` | — | état de la base et du modèle |
| GET | `/kpis` | `airport`, `carrier`, `month` (1–12) | KPI globaux + par aéroport + par compagnie |
| GET | `/kpis/timeseries` | `granularity` = day \| month, filtres ci-dessus | série temporelle (+ indicateur d'anomalie par jour) |
| GET | `/delays/by-hour` | filtres | KPI par heure programmée |
| GET | `/anomalies` | `airport`, `limit` (≤ 500) | journées anormales triées par z robuste |
| GET | `/flights/risk` | `date` (obligatoire, oct.–déc. 2013), `airport`, `limit` | vols triés par probabilité, avec facteurs |
| POST | `/predict` | JSON : `carrier`, `origin`, `dest`, `date`, `time` ; option `distance`, `weather{...}` | probabilité, niveau, facteurs, hypothèses |
| GET | `/quality` | — | dernière exécution ETL et ses règles |
| GET | `/model/metrics` | — | métriques d'évaluation |
| GET | `/model/figures/<nom>` | liste blanche de 4 figures | figures PNG |
| POST | `/admin/reload-model` | en-tête `Authorization: Bearer <JWT>` (rôle admin) | recharge le modèle |

## Exemples (réponses réelles, extraits)

```bash
curl "http://127.0.0.1:5050/api/kpis?airport=JFK"
# {"by_airport": [{"airport": "JFK", "avg_dep_delay": 12.11, "cancel_rate": 0.0167, "cancelled": 1863,
#   "disruption_rate": 0.2265, "flights": 111279, "otp15": 0.7866}], ...}

curl -X POST http://127.0.0.1:5050/api/predict -H "Content-Type: application/json" \
     -d '{"carrier":"UA","origin":"EWR","dest":"ORD","date":"2013-12-05","time":"18:30"}'
# {"probability": 0.78, "risk_level": "élevé",
#  "factors": ["Créneau compagnie × heure historiquement perturbé (38% contre 25% en moyenne)",
#              "Départ en fin de journée (accumulation des retards)"],
#  "assumptions": ["âge de l'avion : médiane d'entraînement", ...], "model": "Gradient boosting (HGB)"}

curl "http://127.0.0.1:5050/api/kpis?month=13"
# 400 {"error": "month doit être un entier entre 1 et 12"}
```

La probabilité exacte dépend du modèle entraîné localement (même graine, mêmes données : résultats reproductibles).

## Administration (JWT)

```bash
# Windows : set AEROOPS_ADMIN_SECRET=une-longue-phrase-secrete     Linux : export AEROOPS_ADMIN_SECRET=...
python -m aeroops.api --token          # affiche un jeton admin valable 1 h
curl -X POST http://127.0.0.1:5050/api/admin/reload-model -H "Authorization: Bearer <jeton>"
```

Sans `AEROOPS_ADMIN_SECRET`, l'endpoint répond 503 : aucun secret n'est codé en dur.
