"""审计链分叉确认工具

默认只读：列出未确认链尾 ≠ 1（写入被拒）的链与处理计划（建议主链尾、各死端侧枝、可直接执行的命令），
以及分叉点扫描结果。
--apply 模式：在一条链上确认一个或多个死端（同一事务、同一把链锁；写后该链恰好剩一个未确认链尾，否则整体回滚）。
--dry-run-apply：用真实库、真实链锁走同一确认流程并整体回滚，输出链尾 / 分叉 / 校验结果，适合执行前演练。

用法:
    python -m scripts.ops.audit_chain_fork_ack [--chain-key __global__]
    python -m scripts.ops.audit_chain_fork_ack --apply --chain-key __global__ \
        --operator admin \
        --survivor <主链尾 entry-id> --dead <死端 entry-id> [--dead <死端 entry-id> ...] \
        --reason "旧写法无链锁并发写出的侧枝，主链取通到最新记录的一支"
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid

# 确保 backend/ 在 sys.path 上
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


def _fmt_ts(value) -> str:
    return value.isoformat(timespec="seconds") if value is not None else "-"


async def _scan(chain_key: str | None = None) -> None:
    from app.core.database import async_session
    from app.services.audit_chain.forks import blocked_chains, plan_chain_forks, scan_forks

    async with async_session() as db:
        blocked = await blocked_chains(db)
        if chain_key:
            blocked = [item for item in blocked if item[0] == chain_key]
        if not blocked:
            print("✅ 没有被阻断的链（每条链恰好一个未确认链尾）")
        for key, count, tails in blocked:
            plan = await plan_chain_forks(db, key)
            print(f"\n⚠️  链 {key}：{count} 条，{tails} 个未确认链尾")
            if plan.survivor_id is None:
                print("   未能给出建议主链尾（链尾时间并列或为空），请人工判断后用 --survivor 指定")
                print("   链尾：" + ", ".join(str(t) for t in plan.tails))
                continue
            print(f"   建议主链尾（时间最新）：{plan.survivor_id}")
            for branch in plan.branches:
                print(
                    f"   死端 {branch.tail_id}：侧枝 {len(branch.entry_ids)} 条，根 {branch.root_id}，"
                    f"{_fmt_ts(branch.first_ts)} ~ {_fmt_ts(branch.last_ts)}，动作 {', '.join(branch.actions)}"
                )
            print(f"   将写确认条目 {len(plan.ack_ids)} 条（死端 + 分叉点上的侧枝根）")
            deads = " ".join(f"--dead {b.tail_id}" for b in plan.branches)
            print(
                "   执行：python -m scripts.ops.audit_chain_fork_ack --apply "
                f"--chain-key {key} --operator <admin 用户名> --survivor {plan.survivor_id} {deads} --reason \"...\""
            )
        forks = await scan_forks(db, chain_key=chain_key)
        unack = [f for f in forks if len(f.get("survivors", [])) > 1]
        print(f"\n分叉点扫描：{len(forks)} 处，其中未确认 {len(unack)} 处")
        for f in unack:
            print(json.dumps(f, ensure_ascii=False))


async def _resolve_operator(db, operator: str):
    from sqlalchemy import select

    from app.models.core import User

    try:
        cond = User.id == uuid.UUID(operator)
    except ValueError:
        cond = User.username == operator
    user = (await db.execute(select(User).where(cond))).scalar_one_or_none()
    if user is None:
        raise SystemExit(f"❌ 用户 {operator} 不存在")
    if str(getattr(user.role, "value", user.role)) != "admin":
        raise SystemExit(f"❌ 用户 {operator} 不是 admin（role={getattr(user, 'role', '?')}）")
    if getattr(user, "is_deleted", False) or getattr(user, "is_active", True) is False:
        raise SystemExit(f"❌ 用户 {operator} 已停用或已删除")
    return user


async def _dry_run_apply(
    operator: str,
    survivor_id: str,
    dead_ids: list[str],
    reason: str,
    chain_key: str | None = None,
) -> None:
    """在共享库真实数据与链锁上演练确认、校验后整体回滚（不写 DB / Redis）。"""
    from app.core.database import async_session
    from app.services.audit_chain.forks import _unconfirmed_tails, append_fork_acks, blocked_chains, scan_forks
    from app.services.audit_chain.verify import verify_chain

    surv_uuid = uuid.UUID(survivor_id)
    dead_uuids = [uuid.UUID(item) for item in dead_ids]
    async with async_session() as db:
        user = await _resolve_operator(db, operator)
        ck = chain_key or "__global__"
        try:
            before = await verify_chain(db, chain_key=ck)
            written = await append_fork_acks(
                db, chain_key=ck, survivor_entry_id=surv_uuid, dead_entry_ids=dead_uuids,
                operator_id=user.id, reason=reason,
            )
            tails = await _unconfirmed_tails(db, ck)
            after = await verify_chain(db, chain_key=ck)
            unack = [f for f in await scan_forks(db, chain_key=ck) if len(f["survivors"]) > 1]
            still_blocked = [item for item in await blocked_chains(db) if item[0] == ck]
            before_set = {(p.get("type"), p.get("entry_id"), p.get("entry_hash")) for p in before.problems}
            added = [p for p in after.problems if (p.get("type"), p.get("entry_id"), p.get("entry_hash")) not in before_set]
            print(
                f"✅ 演练成功（已回滚）：链 {ck} 将写 {len(written)} 条确认；"
                f"未确认链尾 {len(tails)}，未确认分叉 {len(unack)}，写入阻断 {len(still_blocked)}，"
                f"校验新增问题 {len(added)}"
            )
            for issue in added:
                print("   新问题:", json.dumps(issue, ensure_ascii=False, default=str))
        finally:
            await db.rollback()
            print("演练事务已回滚（未写入确认条目）")


async def _apply(
    operator: str,
    survivor_id: str,
    dead_ids: list[str],
    reason: str,
    chain_key: str | None = None,
) -> None:
    from app.core.database import async_session
    from app.services.audit_chain.forks import append_fork_acks

    surv_uuid = uuid.UUID(survivor_id)
    dead_uuids = [uuid.UUID(item) for item in dead_ids]

    async with async_session() as db:
        user = await _resolve_operator(db, operator)
        ck = chain_key or "__global__"
        try:
            written = await append_fork_acks(
                db,
                chain_key=ck,
                survivor_entry_id=surv_uuid,
                dead_entry_ids=dead_uuids,
                operator_id=user.id,
                reason=reason,
            )
        except Exception:
            await db.rollback()
            raise
        await db.commit()
        print(f"✅ 链 {ck} 已写入确认条目 {len(written)} 条：")
        for entry in written:
            print(f"   {entry.id}  dead={entry.payload.get('dead_entry_id')}  role={entry.payload.get('dead_role')}")
        print(f"   新链尾：{written[-1].id}（{written[-1].entry_hash}）")


def main() -> None:
    parser = argparse.ArgumentParser(description="审计链分叉确认工具")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="写入确认")
    mode.add_argument("--dry-run-apply", action="store_true", help="真实链锁内演练确认后整体回滚（不写入）")
    parser.add_argument("--chain-key", default=None, help="链键（默认全部链；--apply 时默认 __global__）")
    parser.add_argument("--operator", default=None, help="操作人用户名或 user_id（须 admin 且在用；--apply 必需）")
    parser.add_argument("--survivor", default=None, help="主链尾条目 ID")
    parser.add_argument("--dead", action="append", default=[], help="死端链尾条目 ID（可重复）")
    parser.add_argument("--reason", default=None, help="确认原因")
    args = parser.parse_args()

    if args.apply or args.dry_run_apply:
        missing = [name for name in ("operator", "survivor", "reason") if not getattr(args, name)]
        if not args.dead:
            missing.append("dead")
        if missing:
            print("❌ --apply / --dry-run-apply 模式需要 " + "、".join(f"--{name}" for name in missing))
            sys.exit(1)
        runner = _apply if args.apply else _dry_run_apply
        asyncio.run(runner(args.operator, args.survivor, args.dead, args.reason, args.chain_key))
    else:
        asyncio.run(_scan(args.chain_key))


if __name__ == "__main__":
    main()
