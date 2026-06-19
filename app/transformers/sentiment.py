"""
app/transformers/sentiment.py
==============================
Transformer for fct_sentiment → Sentiment nodes + EXPRESSED relationships.

Emits:
    - Sentiment node (one per row)
    - EXPRESSED rel (User → Sentiment) when user_id is present

No declared PK in the DWH. Synthetic node id built via
stable_hash_key(source_type, item_id, user_id). Rows where all three
composite key fields are None are skipped — no stable identity exists.

Fields excluded from SentimentNode shape:
    created_at, model_provider, pipeline_run_id, text_hash
"""

from __future__ import annotations

from app.contracts.graph_records import GraphWriteBatch, NodeRecord, RelationshipRecord
from app.contracts.warehouse_rows import ExtractorBatch
from app.core.constants import EXPRESSED, SENTIMENT, USER
from app.core.exceptions import CanonicalizationError, TransformationError
from app.core.ids import build_user_id, stable_hash_key
from app.core.logging import log_transformation_finished, log_transformation_started
from app.schemas.warehouse.sentiment import INCLUSION_MODE, SOURCE_NAME, SentimentRow
from app.transformers.base import BaseTransformer
from app.transformers.graph_record_builder import GraphRecordBuilder


class SentimentTransformer(BaseTransformer):
    """
    Transforms fct_sentiment rows into Sentiment nodes and EXPRESSED
    relationship records.

    Merge key strategy: synthetic_hash on (source_type, item_id, user_id).
    Node id: stable_hash_key(row.source_type, row.item_id, row.user_id)
    """

    source_name = SOURCE_NAME        # "fct_sentiment"
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
            row: SentimentRow
            try:
                node, expressed_rel = self._transform_row(row, builder)
                nodes.append(node)
                if expressed_rel is not None:
                    rels.append(expressed_rel)
            except (TransformationError, CanonicalizationError) as exc:
                self._skip(str(exc), row_id=None)
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
        row: SentimentRow,
        builder: GraphRecordBuilder,
    ) -> tuple[NodeRecord, RelationshipRecord | None]:
        # All three composite key fields must be present for a stable id
        if not row.source_type or not row.item_id or not row.user_id:
            raise TransformationError(
                "SentimentRow missing required composite key fields "
                "(source_type, item_id, user_id)",
                source=SOURCE_NAME,
                source_type=row.source_type,
                item_id=row.item_id,
                user_id=row.user_id,
            )

        node_id = stable_hash_key(row.source_type, row.item_id, row.user_id)

        properties = {
            "source_type":     row.source_type,
            "item_id":         row.item_id,
            "user_id":         row.user_id,
            "sentiment_label": row.sentiment_label,
            "score_positive":  row.score_positive,
            "score_negative":  row.score_negative,
            "score_neutral":   row.score_neutral,
            "language_code":   row.language_code,
            "processed_at":    self._ts(row.processed_at),
        }

        node = builder.node(SENTIMENT, node_id, properties)

        expressed_rel = builder.rel(
            EXPRESSED,
            build_user_id(row.user_id),
            node_id,
            start_label=USER,
            end_label=SENTIMENT,
        )

        return node, expressed_rel