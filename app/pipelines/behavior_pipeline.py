"""
Behavior pipeline — user rating history, persona states, activities, sessions.

fct_user_behavior produces PersonaState records that must be routed through
TemporalLoader (CURRENT_STATE rotation). This routing is handled automatically
by BasePipeline._run_source() for the "fct_user_behavior" source name.

fct_user_sessions is non-emitting (feature source only) — lifecycle log only.
"""

from __future__ import annotations

from app.core.constants import BEHAVIOR_PIPELINE
from app.pipelines.base import BasePipeline


class BehaviorPipeline(BasePipeline):
    """
    Loads behavioral graph structures: RatingSnapshot, PersonaState, activity edges.

    fct_user_behavior → TemporalLoader (special-cased in BasePipeline._run_source).
    fct_user_sessions → non-emitting, runs lifecycle log only.
    """

    pipeline_name = BEHAVIOR_PIPELINE
    sources = (
        "fct_user_rating_history",  # RatingSnapshot nodes + HAS_RATING rels
        "fct_user_behavior",        # PersonaState → TemporalLoader path
        "fct_user_activities",      # LIKED + ANSWERED + FRIENDED rels
        "fct_user_sessions",        # non-emitting — lifecycle log only
    )
