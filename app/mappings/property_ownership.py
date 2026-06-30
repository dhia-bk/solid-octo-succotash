"""
Property ownership and enrichment precedence rules.

This module defines which source is authoritative for each graph property when
multiple sources can write to the same node or relationship.

It answers:

- which source owns a given property
- whether a property is core, enrichment, temporal, or derived
- whether later writes may overwrite earlier ones
- whether nulls may overwrite existing values
- whether updates should append history instead of replacing current state

This is the central guardrail against accidental enrichment chaos. Transformers,
loaders, and pipelines should consult this module rather than inferring write
precedence from source order or implementation details.

Design rules:
- This file is the single executable source-of-truth for property ownership.
- Multi-source entities must declare ownership explicitly per property.
- Write behavior is policy-driven, not transformer-driven.
- Validation in this module is structural and registry-aware. It verifies:
  - target labels / relationship types are valid
  - write policies are valid
  - owner sources exist in source inventory when introspection is possible
  - no duplicate owner_priority exists for the same target/property pair
- Temporal properties must be declared explicitly via temporal=True.
- This module does not define the actual property values or field mappings,
  only who may write them and under what overwrite policy.

Primary outputs:
- PROPERTY_OWNERSHIP_SPECS: full registry of property ownership declarations
- lookup helpers for per-property ownership access
- validation helpers for ownership completeness and conflict detection
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.constants import GRAPH_NODE_LABELS, GRAPH_RELATIONSHIP_TYPES

WRITE_POLICY_OVERWRITE = "overwrite"
WRITE_POLICY_WRITE_ONCE = "write_once"
WRITE_POLICY_FILL_IF_NULL = "fill_if_null"
WRITE_POLICY_APPEND_HISTORY = "append_history"

VALID_WRITE_POLICIES: frozenset[str] = frozenset(
    {
        WRITE_POLICY_OVERWRITE,
        WRITE_POLICY_WRITE_ONCE,
        WRITE_POLICY_FILL_IF_NULL,
        WRITE_POLICY_APPEND_HISTORY,
    }
)


@dataclass(frozen=True)
class PropertyOwnershipSpec:
    """
    Ownership declaration for one graph property.

    Attributes:
        target_label_or_rel: Graph node label or relationship type.
        property_name: Property name on that target.
        owner_source: Logical source allowed to write this property
            authoritatively.
        owner_priority: Lower numbers indicate higher priority when multiple
            sources are intentionally allowed to touch the same property.
        write_policy: One of:
            - overwrite
            - write_once
            - fill_if_null
            - append_history
        null_overwrite_allowed: Whether None/null values from this source may
            overwrite an existing non-null value.
        temporal: Whether this property is part of temporal/history semantics.
        notes: Optional explanatory notes.
    """

    target_label_or_rel: str
    property_name: str
    owner_source: str
    owner_priority: int
    write_policy: str
    null_overwrite_allowed: bool
    temporal: bool
    notes: str | None


# Registry


PROPERTY_OWNERSHIP_SPECS: tuple[PropertyOwnershipSpec, ...] = (
    
    # User node - core identity/profile owned by dim_users
    
    PropertyOwnershipSpec(
        target_label_or_rel="User",
        property_name="user_name",
        owner_source="dim_users",
        owner_priority=10,
        write_policy=WRITE_POLICY_OVERWRITE,
        null_overwrite_allowed=False,
        temporal=False,
        notes="Canonical display/user name comes from dim_users.",
    ),
    PropertyOwnershipSpec(
        target_label_or_rel="User",
        property_name="full_name",
        owner_source="dim_users",
        owner_priority=10,
        write_policy=WRITE_POLICY_FILL_IF_NULL,
        null_overwrite_allowed=False,
        temporal=False,
        notes="Full name is profile data from dim_users; avoid null clobbering.",
    ),
    PropertyOwnershipSpec(
        target_label_or_rel="User",
        property_name="country",
        owner_source="dim_users",
        owner_priority=10,
        write_policy=WRITE_POLICY_OVERWRITE,
        null_overwrite_allowed=False,
        temporal=False,
        notes="Country profile field owned by dim_users.",
    ),
    PropertyOwnershipSpec(
        target_label_or_rel="User",
        property_name="gender",
        owner_source="dim_users",
        owner_priority=10,
        write_policy=WRITE_POLICY_FILL_IF_NULL,
        null_overwrite_allowed=False,
        temporal=False,
        notes="Gender profile field owned by dim_users.",
    ),
    PropertyOwnershipSpec(
        target_label_or_rel="User",
        property_name="age",
        owner_source="dim_users",
        owner_priority=10,
        write_policy=WRITE_POLICY_OVERWRITE,
        null_overwrite_allowed=False,
        temporal=False,
        notes="Derived age field owned by dim_users.",
    ),
    PropertyOwnershipSpec(
        target_label_or_rel="User",
        property_name="user_created_at",
        owner_source="dim_users",
        owner_priority=10,
        write_policy=WRITE_POLICY_WRITE_ONCE,
        null_overwrite_allowed=False,
        temporal=False,
        notes="User creation timestamp should never be overwritten after first write.",
    ),
    PropertyOwnershipSpec(
        target_label_or_rel="User",
        property_name="first_activity_at",
        owner_source="dim_users",
        owner_priority=10,
        write_policy=WRITE_POLICY_WRITE_ONCE,
        null_overwrite_allowed=False,
        temporal=False,
        notes="First activity timestamp is immutable once known.",
    ),
    PropertyOwnershipSpec(
        target_label_or_rel="User",
        property_name="last_activity_at",
        owner_source="dim_users",
        owner_priority=10,
        write_policy=WRITE_POLICY_OVERWRITE,
        null_overwrite_allowed=False,
        temporal=False,
        notes="Last activity is current-state and should advance over time.",
    ),
    PropertyOwnershipSpec(
        target_label_or_rel="User",
        property_name="favorite_team_id",
        owner_source="dim_users",
        owner_priority=10,
        write_policy=WRITE_POLICY_OVERWRITE,
        null_overwrite_allowed=False,
        temporal=False,
        notes="Favorite team owned by dim_users.",
    ),
    PropertyOwnershipSpec(
        target_label_or_rel="User",
        property_name="favorite_team_name",
        owner_source="dim_users",
        owner_priority=10,
        write_policy=WRITE_POLICY_FILL_IF_NULL,
        null_overwrite_allowed=False,
        temporal=False,
        notes="Human-readable favorite team name owned by dim_users.",
    ),
    PropertyOwnershipSpec(
        target_label_or_rel="User",
        property_name="current_subscription_name",
        owner_source="dim_users",
        owner_priority=10,
        write_policy=WRITE_POLICY_OVERWRITE,
        null_overwrite_allowed=False,
        temporal=False,
        notes="Current subscription snapshot on User is sourced from dim_users.",
    ),
    PropertyOwnershipSpec(
        target_label_or_rel="User",
        property_name="duel_rating",
        owner_source="dim_users",
        owner_priority=10,
        write_policy=WRITE_POLICY_OVERWRITE,
        null_overwrite_allowed=False,
        temporal=False,
        notes="Current-state duel rating on User is owned by dim_users; historical rating changes are captured separately in RatingSnapshot nodes.",
    ),
    PropertyOwnershipSpec(
        target_label_or_rel="User",
        property_name="ai_total_credits",
        owner_source="dim_users",
        owner_priority=10,
        write_policy=WRITE_POLICY_OVERWRITE,
        null_overwrite_allowed=False,
        temporal=False,
        notes="AI credit totals owned by dim_users.",
    ),
    PropertyOwnershipSpec(
        target_label_or_rel="User",
        property_name="ai_remaining_credits",
        owner_source="dim_users",
        owner_priority=10,
        write_policy=WRITE_POLICY_OVERWRITE,
        null_overwrite_allowed=False,
        temporal=False,
        notes="Remaining AI credits owned by dim_users.",
    ),
    PropertyOwnershipSpec(
        target_label_or_rel="User",
        property_name="last_payment_at",
        owner_source="dim_users",
        owner_priority=10,
        write_policy=WRITE_POLICY_OVERWRITE,
        null_overwrite_allowed=False,
        temporal=False,
        notes="Payment snapshot field owned by dim_users.",
    ),
    PropertyOwnershipSpec(
        target_label_or_rel="User",
        property_name="avatar_category",
        owner_source="dim_users",
        owner_priority=10,
        write_policy=WRITE_POLICY_FILL_IF_NULL,
        null_overwrite_allowed=False,
        temporal=False,
        notes="Avatar category snapshot owned by dim_users.",
    ),
    PropertyOwnershipSpec(
        target_label_or_rel="User",
        property_name="avatar_id",
        owner_source="dim_users",
        owner_priority=10,
        write_policy=WRITE_POLICY_FILL_IF_NULL,
        null_overwrite_allowed=False,
        temporal=False,
        notes="Avatar reference on User owned by dim_users.",
    ),
    PropertyOwnershipSpec(
        target_label_or_rel="User",
        property_name="notification_opt_in",
        owner_source="dim_notification_preferences",
        owner_priority=30,
        write_policy=WRITE_POLICY_OVERWRITE,
        null_overwrite_allowed=False,
        temporal=False,
        notes="Notification preference fields are owned by dim_notification_preferences.",
    ),
    PropertyOwnershipSpec(
        target_label_or_rel="User",
        property_name="notification_channel_preferences",
        owner_source="dim_notification_preferences",
        owner_priority=30,
        write_policy=WRITE_POLICY_OVERWRITE,
        null_overwrite_allowed=False,
        temporal=False,
        notes="Channel-specific notification preference state is owned by dim_notification_preferences.",
    ),
    PropertyOwnershipSpec(
        target_label_or_rel="User",
        property_name="activity_weight",
        owner_source="fct_user_activities",
        owner_priority=40,
        write_policy=WRITE_POLICY_OVERWRITE,
        null_overwrite_allowed=False,
        temporal=False,
        notes="Activity-derived enrichment belongs to user activity aggregation, but must not overwrite identity/profile fields.",
    ),
    PropertyOwnershipSpec(
        target_label_or_rel="User",
        property_name="notif_total_received",
        owner_source="dim_users",
        owner_priority=10,
        write_policy=WRITE_POLICY_OVERWRITE,
        null_overwrite_allowed=False,
        temporal=False,
        notes="Snapshot notification counts on User come from dim_users; richer aggregates remain feature-only.",
    ),
    PropertyOwnershipSpec(
        target_label_or_rel="User",
        property_name="notif_total_read",
        owner_source="dim_users",
        owner_priority=10,
        write_policy=WRITE_POLICY_OVERWRITE,
        null_overwrite_allowed=False,
        temporal=False,
        notes="Snapshot notification read counts on User come from dim_users.",
    ),
    
    # Team node
    
    PropertyOwnershipSpec(
        target_label_or_rel="Team",
        property_name="team_name",
        owner_source="dim_teams",
        owner_priority=10,
        write_policy=WRITE_POLICY_OVERWRITE,
        null_overwrite_allowed=False,
        temporal=False,
        notes="Canonical team identity owned by dim_teams.",
    ),
    PropertyOwnershipSpec(
        target_label_or_rel="Team",
        property_name="team_code",
        owner_source="dim_teams",
        owner_priority=10,
        write_policy=WRITE_POLICY_WRITE_ONCE,
        null_overwrite_allowed=False,
        temporal=False,
        notes="Team code is a stable identity attribute.",
    ),
    PropertyOwnershipSpec(
        target_label_or_rel="Team",
        property_name="country",
        owner_source="dim_teams",
        owner_priority=10,
        write_policy=WRITE_POLICY_FILL_IF_NULL,
        null_overwrite_allowed=False,
        temporal=False,
        notes="Team country is core metadata from dim_teams.",
    ),
    PropertyOwnershipSpec(
        target_label_or_rel="Team",
        property_name="league_id",
        owner_source="dim_teams",
        owner_priority=10,
        write_policy=WRITE_POLICY_OVERWRITE,
        null_overwrite_allowed=False,
        temporal=False,
        notes="Team -> league association is owned by dim_teams.",
    ),
    PropertyOwnershipSpec(
        target_label_or_rel="Team",
        property_name="team_logo",
        owner_source="dim_teams_enhanced",
        owner_priority=20,
        write_policy=WRITE_POLICY_FILL_IF_NULL,
        null_overwrite_allowed=False,
        temporal=False,
        notes="Enhanced presentation assets come from dim_teams_enhanced.",
    ),
    PropertyOwnershipSpec(
        target_label_or_rel="Team",
        property_name="total_fans",
        owner_source="dim_teams_enhanced",
        owner_priority=20,
        write_policy=WRITE_POLICY_OVERWRITE,
        null_overwrite_allowed=False,
        temporal=False,
        notes="Fan analytics fields belong to dim_teams_enhanced.",
    ),
    PropertyOwnershipSpec(
        target_label_or_rel="Team",
        property_name="fan_rank",
        owner_source="dim_teams_enhanced",
        owner_priority=20,
        write_policy=WRITE_POLICY_OVERWRITE,
        null_overwrite_allowed=False,
        temporal=False,
        notes="Fan analytics fields belong to dim_teams_enhanced.",
    ),
    PropertyOwnershipSpec(
        target_label_or_rel="Team",
        property_name="fan_engagement_score",
        owner_source="dim_teams_enhanced",
        owner_priority=20,
        write_policy=WRITE_POLICY_OVERWRITE,
        null_overwrite_allowed=False,
        temporal=False,
        notes="Fan analytics fields belong to dim_teams_enhanced.",
    ),
    PropertyOwnershipSpec(
        target_label_or_rel="Team",
        property_name="fan_growth_rate",
        owner_source="dim_teams_enhanced",
        owner_priority=20,
        write_policy=WRITE_POLICY_OVERWRITE,
        null_overwrite_allowed=False,
        temporal=False,
        notes="Growth analytics belong to dim_teams_enhanced.",
    ),
    
    # Question node
    
    PropertyOwnershipSpec(
        target_label_or_rel="Question",
        property_name="question_text",
        owner_source="dim_questions",
        owner_priority=10,
        write_policy=WRITE_POLICY_WRITE_ONCE,
        null_overwrite_allowed=False,
        temporal=False,
        notes="Question text/core lifecycle owned by dim_questions.",
    ),
    PropertyOwnershipSpec(
        target_label_or_rel="Question",
        property_name="created_at",
        owner_source="dim_questions",
        owner_priority=10,
        write_policy=WRITE_POLICY_WRITE_ONCE,
        null_overwrite_allowed=False,
        temporal=False,
        notes="Question creation timestamp is immutable.",
    ),
    PropertyOwnershipSpec(
        target_label_or_rel="Question",
        property_name="is_active",
        owner_source="dim_questions",
        owner_priority=10,
        write_policy=WRITE_POLICY_OVERWRITE,
        null_overwrite_allowed=False,
        temporal=False,
        notes="Current question lifecycle state is owned by dim_questions.",
    ),
    PropertyOwnershipSpec(
        target_label_or_rel="Question",
        property_name="total_responses",
        owner_source="dim_questions_enhanced",
        owner_priority=20,
        write_policy=WRITE_POLICY_OVERWRITE,
        null_overwrite_allowed=False,
        temporal=False,
        notes="Question response analytics owned by dim_questions_enhanced.",
    ),
    PropertyOwnershipSpec(
        target_label_or_rel="Question",
        property_name="yes_percentage",
        owner_source="dim_questions_enhanced",
        owner_priority=20,
        write_policy=WRITE_POLICY_OVERWRITE,
        null_overwrite_allowed=False,
        temporal=False,
        notes="Question analytics owned by dim_questions_enhanced.",
    ),
    PropertyOwnershipSpec(
        target_label_or_rel="Question",
        property_name="last_response_at",
        owner_source="dim_questions_enhanced",
        owner_priority=20,
        write_policy=WRITE_POLICY_OVERWRITE,
        null_overwrite_allowed=False,
        temporal=False,
        notes="Question activity analytics owned by dim_questions_enhanced.",
    ),
    
    # PartnerReward node
    
    PropertyOwnershipSpec(
        target_label_or_rel="PartnerReward",
        property_name="partner_name",
        owner_source="dim_partner_reward_catalog",
        owner_priority=10,
        write_policy=WRITE_POLICY_WRITE_ONCE,
        null_overwrite_allowed=False,
        temporal=False,
        notes="Canonical catalog fields belong to dim_partner_reward_catalog.",
    ),
    PropertyOwnershipSpec(
        target_label_or_rel="PartnerReward",
        property_name="reward_name",
        owner_source="dim_partner_reward_catalog",
        owner_priority=10,
        write_policy=WRITE_POLICY_WRITE_ONCE,
        null_overwrite_allowed=False,
        temporal=False,
        notes="Canonical reward name belongs to catalog.",
    ),
    PropertyOwnershipSpec(
        target_label_or_rel="PartnerReward",
        property_name="coin_cost",
        owner_source="dim_partner_reward_catalog",
        owner_priority=10,
        write_policy=WRITE_POLICY_OVERWRITE,
        null_overwrite_allowed=False,
        temporal=False,
        notes="Catalog cost belongs to dim_partner_reward_catalog.",
    ),
    PropertyOwnershipSpec(
        target_label_or_rel="PartnerReward",
        property_name="is_active",
        owner_source="dim_partner_reward_catalog",
        owner_priority=10,
        write_policy=WRITE_POLICY_OVERWRITE,
        null_overwrite_allowed=False,
        temporal=False,
        notes="Catalog active state belongs to dim_partner_reward_catalog.",
    ),
    PropertyOwnershipSpec(
        target_label_or_rel="PartnerReward",
        property_name="stock_total",
        owner_source="fct_partner_reward_inventory",
        owner_priority=20,
        write_policy=WRITE_POLICY_OVERWRITE,
        null_overwrite_allowed=False,
        temporal=False,
        notes="Inventory stock fields belong to fct_partner_reward_inventory.",
    ),
    PropertyOwnershipSpec(
        target_label_or_rel="PartnerReward",
        property_name="stock_remaining",
        owner_source="fct_partner_reward_inventory",
        owner_priority=20,
        write_policy=WRITE_POLICY_OVERWRITE,
        null_overwrite_allowed=False,
        temporal=False,
        notes="Inventory stock fields belong to fct_partner_reward_inventory.",
    ),
    PropertyOwnershipSpec(
        target_label_or_rel="PartnerReward",
        property_name="last_inventory_at",
        owner_source="fct_partner_reward_inventory",
        owner_priority=20,
        write_policy=WRITE_POLICY_OVERWRITE,
        null_overwrite_allowed=False,
        temporal=True,
        notes="Inventory update timestamp belongs to inventory enrichment.",
    ),
    
    # PrivateLeague / LeagueTheme
    
    PropertyOwnershipSpec(
        target_label_or_rel="PrivateLeague",
        property_name="league_name",
        owner_source="dim_private_leagues",
        owner_priority=10,
        write_policy=WRITE_POLICY_OVERWRITE,
        null_overwrite_allowed=False,
        temporal=False,
        notes="Private league identity/core fields owned by dim_private_leagues.",
    ),
    PropertyOwnershipSpec(
        target_label_or_rel="PrivateLeague",
        property_name="created_at",
        owner_source="dim_private_leagues",
        owner_priority=10,
        write_policy=WRITE_POLICY_WRITE_ONCE,
        null_overwrite_allowed=False,
        temporal=False,
        notes="Private league creation timestamp is immutable.",
    ),
    PropertyOwnershipSpec(
        target_label_or_rel="PrivateLeague",
        property_name="member_count",
        owner_source="dim_private_leagues",
        owner_priority=10,
        write_policy=WRITE_POLICY_OVERWRITE,
        null_overwrite_allowed=False,
        temporal=False,
        notes="Current league summary fields owned by dim_private_leagues.",
    ),
    PropertyOwnershipSpec(
        target_label_or_rel="LeagueTheme",
        property_name="theme_name",
        owner_source="dim_private_league_themes",
        owner_priority=10,
        write_policy=WRITE_POLICY_FILL_IF_NULL,
        null_overwrite_allowed=False,
        temporal=False,
        notes="Theme identity and presentation belong to dim_private_league_themes.",
    ),
    PropertyOwnershipSpec(
        target_label_or_rel="LeagueTheme",
        property_name="theme_palette",
        owner_source="dim_private_league_themes",
        owner_priority=10,
        write_policy=WRITE_POLICY_OVERWRITE,
        null_overwrite_allowed=False,
        temporal=False,
        notes="Theming enrichment belongs to dim_private_league_themes.",
    ),
    
    # PersonaState

    PropertyOwnershipSpec(
        target_label_or_rel="PersonaState",
        property_name="user_id",
        owner_source="fct_user_behavior",
        owner_priority=10,
        write_policy=WRITE_POLICY_APPEND_HISTORY,
        null_overwrite_allowed=False,
        temporal=False,
        notes="User FK stored on PersonaState so TemporalLoader can route CURRENT_STATE rotation.",
    ),
    PropertyOwnershipSpec(
            target_label_or_rel="PersonaState",
            property_name="pcm_stage",
            owner_source="fct_user_behavior",
            owner_priority=10,
            write_policy=WRITE_POLICY_APPEND_HISTORY,
            null_overwrite_allowed=False,
            temporal=True,
            notes="PCM stage written by fct_user_behavior; append-only temporal snapshots.",
        ),
    PropertyOwnershipSpec(
        target_label_or_rel="PersonaState",
        property_name="behaviour_label",
        owner_source="fct_user_behavior",
        owner_priority=10,
        write_policy=WRITE_POLICY_APPEND_HISTORY,
        null_overwrite_allowed=False,
        temporal=True,
        notes="Behaviour label written by fct_user_behavior; append-only temporal snapshots.",
    ),
    PropertyOwnershipSpec(
        target_label_or_rel="PersonaState",
        property_name="birfing_coefficient",
        owner_source="fct_user_behavior",
        owner_priority=10,
        write_policy=WRITE_POLICY_APPEND_HISTORY,
        null_overwrite_allowed=False,
        temporal=True,
        notes="Birfing coefficient written by fct_user_behavior; append-only temporal snapshots.",
    ),
    PropertyOwnershipSpec(
        target_label_or_rel="PersonaState",
        property_name="frustration_bias",
        owner_source="fct_user_behavior",
        owner_priority=10,
        write_policy=WRITE_POLICY_APPEND_HISTORY,
        null_overwrite_allowed=False,
        temporal=True,
        notes="Frustration bias written by fct_user_behavior; append-only temporal snapshots.",
    ),
    PropertyOwnershipSpec(
        target_label_or_rel="PersonaState",
        property_name="calculated_at",
        owner_source="fct_user_behavior",
        owner_priority=10,
        write_policy=WRITE_POLICY_APPEND_HISTORY,
        null_overwrite_allowed=False,
        temporal=True,
        notes="Calculation timestamp written by fct_user_behavior; append-only temporal snapshots.",
    ),
    # Relationship property examples
    
    PropertyOwnershipSpec(
        target_label_or_rel="PREDICTED",
        property_name="predicted_outcome",
        owner_source="fct_predictions",
        owner_priority=10,
        write_policy=WRITE_POLICY_WRITE_ONCE,
        null_overwrite_allowed=False,
        temporal=False,
        notes="Prediction edge properties are owned by fct_predictions.",
    ),
    PropertyOwnershipSpec(
        target_label_or_rel="PREDICTED",
        property_name="points_awarded",
        owner_source="fct_predictions",
        owner_priority=10,
        write_policy=WRITE_POLICY_OVERWRITE,
        null_overwrite_allowed=False,
        temporal=False,
        notes="Prediction scoring may update after result settlement.",
    ),
    PropertyOwnershipSpec(
        target_label_or_rel="MEMBER_OF",
        property_name="activity_weight",
        owner_source="weighting_pipeline",
        owner_priority=10,
        write_policy=WRITE_POLICY_OVERWRITE,
        null_overwrite_allowed=False,
        temporal=False,
        notes="Weighted membership edge properties are owned by weighting pipeline output, not raw membership source.",
    ),
    PropertyOwnershipSpec(
        target_label_or_rel="RECEIVED_NOTIFICATION",
        property_name="read_at",
        owner_source="jct_notification_recipients",
        owner_priority=10,
        write_policy=WRITE_POLICY_OVERWRITE,
        null_overwrite_allowed=False,
        temporal=True,
        notes="Notification read state belongs to delivery/recipient source.",
    ),
    PropertyOwnershipSpec(
        target_label_or_rel="PURCHASED",
        property_name="used_date",
        owner_source="fct_voucher_purchases",
        owner_priority=10,
        write_policy=WRITE_POLICY_OVERWRITE,
        null_overwrite_allowed=False,
        temporal=True,
        notes="Voucher lifecycle state belongs to purchase source.",
    ),
)

_PROPERTY_INDEX: dict[tuple[str, str], list[PropertyOwnershipSpec]] = {}
_SOURCE_INDEX: dict[str, list[PropertyOwnershipSpec]] = {}

for _spec in PROPERTY_OWNERSHIP_SPECS:
    _PROPERTY_INDEX.setdefault(
        (_spec.target_label_or_rel, _spec.property_name),
        [],
    ).append(_spec)
    _SOURCE_INDEX.setdefault(_spec.owner_source, []).append(_spec)

for _spec_list in _PROPERTY_INDEX.values():
    _spec_list.sort(key=lambda spec: spec.owner_priority)

for _spec_list in _SOURCE_INDEX.values():
    _spec_list.sort(key=lambda spec: (spec.target_label_or_rel, spec.property_name, spec.owner_priority))


def get_property_owner(
    target_label_or_rel: str,
    property_name: str,
) -> PropertyOwnershipSpec | None:
    """
    Return the highest-priority ownership spec for a target/property pair.

    Args:
        target_label_or_rel: Graph node label or relationship type.
        property_name: Property name.

    Returns:
        PropertyOwnershipSpec if one exists, else None.
    """
    specs = _PROPERTY_INDEX.get((target_label_or_rel, property_name), [])
    return specs[0] if specs else None


def get_properties_for_source(owner_source: str) -> list[PropertyOwnershipSpec]:
    """
    Return all properties owned by a given source.

    Args:
        owner_source: Logical owner source / pipeline name.

    Returns:
        Ordered list of PropertyOwnershipSpec entries.
    """
    return list(_SOURCE_INDEX.get(owner_source, []))


def may_source_write_property(
    source_name: str,
    target_label_or_rel: str,
    property_name: str,
) -> bool:
    """
    Return True if the given source is declared as an owner for the property.

    Args:
        source_name: Source attempting to write.
        target_label_or_rel: Graph node label or relationship type.
        property_name: Target property.

    Returns:
        True if source_name is one of the declared owners.
    """
    specs = _PROPERTY_INDEX.get((target_label_or_rel, property_name), [])
    return any(spec.owner_source == source_name for spec in specs)


def validate_property_ownership_specs() -> list[str]:
    """
    Validate all property ownership declarations.

    Checks:
    - target labels / relationship types exist
    - property_name is non-empty
    - owner_source is non-empty
    - owner_priority is non-negative
    - write_policy is valid
    - no two sources share the same owner_priority for the same target/property
    - owner source exists in source inventory when introspection is possible

    Returns:
        Flat list of validation error strings. Empty list means valid.
    """
    errors: list[str] = []
    valid_targets = set(GRAPH_NODE_LABELS) | set(GRAPH_RELATIONSHIP_TYPES)
    registered_sources = _get_registered_source_names()

    for idx, spec in enumerate(PROPERTY_OWNERSHIP_SPECS):
        prefix = (
            f"PROPERTY_OWNERSHIP_SPECS[{idx}] "
            f"(target={spec.target_label_or_rel!r}, property={spec.property_name!r}, "
            f"owner={spec.owner_source!r})"
        )

        if not spec.target_label_or_rel or not spec.target_label_or_rel.strip():
            errors.append(f"{prefix}: target_label_or_rel cannot be empty")
        elif spec.target_label_or_rel not in valid_targets:
            errors.append(
                f"{prefix}: target_label_or_rel '{spec.target_label_or_rel}' "
                f"is not registered in GRAPH_NODE_LABELS or GRAPH_RELATIONSHIP_TYPES"
            )

        if not spec.property_name or not spec.property_name.strip():
            errors.append(f"{prefix}: property_name cannot be empty")

        if not spec.owner_source or not spec.owner_source.strip():
            errors.append(f"{prefix}: owner_source cannot be empty")

        if spec.owner_priority < 0:
            errors.append(f"{prefix}: owner_priority cannot be negative")

        if spec.write_policy not in VALID_WRITE_POLICIES:
            errors.append(
                f"{prefix}: write_policy '{spec.write_policy}' must be one of "
                f"{sorted(VALID_WRITE_POLICIES)}"
            )

        if registered_sources is not None and spec.owner_source not in registered_sources:
            # allow orchestrator/pipeline owners that are not warehouse sources
            if not spec.owner_source.endswith("_pipeline"):
                errors.append(
                    f"{prefix}: owner_source '{spec.owner_source}' is not registered in source inventory"
                )

    for (target_label_or_rel, property_name), specs in _PROPERTY_INDEX.items():
        priorities: dict[int, list[str]] = {}
        for spec in specs:
            priorities.setdefault(spec.owner_priority, []).append(spec.owner_source)

        for owner_priority, owners in priorities.items():
            if len(owners) > 1:
                errors.append(
                    "Duplicate owner_priority detected for the same target/property: "
                    f"target={target_label_or_rel!r}, property={property_name!r}, "
                    f"owner_priority={owner_priority}, owners={sorted(owners)}"
                )

    return errors


def _get_registered_source_names() -> set[str] | None:
    """
    Best-effort introspection of source inventory registry source names.

    Returns:
        Set of registered source names when a compatible source inventory
        registry shape is available, otherwise None.
    """
    try:
        from app.source_inventory import registry as source_registry  # type: ignore
    except Exception:
        return None

    candidate_names = (
        "SOURCE_REGISTRY",
        "SOURCE_REGISTRATIONS",
        "SOURCE_DEFINITIONS",
        "REGISTERED_SOURCES",
        "ALL_SOURCES",
    )

    for attribute_name in candidate_names:
        if not hasattr(source_registry, attribute_name):
            continue

        value: Any = getattr(source_registry, attribute_name)
        source_names = _extract_source_names(value)
        if source_names:
            return source_names

    return None


def _extract_source_names(value: Any) -> set[str]:
    """
    Extract source names from a registry-like runtime object.

    Supported shapes:
    - dict[str, Any]
    - iterable[str]
    - iterable[object with .source_name]
    - iterable[dict with 'source_name']
    """
    if isinstance(value, dict):
        names = {str(key).strip() for key in value.keys() if str(key).strip()}
        if names:
            return names

        extracted: set[str] = set()
        for item in value.values():
            name = _source_name_from_item(item)
            if name:
                extracted.add(name)
        return extracted

    if isinstance(value, (list, tuple, set, frozenset)):
        extracted: set[str] = set()
        for item in value:
            name = _source_name_from_item(item)
            if name:
                extracted.add(name)
        return extracted

    return set()


def _source_name_from_item(item: Any) -> str | None:
    """
    Best-effort extraction of source_name from one registry item.
    """
    if isinstance(item, str):
        stripped = item.strip()
        return stripped or None

    if isinstance(item, dict):
        raw = item.get("source_name")
        if raw is None:
            return None
        stripped = str(raw).strip()
        return stripped or None

    raw = getattr(item, "source_name", None)
    if raw is None:
        return None

    stripped = str(raw).strip()
    return stripped or None