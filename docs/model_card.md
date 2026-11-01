# Fiche modèle — risque de perturbation au départ

| Élément | Valeur |
|---|---|
| Tâche | Classification binaire : départ ≥ 15 min après l'horaire **ou** annulation |
| Modèle retenu | `HistGradientBoostingClassifier` (scikit-learn), variables catégorielles natives |
| Concurrents | Référence (taux historique compagnie × heure), régression logistique (one-hot + standardisation) |
| Données | nycflights13 (US BTS), 336 776 vols de 2013 au départ de EWR, JFK, LGA |
| Découpage | Entraînement janv.–sept. (252 484), validation oct. (28 889), test nov.–déc. (55 403) — temporel, sans mélange |
| Sélection | PR-AUC de validation (classe positive minoritaire) |
| Version | 1.0.0 — artefact `models/model.joblib` |

## Variables (toutes connues avant le départ)

- Programme : heure programmée, jour de la semaine, mois, distance, compagnie, origine, destination.
- Avion : âge (année de construction ; NULL si l'avion n'est pas référencé).
- Charge : nombre de départs programmés à la même origine dans la même heure (le programme est connu à l'avance).
- Météo à l'heure programmée (température, humidité, vent, rafales, précipitations, visibilité, pression), utilisée comme
  **proxy d'une prévision à court terme**.
- Taux historiques lissés (m-estimate, m = 50) : compagnie × heure, origine × heure, liaison, compagnie × mois —
  **appris sur la période d'entraînement uniquement**.

Variables exclues car connues seulement après le vol : `dep_time`, `dep_delay`, `arr_*`, `air_time`, `cancelled`.
Un test automatique vérifie qu'aucune n'entre dans le modèle.

## Performances (test)

| Modèle | ROC-AUC | PR-AUC | Brier | Précision top 10 % | Rappel top 10 % |
|---|---:|---:|---:|---:|---:|
| Référence historique | 0,660 | 0,355 | 0,1707 | 42,8 % | 18,1 % |
| Régression logistique | 0,699 | 0,428 | 0,1628 | 54,8 % | 23,2 % |
| HGB (retenu) | 0,706 | 0,448 | 0,1617 | 54,9 % | 23,3 % |

Calibration : `reports/figures/calibration.png`. Niveaux de risque fixés sur la validation : « modéré » au-delà du
7e décile (p ≥ 0,240), « élevé » au-delà du 9e décile (p ≥ 0,413).

## Variables les plus utiles (permutation, baisse de PR-AUC sur 20 000 vols du test)

1. taux historique compagnie × heure (0,103) · 2. humidité (0,088) · 3. âge de l'avion (0,045) · 4. compagnie (0,044)
· 5. destination (0,014) · 6. pression (0,013) · 7. température (0,011).

Lecture : le contexte « structurel » (compagnie, créneau, avion) et la météo dominent ; l'humidité agit comme
indicateur de pluie, brouillard ou neige.

## Usage prévu et hors périmètre

- Prévu : prioriser la surveillance des vols d'une journée, alimenter un tableau de bord opérationnel.
- Hors périmètre : décision automatique (annulation, réaffectation), toute utilisation sur un autre réseau sans
  ré-entraînement et ré-évaluation.

## Limites et risques

- Écart de distribution : validation (octobre, 16 % de perturbations) moins perturbée que le test (24 %).
- La météo observée remplace une prévision : biais optimiste possible.
- Une seule année, trois aéroports ; pas d'information sur la rotation de l'avion ni sur le contrôle aérien.
- À surveiller en production : dérive des taux de perturbation, calibration mensuelle, ré-entraînement planifié.
