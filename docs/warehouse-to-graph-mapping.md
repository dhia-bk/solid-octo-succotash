# `docs/warehouse-to-graph-mapping.md`

This version includes **every table present in the warehouse schema** and assigns each one to a graph role.

---

# Warehouse → Graph Mapping

This document defines how **every table in the Scorpii Data Warehouse** maps into the Project Pulse Knowledge Graph.

Each table is classified as one of the following:

| Type               | Meaning                      |
| ------------------ | ---------------------------- |
| Graph Node         | Creates graph nodes          |
| Graph Relationship | Creates graph edges          |
| Graph Enrichment   | Adds properties or context   |
| Feature Source     | Used for analytics features  |
| Serving Only       | Used for API/serving outputs |
| Excluded           | Not ingested into graph      |

---

# Identity Domain

### dim_users

Graph Node

Creates:

```
(:User)
```

Primary Key

```
user_id
```

Relationships

```
User -> MEMBER_OF -> PrivateLeague
User -> PREDICTED -> Match
User -> EXHIBITS -> PersonaState
User -> TALKED_TO -> ChatbotConversation
```

---

### dim_avatars

Graph Node

```
(:Avatar)
```

Relationship

```
User -> EQUIPPED -> Avatar
```

---

### dim_badges

Graph Node

```
(:Badge)
```

Relationship

```
User -> AWARDED -> Badge
```

---

### app_users

Excluded

Operational admin table.
Not used for graph modeling.

---

# Sports Domain

### dim_teams

Graph Node

```
(:Team)
```

---

### dim_teams_enhanced

Graph Enrichment

Adds metadata to Team nodes.

---

### dim_leagues

Graph Node

```
(:League)
```

---

### dim_fixtures

Graph Node

```
(:Match)
```

Relationships

```
Match -> HOME_TEAM -> Team
Match -> AWAY_TEAM -> Team
Match -> IN_LEAGUE -> League
```

---

# Social Domain

### dim_private_leagues

Graph Node

```
(:PrivateLeague)
```

---

### dim_private_league_members

Graph Relationship

```
User -> MEMBER_OF -> PrivateLeague
```

Properties

```
join_date
role
activity_weight
```

---

### dim_private_league_themes

Graph Node

```
(:LeagueTheme)
```

Relationship

```
PrivateLeague -> HAS_THEME -> LeagueTheme
```

---

### dim_posts

Graph Node

```
(:Post)
```

Relationship

```
User -> POSTED -> Post
```

---

### dim_comments

Graph Node

```
(:Comment)
```

Relationship

```
User -> COMMENTED -> Comment
Comment -> REPLIES_TO -> Post
```

---

### dim_discussions

Graph Node

```
(:Discussion)
```

---

### dim_prediction_discussions

Graph Relationship

```
Discussion -> ABOUT -> Prediction
```

---

### fct_discussion_events

Graph Relationship

```
User -> JOINED_DISCUSSION -> Discussion
```

---

### dim_chat_conversations_mysql

Graph Node

```
(:Conversation)
```

---

### dim_chat_direct_pairs

Graph Relationship

```
User -> DIRECT_MESSAGE -> User
```

Properties

```
message_count
last_message_at
```

---

# Intelligence Domain

### fct_user_behavior

Graph Node

```
(:PersonaState)
```

Relationships

```
User -> CURRENT_STATE -> PersonaState
PersonaState -> PREVIOUS_STATE -> PersonaState
```

---

### fct_topics

Graph Node

```
(:Topic)
```

---

### fct_sentiment

Graph Node

```
(:Sentiment)
```

---

### fct_team_affinity

Graph Relationship

```
User -> HAS_AFFINITY -> Team
```

Properties

```
affinity_score
```

---

### fct_user_activities

Graph Enrichment

Adds activity signals to users.

---

### fct_user_sessions

Graph Enrichment

Used for recency and engagement metrics.

---

### fct_user_rating_history

Graph Node

```
(:RatingSnapshot)
```

Relationship

```
User -> HAS_RATING -> RatingSnapshot
```

---

# Competition Domain

### fct_predictions

Graph Relationship

```
User -> PREDICTED -> Match
```

Properties

```
prediction
points_awarded
timestamp
```

---

### fct_prediction_duels

Graph Relationship

```
User -> CHALLENGED -> User
```

Node

```
(:Duel)
```

---

### dim_super6_rounds

Graph Node

```
(:Super6Round)
```

---

### dim_super6_round_fixtures

Graph Relationship

