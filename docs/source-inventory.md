# `docs/source-inventory.md`

# Source Inventory

This document contains the **complete inventory of all tables present in the Scorpii Data Warehouse** as of the latest audit.

This inventory is the **authoritative source list used by the ingestion pipelines**.

Every table in the warehouse must appear in this document.

Each table is assigned a **source classification** that determines how it is handled by the platform.

---

# Source Classifications

| Classification   | Meaning                               |
| ---------------- | ------------------------------------- |
| Graph Core       | Required to build the graph structure |
| Graph Enrichment | Adds additional properties or context |
| Serving Only     | Used only for API outputs             |
| Feature Source   | Used only for analytics features      |
| Excluded         | Ignored by the graph system           |

---

# Dimension Tables

Dimension tables define **entities or static metadata**.

### Identity

```
dim_users
dim_avatars
dim_badges
app_users
```

---

### Sports

```
dim_teams
dim_teams_enhanced
dim_leagues
dim_fixtures
```

---

### Social

```
dim_private_leagues
dim_private_league_members
dim_private_league_themes
dim_posts
dim_comments
dim_discussions
dim_prediction_discussions
```

---

### Messaging

```
dim_chat_conversations_mysql
dim_chat_direct_pairs
```

---

### AI

```
dim_chatbot_conversations
dim_ai_articles
dim_news
```

---

### Competition

```
dim_lms_competitions
dim_super6_rounds
dim_super6_round_fixtures
```

---

### Economy

```
dim_voucher_catalog
dim_partner_reward_catalog
dim_subscription_products
```

---

### Engagement

```
dim_fixture_polls_enhanced
dim_questions
dim_questions_enhanced
dim_quizzes
dim_quiz_questions_enhanced
dim_tags
```

---

### Influencer System

```
dim_influencer_leagues
```

---

# Fact Tables

Fact tables contain **events or measurable user actions**.

---

### User Behavior

```
fct_user_behavior
fct_user_activities
fct_user_sessions
fct_user_rating_history
```

---

### Intelligence Signals

```
fct_topics
fct_sentiment
fct_team_affinity
```

---

### Predictions and Competitions

```
fct_predictions
fct_prediction_duels
fct_super6_participants
```

---

### Economy Events

```
fct_coin_transactions
fct_voucher_purchases
fct_partner_reward_inventory
fct_partner_reward_redemptions
fct_subscription_lifecycle
fct_financials
```

---

### Content Events

```
fct_discussion_events
fct_chatbot_messages
fct_chatbot_tool_calls
```

---

### Notifications

```
fct_notification_content_daily
fct_user_notification_stats
```

---

### Achievements

```
fct_awards_and_achievements
```

---

### Moderation

```
fct_moderation_events
```

---

# Junction Tables

Junction tables define **many-to-many relationships**.

```
jct_notification_recipients
```

---

# Analytics / Telemetry Tables

These tables are used **only for analytics and product metrics**.

They do not create graph nodes or relationships.

```
fct_daily_metrics
fct_heatmap_events
fct_content_engagement_daily
fct_retention_cohorts
fct_team_daily_growth
```

---

# Table Count Summary

| Category           | Tables |
| ------------------ | ------ |
| Dimension Tables   | 28     |
| Fact Tables        | 27     |
| Junction Tables    | 1      |
| Analytics Tables   | 5      |
| Operational Tables | 1      |

**Total Warehouse Tables**

```
62
```

---

# Domain Overview

| Domain         | Tables |
| -------------- | ------ |
| Identity       | 4      |
| Sports         | 4      |
| Social         | 7      |
| Messaging      | 2      |
| AI             | 3      |
| Competition    | 3      |
| Economy        | 3      |
| Engagement     | 6      |
| Influencer     | 1      |
| Behavior       | 4      |
| Intelligence   | 3      |
| Prediction     | 3      |
| Economy Events | 6      |
| Content Events | 3      |
| Notifications  | 2      |
| Achievements   | 1      |
| Moderation     | 1      |
| Analytics      | 5      |

---

# Inventory Governance Rules

1. **Every warehouse table must appear in this document.**

2. If a new table appears in the warehouse:

   * It must first be added to this document.
   * Then added to `warehouse-to-graph-mapping.md`.
   * Then added to `configs/source_inclusion.yaml`.

3. Pipelines must **never ingest a table that is not listed here**.

4. This document must remain synchronized with:

```
docs/warehouse-to-graph-mapping.md
configs/source_inclusion.yaml
```

---

# Schema Audit Timestamp

Latest schema audit:

```
January 23, 2026
```

Future audits must update this document.

---

