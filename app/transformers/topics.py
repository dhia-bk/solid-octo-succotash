"""
app/transformers/topics.py
===========================
Transformer for fct_topics → Topic nodes + DISCUSSED relationships.

Emits:
    - Topic node (one per row)
    - DISCUSSED rel (User → Topic) when user_id is present

Node id resolution:
    1. Try TopicCanonicalizer.resolve(row.topic_label) — if resolved,
       use canonical_form.canonical_id as node id (deduplicates topic
       variants that map to the same canonical label).
    2. Fall back to build_topic_id(row.id) when canonicalization returns
       None (topic label is unknown or canonicalizer not injected).

Fields excluded from TopicNode shape:
    reasoning, model_provider
"""

from __future__ import annotations

from app.canonicalization.topics import TopicCanonicalizer
from app.contracts.graph_records import GraphWriteBatch, NodeRecord, RelationshipRecord
from app.contracts.warehouse_rows import ExtractorBatch
from app.core.constants import DISCUSSED, TOPIC, USER
from app.core.exceptions import CanonicalizationError, TransformationError
from app.core.ids import build_topic_id, build_user_id
from app.core.logging import log_transformation_finished, log_transformation_started
from app.mappings.registry import MappingRegistry
from app.schemas.warehouse.topics import INCLUSION_MODE, SOURCE_NAME, TopicsRow
from app.transformers.base import BaseTransformer
from app.transformers.graph_record_builder import GraphRecordBuilder

_TOPICS_CANONICALIZER_DOMAIN = "topics"


class TopicsTransformer(BaseTransformer):
    """
    Transforms fct_topics rows into Topic nodes and DISCUSSED relationship
    records.

    Merge key strategy: direct on id (declared in merge_keys.py).
    Node id: canonical_form.canonical_id if topic_label resolves,
             else build_topic_id(row.id).

    TopicCanonicalizer injection is optional — if not provided the
    transformer falls back to raw id construction for all rows.
    """

    source_name = SOURCE_NAME        # "fct_topics"
    inclusion_mode = INCLUSION_MODE  # GRAPH_CORE

    def transform(self, batch: ExtractorBatch) -> GraphWriteBatch:
        self._reset_skip_count()
        builder = GraphRecordBuilder(self._run_id, SOURCE_NAME)
        nodes: list[NodeRecord] = []
        rels: list[RelationshipRecord] = []

        # Canonicalizer is optional
        topic_canon: TopicCanonicalizer | None = self._canonicalizers.get(_TOPICS_CANONICALIZER_DOMAIN)  # type: ignore[assignment]

        log_transformation_started(
            self._logger,
            table_name=SOURCE_NAME,
            run_id=self._run_id,
        )

        for row in batch.rows:
            row: TopicsRow
            try:
                node, discussed_rel = self._transform_row(row, builder, topic_canon)
                nodes.append(node)
                if discussed_rel is not None:
                    rels.append(discussed_rel)
            except (TransformationError, CanonicalizationError) as exc:
                self._skip(str(exc), row_id=getattr(row, "id", None))
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
        row: TopicsRow,
        builder: GraphRecordBuilder,
        topic_canon: TopicCanonicalizer | None,
    ) -> tuple[NodeRecord, RelationshipRecord | None]:
        # Resolve node id — canonical if possible, raw otherwise
        node_id = self._resolve_topic_id(row, topic_canon)

        properties = {
            "topic_label":  row.topic_label,
            "source_type":  row.source_type,
            "item_id":      row.item_id,
            "user_id":      row.user_id,
            "processed_at": self._ts(row.processed_at),
            "model_version": row.model_version,
        }

        node = builder.node(TOPIC, node_id, properties)
        discussed_rel = self._build_discussed_rel(row, node_id, builder)

        return node, discussed_rel

    # -- Id resolution --------------------------------------------------------

    def _resolve_topic_id(
        self,
        row: TopicsRow,
        topic_canon: TopicCanonicalizer | None,
    ) -> str:
        """
        Resolve the Topic node id.

        Attempts canonical resolution when a canonicalizer is available and
        topic_label is not None. Falls back to raw id on any failure.
        """
        if topic_canon is not None and row.topic_label:
            canonical_form = topic_canon.resolve_label(row.topic_label)
            if canonical_form is not None:
                return canonical_form.canonical_id

        return build_topic_id(row.id)

    # -- Relationship builder -------------------------------------------------

    def _build_discussed_rel(
        self,
        row: TopicsRow,
        topic_node_id: str,
        builder: GraphRecordBuilder,
    ) -> RelationshipRecord | None:
        if not row.user_id:
            return None

        return builder.rel(
            DISCUSSED,
            build_user_id(row.user_id),
            topic_node_id,
            start_label=USER,
            end_label=TOPIC,
        )