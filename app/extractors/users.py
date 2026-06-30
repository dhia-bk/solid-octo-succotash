"""
Extractor for the dim_users warehouse source.

Purpose:
- Extract the primary user identity backbone from dim_users.
- Support incremental extraction using last_activity_at_utc as the watermark.
- Return typed UsersRow instances wrapped in ExtractorBatch.

Design rules:
- This extractor is the primary current-state user source.
- It must preserve all downstream identity, profile, subscription, activity,
  auth snapshot, duel rating, and notification summary fields.
- It must not drop source columns needed by mappings or later ownership rules.
- It performs warehouse extraction only; no graph logic or canonicalization.

Source schema:
- Source table: dim_users
- Inclusion mode: GRAPH_CORE
- Graph entity: User
- Freshness field: last_activity_at_utc
"""

from __future__ import annotations

from app.contracts.warehouse_rows import WarehouseRow
from app.extractors.base import BaseExtractor
from app.schemas.warehouse.users import (
    FRESHNESS_FIELD,
    INCLUSION_MODE,
    PRIMARY_KEYS,
    SOURCE_NAME,
    UsersRow,
)


class UsersExtractor(BaseExtractor):
    """
    Extractor for dim_users.

    Incremental strategy:
    - watermark field: last_activity_at_utc
    - ordering: last_activity_at_utc, user_id
    """

    source_name = SOURCE_NAME
    schema_row_class: type[WarehouseRow] = UsersRow
    inclusion_mode = INCLUSION_MODE
    freshness_field = FRESHNESS_FIELD
    primary_key_fields = PRIMARY_KEYS
    default_chunk_size = 5000
    supports_incremental = True

    def get_source_columns(self) -> tuple[str, ...]:
        """
        Return the explicit ordered source columns for dim_users.

        These columns must stay aligned with UsersRow.from_row().
        """
        return (
            "user_id",
            "user_name",
            "full_name",
            "country",
            "birthdate",
            "age",
            "user_created_at_utc",
            "gender",
            "favorite_team_id",
            "favorite_team_name",
            "first_activity_at_utc",
            "last_activity_at_utc",
            "lifetime_posts",
            "lifetime_comments",
            "lifetime_predictions",
            "lifetime_prediction_points",
            "current_streak_count",
            "longest_streak_count",
            "current_subscription_name",
            "has_early_prediction_permission",
            "is_suspended",
            "referred_by_user_id",
            "referral_code",
            "is_waiting",
            "lockout_enabled",
            "lockout_end_utc",
            "access_failed_count",
            "days_since_last_activity",
            "blocks_given_count",
            "blocks_received_count",
            "ai_total_credits",
            "ai_remaining_credits",
            "ai_credits_expires_at_utc",
            "ai_credits_last_reset_at_utc",
            "last_payment_at_utc",
            "days_since_last_payment",
            "avatar_category",
            "avatar_id",
            "auth_provider",
            "all_auth_providers",
            "duel_rating",
            "notif_total_received",
            "notif_total_read",
        )

    def build_base_query(self) -> str:
        """
        Return the base SELECT for dim_users without incremental filtering.
        """
        columns = ",\n    ".join(self.get_source_columns())
        return f"""
SELECT
    {columns}
FROM {self.source_name}
""".strip()

    def build_incremental_clause(self, watermark_value: str | None) -> str:
        """
        Build the incremental filter using last_activity_at_utc.

        Uses strict greater-than semantics so watermark advancement remains
        monotonic across runs.
        """
        if not self.supports_incremental or not self.freshness_field:
            return ""

        if not watermark_value:
            return ""

        return f"\nWHERE {self.freshness_field} > :watermark_value"

    def build_order_by_clause(self) -> str:
        """
        Return stable deterministic ordering for dim_users.
        """
        return "\nORDER BY last_activity_at_utc, user_id"

    def build_pagination_clause(self, limit: int, offset: int) -> str:
        """
        Return LIMIT/OFFSET pagination clause.
        """
        return "\nLIMIT %(limit)s OFFSET %(offset)s"