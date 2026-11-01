"""Orchestrateur ETL : extraction -> contrôles qualité -> transformation -> chargement.

Usage : ``python -m aeroops.etl [--no-download]``
"""

from __future__ import annotations

import argparse
import hashlib
import logging
from datetime import datetime, timezone

from .config import Settings
from .extract import ensure_raw_data, read_raw_tables
from .load import connect, init_schema, load_star_schema
from .logging_utils import setup_logging
from .transform import transform
from .validate import blocking, run_rules, write_report

log = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_etl(settings: Settings, *, download_missing: bool = True, verify_checksums: bool = True) -> dict:
    """Exécute l'ETL complet et retourne un résumé (identifiant, volumes, règles)."""
    settings.ensure_dirs()
    sources = ensure_raw_data(settings.raw_dir, download_missing=download_missing, verify=verify_checksums)
    fingerprint = hashlib.sha256("".join(sources[k].sha256 for k in sorted(sources)).encode()).hexdigest()[:16]
    run_id = f"{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%fZ')}_{fingerprint}"
    started = _now()
    conn = connect(settings.db_path)
    init_schema(conn)
    with conn:
        conn.execute("INSERT INTO etl_runs(run_id, started_at, status, source_fingerprint) VALUES (?,?,?,?)",
                     (run_id, started, "RUNNING", fingerprint))
    try:
        tables = read_raw_tables(settings.raw_dir)
        results = run_rules(tables)
        stop = blocking(results)
        if stop:
            raise RuntimeError("Règle bloquante violée : " + "; ".join(f"{r.rule_id}/{r.table}" for r in stop))
        star = transform(tables)
        counts = load_star_schema(conn, star)
        with conn:
            conn.executemany(
                "INSERT INTO dq_results VALUES (?,?,?,?,?,?,?,?)",
                [(run_id, r.rule_id, r.table, r.description, r.severity, r.checked, r.violations, r.action)
                 for r in results])
            conn.execute("UPDATE etl_runs SET finished_at=?, status='SUCCESS', rows_flight=?, rows_weather=? "
                         "WHERE run_id=?", (_now(), counts["fact_flight"], counts["fact_weather_hourly"], run_id))
        write_report(results, settings.reports_dir, run_id)
        log.info("ETL termine (%s) : %s", run_id, counts)
        return {"run_id": run_id, "counts": counts, "rules": len(results),
                "violations": {f"{r.rule_id}:{r.table}": r.violations for r in results if r.violations}}
    except Exception as exc:
        with conn:
            conn.execute("UPDATE etl_runs SET finished_at=?, status='FAILED', message=? WHERE run_id=?",
                         (_now(), str(exc)[:500], run_id))
        raise
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ETL ponctualité : CSV publics -> entrepôt SQLite.")
    parser.add_argument("--no-download", action="store_true")
    args = parser.parse_args(argv)
    setup_logging()
    summary = run_etl(Settings.from_env(), download_missing=not args.no_download)
    print(f"ETL OK — run {summary['run_id']}")
    for table, n in summary["counts"].items():
        print(f"  {table:22s} {n:>8d} lignes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
