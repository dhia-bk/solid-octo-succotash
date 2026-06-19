"""
app/transformers/enrichment.py
===============================
Property merging engine for nodes written by multiple sources.

When more than one warehouse source contributes properties to the same
graph node (e.g. User from dim_users + app_users, Team from dim_teams +
dim_teams_enhanced), this engine enforces the write rules declared in
app/mappings/property_ownership.py before any merge takes place.

No numeric thresholds, YAML config, or domain knowledge lives here.
All write authority decisions are delegated entirely to:
    - may_source_write_property()  from app/mappings/property_ownership.py
    - get_property_owner()         from app/mappings/property_ownership.py
    - WRITE_ONCE_PROPERTIES        from app/schemas/graph/properties.py
    - WRITE_POLICY_OVERWRITE       from app/mappings/property_ownership.py

Used by:
    users.py  — merges dim_users (base) + app_users (enrichment)
    teams.py  — merges dim_teams (base) + dim_teams_enhanced (enrichment)
"""

from __future__ import annotations

from typing import Any

from app.core.logging import get_logger
from app.mappings.property_ownership import (
    WRITE_POLICY_OVERWRITE,
    may_source_write_property,
    get_property_owner,
)
from app.schemas.graph.properties import WRITE_ONCE_PROPERTIES

logger = get_logger(__name__)


class EnrichmentEngine:
    """
    Merges enrichment properties into a base property dict under write rules
    declared in app/mappings/property_ownership.py.

    No state is held — all methods are pure functions over their arguments.
    A single shared instance can be constructed once and reused across
    all transformers that need enrichment merging.

    Construction:
        engine = EnrichmentEngine()

    Usage (users.py):
        merged = engine.merge_node_properties(
            base=identity_props,
            enrichment=app_identity_props,
            source_name="app_users",
            target_label="User",
        )

    Usage (teams.py):
        merged = engine.merge_node_properties(
            base=dim_teams_props,
            enrichment=dim_teams_enhanced_props,
            source_name="dim_teams_enhanced",
            target_label="Team",
        )
    """

    def merge_node_properties(
        self,
        base: dict[str, Any],
        enrichment: dict[str, Any],
        *,
        source_name: str,
        target_label: str,
        write_once_keys: frozenset[str] = WRITE_ONCE_PROPERTIES,
    ) -> dict[str, Any]:
        """
        Merge enrichment properties into base under ownership and write rules.

        Rules applied per property key in enrichment (in order):

        1. Ownership check:
               may_source_write_property(source_name, target_label, key)
               must be True. Keys not owned by source_name are silently
               dropped — the source has no authority to write them.

        2. Write-once guard:
               If key is in write_once_keys AND the key already exists in
               base with a non-None value, the enrichment value is ignored
               regardless of write_policy. Creation timestamps and identity
               fields must never be overwritten after first write.

        3. Null overwrite guard:
               If the enrichment value is None AND the base already holds a
               non-None value, the enrichment value is dropped UNLESS the
               declared write_policy is OVERWRITE. This prevents enrichment
               sources from accidentally clearing established values.

        4. Merge:
               All keys that pass rules 1–3 are written into the result.
               Keys present only in base are always preserved unchanged.
               New keys from enrichment (not yet in base) are added if
               rules 1–3 pass.

        Args:
            base:           Property dict from the primary/authoritative source.
            enrichment:     Property dict from the enriching source.
            source_name:    Logical source name of the enrichment dict
                            (used for ownership lookup).
            target_label:   Graph node label being written to.
            write_once_keys: Property names that may never be overwritten
                            after first write. Defaults to WRITE_ONCE_PROPERTIES.

        Returns:
            New dict containing the merged result. Neither base nor
            enrichment is mutated.
        """
        result: dict[str, Any] = dict(base)
        dropped_ownership = 0
        dropped_write_once = 0
        dropped_null = 0
        applied = 0

        for key, enrichment_value in enrichment.items():

            # Rule 1 — ownership check
            if not may_source_write_property(source_name, target_label, key):
                dropped_ownership += 1
                continue

            # Rule 2 — write-once guard
            if key in write_once_keys:
                existing = result.get(key)
                if existing is not None:
                    dropped_write_once += 1
                    continue

            # Rule 3 — null overwrite guard
            if enrichment_value is None:
                existing = result.get(key)
                if existing is not None:
                    ownership_spec = get_property_owner(target_label, key)
                    write_policy = (
                        ownership_spec.write_policy if ownership_spec is not None else None
                    )
                    if write_policy != WRITE_POLICY_OVERWRITE:
                        dropped_null += 1
                        continue

            # Rule 4 — merge
            result[key] = enrichment_value
            applied += 1

        logger.debug(
            "EnrichmentEngine.merge_node_properties completed",
            extra={
                "source_name": source_name,
                "target_label": target_label,
                "applied": applied,
                "dropped_ownership": dropped_ownership,
                "dropped_write_once": dropped_write_once,
                "dropped_null": dropped_null,
            },
        )

        return result

    def filter_owned_properties(
        self,
        properties: dict[str, Any],
        *,
        source_name: str,
        target_label: str,
    ) -> dict[str, Any]:
        """
        Return only the properties this source is authorized to write.

        Used before building a NodeRecord for enrichment sources that do
        not have a base dict to merge into — they need their property dict
        pre-filtered to only what they own before passing to
        build_node_record().

        This is a strict ownership filter. It does not apply write-once or
        null guards — those are only relevant when merging against an
        existing base. The caller is responsible for null handling if needed.

        Args:
            properties:   Raw property dict assembled by the transformer.
            source_name:  Logical source name (used for ownership lookup).
            target_label: Graph node label being written to.

        Returns:
            New dict containing only the keys source_name is authorized to
            write. The original dict is not mutated.
        """
        result = {
            key: value
            for key, value in properties.items()
            if may_source_write_property(source_name, target_label, key)
        }

        dropped = len(properties) - len(result)
        if dropped > 0:
            logger.debug(
                "EnrichmentEngine.filter_owned_properties dropped unauthorized keys",
                extra={
                    "source_name": source_name,
                    "target_label": target_label,
                    "total_keys": len(properties),
                    "dropped": dropped,
                    "retained": len(result),
                },
            )

        return result