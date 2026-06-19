"""
Merge queries for private league memberships.
Source(s): dim_private_league_members
"""

from __future__ import annotations


def get_member_of_merge_query(source_name: str = "dim_private_league_members") -> str:
    """Return Cypher MERGE query for MEMBER_OF (User→PrivateLeague) from source_name.

    Uses a raw Cypher string because the membership_id merge key requires a
    COALESCE fallback that the builder API does not support directly.
    """
    return """
UNWIND $rows AS row
MATCH (u:User {id: row.start_id})
MATCH (pl:PrivateLeague {id: row.end_id})
MERGE (u)-[r:MEMBER_OF {membership_id: COALESCE(row.membership_id, row.start_id + '::' + row.end_id)}]->(pl)
ON CREATE SET
    r.role = row.role,
    r.joined_at = row.joined_at,
    r._created_at = row._created_at,
    r._source_name = row._source_name,
    r._run_id = row._run_id
ON MATCH SET
    r.role = row.role,
    r.activity_weight = row.activity_weight,
    r._updated_at = row._updated_at,
    r._source_name = row._source_name,
    r._run_id = row._run_id
""".strip()
