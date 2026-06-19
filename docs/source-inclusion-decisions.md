# `docs/source-inclusion-decisions.md`

---

# Source Inclusion Decisions

This document defines **how every table in the Scorpii Data Warehouse is used by the Project Pulse Knowledge Graph platform**.

Each table is assigned exactly **one inclusion category**.

---

# Inclusion Categories

| Category         | Meaning                                        |
| ---------------- | ---------------------------------------------- |
| Graph Core       | Table creates core nodes or edges in the graph |
| Graph Enrichment | Adds properties or context to graph entities   |
| Serving Only     | Used only for API outputs                      |
| Feature Source   | Used for analytics features and models         |
| Excluded         | Not ingested into the graph system             |

---

# Identity Domain

### Graph Core

```
dim_users
```

Creates primary graph node:

```
(:User)
```

---

### Graph Enrichment

```
dim_avatars
dim_badges
```

Enhances user identity.

Relationships:

```
User -> EQUIPPED -> Avatar
User -> AWARDED -> Badge
```

---

### Excluded

```
app_users
```

Operational/admin identity table.

---

# Sports Domain

### Graph Core

```
dim_teams
dim_leagues
dim_fixtures
```

Creates nodes:

```
(:Team)
(:League)
(:Match)
```

Relationships:

```
Match -> HOME_TEAM -> Team
Match -> AWAY_TEAM -> Team
Match -> IN_LEAGUE -> League
```

---

### Graph Enrichment

```
dim_teams_enhanced
```

Adds metadata fields such as:

* team logos
* stadium
* historical data

---

# Social Domain

### Graph Core

```
dim_private_leagues
dim_private_league_members
dim_posts
dim_comments
```

Creates nodes:

```
(:PrivateLeague)
(:Post)
(:Comment)
```

Creates relationships:

```
User -> MEMBER_OF -> PrivateLeague
User -> POSTED -> Post
User -> COMMENTED -> Comment
```

---

### Graph Enrichment

```
dim_private_league_themes
```

Adds theme metadata to private leagues.

Relationship:

```
PrivateLeague -> HAS_THEME -> LeagueTheme
```

---

# Discussion Domain

### Graph Enrichment

```
dim_discussions
dim_prediction_discussions
fct_discussion_events
```

Adds discussion metadata and events.

Creates nodes:

```
(:Discussion)
```

Relationships:

```
User -> JOINED_DISCUSSION -> Discussion
Discussion -> ABOUT -> Prediction
```

---

# Messaging Domain

### Graph Enrichment

```
dim_chat_conversations_mysql
dim_chat_direct_pairs
```

Creates nodes:

```
(:Conversation)
```

Relationships:

```
User -> DIRECT_MESSAGE -> User
```

Used to enrich social graph connectivity.

---

# Intelligence Domain

### Graph Core

```
fct_user_behavior
fct_topics
fct_sentiment
```

Creates nodes:

```
(:PersonaState)
(:Topic)
(:Sentiment)
```

Relationships:

```
User -> CURRENT_STATE -> PersonaState
User -> DISCUSSED -> Topic
User -> EXPRESSED -> Sentiment
```

---

### Graph Enrichment

```
fct_team_affinity
fct_user_activities
fct_user_sessions
fct_user_rating_history
```

Adds behavioral signals:

* team affinity
* activity counts
* session history
* rating history

---

# Competition Domain

### Graph Core

```
fct_predictions
```

Creates relationship:

```
User -> PREDICTED -> Match
```

---

### Graph Enrichment

```
fct_prediction_duels
dim_super6_rounds
dim_super6_round_fixtures
fct_super6_participants
dim_lms_competitions
```

Creates nodes:

```
(:Duel)
(:Super6Round)
(:LMSCompetition)
```

Relationships:

```
User -> PARTICIPATED_IN -> Competition
```

---

# AI Domain

### Graph Enrichment

```
dim_chatbot_conversations
fct_chatbot_messages
fct_chatbot_tool_calls
```

Creates nodes:

```
(:ChatbotConversation)
(:ChatbotMessage)
(:ToolCall)
```

