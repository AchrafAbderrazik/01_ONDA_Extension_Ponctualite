# Décisions techniques (et alternatives envisagées)

| Décision | Pourquoi | Alternatives écartées |
|---|---|---|
| Données publiques nycflights13 | Réelles, complètes (vols + météo + référentiels), licence CC0, évaluation honnête possible | Données synthétiques (résultats non crédibles) ; données de l'ONDA (confidentielles, non disponibles) |
| SQLite + schéma en étoile | Aucun serveur à installer, démonstration locale ; le schéma (faits / dimensions) est celui d'un entrepôt | PostgreSQL (meilleur en production, plus lourd pour une démo) ; fichiers Parquet (pas de SQL relationnel ni de contraintes) |
| Rafraîchissement complet transactionnel | Idempotent et simple : relancer l'ETL donne le même état ; rollback en cas d'erreur | Chargement incrémental / upsert (utile au-delà de quelques millions de lignes) |
| Membres « inconnus » dans les dimensions | Garder 100 % des vols tout en respectant les clés étrangères | Supprimer les vols (perte de 15 % des données) ; désactiver les clés étrangères |
| Règles de qualité codées en Python | Lisibles, testées, rapport chiffré | Great Expectations / dbt tests (plus d'outillage que nécessaire ici) |
| Découpage temporel train / validation / test | Reproduit l'usage réel (prédire le futur), évite la fuite | Validation croisée aléatoire (optimiste sur des données temporelles) |
| Encodage cible lissé appris sur l'entraînement | Capture le « contexte » compagnie × heure sans fuite | One-hot de toutes les combinaisons (très creux) |
| HistGradientBoosting | Rapide, gère les NaN et les catégories, souvent le meilleur sur des données tabulaires | XGBoost/LightGBM (dépendances en plus, gain attendu faible) ; réseau de neurones (inadapté ici) |
| Sélection sur la PR-AUC | Classe positive minoritaire : la PR-AUC est plus exigeante que la ROC-AUC | Exactitude (trompeuse avec 75 % de vols à l'heure) |
| Seuils de risque par déciles de validation | Lien direct avec la capacité de surveillance (top 10 %) | Seuil fixe à 0,5 (sans sens opérationnel) |
| Anomalies : médiane / MAD sur 28 jours passés | Robuste aux pics, n'utilise aucune information future | Moyenne / écart-type (sensibles aux pics) ; Isolation Forest (moins explicable) |
| Facteurs de contexte par règles | Explication compréhensible, honnête sur sa nature | SHAP (plus exact, dépendance lourde) — piste d'amélioration |
| Flask + blueprint | Même pile que la plateforme du stage, intégration naturelle | FastAPI (choisi dans l'autre projet, pour comparer) |
| React (Vite) + Recharts, build servi par Flask | Cohérent avec la plateforme ; l'utilisateur n'a pas besoin de Node | Streamlit (plus rapide à écrire, moins proche d'une vraie application web) |
| JWT uniquement sur l'administration | Démonstration locale ; montre le mécanisme sans alourdir la lecture | JWT partout (à faire pour une vraie mise en production) |
