"""
Warehouse audit script for Project Pulse.

For every registered warehouse source it checks:
  - table exists
  - row count
  - most-recent and oldest freshness timestamp
  - null rate on primary key column(s)
  - duplicate primary key count

Groups results by inclusion mode:
  graph_core | graph_enrichment | serving_only | feature_source | excluded

Usage:
    .venv/bin/python3 scripts/audit_warehouse.py [--json path/to/report.json] [--table TABLE]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

try:
    import pymysql
    import pymysql.cursors
except ImportError:
    sys.exit("pymysql not found. Run: .venv/bin/pip install -e .")

# ── colour helpers ─────────────────────────────────────────────────────────────

RESET  = "\033[0m"
BOLD   = "\033[1m"
GREEN  = "\033[32m"
YELLOW = "\033[33m"
RED    = "\033[31m"
CYAN   = "\033[36m"
DIM    = "\033[2m"

def ok(msg):     print(f"  {GREEN}✓{RESET} {msg}")
def warn(msg):   print(f"  {YELLOW}⚠{RESET} {msg}")
def fail(msg):   print(f"  {RED}✗{RESET} {msg}")
def info(msg):   print(f"  {CYAN}·{RESET} {msg}")
def header(msg): print(f"\n{BOLD}{'─' * 64}{RESET}\n{BOLD}{msg}{RESET}\n")


# ── full source catalogue (from app/schemas/warehouse/) ───────────────────────

SOURCES = [
    # source_name                        inclusion_mode       pk_cols                              freshness_col
    ("dim_users",                        "graph_core",        ("user_id",),                        "last_activity_at_utc"),
    ("dim_avatars",                      "graph_core",        ("avatar_id",),                      None),
    ("dim_badges",                       "graph_core",        ("badge_id",),                       None),
    ("dim_teams",                        "graph_core",        ("team_id",),                        None),
    ("dim_teams_enhanced",               "graph_enrichment",  ("team_id",),                        "last_fan_joined_at"),
    ("dim_leagues",                      "graph_core",        ("league_id",),                      "updated_at"),
    ("dim_fixtures",                     "graph_core",        ("fixture_id",),                     "kickoff_at_utc"),
    ("dim_private_leagues",              "graph_core",        ("private_league_id",),              None),
    ("dim_private_league_themes",        "graph_enrichment",  ("theme_id",),                       None),
    ("dim_private_league_members",       "graph_core",        ("membership_id",),                  "joined_at"),
    ("dim_influencer_leagues",           "graph_core",        ("influencer_league_id",),           "updated_at"),
    ("dim_posts",                        "graph_core",        ("post_id",),                        "published_at_utc"),
    ("dim_comments",                     "graph_core",        ("comment_id",),                     "created_at_utc"),
    ("dim_discussions",                  "graph_core",        ("discussion_id",),                  "created_at_utc"),
    ("dim_prediction_discussions",       "graph_core",        ("prediction_discussion_id",),       "created_at_utc"),
    ("dim_chat_conversations_mysql",     "graph_core",        ("conversation_id",),                "last_message_at"),
    ("dim_chat_direct_pairs",            "graph_core",        ("direct_pair_key",),                "last_message_at"),
    ("dim_chatbot_conversations",        "graph_core",        ("conversation_id",),                "conversation_start_utc"),
    ("dim_tags",                         "graph_core",        ("tag_id",),                         "last_used_at_utc"),
    ("dim_notification_content",         "graph_core",        ("content_id",),                     "last_seen_at_utc"),
    ("dim_notification_preferences",     "graph_enrichment",  ("user_id",),                        "preference_updated_at_utc"),
    ("dim_ai_articles",                  "graph_core",        ("article_id",),                     "updated_at_utc"),
    ("dim_news",                         "graph_core",        ("news_id",),                        "published_at_utc"),
    ("dim_partner_reward_catalog",       "graph_core",        ("reward_key",),                     "created_at"),
    ("dim_subscription_products",        "graph_core",        ("subscription_type_id",),           None),
    ("dim_voucher_catalog",              "graph_core",        ("voucher_key",),                    "created_at"),
    ("dim_lms_competitions",             "graph_core",        ("lms_competition_id",),             "created_at"),
    ("dim_fixture_polls_enhanced",       "graph_core",        ("fixture_poll_id",),                "created_at_utc"),
    ("dim_questions",                    "graph_core",        ("question_id",),                    "created_at_utc"),
    ("dim_questions_enhanced",           "graph_enrichment",  ("question_id",),                    "last_response_at_utc"),
    ("dim_quizzes",                      "graph_core",        ("quiz_id",),                        "created_at_utc"),
    ("dim_quiz_questions_enhanced",      "graph_core",        ("quiz_question_id",),               "last_answer_at_utc"),
    ("dim_super6_rounds",                "graph_core",        ("super6_round_id",),                "start_date_utc"),
    ("dim_super6_round_fixtures",        "graph_core",        ("super6_round_fixture_id",),        None),
    ("fct_predictions",                  "graph_core",        ("unified_prediction_id",),          "predicted_at_utc"),
    ("fct_user_behavior",                "graph_enrichment",  ("id",),                             "last_calculated_at"),
    ("fct_topics",                       "graph_core",        ("id",),                             "processed_at"),
    ("fct_sentiment",                    "graph_core",        ("source_type", "item_id", "user_id"), "processed_at"),
    ("fct_team_affinity",                "graph_core",        ("affinity_id",),                    "calculated_at_utc"),
    ("fct_user_rating_history",          "graph_core",        ("rating_event_id",),                "created_at_utc"),
    ("fct_chatbot_messages",             "graph_core",        ("message_id",),                     "message_at_utc"),
    ("fct_chatbot_tool_calls",           "graph_core",        ("tool_call_id",),                   "tool_call_at_utc"),
    ("fct_coin_transactions",            "graph_core",        ("event_id",),                       "event_at_utc"),
    ("fct_partner_reward_inventory",     "graph_enrichment",  ("inventory_event_id",),             "created_at_utc"),
    ("fct_partner_reward_redemptions",   "graph_core",        ("redemption_id",),                  "redeemed_at_utc"),
    ("fct_voucher_purchases",            "graph_core",        ("purchase_id",),                    "purchase_date_utc"),
    ("fct_financials",                   "graph_core",        ("event_id",),                       "event_at_utc"),
    ("fct_subscription_lifecycle",       "graph_core",        ("lifecycle_event_id",),             "event_timestamp_utc"),
    ("fct_awards_and_achievements",      "graph_core",        ("award_id",),                       "earned_at_utc"),
    ("fct_prediction_duels",             "graph_core",        ("duel_id",),                        "created_at_utc"),
    ("fct_super6_participants",          "graph_core",        ("super6_participant_id",),           "joined_at_utc"),
    ("fct_moderation_events",            "graph_core",        ("event_id",),                       "event_at_utc"),
    ("fct_discussion_events",            "graph_core",        ("event_id",),                       "event_at_utc"),
    ("fct_user_activities",              "graph_enrichment",  ("activity_id",),                    "activity_at_utc"),
    ("jct_notification_recipients",      "graph_core",        ("notification_id", "user_id"),      "sent_at_utc"),
    ("app_users",                        "graph_enrichment",  ("id",),                             "updated_at"),
    ("fct_daily_metrics",                "serving_only",      ("metric_date",),                    "metric_date"),
    ("fct_content_engagement_daily",     "serving_only",      ("engagement_id",),                  "metric_date"),
    ("fct_retention_cohorts",            "serving_only",      ("cohort_date_key", "period_weeks_since_cohort"), "cohort_date"),
    ("fct_heatmap_events",               "feature_source",    ("heatmap_event_id",),               "event_timestamp_utc"),
    ("fct_user_notification_stats",      "feature_source",    ("user_id",),                        "last_notification_at_utc"),
    ("fct_user_sessions",                "feature_source",    ("session_id",),                     "session_start_utc"),
    ("fct_team_daily_growth",            "feature_source",    ("metric_date", "team_id"),          "metric_date"),
]

INCLUSION_ORDER = ["graph_core", "graph_enrichment", "serving_only", "feature_source", "excluded"]


# ── per-table checks ──────────────────────────────────────────────────────────

def table_exists(cur, db: str, table: str) -> bool:
    cur.execute(
        "SELECT COUNT(*) FROM information_schema.tables "
        "WHERE table_schema = %s AND table_name = %s",
        (db, table),
    )
    return cur.fetchone()[0] > 0


def audit_table(cur, db: str, source: str, pk_cols: tuple, freshness_col: str | None) -> dict:
    result: dict = {
        "source": source,
        "exists": False,
        "row_count": None,
        "freshness_max": None,
        "freshness_min": None,
        "pk_nulls": None,
        "pk_dupes": None,
    }

    if not table_exists(cur, db, source):
        return result

    result["exists"] = True

    # row count
    cur.execute(f"SELECT COUNT(*) FROM `{source}`")
    result["row_count"] = cur.fetchone()[0]

    if result["row_count"] == 0:
        return result

    # freshness range
    if freshness_col:
        cur.execute(
            f"SELECT MAX(`{freshness_col}`), MIN(`{freshness_col}`) FROM `{source}`"
        )
        row = cur.fetchone()
        result["freshness_max"] = str(row[0]) if row[0] else None
        result["freshness_min"] = str(row[1]) if row[1] else None

    # PK null check (first PK col only for composite keys)
    pk = pk_cols[0]
    cur.execute(
        f"SELECT SUM(CASE WHEN `{pk}` IS NULL THEN 1 ELSE 0 END) FROM `{source}`"
    )
    result["pk_nulls"] = int(cur.fetchone()[0] or 0)

    # PK duplicate check
    if len(pk_cols) == 1:
        cur.execute(
            f"SELECT COUNT(*) FROM ("
            f"  SELECT `{pk}`, COUNT(*) AS c FROM `{source}` GROUP BY `{pk}` HAVING c > 1"
            f") t"
        )
        result["pk_dupes"] = int(cur.fetchone()[0] or 0)
    else:
        pk_expr = ", ".join(f"`{c}`" for c in pk_cols)
        cur.execute(
            f"SELECT COUNT(*) FROM ("
            f"  SELECT {pk_expr}, COUNT(*) AS c FROM `{source}` GROUP BY {pk_expr} HAVING c > 1"
            f") t"
        )
        result["pk_dupes"] = int(cur.fetchone()[0] or 0)

    return result


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Audit MySQL warehouse tables")
    parser.add_argument("--json", metavar="PATH", help="Write full JSON report to file")
    parser.add_argument("--table", metavar="TABLE", help="Audit a single table only")
    args = parser.parse_args()

    host     = os.environ.get("MYSQL_HOST", "")
    user     = os.environ.get("MYSQL_USER", "")
    password = os.environ.get("MYSQL_PASSWORD", "")
    db       = os.environ.get("MYSQL_DB", "")
    port     = int(os.environ.get("MYSQL_PORT", "3306"))

    missing = [k for k, v in [("MYSQL_HOST", host), ("MYSQL_USER", user),
                               ("MYSQL_PASSWORD", password), ("MYSQL_DB", db)] if not v]
    if missing:
        sys.exit(f"Missing env vars: {', '.join(missing)}")

    print(f"\n{BOLD}Project Pulse — Warehouse Audit{RESET}")
    print(f"{DIM}  Host : {host}:{port}  DB: {db}{RESET}")
    print(f"{DIM}  Time : {datetime.now(timezone.utc).isoformat()}{RESET}")

    try:
        conn = pymysql.connect(
            host=host, port=port, user=user, password=password,
            database=db, autocommit=True,
            cursorclass=pymysql.cursors.Cursor,
            connect_timeout=10,
        )
    except Exception as exc:
        sys.exit(f"Cannot connect to warehouse: {exc}")

    print(f"  {GREEN}Connected OK{RESET}")

    cur = conn.cursor()

    sources = SOURCES
    if args.table:
        sources = [s for s in SOURCES if s[0] == args.table]
        if not sources:
            sys.exit(f"Table '{args.table}' not found in catalogue.")

    # group by inclusion mode
    by_mode: dict[str, list] = {m: [] for m in INCLUSION_ORDER}
    for source, mode, pks, freshness in sources:
        by_mode.setdefault(mode, []).append((source, pks, freshness))

    report: dict = {"tables": {}, "summary": {}}

    totals = {"missing": 0, "empty": 0, "populated": 0, "pk_issues": 0}

    for mode in INCLUSION_ORDER:
        tables = by_mode.get(mode, [])
        if not tables:
            continue

        header(f"{mode.upper().replace('_', ' ')}  ({len(tables)} tables)")

        for source, pks, freshness in tables:
            r = audit_table(cur, db, source, pks, freshness)
            report["tables"][source] = r

            count   = r["row_count"]
            exists  = r["exists"]
            nulls   = r["pk_nulls"] or 0
            dupes   = r["pk_dupes"] or 0
            fresh   = r["freshness_max"]
            issues  = nulls > 0 or dupes > 0

            if not exists:
                totals["missing"] += 1
                fail(f"{source:<45} MISSING")
                continue

            if count == 0:
                totals["empty"] += 1
                warn(f"{source:<45} {count:>10,} rows  (empty)")
                continue

            totals["populated"] += 1
            if issues:
                totals["pk_issues"] += 1

            fresh_str = f"  latest={fresh[:10] if fresh else '?'}" if freshness else ""
            base = f"{source:<45} {count:>10,} rows{fresh_str}"

            if issues:
                warn(f"{base}  ⚠ pk_nulls={nulls} pk_dupes={dupes}")
            else:
                ok(base)

    cur.close()
    conn.close()

    # summary
    total_tables = len(sources)
    header("Summary")
    info(f"Tables audited   : {total_tables}")
    ok(f"Populated        : {totals['populated']}")
    if totals["empty"]:
        warn(f"Empty            : {totals['empty']}")
    if totals["missing"]:
        fail(f"Missing          : {totals['missing']}")
    if totals["pk_issues"]:
        warn(f"PK integrity issues: {totals['pk_issues']}")
    else:
        ok(f"PK integrity     : clean")
    print()

    report["summary"] = {**totals, "total": total_tables}

    if args.json:
        out = Path(args.json)
        out.write_text(json.dumps(report, indent=2, default=str))
        print(f"Report written to {out}\n")


if __name__ == "__main__":
    main()
