"""
Central constant registry for Project Pulse Knowledge Graph.

This module is the single source of truth for:
- graph node labels
- graph relationship types
- pipeline names
- runtime defaults
- inclusion category names
- environment names
- common config section names
- common metadata keys

Rules:
- Do not hardcode graph labels outside this module.
- Do not hardcode relationship types outside this module.
- Do not hardcode pipeline names outside this module.
- Keep this file free of runtime logic.
"""

from __future__ import annotations

from typing import Literal

# Environments

type AppEnv = Literal["dev", "staging", "prod"]
DEV: AppEnv = "dev"
STAGING: AppEnv = "staging"
PROD: AppEnv = "prod"

ENVIRONMENTS: tuple[AppEnv, ...] = (DEV, STAGING, PROD)

# Runtime defaults


DEFAULT_BATCH_SIZE: int = 5_000
MAX_BATCH_SIZE: int = 20_000
DEFAULT_MAX_RETRIES: int = 3
DEFAULT_RETRY_BACKOFF_SECONDS: int = 2

DEFAULT_TIMEZONE: str = "UTC"
DEFAULT_DATE_FORMAT: str = "%Y-%m-%d"
DEFAULT_TIMESTAMP_FORMAT: str = "%Y-%m-%dT%H:%M:%SZ"
DEFAULT_PARTITION_DATE_FORMAT: str = "%Y%m%d"
DEFAULT_PARTITION_HOUR_FORMAT: str = "%Y%m%d%H"

DEFAULT_CHECKPOINT_NAMESPACE: str = "project_pulse"
DEFAULT_APP_NAME: str = "project-pulse-kg"


# Config section names


CONFIG_SECTION_APP: str = "app"
CONFIG_SECTION_API: str = "api"
CONFIG_SECTION_SECURITY: str = "security"
CONFIG_SECTION_RUNTIME: str = "runtime"
CONFIG_SECTION_PIPELINES: str = "pipelines"
CONFIG_SECTION_CHECKPOINTS: str = "checkpoints"
CONFIG_SECTION_MYSQL: str = "mysql"
CONFIG_SECTION_NEO4J: str = "neo4j"
CONFIG_SECTION_METADATA_DB: str = "metadata_db"
CONFIG_SECTION_OBSERVABILITY: str = "observability"
CONFIG_SECTION_SCHEDULER: str = "scheduler"
CONFIG_SECTION_ONTOLOGY: str = "ontology"
CONFIG_SECTION_WEIGHTING: str = "weighting"
CONFIG_SECTION_INFERENCE: str = "inference"
CONFIG_SECTION_GDS: str = "gds"
CONFIG_SECTION_SOURCE_INCLUSION: str = "source_inclusion"
CONFIG_SECTION_SERVING: str = "serving"

CONFIG_SECTIONS: tuple[str, ...] = (
    CONFIG_SECTION_APP,
    CONFIG_SECTION_API,
    CONFIG_SECTION_SECURITY,
    CONFIG_SECTION_RUNTIME,
    CONFIG_SECTION_PIPELINES,
    CONFIG_SECTION_CHECKPOINTS,
    CONFIG_SECTION_MYSQL,
    CONFIG_SECTION_NEO4J,
    CONFIG_SECTION_METADATA_DB,
    CONFIG_SECTION_OBSERVABILITY,
    CONFIG_SECTION_SCHEDULER,
    CONFIG_SECTION_ONTOLOGY,
    CONFIG_SECTION_WEIGHTING,
    CONFIG_SECTION_INFERENCE,
    CONFIG_SECTION_GDS,
    CONFIG_SECTION_SOURCE_INCLUSION,
    CONFIG_SECTION_SERVING,
)


# Source inclusion categories


GRAPH_CORE: str = "graph_core"
GRAPH_ENRICHMENT: str = "graph_enrichment"
SERVING_ONLY: str = "serving_only"
FEATURE_SOURCE: str = "feature_source"
EXCLUDED: str = "excluded"

SOURCE_INCLUSION_CATEGORIES: tuple[str, ...] = (
    GRAPH_CORE,
    GRAPH_ENRICHMENT,
    SERVING_ONLY,
    FEATURE_SOURCE,
    EXCLUDED,
)


# Graph node labels
# Keep these synchronized with docs/ontology.md and configs/ontology.yaml


USER: str = "User"
AVATAR: str = "Avatar"
BADGE: str = "Badge"

TEAM: str = "Team"
LEAGUE: str = "League"
MATCH: str = "Match"

