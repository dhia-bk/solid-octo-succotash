"""
Extractor for the app_users warehouse source.

Purpose:
- Extract auth bridge rows from app_users, including user identity, email,
  username, seed flag, password hash, and auth timestamps.
- Incremental strategy using updated_at as the watermark.
- Return typed AppUsersRow instances wrapped in ExtractorBatch.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PII AND CREDENTIAL FIELD POLICY — READ BEFORE MODIFYING THIS FILE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

This source contains two fields that are subject to strict handling rules:

    email (PII):
        Purpose in pipeline: join key to dim_users only.
        MUST NOT be written to graph node properties.
        MUST NOT appear in any log output, error message, or structured event.
        MUST be dropped by the transformer before any graph write or export.

    password (CREDENTIAL):
        Purpose in pipeline: none beyond extraction completeness.
        MUST NEVER be written to graph node properties, logs, structured
        events, downstream APIs, or any system outside the extraction layer.
        The transformer MUST assert this field is absent (None or stripped)
        before any processing step proceeds. Failure to assert absence is a
        pipeline defect.

These rules are enforced by convention at the transformer layer. The extractor
faithfully extracts both fields as declared in the source schema because:
1. Dropping fields at extraction time would silently break the row contract
   and cause KeyError failures in from_row() on the schema dataclass.
2. The schema layer (AppUsersRow) is the authoritative record of what the
   source contains; suppressing fields here would obscure that record.
3. Enforcement at the transformer — the only layer that writes to graph,
   logs, and APIs — is the correct chokepoint. The transformer must assert
   both fields are dropped before any downstream write.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Watermark field — updated_at:
    updated_at is the correct incremental field because app_users rows mutate
    when credentials are updated, email is changed, or is_seeded transitions.
    updated_at advances on each mutation, ensuring incremental runs capture
    both newly registered users and updated existing auth records. created_at
    would miss all post-registration mutations.

Design rules:
- id is a string PK; used as the ordering tiebreaker.
- is_seeded is TINYINT 0/1 in the DWH; extracted as int | None, not bool.
- created_at and updated_at are TIMESTAMP columns; normalized to datetime | None.
- No graph logic, enrichment merging, or PII redaction is applied here.
  PII/credential field handling is the exclusive responsibility of the
  transformer layer.

Source schema:
- Source table  : app_users
- Inclusion mode: GRAPH_ENRICHMENT
- Graph entity  : User (enrichment; auth metadata)
- Freshness field: updated_at
- Declared PK   : id
"""

from __future__ import annotations

from app.contracts.warehouse_rows import WarehouseRow
from app.extractors.base import BaseExtractor
from app.schemas.warehouse.app_users import (
    FRESHNESS_FIELD,
    INCLUSION_MODE,
    PRIMARY_KEYS,
    SOURCE_NAME,
    AppUsersRow,
)


class AppUsersExtractor(BaseExtractor):
    """
    Extractor for app_users.

    Incremental strategy:
    - watermark field: updated_at
    - ordering: updated_at, id

    Mutation coverage:
    - updated_at advances on credential updates, email changes, and
      is_seeded transitions. Incremental runs therefore capture all auth
      record mutations, not only newly registered users.

    ── PII AND CREDENTIAL FIELDS ──────────────────────────────────────────────

    This extractor faithfully extracts two sensitive fields present in the
    source schema. Their handling rules are non-negotiable:

    email (PII):
        Extracted for join-key use only. MUST NOT be written to graph
        properties or appear in any log, structured event, or export.
        The transformer MUST drop this field before any graph write.

    password (CREDENTIAL):
        Extracted to preserve row contract completeness. MUST NEVER be
        written to any downstream system, log, or API. The transformer
        MUST assert this field is absent before any processing step.

    Enforcement responsibility: transformer layer exclusively.
    The extractor does not redact, hash, or suppress these fields.
    ───────────────────────────────────────────────────────────────────────────
    """

    source_name: str = SOURCE_NAME
    schema_row_class: type[WarehouseRow] = AppUsersRow
    inclusion_mode: str = INCLUSION_MODE
    freshness_field: str | None = FRESHNESS_FIELD       # updated_at
    primary_key_fields: tuple[str, ...] = PRIMARY_KEYS
    default_chunk_size: int = 1000
    supports_incremental: bool = True

    # ── Source column contract ────────────────────────────────────────────────

    def get_source_columns(self) -> tuple[str, ...]:
        """
        Return the explicit ordered source columns for app_users.

        These columns must stay aligned with AppUsersRow.from_row().
        Adding or removing a column here requires a matching change in
        the schema row dataclass.

        ── SENSITIVE FIELD HANDLING ────────────────────────────────────────────

        email    ⚠ PII — join key to dim_users only.
                   MUST NOT be written to graph properties or logs.
                   Transformer MUST drop before graph write.

        password ⚠ CREDENTIAL — no downstream use permitted.
                   MUST NEVER be written to graph, logs, APIs, or any
                   system outside the extraction layer.
                   Transformer MUST assert field is absent before processing.

        Both fields are included here to preserve row contract completeness
        with AppUsersRow.from_row(). Suppressing either field at extraction
        time would cause KeyError failures in the schema dataclass.
        Enforcement is the transformer's responsibility.
        ────────────────────────────────────────────────────────────────────────

        is_seeded note:
            TINYINT 0/1 in the DWH; coerced to int | None. Not a Python bool.

        created_at / updated_at note:
            TIMESTAMP columns in the DWH; normalized to datetime | None via
            warehouse_value_to_utc_datetime.
        """
        return (
            "id",
            "email",            # ⚠ PII — join key only; transformer MUST drop before graph write
            "username",
            "is_seeded",        # TINYINT 0/1 in DWH (not bool)
            "password",         # ⚠ CREDENTIAL — transformer MUST assert absent before processing
            "created_at",
            "updated_at",       # extractor watermark field
        )

    # ── Query construction ────────────────────────────────────────────────────

    def build_base_query(self) -> str:
        """
        Return the base SELECT for app_users without incremental filtering.

        The incremental clause (WHERE updated_at > %(watermark_value)s) is
        appended by the base runtime via build_incremental_clause().
        """
        columns = ",\n    ".join(self.get_source_columns())
        return f"""
SELECT
    {columns}
FROM {self.source_name}
""".strip()

    def build_incremental_clause(self, watermark_value: str | None) -> str:
        """
        Build the incremental filter using updated_at.

        Uses strict greater-than semantics so watermark advancement remains
        monotonic across runs. Covers credential updates, email changes, and
        is_seeded transitions in addition to newly registered users.

        No clause is emitted on first run (watermark is None), triggering a
        full-table bootstrap load.
        """
        if not self.supports_incremental or not self.freshness_field:
            return ""

        if not watermark_value:
            return ""

        return f"\nWHERE {self.freshness_field} > %(watermark_value)s"

    def build_order_by_clause(self) -> str:
        """
        Return stable deterministic ordering for app_users.

        updated_at first — aligns with watermark advancement and clusters
        output by most recent auth record mutation.

        id second — string PK; breaks ties within the same updated_at bucket
        deterministically.
        """
        return "\nORDER BY updated_at, id"

    def build_pagination_clause(self, limit: int, offset: int) -> str:
        """
        Return LIMIT/OFFSET pagination clause.
        """
        return "\nLIMIT %(limit)s OFFSET %(offset)s"