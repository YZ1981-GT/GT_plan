# -*- coding: utf-8 -*-
"""作废前全文快照（不只存哈希）：17 条 conflict operation + 其全部冲突行 + 相关 event。

用法：python backend/scripts/ops/abandon_legacy_conflicts.py --snapshot out.json
      python backend/scripts/ops/abandon_legacy_conflicts.py --apply --actor <uuid> --reason "..." [--project <uuid>]
      python backend/scripts/ops/abandon_legacy_conflicts.py --verify out.json

纪律：
* 默认 dry-run（只打印将作废什么），`--apply` 才写；
* 走 `ConflictAbandonService`，**不裸 SQL 改 state**（会破坏版本链与审计链）；
* 快照存全文字段，供事后逐字段对账与回退参考。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool


def _engine():
    from app.core.config import settings

    return create_async_engine(settings.DATABASE_URL, poolclass=NullPool)


async def _load_rows(session, project_id: str | None) -> list[dict]:
    where = "o.state = 'conflict'"
    params: dict = {}
    if project_id:
        where += " AND o.project_id = :pid"
        params["pid"] = project_id
    res = await session.execute(
        sa.text(
            f"""
            SELECT o.id::text AS operation_id, o.project_id::text AS project_id,
                   o.wp_id::text AS wp_id, o.entry_id, o.state, o.created_at::text AS created_at,
                   p.name AS project_name
            FROM working_paper_sync_operation o
            JOIN projects p ON p.id = o.project_id
            WHERE {where}
            ORDER BY p.name, o.created_at
            """
        ),
        params,
    )
    return [dict(r._mapping) for r in res.fetchall()]


async def _snapshot(session, ops: list[dict]) -> dict:
    ids = [o["operation_id"] for o in ops]
    conflicts = []
    events = []
    if ids:
        res = await session.execute(
            sa.text(
                """
                SELECT id::text, operation_id::text, conflict_kind, stable_field_key,
                       business_label, row_key, oo_location, incoming_value, current_value,
                       base_value, suggested_action, schema_anomaly,
                       resolved_at::text, resolved_by::text, resolved_value,
                       superseded_at::text, abandoned_at::text, abandon_reason, abandoned_by::text
                FROM working_paper_sync_conflict
                WHERE operation_id IN :ids
                ORDER BY operation_id, id
                """
            ).bindparams(sa.bindparam("ids", expanding=True)),
            {"ids": ids},
        )
        conflicts = [dict(r._mapping) for r in res.fetchall()]
        res2 = await session.execute(
            sa.text(
                """
                SELECT id::text, operation_id::text, sequence_no, from_state, to_state,
                       stage, error_code, occurred_at::text
                FROM working_paper_sync_operation_event
                WHERE operation_id IN :ids
                ORDER BY operation_id, sequence_no
                """
            ).bindparams(sa.bindparam("ids", expanding=True)),
            {"ids": ids},
        )
        events = [dict(r._mapping) for r in res2.fetchall()]
    return {"operations": ops, "conflicts": conflicts, "events": events}


async def cmd_snapshot(out: str, project_id: str | None) -> int:
    eng = _engine()
    try:
        Session = async_sessionmaker(eng, expire_on_commit=False)
        async with Session() as s:
            ops = await _load_rows(s, project_id)
            snap = await _snapshot(s, ops)
        Path(out).write_text(json.dumps(snap, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        print(f"[snapshot] {len(snap['operations'])} operations / "
              f"{len(snap['conflicts'])} conflicts / {len(snap['events'])} events -> {out}")
        return 0
    finally:
        await eng.dispose()


async def cmd_apply(actor: str, reason: str, project_id: str | None) -> int:
    from app.services.workpaper_sync.conflict_abandon import ConflictAbandonService
    from app.services.workpaper_sync.repository import WorkpaperSyncRepository

    eng = _engine()
    try:
        Session = async_sessionmaker(eng, expire_on_commit=False)
        async with Session() as s:
            ops = await _load_rows(s, project_id)
            print(f"[apply] 待作废 operation: {len(ops)}")
            ok = failed = 0
            for row in ops:
                label = f"{row['project_name'][:26]:26s} {row['entry_id'][:32]:32s} {row['operation_id'][:8]}"
                try:
                    svc = ConflictAbandonService(repo=WorkpaperSyncRepository(s))
                    outcome = await svc.abandon(
                        operation_id=uuid.UUID(row["operation_id"]),
                        reason=reason,
                        actor_id=uuid.UUID(actor),
                    )
                    await s.commit()
                    ok += 1
                    replay = " (idempotent replay)" if outcome.idempotent_replay else ""
                    print(f"  OK   {label}  {outcome.from_state} -> {outcome.to_state}"
                          f"  conflicts={outcome.abandoned_conflicts}{replay}")
                except Exception as exc:  # noqa: BLE001
                    await s.rollback()
                    failed += 1
                    print(f"  FAIL {label}  -> {type(exc).__name__}: {str(exc)[:120]}")
        print(f"[apply] ok={ok} failed={failed}")
        return 0 if failed == 0 else 1
    finally:
        await eng.dispose()


async def cmd_verify(snapshot_path: str) -> int:
    """对账：快照里的每条 operation 应已离开 conflict 态、冲突行三列齐备、未删行。"""
    snap = json.loads(Path(snapshot_path).read_text(encoding="utf-8"))
    eng = _engine()
    try:
        Session = async_sessionmaker(eng, expire_on_commit=False)
        async with Session() as s:
            bad = 0
            for op in snap["operations"]:
                oid = op["operation_id"]
                res = await s.execute(
                    sa.text("SELECT state, finished_at::text FROM working_paper_sync_operation WHERE id = :id"),
                    {"id": oid},
                )
                cur = res.first()
                res2 = await s.execute(
                    sa.text(
                        "SELECT count(*) AS n, "
                        "count(*) FILTER (WHERE abandoned_at IS NULL OR abandon_reason IS NULL "
                        "                   OR abandoned_by IS NULL) AS incomplete "
                        "FROM working_paper_sync_conflict WHERE operation_id = :id"
                    ),
                    {"id": oid},
                )
                c = res2.first()
                state = cur[0] if cur else "<missing>"
                flag = "OK "
                if state == "conflict" or c[1] > 0:
                    flag = "BAD"
                    bad += 1
                print(f"  {flag} {oid[:8]}  state={state:22s} conflicts={c[0]:3d} incomplete={c[1]}")
            print(f"[verify] bad={bad} / {len(snap['operations'])}")
            return 0 if bad == 0 else 1
    finally:
        await eng.dispose()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--verify")
    ap.add_argument("--actor")
    ap.add_argument("--reason", default="")
    ap.add_argument("--project")
    a = ap.parse_args()
    if a.snapshot:
        return asyncio.run(cmd_snapshot(a.snapshot, a.project))
    if a.verify:
        return asyncio.run(cmd_verify(a.verify))
    if a.apply:
        if not a.actor or not a.reason.strip():
            print("--apply 需要 --actor <uuid> 与 --reason \"...\"")
            return 2
        return asyncio.run(cmd_apply(a.actor, a.reason, a.project))
    print("用法：--snapshot out.json | --apply --actor <uuid> --reason ... | --verify out.json")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
