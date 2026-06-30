"""
Apply all Neo4j migration files in order (001 → 006).

Usage:
    python scripts/migrate_neo4j.py

Reads NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD from environment (or .env).
Splits each .cypher file on semicolons, strips comment lines, and runs
each statement as a separate write transaction.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Load .env before anything else
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass  # python-dotenv optional; rely on env vars being set externally

try:
    from neo4j import GraphDatabase
    from neo4j.exceptions import Neo4jError
except ImportError:
    sys.exit("neo4j package not installed. Run: pip install neo4j")

MIGRATIONS_DIR = ROOT / "migrations" / "neo4j"
MIGRATION_FILES = [
    "001_constraints.cypher",
    "002_indexes.cypher",
    "003_node_labels.cypher",
    "004_relationship_types.cypher",
    "005_serving_views.cypher",
    "006_graph_metadata.cypher",
]

COMMENT_LINE = re.compile(r"^\s*//.*$", re.MULTILINE)


def _statements(cypher_text: str) -> list[str]:
    stripped = COMMENT_LINE.sub("", cypher_text)
    parts = stripped.split(";")
    return [s.strip() for s in parts if s.strip()]


def run_migrations(uri: str, user: str, password: str) -> None:
    print(f"Connecting to {uri} as {user} …")
    driver = GraphDatabase.driver(uri, auth=(user, password))

    try:
        driver.verify_connectivity()
        print("Connection OK\n")
    except Exception as exc:
        sys.exit(f"Cannot reach Neo4j at {uri}: {exc}")

    with driver.session(database="neo4j") as session:
        for filename in MIGRATION_FILES:
            path = MIGRATIONS_DIR / filename
            if not path.exists():
                sys.exit(f"Migration file not found: {path}")

            cypher_text = path.read_text(encoding="utf-8")
            statements = _statements(cypher_text)

            print(f"  [{filename}]  {len(statements)} statement(s)")
            for i, stmt in enumerate(statements, 1):
                try:
                    session.execute_write(lambda tx, s=stmt: tx.run(s))
                    print(f"    ✓ statement {i}")
                except Neo4jError as exc:
                    sys.exit(f"    ✗ statement {i} FAILED:\n      {exc}\n\n  Cypher:\n  {stmt[:300]}")

            print(f"  → {filename} applied\n")

    driver.close()
    print("All 6 Neo4j migrations applied successfully.")


if __name__ == "__main__":
    uri = os.environ.get("NEO4J_URI", "")
    user = os.environ.get("NEO4J_USER", "")
    password = os.environ.get("NEO4J_PASSWORD", "")

    missing = [k for k, v in [("NEO4J_URI", uri), ("NEO4J_USER", user), ("NEO4J_PASSWORD", password)] if not v]
    if missing:
        sys.exit(f"Missing env vars: {', '.join(missing)}\nSet them in .env or export before running.")

    run_migrations(uri, user, password)
