"""
Extractor for the dim_private_league_members warehouse source.

Purpose:
- Extract membership rows from dim_private_league_members, including
  membership_id, private_league_id, user_id, role, joined_at, permissions,
  and activity metadata.
- Incremental strategy using last_active_at_utc as the watermark — preferred
  over the schema-declared joined_at because membership rows mutate after the
  join event (role changes, permission updates, left_at, last_active_at_utc).
  Filtering on joined_at would silently miss all post-join mutations.
- Falls back to full refresh when no watermark is available (first run or
  checkpoint reset) or when last_active_at_utc is unreliable (NULL-heavy).
- Return typed PrivateLeagueMembersRow instances wrapped in ExtractorBatch.

Watermark field rationale — last_active_at_utc vs joined_at:
    The schema module declares FRESHNESS_FIELD = "joined_at". However,
    membership rows can change significantly after the join event:
      - role promoted/demoted
      - can_post / can_moderate / can_invite toggled
      - left_at and leave_reason populated on departure
      - last_active_at_utc advanced on every fixture participation
    Using joined_at as the watermark would produce a correct initial load
    but then silently skip all subsequent mutations. last_active_at_utc
    advances on every meaningful membership event and is therefore the
    correct incremental field for this source. joined_at is preserved in
    the column list and the typed row for downstream use.

Nullable membership_id handling:
    membership_id is VARCHAR(50) and is NULL in some rows. The extractor
    must not attempt to resolve, synthesize, or drop rows with NULL
    membership_id. All fallback identity fields (private_league_id, user_id)
    are preserved so the transformer can construct a composite merge key
    when membership_id is absent.

Design rules:
- Do not infer membership identity. Preserve membership_id (nullable) and
  all composite fallback fields (private_league_id, user_id) exactly.
- invited_by_user_id is INTEGER in the DWH but is a user reference;
  PrivateLeagueMembersRow.from_row() normalises it to str | None. No
  SQL-level CAST is needed; Python-level coercion in from_row() is sufficient.
- invite_code_used is a sensitive operational field. Extracted faithfully
  from source truth; must not propagate into graph DTOs or API responses.
- No graph logic, canonicalization, or enrichment is applied here.

Source schema:
- Source table  : dim_private_league_members
- Inclusion mode: GRAPH_CORE
- Graph entity  : MEMBER_OF relationship (User → PrivateLeague)
- Schema freshness field: joined_at (declared)
- Extractor watermark  : last_active_at_utc (preferred — captures mutations)
"""

from __future__ import annotations

from app.contracts.warehouse_rows import WarehouseRow
from app.extractors.base import BaseExtractor
from app.schemas.warehouse.private_league_members import (
    INCLUSION_MODE,
    PRIMARY_KEYS,
    SOURCE_NAME,
    PrivateLeagueMembersRow,
)

# Watermark field used by this extractor — intentionally different from
# the schema-declared FRESHNESS_FIELD ("joined_at").  See module docstring.
_WATERMARK_FIELD: str = "last_active_at_utc"


class PrivateLeagueMembersExtractor(BaseExtractor):
    """
    Extractor for dim_private_league_members.

    Incremental strategy:
    - watermark field: last_active_at_utc (not the schema-declared joined_at)
    - ordering: private_league_id, user_id, membership_id
      — composite ordering because membership_id is nullable; this ordering
        is stable regardless of whether membership_id is present.

    Full-refresh fallback:
    - When no prior watermark exists, the base runtime omits the incremental
      clause and extracts all membership rows.
    - Full refresh is also the correct recovery path when last_active_at_utc
      is NULL-heavy (e.g. inactive members who have never triggered an
      activity event after initial import). In that case a watermark-filtered
      run would silently omit all NULL last_active_at_utc rows. The pipeline
      operator should trigger a checkpoint reset to force a full refresh
      when NULL prevalence is discovered.
    """

    source_name: str = SOURCE_NAME
    schema_row_class: type[WarehouseRow] = PrivateLeagueMembersRow
    inclusion_mode: str = INCLUSION_MODE
    freshness_field: str | None = _WATERMARK_FIELD    # last_active_at_utc
    primary_key_fields: tuple[str, ...] = PRIMARY_KEYS
    default_chunk_size: int = 5000                    
    supports_incremental: bool = True

    # ── Source column contract ────────────────────────────────────────────────

    def get_source_columns(self) -> tuple[str, ...]:
        """
        Return the explicit ordered source columns for dim_private_league_members.

        These columns must stay aligned with PrivateLeagueMembersRow.from_row().

        Identity preservation note:
            membership_id   — nullable; preserved as-is. NULL rows are valid
                              extraction output. Do not filter or drop them.
            private_league_id, user_id — composite fallback identity fields.
                              Both must be present for transformer merge-key
                              construction when membership_id is NULL.

        Sensitivity note:
            invite_code_used — operational field that reveals how the member
                               joined. Extracted faithfully; must not reach
                               graph/API boundary.

        Watermark note:
            joined_at is included as a column despite not being the watermark.
            It carries distinct semantic meaning (when the user joined) and is
            needed by downstream MEMBER_OF edge construction.
        """
        return (
            "membership_id",          # nullable — see identity preservation note
            "private_league_id",      # composite fallback PK field
            "user_id",                # composite fallback PK field
            "role",
            "joined_at",              # semantic join timestamp; not the watermark
            "invite_code_used",       # sensitive — must not reach graph/API boundary
            "invited_by_user_id",     # INTEGER in DWH; coerced to str in from_row()
            "is_active",
            "left_at",
            "leave_reason",
            "can_post",
            "can_moderate",
            "can_invite",
            "division",
            "last_active_at_utc",     # extractor watermark field
            "fixture_participation_count",
            "days_since_joined",
        )

    # ── Query construction ────────────────────────────────────────────────────

    def build_base_query(self) -> str:
        """
        Return the base SELECT for dim_private_league_members without
        incremental filtering.

        The incremental clause (WHERE last_active_at_utc > :watermark_value)
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
        Build the incremental filter using last_active_at_utc.

        Uses strict greater-than semantics so watermark advancement remains
        monotonic across runs.

        Full-refresh fallback:
            When watermark_value is None (first run or checkpoint reset),
            no clause is emitted and the full membership table is extracted.
            This is the correct bootstrap and recovery behavior.

        NULL last_active_at_utc rows:
            Rows where last_active_at_utc IS NULL (members who have never
            triggered an activity event) are excluded by any watermark filter.
            These rows are captured on the initial full-refresh load and
            should be re-captured via a checkpoint reset when needed.
        """
        if not self.supports_incremental or not self.freshness_field:
            return ""

        if not watermark_value:
            return ""

        return f"\nWHERE {self.freshness_field} > :watermark_value"

    def build_order_by_clause(self) -> str:
        """
        Return stable deterministic ordering for dim_private_league_members.

        Ordered by private_league_id, user_id, membership_id rather than
        watermark-field-first because:
        - membership_id is nullable; using it as the primary sort would
          cluster NULLs unpredictably across database engines.
        - The composite (private_league_id, user_id) ordering is stable
          and matches the fallback merge-key used by the transformer.
        - membership_id is included as the final tiebreaker for the
          (rare) case of duplicate composite keys in the source table.
        """
        return "\nORDER BY private_league_id, user_id, membership_id"

    def build_pagination_clause(self, limit: int, offset: int) -> str:
        """
        Return LIMIT/OFFSET pagination clause.
        """
        return "\nLIMIT %(limit)s OFFSET %(offset)s"