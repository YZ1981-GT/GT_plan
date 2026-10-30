#!/usr/bin/env python
"""Build large ledger indexes concurrently; dry-run unless ``--apply``.

Runtime migrations cannot execute ``CREATE INDEX CONCURRENTLY`` because each
migration is transactional.  This pre-deploy tool builds and validates the
large index first; the paired migration only verifies it on populated systems.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


@dataclass(frozen=True)
class IndexSpec:
    name: str
    table: str
    definition: str
    purpose: str


INDEXES = {
    "aux-account-prefix": IndexSpec(
        name="idx_tb_aux_ledger_active_account_prefix",
        table="tb_aux_ledger",
        definition=(
            "CREATE INDEX CONCURRENTLY idx_tb_aux_ledger_active_account_prefix "
            "ON public.tb_aux_ledger "
            "(project_id, year, dataset_id, account_code text_pattern_ops) "
            "WHERE is_deleted = false"
        ),
        purpose="active dataset auxiliary-ledger account prefix COUNT/filter",
    ),
    "ledger-window": IndexSpec(
        name="idx_tb_ledger_active_window",
        table="tb_ledger",
        definition=(
            "CREATE INDEX CONCURRENTLY idx_tb_ledger_active_window "
            "ON public.tb_ledger "
            "(project_id, year, dataset_id, account_code, "
            "voucher_date ASC NULLS LAST, voucher_no ASC NULLS LAST, id ASC) "
            "WHERE is_deleted = false"
        ),
        purpose="ordinary Ledger exact-account window order",
    ),
    "aux-window": IndexSpec(
        name="idx_tb_aux_ledger_active_window",
        table="tb_aux_ledger",
        definition=(
            "CREATE INDEX CONCURRENTLY idx_tb_aux_ledger_active_window "
            "ON public.tb_aux_ledger "
            "(project_id, year, dataset_id, account_code, aux_type, aux_code, "
            "voucher_date ASC NULLS LAST, voucher_no ASC NULLS LAST, id ASC) "
            "WHERE is_deleted = false"
        ),
        purpose="auxiliary Ledger exact-triplet window order",
    ),
}


async def _status(conn, spec: IndexSpec) -> dict:
    row = (
        await conn.execute(
            sa.text(
                "SELECT c.relname, i.indisvalid, i.indisready, "
                "pg_relation_size(c.oid) AS size_bytes "
                "FROM pg_class c JOIN pg_index i ON i.indexrelid=c.oid "
                "JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE n.nspname='public' AND c.relname=:name"
            ),
            {"name": spec.name},
        )
    ).mappings().one_or_none()
    return dict(row) if row else {"relname": spec.name, "missing": True}


async def run(selected: list[IndexSpec], *, apply: bool, drop: bool) -> int:
    from app.core.config import settings

    engine = create_async_engine(
        settings.DATABASE_URL,
        isolation_level="AUTOCOMMIT",
        poolclass=NullPool,
    )
    try:
        async with engine.connect() as conn:
            await conn.exec_driver_sql("SET lock_timeout = '5s'")
            await conn.exec_driver_sql("SET statement_timeout = '30min'")
            for spec in selected:
                before = await _status(conn, spec)
                print({"index": spec.name, "purpose": spec.purpose, "before": before})
                if not apply:
                    print({"dry_run": True, "sql": f"DROP/CREATE CONCURRENTLY {spec.name}" if drop else spec.definition})
                    continue
                if drop:
                    await conn.exec_driver_sql(f"DROP INDEX CONCURRENTLY IF EXISTS public.{spec.name}")
                    print({"index": spec.name, "dropped": True})
                    continue
                if not before.get("missing") and (not before.get("indisvalid") or not before.get("indisready")):
                    await conn.exec_driver_sql(f"DROP INDEX CONCURRENTLY IF EXISTS public.{spec.name}")
                    before = {"missing": True}
                if before.get("missing"):
                    await conn.exec_driver_sql(spec.definition)
                after = await _status(conn, spec)
                print({"index": spec.name, "after": after})
                if not after.get("indisvalid") or not after.get("indisready"):
                    raise RuntimeError(f"index not valid/ready: {spec.name}")
        return 0
    finally:
        await engine.dispose()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--index", action="append", choices=sorted(INDEXES),
        help="index key; repeatable, default all",
    )
    parser.add_argument("--apply", action="store_true", help="execute concurrent DDL")
    parser.add_argument("--drop", action="store_true", help="drop selected indexes concurrently")
    parser.add_argument(
        "--confirm", default="",
        help="required with --apply: BUILD_LEDGER_INDEXES or DROP_LEDGER_INDEXES",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.drop and not args.apply:
        raise SystemExit("--drop requires --apply")
    if args.apply:
        expected = "DROP_LEDGER_INDEXES" if args.drop else "BUILD_LEDGER_INDEXES"
        if args.confirm != expected:
            raise SystemExit(f"--apply requires --confirm {expected}")
    keys = args.index or list(INDEXES)
    return asyncio.run(run([INDEXES[key] for key in keys], apply=args.apply, drop=args.drop))


if __name__ == "__main__":
    raise SystemExit(main())
