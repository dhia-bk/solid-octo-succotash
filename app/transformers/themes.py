"""
app/transformers/themes.py
===========================
Transformer for dim_private_league_themes → LeagueTheme nodes + HAS_THEME rels.

Emits:
    - LeagueTheme node (one per row)
    - HAS_THEME rel (PrivateLeague → LeagueTheme) when private_league_id present

Node id strategy (fallback per merge_keys.py):
    slugify(str(row.theme_id) + "_theme") if theme_id not None,
    else slugify(str(row.private_league_id) + "_theme")

Skip the row entirely if both theme_id and private_league_id are None —
no stable identity exists.

HAS_THEME endpoint resolution:
    Start: HAS_THEME_START spec → direct_id, private_league_id
    End:   HAS_THEME_END spec → fallback_theme_key strategy, theme_id field
    Both via self._resolve_endpoint() — declared in ENDPOINT_SPECS.
"""

from __future__ import annotations

from app.contracts.graph_records import GraphWriteBatch, NodeRecord, RelationshipRecord
from app.contracts.warehouse_rows import ExtractorBatch
from app.core.constants import HAS_THEME, LEAGUE_THEME, PRIVATE_LEAGUE
from app.core.exceptions import CanonicalizationError, TransformationError
from app.core.ids import build_private_league_id, slugify
from app.core.logging import log_transformation_finished, log_transformation_started
from app.schemas.warehouse.private_league_themes import (
    INCLUSION_MODE,
    SOURCE_NAME,
    PrivateLeagueThemesRow,
)
from app.transformers.base import BaseTransformer
from app.transformers.graph_record_builder import GraphRecordBuilder


class ThemesTransformer(BaseTransformer):
    """
    Transforms dim_private_league_themes rows into LeagueTheme nodes and
    HAS_THEME relationship records.

    Merge key strategy: fallback on theme_id, fallback private_league_id.
    """

    source_name = SOURCE_NAME        # "dim_private_league_themes"
    inclusion_mode = INCLUSION_MODE  # GRAPH_ENRICHMENT

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
            row: PrivateLeagueThemesRow
            try:
                node, has_theme_rel = self._transform_row(row, builder)
                nodes.append(node)
                if has_theme_rel is not None:
                    rels.append(has_theme_rel)
            except (TransformationError, CanonicalizationError) as exc:
                self._skip(str(exc), row_id=getattr(row, "theme_id", None))
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
        row: PrivateLeagueThemesRow,
        builder: GraphRecordBuilder,
    ) -> tuple[NodeRecord, RelationshipRecord | None]:
        # Require at least one stable key
        if row.theme_id is None and row.private_league_id is None:
            raise TransformationError(
                "PrivateLeagueThemesRow has no stable key (both theme_id and private_league_id are None)",
                source=SOURCE_NAME,
            )

        # Node id — fallback strategy
        if row.theme_id is not None:
            node_id = slugify(str(row.theme_id) + "_theme")
        else:
            node_id = slugify(str(row.private_league_id) + "_theme")

        properties = {
            "private_league_id":    str(row.private_league_id) if row.private_league_id is not None else None,
            "background_color":     row.background_color,
            "accent_color":         row.accent_color,
            "banner_url":           row.banner_url,
        }

        node = builder.node(LEAGUE_THEME, node_id, properties)

        has_theme_rel = None
        if row.private_league_id is not None:
            league_node_id = build_private_league_id(row.private_league_id)
            has_theme_rel = builder.rel(
                HAS_THEME,
                league_node_id,
                node_id,
                start_label=PRIVATE_LEAGUE,
                end_label=LEAGUE_THEME,
                properties={"theme_id": str(row.theme_id) if row.theme_id is not None else None},
            )
        else:
            self._skip(
                "private_league_id is None — skipping HAS_THEME rel",
                row_id=row.theme_id,
            )

        return node, has_theme_rel