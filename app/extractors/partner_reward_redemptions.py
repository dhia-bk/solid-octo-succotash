"""
Extractor for the fct_partner_reward_redemptions warehouse source.

Purpose:
- Extract partner reward redemption events from fct_partner_reward_redemptions,
  including user, reward linkage, quantity, transaction amount, redemption
  timestamp, and event metadata.
- Incremental strategy using redeemed_at_utc as the watermark.
- Return typed PartnerRewardRedemptionsRow instances wrapped in ExtractorBatch.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PII WARNING — user_email
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
This source contains user_email, a PII field required by the partner
fulfilment workflow and present in the source table. The extractor MUST
extract it faithfully to preserve source truth, but downstream stages MUST
enforce the following boundary rules:

  • The transformer MUST NOT write user_email to any graph node or edge
    property.
  • user_email MUST NOT appear in any DTO, API response, or log output.
  • If the transformer requires email for fulfilment routing, it must hash
    or encrypt the value before any storage or transmission.
  • Audit logs of extraction runs must not capture field values.

This is the same PII boundary requirement as app_users.py (email, password).
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Source characteristics:
    fct_partner_reward_redemptions is an append-oriented event log — one row
    per redemption event. Rows are written once and not updated after initial
    insert; redeemed_at_utc is the authoritative event timestamp. Incremental
    extraction is therefore complete and correct with no mutation window.

    reward_key is the FK to dim_partner_reward_catalog (and by extension to
    the PartnerReward graph nodes). Both reward_key and event_id are preserved
    for REDEEMED edge construction and for cross-referencing against the
    inventory event log (fct_partner_reward_inventory).

    source_sequence provides event ordering within the same
    event_created_at_utc bucket, following the same pattern as
    fct_partner_reward_inventory.

Design rules:
- user_email is extracted faithfully from source truth; the PII boundary is
  enforced downstream, not here. See PII WARNING section above.
- transaction_amount is DECIMAL(10,2); stored as float | None.
- redemption_id has no PK constraint; treated as the stable de facto key.
- No graph logic, canonicalization, or enrichment is applied here.

Source schema:
- Source table  : fct_partner_reward_redemptions
- Inclusion mode: GRAPH_CORE
- Graph entity  : REDEEMED relationship (User → PartnerReward)
- Freshness field: redeemed_at_utc
- Declared PK   : None (redemption_id treated as stable de facto key)
"""

from __future__ import annotations

from app.contracts.warehouse_rows import WarehouseRow
from app.extractors.base import BaseExtractor
from app.schemas.warehouse.partner_reward_redemptions import (
    FRESHNESS_FIELD,
    INCLUSION_MODE,
    PRIMARY_KEYS,
    SOURCE_NAME,
    PartnerRewardRedemptionsRow,
)


class PartnerRewardRedemptionsExtractor(BaseExtractor):
    """
    Extractor for fct_partner_reward_redemptions.

    Incremental strategy:
    - watermark field: redeemed_at_utc
    - ordering: redeemed_at_utc, redemption_id

    PII boundary:
    - user_email is extracted faithfully from source truth.
    - The transformer MUST NOT write user_email to graph properties, DTOs,
      API responses, or log output. See module docstring PII WARNING.

    Append-oriented semantics:
    - Redemption events are written once and not updated. Incremental
      extraction is therefore complete and correct.

    No declared PK:
    - redemption_id is treated as the stable de facto key.
      Deduplication is a transformer concern.
    """

    source_name: str = SOURCE_NAME
    schema_row_class: type[WarehouseRow] = PartnerRewardRedemptionsRow
    inclusion_mode: str = INCLUSION_MODE
    freshness_field: str | None = FRESHNESS_FIELD     # redeemed_at_utc
    primary_key_fields: tuple[str, ...] = PRIMARY_KEYS
    default_chunk_size: int = 5000
    supports_incremental: bool = True

    # ── Source column contract ────────────────────────────────────────────────

    def get_source_columns(self) -> tuple[str, ...]:
        """
        Return the explicit ordered source columns for fct_partner_reward_redemptions.

        These columns must stay aligned with PartnerRewardRedemptionsRow.from_row().
        Adding or removing a column here requires a matching change in
        the schema row dataclass.

        ╔══════════════════════════════════════════════════════════════════╗
        ║  PII FIELD — user_email                                         ║
        ║  Source-only. MUST NOT cross the graph/DTO/API boundary.        ║
        ║  Transformer MUST drop or hash before any downstream storage.   ║
        ╚══════════════════════════════════════════════════════════════════╝

        reward_key note:
            FK to dim_partner_reward_catalog. Preserved exactly for REDEEMED
            edge construction routing to the correct PartnerReward node.

        transaction_amount note:
            DECIMAL(10,2) in the DWH; stored as float | None. Downstream
            financial aggregations should use precision-safe arithmetic.

        source_sequence note:
            Event ordering signal within the same event_created_at_utc
            bucket. Preserved for transformer-layer event sequencing.
        """
        return (
            "redemption_id",
            "reward_key",              # FK to dim_partner_reward_catalog
            "partner_name",
            "reward_title",
            "user_id",
            "user_email",              # ⚠ PII — source-only; MUST NOT reach graph/DTO/API
            "quantity",
            "transaction_amount",      # DECIMAL(10,2) — float | None
            "redeemed_at_utc",
            "redemption_date_key",     # INTEGER partition label; str | None
            "event_id",
            "event_type",
            "source_sequence",         # event ordering within same timestamp
            "event_created_at_utc",
        )

    # ── Query construction ────────────────────────────────────────────────────

    def build_base_query(self) -> str:
        """
        Return the base SELECT for fct_partner_reward_redemptions without
        incremental filtering.

        The incremental clause (WHERE redeemed_at_utc > %(watermark_value)s)
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
        Build the incremental filter using redeemed_at_utc.

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
        Return stable deterministic ordering for fct_partner_reward_redemptions.

        redeemed_at_utc first — aligns with watermark advancement and clusters
        output by redemption event time.

        redemption_id second — de facto key; breaks ties within the same
        redemption timestamp bucket deterministically.
        """
        return "\nORDER BY redeemed_at_utc, redemption_id"

    def build_pagination_clause(self, limit: int, offset: int) -> str:
        """
        Return LIMIT/OFFSET pagination clause.
        """
        return "\nLIMIT %(limit)s OFFSET %(offset)s"