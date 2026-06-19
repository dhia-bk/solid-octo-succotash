"""
app/transformers/fixtures.py
=============================
Transformer for dim_fixtures → Match nodes + HOME_TEAM, AWAY_TEAM,
IN_LEAGUE relationships.

fixture_era is read directly from the row (pre-computed by the DWH).
TemporalEngine is used as a fallback when row.fixture_era is None.

Endpoint resolution for HOME_TEAM and AWAY_TEAM uses TeamCanonicalizer
as declared in ENDPOINT_SPECS (required=True). If canonicalization fails
the relationship is skipped — the Match node is still emitted.
IN_LEAGUE uses direct id construction — no canonicalization.
"""

from __future__ import annotations

from app.canonicalization.base import BaseCanonicalizer
from app.contracts.graph_records import GraphWriteBatch, NodeRecord, RelationshipRecord
from app.contracts.warehouse_rows import ExtractorBatch
from app.core.constants import AWAY_TEAM, HOME_TEAM, IN_LEAGUE, LEAGUE, MATCH, TEAM
from app.core.exceptions import CanonicalizationError, TransformationError
from app.core.ids import build_fixture_id, build_league_id
from app.core.logging import log_transformation_finished, log_transformation_started
from app.mappings.registry import MappingRegistry
from app.schemas.warehouse.fixtures import INCLUSION_MODE, SOURCE_NAME, FixturesRow
from app.transformers.base import BaseTransformer
from app.transformers.graph_record_builder import GraphRecordBuilder
from app.transformers.temporal import TemporalEngine, build_temporal_engine


class FixturesTransformer(BaseTransformer):
    """
    Transforms dim_fixtures rows into Match nodes and sports-core
    relationship records.

    Merge key strategy: direct on fixture_id.
    Node id:           build_fixture_id(row.fixture_id)

    Relationships emitted:
        HOME_TEAM  (Match → Team)   — requires TeamCanonicalizer
        AWAY_TEAM  (Match → Team)   — requires TeamCanonicalizer
        IN_LEAGUE  (Match → League) — direct id, no canonicalization

    fixture_era:
        Taken from row.fixture_era when present (DWH pre-computed).
        Falls back to TemporalEngine.classify_era(row.kickoff_at_utc)
        when row.fixture_era is None.
    """

    source_name = SOURCE_NAME        # "dim_fixtures"
    inclusion_mode = INCLUSION_MODE  # GRAPH_CORE

    def __init__(
        self,
        run_id: str,
        canonicalizer_registry: dict[str, BaseCanonicalizer] | None = None,
        mapping_registry: MappingRegistry | None = None,
        temporal_engine: TemporalEngine | None = None,
    ) -> None:
        super().__init__(run_id, canonicalizer_registry, mapping_registry)
        self._temporal = temporal_engine or build_temporal_engine()

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
            row: FixturesRow
            try:
                node, row_rels = self._transform_row(row, builder)
                nodes.append(node)
                rels.extend(row_rels)
            except (TransformationError, CanonicalizationError) as exc:
                self._skip(str(exc), row_id=getattr(row, "fixture_id", None))
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
        row: FixturesRow,
        builder: GraphRecordBuilder,
    ) -> tuple[NodeRecord, list[RelationshipRecord]]:
        if not row.fixture_id:
            raise TransformationError(
                "FixturesRow missing required fixture_id",
                source=SOURCE_NAME,
            )

        node_id = build_fixture_id(row.fixture_id)
        node = builder.node(MATCH, node_id, self._build_match_properties(row))

        row_rels: list[RelationshipRecord] = []

        home_rel = self._build_home_team_rel(row, node_id, builder)
        if home_rel is not None:
            row_rels.append(home_rel)

        away_rel = self._build_away_team_rel(row, node_id, builder)
        if away_rel is not None:
            row_rels.append(away_rel)

        league_rel = self._build_in_league_rel(row, node_id, builder)
        if league_rel is not None:
            row_rels.append(league_rel)

        return node, row_rels

    # -- Property builder -----------------------------------------------------

    def _build_match_properties(self, row: FixturesRow) -> dict:
        # Trust DWH fixture_era; fall back to engine when None
        era = row.fixture_era or self._temporal.classify_era(row.kickoff_at_utc)

        return {
            "home_team_id":    row.home_team_id,
            "away_team_id":    row.away_team_id,
            "league_id":       str(row.league_id) if row.league_id is not None else None,
            "kickoff_at":      self._ts(row.kickoff_at_utc),
            "status":          row.status,
            "final_game_score": row.final_game_score,
            "result_known":    self._bool(row.result_known),
            "fixture_era":     era,
        }

    # -- Relationship builders ------------------------------------------------

    def _build_home_team_rel(
        self,
        row: FixturesRow,
        fixture_node_id: str,
        builder: GraphRecordBuilder,
    ) -> RelationshipRecord | None:
        if not row.home_team_id:
            self._skip(
                "home_team_id is None — skipping HOME_TEAM rel",
                row_id=row.fixture_id,
            )
            return None

        try:
            team_id = self._resolve_endpoint(HOME_TEAM, "end", row.home_team_id)
        except TransformationError as exc:
            self._skip(str(exc), row_id=row.fixture_id, rel=HOME_TEAM)
            return None

        if team_id is None:
            return None

        return builder.rel(
            HOME_TEAM,
            fixture_node_id,
            team_id,
            start_label=MATCH,
            end_label=TEAM,
        )

    def _build_away_team_rel(
        self,
        row: FixturesRow,
        fixture_node_id: str,
        builder: GraphRecordBuilder,
    ) -> RelationshipRecord | None:
        if not row.away_team_id:
            self._skip(
                "away_team_id is None — skipping AWAY_TEAM rel",
                row_id=row.fixture_id,
            )
            return None

        try:
            team_id = self._resolve_endpoint(AWAY_TEAM, "end", row.away_team_id)
        except TransformationError as exc:
            self._skip(str(exc), row_id=row.fixture_id, rel=AWAY_TEAM)
            return None

        if team_id is None:
            return None

        return builder.rel(
            AWAY_TEAM,
            fixture_node_id,
            team_id,
            start_label=MATCH,
            end_label=TEAM,
        )

    def _build_in_league_rel(
        self,
        row: FixturesRow,
        fixture_node_id: str,
        builder: GraphRecordBuilder,
    ) -> RelationshipRecord | None:
        if row.league_id is None:
            self._skip(
                "league_id is None — skipping IN_LEAGUE rel",
                row_id=row.fixture_id,
            )
            return None

        league_node_id = build_league_id(row.league_id)

        return builder.rel(
            IN_LEAGUE,
            fixture_node_id,
            league_node_id,
            start_label=MATCH,
            end_label=LEAGUE,
        )