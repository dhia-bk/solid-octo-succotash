"""
Temporal pipeline — post-transform graph operations for temporal data consistency.

Does not re-extract or re-transform warehouse sources. Operates entirely on the
already-loaded graph to:

1. Fill missing CURRENT_STATE pointers for users whose PersonaState was partially loaded.
2. Log warnings for users with PersonaState chain gaps (does not repair chains).
3. Back-fill null fixture_era / prediction_era properties on Match/Prediction nodes.
4. Write a TemporalPipelineRun audit node to the graph.

Must run after behavior_pipeline and intelligence_pipeline.
"""

from __future__ import annotations

from time import perf_counter
from typing import Any

from app.core.constants import PERSONA_STATE, TEMPORAL_PIPELINE, MATCH, USER
from app.core.logging import get_logger, log_event
from app.core.time import utc_now
from app.pipelines.base import BasePipeline, PipelineResult

LOGGER = get_logger(__name__)

# ── Temporal repair queries ────────────────────────────────────────────────────

_MISSING_CURRENT_STATE_QUERY = """\
MATCH (u:User)
WHERE NOT (u)-[:CURRENT_STATE]->(:PersonaState)
  AND (u)-[:HAS_STATE]->(:PersonaState)
RETURN u.id AS user_id"""

_LATEST_PERSONA_STATE_QUERY = """\
MATCH (u:User {id: $user_id})-[:HAS_STATE]->(ps:PersonaState)
RETURN ps.id AS ps_id
ORDER BY ps.snapshot_at DESC
LIMIT 1"""

_CREATE_CURRENT_STATE_QUERY = """\
MATCH (u:User {id: $user_id})
MATCH (ps:PersonaState {id: $ps_id})
MERGE (u)-[:CURRENT_STATE]->(ps)"""

_CHAIN_GAPS_QUERY = """\
MATCH (u:User)-[:HAS_STATE]->(ps:PersonaState)
WHERE NOT (ps)-[:PREVIOUS_STATE]->(:PersonaState)
  AND NOT (ps)-[:CURRENT_STATE]-(:User)
WITH u.id AS user_id, count(ps) AS gap_count
WHERE gap_count > 1
RETURN user_id, gap_count
LIMIT 1000"""

_NULL_ERA_MATCH_QUERY = """\
MATCH (m:Match)
WHERE m.fixture_era IS NULL
RETURN m.id AS match_id, m.kickoff_at AS kickoff_at
LIMIT 5000"""

_SET_MATCH_ERA_QUERY = """\
UNWIND $rows AS row
MATCH (m:Match {id: row.match_id})
SET m.fixture_era = row.era"""

_NULL_ERA_PREDICTION_QUERY = """\
MATCH (u:User)-[r:PREDICTED]->(m:Match)
WHERE r.prediction_era IS NULL
RETURN id(r) AS rel_id, m.fixture_era AS match_era
LIMIT 5000"""

_SET_PREDICTION_ERA_QUERY = """\
UNWIND $rows AS row
MATCH ()-[r:PREDICTED]->()
WHERE id(r) = row.rel_id
SET r.prediction_era = row.match_era"""

_AUDIT_NODE_QUERY = """\
MERGE (t:TemporalPipelineRun {id: $run_id})
SET t.ran_at = datetime(),
    t.era_count = $era_count,
    t.current_state_repairs = $current_state_repairs,
    t.chain_gap_warnings = $chain_gap_warnings"""


