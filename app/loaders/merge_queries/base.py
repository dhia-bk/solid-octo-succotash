"""
Shared Cypher query builders for the merge_queries layer.

All node and relationship MERGE queries in the loader layer are generated via
these builders. No loader or domain file should write raw UNWIND/MERGE strings.

Build rules:
- The merge key for ALL nodes is always the canonical `id` property.
- write_once_fields → ON CREATE SET only.
- mutable_fields    → ON MATCH SET + ON CREATE SET.
- FILL_IF_NULL      → CASE WHEN n.prop IS NULL THEN row.prop ELSE n.prop END
- System _meta properties (_source_name, _run_id, _created_at, _updated_at)
  are appended automatically.
- rel_merge_fields: if provided, these properties are included in the MERGE
  pattern on the relationship (composite or direct relationship identity).
- All Cypher parameters come from row dicts built by BatchWriter._build_*_row.
"""

from __future__ import annotations

from app.schemas.graph.properties import WRITE_ONCE_PROPERTIES


# ── System meta properties ─────────────────────────────────────────────────────

_NODE_META_ON_CREATE: tuple[str, ...] = (
    "n._source_name = row._source_name",
    "n._run_id = row._run_id",
    "n._created_at = row._created_at",
)

_NODE_META_ON_MATCH: tuple[str, ...] = (
    "n._source_name = row._source_name",
    "n._run_id = row._run_id",
    "n._updated_at = row._updated_at",
)

_REL_META_ON_CREATE: tuple[str, ...] = (
    "r._source_name = row._source_name",
    "r._run_id = row._run_id",
    "r._created_at = row._created_at",
)

_REL_META_ON_MATCH: tuple[str, ...] = (
    "r._source_name = row._source_name",
    "r._run_id = row._run_id",
    "r._updated_at = row._updated_at",
)


def _indent(parts: list[str], spaces: int = 4) -> str:
    pad = " " * spaces
    return f",\n{pad}".join(parts)


def build_node_merge_query(
    label: str,
    merge_key_field: str,
    write_once_fields: list[str],
    mutable_fields: list[str],
) -> str:
    """
    Generate a parameterized MERGE query for a node type.

    Expected row dict keys (built by BatchWriter._build_node_row):
        row.id              — node identity (constraint property)
        row._source_name    — system metadata
        row._run_id         — system metadata
        row._created_at     — set on first write only
        row._updated_at     — set on every subsequent write
        row.<field>         — one key per write_once or mutable field

    Args:
        label:              Graph node label (e.g. "User").
        merge_key_field:    Property used in the MERGE pattern (always "id").
        write_once_fields:  Properties set only on ON CREATE SET.
        mutable_fields:     Properties set on both ON CREATE SET and ON MATCH SET.

    Returns:
        Parameterized Cypher string.
    """
    on_create_parts: list[str] = []
    on_create_parts.extend(f"n.{f} = row.{f}" for f in write_once_fields)
    on_create_parts.extend(_NODE_META_ON_CREATE)
    on_create_parts.extend(f"n.{f} = row.{f}" for f in mutable_fields)

    on_match_parts: list[str] = list(_NODE_META_ON_MATCH)
    on_match_parts.extend(f"n.{f} = row.{f}" for f in mutable_fields)

    lines: list[str] = [
        "UNWIND $rows AS row",
        f"MERGE (n:{label} {{{merge_key_field}: row.{merge_key_field}}})",
    ]

    if on_create_parts:
        lines.append(f"ON CREATE SET\n    {_indent(on_create_parts)}")

    if on_match_parts:
        lines.append(f"ON MATCH SET\n    {_indent(on_match_parts)}")

    return "\n".join(lines)


