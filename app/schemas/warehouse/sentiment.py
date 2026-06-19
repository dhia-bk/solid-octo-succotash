"""
Warehouse schema for fct_sentiment.

Source table: fct_sentiment
Domain: intelligence
Inclusion mode: GRAPH_CORE — direct graph node creation
Graph entity: Sentiment
Freshness field: processed_at

ML-derived sentiment scores per content item and user. No declared PK in
the DWH. The composite key (source_type, item_id, user_id) is the stable
row identifier. Use stable_hash_key(source_type, item_id, user_id) from
app.core.ids to produce a synthetic node ID for graph merges.

Feeds Sentiment nodes and the EXPRESSED relationship (User → Sentiment).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.core.constants import GRAPH_CORE, SENTIMENT
from app.core.ids import normalize_nullable_string_id
from app.core.time import warehouse_value_to_utc_datetime

# ── Module-level constants ────────────────────────────────────────────────────

SOURCE_NAME: str = "fct_sentiment"
INCLUSION_MODE: str = GRAPH_CORE
PRIMARY_KEYS: tuple[str, ...] = ("source_type", "item_id", "user_id")
FRESHNESS_FIELD: str | None = "processed_at"
GRAPH_ENTITY_MAPPINGS: tuple[str, ...] = (SENTIMENT,)


# ── Row shape ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SentimentRow:
    """
    Typed row shape for fct_sentiment.

    No single-column PK declared in the DWH. All three composite key
    fields (source_type, item_id, user_id) are nullable at the column
    level; treat them as required together for a valid row.

    score_* fields are FLOAT in the DWH.
    """

    source_type: str | None
    item_id: str | None
    user_id: str | None
    created_at: datetime | None
    processed_at: datetime | None
    language_code: str | None
    sentiment_label: str | None
    score_positive: float | None
    score_negative: float | None
    score_neutral: float | None
    score_mixed: float | None
    model_provider: str | None
    model_version: str | None
    pipeline_run_id: str | None
    text_hash: str | None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> SentimentRow:
        """Normalize a raw warehouse row into a typed SentimentRow."""
        return cls(
            source_type=row.get("source_type"),
            item_id=normalize_nullable_string_id(row.get("item_id"), field_name="item_id"),
            user_id=normalize_nullable_string_id(row.get("user_id"), field_name="user_id"),
            created_at=warehouse_value_to_utc_datetime(row.get("created_at")),
            processed_at=warehouse_value_to_utc_datetime(row.get("processed_at")),
            language_code=row.get("language_code"),
            sentiment_label=row.get("sentiment_label"),
            score_positive=float(row["score_positive"]) if row.get("score_positive") is not None else None,
            score_negative=float(row["score_negative"]) if row.get("score_negative") is not None else None,
            score_neutral=float(row["score_neutral"]) if row.get("score_neutral") is not None else None,
            score_mixed=float(row["score_mixed"]) if row.get("score_mixed") is not None else None,
            model_provider=row.get("model_provider"),
            model_version=row.get("model_version"),
            pipeline_run_id=row.get("pipeline_run_id"),
            text_hash=row.get("text_hash"),
        )
