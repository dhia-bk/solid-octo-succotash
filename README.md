# Project Pulse Knowledge Graph

Project Pulse Knowledge Graph is the production graph intelligence platform for Scorpii. It ingests relational O data, transforms it into a Neo4j knowledge graph, runs graph analytics such as Leiden community detection, materializes serving views, and exposes stable APIs for downstream product and intelligence use cases.

## Purpose

The platform exists to turn disconnected warehouse facts into connected behavioral intelligence.

It supports:
- user, team, match, and league graph modeling
- private-league and social connectivity analysis
- temporal persona tracking
- tribe detection with graph analytics
- sentiment/topic enrichment and inference
- serving features for APIs and downstream consumers

## High-level architecture

```text
MySQL DWH
   |
   v
Extractors -> Transformers -> Validators -> Neo4j Loaders
   |
   v
Neo4j AuraDB
   |
   +--> Graph Analytics / GDS jobs
   |       - Leiden
   |       - centrality
   |       - inference
   |
   +--> Serving materialization
   |
   v
FastAPI
   |
   v
Consumers / internal services / analytics clients

Repository structure
project-pulse-kg/
  app/           application code
  configs/       environment and runtime config
  docs/          architecture, ontology, runbooks
  infra/         docker, k8s, terraform, cicd
  migrations/    neo4j and metadata migrations
  scripts/       operational entrypoints
  tests/         unit, integration, e2e tests
Local setup
Requirements

Python 3.12+

Docker and Docker Compose

Make

Access to:

MySQL warehouse

Neo4j instance

local or remote metadata database

1. Create virtual environment
python -m venv .venv
source .venv/bin/activate
2. Copy environment file
cp .env.example .env
3. Install dependencies
make setup
4. Start local services
docker compose up -d
5. Validate config
python scripts/validate_config.py
Run modes
Full backfill

Loads the graph from warehouse history.

make run-backfill
Incremental sync

Loads only new or changed data using checkpoints.

make run-sync
Leiden analytics

Runs graph projection and tribe detection.

make run-leiden
API

Starts the FastAPI service.

make run-api
Tests
make test
Deployment overview
Environments

dev

staging

prod

Runtime components

API service

worker service

scheduler / cron jobs

metadata database

Neo4j graph database

optional analytics environment for heavy GDS execution

Typical production flow

Config and secrets are loaded

Source inventory and checkpoints are read

Incremental or backfill pipelines run

Validation and reconciliation checks execute

Graph analytics jobs run

Serving views are materialized

API exposes stable read contracts

Make targets
make setup
make lint
make format
make test
make run-backfill
make run-sync
make run-api
make run-leiden
Notes

Do not commit secrets

Do not use .env in production

Use environment-specific config overlays in configs/

All graph schema changes should go through migrations/