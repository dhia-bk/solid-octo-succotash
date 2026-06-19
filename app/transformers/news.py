"""
app/transformers/news.py
=========================
Transformer for dim_news → News nodes.

Emits News nodes only.
HAS_TAG (News → Tag) is NOT emitted here — NewsRow carries no tag_id fields.
Tag associations must come from a dedicated tag junction source.
"""

from __future__ import annotations

from app.contracts.graph_records import GraphWriteBatch, NodeRecord
from app.contracts.warehouse_rows import ExtractorBatch
from app.core.constants import NEWS
from app.core.exceptions import CanonicalizationError, TransformationError
from app.core.ids import build_news_id
from app.core.logging import log_transformation_finished, log_transformation_started
from app.schemas.warehouse.news import INCLUSION_MODE, SOURCE_NAME, NewsRow
from app.transformers.base import BaseTransformer
from app.transformers.graph_record_builder import GraphRecordBuilder


class NewsTransformer(BaseTransformer):
    """
    Transforms dim_news rows into News nodes.

    Merge key strategy: direct on news_id (declared in merge_keys.py).
    Node id: build_news_id(row.news_id) — news_id is int on row.
    """

    source_name = SOURCE_NAME        # "dim_news"
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
            row: NewsRow
            try:
                if row.news_id is None:
                    raise TransformationError(
                        "NewsRow missing required news_id",
                        source=SOURCE_NAME,
                    )

                node_id = build_news_id(row.news_id)

                properties = {
                    "title":        row.title,
                    "author":       row.author,
                    "url":          row.url,
                    "image":        row.image,
                    "published_at": self._ts(row.published_at_utc),
                    "is_active":    self._bool(row.is_active),
                }

                nodes.append(builder.node(NEWS, node_id, properties))

            except (TransformationError, CanonicalizationError) as exc:
                self._skip(str(exc), row_id=getattr(row, "news_id", None))
                continue

        log_transformation_finished(
            self._logger,
            record_count=len(nodes),
            table_name=SOURCE_NAME,
            run_id=self._run_id,
        )

        return builder.batch(nodes, [], batch_sequence=0)