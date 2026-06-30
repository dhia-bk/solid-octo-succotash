"""
app/transformers/posts.py
==========================
Transformer for dim_posts → Post nodes + POSTED relationships.

Emits:
    - Post node (one per row)
    - POSTED rel (User → Post) when author_user_id is present

HAS_TAG (Post → Tag) is NOT emitted here — PostsRow carries no tag_id
fields. Tag associations must come from a dedicated tag junction source.

Fields on PostsRow excluded from PostNode shape:
    description, content, url, image, video,
    clap_count, fire_count, football_count,
    thumbs_down_count, thumbs_up_count
"""

from __future__ import annotations

from app.contracts.graph_records import GraphWriteBatch, NodeRecord, RelationshipRecord
from app.contracts.warehouse_rows import ExtractorBatch
from app.core.constants import POST, POSTED, USER
from app.core.exceptions import CanonicalizationError, TransformationError
from app.core.ids import build_post_id, build_user_id
from app.core.logging import log_transformation_finished, log_transformation_started
from app.schemas.warehouse.posts import INCLUSION_MODE, SOURCE_NAME, PostsRow
from app.transformers.base import BaseTransformer
from app.transformers.graph_record_builder import GraphRecordBuilder


class PostsTransformer(BaseTransformer):
    """
    Transforms dim_posts rows into Post nodes and POSTED relationship records.

    Merge key strategy:
        Node:    direct on post_id
        POSTED:  composite on (user_id, post_id)

    Node id:  build_post_id(row.post_id)
    """

    source_name = SOURCE_NAME        # "dim_posts"
    inclusion_mode = INCLUSION_MODE  # GRAPH_CORE

    def transform(self, batch: ExtractorBatch) -> GraphWriteBatch:
        """
        Transform a batch of PostsRow instances into Post node and POSTED
        relationship records.

        Args:
            batch: ExtractorBatch from the dim_posts extractor.

        Returns:
            GraphWriteBatch containing Post NodeRecord and POSTED
            RelationshipRecord instances.
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
            row: PostsRow
            try:
                node, posted_rel = self._transform_row(row, builder)
                nodes.append(node)
                if posted_rel is not None:
                    rels.append(posted_rel)
            except (TransformationError, CanonicalizationError) as exc:
                self._skip(str(exc), row_id=getattr(row, "post_id", None))
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
        row: PostsRow,
        builder: GraphRecordBuilder,
    ) -> tuple[NodeRecord, RelationshipRecord | None]:
        if not row.post_id:
            raise TransformationError(
                "PostsRow missing required post_id",
                source=SOURCE_NAME,
            )

        node_id = build_post_id(row.post_id)

        properties = {
            "author_user_id": row.author_user_id,
            "title":          row.title,
            "description":    row.description,
            "content":        row.content,
            "published_at":   self._ts(row.published_at_utc),
            "like_count":     row.like_count,
            "view_count":     row.view_count,
            "is_active":      self._bool(row.is_active),
        }

        node = builder.node(POST, node_id, properties)
        posted_rel = self._build_posted_rel(row, node_id, builder)

        return node, posted_rel

    # -- Relationship builder -------------------------------------------------

    def _build_posted_rel(
        self,
        row: PostsRow,
        post_node_id: str,
        builder: GraphRecordBuilder,
    ) -> RelationshipRecord | None:
        """
        Build POSTED (User → Post) rel. Returns None if author_user_id is absent.
        """
        if not row.author_user_id:
            self._skip(
                "author_user_id is None — skipping POSTED rel",
                row_id=row.post_id,
            )
            return None

        user_node_id = build_user_id(row.author_user_id)

        return builder.rel(
            POSTED,
            user_node_id,
            post_node_id,
            start_label=USER,
            end_label=POST,
            properties={"published_at": self._ts(row.published_at_utc)},
        )