Relationships:

```
ChatbotConversation -> HAS_MESSAGE -> ChatbotMessage
ChatbotMessage -> USED_TOOL -> ToolCall
```

---

### Graph Enrichment

```
dim_ai_articles
dim_news
```

Creates nodes:

```
(:AIArticle)
(:News)
```

Relationships:

```
Article -> ABOUT -> Team
Article -> ABOUT -> Match
```

---

# Economy Domain

### Graph Enrichment

```
fct_coin_transactions
dim_voucher_catalog
fct_voucher_purchases
```

Creates nodes:

```
(:CoinTransaction)
(:Voucher)
```

Relationships:

```
User -> SPENT -> CoinTransaction
User -> PURCHASED -> Voucher
```

---

### Graph Enrichment

```
dim_partner_reward_catalog
fct_partner_reward_inventory
fct_partner_reward_redemptions
```

Creates nodes:

```
(:PartnerReward)
```

Relationships:

```
User -> REDEEMED -> PartnerReward
```

---

### Graph Enrichment

```
dim_subscription_products
fct_subscription_lifecycle
```

Creates nodes:

```
(:SubscriptionProduct)
```

Relationships:

```
User -> SUBSCRIBED_TO -> SubscriptionProduct
```

---

### Graph Enrichment

```
fct_awards_and_achievements
```

Creates nodes:

```
(:Achievement)
```

Relationships:

```
User -> ACHIEVED -> Achievement
```

---

### Feature Source

```
fct_financials
```

Used for revenue analytics only.

---

# Gamification Domain

### Graph Enrichment

```
dim_fixture_polls_enhanced
dim_questions
dim_questions_enhanced
dim_quizzes
dim_quiz_questions_enhanced
```

Creates nodes:

```
(:Poll)
(:Question)
(:Quiz)
(:QuizQuestion)
```

Relationships:

```
Quiz -> HAS_QUESTION -> QuizQuestion
```

---

### Graph Enrichment

```
dim_tags
```

Creates nodes:

```
(:Tag)
```

Relationships:

```
Post -> HAS_TAG -> Tag
News -> HAS_TAG -> Tag
AIArticle -> HAS_TAG -> Tag
```

---

# Notifications Domain

### Serving Only

```
dim_notification_content
dim_notification_preferences
fct_notification_content_daily
jct_notification_recipients
fct_user_notification_stats
```

Used for:

* notification APIs
* user messaging insights

These tables do **not create graph nodes**.

---

# Moderation Domain

### Graph Enrichment

```
fct_moderation_events
```

Creates nodes:

```
(:ModerationEvent)
```

Relationships:

```
Moderator -> MODERATED -> Content
```

---

# Influencer Domain

### Graph Enrichment

```
dim_influencer_leagues
```

Creates nodes:

```
(:InfluencerLeague)
```

Relationships:

```
InfluencerLeague -> PROMOTES -> PrivateLeague
```

---

# Analytics / Telemetry Domain

### Feature Source

```
fct_daily_metrics
fct_heatmap_events
fct_content_engagement_daily
fct_retention_cohorts
fct_team_daily_growth
```

Used for:

* engagement modeling
* churn modeling
* recommendation features
* health monitoring

These tables **do not create graph nodes**.

---

# Summary

| Category         | Table Count |
| ---------------- | ----------- |
| Graph Core       | 11          |
| Graph Enrichment | 33          |
| Serving Only     | 5           |
| Feature Source   | 6           |
| Excluded         | 1           |

Total tables covered:

```
56
```

---

# Governance Rules

1. **Every warehouse table must be assigned exactly one inclusion category.**

2. Any new warehouse table must be added to:

```
docs/source-inventory.md
docs/source-inclusion-decisions.md
docs/warehouse-to-graph-mapping.md
configs/source_inclusion.yaml
```

3. Pipelines may only ingest tables defined in this document.

4. Changes to inclusion categories require:

* architecture review
* pipeline update
* validation checks

---

# Schema Audit

Last verified warehouse schema:

```
January 23, 2026
```
