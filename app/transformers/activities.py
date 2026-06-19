"""
app/transformers/activities.py
================================
Transformer for fct_user_activities → LIKED, ANSWERED, FRIENDED relationships.

Dispatches on activity_type to emit the appropriate relationship.

Activity type mapping:
    like_given            → LIKED    (User → Post)
    post_like             → LIKED    (User → Post)
    comment_like          → LIKED    (User → Comment)
    fixture_poll_answered → ANSWERED (User → Poll)
    friend_added          → FRIENDED (User → User)

Skipped activity types (handled by dedicated transformers or not modelled):
    chat_message_reaction — no ChatMessage node in graph schema
    comment_created       — covered by comments.py
    post_created          — covered by posts.py
    joined_private_league — covered by memberships.py
    prediction_duel       — covered by duels.py

Endpoint resolution:
    All endpoints are direct_id — no canonicalization required.
    End node id builders dispatch per activity_type.
"""

from __future__ import annotations

from app.contracts.graph_records import GraphWriteBatch, RelationshipRecord
from app.contracts.warehouse_rows import ExtractorBatch
from app.core.constants import ANSWERED, COMMENT, FRIENDED, LIKED, POLL, POST, USER
from app.core.exceptions import CanonicalizationError, TransformationError
from app.core.ids import build_comment_id, build_poll_id, build_post_id, build_user_id
from app.core.logging import log_transformation_finished, log_transformation_started
from app.schemas.warehouse.user_activities import (
    INCLUSION_MODE,
    SOURCE_NAME,
    UserActivitiesRow,
)
from app.transformers.base import BaseTransformer
from app.transformers.graph_record_builder import GraphRecordBuilder

# Activity types this transformer handles
_LIKE_POST_TYPES: frozenset[str] = frozenset({"like_given", "post_like"})
_LIKE_COMMENT_TYPE: str = "comment_like"
_POLL_ANSWER_TYPE: str = "fixture_poll_answered"
_FRIEND_TYPE: str = "friend_added"

# Activity types explicitly handled by other transformers or not modelled
_SKIP_TYPES: frozenset[str] = frozenset({
    "chat_message_reaction",  # no ChatMessage node in graph schema
    "comment_created",        # covered by comments.py
    "post_created",           # covered by posts.py
    "joined_private_league",  # covered by memberships.py
    "prediction_duel",        # covered by duels.py
})


class ActivitiesTransformer(BaseTransformer):
    """
    Transforms fct_user_activities rows into LIKED, ANSWERED, and FRIENDED
    relationship records.

    Merge key strategy: composite on (user_id, activity_id) for all three
    rel types (declared in merge_keys.py).

    Rows with unrecognised activity_type are silently skipped — new activity
    types added to the DWH are ignored until explicitly mapped here.
    """

    source_name = SOURCE_NAME        # "fct_user_activities"
    inclusion_mode = INCLUSION_MODE  # GRAPH_ENRICHMENT

    def transform(self, batch: ExtractorBatch) -> GraphWriteBatch:
        self._reset_skip_count()
        builder = GraphRecordBuilder(self._run_id, SOURCE_NAME)
        rels: list[RelationshipRecord] = []

        log_transformation_started(
            self._logger,
            table_name=SOURCE_NAME,
            run_id=self._run_id,
        )

        for row in batch.rows:
            row: UserActivitiesRow
            try:
                rel = self._transform_row(row, builder)
                if rel is not None:
                    rels.append(rel)
            except (TransformationError, CanonicalizationError) as exc:
                self._skip(str(exc), row_id=getattr(row, "activity_id", None))
                continue

        log_transformation_finished(
            self._logger,
            record_count=len(rels),
            table_name=SOURCE_NAME,
            run_id=self._run_id,
        )

        return builder.batch([], rels, batch_sequence=0)

    # -- Row-level dispatch ---------------------------------------------------

    def _transform_row(
        self,
        row: UserActivitiesRow,
        builder: GraphRecordBuilder,
    ) -> RelationshipRecord | None:
        activity_type = row.activity_type

        # Skip types handled elsewhere or not modelled
        if activity_type is None or activity_type in _SKIP_TYPES:
            return None

        if not row.user_id:
            self._skip(
                "user_id is None — skipping activity row",
                row_id=row.activity_id,
                activity_type=activity_type,
            )
            return None

        if not row.target_id:
            self._skip(
                "target_id is None — skipping activity row",
                row_id=row.activity_id,
                activity_type=activity_type,
            )
            return None

        if activity_type in _LIKE_POST_TYPES:
            return self._build_liked_post_rel(row, builder)

        if activity_type == _LIKE_COMMENT_TYPE:
            return self._build_liked_comment_rel(row, builder)

        if activity_type == _POLL_ANSWER_TYPE:
            return self._build_answered_rel(row, builder)

        if activity_type == _FRIEND_TYPE:
            return self._build_friended_rel(row, builder)

        # Unknown activity type — log and skip
        self._logger.debug(
            "Unrecognised activity_type — skipping",
            extra={"activity_type": activity_type, "activity_id": row.activity_id},
        )
        return None

    # -- Relationship builders ------------------------------------------------

    def _build_liked_post_rel(
        self,
        row: UserActivitiesRow,
        builder: GraphRecordBuilder,
    ) -> RelationshipRecord:
        return builder.rel(
            LIKED,
            build_user_id(row.user_id),
            build_post_id(row.target_id),
            start_label=USER,
            end_label=POST,
            properties={
                "target_type": "Post",
                "activity_at": self._ts(row.activity_at_utc),
            },
        )

    def _build_liked_comment_rel(
        self,
        row: UserActivitiesRow,
        builder: GraphRecordBuilder,
    ) -> RelationshipRecord:
        return builder.rel(
            LIKED,
            build_user_id(row.user_id),
            build_comment_id(row.target_id),
            start_label=USER,
            end_label=COMMENT,
            properties={
                "target_type": "Comment",
                "activity_at": self._ts(row.activity_at_utc),
            },
        )

    def _build_answered_rel(
        self,
        row: UserActivitiesRow,
        builder: GraphRecordBuilder,
    ) -> RelationshipRecord:
        return builder.rel(
            ANSWERED,
            build_user_id(row.user_id),
            build_poll_id(row.target_id),
            start_label=USER,
            end_label=POLL,
            properties={"activity_at": self._ts(row.activity_at_utc)},
        )

    def _build_friended_rel(
        self,
        row: UserActivitiesRow,
        builder: GraphRecordBuilder,
    ) -> RelationshipRecord:
        return builder.rel(
            FRIENDED,
            build_user_id(row.user_id),
            build_user_id(row.target_id),
            start_label=USER,
            end_label=USER,
            properties={"activity_at": self._ts(row.activity_at_utc)},
        )