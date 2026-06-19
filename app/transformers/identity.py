"""
app/transformers/identity.py
=============================
Transformer for dim_users → User nodes + FAVORS relationships.

This is the primary identity transformer. Every User node in the graph
originates here. No other transformer creates User nodes.

Emits:
    - User node (one per row)
    - FAVORS rel (User → Team) when favorite_team_id is present

TINYINT fields coerced to bool:
    is_suspended, is_waiting, lockout_enabled,
    has_early_prediction_permission

Fields excluded from graph properties:
    - birthdate: not in UserNode shape
    - days_since_last_activity, days_since_last_payment: derived/volatile
    - blocks_given_count, blocks_received_count: not in UserNode shape
    - access_failed_count: operational/security field, not in UserNode shape
    - current_streak_count, longest_streak_count: not in UserNode shape
    - lifetime_* counters: not in UserNode shape
    - lockout_end_utc, ai_credits_expires_at_utc,
      ai_credits_last_reset_at_utc: not in UserNode shape
    - referred_by_user_id, referral_code: not in UserNode shape
    - has_early_prediction_permission: not in UserNode shape
    - is_waiting, lockout_enabled, access_failed_count: not in UserNode shape

Only properties declared on UserNode (nodes.py) and authorized via
may_source_write_property("dim_users", "User", prop) are written.
"""

from __future__ import annotations

from app.contracts.graph_records import GraphWriteBatch, NodeRecord, RelationshipRecord
from app.contracts.warehouse_rows import ExtractorBatch
from app.core.constants import FAVORS, TEAM, USER
from app.core.exceptions import CanonicalizationError, TransformationError
from app.core.ids import build_team_id, build_user_id
from app.core.logging import log_transformation_finished, log_transformation_started
from app.mappings.property_ownership import may_source_write_property
from app.schemas.warehouse.users import INCLUSION_MODE, SOURCE_NAME, UsersRow
from app.transformers.base import BaseTransformer
from app.transformers.graph_record_builder import GraphRecordBuilder


class IdentityTransformer(BaseTransformer):
    """
    Transforms dim_users rows into User nodes and FAVORS relationships.

    Merge key strategy: direct on user_id (declared in merge_keys.py).
    Node id:           build_user_id(row.user_id)
    Relationships:     FAVORS (User → Team) when favorite_team_id is not None.

    Property authority: all User properties written here are owned by
    dim_users per property_ownership.py. may_source_write_property() is
    called for every key before inclusion.
    """

    source_name = SOURCE_NAME      # "dim_users"
    inclusion_mode = INCLUSION_MODE  # GRAPH_CORE

    def transform(self, batch: ExtractorBatch) -> GraphWriteBatch:
        """
        Transform a batch of UsersRow instances into User nodes and
        FAVORS relationship records.

        Args:
            batch: ExtractorBatch from the dim_users extractor.

        Returns:
            GraphWriteBatch containing NodeRecord and RelationshipRecord
            instances.
        """
        self._reset_skip_count()
        builder = GraphRecordBuilder(self._run_id, SOURCE_NAME)
        nodes: list[NodeRecord] = []
        rels: list[RelationshipRecord] = []

        log_transformation_started(
            self._logger,
            table_name=SOURCE_NAME,
            run_id=self._run_id,
        )

        for row in batch.rows:
            row: UsersRow
            try:
                node, favors_rel = self._transform_row(row, builder)
                nodes.append(node)
                if favors_rel is not None:
                    rels.append(favors_rel)

            except (TransformationError, CanonicalizationError) as exc:
                self._skip(str(exc), row_id=getattr(row, "user_id", None))
                continue

        log_transformation_finished(
            self._logger,
            record_count=len(nodes) + len(rels),
            table_name=SOURCE_NAME,
            run_id=self._run_id,
        )

        return builder.batch(nodes, rels, batch_sequence=0)

    # -- Row-level transform --------------------------------------------------

    def _transform_row(
        self,
        row: UsersRow,
        builder: GraphRecordBuilder,
    ) -> tuple[NodeRecord, RelationshipRecord | None]:
        """
        Transform a single UsersRow into a User NodeRecord and optional
        FAVORS RelationshipRecord.

        Args:
            row:     Typed UsersRow instance.
            builder: GraphRecordBuilder pre-filled with run_id and source.

        Returns:
            Tuple of (NodeRecord, RelationshipRecord | None).

        Raises:
            TransformationError: If user_id is missing.
        """
        if not row.user_id:
            raise TransformationError(
                "UsersRow missing required user_id",
                source=SOURCE_NAME,
            )

        node_id = build_user_id(row.user_id)
        properties = self._build_user_properties(row)
        node = builder.node(USER, node_id, properties)

        favors_rel = self._build_favors_rel(row, node_id, builder)

        return node, favors_rel

    # -- Property builder -----------------------------------------------------

    def _build_user_properties(self, row: UsersRow) -> dict:
        """
        Build the User node property dict from a UsersRow.

        Only properties declared on UserNode (nodes.py) are included.
        Each key is checked via may_source_write_property() before inclusion.
        datetime fields are converted to ISO strings via self._ts().
        TINYINT fields are converted to bool via self._bool().

        Args:
            row: Typed UsersRow instance.

        Returns:
            PII-free property dict ready for NodeRecord construction.
        """
        candidates: dict = {
            "user_name":                  row.user_name,
            "full_name":                  row.full_name,
            "country":                    row.country,
            "gender":                     row.gender,
            "age":                        row.age,
            "birthdate":                  row.birthdate,
            "user_created_at":            self._ts(row.user_created_at_utc),
            "last_activity_at":           self._ts(row.last_activity_at_utc),
            "favorite_team_id":           row.favorite_team_id,
            "current_subscription_name":  row.current_subscription_name,
            "is_suspended":               self._bool(row.is_suspended),
            "duel_rating":                row.duel_rating,
            "avatar_id":                  str(row.avatar_id) if row.avatar_id is not None else None,
            "avatar_category":            row.avatar_category,
            "auth_provider":              row.auth_provider,
            "all_auth_providers":         row.all_auth_providers,
            "ai_total_credits":           row.ai_total_credits,
            "ai_remaining_credits":       row.ai_remaining_credits,
            "last_payment_at":            self._ts(row.last_payment_at_utc),
            "notif_total_received":       row.notif_total_received,
            "notif_total_read":           row.notif_total_read,
        }

        return {
            key: value
            for key, value in candidates.items()
            if may_source_write_property(SOURCE_NAME, "User", key)
        }

    # -- Relationship builder -------------------------------------------------

    def _build_favors_rel(
        self,
        row: UsersRow,
        user_node_id: str,
        builder: GraphRecordBuilder,
    ) -> RelationshipRecord | None:
        """
        Build a FAVORS relationship (User → Team) if favorite_team_id exists.

        No endpoint spec is declared in ENDPOINT_SPECS for FAVORS — direct
        id construction via build_team_id().

        Args:
            row:          Typed UsersRow instance.
            user_node_id: Pre-built User node id.
            builder:      GraphRecordBuilder pre-filled with run_id and source.

        Returns:
            RelationshipRecord or None if favorite_team_id is absent.
        """
        if not row.favorite_team_id:
            return None

        team_node_id = build_team_id(row.favorite_team_id)

        return builder.rel(
            FAVORS,
            user_node_id,
            team_node_id,
            start_label=USER,
            end_label=TEAM,
        )