"""Extraction : téléchargement des CSV publics (si absents) et contrôle d'intégrité.

Source : miroir CSV « Rdatasets » du package R ``nycflights13`` (licence CC0).
Chaque fichier est vérifié par empreinte SHA-256 par rapport au manifeste
``data/raw/manifest.json`` ; une différence est bloquante (dérive ou corruption
de la source) sauf si l'on demande explicitement la mise à jour du manifeste.

Usage : ``python -m aeroops.extract [--update-manifest]``
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import shutil
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from .config import Settings
from .logging_utils import setup_logging

log = logging.getLogger(__name__)

BASE_URL = "https://raw.githubusercontent.com/vincentarelbundock/Rdatasets/master/csv/nycflights13"
DATASETS: tuple[str, ...] = ("flights", "weather", "airlines", "airports", "planes")
MANIFEST_NAME = "manifest.json"

DATASET_DESCRIPTIONS = {
    "flights": "Vols au départ de EWR, JFK et LGA en 2013 (US BTS / RITA, table On-Time)",
    "weather": "Observations météo horaires des 3 aéroports (ASOS, Iowa Environmental Mesonet)",
    "airlines": "Référentiel des codes compagnies (US BTS)",
    "airports": "Référentiel des aéroports (OpenFlights, téléchargé le 2014-06-27 par l'auteur du package)",
    "planes": "Référentiel des avions (registre FAA ; AA et MQ déclarent des numéros de flotte non appariables)",
}


class ChecksumError(RuntimeError):
    """Empreinte SHA-256 différente de celle du manifeste."""


@dataclass
class SourceFile:
    name: str
    filename: str
    url: str
    sha256: str
    bytes: int
    rows: int
    retrieved_at: str


def url_for(name: str) -> str:
    return f"{BASE_URL}/{name}.csv"


def sha256_of(path: Path, chunk_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def count_records(path: Path) -> int:
    """Nombre d'enregistrements CSV (hors en-tête), en respectant les guillemets."""
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        next(reader, None)
        return sum(1 for _ in reader)


