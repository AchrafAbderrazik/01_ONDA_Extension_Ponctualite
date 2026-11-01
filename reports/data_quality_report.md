# Rapport de qualité des données

Exécution ETL : `2026-10-30T17:23:02.397370Z_5808496b615421d5` — généré automatiquement par `python -m aeroops.etl`.

| Règle | Table | Contrôle | Gravité | Lignes contrôlées | Violations | Taux | Action |
|---|---|---|---|---:|---:|---:|---|
| R01 | flights | Colonnes obligatoires présentes (17) | CRITIQUE | 17 | 0 | 0.00% | Aucune |
| R01 | weather | Colonnes obligatoires présentes (15) | CRITIQUE | 15 | 0 | 0.00% | Aucune |
| R01 | airlines | Colonnes obligatoires présentes (2) | CRITIQUE | 2 | 0 | 0.00% | Aucune |
| R01 | airports | Colonnes obligatoires présentes (8) | CRITIQUE | 8 | 0 | 0.00% | Aucune |
| R01 | planes | Colonnes obligatoires présentes (8) | CRITIQUE | 8 | 0 | 0.00% | Aucune |
| R02 | flights | Valeurs numériques non convertibles | AVERTISSEMENT | 4 041 312 | 0 | 0.00% | Valeur mise à NULL |
| R02 | weather | Valeurs numériques non convertibles | AVERTISSEMENT | 339 495 | 0 | 0.00% | Valeur mise à NULL |
| R02 | planes | Valeurs numériques non convertibles | AVERTISSEMENT | 9 966 | 0 | 0.00% | Valeur mise à NULL |
| R03 | flights | Clés métier renseignées (date, compagnie, vol, origine, destination, horaire) | CRITIQUE | 336 776 | 0 | 0.00% | Lignes exclues |
| R04 | flights | Unicité de la clé naturelle year+month+day+carrier+flight+origin+sched_dep_time | AVERTISSEMENT | 336 776 | 0 | 0.00% | Doublons exclus (première occurrence conservée) |
| R05 | flights | Horaire programmé HHMM valide | CRITIQUE | 336 776 | 0 | 0.00% | Lignes exclues |
| R06 | flights | Heure réelle 2400 (minuit) normalisée | INFO | 336 776 | 29 | 0.01% | 2400 converti en 0000 du jour suivant |
| R07 | flights | Vols sans heure de départ réelle (annulés) | INFO | 336 776 | 8 255 | 2.45% | Conservés, marqués cancelled=1 (comptent comme perturbation) |
| R08 | flights | Distance strictement positive | AVERTISSEMENT | 336 776 | 0 | 0.00% | Lignes exclues |
| R09 | flights | Retard au départ dans [-120 ; 1 500] min | AVERTISSEMENT | 328 521 | 0 | 0.00% | Conservé et signalé |
| R10 | flights | Compagnie présente dans le référentiel airlines | CRITIQUE | 336 776 | 0 | 0.00% | Lignes exclues |
| R11 | flights | Destination présente dans le référentiel airports (4 codes absents) | AVERTISSEMENT | 336 776 | 7 602 | 2.26% | Aéroport ajouté comme membre « inconnu » de dim_airport |
| R12 | flights | Immatriculation présente dans le référentiel planes | AVERTISSEMENT | 334 264 | 50 094 | 14.99% | Avion ajouté comme membre « inconnu » de dim_aircraft (âge NULL) |
| R13 | flights | Observation météo disponible à l'heure programmée | AVERTISSEMENT | 336 776 | 1 556 | 0.46% | Variables météo NULL (imputées au moment de l'entraînement) |
| R14 | weather | Unicité (origine, heure) des observations météo | AVERTISSEMENT | 26 115 | 0 | 0.00% | Doublons exclus |
| R15 | weather | Vitesse du vent ≤ 150 mph | AVERTISSEMENT | 26 111 | 1 | 0.00% | Valeur mise à NULL |
| R16 | planes | Année de construction entre 1950 et 2013 | AVERTISSEMENT | 3 252 | 0 | 0.00% | Valeur mise à NULL |
| R17 | planes | Année de construction renseignée | INFO | 3 322 | 70 | 2.11% | Âge de l'avion NULL |