class TemporalPipeline(BasePipeline):
    """
    Graph-only temporal integrity pass.

    No warehouse extraction. All operations are read-then-write Cypher
    against the already-loaded graph.
    """

    pipeline_name = TEMPORAL_PIPELINE
    sources: tuple[str, ...] = ()

    def run(self) -> PipelineResult:
        started = perf_counter()
        started_at = utc_now().isoformat()
        result = PipelineResult(
            pipeline_name=self.pipeline_name,
            run_id=self._run_id,
            status="failed",
            started_at=started_at,
        )

        self._log_pipeline_started()

        current_state_repairs = 0
        chain_gap_warnings = 0
        era_count = 0

        try:
            if not self._dry_run:
                # Step 1 — repair missing CURRENT_STATE pointers
                current_state_repairs = self._repair_missing_current_state()

                # Step 2 — log chain gap warnings (no repair)
                chain_gap_warnings = self._log_chain_gaps()

                # Step 3 — back-fill null era properties
                era_count = self._backfill_era_properties()

                # Step 4 — write audit node
                self._write_audit_node(
                    era_count=era_count,
                    current_state_repairs=current_state_repairs,
                    chain_gap_warnings=chain_gap_warnings,
                )

            result.status = "dry_run" if self._dry_run else "completed"

        except Exception as exc:
            result.status = "failed"
            result.error_messages.append(str(exc))
            log_event(self._logger, event_name="temporal_pipeline_error",
                      run_id=self._run_id, error=str(exc))

        finally:
            result.finished_at = utc_now().isoformat()
            result.duration_seconds = perf_counter() - started
            log_event(
                self._logger,
                event_name="temporal_pipeline_summary",
                run_id=self._run_id,
                current_state_repairs=current_state_repairs,
                chain_gap_warnings=chain_gap_warnings,
                era_count=era_count,
                status=result.status,
            )
            self._log_pipeline_finished(result)

        return result

    def _repair_missing_current_state(self) -> int:
        """
        Find users with HAS_STATE but no CURRENT_STATE and wire their latest
        PersonaState as the CURRENT_STATE. Returns repair count.
        """
        repairs = 0
        try:
            records = self._neo4j_client.query_many(_MISSING_CURRENT_STATE_QUERY)
            for record in records:
                user_id = record["user_id"]
                latest = self._neo4j_client.query_many(
                    _LATEST_PERSONA_STATE_QUERY, {"user_id": user_id}
                )
                if not latest:
                    continue
                ps_id = latest[0]["ps_id"]
                self._neo4j_client.run_write(
                    _CREATE_CURRENT_STATE_QUERY,
                    {"user_id": user_id, "ps_id": ps_id},
                )
                repairs += 1

            log_event(
                self._logger,
                event_name="current_state_repairs",
                repairs=repairs,
                run_id=self._run_id,
            )
        except Exception as exc:
            log_event(
                self._logger,
                event_name="current_state_repair_error",
                error=str(exc),
                run_id=self._run_id,
            )
        return repairs

    def _log_chain_gaps(self) -> int:
        """
        Find users with PersonaState chain gaps and log a warning.
        Does not repair — flags for manual review. Returns gap count.
        """
        gap_warnings = 0
        try:
            records = self._neo4j_client.query_many(_CHAIN_GAPS_QUERY)
            for record in records:
                gap_warnings += 1
                log_event(
                    self._logger,
                    event_name="persona_state_chain_gap_warning",
                    user_id=record["user_id"],
                    gap_count=record["gap_count"],
                    run_id=self._run_id,
                )
        except Exception as exc:
            log_event(
                self._logger,
                event_name="chain_gap_check_error",
                error=str(exc),
                run_id=self._run_id,
            )
        return gap_warnings

    def _backfill_era_properties(self) -> int:
        """
        Back-fill null fixture_era on Match nodes and propagate to PREDICTED rels.
        Returns the number of era values written.
        """
        from app.core.time import utc_now as _utc_now

        era_count = 0

        try:
            # Back-fill Match.fixture_era
            matches = self._neo4j_client.query_many(_NULL_ERA_MATCH_QUERY)
            if matches:
                rows = []
                for m in matches:
                    era = self._classify_era(m.get("kickoff_at"))
                    if era:
                        rows.append({"match_id": m["match_id"], "era": era})
                        era_count += 1
                if rows:
                    self._neo4j_client.run_many(
                        _SET_MATCH_ERA_QUERY, rows, rows_param_name="rows"
                    )

            # Propagate to PREDICTED rels with null prediction_era
            predictions = self._neo4j_client.query_many(_NULL_ERA_PREDICTION_QUERY)
            if predictions:
                rows = [
                    {"rel_id": p["rel_id"], "match_era": p["match_era"]}
                    for p in predictions
                    if p.get("match_era")
                ]
                if rows:
                    self._neo4j_client.run_many(
                        _SET_PREDICTION_ERA_QUERY, rows, rows_param_name="rows"
                    )

        except Exception as exc:
            log_event(
                self._logger,
                event_name="era_backfill_error",
                error=str(exc),
                run_id=self._run_id,
            )

        return era_count

    def _classify_era(self, kickoff_at: Any) -> str | None:
        """Classify a match kickoff timestamp into a temporal era string."""
        if not kickoff_at:
            return None
        try:
            from app.core.time import warehouse_value_to_utc_datetime
            dt = warehouse_value_to_utc_datetime(kickoff_at)
            if dt is None:
                return None
            year = dt.year
            if year < 2020:
                return "pre_2020"
            elif year < 2022:
                return "2020_2021"
            elif year < 2024:
                return "2022_2023"
            else:
                return "2024_plus"
        except Exception:
            return None

    def _write_audit_node(
        self,
        era_count: int,
        current_state_repairs: int,
        chain_gap_warnings: int,
    ) -> None:
        """Merge a TemporalPipelineRun audit node into the graph."""
        try:
            self._neo4j_client.run_write(
                _AUDIT_NODE_QUERY,
                {
                    "run_id": self._run_id,
                    "era_count": era_count,
                    "current_state_repairs": current_state_repairs,
                    "chain_gap_warnings": chain_gap_warnings,
                },
            )
        except Exception as exc:
            log_event(
                self._logger,
                event_name="temporal_audit_node_error",
                error=str(exc),
                run_id=self._run_id,
            )
