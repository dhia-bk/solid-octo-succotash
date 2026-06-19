# Migrations

Schema migrations for the Project Pulse Knowledge Graph.

Two migration tracks:
- `metadata/` — SQL DDL for the metadata database (SQLite in dev, PostgreSQL in staging/prod)
- `neo4j/` — Cypher DDL for the Neo4j graph database

---

## Applying metadata migrations

```bash
# Dev (SQLite)
python scripts/run_metadata_migrations.py --db-url sqlite:///pulse_metadata.db

# Staging / Prod (PostgreSQL)
python scripts/run_metadata_migrations.py --db-url postgresql://user:pass@host:5432/pulse_metadata
```

The runner automatically tracks applied migrations in a `_migrations` table.
Re-running on an already-migrated database is safe — applied migrations are skipped.

---

## Applying Neo4j migrations

```bash
# All environments
python scripts/run_neo4j_migrations.py \
    --neo4j-uri bolt://localhost:7687 \
    --neo4j-user neo4j \
    --neo4j-password <password>
```

Applied migrations are recorded as `GraphMigrationLog` nodes in the graph.
Re-running is safe — all Cypher statements use `IF NOT EXISTS`.

---

## Migration ordering rules

1. Metadata migrations are applied in filename order (`001_`, `002_`, …).
2. Neo4j migrations are applied in filename order (`001_`, `002_`, …).
3. Metadata migrations have no dependency on Neo4j migrations; they may be applied independently.
4. Within Neo4j: constraints (`001`) must be applied before indexes (`002`) and serving views (`005`).

---

## Checking applied migrations

**Metadata:**

```sql
SELECT * FROM _migrations ORDER BY applied_at;
```

**Neo4j:**

```cypher
MATCH (m:GraphMigrationLog) RETURN m ORDER BY m.applied_at;
```

---

## Rollback policy

Migrations in this directory are **append-only and never drop objects**.

Rollback scripts live in `migrations/rollback/` and must be applied manually after review.
Never run a rollback in production without a verified backup.

---

## Environment notes

| Environment | Metadata DB         | Notes                                      |
|-------------|---------------------|--------------------------------------------|
| dev         | SQLite              | `sqlite:///pulse_metadata.db` in repo root |
| staging     | PostgreSQL          | Managed instance, same schema as prod      |
| prod        | PostgreSQL          | Managed instance                           |

**SQLite compatibility notes:**
- `INTEGER PRIMARY KEY` in SQLite acts as an auto-increment alias for `rowid`.
- `AUTOINCREMENT` is explicit and slightly stricter; either form is acceptable.
- `ON DUPLICATE KEY UPDATE` (MySQL syntax) used in `app/db/checkpoints.py` is handled
  at the application layer — the migration creates the UNIQUE constraint that makes upserts work.
- `REAL` (SQLite) maps to `DOUBLE PRECISION` or `FLOAT8` in PostgreSQL.
- `TEXT` maps to `VARCHAR` / `TEXT` in PostgreSQL.
- `INTEGER` maps to `INTEGER` / `BIGINT` in PostgreSQL.

**PostgreSQL-only features** are noted inline in migration files where applicable.
