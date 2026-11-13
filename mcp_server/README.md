# MCP server and Postgres loader (decision register #15 and #12)

## `server.py` — read-only MCP server over the marts

A small [MCP](https://modelcontextprotocol.io) stdio server that lets an assistant explore
`data/md_transparency.duckdb` (opened `read_only=True`) without write access. DuckDB stays the
project's only store; this is a read-only window onto it.

Tools:

| Tool | Arguments | Returns |
|---|---|---|
| `list_tables` | — | every `schema.table` in the database |
| `describe_table` | `table` (e.g. `mart.f_scope`) | column names, types, nullability |
| `run_query` | `sql` | JSON `{columns, rows, row_count}` |

`run_query` accepts a single `SELECT`/`WITH` statement only — DDL, DML, `PRAGMA`, `ATTACH`,
`COPY` and friends are rejected — and caps results at 1,000 rows (a `LIMIT` is added or lowered).

### Install

```bash
pip install -e ".[dev]"   # project venv, then:
pip install "mcp>=2"      # the only extra dependency (duckdb is already a project dependency)
make build                # if data/md_transparency.duckdb does not exist yet
```

### Claude Desktop / Claude Code config

Point the client at the venv's Python; the database path defaults to
`<repo>/data/md_transparency.duckdb` and can be overridden with `MD_TRANSPARENCY_DB`.

```json
{
  "mcpServers": {
    "md-transparency": {
      "command": "/absolute/path/to/gmi-savings-tracker/.venv/bin/python",
      "args": ["/absolute/path/to/gmi-savings-tracker/mcp_server/server.py"]
    }
  }
}
```

For Claude Code: `claude mcp add md-transparency -- /absolute/path/to/.venv/bin/python /absolute/path/to/mcp_server/server.py`

## `db/load_postgres.py` — optional Postgres mirror

Loads the published marts into a local Postgres under schema `marts`, for BI tools that expect
Postgres. Opt-in only; DuckDB remains the default. See the `postgres` target in the Makefile:

```bash
make postgres DRY_RUN=1                 # print what would load, no connection
export DATABASE_URL=postgresql://user:pass@localhost:5432/md_marts
make postgres                           # load from data/export/latest/*.csv
make postgres SRC=--duckdb              # or straight from the DuckDB mart schema
```
