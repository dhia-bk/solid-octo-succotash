"""
Relationship loader — loads RelationshipRecord instances from a GraphWriteBatch.

Flow per batch:
1. validate_graph_write_batch(batch) — pre-load validation
2. Group RelationshipRecords by (rel_type, source_name, end_label)
3. For each group, look up merge query from MergeQueryRegistry
4. Delegate to BatchWriter.write_relationships()
5. Return LoadResult
"""

from __future__ import annotations

from collections import defaultdict
from time import perf_counter

from app.contracts.graph_records import GraphWriteBatch, RelationshipRecord
from app.core.constants import DEFAULT_BATCH_SIZE
from app.core.logging import get_logger, log_event, log_load_finished, log_load_started
from app.db.neo4j_client import Neo4jClient
from app.loaders.base import BaseLoader, LoadResult
from app.loaders.batch_writer import BatchWriter
from app.loaders.node_loader import MergeQueryRegistry
from app.validation.transform_checks import validate_graph_write_batch


class RelationshipLoader(BaseLoader):
    """
    Loads RelationshipRecord instances from a GraphWriteBatch into Neo4j.

    Groups RelationshipRecords by (rel_type, source_name, end_label), looks up
    the merge query from the registry, and delegates to BatchWriter.
    """

    def __init__(
        self,
        neo4j_client: Neo4jClient,
        run_id: str,
        merge_query_registry: MergeQueryRegistry,
        batch_size: int = DEFAULT_BATCH_SIZE,
        dry_run: bool = False,
    ) -> None:
        super().__init__(neo4j_client, run_id, dry_run)
        self._registry = merge_query_registry
        self._writer = BatchWriter(
            neo4j_client=neo4j_client,
            run_id=run_id,
            batch_size=batch_size,
            dry_run=dry_run,
        )

    def load(self, batch: GraphWriteBatch) -> LoadResult:
        """
        Load all RelationshipRecord instances from a GraphWriteBatch into Neo4j.
        """
        started = perf_counter()
        result = LoadResult(source_name=batch.source_name, run_id=self._run_id)

        log_load_started(
            self._logger,
            run_id=self._run_id,
            batch_id=batch.batch_id,
            source_name=batch.source_name,
            rel_count=batch.relationship_count(),
        )

        # Pre-load validation
        validation_results = validate_graph_write_batch(batch, self._run_id)
        critical_or_error = [
            r for r in validation_results if r.severity in ("CRITICAL", "ERROR") and not r.passed
        ]
        if critical_or_error:
            error_msgs = [r.message for r in critical_or_error]
            result.errors.extend(error_msgs)
            result.duration_seconds = self._elapsed(started)
            log_event(
                self._logger,
                event_name="rel_loader_validation_failed",
                message="Batch validation failed; aborting relationship load",
                error_count=len(error_msgs),
                batch_id=batch.batch_id,
            )
            return result

        if not batch.relationship_records:
            result.duration_seconds = self._elapsed(started)
            return result

        # Group by (rel_type, source_name, end_label)
        groups: dict[tuple[str, str, str], list[RelationshipRecord]] = defaultdict(list)
        for rec in batch.relationship_records:
            groups[(rec.rel_type, rec.source_name, rec.end_label)].append(rec)

        for (rel_type, source_name, end_label), records in groups.items():
            written, skipped = self.load_relationships_for_type(
                rel_type, source_name, records, end_label=end_label
            )
            result.relationships_written += written
            result.relationships_skipped += skipped
            result.batch_count += 1

        result.duration_seconds = self._elapsed(started)

        log_load_finished(
            self._logger,
            run_id=self._run_id,
            batch_id=batch.batch_id,
            record_count=result.relationships_written,
            duration_ms=int(result.duration_seconds * 1000),
            source_name=batch.source_name,
        )
        return result

    def load_relationships_for_type(
        self,
        rel_type: str,
        source_name: str,
        records: list[RelationshipRecord],
        end_label: str | None = None,
    ) -> tuple[int, int]:
        """
        Load relationships for a single (rel_type, source_name[, end_label]) group.

        Returns (written_count, skipped_count).
        """
        query = self._registry.get_rel_query(rel_type, source_name, end_label)
        if query is None:
            log_event(
                self._logger,
                event_name="rel_query_not_found",
                message=(
                    f"No merge query registered for ({rel_type}, {source_name}, "
                    f"{end_label}) — records skipped"
                ),
                rel_type=rel_type,
                source_name=source_name,
                end_label=end_label,
                record_count=len(records),
            )
            return 0, len(records)

        try:
            written, skipped = self._writer.write_relationships(query, records)
            log_event(
                self._logger,
                event_name="relationships_written",
                message=f"Wrote {written} {rel_type} relationships from {source_name}",
                rel_type=rel_type,
                source_name=source_name,
                end_label=end_label,
                written=written,
                skipped=skipped,
            )
            return written, skipped
        except Exception as exc:
            log_event(
                self._logger,
                event_name="rel_write_error",
                message=f"Error writing {rel_type} relationships from {source_name}",
                rel_type=rel_type,
                source_name=source_name,
                error=str(exc),
            )
            raise