def build_relationship_merge_query(
    rel_type: str,
    start_label: str,
    end_label: str,
    start_merge_field: str,
    end_merge_field: str,
    rel_merge_fields: list[str] | None,
    rel_property_fields: list[str],
) -> str:
    """
    Generate a parameterized MERGE query for a relationship type.

    Expected row dict keys (built by BatchWriter._build_relationship_row):
        row.start_id        — start node identity
        row.end_id          — end node identity
        row._source_name    — system metadata
        row._run_id         — system metadata
        row._created_at     — set on first write only
        row._updated_at     — set on every subsequent write
        row.<field>         — one key per rel_merge_field or rel_property_field

    Args:
        rel_type:           Relationship type (e.g. "PREDICTED").
        start_label:        Graph label of the start node.
        end_label:          Graph label of the end node.
        start_merge_field:  Property used to match start node (typically "id").
        end_merge_field:    Property used to match end node (typically "id").
        rel_merge_fields:   If provided, included in the MERGE pattern on the
                            relationship (composite/direct identity fields).
                            If None or empty, MERGE uses only endpoint nodes.
        rel_property_fields: Additional properties SET on the relationship.
                            Write-once properties (from WRITE_ONCE_PROPERTIES)
                            appear in ON CREATE SET only; others appear in both.

    Returns:
        Parameterized Cypher string.
    """
    merge_key_part = ""
    if rel_merge_fields:
        kv_pairs = ", ".join(f"{f}: row.{f}" for f in rel_merge_fields)
        merge_key_part = f" {{{kv_pairs}}}"

    write_once = [f for f in rel_property_fields if f in WRITE_ONCE_PROPERTIES]
    mutable = [f for f in rel_property_fields if f not in WRITE_ONCE_PROPERTIES]

    on_create_parts: list[str] = []
    on_create_parts.extend(f"r.{f} = row.{f}" for f in write_once)
    on_create_parts.extend(_REL_META_ON_CREATE)
    on_create_parts.extend(f"r.{f} = row.{f}" for f in mutable)

    on_match_parts: list[str] = list(_REL_META_ON_MATCH)
    on_match_parts.extend(f"r.{f} = row.{f}" for f in mutable)

    lines: list[str] = [
        "UNWIND $rows AS row",
        f"MATCH (start:{start_label} {{{start_merge_field}: row.start_id}})",
        f"MATCH (end:{end_label} {{{end_merge_field}: row.end_id}})",
        f"MERGE (start)-[r:{rel_type}{merge_key_part}]->(end)",
    ]

    if on_create_parts:
        lines.append(f"ON CREATE SET\n    {_indent(on_create_parts)}")

    if on_match_parts:
        lines.append(f"ON MATCH SET\n    {_indent(on_match_parts)}")

    return "\n".join(lines)


def build_enrichment_merge_query(
    label: str,
    merge_key_field: str,
    enrichment_fields: list[str],
    write_policy_overwrite: list[str],
    write_policy_fill_if_null: list[str],
) -> str:
    """
    Generate a MERGE query for enrichment sources that write to existing nodes.

    write_policy_overwrite:    Always SET, even if already populated.
    write_policy_fill_if_null: SET only if the current value is NULL:
        n.prop = CASE WHEN n.prop IS NULL THEN row.prop ELSE n.prop END

    System _meta properties are included in ON MATCH SET.

    Args:
        label:                  Graph node label.
        merge_key_field:        Merge identity field (always "id").
        enrichment_fields:      Unused — kept for signature symmetry. Pass []
                                unless the domain file needs it explicitly.
        write_policy_overwrite:    Fields to unconditionally overwrite.
        write_policy_fill_if_null: Fields to set only when currently null.

    Returns:
        Parameterized Cypher string.
    """
    on_match_parts: list[str] = list(_NODE_META_ON_MATCH)
    on_match_parts.extend(f"n.{f} = row.{f}" for f in write_policy_overwrite)
    on_match_parts.extend(
        f"n.{f} = CASE WHEN n.{f} IS NULL THEN row.{f} ELSE n.{f} END"
        for f in write_policy_fill_if_null
    )

    lines: list[str] = [
        "UNWIND $rows AS row",
        f"MERGE (n:{label} {{{merge_key_field}: row.{merge_key_field}}})",
        f"ON MATCH SET\n    {_indent(on_match_parts)}",
    ]

    return "\n".join(lines)
