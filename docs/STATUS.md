# État d'avancement (30/10/2026)

## Implémenté et testé

- Extraction avec vérification SHA-256, manifeste et `SOURCES.md`.
- 17 règles de qualité, rapport JSON + Markdown, résultats historisés (`dq_results`, `etl_runs`).
- Transformation (indicateurs de ponctualité, membres « inconnus »), chargement transactionnel idempotent, vues KPI.
- Modèle : référence, régression logistique, gradient boosting ; découpage temporel ; métriques, calibration,
  importance par permutation ; prédictions d'octobre à décembre stockées.
- Détection d'anomalies journalières + cause probable ; figure et CSV.
- API Flask (11 routes) avec validation des entrées et administration JWT.
- Tableau de bord React construit (5 onglets), vérifié dans Chromium sans erreur de console.
- 21 tests pytest (jeu synthétique isolé) : tous réussis — sortie dans `reports/test_results.txt`.
- Exécution complète sur les vraies données le 30/10/2026 (chiffres du README).

## Non fait / pistes d'amélioration

- Explications locales exactes (SHAP) à la place des facteurs de contexte par règles.
- Prévisions météo réelles au lieu des observations.
- Ré-entraînement planifié, suivi de dérive, conteneurisation Docker, CI (GitHub Actions).
- Authentification JWT sur tous les endpoints ; journalisation des accès.
- Chargement incrémental pour des volumes plus importants ; PostgreSQL.

## À configurer par l'utilisateur

- Variable `AEROOPS_ADMIN_SECRET` (optionnelle) pour tester l'endpoint d'administration.
- Pour modifier le tableau de bord : Node.js 18+ puis `cd dashboard && npm install && npm run build`.
