#!/usr/bin/env python3
"""Read-only MCP server over the Maryland transparency marts (decision register #15).

Exposes three tools over stdio against data/md_transparency.duckdb, opened read-only:

  list_tables()                      -> every schema.table in the database
  describe_table(table)              -> columns (name, type) for one table, e.g. "mart.f_scope"
  run_query(sql)                     -> run a read-only SELECT and return rows as JSON

run_query guards:
  - only a single SELECT/WITH statement is accepted;
  - DDL/DML/PRAGMA/ATTACH/COPY and friends are rejected by keyword scan;
  - results are capped at 1,000 rows (a LIMIT is added or lowered if needed).

Database path: env MD_TRANSPARENCY_DB, default <repo>/data/md_transparency.duckdb.
Run:  python mcp_server/server.py        (stdio; see mcp_server/README.md for client config)
"""

from __future__ import annotations

import json
import os
import pathlib
import re

import duckdb
from mcp.server.mcpserver import MCPServer  # mcp 2.x (v1's FastMCP renamed)

REPO = pathlib.Path(__file__).resolve().parents[1]
DB_PATH = pathlib.Path(os.environ.get("MD_TRANSPARENCY_DB", REPO / "data" / "md_transparency.duckdb"))
ROW_LIMIT = 1000

_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|create|alter|attach|detach|copy|export|import|pragma|vacuum|"
    r"checkpoint|install|load|set|use|call|grant|revoke|truncate|replace|comment|begin|commit|rollback)\b",
    re.IGNORECASE,
)
_LIMIT = re.compile(r"\blimit\s+(\d+)", re.IGNORECASE)
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)?$")

_con = None


def _db() -> duckdb.DuckDBPyConnection:
    global _con
    if _con is None:
        if not DB_PATH.exists():
            raise FileNotFoundError(f"database not found: {DB_PATH} (run `make build` first)")
        _con = duckdb.connect(str(DB_PATH), read_only=True)
    return _con


def guard_query(sql: str) -> str:
    """Validate a read-only SELECT and enforce the row cap. Returns the SQL to execute."""
    q = sql.strip().rstrip(";").strip()
    if not q:
        raise ValueError("empty query")
    if ";" in q:
        raise ValueError("only a single statement is allowed")
    if not re.match(r"^(select|with)\b", q, re.IGNORECASE):
        raise ValueError("read-only server: only SELECT (or WITH ... SELECT) is allowed")
    m = _FORBIDDEN.search(q)
    if m:
        raise ValueError(f"read-only server: '{m.group(1)}' is not allowed")
    limits = _LIMIT.findall(q)
    if not limits:
        q = f"SELECT * FROM ({q}) AS _capped LIMIT {ROW_LIMIT}"
    elif int(limits[-1]) > ROW_LIMIT:
        q = _LIMIT.sub(f"LIMIT {ROW_LIMIT}", q, count=1)
    return q


def _rows_as_json(cursor) -> str:
    cols = [c[0] for c in cursor.description]
    rows = cursor.fetchall()
    return json.dumps({"columns": cols, "rows": [list(r) for r in rows], "row_count": len(rows)}, default=str)


mcp = MCPServer("md-transparency-marts")


@mcp.tool()
def list_tables() -> str:
    """List every table and view in the transparency database, as schema.table."""
    cur = _db().execute(
        "SELECT table_schema || '.' || table_name AS table FROM information_schema.tables ORDER BY 1"
    )
    return json.dumps([r[0] for r in cur.fetchall()])


@mcp.tool()
def describe_table(table: str) -> str:
    """Describe one table's columns. table: schema.table or bare table name, e.g. mart.f_scope."""
    if not _IDENTIFIER.match(table):
        raise ValueError(f"not a valid table identifier: {table!r}")
    cur = _db().execute(f"DESCRIBE {table}")
    return json.dumps([{"column": r[0], "type": r[1], "nullable": r[2]} for r in cur.fetchall()])


@mcp.tool()
def run_query(sql: str) -> str:
    """Run a read-only SELECT against the marts and return JSON {columns, rows, row_count}.

    Results are capped at 1,000 rows; anything that is not a single SELECT is rejected.
    """
    return _rows_as_json(_db().execute(guard_query(sql)))


if __name__ == "__main__":
    mcp.run()  # stdio transport
