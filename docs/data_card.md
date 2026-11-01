# Fiche données

## Source

- **nycflights13** (Hadley Wickham, package R, licence **CC0**), récupéré au format CSV depuis le miroir **Rdatasets**
  (raw.githubusercontent.com/vincentarelbundock/Rdatasets). Données de vols issues du **US Bureau of Transportation
  Statistics** (Airline On-Time Performance), météo des stations ASOS des trois aéroports.
- Provenance, tailles et empreintes SHA-256 : `data/raw/SOURCES.md` et `data/raw/manifest.json`.

| Fichier | Lignes | Contenu |
|---|---:|---|
| flights.csv | 336 776 | un vol programmé au départ de EWR, JFK ou LGA en 2013 |
| weather.csv | 26 115 | observation horaire par aéroport d'origine |
| airlines.csv | 16 | codes compagnies |
| airports.csv | 1 458 | référentiel aéroports (OpenFlights) |
| planes.csv | 3 322 | référentiel avions (registre FAA) |

## Pourquoi ces données

Les données vol par vol des aéroports marocains ne sont pas publiées en open data. nycflights13 est un jeu public,
réel, complet et documenté, idéal pour construire et évaluer honnêtement toute la chaîne. Le module est conçu pour
accepter d'autres données de vols qui respectent le contrat décrit dans `integration_onda.md`.

## Particularités connues (détectées par les règles de qualité)

- 8 255 vols sans heure de départ réelle : annulations.
- 4 codes de destination (aéroports de Porto Rico et des îles Vierges) absents du référentiel : 7 602 vols.
- Immatriculations non appariées (notamment deux compagnies qui déclarent des numéros de flotte) : 50 094 vols.
- Une vitesse de vent de plus de 1 000 mph (erreur de capteur) : mise à NULL.
- Heures « 2400 » pour minuit : normalisées.

## Données personnelles

Aucune : les données décrivent des vols, des avions et la météo.