PRIVATE_LEAGUE: str = "PrivateLeague"
LEAGUE_THEME: str = "LeagueTheme"
INFLUENCER_LEAGUE: str = "InfluencerLeague"

POST: str = "Post"
COMMENT: str = "Comment"
DISCUSSION: str = "Discussion"
PREDICTION_DISCUSSION: str = "PredictionDiscussion"
CONVERSATION: str = "Conversation"
DIRECT_PAIR: str = "DirectPair"

PERSONA_STATE: str = "PersonaState"
TOPIC: str = "Topic"
SENTIMENT: str = "Sentiment"
RATING_SNAPSHOT: str = "RatingSnapshot"

CHATBOT_CONVERSATION: str = "ChatbotConversation"
CHATBOT_MESSAGE: str = "ChatbotMessage"
TOOL_CALL: str = "ToolCall"
TOOL: str = "Tool"

COIN_TRANSACTION: str = "CoinTransaction"
VOUCHER: str = "Voucher"
PARTNER_REWARD: str = "PartnerReward"
SUBSCRIPTION_PRODUCT: str = "SubscriptionProduct"
ACHIEVEMENT: str = "Achievement"
FINANCIAL_EVENT: str = "FinancialEvent"

DUEL: str = "Duel"
SUPER6_ROUND: str = "Super6Round"
LMS_COMPETITION: str = "LMSCompetition"

POLL: str = "Poll"
QUESTION: str = "Question"
QUIZ: str = "Quiz"
QUIZ_QUESTION: str = "QuizQuestion"
TAG: str = "Tag"

NOTIFICATION_CONTENT: str = "NotificationContent"
MODERATION_EVENT: str = "ModerationEvent"

AI_ARTICLE: str = "AIArticle"
NEWS: str = "News"

GRAPH_NODE_LABELS: tuple[str, ...] = (
    USER,
    AVATAR,
    BADGE,
    TEAM,
    LEAGUE,
    MATCH,
    PRIVATE_LEAGUE,
    LEAGUE_THEME,
    INFLUENCER_LEAGUE,
    POST,
    COMMENT,
    DISCUSSION,
    PREDICTION_DISCUSSION,
    CONVERSATION,
    DIRECT_PAIR,
    PERSONA_STATE,
    TOPIC,
    SENTIMENT,
    RATING_SNAPSHOT,
    CHATBOT_CONVERSATION,
    CHATBOT_MESSAGE,
    TOOL_CALL,
    TOOL,
    COIN_TRANSACTION,
    VOUCHER,
    PARTNER_REWARD,
    SUBSCRIPTION_PRODUCT,
    ACHIEVEMENT,
    FINANCIAL_EVENT,
    DUEL,
    SUPER6_ROUND,
    LMS_COMPETITION,
    POLL,
    QUESTION,
    QUIZ,
    QUIZ_QUESTION,
    TAG,
    NOTIFICATION_CONTENT,
    MODERATION_EVENT,
    AI_ARTICLE,
    NEWS,
)


# Graph relationship types
# Keep these synchronized with docs/ontology.md and configs/ontology.yaml


EQUIPPED: str = "EQUIPPED"
AWARDED: str = "AWARDED"
FAVORS: str = "FAVORS"

PLAYS_IN: str = "PLAYS_IN"
HOME_TEAM: str = "HOME_TEAM"
AWAY_TEAM: str = "AWAY_TEAM"
IN_LEAGUE: str = "IN_LEAGUE"
PLAYED_IN: str = "PLAYED_IN"

MEMBER_OF: str = "MEMBER_OF"
HAS_THEME: str = "HAS_THEME"
PROMOTES: str = "PROMOTES"

POSTED: str = "POSTED"
COMMENTED: str = "COMMENTED"
REPLIES_TO: str = "REPLIES_TO"
JOINED_DISCUSSION: str = "JOINED_DISCUSSION"
DIRECT_MESSAGE: str = "DIRECT_MESSAGE"

PREDICTED: str = "PREDICTED"
CHALLENGED: str = "CHALLENGED"
PARTICIPATED_IN: str = "PARTICIPATED_IN"
HAS_FIXTURE: str = "HAS_FIXTURE"
ABOUT: str = "ABOUT"

EXHIBITS: str = "EXHIBITS"
CURRENT_STATE: str = "CURRENT_STATE"
PREVIOUS_STATE: str = "PREVIOUS_STATE"
HAS_STATE: str = "HAS_STATE"
DISCUSSED: str = "DISCUSSED"
EXPRESSED: str = "EXPRESSED"
HAS_AFFINITY: str = "HAS_AFFINITY"
HAS_RATING: str = "HAS_RATING"