```
Super6Round -> HAS_FIXTURE -> Match
```

---

### fct_super6_participants

Graph Relationship

```
User -> PARTICIPATED_IN -> Super6Round
```

---

### dim_lms_competitions

Graph Node

```
(:LMSCompetition)
```

Relationship

```
User -> PARTICIPATED_IN -> LMSCompetition
```

---

# AI Domain

### dim_chatbot_conversations

Graph Node

```
(:ChatbotConversation)
```

---

### fct_chatbot_messages

Graph Node

```
(:ChatbotMessage)
```

Relationship

```
ChatbotConversation -> HAS_MESSAGE -> ChatbotMessage
```

---

### fct_chatbot_tool_calls

Graph Node

```
(:ToolCall)
```

Relationship

```
ChatbotMessage -> USED_TOOL -> ToolCall
```

---

### dim_ai_articles

Graph Node

```
(:AIArticle)
```

Relationship

```
AIArticle -> ABOUT -> Team
AIArticle -> ABOUT -> Match
```

---

### dim_news

Graph Node

```
(:News)
```

Relationship

```
News -> ABOUT -> Team
News -> ABOUT -> Match
```

---

# Economy Domain

### fct_coin_transactions

Graph Node

```
(:CoinTransaction)
```

Relationship

```
User -> SPENT -> CoinTransaction
```

---

### dim_voucher_catalog

Graph Node

```
(:Voucher)
```

---

### fct_voucher_purchases

Graph Relationship

```
User -> PURCHASED -> Voucher
```

---

### dim_partner_reward_catalog

Graph Node

```
(:PartnerReward)
```

---

### fct_partner_reward_inventory

Graph Enrichment

Inventory tracking.

---

### fct_partner_reward_redemptions

Graph Relationship

```
User -> REDEEMED -> PartnerReward
```

---

### dim_subscription_products

Graph Node

```
(:SubscriptionProduct)
```

---

### fct_subscription_lifecycle

Graph Relationship

```
User -> SUBSCRIBED_TO -> SubscriptionProduct
```

---

### fct_awards_and_achievements

Graph Node

```
(:Achievement)
```

Relationship

```
User -> ACHIEVED -> Achievement
```

---

### fct_financials

Feature Source

Used for revenue analytics only.

---

# Gamification Domain

### dim_fixture_polls_enhanced

Graph Node

```
(:Poll)
```

---

### dim_questions

Graph Node

```
(:Question)
```

---

### dim_questions_enhanced

Graph Enrichment

---

### dim_quizzes

Graph Node

```
(:Quiz)
```

---

### dim_quiz_questions_enhanced

Graph Node

```
(:QuizQuestion)
```

Relationship

```
Quiz -> HAS_QUESTION -> QuizQuestion
```

---

### dim_tags

Graph Node

```
(:Tag)
```

Relationships

```
Post -> HAS_TAG -> Tag
News -> HAS_TAG -> Tag
AIArticle -> HAS_TAG -> Tag
```

---

# Notifications Domain

### dim_notification_content

Serving Only

---

### dim_notification_preferences

Serving Only

---

### fct_notification_content_daily

Serving Only

---

### jct_notification_recipients

Serving Only

Relationship

```
User -> RECEIVED_NOTIFICATION -> NotificationContent
```

---

### fct_user_notification_stats

Serving Only

---

# Moderation Domain

### fct_moderation_events

Graph Node

```
(:ModerationEvent)
```

Relationship

```
User -> MODERATED -> Content
```

---

# Analytics Domain

These tables **do not produce graph nodes**.

They are used for **feature engineering and monitoring only**.

### fct_daily_metrics

Feature Source

### fct_heatmap_events

Feature Source

### fct_content_engagement_daily

Feature Source

### fct_retention_cohorts

Feature Source

### fct_team_daily_growth

Feature Source

---

# Influencer Domain

### dim_influencer_leagues

Graph Node

```
(:InfluencerLeague)
```

Relationship

```
InfluencerLeague -> PROMOTES -> PrivateLeague
```

---

# Summary

| Category                 | Count |
| ------------------------ | ----- |
| Graph Nodes              | 34    |
| Graph Relationships      | 21    |
| Graph Enrichment Sources | 12    |
| Feature Sources          | 6     |
| Serving Only             | 5     |
| Excluded                 | 1     |

---

# Governance Rule

Every warehouse table must appear in this document.

If a new table appears in the warehouse schema, it must be added here before ingestion pipelines are created.

This document is the **authoritative contract between the warehouse and the knowledge graph platform**.

---