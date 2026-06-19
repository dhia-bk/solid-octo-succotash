"""
Temporal loader — handles PersonaState chain management.

Manages:
- PersonaState node writes (via NodeLoader)
- CURRENT_STATE pointer rotation (atomic per-user transaction)
- PREVIOUS_STATE chaining between successive PersonaState snapshots
- HAS_STATE relationship writes (all snapshots, not just current)
"""

from __future__ import annotations

from time import perf_counter

from app.contracts.graph_records import GraphWriteBatch
from app.core.constants import PERSONA_STATE, USER
from app.core.logging import get_logger, log_event
from app.db.neo4j_client import Neo4jClient
from app.loaders.base import BaseLoader, LoadResult
from app.loaders.batch_writer import BatchWriter
from app.loaders.node_loader import MergeQueryRegistry, NodeLoader
from app.loaders.relationship_loader import RelationshipLoader

# ── Temporal Cypher ───────────────────────────────────────────────────────────

ROTATE_CURRENT_STATE_QUERY: str = """\
MATCH (u:User {id: $user_id})
OPTIONAL MATCH (u)-[old_cs:CURRENT_STATE]->(old_ps:PersonaState)
WITH u, old_cs, old_ps
MATCH (new_ps:PersonaState {id: $new_persona_state_id})
WHERE old_ps IS NULL OR old_ps.id <> new_ps.id
FOREACH (_ IN CASE WHEN old_cs IS NOT NULL THEN [1] ELSE [] END |
    DELETE old_cs
    MERGE (old_ps)-[:PREVIOUS_STATE]->(new_ps)
)
MERGE (u)-[:CURRENT_STATE]->(new_ps)"""


class TemporalLoader(BaseLoader):
    """
    Specialized loader for PersonaState temporal patterns.

    On each run for a given user:
    1. MERGE PersonaState nodes.
    2. For users with a new CURRENT_STATE in this batch:
       a. Read existing CURRENT_STATE rel.
       b. If exists: DELETE old CURRENT_STATE, MERGE PREVIOUS_STATE link
          from old PersonaState → new PersonaState.
       c. MERGE new CURRENT_STATE rel.
    3. MERGE HAS_STATE rels (all snapshots, not just current).
    """

    def __init__(
        self,
        neo4j_client: Neo4jClient,
        run_id: str,
        merge_query_registry: MergeQueryRegistry,
        dry_run: bool = False,
    ) -> None:
        super().__init__(neo4j_client, run_id, dry_run)
        self._registry = merge_query_registry
        self._node_loader = NodeLoader(
            neo4j_client=neo4j_client,
            run_id=run_id,
            merge_query_registry=merge_query_registry,
            dry_run=dry_run,
        )
        self._rel_loader = RelationshipLoader(
            neo4j_client=neo4j_client,
            run_id=run_id,
            merge_query_registry=merge_query_registry,
            dry_run=dry_run,
        )
        self._writer = BatchWriter(
            neo4j_client=neo4j_client,
            run_id=run_id,
            dry_run=dry_run,
        )

    def load(self, batch: GraphWriteBatch) -> LoadResult:
        """
        Load a full GraphWriteBatch via temporal persona logic.

        Delegates node writes to NodeLoader and relationship writes to
        RelationshipLoader, then runs CURRENT_STATE rotation for all
        PersonaState records in the batch.
        """
        return self.load_persona_states(batch)

    def load_persona_states(self, batch: GraphWriteBatch) -> LoadResult:
        """
        Specialized load for PersonaState nodes and CURRENT_STATE relationships.
        """
        started = perf_counter()
        result = LoadResult(source_name=batch.source_name, run_id=self._run_id)

        log_event(
            self._logger,
            event_name="temporal_load_started",
            message="Temporal PersonaState load started",
            run_id=self._run_id,
            batch_id=batch.batch_id,
            source_name=batch.source_name,
            node_count=batch.node_count(),
            rel_count=batch.relationship_count(),
        )

        # 1. Write PersonaState nodes
        node_result = self._node_loader.load(batch)
        result.nodes_written += node_result.nodes_written
        result.nodes_skipped += node_result.nodes_skipped
        result.errors.extend(node_result.errors)
        result.batch_count += node_result.batch_count

        if node_result.errors:
            result.duration_seconds = self._elapsed(started)
            return result

        # 2. Rotate CURRENT_STATE for each user with a PersonaState in this batch
        persona_records = [
            rec for rec in batch.node_records
            if rec.label == PERSONA_STATE
        ]

        for rec in persona_records:
            user_id = rec.properties.get("user_id")
            if not user_id:
                log_event(
                    self._logger,
                    event_name="temporal_missing_user_id",
                    message="PersonaState record missing user_id; skipping rotation",
                    node_id=rec.node_id,
                )
                result.nodes_skipped += 1
                continue

            calculated_at = rec.properties.get("calculated_at", "")
            try:
                self._rotate_current_state(
                    user_id=str(user_id),
                    new_persona_state_id=rec.node_id,
                    calculated_at=calculated_at,
                )
            except Exception as exc:
                msg = f"CURRENT_STATE rotation failed for user {user_id}: {exc}"
                result.errors.append(msg)
                log_event(
                    self._logger,
                    event_name="current_state_rotation_error",
                    message=msg,
                    user_id=user_id,
                    persona_state_id=rec.node_id,
                    error=str(exc),
                )

        # 3. Write HAS_STATE and other relationships
        rel_result = self._rel_loader.load(batch)
        result.relationships_written += rel_result.relationships_written
        result.relationships_skipped += rel_result.relationships_skipped
        result.errors.extend(rel_result.errors)
        result.batch_count += rel_result.batch_count

        result.duration_seconds = self._elapsed(started)

        log_event(
            self._logger,
            event_name="temporal_load_finished",
            message="Temporal PersonaState load finished",
            run_id=self._run_id,
            batch_id=batch.batch_id,
            nodes_written=result.nodes_written,
            relationships_written=result.relationships_written,
            errors=len(result.errors),
            duration_seconds=round(result.duration_seconds, 3),
        )
        return result

    def _rotate_current_state(
        self,
        user_id: str,
        new_persona_state_id: str,
        calculated_at: str,
    ) -> None:
        """
        Execute the CURRENT_STATE rotation Cypher for a single user.

        Wrapped in a single transaction to ensure atomicity:
        - Deletes old CURRENT_STATE relationship.
        - Creates PREVIOUS_STATE link from old PersonaState to new.
        - Merges new CURRENT_STATE relationship.
        """
        if self._dry_run:
            log_event(
                self._logger,
                event_name="current_state_rotation_dry_run",
                message="Dry-run: skipped CURRENT_STATE rotation",
                user_id=user_id,
                new_persona_state_id=new_persona_state_id,
            )
            return

        self._client.run_write(
            ROTATE_CURRENT_STATE_QUERY,
            {
                "user_id": user_id,
                "new_persona_state_id": new_persona_state_id,
                "calculated_at": calculated_at,
            },
        )
