# Sources des données brutes

Fichiers CSV publics du package R **nycflights13** (Hadley Wickham, licence **CC0**),
récupérés depuis le miroir **Rdatasets** (Vincent Arel-Bundock) sur GitHub.
Les CSV Rdatasets contiennent une première colonne d'index `rownames`.

Citation : Wickham H. *nycflights13: Flights that Departed NYC in 2013*. Package R,
https://github.com/tidyverse/nycflights13. Données de vols : US Bureau of Transportation
Statistics (BTS/RITA, TranStats « Airline On-Time Performance »).

Ce fichier est généré par `python -m aeroops.extract` à partir de `manifest.json`.

| Fichier | Contenu | Lignes | Taille (octets) | Récupéré le (UTC) | SHA-256 |
|---|---|---:|---:|---|---|
| [`flights.csv`](https://raw.githubusercontent.com/vincentarelbundock/Rdatasets/master/csv/nycflights13/flights.csv) | Vols au départ de EWR, JFK et LGA en 2013 (US BTS / RITA, table On-Time) | 336 776 | 33 206 996 | 2026-10-30T17:12:38Z | `b791a2590c9167aa0bd3cb45af3f64101180878cf088c183eae4011e3a654f42` |
| [`weather.csv`](https://raw.githubusercontent.com/vincentarelbundock/Rdatasets/master/csv/nycflights13/weather.csv) | Observations météo horaires des 3 aéroports (ASOS, Iowa Environmental Mesonet) | 26 115 | 2 391 865 | 2026-10-30T17:12:39Z | `e69580cc3c18070692b6bf2f52e890803a313507c23283b15f06dbbae86451cf` |
| [`airlines.csv`](https://raw.githubusercontent.com/vincentarelbundock/Rdatasets/master/csv/nycflights13/airlines.csv) | Référentiel des codes compagnies (US BTS) | 16 | 434 | 2026-10-30T17:12:39Z | `5c9f0c947dca4a2b7e009c9dc86b96fc637e45bf39a034bffb413e84b98b08f6` |
| [`airports.csv`](https://raw.githubusercontent.com/vincentarelbundock/Rdatasets/master/csv/nycflights13/airports.csv) | Référentiel des aéroports (OpenFlights, téléchargé le 2014-06-27 par l'auteur du package) | 1 458 | 110 488 | 2026-10-30T17:12:39Z | `f1c5dba736fa36ecffa93cd0556b9b920a4b1a5e27bbc3ed417f05fa42edf3d6` |
| [`planes.csv`](https://raw.githubusercontent.com/vincentarelbundock/Rdatasets/master/csv/nycflights13/planes.csv) | Référentiel des avions (registre FAA ; AA et MQ déclarent des numéros de flotte non appariables) | 3 322 | 255 972 | 2026-10-30T17:12:39Z | `95a3cd5a64dc1c4ae0c002e6aec457084455ea5835d73368114285f79a66a65c` |

## Pourquoi des données américaines ?

Les données de ponctualité vol par vol des aéroports marocains ne sont pas publiées
en open data. Le jeu nycflights13 est un standard public, réel et complet (336 776 vols,
météo horaire, référentiels) qui permet de construire et d'évaluer honnêtement la chaîne
complète. Le contrat de données décrit dans `docs/integration_onda.md` indique comment
brancher une table de vols équivalente provenant d'un autre opérateur.

## Licence

nycflights13 est distribué sous licence CC0 (domaine public). Les données de vols
proviennent du US Bureau of Transportation Statistics (données publiques fédérales).
