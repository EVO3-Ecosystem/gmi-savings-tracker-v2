#!/usr/bin/env python3
"""Load the exported dashboard marts into a local Postgres database.

Opt-in demonstration (decision register #12): DuckDB (data/md_transparency.duckdb) stays the
default store; this script mirrors the published marts into Postgres, e.g. for BI tools that
expect a Postgres connection.

Sources (pick one):
  --csv     the checked export snapshot in data/export/latest/*.csv (default)
  --duckdb  the mart.* tables of data/md_transparency.duckdb, opened read-only

Connection comes from the DATABASE_URL environment variable
(e.g. export DATABASE_URL=postgresql://user:pass@localhost:5432/md_marts).

Usage:
  python mcp_server/db/load_postgres.py --dry-run          # print what would load, no connection
  python mcp_server/db/load_postgres.py                    # load CSV snapshot
  python mcp_server/db/load_postgres.py --duckdb           # load from the DuckDB marts instead
"""

from __future__ import annotations

import argparse
import os
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
EXPORT_DIR = REPO / "data" / "export" / "latest"
DUCKDB_PATH = REPO / "data" / "md_transparency.duckdb"
SCHEMA = "marts"

# DuckDB column type -> Postgres column type (everything else falls back to TEXT).
PG_TYPES = {
    "BIGINT": "BIGINT",
    "INTEGER": "INTEGER",
    "SMALLINT": "SMALLINT",
    "TINYINT": "SMALLINT",
    "DOUBLE": "DOUBLE PRECISION",
    "FLOAT": "REAL",
    "DECIMAL": "NUMERIC",
    "BOOLEAN": "BOOLEAN",
    "DATE": "DATE",
    "TIMESTAMP": "TIMESTAMP",
    "VARCHAR": "TEXT",
}


def pg_type(duckdb_type: str) -> str:
    base = duckdb_type.split("(")[0].upper()
    return PG_TYPES.get(base, "TEXT")


def collect_tables(use_duckdb: bool):
    """Return (duckdb_connection, {table_name: select_sql}) for the chosen source."""
    import duckdb

    con = duckdb.connect()  # in-memory reader; CSV mode needs no warehouse file
    plan: dict[str, str] = {}
    if use_duckdb:
        if not DUCKDB_PATH.exists():
            sys.exit(f"DuckDB database not found: {DUCKDB_PATH} (run `make build` first)")
        con.execute(f"ATTACH '{DUCKDB_PATH}' AS mdb (READ_ONLY)")
        names = [
            r[0]
            for r in con.execute(
                "SELECT table_name FROM information_schema.tables"
                " WHERE table_catalog = 'mdb' AND table_schema = 'mart' ORDER BY table_name"
            ).fetchall()
        ]
        for name in names:
            plan[name] = f"SELECT * FROM mdb.mart.{name}"
    else:
        if not EXPORT_DIR.exists():
            sys.exit(f"Export snapshot not found: {EXPORT_DIR} (run `make export` first)")
        for csv_path in sorted(EXPORT_DIR.glob("*.csv")):
            plan[csv_path.stem] = f"SELECT * FROM read_csv_auto('{csv_path}', header = true)"
    return con, plan


def describe(con, tables):
    """Yield (table, columns, row_count) without touching Postgres."""
    for name, sql in tables.items():
        cols = con.execute(f"SELECT * FROM ({sql}) LIMIT 0").description
        count = con.execute(f"SELECT count(*) FROM ({sql})").fetchone()[0]
        yield name, [(c[0], pg_type(str(c[1]))) for c in cols], count


def load(con, tables, database_url: str):
    import psycopg

    with psycopg.connect(database_url) as conn:
        conn.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
        for name, sql in tables.items():
            cols = con.execute(f"SELECT * FROM ({sql}) LIMIT 0").description
            col_defs = ", ".join(f'"{c[0]}" {pg_type(str(c[1]))}' for c in cols)
            conn.execute(f'DROP TABLE IF EXISTS {SCHEMA}."{name}"')
            conn.execute(f'CREATE TABLE {SCHEMA}."{name}" ({col_defs})')
            rows = con.execute(sql)
            with conn.cursor().copy(f'COPY {SCHEMA}."{name}" FROM STDIN') as copy:
                for row in rows.fetchall():
                    copy.write_row(row)
            count = conn.execute(f'SELECT count(*) FROM {SCHEMA}."{name}"').fetchone()[0]
            print(f"loaded {SCHEMA}.{name}: {count} rows")
        conn.commit()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--csv", dest="source", action="store_const", const="csv", default="csv",
                        help="load data/export/latest/*.csv (default)")
    parser.add_argument("--duckdb", dest="source", action="store_const", const="duckdb",
                        help="load mart.* tables from data/md_transparency.duckdb instead")
    parser.add_argument("--dry-run", action="store_true",
                        help="print what would be loaded without connecting to Postgres")
    args = parser.parse_args(argv)

    con, tables = collect_tables(args.source == "duckdb")
    print(f"source: {'DuckDB marts' if args.source == 'duckdb' else 'CSV export'}  target schema: {SCHEMA}")

    if args.dry_run:
        for name, cols, count in describe(con, tables):
            col_list = ", ".join(f"{c} {t}" for c, t in cols)
            print(f"  would load {SCHEMA}.{name}: {count} rows ({col_list})")
        print(f"dry run: {len(tables)} tables; nothing written")
        return 0

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        sys.exit(
            "DATABASE_URL is not set. Point it at a local Postgres, e.g.\n"
            "  export DATABASE_URL=postgresql://user:pass@localhost:5432/md_marts\n"
            "or preview without connecting: make postgres DRY_RUN=1"
        )
    load(con, tables, database_url)
    print(f"done: {len(tables)} tables in schema {SCHEMA}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
