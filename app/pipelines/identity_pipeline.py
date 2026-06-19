"""
Identity pipeline — dim_users, dim_avatars, dim_badges.

User nodes must be loaded first as they are the anchor for every
social, behavior, and economy relationship in downstream pipelines.
"""

from __future__ import annotations

from app.core.constants import IDENTITY_PIPELINE
from app.pipelines.base import BasePipeline


class IdentityPipeline(BasePipeline):
    """
    Loads core identity nodes: User, Avatar, Badge.

    Order: dim_users first (User nodes + FAVORS rels), then catalog nodes.
    """

    pipeline_name = IDENTITY_PIPELINE
    sources = (
        "dim_users",    # User nodes + FAVORS rels — must be first
        "dim_avatars",  # Avatar nodes
        "dim_badges",   # Badge nodes
    )
