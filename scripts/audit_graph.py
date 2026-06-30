"""
Graph audit and analysis script for Project Pulse Knowledge Graph.

Sections:
  1. Schema health   — constraints, indexes, schema version
  2. Node census     — count per label, compare against declared labels
  3. Relationship census — count per type, compare against declared types
  4. Property health — null-rate on key properties per label
  5. Connectivity    — orphaned nodes, degree distribution, top hubs
  6. Source sync     — SourceSyncState freshness per warehouse source
  7. Pipeline runs   — recent job history from metadata PostgreSQL DB
  8. Data quality    — recent validation failures from metadata DB
  9. Graph metadata  — GDS projection configs, serving view configs

Usage:
    .venv/bin/python3 scripts/audit_graph.py [--json path/to/report.json]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from textwrap import indent

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

try:
    from neo4j import GraphDatabase
    from neo4j.exceptions import Neo4jError
except ImportError:
    sys.exit("neo4j package not found. Run: .venv/bin/pip install -e .")

try:
    import psycopg
except ImportError:
    psycopg = None  # metadata DB checks will be skipped


# ── helpers ───────────────────────────────────────────────────────────────────

NOW = datetime.now(timezone.utc).isoformat()

RESET  = "\033[0m"
BOLD   = "\033[1m"
GREEN  = "\033[32m"
YELLOW = "\033[33m"
RED    = "\033[31m"
CYAN   = "\033[36m"
DIM    = "\033[2m"

def ok(msg):    print(f"  {GREEN}✓{RESET} {msg}")
def warn(msg):  print(f"  {YELLOW}⚠{RESET} {msg}")
def fail(msg):  print(f"  {RED}✗{RESET} {msg}")
def info(msg):  print(f"  {CYAN}·{RESET} {msg}")
def header(msg): print(f"\n{BOLD}{'─' * 60}{RESET}\n{BOLD}{msg}{RESET}")

def run(session, cypher, **params):
    return [dict(r) for r in session.run(cypher, **params)]

def scalar(session, cypher, **params):
    rows = run(session, cypher, **params)
    if rows:
        return next(iter(rows[0].values()))
    return None


# ── declared schema (from migration files) ────────────────────────────────────

EXPECTED_LABELS = [
    "User", "Avatar", "Badge",
    "Team", "League", "Match",
    "PrivateLeague", "LeagueTheme", "InfluencerLeague",
    "Post", "Comment", "Discussion", "PredictionDiscussion",
    "Conversation", "DirectPair",
    "PersonaState", "Topic", "Sentiment", "RatingSnapshot",
    "ChatbotConversation", "ChatbotMessage", "ToolCall", "Tool",
    "CoinTransaction", "Voucher", "PartnerReward",
    "SubscriptionProduct", "Achievement", "FinancialEvent",
    "Duel", "Super6Round", "LMSCompetition",
    "Poll", "Question", "Quiz", "QuizQuestion", "Tag",
    "NotificationContent", "ModerationEvent", "AIArticle", "News",
]

EXPECTED_REL_TYPES = [
    "EQUIPPED", "AWARDED", "FAVORS",
    "PLAYS_IN", "HOME_TEAM", "AWAY_TEAM", "IN_LEAGUE", "PLAYED_IN",
    "MEMBER_OF", "HAS_THEME", "PROMOTES",
    "POSTED", "COMMENTED", "REPLIES_TO", "JOINED_DISCUSSION", "DIRECT_MESSAGE",
    "PREDICTED", "CHALLENGED", "PARTICIPATED_IN", "HAS_FIXTURE", "ABOUT",
    "EXHIBITS", "CURRENT_STATE", "PREVIOUS_STATE", "HAS_STATE",
    "DISCUSSED", "EXPRESSED", "HAS_AFFINITY", "HAS_RATING",
    "TALKED_TO", "HAS_MESSAGE", "USED_TOOL",
    "SPENT", "PURCHASED", "REDEEMED", "SUBSCRIBED_TO", "ACHIEVED",
    "HAS_TAG", "RECEIVED_NOTIFICATION", "MODERATED", "GENERATED_FOR",
    "LIKED", "ANSWERED", "FRIENDED",
]

EXPECTED_CONSTRAINTS = [
    "unique_user_id", "unique_avatar_id", "unique_badge_id",
    "unique_team_id", "unique_league_id", "unique_match_id",
    "unique_private_league_id", "unique_league_theme_id", "unique_influencer_league_id",
    "unique_post_id", "unique_comment_id", "unique_discussion_id",
    "unique_prediction_discussion_id", "unique_conversation_id", "unique_direct_pair_id",
    "unique_persona_state_id", "unique_topic_id", "unique_sentiment_id",
    "unique_rating_snapshot_id",
    "unique_chatbot_conversation_id", "unique_chatbot_message_id",
    "unique_tool_call_id", "unique_tool_id",
    "unique_coin_transaction_id", "unique_voucher_id", "unique_partner_reward_id",
    "unique_subscription_product_id", "unique_achievement_id", "unique_financial_event_id",
    "unique_duel_id", "unique_super6_round_id", "unique_lms_competition_id",
    "unique_poll_id", "unique_question_id", "unique_quiz_id", "unique_quiz_question_id",
    "unique_tag_id",
    "unique_notification_content_id", "unique_moderation_event_id",
    "unique_ai_article_id", "unique_news_id",
    "pipeline_run_id_unique", "source_sync_state_unique",
]

EXPECTED_INDEXES = [
    "idx_user_country", "idx_user_gender", "idx_user_subscription", "idx_user_suspended",
    "idx_match_kickoff_at", "idx_match_status",
    "idx_post_published_at", "idx_comment_created_at",
    "idx_topic_label", "idx_sentiment_label", "idx_persona_state_pcm_stage",
    "idx_chatbot_conversation_start",
    "idx_moderation_event_at",
    "idx_tag_name", "idx_tag_trending",
    "pipeline_run_started_at", "pipeline_run_source_name",
]

KEY_PROPERTIES = {
    "User":                 ["id", "country"],
    "Match":                ["id", "kickoff_at", "status"],
    "Team":                 ["id"],
    "League":               ["id"],
    "Post":                 ["id", "published_at"],
    "Comment":              ["id"],
    "PersonaState":         ["id", "pcm_stage"],
    "Topic":                ["id", "topic_label"],
    "Sentiment":            ["id", "sentiment_label"],
    "ChatbotConversation":  ["id", "conversation_start"],
    "CoinTransaction":      ["id"],
    "ModerationEvent":      ["id", "event_at"],
}


# ── section 1: schema health ──────────────────────────────────────────────────

def audit_schema(session) -> dict:
    header("1 · Schema Health")
    results = {}

    # Schema version
    row = scalar(session, "MATCH (v:GraphSchemaVersion) RETURN v.version AS ver LIMIT 1")
    if row:
        ok(f"GraphSchemaVersion: {row}")
        results["schema_version"] = row
    else:
        warn("No GraphSchemaVersion node found")
        results["schema_version"] = None

    # Constraints
    existing = {r["name"] for r in run(session, "SHOW CONSTRAINTS YIELD name")}
    missing_c = [c for c in EXPECTED_CONSTRAINTS if c not in existing]
    results["constraints"] = {
        "expected": len(EXPECTED_CONSTRAINTS),
        "found": len(existing),
        "missing": missing_c,
    }
    if missing_c:
        fail(f"Constraints: {len(existing)}/{len(EXPECTED_CONSTRAINTS)} found — missing: {missing_c}")
    else:
        ok(f"Constraints: all {len(EXPECTED_CONSTRAINTS)} present")

    # Indexes
    existing_idx = {r["name"] for r in run(session, "SHOW INDEXES YIELD name")}
    missing_i = [i for i in EXPECTED_INDEXES if i not in existing_idx]
    results["indexes"] = {
        "expected": len(EXPECTED_INDEXES),
        "found": len(existing_idx),
        "missing": missing_i,
    }
    if missing_i:
        warn(f"Indexes: {len(existing_idx) - len(EXPECTED_CONSTRAINTS)}/{len(EXPECTED_INDEXES)} lookup indexes — missing: {missing_i}")
    else:
        ok(f"Indexes: all {len(EXPECTED_INDEXES)} present")

    return results


# ── section 2: node census ────────────────────────────────────────────────────

def audit_nodes(session) -> dict:
    header("2 · Node Census")
    rows = run(session, """
        CALL apoc.meta.stats() YIELD labels
        RETURN labels
    """)
    if rows:
        counts = rows[0]["labels"]
    else:
        # fallback without APOC
        counts = {}
        for label in EXPECTED_LABELS:
            n = scalar(session, f"MATCH (n:{label}) RETURN count(n) AS c")
            counts[label] = n or 0

    results = {}
    total = 0
    empty = []
    for label in sorted(EXPECTED_LABELS):
        c = counts.get(label, 0)
        total += c
        results[label] = c
        if c == 0:
            empty.append(label)
            warn(f"  {label:<30}  {c:>10,}  ← empty")
        else:
            info(f"  {label:<30}  {c:>10,}")

    # Extra labels not in declared set
    extra = [l for l in counts if l not in EXPECTED_LABELS and not l.startswith("_")]
    if extra:
        warn(f"Undeclared labels in graph: {extra}")
        results["_undeclared"] = extra

    info(f"  {'TOTAL':<30}  {total:>10,}")
    results["_total"] = total
    results["_empty_labels"] = empty

    return results


# ── section 3: relationship census ───────────────────────────────────────────

def audit_relationships(session) -> dict:
    header("3 · Relationship Census")
    rows = run(session, """
        CALL apoc.meta.stats() YIELD relTypesCount
        RETURN relTypesCount
    """)
    if rows:
        raw = rows[0]["relTypesCount"]
        # apoc returns {()-[TYPE]->(): count} keys
        counts = {}
        for key, val in raw.items():
            rel_type = key.split("[")[1].split("]")[0] if "[" in key else key
            counts[rel_type] = counts.get(rel_type, 0) + val
    else:
        counts = {}
        for rel in EXPECTED_REL_TYPES:
            n = scalar(session, f"MATCH ()-[r:{rel}]->() RETURN count(r) AS c")
            counts[rel] = n or 0

    results = {}
    total = 0
    empty = []
    for rel in sorted(EXPECTED_REL_TYPES):
        c = counts.get(rel, 0)
        total += c
        results[rel] = c
        if c == 0:
            empty.append(rel)
            warn(f"  {rel:<35}  {c:>10,}  ← empty")
        else:
            info(f"  {rel:<35}  {c:>10,}")

    extra = [r for r in counts if r not in EXPECTED_REL_TYPES]
    if extra:
        warn(f"Undeclared relationship types: {extra}")
        results["_undeclared"] = extra

    info(f"  {'TOTAL':<35}  {total:>10,}")
    results["_total"] = total
    results["_empty_types"] = empty
    return results


# ── section 4: property health ────────────────────────────────────────────────

def audit_properties(session) -> dict:
    header("4 · Property Health  (null-rate on key properties, sample 1000)")
    results = {}
    for label, props in KEY_PROPERTIES.items():
        results[label] = {}
        for prop in props:
            cypher = f"""
                MATCH (n:{label})
                WITH n LIMIT 1000
                RETURN
                  count(n) AS total,
                  sum(CASE WHEN n.{prop} IS NULL THEN 1 ELSE 0 END) AS nulls
            """
            row = run(session, cypher)
            if not row:
                continue
            total = row[0]["total"] or 0
            nulls = row[0]["nulls"] or 0
            pct = (nulls / total * 100) if total else 0
            results[label][prop] = {"sample": total, "nulls": nulls, "null_pct": round(pct, 2)}
            tag = f"{label}.{prop}"
            if pct > 10:
                fail(f"  {tag:<40}  {pct:5.1f}% null  ({nulls}/{total})")
            elif pct > 0:
                warn(f"  {tag:<40}  {pct:5.1f}% null  ({nulls}/{total})")
            else:
                ok(f"  {tag:<40}  0% null  (sample {total:,})")
    return results


# ── section 5: connectivity ───────────────────────────────────────────────────

def audit_connectivity(session) -> dict:
    header("5 · Connectivity")
    results = {}

    # Orphaned nodes per label (no relationships at all)
    print(f"\n  {DIM}Orphaned nodes (no relationships):{RESET}")
    orphan_results = {}
    for label in ["User", "Match", "Team", "Post", "Comment", "Topic"]:
        n = scalar(session, f"MATCH (n:{label}) WHERE COUNT {{ (n)--() }} = 0 RETURN count(n) AS c")
        orphan_results[label] = n or 0
        if n:
            warn(f"    {label:<20} {n:,} orphaned")
        else:
            ok(f"    {label:<20} 0 orphaned")
    results["orphaned"] = orphan_results

    # Degree distribution for User nodes
    print(f"\n  {DIM}User degree distribution (sample 10,000):{RESET}")
    deg_rows = run(session, """
        MATCH (u:User)
        WITH u LIMIT 10000
        WITH u, COUNT { (u)--() } AS degree
        RETURN
          min(degree)  AS min_degree,
          max(degree)  AS max_degree,
          avg(degree)  AS avg_degree,
          percentileCont(degree, 0.50) AS p50,
          percentileCont(degree, 0.90) AS p90,
          percentileCont(degree, 0.99) AS p99
    """)
    if deg_rows and deg_rows[0].get("min_degree") is not None:
        d = deg_rows[0]
        info(f"    min={d['min_degree']}  avg={d['avg_degree']:.1f}  p50={d['p50']:.0f}  p90={d['p90']:.0f}  p99={d['p99']:.0f}  max={d['max_degree']}")
        results["user_degree"] = {k: round(v, 2) if isinstance(v, float) else v for k, v in d.items()}
    else:
        info("    no User nodes in graph")

    # Top 10 users by degree
    print(f"\n  {DIM}Top 10 Users by total degree:{RESET}")
    top_users = run(session, """
        MATCH (u:User)
        WITH u, COUNT { (u)--() } AS degree
        ORDER BY degree DESC LIMIT 10
        RETURN u.id AS user_id, degree
    """)
    results["top_users_by_degree"] = top_users
    for r in top_users:
        info(f"    user_id={r['user_id']}  degree={r['degree']:,}")

    # Top 10 matches by prediction count
    print(f"\n  {DIM}Top 10 Matches by PREDICTED edges:{RESET}")
    top_matches = run(session, """
        MATCH (m:Match)<-[:PREDICTED]-()
        WITH m, count(*) AS preds
        ORDER BY preds DESC LIMIT 10
        RETURN m.id AS match_id, preds
    """)
    results["top_matches_by_predictions"] = top_matches
    for r in top_matches:
        info(f"    match_id={r['match_id']}  predictions={r['preds']:,}")

    return results


# ── section 6: source sync state ─────────────────────────────────────────────

def audit_sync_state(session) -> dict:
    header("6 · Source Sync State")
    rows = run(session, """
        MATCH (s:SourceSyncState)
        RETURN s.source_name AS source, s.status AS status,
               s.last_synced_at AS synced_at, s.last_row_count AS rows
        ORDER BY source
    """)
    results = {}
    never = []
    synced = []
    for r in rows:
        results[r["source"]] = r
        if r["status"] == "never_synced" or r["synced_at"] is None:
            never.append(r["source"])
            warn(f"  {r['source']:<40}  never synced")
        else:
            synced.append(r["source"])
            ok(f"  {r['source']:<40}  synced  rows={r['rows']}  at={str(r['synced_at'])[:19]}")

    results["_summary"] = {"synced": len(synced), "never_synced": len(never)}
    info(f"\n  Synced: {len(synced)}   Never synced: {len(never)}")
    return results


# ── section 7: pipeline run history (metadata DB) ────────────────────────────

def audit_pipeline_runs(conn) -> dict:
    header("7 · Pipeline Run History  (last 20 runs)")
    if conn is None:
        warn("Metadata DB not available — skipping")
        return {}

    rows = conn.execute("""
        SELECT run_id, pipeline_name, status, started_at, finished_at, duration_ms, error_message
        FROM job_runs
        ORDER BY created_at DESC LIMIT 20
    """).fetchall()
    cols = ["run_id", "pipeline_name", "status", "started_at", "finished_at", "duration_ms", "error_message"]
    records = [dict(zip(cols, r)) for r in rows]

    by_status: dict[str, int] = {}
    for r in records:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
        dur = f"{r['duration_ms']/1000:.1f}s" if r["duration_ms"] else "—"
        line = f"  {r['pipeline_name'] or '—':<35} {r['status']:<12} {dur:<8}"
        if r["status"] == "succeeded":
            ok(line)
        elif r["status"] == "running":
            warn(line)
        else:
            fail(line + f"  ← {r['error_message'] or ''}")

    info(f"\n  Status breakdown: {by_status}")
    return {"recent_runs": records, "by_status": by_status}


# ── section 8: data quality (metadata DB) ────────────────────────────────────

def audit_data_quality(conn) -> dict:
    header("8 · Data Quality Results  (last run)")
    if conn is None:
        warn("Metadata DB not available — skipping")
        return {}

    rows = conn.execute("""
        SELECT source_name, check_name, passed, severity, message
        FROM data_quality_results
        WHERE run_id = (SELECT run_id FROM job_runs ORDER BY created_at DESC LIMIT 1)
        ORDER BY severity, source_name
    """).fetchall()
    cols = ["source_name", "check_name", "passed", "severity", "message"]
    records = [dict(zip(cols, r)) for r in rows]

    by_sev: dict[str, int] = {}
    for r in records:
        by_sev[r["severity"]] = by_sev.get(r["severity"], 0) + 1
        if r["passed"]:
            continue  # only print failures
        line = f"  [{r['severity']}] {r['source_name']}: {r['check_name']} — {r['message']}"
        if r["severity"] == "critical":
            fail(line)
        elif r["severity"] == "error":
            fail(line)
        else:
            warn(line)

    total = len(records)
    failed = sum(1 for r in records if not r["passed"])
    if total == 0:
        info("No data quality results found for latest run")
    else:
        info(f"  {total} checks  |  {total - failed} passed  |  {failed} failed  |  {by_sev}")

    return {"total": total, "failed": failed, "by_severity": by_sev}


# ── section 9: graph metadata ─────────────────────────────────────────────────

def audit_graph_metadata(session) -> dict:
    header("9 · Graph Metadata")
    results = {}

    # GDS projection configs
    print(f"\n  {DIM}GDS Projection Configs:{RESET}")
    proj_rows = run(session, """
        MATCH (p:GDSProjectionConfig)
        RETURN p.name AS name, p.node_labels AS node_labels,
               p.relationship_types AS rel_types, p.orientation AS orientation
    """)
    results["gds_projections"] = proj_rows
    for r in proj_rows:
        info(f"    {r['name']:<25}  nodes={r['node_labels']}  rels={r['rel_types']}")

    # Serving view configs
    print(f"\n  {DIM}Serving View Configs:{RESET}")
    sv_rows = run(session, """
        MATCH (s:ServingViewConfig)
        RETURN s.view_name AS name, s.freshness_max_hours AS freshness_h
    """)
    results["serving_views"] = sv_rows
    for r in sv_rows:
        info(f"    {r['name']:<30}  freshness_max={r['freshness_h']}h")

    # Graph schema meta
    meta_rows = run(session, """
        MATCH (m:GraphSchemaMeta)
        RETURN m.schema_type AS type, m.label_count AS label_count,
               m.type_count AS type_count, m.schema_version AS version
    """)
    results["schema_meta"] = meta_rows
    for r in meta_rows:
        info(f"    GraphSchemaMeta type={r['type']}  labels={r.get('label_count')}  types={r.get('type_count')}  v={r.get('version')}")

    return results


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Audit and analyse the Project Pulse graph")
    parser.add_argument("--json", metavar="PATH", help="Write full JSON report to file")
    args = parser.parse_args()

    neo4j_uri      = os.environ.get("NEO4J_URI", "")
    neo4j_user     = os.environ.get("NEO4J_USER", "")
    neo4j_password = os.environ.get("NEO4J_PASSWORD", "")

    if not all([neo4j_uri, neo4j_user, neo4j_password]):
        sys.exit("Missing NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD in .env")

    meta_host = os.environ.get("METADATA_DB_HOST", "")
    meta_user = os.environ.get("METADATA_DB_USER", "")
    meta_pass = os.environ.get("METADATA_DB_PASSWORD", "")
    meta_db   = os.environ.get("METADATA_DB_NAME", "")
    meta_port = int(os.environ.get("METADATA_DB_PORT", "5432"))

    print(f"\n{BOLD}Project Pulse Knowledge Graph — Full Audit{RESET}")
    print(f"{DIM}  Neo4j : {neo4j_uri}{RESET}")
    print(f"{DIM}  Time  : {NOW}{RESET}")

    # Neo4j connection
    driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))
    try:
        driver.verify_connectivity()
    except Exception as exc:
        sys.exit(f"Cannot connect to Neo4j: {exc}")

    # Metadata DB connection
    meta_conn = None
    if psycopg and meta_host:
        try:
            meta_conn = psycopg.connect(
                host=meta_host, port=meta_port,
                user=meta_user, password=meta_pass,
                dbname=meta_db, autocommit=True,
            )
        except Exception as exc:
            warn(f"Metadata DB unavailable ({exc}) — sections 7/8 skipped")

    report = {"generated_at": NOW, "neo4j_uri": neo4j_uri}

    with driver.session(database="neo4j") as session:
        report["schema"]       = audit_schema(session)
        report["nodes"]        = audit_nodes(session)
        report["relationships"]= audit_relationships(session)
        report["properties"]   = audit_properties(session)
        report["connectivity"] = audit_connectivity(session)
        report["sync_state"]   = audit_sync_state(session)
        report["graph_meta"]   = audit_graph_metadata(session)

    report["pipeline_runs"]  = audit_pipeline_runs(meta_conn)
    report["data_quality"]   = audit_data_quality(meta_conn)

    if meta_conn:
        meta_conn.close()
    driver.close()

    # Summary
    header("Summary")
    node_total = report["nodes"].get("_total", 0)
    rel_total  = report["relationships"].get("_total", 0)
    empty_labels = report["nodes"].get("_empty_labels", [])
    empty_rels   = report["relationships"].get("_empty_types", [])
    missing_c    = report["schema"].get("constraints", {}).get("missing", [])

    info(f"Total nodes        : {node_total:,}")
    info(f"Total relationships: {rel_total:,}")
    if missing_c:
        fail(f"Missing constraints: {missing_c}")
    else:
        ok("All constraints present")
    if empty_labels:
        warn(f"Empty labels       : {empty_labels}")
    if empty_rels:
        warn(f"Empty rel types    : {empty_rels}")

    print()

    if args.json:
        out = Path(args.json)
        out.write_text(json.dumps(report, indent=2, default=str))
        print(f"Report written to {out}\n")


if __name__ == "__main__":
    main()
