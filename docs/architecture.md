# Project Pulse Knowledge Graph Architecture

## Overview

Project Pulse Knowledge Graph is a production data platform that transforms relational warehouse data into a graph intelligence system built on Neo4j.

The system performs the following functions:

1. Extract data from the Scorpii Data Warehouse
2. Normalize and canonicalize entities
3. Load entities and relationships into Neo4j
4. Run graph analytics (community detection, centrality)
5. Perform behavioral inference
6. Materialize serving features
7. Expose APIs for downstream consumers

---

# System Components

## 1. Data Warehouse

Primary source of truth.

Technology:
- MySQL / relational warehouse

Contains:

Identity
- users
- avatars
- badges

Sports
- teams
- leagues
- fixtures

Social
- private leagues
- memberships
- posts
- comments
- discussions

Intelligence
- topics
- sentiment
- personas
- team affinity

Competition
- predictions
- duels
- Super6
- LMS competitions

Economy
- coins
- vouchers
- partner rewards
- subscriptions

AI
- chatbot conversations
- chatbot messages
- tool calls
- AI articles

Analytics / telemetry
- engagement
- heatmap events
- retention cohorts

---

# Platform Layers

## Layer 1 — Extractors

Location:

app/extractors/


Responsibilities:

- Query warehouse tables
- Apply incremental filters
- Paginate results
- Return typed warehouse records

No transformations occur here.

---

## Layer 2 — Canonicalization

Location:

app/canonicalization/


Responsibilities:

- Resolve entity aliases
- Normalize IDs
- Map entity variants to canonical identifiers

Example:


Man Utd
Manchester United
MAN UNITED


→


Team(id=33)


---

## Layer 3 — Transformers

Location:

app/transformers/


Responsibilities:

- Convert warehouse rows into graph records
- Build node and relationship objects
- Apply weighting
- Apply temporal modeling
- Apply enrichment logic

Output:


GraphRecord
NodeRecord
RelationshipRecord


---

## Layer 4 — Loaders

Location:


app/loaders/


Responsibilities:

- Write graph data into Neo4j
- Apply MERGE queries
- Maintain graph constraints
- Batch writes for efficiency

---

## Layer 5 — Graph Database

Technology:


Neo4j AuraDB


Stores:

- entities
- relationships
- graph analytics outputs
- inference results

---

## Layer 6 — Graph Analytics

Location:


app/analytics/


Main algorithms:

Leiden
- community detection

PageRank
- user authority

Centrality
- influence scoring

Label propagation
- inference

Outputs written back to graph.

---

## Layer 7 — Serving Materialization

Location:


app/serving/


Produces stable views:

User profile
Tribe summary
Persona timeline
Inference results
Feature summaries

---

## Layer 8 — API

Location:


app/api/


Technology:


FastAPI


Exposes:

User insights
Tribe membership
Persona trajectory
Inferred labels
Content insights

---

# Runtime Jobs

## Full Backfill

Rebuilds graph from scratch.

Command:


make run-backfill


---

## Incremental Sync

Updates graph with new warehouse data.

Command:


make run-sync


---

## Graph Analytics

Runs GDS algorithms.

Command:


make run-leiden


---

## Inference

Runs tribe-based prediction.

Command:


make run-inference


---

# Metadata Database

Stores:

- job runs
- checkpoints
- model registry
- validation results

Technology:


PostgreSQL


---

# Observability

Metrics:
- pipeline latency
- sync lag
- graph node counts
- graph edge counts

Logs:
- structured JSON logs

Alerts:
- pipeline failure
- graph drift
- inference anomalies

---

# Deployment Architecture

Environment separation:


dev
staging
prod


Services:

API
Worker
Scheduler
Metadata DB
Neo4j

---

# Design Principles

Single responsibility per module

Explicit configuration via YAML

Reproducible analytics runs

Never overwrite ground truth

Graph is append-safe and auditable

All pipelines idempotent

All writes validated