TALKED_TO: str = "TALKED_TO"
HAS_MESSAGE: str = "HAS_MESSAGE"
USED_TOOL: str = "USED_TOOL"

SPENT: str = "SPENT"
PURCHASED: str = "PURCHASED"
REDEEMED: str = "REDEEMED"
SUBSCRIBED_TO: str = "SUBSCRIBED_TO"
ACHIEVED: str = "ACHIEVED"

HAS_TAG: str = "HAS_TAG"
RECEIVED_NOTIFICATION: str = "RECEIVED_NOTIFICATION"
MODERATED: str = "MODERATED"

GENERATED_FOR: str = "GENERATED_FOR"

LIKED: str = "LIKED"
ANSWERED: str = "ANSWERED"
FRIENDED: str = "FRIENDED"

GRAPH_RELATIONSHIP_TYPES: tuple[str, ...] = (
    EQUIPPED,
    AWARDED,
    FAVORS,
    PLAYS_IN,
    HOME_TEAM,
    AWAY_TEAM,
    IN_LEAGUE,
    PLAYED_IN,
    MEMBER_OF,
    HAS_THEME,
    PROMOTES,
    POSTED,
    COMMENTED,
    REPLIES_TO,
    JOINED_DISCUSSION,
    DIRECT_MESSAGE,
    PREDICTED,
    CHALLENGED,
    PARTICIPATED_IN,
    HAS_FIXTURE,
    ABOUT,
    EXHIBITS,
    CURRENT_STATE,
    PREVIOUS_STATE,
    HAS_STATE,
    DISCUSSED,
    EXPRESSED,
    HAS_AFFINITY,
    HAS_RATING,
    TALKED_TO,
    HAS_MESSAGE,
    USED_TOOL,
    SPENT,
    PURCHASED,
    REDEEMED,
    SUBSCRIBED_TO,
    ACHIEVED,
    HAS_TAG,
    RECEIVED_NOTIFICATION,
    MODERATED,
    GENERATED_FOR,
    LIKED,
    ANSWERED,
    FRIENDED,
)


# Pipeline names


SOURCE_INVENTORY_PIPELINE: str = "source_inventory_pipeline"
CONSTRAINTS_PIPELINE: str = "constraints_pipeline"

IDENTITY_PIPELINE: str = "identity_pipeline"
SPORTS_PIPELINE: str = "sports_pipeline"
SOCIAL_PIPELINE: str = "social_pipeline"
CONTENT_PIPELINE: str = "content_pipeline"
BEHAVIOR_PIPELINE: str = "behavior_pipeline"
INTELLIGENCE_PIPELINE: str = "intelligence_pipeline"
AI_PIPELINE: str = "ai_pipeline"
ECONOMY_PIPELINE: str = "economy_pipeline"
COMPETITION_PIPELINE: str = "competition_pipeline"
COMMUNICATION_PIPELINE: str = "communication_pipeline"
NOTIFICATIONS_PIPELINE: str = "notifications_pipeline"
MODERATION_PIPELINE: str = "moderation_pipeline"
ANALYTICS_FEATURE_PIPELINE: str = "analytics_feature_pipeline"
TEMPORAL_PIPELINE: str = "temporal_pipeline"

FULL_BACKFILL_PIPELINE: str = "full_backfill_pipeline"
INCREMENTAL_PIPELINE: str = "incremental_pipeline"
SERVING_MATERIALIZATION_PIPELINE: str = "serving_materialization_pipeline"

PIPELINE_NAMES: tuple[str, ...] = (
    SOURCE_INVENTORY_PIPELINE,
    CONSTRAINTS_PIPELINE,
    IDENTITY_PIPELINE,
    SPORTS_PIPELINE,
    SOCIAL_PIPELINE,
    CONTENT_PIPELINE,
    BEHAVIOR_PIPELINE,
    INTELLIGENCE_PIPELINE,
    AI_PIPELINE,
    ECONOMY_PIPELINE,
    COMPETITION_PIPELINE,
    COMMUNICATION_PIPELINE,
    NOTIFICATIONS_PIPELINE,
    MODERATION_PIPELINE,
    ANALYTICS_FEATURE_PIPELINE,
    TEMPORAL_PIPELINE,
    FULL_BACKFILL_PIPELINE,
    INCREMENTAL_PIPELINE,
    SERVING_MATERIALIZATION_PIPELINE,
)


# Job / analytics names


