"""
Social pipeline — private leagues, members, posts, comments, discussions, chat.

Requires identity_pipeline (User nodes for all relationship endpoints).
"""

from __future__ import annotations

from app.core.constants import SOCIAL_PIPELINE
from app.pipelines.base import BasePipeline


class SocialPipeline(BasePipeline):
    """
    Loads social graph nodes and relationships.

    Order: group nodes first, then membership/authorship relationships,
    then discussion and chat nodes.
    """

    pipeline_name = SOCIAL_PIPELINE
    sources = (
        "dim_private_leagues",          # PrivateLeague nodes
        "dim_private_league_members",   # MEMBER_OF rels (User → PrivateLeague)
        "dim_posts",                    # Post nodes + POSTED rels
        "dim_comments",                 # Comment nodes + COMMENTED + REPLIES_TO
        "dim_discussions",              # Discussion nodes
        "dim_prediction_discussions",   # PredictionDiscussion nodes + ABOUT rels
        "dim_chat_conversations_mysql", # Conversation nodes
        "dim_chat_direct_pairs",        # DirectPair nodes + DIRECT_MESSAGE rels
    )
