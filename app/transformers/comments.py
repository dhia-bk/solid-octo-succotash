"""
app/transformers/comments.py
=============================
Transformer for dim_comments → Comment nodes + COMMENTED and REPLIES_TO
relationships.

Emits:
    - Comment node (one per row)
    - COMMENTED rel (User → Comment) when user_id is present
    - REPLIES_TO rel (Comment → Comment) when parent_comment_id is present

Fields on CommentsRow excluded from CommentNode shape:
    content, clap_count, fire_count, football_count,
    thumbs_down_count, thumbs_up_count
"""

from __future__ import annotations

from app.contracts.graph_records import GraphWriteBatch, NodeRecord, RelationshipRecord
from app.contracts.warehouse_rows import ExtractorBatch
from app.core.constants import COMMENT, COMMENTED, REPLIES_TO, USER
from app.core.exceptions import CanonicalizationError, TransformationError
from app.core.ids import build_comment_id, build_user_id
from app.core.logging import log_transformation_finished, log_transformation_started
from app.schemas.warehouse.comments import INCLUSION_MODE, SOURCE_NAME, CommentsRow
from app.transformers.base import BaseTransformer
from app.transformers.graph_record_builder import GraphRecordBuilder


class CommentsTransformer(BaseTransformer):
    """
    Transforms dim_comments rows into Comment nodes, COMMENTED and
    REPLIES_TO relationship records.

    Merge key strategy:
        Node:      direct on comment_id
        COMMENTED: composite on (user_id, comment_id)
        REPLIES_TO: no merge key spec — direct construction from comment_id
                    and parent_comment_id
    """

    source_name = SOURCE_NAME        # "dim_comments"
    inclusion_mode = INCLUSION_MODE  # GRAPH_CORE

    def transform(self, batch: ExtractorBatch) -> GraphWriteBatch:
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
            row: CommentsRow
            try:
                node, row_rels = self._transform_row(row, builder)
                nodes.append(node)
                rels.extend(row_rels)
            except (TransformationError, CanonicalizationError) as exc:
                self._skip(str(exc), row_id=getattr(row, "comment_id", None))
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
        row: CommentsRow,
        builder: GraphRecordBuilder,
    ) -> tuple[NodeRecord, list[RelationshipRecord]]:
        if not row.comment_id:
            raise TransformationError(
                "CommentsRow missing required comment_id",
                source=SOURCE_NAME,
            )

        node_id = build_comment_id(row.comment_id)

        properties = {
            "user_id":           row.user_id,
            "post_id":           row.post_id,
            "parent_comment_id": row.parent_comment_id,
            "created_at":        self._ts(row.created_at_utc),
            "like_count":        row.like_count,
        }

        node = builder.node(COMMENT, node_id, properties)
        row_rels: list[RelationshipRecord] = []

        commented_rel = self._build_commented_rel(row, node_id, builder)
        if commented_rel is not None:
            row_rels.append(commented_rel)

        replies_to_rel = self._build_replies_to_rel(row, node_id, builder)
        if replies_to_rel is not None:
            row_rels.append(replies_to_rel)

        return node, row_rels

    # -- Relationship builders ------------------------------------------------

    def _build_commented_rel(
        self,
        row: CommentsRow,
        comment_node_id: str,
        builder: GraphRecordBuilder,
    ) -> RelationshipRecord | None:
        if not row.user_id:
            self._skip(
                "user_id is None — skipping COMMENTED rel",
                row_id=row.comment_id,
            )
            return None

        return builder.rel(
            COMMENTED,
            build_user_id(row.user_id),
            comment_node_id,
            start_label=USER,
            end_label=COMMENT,
            properties={"created_at": self._ts(row.created_at_utc)},
        )

    def _build_replies_to_rel(
        self,
        row: CommentsRow,
        comment_node_id: str,
        builder: GraphRecordBuilder,
    ) -> RelationshipRecord | None:
        """
        Build REPLIES_TO (child Comment → parent Comment).
        No endpoint spec declared — direct id construction.
        """
        if not row.parent_comment_id:
            return None

        return builder.rel(
            REPLIES_TO,
            comment_node_id,
            build_comment_id(row.parent_comment_id),
            start_label=COMMENT,
            end_label=COMMENT,
        )