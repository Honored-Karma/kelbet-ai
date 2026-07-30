"""Audit a staging video batch and emit a machine-readable financial report."""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from kelbet.config import get_settings
from kelbet.db.session import build_session_factory
from kelbet.operations import reconcile_video_jobs


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hours", type=int, default=24)
    parser.add_argument("--minimum-jobs", type=int, default=100)
    parser.add_argument("--limit", type=int, default=1_000)
    parser.add_argument("--maximum-active-age-minutes", type=int, default=35)
    parser.add_argument(
        "--allow-active",
        action="store_true",
        help="Allow young non-terminal jobs instead of requiring a fully terminal batch",
    )
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


async def _run(args: argparse.Namespace) -> int:
    now = datetime.now(UTC)
    since = now - timedelta(hours=args.hours)
    factory = build_session_factory(get_settings())
    async with factory() as session:
        report = await reconcile_video_jobs(
            session,
            since=since,
            minimum_jobs=args.minimum_jobs,
            limit=args.limit,
            maximum_active_age=timedelta(minutes=args.maximum_active_age_minutes),
            require_all_terminal=not args.allow_active,
            now=now,
        )
    serialized = json.dumps(report.as_dict(), ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
    print(serialized, end="")
    return 0 if report.passed else 1


def main() -> None:
    raise SystemExit(asyncio.run(_run(_arguments())))


if __name__ == "__main__":
    main()
