from __future__ import annotations

from typing import Any

from fastapi import Request

from app.db.neo4j_client import Neo4jClient


def get_request_id(request: Request) -> str:
    return request.headers.get("x-request-id", "unknown")


def get_neo4j_client() -> Neo4jClient:
    return Neo4jClient()


def get_api_context(request: Request) -> dict[str, Any]:
    return {
        "request_id": get_request_id(request),
        "path": request.url.path,
    }
