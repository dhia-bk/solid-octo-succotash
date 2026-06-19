// 003_node_labels.cypher
// Purpose: Register all expected node labels in a graph metadata node.
//          Used for schema audit and label coverage checks.
// Unlocks: app/validation/source_coverage_checks.py label checks
// Depends on: 001_constraints.cypher
//
// The label list mirrors GRAPH_NODE_LABELS in app/core/constants.py exactly.
// This migration creates no schema objects — it writes a single GraphSchemaMeta
// node so pipeline audit jobs can verify all expected labels are present.

MERGE (meta:GraphSchemaMeta {schema_type: 'node_labels'})
SET meta.labels = [
    'User', 'Avatar', 'Badge',
    'Team', 'League', 'Match',
    'PrivateLeague', 'LeagueTheme', 'InfluencerLeague',
    'Post', 'Comment', 'Discussion', 'PredictionDiscussion',
    'Conversation', 'DirectPair',
    'PersonaState', 'Topic', 'Sentiment', 'RatingSnapshot',
    'ChatbotConversation', 'ChatbotMessage', 'ToolCall', 'Tool',
    'CoinTransaction', 'Voucher', 'PartnerReward',
    'SubscriptionProduct', 'Achievement', 'FinancialEvent',
    'Duel', 'Super6Round', 'LMSCompetition',
    'Poll', 'Question', 'Quiz', 'QuizQuestion', 'Tag',
    'NotificationContent', 'ModerationEvent',
    'AIArticle', 'News'
],
meta.label_count = 41,
meta.registered_at = datetime(),
meta.schema_version = '1.0.0';
