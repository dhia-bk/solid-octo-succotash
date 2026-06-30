"""
Apply all metadata DB migrations in order (001 → 005).

Usage:
    python scripts/migrate_metadata.py

Reads METADATA_DB_HOST, METADATA_DB_USER, METADATA_DB_PASSWORD, METADATA_DB_NAME
from environment (or .env). Splits each .sql file on semicolons and runs each
statement against the MySQL metadata database.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

try:
    import psycopg
except ImportError:
    sys.exit("psycopg not installed. Run: pip install -e .")

MIGRATIONS_DIR = ROOT / "migrations" / "metadata"
MIGRATION_FILES = [
    "001_job_runs.sql",
    "002_checkpoints.sql",
    "003_model_registry.sql",
    "004_data_quality_results.sql",
    "005_source_inventory.sql",
]

COMMENT_LINE = __import__("re").compile(r"--[^\n]*", __import__("re").MULTILINE)


def _statements(sql_text: str) -> list[str]:
    stripped = COMMENT_LINE.sub("", sql_text)
    parts = stripped.split(";")
    return [s.strip() for s in parts if s.strip()]


def run_migrations(host: str, user: str, password: str, db: str, port: int = 5432) -> None:
    print(f"Connecting to PostgreSQL {host}:{port} db={db} …")
    try:
        conn = psycopg.connect(
            host=host, port=port, user=user, password=password, dbname=db, autocommit=True
        )
    except Exception as exc:
        sys.exit(f"Cannot connect to metadata DB: {exc}")

    print("Connection OK\n")

    with conn.cursor() as cur:
        for filename in MIGRATION_FILES:
            path = MIGRATIONS_DIR / filename
            if not path.exists():
                sys.exit(f"Migration file not found: {path}")

            sql_text = path.read_text(encoding="utf-8")
            statements = _statements(sql_text)

            print(f"  [{filename}]  {len(statements)} statement(s)")
            for i, stmt in enumerate(statements, 1):
                try:
                    cur.execute(stmt)
                    print(f"    ✓ statement {i}")
                except Exception as exc:
                    sys.exit(f"    ✗ statement {i} FAILED:\n      {exc}\n\n  SQL:\n  {stmt[:300]}")

            print(f"  → {filename} applied\n")

    conn.close()
    print("All 5 metadata migrations applied successfully.")


if __name__ == "__main__":
    host = os.environ.get("METADATA_DB_HOST", "")
    user = os.environ.get("METADATA_DB_USER", "")
    password = os.environ.get("METADATA_DB_PASSWORD", "")
    db = os.environ.get("METADATA_DB_NAME", "")
    port = int(os.environ.get("METADATA_DB_PORT", "5432"))

    missing = [
        k for k, v in [
            ("METADATA_DB_HOST", host),
            ("METADATA_DB_USER", user),
            ("METADATA_DB_PASSWORD", password),
            ("METADATA_DB_NAME", db),
        ] if not v
    ]
    if missing:
        sys.exit(f"Missing env vars: {', '.join(missing)}\nSet them in .env or export before running.")

    run_migrations(host, user, password, db, port)