def download_file(url: str, dest: Path, *, timeout: int = 120, retries: int = 3) -> None:
    """Télécharge ``url`` vers ``dest`` de façon atomique (fichier .part puis renommage)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            log.info("Telechargement %s (tentative %d/%d)", url, attempt, retries)
            with urllib.request.urlopen(url, timeout=timeout) as resp, open(tmp, "wb") as fh:
                shutil.copyfileobj(resp, fh, length=1 << 20)
            tmp.replace(dest)
            return
        except (urllib.error.URLError, TimeoutError, OSError) as exc:  # réseau ou disque
            last_error = exc
            log.warning("Echec du telechargement (%s) : %s", url, exc)
            time.sleep(2 * attempt)
    if tmp.exists():
        tmp.unlink()
    raise RuntimeError(f"Impossible de télécharger {url} : {last_error}")


def load_manifest(raw_dir: Path) -> dict[str, dict]:
    path = raw_dir / MANIFEST_NAME
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    return {entry["name"]: entry for entry in data.get("files", [])}


def save_manifest(raw_dir: Path, files: dict[str, SourceFile]) -> Path:
    path = raw_dir / MANIFEST_NAME
    payload = {
        "description": "Empreintes des fichiers sources publics (nycflights13 via Rdatasets).",
        "licence": "CC0 (package nycflights13, H. Wickham)",
        "files": [asdict(files[name]) for name in DATASETS if name in files],
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    return path


def write_sources_md(raw_dir: Path, files: dict[str, SourceFile]) -> Path:
    """Génère ``SOURCES.md`` (provenance, licence, volumétrie, empreintes)."""
    lines = [
        "# Sources des données brutes",
        "",
        "Fichiers CSV publics du package R **nycflights13** (Hadley Wickham, licence **CC0**),",
        "récupérés depuis le miroir **Rdatasets** (Vincent Arel-Bundock) sur GitHub.",
        "Les CSV Rdatasets contiennent une première colonne d'index `rownames`.",
        "",
        "Citation : Wickham H. *nycflights13: Flights that Departed NYC in 2013*. Package R,",
        "https://github.com/tidyverse/nycflights13. Données de vols : US Bureau of Transportation",
        "Statistics (BTS/RITA, TranStats « Airline On-Time Performance »).",
        "",
        "Ce fichier est généré par `python -m aeroops.extract` à partir de `manifest.json`.",
        "",
        "| Fichier | Contenu | Lignes | Taille (octets) | Récupéré le (UTC) | SHA-256 |",
        "|---|---|---:|---:|---|---|",
    ]
    for name in DATASETS:
        if name not in files:
            continue
        f = files[name]
        lines.append(
            f"| [`{f.filename}`]({f.url}) | {DATASET_DESCRIPTIONS[name]} | {_fr_int(f.rows)} | "
            f"{_fr_int(f.bytes)} | {f.retrieved_at} | `{f.sha256}` |"
        )
    lines += [
        "",
        "## Pourquoi des données américaines ?",
        "",
        "Les données de ponctualité vol par vol des aéroports marocains ne sont pas publiées",
        "en open data. Le jeu nycflights13 est un standard public, réel et complet (336 776 vols,",
        "météo horaire, référentiels) qui permet de construire et d'évaluer honnêtement la chaîne",
        "complète. Le contrat de données décrit dans `docs/integration_onda.md` indique comment",
        "brancher une table de vols équivalente provenant d'un autre opérateur.",
        "",
        "## Licence",
        "",
        "nycflights13 est distribué sous licence CC0 (domaine public). Les données de vols",
        "proviennent du US Bureau of Transportation Statistics (données publiques fédérales).",
        "",
    ]
    path = raw_dir / "SOURCES.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _fr_int(value: int) -> str:
    """Entier formaté à la française (espace fine insécable comme séparateur de milliers)."""
    return f"{value:,}".replace(",", " ")


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ensure_raw_data(
    raw_dir: Path,
    *,
    download_missing: bool = True,
    verify: bool = True,
    update_manifest: bool = False,
) -> dict[str, SourceFile]:
    """Garantit la présence des 5 fichiers sources et vérifie leurs empreintes.

    - fichier absent : téléchargé (si ``download_missing``) ;
    - empreinte différente du manifeste : ``ChecksumError`` (sauf ``update_manifest``) ;
    - manifeste absent : créé, avec ``SOURCES.md``.
    """
    raw_dir = Path(raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest(raw_dir)
    results: dict[str, SourceFile] = {}

    for name in DATASETS:
        path = raw_dir / f"{name}.csv"
        downloaded = False
        if not path.exists():
            if not download_missing:
                raise FileNotFoundError(f"Fichier source manquant : {path}")
            download_file(url_for(name), path)
            downloaded = True
        digest = sha256_of(path)
        expected = manifest.get(name, {}).get("sha256")
        if verify and expected and digest != expected and not update_manifest:
            raise ChecksumError(
                f"{name}.csv : empreinte SHA-256 inattendue (attendu {expected[:12]}..., "
                f"obtenu {digest[:12]}...). Source modifiée ou fichier corrompu ; relancer avec "
                "--update-manifest après vérification."
            )
        if name in manifest and not downloaded and digest == expected:
            retrieved_at = manifest[name].get("retrieved_at", _now_utc())
        else:
            retrieved_at = _now_utc()
        results[name] = SourceFile(
            name=name,
            filename=path.name,
            url=url_for(name),
            sha256=digest,
            bytes=path.stat().st_size,
            rows=count_records(path),
            retrieved_at=retrieved_at,
        )
        log.info("%s.csv : %d lignes, sha256=%s...", name, results[name].rows, digest[:12])

    if update_manifest or set(manifest) != set(DATASETS):
        save_manifest(raw_dir, results)
        write_sources_md(raw_dir, results)
        log.info("Manifeste et SOURCES.md mis a jour dans %s", raw_dir)
    return results


def read_raw_tables(raw_dir: Path) -> dict[str, "pd.DataFrame"]:
    """Lit les 5 CSV **en texte brut** (aucune conversion implicite).

    Le typage est réalisé ensuite par la validation, qui compte les valeurs non
    conformes au lieu de les masquer silencieusement.
    """
    import pandas as pd  # import local : extract reste utilisable sans pandas

    tables = {}
    for name in DATASETS:
        path = Path(raw_dir) / f"{name}.csv"
        tables[name] = pd.read_csv(path, dtype=str, keep_default_na=True, na_values=["NA", ""])
        log.info("Lecture %s : %d lignes x %d colonnes", path.name, *tables[name].shape)
    return tables


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Téléchargement et vérification des données brutes.")
    parser.add_argument("--raw-dir", type=Path, default=None, help="Dossier des CSV bruts.")
    parser.add_argument("--update-manifest", action="store_true", help="Accepter et enregistrer de nouvelles empreintes.")
    parser.add_argument("--no-download", action="store_true", help="Échouer si un fichier manque.")
    args = parser.parse_args(argv)
    setup_logging()
    settings = Settings.from_env()
    raw_dir = args.raw_dir or settings.raw_dir
    ensure_raw_data(raw_dir, download_missing=not args.no_download, update_manifest=args.update_manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
