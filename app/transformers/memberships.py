"""
app/transformers/memberships.py
================================
Transformer for dim_private_league_members → MEMBER_OF relationships.

Emits MEMBER_OF (User → PrivateLeague) relationship records only.
No new nodes are created.

Merge key strategy (from merge_keys.py):
    fallback on membership_id; composite (private_league_id, user_id) when
    membership_id is None.

Endpoint resolution (from endpoint_resolution.py):
    MEMBER_OF start: direct user_id
    MEMBER_OF end:   direct private_league_id
    Neither endpoint requires canonicalization.

activity_weight is computed via WeightingEngine using the fields available
on the membership row. chat_message_count is not present on this source —
it defaults to 0 via the weighting config.
"""

from __future__ import annotations

from app.canonicalization.base import BaseCanonicalizer
from app.contracts.graph_records import GraphWriteBatch, RelationshipRecord
from app.contracts.warehouse_rows import ExtractorBatch
from app.core.constants import MEMBER_OF, PRIVATE_LEAGUE, USER
from app.core.exceptions import CanonicalizationError, TransformationError
from app.core.ids import build_private_league_id, build_user_id
from app.core.logging import log_transformation_finished, log_transformation_started
from app.mappings.registry import MappingRegistry
from app.schemas.warehouse.private_league_members import (
    INCLUSION_MODE,
    SOURCE_NAME,
    PrivateLeagueMembersRow,
)
from app.transformers.base import BaseTransformer
from app.transformers.graph_record_builder import GraphRecordBuilder
from app.transformers.weighting import WeightingEngine, build_weighting_engine

# Roles that qualify for the moderator bonus in activity_weight computation
_MODERATOR_ROLES: frozenset[str] = frozenset({"owner", "admin", "moderator"})


class MembershipsTransformer(BaseTransformer):
    """
    Transforms dim_private_league_members rows into MEMBER_OF relationship
    records.

    Merge key: fallback on membership_id → composite (private_league_id, user_id).
    Node id:   not applicable — relationship-only transformer.
    """

    source_name = SOURCE_NAME        # "dim_private_league_members"
    inclusion_mode = INCLUSION_MODE  # GRAPH_CORE

    def __init__(
        self,
        run_id: str,
        canonicalizer_registry: dict[str, BaseCanonicalizer] | None = None,
        mapping_registry: MappingRegistry | None = None,
        weighting_engine: WeightingEngine | None = None,
    ) -> None:
        super().__init__(run_id, canonicalizer_registry, mapping_registry)
        self._weighting = weighting_engine or build_weighting_engine()

    def transform(self, batch: ExtractorBatch) -> GraphWriteBatch:
        """
        Transform a batch of PrivateLeagueMembersRow instances into
        MEMBER_OF relationship records.

        Args:
            batch: ExtractorBatch from the dim_private_league_members extractor.

        Returns:
            GraphWriteBatch containing MEMBER_OF RelationshipRecord instances.
        """
        self._reset_skip_count()
        builder = GraphRecordBuilder(self._run_id, SOURCE_NAME)
        rels: list[RelationshipRecord] = []

        log_transformation_started(
            self._logger,
            table_name=SOURCE_NAME,
            run_id=self._run_id,
        )

        for row in batch.rows:
            row: PrivateLeagueMembersRow
            try:
                rel = self._transform_row(row, builder)
                if rel is not None:
                    rels.append(rel)
            except (TransformationError, CanonicalizationError) as exc:
                self._skip(str(exc), row_id=getattr(row, "membership_id", None))
                continue

        log_transformation_finished(
            self._logger,
            record_count=len(rels),
            table_name=SOURCE_NAME,
            run_id=self._run_id,
        )

        return builder.batch([], rels, batch_sequence=0)

    # -- Row-level transform --------------------------------------------------

    def _transform_row(
        self,
        row: PrivateLeagueMembersRow,
        builder: GraphRecordBuilder,
    ) -> RelationshipRecord | None:
        """
        Transform a single PrivateLeagueMembersRow into a MEMBER_OF
        RelationshipRecord.

        Returns None (with skip logged) if required endpoint ids are missing.

        Args:
            row:     Typed PrivateLeagueMembersRow instance.
            builder: GraphRecordBuilder pre-filled with run_id and source.

        Returns:
            RelationshipRecord or None.
        """
        if not row.user_id:
            self._skip(
                "user_id is None — skipping MEMBER_OF rel",
                row_id=row.membership_id,
            )
            return None

        if row.private_league_id is None:
            self._skip(
                "private_league_id is None — skipping MEMBER_OF rel",
                row_id=row.membership_id,
            )
            return None

        user_node_id = build_user_id(row.user_id)
        league_node_id = build_private_league_id(row.private_league_id)

        is_active_bool = self._bool(row.is_active)
        is_moderator = row.role in _MODERATOR_ROLES if row.role else False

        activity_weight = self._weighting.compute_membership_weight(
            fixture_participation_count=row.fixture_participation_count,
            chat_message_count=None,   # not available on membership row → defaults to 0
            last_active_at=row.last_active_at_utc,
            joined_at=row.joined_at,
            is_moderator=is_moderator,
        )

        properties = {
            "role":            row.role,
            "joined_at":       self._ts(row.joined_at),
            "is_active":       is_active_bool,
            "activity_weight": activity_weight,
        }

        return builder.rel(
            MEMBER_OF,
            user_node_id,
            league_node_id,
            start_label=USER,
            end_label=PRIVATE_LEAGUE,
            properties=properties,
        )