# Intégrer ce module à une plateforme aéroportuaire (Flask + SQLAlchemy + React)

Ce document est **conceptuel**. Il ne s'appuie sur aucun code ni aucune donnée de l'ONDA : il décrit comment un module
de ce type se brancherait sur une plateforme construite avec la même pile que celle du stage
(SPA React sur API REST Flask, SQLAlchemy, authentification JWT).

## 1. Côté backend

- Le module expose un **blueprint Flask** (`aeroops.api.api`, préfixe `/api`) : il s'enregistre dans une application
  existante avec `app.register_blueprint(...)`, en changeant le préfixe (`/api/ponctualite`) pour éviter les collisions.
- L'accès aux données passe par SQLAlchemy : remplacer l'URI SQLite par celle de la base de la plateforme.
- Les endpoints de lecture peuvent être protégés par le même décorateur JWT que le reste de la plateforme ; le rôle
  « admin » existant donnerait accès au rechargement du modèle.

## 2. Contrat de données (table de vols minimale)

| Champ | Type | Obligatoire | Usage |
|---|---|---|---|
| date du vol | date | oui | partition temporelle, KPI journaliers |
| compagnie (code) | texte | oui | KPI, variable du modèle |
| numéro de vol | entier/texte | oui | clé naturelle |
| aéroport d'origine / de destination (code IATA ou OACI) | texte | oui | KPI, variable du modèle |
| heure de départ programmée (locale) | horodatage | oui | variable du modèle, charge horaire |
| heure de départ réelle | horodatage | non (NULL si annulé) | cible (retard), OTP |
| statut annulé | booléen | oui | cible |
| immatriculation de l'avion | texte | non | âge de l'avion |
| distance | numérique | non | variable du modèle (sinon dérivée des coordonnées) |

Météo : observations ou prévisions horaires par aéroport (température, humidité, vent, rafales, précipitations,
visibilité, pression), jointes sur (aéroport, heure).

## 3. Côté frontend

- Le tableau de bord est une application React autonome ; ses composants (KPI, graphiques Recharts, table des vols à
  risque) peuvent devenir une page du tableau de bord d'administration existant.
- Les appels passent par `/api/...` : seule l'URL de base change.

## 4. Étapes pour un vrai déploiement

1. Adapter `transform.py` au schéma réel (le contrat ci-dessus) et rejouer les 17 règles de qualité.
2. Ré-entraîner et ré-évaluer sur les données locales (découpage temporel), recalibrer les seuils de risque.
3. Planifier l'ETL (quotidien) et le ré-entraînement (mensuel), surveiller la dérive et la calibration.
4. Valider l'usage avec les équipes opérations (quels seuils déclenchent une action).
