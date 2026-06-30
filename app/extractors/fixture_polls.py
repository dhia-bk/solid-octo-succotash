"""
Extractor for the dim_fixture_polls_enhanced warehouse source.

Purpose:
- Extract fixture-linked poll rows from dim_fixture_polls_enhanced, including
  poll identity, question text, options, activity window, and response
  analytics (counts, percentages, timing, demographics).
- Incremental strategy using last_response_at_utc as the watermark.
- Return typed FixturePollsRow instances wrapped in ExtractorBatch.

Watermark field — last_response_at_utc vs created_at_utc:
    The schema module declares FRESHNESS_FIELD = "created_at_utc". However,
    dim_fixture_polls_enhanced carries running response analytics (total_responses,
    unique_respondents, option1/2_count, option1/2_percentage,
    last_response_at_utc, avg_response_time_minutes, responses_in_first_hour,
    responses_in_first_day, top_responding_country, top_responding_gender)
    that update in-place as users respond to the poll. Filtering by
    created_at_utc captures new polls correctly but silently misses all
    aggregate updates on existing polls.

    last_response_at_utc advances each time a new response is recorded and
    is NULL for polls with no responses yet. Using it as the watermark
    captures both new polls (when their first response is recorded) and
    existing polls with new response activity. Polls with zero responses
    are captured on the initial full-refresh bootstrap and re-captured if
    they ever receive their first response.

    NULL last_response_at_utc limitation:
    - Polls that receive no responses after initial bootstrap will not be
      re-extracted until their first response arrives. For polls that are
      never answered, this is acceptable — their identity and question text
      are captured once on bootstrap and do not change.

Ordering — created_at_utc, fixture_poll_id:
    The plan explicitly specifies this ordering. Although last_response_at_utc
    is the watermark, ordering by creation time is more semantically stable
    for downstream poll timeline construction, and avoids NULL-first or
    NULL-last instability from ordering on the potentially-NULL
    last_response_at_utc.

Design rules:
- fixture_poll_id and fixture_id are VARCHAR(100); preserved as str / str | None.
- All percentage and timing fields are DOUBLE; stored as float | None.
- is_active is a TINYINT 0/1 flag; can change after poll creation.
  Incremental runs by last_response_at_utc will naturally re-extract polls
  that receive new responses, which covers most is_active state changes
  (polls are typically deactivated when response activity stops).
- No graph logic, canonicalization, or enrichment is applied here.

Source schema:
- Source table  : dim_fixture_polls_enhanced
- Inclusion mode: GRAPH_CORE
- Graph entity  : Poll
- Schema freshness field: created_at_utc (declared)
- Extractor watermark  : last_response_at_utc (preferred — captures analytics updates)
"""

from __future__ import annotations

from app.contracts.warehouse_rows import WarehouseRow
from app.extractors.base import BaseExtractor
from app.schemas.warehouse.fixture_polls import (
    INCLUSION_MODE,
    PRIMARY_KEYS,
    SOURCE_NAME,
    FixturePollsRow,
)

# Watermark field used by this extractor — intentionally different from the
# schema-declared FRESHNESS_FIELD ("created_at_utc"). See module docstring.
_WATERMARK_FIELD: str = "last_response_at_utc"


class FixturePollsExtractor(BaseExtractor):
    """
    Extractor for dim_fixture_polls_enhanced.

    Incremental strategy:
    - watermark field: last_response_at_utc (not schema-declared created_at_utc)
    - ordering: created_at_utc, fixture_poll_id

    Response-activity watermark:
    - last_response_at_utc advances on every new poll response, capturing
      both new polls (first response) and existing polls with new activity.
    - NULL last_response_at_utc means no responses yet; such polls are
      captured on the initial bootstrap and not re-extracted until their
      first response arrives.

    Aggregate completeness:
    - All response analytics columns update in-place. The watermark
      strategy ensures polls with any new response activity are fully
      re-extracted with their latest aggregate state.
    """

    source_name: str = SOURCE_NAME
    schema_row_class: type[WarehouseRow] = FixturePollsRow
    inclusion_mode: str = INCLUSION_MODE
    freshness_field: str | None = _WATERMARK_FIELD    # last_response_at_utc
    primary_key_fields: tuple[str, ...] = PRIMARY_KEYS
    default_chunk_size: int = 2000                    # poll volume tracks
                                                      # active fixtures count
    supports_incremental: bool = True

    # ── Source column contract ────────────────────────────────────────────────

    def get_source_columns(self) -> tuple[str, ...]:
        """
        Return the explicit ordered source columns for dim_fixture_polls_enhanced.

        These columns must stay aligned with FixturePollsRow.from_row().
        Adding or removing a column here requires a matching change in
        the schema row dataclass.

        Watermark note:
            last_response_at_utc is the extractor watermark. NULL for polls
            with zero responses; non-NULL and advancing on every new response.

        Aggregate fields note:
            total_responses, unique_respondents, option1_count, option2_count,
            option1_percentage, option2_percentage, avg_response_time_minutes,
            responses_in_first_hour, responses_in_first_day,
            top_responding_country, top_responding_gender — all update in-place
            as users respond. These are the primary reason for choosing
            last_response_at_utc over created_at_utc as the watermark.
        """
        return (
            "fixture_poll_id",
            "fixture_id",
            "creator_user_id",
            "question_text",
            "option1",
            "option2",
            "created_at_utc",
            "is_active",
            "total_responses",
            "unique_respondents",
            "option1_count",
            "option2_count",
            "option1_percentage",              # DOUBLE — float | None
            "option2_percentage",              # DOUBLE — float | None
            "first_response_at_utc",
            "last_response_at_utc",            # extractor watermark field
            "avg_response_time_minutes",       # DOUBLE — float | None
            "responses_in_first_hour",
            "responses_in_first_day",
            "top_responding_country",
            "top_responding_gender",
        )

    # ── Query construction ────────────────────────────────────────────────────

    def build_base_query(self) -> str:
        """
        Return the base SELECT for dim_fixture_polls_enhanced without
        incremental filtering.

        The incremental clause
        (WHERE last_response_at_utc > :watermark_value) is appended by
        the base runtime via build_incremental_clause().
        """
        columns = ",\n    ".join(self.get_source_columns())
        return f"""
SELECT
    {columns}
FROM {self.source_name}
""".strip()

    def build_incremental_clause(self, watermark_value: str | None) -> str:
        """
        Build the incremental filter using last_response_at_utc.

        Uses strict greater-than semantics so watermark advancement remains
        monotonic across runs. No clause is emitted on first run (watermark
        is None), triggering a full-table bootstrap load that captures all
        polls including those with zero responses.
        """
        if not self.supports_incremental or not self.freshness_field:
            return ""

        if not watermark_value:
            return ""

        return f"\nWHERE {self.freshness_field} > :watermark_value"

    def build_order_by_clause(self) -> str:
        """
        Return stable deterministic ordering for dim_fixture_polls_enhanced.

        created_at_utc first — stable, non-NULL creation timestamp; avoids
        NULL-ordering instability from ordering on last_response_at_utc
        (which is NULL for polls with no responses). Ordering by creation
        time is semantically aligned with the poll timeline.

        fixture_poll_id second — VARCHAR PK; breaks ties within the same
        creation timestamp bucket deterministically.
        """
        return "\nORDER BY created_at_utc, fixture_poll_id"

    def build_pagination_clause(self, limit: int, offset: int) -> str:
        """
        Return LIMIT/OFFSET pagination clause.
        """
        return "\nLIMIT %(limit)s OFFSET %(offset)s"