LEIDEN_JOB: str = "leiden"
PAGERANK_JOB: str = "pagerank"
CENTRALITY_JOB: str = "centrality"
INFERENCE_JOB: str = "inference"
SERVING_MATERIALIZATION_JOB: str = "serving_materialization"
RECONCILIATION_JOB: str = "reconciliation"
SOURCE_INVENTORY_AUDIT_JOB: str = "source_inventory_audit"

JOB_NAMES: tuple[str, ...] = (
    LEIDEN_JOB,
    PAGERANK_JOB,
    CENTRALITY_JOB,
    INFERENCE_JOB,
    SERVING_MATERIALIZATION_JOB,
    RECONCILIATION_JOB,
    SOURCE_INVENTORY_AUDIT_JOB,
)


# GDS / analytics defaults


DEFAULT_GDS_GRAPH_NAME: str = "hidden_tribes"
DEFAULT_LEIDEN_WRITE_PROPERTY: str = "tribe_id"
DEFAULT_PAGERANK_WRITE_PROPERTY: str = "pagerank_score"
DEFAULT_GDS_RELATIONSHIP_WEIGHT_PROPERTY: str = "shared_league_weight"
DEFAULT_MEMBERSHIP_ACTIVITY_WEIGHT_PROPERTY: str = "activity_weight"


# Checkpoint strategies


CHECKPOINT_STRATEGY_TIMESTAMP_WATERMARK: str = "timestamp_watermark"
CHECKPOINT_STRATEGY_NUMERIC_WATERMARK: str = "numeric_watermark"
CHECKPOINT_STRATEGY_FULL_REFRESH: str = "full_refresh"

CHECKPOINT_STRATEGIES: tuple[str, ...] = (
    CHECKPOINT_STRATEGY_TIMESTAMP_WATERMARK,
    CHECKPOINT_STRATEGY_NUMERIC_WATERMARK,
    CHECKPOINT_STRATEGY_FULL_REFRESH,
)


# Common metadata keys used in logs / job tracking / records


KEY_RUN_ID: str = "run_id"
KEY_JOB_NAME: str = "job_name"
KEY_PIPELINE_NAME: str = "pipeline_name"
KEY_TABLE_NAME: str = "table_name"
KEY_BATCH_ID: str = "batch_id"
KEY_BATCH_SIZE: str = "batch_size"
KEY_RECORD_COUNT: str = "record_count"
KEY_GRAPH_NAME: str = "graph_name"
KEY_VERSION: str = "version"
KEY_ENV: str = "env"
KEY_ERROR: str = "error"
KEY_STATUS: str = "status"
KEY_STARTED_AT: str = "started_at"
KEY_FINISHED_AT: str = "finished_at"
KEY_DURATION_MS: str = "duration_ms"

COMMON_METADATA_KEYS: tuple[str, ...] = (
    KEY_RUN_ID,
    KEY_JOB_NAME,
    KEY_PIPELINE_NAME,
    KEY_TABLE_NAME,
    KEY_BATCH_ID,
    KEY_BATCH_SIZE,
    KEY_RECORD_COUNT,
    KEY_GRAPH_NAME,
    KEY_VERSION,
    KEY_ENV,
    KEY_ERROR,
    KEY_STATUS,
    KEY_STARTED_AT,
    KEY_FINISHED_AT,
    KEY_DURATION_MS,
)


# Log event names


EVENT_PIPELINE_STARTED: str = "pipeline_started"
EVENT_PIPELINE_FINISHED: str = "pipeline_finished"
EVENT_EXTRACTION_STARTED: str = "extraction_started"
EVENT_EXTRACTION_FINISHED: str = "extraction_finished"
EVENT_TRANSFORMATION_STARTED: str = "transformation_started"
EVENT_TRANSFORMATION_FINISHED: str = "transformation_finished"
EVENT_LOAD_STARTED: str = "load_started"
EVENT_LOAD_FINISHED: str = "load_finished"
EVENT_VALIDATION_FAILED: str = "validation_failed"
EVENT_ANALYTICS_STARTED: str = "analytics_started"
EVENT_ANALYTICS_FINISHED: str = "analytics_finished"

LOG_EVENT_NAMES: tuple[str, ...] = (
    EVENT_PIPELINE_STARTED,
    EVENT_PIPELINE_FINISHED,
    EVENT_EXTRACTION_STARTED,
    EVENT_EXTRACTION_FINISHED,
    EVENT_TRANSFORMATION_STARTED,
    EVENT_TRANSFORMATION_FINISHED,
    EVENT_LOAD_STARTED,
    EVENT_LOAD_FINISHED,
    EVENT_VALIDATION_FAILED,
    EVENT_ANALYTICS_STARTED,
    EVENT_ANALYTICS_FINISHED,
)
