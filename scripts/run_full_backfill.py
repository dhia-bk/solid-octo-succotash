"""
Full backfill — clears all checkpoints and runs every pipeline wave from scratch.

Usage:
    python scripts/run_full_backfill.py [--dry-run] [--workers N]

Options:
    --dry-run    Extract and transform but skip all Neo4j writes.
    --workers N  Parallel workers per wave (default: 1).
"""

from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from app.pipelines import FullBackfillPipeline, build_pipeline_context


def main() -> None:
    parser = argparse.ArgumentParser(description="Run full backfill pipeline")
    parser.add_argument("--dry-run", action="store_true", help="Skip Neo4j writes")
    parser.add_argument("--workers", type=int, default=1, help="Parallel workers per wave")
    args = parser.parse_args()

    run_id = str(uuid.uuid4())
    print(f"Starting full backfill  run_id={run_id}  dry_run={args.dry_run}  workers={args.workers}\n")

    ctx = build_pipeline_context(run_id=run_id, dry_run=args.dry_run)
    pipeline = FullBackfillPipeline(ctx, max_parallel_workers=args.workers)
    results = pipeline.run()

    print("\n─── Results ───────────────────────────────")
    failed = []
    for name, r in results.items():
        status_icon = "✓" if r.status in ("completed", "dry_run") else "✗"
        print(f"  {status_icon} {name:<40} {r.status}")
        if r.status == "failed":
            failed.append(name)

    print()
    if failed:
        print(f"FAILED pipelines: {', '.join(failed)}")
        sys.exit(1)
    else:
        print("All pipelines completed successfully.")


if __name__ == "__main__":
    main()
