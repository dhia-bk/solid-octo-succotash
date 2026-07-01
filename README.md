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
```

## Repository structure

```text
project-pulse-kg/
  app/           application code
  configs/       environment and runtime config
  docs/          architecture, ontology, runbooks
  infra/         docker, k8s, terraform, cicd
  migrations/    neo4j and metadata migrations
  scripts/       operational entrypoints
  tests/         unit, integration, e2e tests
```

## Local setup

### Requirements

- Python 3.12+
- Docker and Docker Compose
- Make
- Access to:
  - MySQL warehouse
  - Neo4j instance
  - local or remote metadata database

### 1. Create virtual environment

```bash
python -m venv .venv
source .venv/bin/activate
```

### 2. Copy environment file

```bash
cp .env.example .env
```

### 3. Install dependencies

```bash
make setup
```

### 4. Start local services

```bash
docker compose up -d
```

### 5. Validate config

```bash
python scripts/validate_config.py
```

## Run modes

### Full backfill

Loads the graph from warehouse history.

```bash
make run-backfill
```

### Incremental sync

Loads only new or changed data using checkpoints.

```bash
make run-sync
```

### Leiden analytics

Runs graph projection and tribe detection.

```bash
make run-leiden
```

### API

Starts the FastAPI service.

```bash
make run-api
```

### Tests

```bash
make test
```

## Deployment overview

### Environments

- dev
- staging
- prod

### Runtime components

- API service
- worker service
- scheduler / cron jobs
- metadata database
- Neo4j graph database
- optional analytics environment for heavy GDS execution

### Typical production flow

1. Config and secrets are loaded
2. Source inventory and checkpoints are read
3. Incremental or backfill pipelines run
4. Validation and reconciliation checks execute
5. Graph analytics jobs run
6. Serving views are materialized
7. API exposes stable read contracts

## Make targets

```bash
make setup
make lint
make format
make test
make run-backfill
make run-sync
make run-api
make run-leiden
```

## Notes

- Do not commit secrets
- Do not use `.env` in production
- Use environment-specific config overlays in `configs/`
- All graph schema changes should go through `migrations/`
