from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response

from app.api.dto.user import GraphEdgeDTO, GraphNodeDTO, UserSubgraphDTO
from app.core.ids import build_user_id

router = APIRouter(prefix="/api/users", tags=["users"])


def get_neo4j_client() -> Any:
    try:
        from app.db.neo4j_client import Neo4jClient

        return Neo4jClient()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"Unable to initialize Neo4j client: {exc}") from exc


def _escape_label(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _format_properties(properties: dict[str, Any]) -> str:
    if not properties:
        return ""
    parts = [f'{_escape_label(str(key))}={_escape_label(str(value))}' for key, value in properties.items()]
    return ", ".join(parts)


def _build_subgraph_dot(subgraph: UserSubgraphDTO) -> str:
    lines = ["digraph UserSubgraph {", "  graph [rankdir=LR];"]

    for node in subgraph.nodes:
        label = node.labels[0] if node.labels else "Node"
        props = _format_properties(node.properties)
        node_attrs = [f'label="{_escape_label(label)}"', "shape=box"]
        if props:
            node_attrs.append(f'tooltip="{_escape_label(props)}"')
        lines.append(f'  "{_escape_label(node.id)}" [{", ".join(node_attrs)}];')

    for edge in subgraph.edges:
        props = _format_properties(edge.properties)
        edge_attrs = [f'label="{_escape_label(edge.type)}"']
        if props:
            edge_attrs.append(f'tooltip="{_escape_label(props)}"')
        if edge.properties.get("weight") is not None:
            edge_attrs.append(f'weight={edge.properties["weight"]}')
        lines.append(
            f'  "{_escape_label(edge.source)}" -> "{_escape_label(edge.target)}" [{", ".join(edge_attrs)}];'
        )

    lines.append("}")
    return "\n".join(lines)


def _build_user_subgraph(user_id: str, client: Any) -> UserSubgraphDTO:
    canonical_user_id = build_user_id(user_id)

    query = """
    MATCH (u:User {id: $user_id})
    MATCH p=(u)-[*1..100]-(n)
    WITH collect(DISTINCT nodes(p)) AS node_lists, collect(DISTINCT relationships(p)) AS rel_lists
    UNWIND node_lists AS node_list
    UNWIND node_list AS node
    WITH collect(DISTINCT {id: coalesce(node.id, elementId(node)), labels: labels(node), properties: properties(node)}) AS nodes, rel_lists
    UNWIND rel_lists AS rel_list
    UNWIND rel_list AS rel
    WITH nodes,
         collect(DISTINCT {
           source: coalesce(startNode(rel).id, elementId(startNode(rel))),
           target: coalesce(endNode(rel).id, elementId(endNode(rel))),
           type: type(rel),
           properties: properties(rel)
         }) AS edges
    RETURN nodes, edges
    """

    records = client.fetch_all(query, {"user_id": canonical_user_id})
    payload = records[0] if records else {"nodes": [], "edges": []}

    nodes: list[GraphNodeDTO] = [
        GraphNodeDTO(id=canonical_user_id, labels=["User"]),
        *[
            GraphNodeDTO(
                id=str(node.get("id", "")),
                labels=list(node.get("labels", []) or []),
                properties=dict(node.get("properties", {}) or {}),
            )
            for node in payload.get("nodes", []) or []
            if str(node.get("id", "")) != canonical_user_id
        ],
    ]
    edges: list[GraphEdgeDTO] = [
        GraphEdgeDTO(
            source=str(edge.get("source", "")),
            target=str(edge.get("target", "")),
            type=str(edge.get("type", "")),
            properties=dict(edge.get("properties", {}) or {}),
        )
        for edge in payload.get("edges", []) or []
    ]

    return UserSubgraphDTO(user_id=canonical_user_id, nodes=nodes, edges=edges)


@router.get("/{user_id}/subgraph")
def get_user_subgraph(user_id: str, client: Any = Depends(get_neo4j_client)) -> Response:
    """Return the user-centered subgraph as a Graphviz DOT graph string."""
    subgraph = _build_user_subgraph(user_id, client)
    return Response(content=_build_subgraph_dot(subgraph), media_type="text/plain")


@router.get("/{user_id}/subgraph.json")
def get_user_subgraph_json(user_id: str, client: Any = Depends(get_neo4j_client)) -> UserSubgraphDTO:
    """Return the user-centered subgraph as JSON."""
    return _build_user_subgraph(user_id, client)
