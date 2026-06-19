"""
app/transformers/tags.py
=========================
Transformer for dim_tags → Tag nodes.

Emits Tag nodes only. HAS_TAG relationships (Post/News/AIArticle → Tag)
are written by posts.py, news.py, and ai_articles.py respectively.

trending_score is DECIMAL on the row — written as float (TagNode shape
declares float | None).
team_id and league_id are int on the row — converted to str for graph storage.
"""

from __future__ import annotations

from app.contracts.graph_records import GraphWriteBatch, NodeRecord
from app.contracts.warehouse_rows import ExtractorBatch
from app.core.constants import TAG
from app.core.exceptions import CanonicalizationError, TransformationError
from app.core.ids import build_tag_id
from app.core.logging import log_transformation_finished, log_transformation_started
from app.schemas.warehouse.tags import INCLUSION_MODE, SOURCE_NAME, TagsRow
from app.transformers.base import BaseTransformer
from app.transformers.graph_record_builder import GraphRecordBuilder


class TagsTransformer(BaseTransformer):
    """
    Transforms dim_tags rows into Tag nodes.

    Merge key strategy: direct on tag_id (declared in merge_keys.py).
    Node id: build_tag_id(row.tag_id) — tag_id is int on row.
    """

    source_name = SOURCE_NAME        # "dim_tags"
    inclusion_mode = INCLUSION_MODE  # GRAPH_CORE

    def transform(self, batch: ExtractorBatch) -> GraphWriteBatch:
        self._reset_skip_count()
        builder = GraphRecordBuilder(self._run_id, SOURCE_NAME)
        nodes: list[NodeRecord] = []

        log_transformation_started(
            self._logger,
            table_name=SOURCE_NAME,
            run_id=self._run_id,
        )

        for row in batch.rows:
            row: TagsRow
            try:
                if row.tag_id is None:
                    raise TransformationError(
                        "TagsRow missing required tag_id",
                        source=SOURCE_NAME,
                    )

                node_id = build_tag_id(row.tag_id)

                properties = {
                    "tag_name":       row.tag_name,
                    "tag_url":        row.tag_url,
                    "is_trending":    self._bool(row.is_trending),
                    "trending_score": row.trending_score,
                    "team_id":        str(row.team_id) if row.team_id is not None else None,
                    "league_id":      str(row.league_id) if row.league_id is not None else None,
                }

                nodes.append(builder.node(TAG, node_id, properties))

            except (TransformationError, CanonicalizationError) as exc:
                self._skip(str(exc), row_id=getattr(row, "tag_id", None))
                continue

        log_transformation_finished(
            self._logger,
            record_count=len(nodes),
            table_name=SOURCE_NAME,
            run_id=self._run_id,
        )

        return builder.batch(nodes, [], batch_sequence=0)