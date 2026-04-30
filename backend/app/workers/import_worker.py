"""Standalone durable import worker.

Run with:

    python -m app.workers.import_worker
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from app.core.config import settings
from app.core.database import dispose_engine
from app.core.logging_config import setup_logging
from app.services.event_handlers import register_event_handlers
from app.services.gate_rules_phase14 import register_phase14_rules
from app.services.import_job_runner import ImportJobRunner
from app.services.task_event_handlers import register_event_handlers as register_task_handlers


logger = logging.getLogger("import_worker")


async def run_worker(*, poll_interval_seconds: int | None = None, batch_size: int | None = None) -> None:
    setup_logging(level="INFO", json_format=False)
    register_event_handlers()
    register_phase14_rules()
    register_task_handlers()
    try:
        await ImportJobRunner.run_forever(
            poll_interval_seconds=poll_interval_seconds,
            batch_size=batch_size,
        )
    finally:
        await dispose_engine()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the ledger import durable worker")
    parser.add_argument(
        "--poll-interval",
        type=int,
        default=settings.LEDGER_IMPORT_WORKER_POLL_INTERVAL_SECONDS,
        help="Seconds between worker polling cycles",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=settings.LEDGER_IMPORT_WORKER_BATCH_SIZE,
        help="Maximum queued jobs to claim per polling cycle",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    try:
        asyncio.run(
            run_worker(
                poll_interval_seconds=args.poll_interval,
                batch_size=args.batch_size,
            )
        )
    except KeyboardInterrupt:
        logger.info("Import worker interrupted")


if __name__ == "__main__":
    main()
