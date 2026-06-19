"""
Endpoint resolution rules for relationship mappings.

This module centralizes how graph endpoints are resolved for relationship-
producing sources. It declares:

- which source field supplies the raw endpoint ID or alias
- whether the endpoint label is fixed or dynamic
- which canonicalizer, if any, must be used
- whether endpoint resolution is required or optional
- which merge-key strategy applies at the endpoint level

This is the place where relationship endpoint identity stops being implicit.
Transformers must not invent endpoint label selection or canonicalizer usage
for relationships declared here.

Design rules:
- Every declared relationship endpoint must be represented by an EndpointSpec.
- Dynamic label resolution is declared separately via DynamicLabelResolution
  and keyed to the same (rel_type, endpoint_name, source_name) triple.
- Fixed endpoint labels must exist in GRAPH_NODE_LABELS.
- Relationship types must exist in GRAPH_RELATIONSHIP_TYPES.
- Canonicalizer domains must refer to supported domain canonicalizers.
- Required endpoints must declare an id_source_field.

Primary outputs:
- relationship endpoint registries for all declared relationship patterns
- endpoint lookup helpers
- validation helpers for endpoint and dynamic label declarations

This module does NOT define:
- source → artifact routing (source_to_graph.py)
- field/property mappings (later mapping spec files)
- merge key strategy definitions (merge_keys.py)
- property ownership rules (property_ownership.py)
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.constants import GRAPH_NODE_LABELS, GRAPH_RELATIONSHIP_TYPES
from app.mappings.base import (
    CanonicalizerRequirement,
    EndpointSpec,
    validate_endpoint_spec,
)

from app.canonicalization.registry_loader import SUPPORTED_SEED_DOMAINS as _SUPPORTED_CANONICALIZER_DOMAINS



@dataclass(frozen=True)
class DynamicLabelResolution:
    """
    Descriptor for endpoints whose graph label is determined dynamically.

    Attributes:
        canonicalizer_domain: Canonicalizer domain used to resolve the target.
        label_method: Method on the domain canonicalizer that returns the
            graph label for a resolved canonical ID, e.g. "get_node_label".
        required: Whether failure to determine the label must fail the mapping.
    """

    canonicalizer_domain: str
    label_method: str
    required: bool


# Endpoint registry
# Key: (rel_type, endpoint_name, source_name)

# PREDICTED: User -> Match
PREDICTED_START = EndpointSpec(
    endpoint_name="start",
    label="User",
    label_from_field=None,
    id_source_field="user_id",
    canonicalizer=None,
    merge_key_strategy="direct_id",
    required=True,
    notes="User id is already normalized at the warehouse/schema boundary.",
)

PREDICTED_END = EndpointSpec(
    endpoint_name="end",
    label="Match",
    label_from_field=None,
    id_source_field="fixture_id",
    canonicalizer=None,
    merge_key_strategy="direct_id",
    required=True,
    notes="fixture_id is the canonical Match identity.",
)

# MEMBER_OF: User -> PrivateLeague
MEMBER_OF_START = EndpointSpec(
    endpoint_name="start",
    label="User",
    label_from_field=None,
    id_source_field="user_id",
    canonicalizer=None,
    merge_key_strategy="direct_id",
    required=True,
    notes="Membership start endpoint is always User.",
)

MEMBER_OF_END = EndpointSpec(
    endpoint_name="end",
    label="PrivateLeague",
    label_from_field=None,
    id_source_field="private_league_id",
    canonicalizer=None,
    merge_key_strategy="direct_id",
    required=True,
    notes="Membership end endpoint is always PrivateLeague.",
)

# HAS_AFFINITY: User -> Team
HAS_AFFINITY_START = EndpointSpec(
    endpoint_name="start",
    label="User",
    label_from_field=None,
    id_source_field="user_id",
    canonicalizer=None,
    merge_key_strategy="direct_id",
    required=True,
    notes="Affinity start endpoint is User.",
)

HAS_AFFINITY_END = EndpointSpec(
    endpoint_name="end",
    label="Team",
    label_from_field=None,
    id_source_field="team_id",
    canonicalizer=CanonicalizerRequirement(
        domain="teams",
        resolver_method="resolve_team_id",
        required=True,
    ),
    merge_key_strategy="canonicalized_id",
    required=True,
    notes="team_id may vary across sources; resolve via TeamCanonicalizer.",
)

# RECEIVED_NOTIFICATION: User -> NotificationContent
RECEIVED_NOTIFICATION_START = EndpointSpec(
    endpoint_name="start",
    label="User",
    label_from_field=None,
    id_source_field="user_id",
    canonicalizer=None,
    merge_key_strategy="direct_id",
    required=True,
    notes="Notification recipient is always User.",
)

RECEIVED_NOTIFICATION_END = EndpointSpec(
    endpoint_name="end",
    label="NotificationContent",
    label_from_field=None,
    id_source_field="notification_id",
    canonicalizer=None,
    merge_key_strategy="direct_id",
    required=True,
    notes="Notification content identity comes from notification_id/content_id mapping.",
)

# REDEEMED: User -> PartnerReward
REDEEMED_START = EndpointSpec(
    endpoint_name="start",
    label="User",
    label_from_field=None,
    id_source_field="user_id",
    canonicalizer=None,
    merge_key_strategy="direct_id",
    required=True,
    notes="Reward redemption start endpoint is User.",
)

REDEEMED_END = EndpointSpec(
    endpoint_name="end",
    label="PartnerReward",
    label_from_field=None,
    id_source_field="reward_key",
    canonicalizer=None,
    merge_key_strategy="direct_id",
    required=True,
    notes="Reward catalog identity is assumed stable via partner_reward_id.",
)

# PURCHASED: User -> Voucher
PURCHASED_START = EndpointSpec(
    endpoint_name="start",
    label="User",
    label_from_field=None,
    id_source_field="user_id",
    canonicalizer=None,
    merge_key_strategy="direct_id",
    required=True,
    notes="Voucher purchase start endpoint is User.",
)

PURCHASED_END = EndpointSpec(
    endpoint_name="end",
    label="Voucher",
    label_from_field=None,
    id_source_field="voucher_key",
    canonicalizer=CanonicalizerRequirement(
        domain="vouchers",
        resolver_method="resolve_purchase_voucher_id",
        required=True,
    ),
    merge_key_strategy="canonicalized_id",
    required=True,
    notes="Purchase-side voucher identifiers may differ from catalog key.",
)

# SUBSCRIBED_TO: User -> SubscriptionProduct
SUBSCRIBED_TO_START = EndpointSpec(
    endpoint_name="start",
    label="User",
    label_from_field=None,
    id_source_field="user_id",
    canonicalizer=None,
    merge_key_strategy="direct_id",
    required=True,
    notes="Subscription lifecycle start endpoint is User.",
)

SUBSCRIBED_TO_END = EndpointSpec(
    endpoint_name="end",
    label="SubscriptionProduct",
    label_from_field=None,
    id_source_field="subscription_product_id",
    canonicalizer=None,
    merge_key_strategy="direct_id",
    required=True,
    notes="Subscription product catalog IDs are canonical.",
)

# PARTICIPATED_IN: User -> Super6Round or LMSCompetition
PARTICIPATED_IN_START = EndpointSpec(
    endpoint_name="start",
    label="User",
    label_from_field=None,
    id_source_field="user_id",
    canonicalizer=None,
    merge_key_strategy="direct_id",
    required=True,
    notes="Participation start endpoint is always User.",
)

PARTICIPATED_IN_END_SUPER6 = EndpointSpec(
    endpoint_name="end",
    label="Super6Round",
    label_from_field=None,
    id_source_field="super6_round_id",
    canonicalizer=CanonicalizerRequirement(
        domain="competitions",
        resolver_method="resolve_super6_round",
        required=True,
    ),
    merge_key_strategy="canonicalized_id",
    required=True,
    notes="Super6 participation targets Super6Round.",
)

PARTICIPATED_IN_END_LMS = EndpointSpec(
    endpoint_name="end",
    label="LMSCompetition",
    label_from_field=None,
    id_source_field="competition_id",
    canonicalizer=CanonicalizerRequirement(
        domain="competitions",
        resolver_method="resolve_lms_competition",
        required=True,
    ),
    merge_key_strategy="canonicalized_id",
    required=True,
    notes="LMS participation targets LMSCompetition.",
)

# Optional fully dynamic competition endpoint descriptor for any future mixed-source case
PARTICIPATED_IN_END_DYNAMIC = EndpointSpec(
    endpoint_name="end",
    label=None,
    label_from_field="competition_type",
    id_source_field="competition_id",
    canonicalizer=CanonicalizerRequirement(
        domain="competitions",
        resolver_method="resolve",
        required=True,
    ),
    merge_key_strategy="canonicalized_id",
    required=True,
    notes="Dynamic competition target; label determined by CompetitionCanonicalizer.get_node_label().",
)

# HAS_FIXTURE: Super6Round -> Match
HAS_FIXTURE_START = EndpointSpec(
    endpoint_name="start",
    label="Super6Round",
    label_from_field=None,
    id_source_field="super6_round_id",
    canonicalizer=CanonicalizerRequirement(
        domain="competitions",
        resolver_method="resolve_super6_round",
        required=True,
    ),
    merge_key_strategy="canonicalized_id",
    required=True,
    notes="HAS_FIXTURE start endpoint is Super6Round.",
)

HAS_FIXTURE_END = EndpointSpec(
    endpoint_name="end",
    label="Match",
    label_from_field=None,
    id_source_field="fixture_id",
    canonicalizer=None,
    merge_key_strategy="direct_id",
    required=True,
    notes="HAS_FIXTURE end endpoint is Match.",
)

# HAS_THEME: PrivateLeague -> LeagueTheme
HAS_THEME_START = EndpointSpec(
    endpoint_name="start",
    label="PrivateLeague",
    label_from_field=None,
    id_source_field="private_league_id",
    canonicalizer=None,
    merge_key_strategy="direct_id",
    required=True,
    notes="PrivateLeague identity is direct.",
)

HAS_THEME_END = EndpointSpec(
    endpoint_name="end",
    label="LeagueTheme",
    label_from_field=None,
    id_source_field="theme_id",
    canonicalizer=None,
    merge_key_strategy="fallback_theme_key",
    required=True,
    notes="LeagueTheme may fall back to private_league_id-based identity if theme_id is unstable.",
)

# ABOUT: PredictionDiscussion -> Match
ABOUT_START = EndpointSpec(
    endpoint_name="start",
    label="PredictionDiscussion",
    label_from_field=None,
    id_source_field="discussion_id",
    canonicalizer=None,
    merge_key_strategy="direct_id",
    required=True,
    notes="PredictionDiscussion identity is direct.",
)

ABOUT_END = EndpointSpec(
    endpoint_name="end",
    label="Match",
    label_from_field=None,
    id_source_field="fixture_id",
    canonicalizer=None,
    merge_key_strategy="direct_id",
    required=True,
    notes="Discussion target match identity is direct.",
)

# HAS_TAG: Post/News/AIArticle -> Tag
HAS_TAG_END = EndpointSpec(
    endpoint_name="end",
    label="Tag",
    label_from_field=None,
    id_source_field="tag_id",
    canonicalizer=CanonicalizerRequirement(
        domain="tags",
        resolver_method="resolve_tag_id",
        required=True,
    ),
    merge_key_strategy="canonicalized_id",
    required=True,
    notes="Tag endpoint resolves through TagCanonicalizer.",
)

HAS_TAG_START_POST = EndpointSpec(
    endpoint_name="start",
    label="Post",
    label_from_field=None,
    id_source_field="post_id",
    canonicalizer=None,
    merge_key_strategy="direct_id",
    required=True,
    notes="Post source side of HAS_TAG.",
)

HAS_TAG_START_NEWS = EndpointSpec(
    endpoint_name="start",
    label="News",
    label_from_field=None,
    id_source_field="news_id",
    canonicalizer=None,
    merge_key_strategy="direct_id",
    required=True,
    notes="News source side of HAS_TAG.",
)

HAS_TAG_START_AI_ARTICLE = EndpointSpec(
    endpoint_name="start",
    label="AIArticle",
    label_from_field=None,
    id_source_field="ai_article_id",
    canonicalizer=None,
    merge_key_strategy="direct_id",
    required=True,
    notes="AIArticle source side of HAS_TAG.",
)

# POSTED: User -> Post
POSTED_START = EndpointSpec(
    endpoint_name="start",
    label="User",
    label_from_field=None,
    id_source_field="user_id",
    canonicalizer=None,
    merge_key_strategy="direct_id",
    required=True,
    notes="Author user identity is direct.",
)

POSTED_END = EndpointSpec(
    endpoint_name="end",
    label="Post",
    label_from_field=None,
    id_source_field="post_id",
    canonicalizer=None,
    merge_key_strategy="direct_id",
    required=True,
    notes="Post identity is direct.",
)

# COMMENTED: User -> Comment
COMMENTED_START = EndpointSpec(
    endpoint_name="start",
    label="User",
    label_from_field=None,
    id_source_field="user_id",
    canonicalizer=None,
    merge_key_strategy="direct_id",
    required=True,
    notes="Comment author identity is direct.",
)

COMMENTED_END = EndpointSpec(
    endpoint_name="end",
    label="Comment",
    label_from_field=None,
    id_source_field="comment_id",
    canonicalizer=None,
    merge_key_strategy="direct_id",
    required=True,
    notes="Comment identity is direct.",
)

# JOINED_DISCUSSION: User -> Discussion
JOINED_DISCUSSION_START = EndpointSpec(
    endpoint_name="start",
    label="User",
    label_from_field=None,
    id_source_field="user_id",
    canonicalizer=None,
    merge_key_strategy="direct_id",
    required=True,
    notes="Discussion participant is User.",
)

JOINED_DISCUSSION_END = EndpointSpec(
    endpoint_name="end",
    label="Discussion",
    label_from_field=None,
    id_source_field="discussion_id",
    canonicalizer=None,
    merge_key_strategy="direct_id",
    required=True,
    notes="Discussion identity is direct.",
)

# HOME_TEAM / AWAY_TEAM / IN_LEAGUE: Match -> Team / League
HOME_TEAM_START = EndpointSpec(
    endpoint_name="start",
    label="Match",
    label_from_field=None,
    id_source_field="fixture_id",
    canonicalizer=None,
    merge_key_strategy="direct_id",
    required=True,
    notes="Match identity is direct.",
)

HOME_TEAM_END = EndpointSpec(
    endpoint_name="end",
    label="Team",
    label_from_field=None,
    id_source_field="home_team_id",
    canonicalizer=CanonicalizerRequirement(
        domain="teams",
        resolver_method="resolve_team_id",
        required=True,
    ),
    merge_key_strategy="canonicalized_id",
    required=True,
    notes="Home team resolves via TeamCanonicalizer.",
)

AWAY_TEAM_START = EndpointSpec(
    endpoint_name="start",
    label="Match",
    label_from_field=None,
    id_source_field="fixture_id",
    canonicalizer=None,
    merge_key_strategy="direct_id",
    required=True,
    notes="Match identity is direct.",
)

AWAY_TEAM_END = EndpointSpec(
    endpoint_name="end",
    label="Team",
    label_from_field=None,
    id_source_field="away_team_id",
    canonicalizer=CanonicalizerRequirement(
        domain="teams",
        resolver_method="resolve_team_id",
        required=True,
    ),
    merge_key_strategy="canonicalized_id",
    required=True,
    notes="Away team resolves via TeamCanonicalizer.",
)

IN_LEAGUE_START = EndpointSpec(
    endpoint_name="start",
    label="Match",
    label_from_field=None,
    id_source_field="fixture_id",
    canonicalizer=None,
    merge_key_strategy="direct_id",
    required=True,
    notes="Match identity is direct.",
)

IN_LEAGUE_END = EndpointSpec(
    endpoint_name="end",
    label="League",
    label_from_field=None,
    id_source_field="league_id",
    canonicalizer=None,
    merge_key_strategy="direct_id",
    required=True,
    notes="League identity is direct.",
)
# LIKED: User -> Post or User -> Comment
LIKED_START = EndpointSpec(
    endpoint_name="start",
    label="User",
    label_from_field=None,
    id_source_field="user_id",
    canonicalizer=None,
    merge_key_strategy="direct_id",
    required=True,
    notes="Like activity start endpoint is always User.",
)

LIKED_END_POST = EndpointSpec(
    endpoint_name="end",
    label="Post",
    label_from_field=None,
    id_source_field="target_id",
    canonicalizer=None,
    merge_key_strategy="direct_id",
    required=True,
    notes="Like activity targeting a Post.",
)

LIKED_END_COMMENT = EndpointSpec(
    endpoint_name="end",
    label="Comment",
    label_from_field=None,
    id_source_field="target_id",
    canonicalizer=None,
    merge_key_strategy="direct_id",
    required=True,
    notes="Like activity targeting a Comment.",
)

# ANSWERED: User -> Poll
ANSWERED_START = EndpointSpec(
    endpoint_name="start",
    label="User",
    label_from_field=None,
    id_source_field="user_id",
    canonicalizer=None,
    merge_key_strategy="direct_id",
    required=True,
    notes="Poll answer start endpoint is always User.",
)

ANSWERED_END = EndpointSpec(
    endpoint_name="end",
    label="Poll",
    label_from_field=None,
    id_source_field="target_id",
    canonicalizer=None,
    merge_key_strategy="direct_id",
    required=True,
    notes="Poll answer end endpoint is Poll.",
)

# FRIENDED: User -> User
FRIENDED_START = EndpointSpec(
    endpoint_name="start",
    label="User",
    label_from_field=None,
    id_source_field="user_id",
    canonicalizer=None,
    merge_key_strategy="direct_id",
    required=True,
    notes="Friend activity start endpoint is the acting User.",
)

FRIENDED_END = EndpointSpec(
    endpoint_name="end",
    label="User",
    label_from_field=None,
    id_source_field="target_id",
    canonicalizer=None,
    merge_key_strategy="direct_id",
    required=True,
    notes="Friend activity end endpoint is the target User.",
)

ENDPOINT_SPECS: dict[tuple[str, str, str], EndpointSpec] = {
    ("PREDICTED", "start", "fct_predictions"): PREDICTED_START,
    ("PREDICTED", "end", "fct_predictions"): PREDICTED_END,

    ("MEMBER_OF", "start", "dim_private_league_members"): MEMBER_OF_START,
    ("MEMBER_OF", "end", "dim_private_league_members"): MEMBER_OF_END,

    ("HAS_AFFINITY", "start", "fct_team_affinity"): HAS_AFFINITY_START,
    ("HAS_AFFINITY", "end", "fct_team_affinity"): HAS_AFFINITY_END,

    ("RECEIVED_NOTIFICATION", "start", "jct_notification_recipients"): RECEIVED_NOTIFICATION_START,
    ("RECEIVED_NOTIFICATION", "end", "jct_notification_recipients"): RECEIVED_NOTIFICATION_END,

    ("REDEEMED", "start", "fct_partner_reward_redemptions"): REDEEMED_START,
    ("REDEEMED", "end", "fct_partner_reward_redemptions"): REDEEMED_END,

    ("PURCHASED", "start", "fct_voucher_purchases"): PURCHASED_START,
    ("PURCHASED", "end", "fct_voucher_purchases"): PURCHASED_END,

    ("SUBSCRIBED_TO", "start", "fct_subscription_lifecycle"): SUBSCRIBED_TO_START,
    ("SUBSCRIBED_TO", "end", "fct_subscription_lifecycle"): SUBSCRIBED_TO_END,

    ("PARTICIPATED_IN", "start", "fct_super6_participants"): PARTICIPATED_IN_START,
    ("PARTICIPATED_IN", "end", "fct_super6_participants"): PARTICIPATED_IN_END_SUPER6,

    ("PARTICIPATED_IN", "start", "dim_lms_competitions"): PARTICIPATED_IN_START,
    ("PARTICIPATED_IN", "end", "dim_lms_competitions"): PARTICIPATED_IN_END_LMS,

    ("HAS_FIXTURE", "start", "dim_super6_round_fixtures"): HAS_FIXTURE_START,
    ("HAS_FIXTURE", "end", "dim_super6_round_fixtures"): HAS_FIXTURE_END,

    ("HAS_THEME", "start", "dim_private_league_themes"): HAS_THEME_START,
    ("HAS_THEME", "end", "dim_private_league_themes"): HAS_THEME_END,

    ("ABOUT", "start", "dim_prediction_discussions"): ABOUT_START,
    ("ABOUT", "end", "dim_prediction_discussions"): ABOUT_END,

    ("HAS_TAG", "start", "dim_posts"): HAS_TAG_START_POST,
    ("HAS_TAG", "end", "dim_posts"): HAS_TAG_END,
    ("HAS_TAG", "start", "dim_news"): HAS_TAG_START_NEWS,
    ("HAS_TAG", "end", "dim_news"): HAS_TAG_END,
    ("HAS_TAG", "start", "dim_ai_articles"): HAS_TAG_START_AI_ARTICLE,
    ("HAS_TAG", "end", "dim_ai_articles"): HAS_TAG_END,

    ("POSTED", "start", "dim_posts"): POSTED_START,
    ("POSTED", "end", "dim_posts"): POSTED_END,

    ("COMMENTED", "start", "dim_comments"): COMMENTED_START,
    ("COMMENTED", "end", "dim_comments"): COMMENTED_END,

    ("JOINED_DISCUSSION", "start", "fct_discussion_events"): JOINED_DISCUSSION_START,
    ("JOINED_DISCUSSION", "end", "fct_discussion_events"): JOINED_DISCUSSION_END,

    ("HOME_TEAM", "start", "dim_fixtures"): HOME_TEAM_START,
    ("HOME_TEAM", "end", "dim_fixtures"): HOME_TEAM_END,
    ("AWAY_TEAM", "start", "dim_fixtures"): AWAY_TEAM_START,
    ("AWAY_TEAM", "end", "dim_fixtures"): AWAY_TEAM_END,
    ("IN_LEAGUE", "start", "dim_fixtures"): IN_LEAGUE_START,
    ("IN_LEAGUE", "end", "dim_fixtures"): IN_LEAGUE_END,

    ("LIKED", "start", "fct_user_activities"): LIKED_START,
    ("LIKED", "end_post", "fct_user_activities"): LIKED_END_POST,
    ("LIKED", "end_comment", "fct_user_activities"): LIKED_END_COMMENT,

    ("ANSWERED", "start", "fct_user_activities"): ANSWERED_START,
    ("ANSWERED", "end", "fct_user_activities"): ANSWERED_END,

    ("FRIENDED", "start", "fct_user_activities"): FRIENDED_START,
    ("FRIENDED", "end", "fct_user_activities"): FRIENDED_END,
}

# Dynamic endpoint label resolution
# Key: (rel_type, endpoint_name, source_name)

DYNAMIC_LABEL_RESOLUTIONS: dict[tuple[str, str, str], DynamicLabelResolution] = {
    ("PARTICIPATED_IN", "end", "mixed_competition_source"): DynamicLabelResolution(
        canonicalizer_domain="competitions",
        label_method="get_node_label",
        required=True,
    ),
}

def get_endpoint_spec(rel_type: str, endpoint_name: str, source_name: str) -> EndpointSpec:
    """
    Return the endpoint spec for a relationship/source/endpoint triple.

    Args:
        rel_type: Relationship type, e.g. "PREDICTED".
        endpoint_name: Usually "start" or "end".
        source_name: Logical source/table name.

    Returns:
        EndpointSpec.

    Raises:
        KeyError: If no endpoint spec is registered for the triple.
    """
    return ENDPOINT_SPECS[(rel_type, endpoint_name, source_name)]


def get_dynamic_label_resolution(
    rel_type: str,
    endpoint_name: str,
    source_name: str,
) -> DynamicLabelResolution | None:
    """
    Return the dynamic label resolution rule for an endpoint, if any.
    """
    return DYNAMIC_LABEL_RESOLUTIONS.get((rel_type, endpoint_name, source_name))


def requires_canonicalization(spec: EndpointSpec) -> bool:
    """
    Return True if the endpoint requires canonicalization.
    """
    return spec.canonicalizer is not None


def is_dynamic_label_endpoint(spec: EndpointSpec) -> bool:
    """
    Return True if the endpoint label is not fixed and is expected to be
    determined dynamically.
    """
    return spec.label is None and spec.label_from_field is not None


def validate_endpoint_specs() -> list[str]:
    """
    Validate all endpoint and dynamic label declarations.

    Checks:
    - relationship type exists
    - endpoint_name is structurally valid
    - fixed endpoint labels exist in GRAPH_NODE_LABELS
    - required endpoints have id_source_field
    - canonicalizer domains refer to supported canonicalizer domains
    - dynamic label rules declare a canonicalizer domain and label method
    - every dynamic label resolution has a corresponding EndpointSpec
    - no duplicate or incomplete specs are present

    Returns:
        Flat list of validation error strings. Empty list means valid.
    """
    errors: list[str] = []

    valid_canonicalizer_domains = set(_SUPPORTED_CANONICALIZER_DOMAINS)

    for (rel_type, endpoint_name, source_name), spec in ENDPOINT_SPECS.items():
        prefix = (
            f"ENDPOINT_SPECS[(rel_type={rel_type!r}, endpoint={endpoint_name!r}, "
            f"source={source_name!r})]"
        )

        if rel_type not in GRAPH_RELATIONSHIP_TYPES:
            errors.append(
                f"{prefix}: rel_type '{rel_type}' is not registered in GRAPH_RELATIONSHIP_TYPES"
            )

        if endpoint_name not in {"start", "end", "node"} and not endpoint_name.startswith("end_"):
            errors.append(
                f"{prefix}: endpoint_name '{endpoint_name}' should usually be one of "
                f"'start', 'end', or 'node'"
            )

        endpoint_errors = validate_endpoint_spec(spec)
        errors.extend(f"{prefix}: {error}" for error in endpoint_errors)

        if spec.label is not None and spec.label not in GRAPH_NODE_LABELS:
            errors.append(
                f"{prefix}: fixed label '{spec.label}' is not registered in GRAPH_NODE_LABELS"
            )

        if spec.canonicalizer is not None:
            domain = spec.canonicalizer.domain
            if domain not in valid_canonicalizer_domains:
                errors.append(
                    f"{prefix}: canonicalizer domain '{domain}' is not supported"
                )

        dynamic_rule = get_dynamic_label_resolution(rel_type, endpoint_name, source_name)
        if dynamic_rule is not None:
            if spec.label is not None:
                errors.append(
                    f"{prefix}: dynamic label resolution declared, but EndpointSpec already has fixed label '{spec.label}'"
                )
            if spec.label_from_field is None or not spec.label_from_field.strip():
                errors.append(
                    f"{prefix}: dynamic label resolution requires label_from_field on EndpointSpec"
                )

    for key, rule in DYNAMIC_LABEL_RESOLUTIONS.items():
        rel_type, endpoint_name, source_name = key
        prefix = (
            f"DYNAMIC_LABEL_RESOLUTIONS[(rel_type={rel_type!r}, endpoint={endpoint_name!r}, "
            f"source={source_name!r})]"
        )

        if rel_type not in GRAPH_RELATIONSHIP_TYPES:
            errors.append(
                f"{prefix}: rel_type '{rel_type}' is not registered in GRAPH_RELATIONSHIP_TYPES"
            )

        if not rule.canonicalizer_domain or not rule.canonicalizer_domain.strip():
            errors.append(f"{prefix}: canonicalizer_domain cannot be empty")
        elif rule.canonicalizer_domain not in valid_canonicalizer_domains:
            errors.append(
                f"{prefix}: canonicalizer_domain '{rule.canonicalizer_domain}' is not supported"
            )

        if not rule.label_method or not rule.label_method.strip():
            errors.append(f"{prefix}: label_method cannot be empty")

        if key not in ENDPOINT_SPECS:
            errors.append(
                f"{prefix}: no corresponding EndpointSpec exists for dynamic label resolution"
            )
            continue

        spec = ENDPOINT_SPECS[key]
        if spec.label is not None:
            errors.append(
                f"{prefix}: dynamic label resolution cannot be paired with fixed label '{spec.label}'"
            )
        if spec.canonicalizer is None:
            errors.append(
                f"{prefix}: dynamic label resolution requires EndpointSpec.canonicalizer"
            )
        elif spec.canonicalizer.domain != rule.canonicalizer_domain:
            errors.append(
                f"{prefix}: canonicalizer_domain '{rule.canonicalizer_domain}' does not match "
                f"EndpointSpec.canonicalizer.domain '{spec.canonicalizer.domain}'"
            )

    return errors