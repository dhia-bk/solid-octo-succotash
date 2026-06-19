"""
Extractor for the dim_super6_rounds warehouse source.

Purpose:
- Extract Super6 competition round nodes from dim_super6_rounds, including
  super6_round_id, round window (start/end), active state, and creation time.
- Incremental strategy using created_at_utc as the watermark.
- Return typed Super6RoundsRow instances wrapped in ExtractorBatch.

Watermark field — created_at_utc vs start_date_utc:
    The schema module declares FRESHNESS_FIELD = "start_date_utc". However,
    start_date_utc represents when a round is scheduled to begin, not when
    the row was written. Rounds are typically created in the DWH before their
    start date (pre-planned schedule), meaning start_date_utc can be in the
    future relative to the pipeline run. Using start_date_utc as a watermark
    would incorrectly exclude pre-scheduled future rounds from incremental
    runs, making the bootstrap load the only way to pick them up.

    created_at_utc is the row-write timestamp and is the correct incremental
    field — it captures newly inserted round records regardless of when the
    round is scheduled to start. start_date_utc is preserved in the column
    list and typed row for downstream scheduling and ordering logic.

Ordering — start_date_utc, super6_round_id:
    The plan explicitly specifies this ordering. Rounds ordered by their
    scheduled start date produce output that is naturally aligned with the
    competition calendar, which is the most useful ordering for downstream
    HAS_FIXTURE and PARTICIPATED_IN edge construction.

Source characteristics:
    dim_super6_rounds is a low-churn identity table — a new row is created
    per competition round, which is a low-frequency event (weekly or monthly
    cadence on most deployments). is_active can toggle as rounds open and
    close; like is_closed on discussions, this mutation is not captured
    by created_at_utc-based incremental runs.

Design rules:
- super6_round_id is VARCHAR(100) in the DWH; preserved as str.
- is_active is a TINYINT 0/1 flag; stored as int | None. Can change after
  row creation; incremental runs will not re-extract state changes on
  existing rounds.
- No graph logic, canonicalization, or enrichment is applied here.

Source schema:
- Source table  : dim_super6_rounds
- Inclusion mode: GRAPH_CORE
- Graph entity  : Super6Round
- Schema freshness field: start_date_utc (declared)
- Extractor watermark  : created_at_utc (preferred — see rationale above)
"""

from __future__ import annotations

from app.contracts.warehouse_rows import WarehouseRow
from app.extractors.base import BaseExtractor
from app.schemas.warehouse.super6_rounds import (
    INCLUSION_MODE,
    PRIMARY_KEYS,
    SOURCE_NAME,
    Super6RoundsRow,
)

# Watermark field used by this extractor — intentionally different from the
# schema-declared FRESHNESS_FIELD ("start_date_utc"). See module docstring.
_WATERMARK_FIELD: str = "created_at_utc"


class Super6RoundsExtractor(BaseExtractor):
    """
    Extractor for dim_super6_rounds.

    Incremental strategy:
    - watermark field: created_at_utc (not the schema-declared start_date_utc)
    - ordering: start_date_utc, super6_round_id

    Pre-scheduled round handling:
    - Rounds are inserted into the DWH before their start date. Using
      created_at_utc as the watermark ensures pre-scheduled future rounds
      are captured as soon as they are written, not only when their
      start_date_utc is reached.

    Active state limitation:
    - is_active can toggle after row creation. Incremental runs will not
      re-extract state changes on existing rounds. Schedule periodic
      full-refresh runs when accurate is_active state is required.
    """

    source_name: str = SOURCE_NAME
    schema_row_class: type[WarehouseRow] = Super6RoundsRow
    inclusion_mode: str = INCLUSION_MODE
    freshness_field: str | None = _WATERMARK_FIELD    # created_at_utc
    primary_key_fields: tuple[str, ...] = PRIMARY_KEYS
    default_chunk_size: int = 500                     # low-churn; rounds are
                                                      # created at weekly or
                                                      # monthly cadence
    supports_incremental: bool = True

    # ── Source column contract ────────────────────────────────────────────────

    def get_source_columns(self) -> tuple[str, ...]:
        """
        Return the explicit ordered source columns for dim_super6_rounds.

        These columns must stay aligned with Super6RoundsRow.from_row().
        Adding or removing a column here requires a matching change in
        the schema row dataclass.

        Watermark note:
            start_date_utc is the schema-declared freshness field but is not
            used as the watermark here — see module docstring. It is still
            selected because it carries scheduling semantics used by the
            ordering clause and downstream edge construction.

        is_active note:
            TINYINT 0/1 flag; can change after row creation. Incremental
            runs will not re-extract is_active changes on existing rounds.
        """
        return (
            "super6_round_id",
            "round_number",
            "start_date_utc",     # scheduling timestamp; also drives ordering
            "end_date_utc",
            "is_active",          # mutable after creation — see active state note
            "created_at_utc",     # extractor watermark field
        )

    # ── Query construction ────────────────────────────────────────────────────

    def build_base_query(self) -> str:
        """
        Return the base SELECT for dim_super6_rounds without incremental
        filtering.

        The incremental clause (WHERE created_at_utc > %(watermark_value)s)
        is appended by the base runtime via build_incremental_clause().
        """
        columns = ",\n    ".join(self.get_source_columns())
        return f"""
SELECT
    {columns}
FROM {self.source_name}
""".strip()

    def build_incremental_clause(self, watermark_value: str | None) -> str:
        """
        Build the incremental filter using created_at_utc.

        Uses strict greater-than semantics so watermark advancement remains
        monotonic across runs. No clause is emitted on first run (watermark
        is None), triggering a full-table bootstrap load.
        """
        if not self.supports_incremental or not self.freshness_field:
            return ""

        if not watermark_value:
            return ""

        return f"\nWHERE {self.freshness_field} > %(watermark_value)s"

    def build_order_by_clause(self) -> str:
        """
        Return stable deterministic ordering for dim_super6_rounds.

        start_date_utc first — aligns output with the competition calendar,
        which is the natural downstream consumption pattern for round-level
        HAS_FIXTURE and PARTICIPATED_IN edge construction.

        super6_round_id second — VARCHAR PK; breaks ties within the same
        start_date_utc bucket (e.g. rounds starting simultaneously in
        different leagues) deterministically.
        """
        return "\nORDER BY start_date_utc, super6_round_id"

    def build_pagination_clause(self, limit: int, offset: int) -> str:
        """
        Return LIMIT/OFFSET pagination clause.
        """
        return "\nLIMIT %(limit)s OFFSET %(offset)s"