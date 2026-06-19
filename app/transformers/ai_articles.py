"""
app/transformers/ai_articles.py
=================================
Transformer for dim_ai_articles → AIArticle nodes + GENERATED_FOR relationships.

Emits:
    - AIArticle node (one per row)
    - GENERATED_FOR rel (AIArticle → Match) when match_id present AND status == "published"
    - GENERATED_FOR rel (AIArticle → News) when published_news_id present

HAS_TAG (AIArticle → Tag) is NOT emitted here — AiArticlesRow carries no
tag_id fields. Tag associations must come from a dedicated tag junction source.

generation_succeeded is TINYINT — used as gate logic only (not written to properties).
Rows where generation_succeeded is falsy still produce AIArticle nodes;
only GENERATED_FOR to Match is gated on status == "published".
"""

from __future__ import annotations

from app.contracts.graph_records import GraphWriteBatch, NodeRecord, RelationshipRecord
from app.contracts.warehouse_rows import ExtractorBatch
from app.core.constants import AI_ARTICLE, GENERATED_FOR, MATCH, NEWS
from app.core.exceptions import CanonicalizationError, TransformationError
from app.core.ids import build_ai_article_id, build_fixture_id, build_news_id
from app.core.logging import log_transformation_finished, log_transformation_started
from app.schemas.warehouse.ai_articles import INCLUSION_MODE, SOURCE_NAME, AiArticlesRow
from app.transformers.base import BaseTransformer
from app.transformers.graph_record_builder import GraphRecordBuilder

_STATUS_PUBLISHED = "published"


class AiArticlesTransformer(BaseTransformer):
    """
    Transforms dim_ai_articles rows into AIArticle nodes and GENERATED_FOR
    relationship records.

    Merge key strategy: direct on article_id (declared in merge_keys.py).
    Node id: build_ai_article_id(row.article_id)
    """

    source_name = SOURCE_NAME        # "dim_ai_articles"
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
            row: AiArticlesRow
            try:
                node, row_rels = self._transform_row(row, builder)
                nodes.append(node)
                rels.extend(row_rels)
            except (TransformationError, CanonicalizationError) as exc:
                self._skip(str(exc), row_id=getattr(row, "article_id", None))
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
        row: AiArticlesRow,
        builder: GraphRecordBuilder,
    ) -> tuple[NodeRecord, list[RelationshipRecord]]:
        if not row.article_id:
            raise TransformationError(
                "AiArticlesRow missing required article_id",
                source=SOURCE_NAME,
            )

        node_id = build_ai_article_id(row.article_id)

        properties = {
            "article_type":     row.article_type,
            "content_category": row.content_category,
            "status":           row.status,
            "published_at":     self._ts(row.published_at_utc),
            "view_count":       row.view_count,
            "like_count":       row.like_count,
            "match_id":         str(row.match_id) if row.match_id is not None else None,
        }

        node = builder.node(AI_ARTICLE, node_id, properties)
        row_rels: list[RelationshipRecord] = []

        # GENERATED_FOR → Match: only when published and match_id present
        if row.match_id is not None and row.status == _STATUS_PUBLISHED:
            row_rels.append(builder.rel(
                GENERATED_FOR,
                node_id,
                build_fixture_id(row.match_id),
                start_label=AI_ARTICLE,
                end_label=MATCH,
            ))

        # GENERATED_FOR → News: when published_news_id present
        if row.published_news_id is not None:
            row_rels.append(builder.rel(
                GENERATED_FOR,
                node_id,
                build_news_id(row.published_news_id),
                start_label=AI_ARTICLE,
                end_label=NEWS,
            ))

        return node, row_rels