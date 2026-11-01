# Rapport d'évaluation — modèle de risque de retard

Projet personnel sur données publiques (nycflights13, US BTS 2013). Non affilié à l'ONDA.

## Protocole

- Cible : retard au départ ≥ 15 min **ou** vol annulé (« perturbation »).
- Variables : uniquement des informations connues avant le départ (programme, compagnie, origine, destination, distance, âge de l'avion, charge programmée de l'heure, météo à l'heure programmée utilisée comme proxy d'une prévision à court terme, taux historiques appris sur l'entraînement).
- Découpage temporel : entraînement 2013-01-01..2013-09-30 (252 484 vols), validation 2013-10-01..2013-10-31 (28 889), test 2013-11-01..2013-12-31 (55 403).
- Sélection du modèle sur la PR-AUC de validation ; le test n'est utilisé qu'une fois.

## Résultats sur le test (nov.–déc. 2013)

| Modèle | ROC-AUC | PR-AUC | Brier | Précision top 10 % | Rappel top 10 % | Lift top 10 % |
|---|---:|---:|---:|---:|---:|---:|
| Référence historique | 0.660 | 0.355 | 0.1707 | 42.8% | 18.1% | 1.81 |
| Régression logistique | 0.699 | 0.428 | 0.1628 | 54.8% | 23.2% | 2.32 |
| Gradient boosting (HGB) **(retenu)** | 0.706 | 0.448 | 0.1617 | 54.9% | 23.3% | 2.33 |

Taux de perturbation : entraînement 25.1%, validation 16.1%, test 23.6%.

## Lecture

- La ROC-AUC mesure la capacité à classer un vol perturbé avant un vol à l'heure ; la PR-AUC est plus exigeante car la classe positive est minoritaire.
- Le « top 10 % » correspond à l'usage opérationnel : surveiller en priorité les 10 % de vols les plus risqués.
- Les niveaux de risque (faible / modéré / élevé) sont fixés sur les déciles de la validation (seuils 0.240 et 0.413).

## Variables les plus utiles (importance par permutation, PR-AUC, test)

| Variable | Baisse de PR-AUC |
|---|---:|
| hist_rate_carrier_hour | 0.1028 |
| humid | 0.0881 |
| plane_age | 0.0446 |
| carrier | 0.0440 |
| dest | 0.0138 |
| pressure | 0.0130 |
| temp | 0.0109 |
| hist_rate_origin_hour | 0.0076 |
| weekday | 0.0055 |
| wind_speed | 0.0055 |
| origin | 0.0046 |
| visib | 0.0041 |

## Limites

- La météo observée à l'heure programmée sert de proxy d'une prévision : en production, il faudrait des prévisions réelles (risque d'optimisme si la prévision est moins précise).
- Une seule année (2013) et trois aéroports : la saisonnalité de fin d'année (test) diffère de l'été (entraînement) ; un ré-entraînement régulier serait nécessaire.
- Les causes réelles des retards (contrôle aérien, rotation de l'avion précédent) ne sont pas disponibles.

Figures : `reports/figures/roc_pr.png`, `calibration.png`, `importance.png`.
