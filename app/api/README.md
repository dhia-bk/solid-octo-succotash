# API

This API exposes lightweight graph read endpoints for the Project Pulse knowledge graph.

## Endpoints

### Health check

- GET /api/health
- Returns a simple status payload.

Example:

```bash
curl http://localhost:8000/api/health
```

Example response:

```json
{
  "status": "ok",
  "service": "api"
}
```

### User subgraph

- GET /api/users/{user_id}/subgraph
- Returns the connected subgraph as a Graphviz DOT graph string.

- GET /api/users/{user_id}/subgraph.json
- Returns the same subgraph as structured JSON.

Examples:

```bash
curl http://localhost:8000/api/users/user-123/subgraph
curl http://localhost:8000/api/users/user-123/subgraph.json
```

Example DOT response:

```text
digraph UserSubgraph {
  graph [rankdir=LR];
  "user-123" [label="User", shape=box, tooltip="source=demo"];
  "post-1" [label="Post", shape=box];
  "user-123" -> "post-1" [label="POSTED", tooltip="weight=1.0"];
}
```

Example JSON response:

```json
{
  "user_id": "user-123",
  "nodes": [
    {
      "id": "user-123",
      "labels": ["User"],
      "properties": {}
    },
    {
      "id": "post-1",
      "labels": ["Post"],
      "properties": {}
    }
  ],
  "edges": [
    {
      "source": "user-123",
      "target": "post-1",
      "type": "POSTED",
      "properties": {}
    }
  ]
}
```

## Running locally

```bash
source .venv/bin/activate
uvicorn app.main:app --reload
```
