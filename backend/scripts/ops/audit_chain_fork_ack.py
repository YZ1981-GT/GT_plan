"""审计链分叉确认工具

默认只读：扫描分叉并打印。
--apply 模式：确认一处分叉（需提供 --operator / --survivor / --dead / --reason）。

用法:
    python -m scripts.ops.audit_chain_fork_ack
    python -m scripts.ops.audit_chain_fork_ack --apply \
        --operator <admin-user-id> \
        --survivor <entry-id> --dead <entry-id> \
        --reason "保留 view 分支"
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


async def _scan(chain_key: str | None = None) -> None:
    from app.core.database import async_session
    from app.services.audit_chain.forks import scan_forks

    async with async_session() as db:
        forks = await scan_forks(db, chain_key=chain_key)
        if not forks:
            print("✅ 未发现未确认分叉")
            return
        print(f"⚠️  发现 {len(forks)} 处分叉：")
        for f in forks:
            print(json.dumps(f, indent=2, ensure_ascii=False))


async def _apply(
    operator_id: str,
    survivor_id: str,
    dead_id: str,
    reason: str,
    chain_key: str | None = None,
) -> None:
    from sqlalchemy import select

    from app.core.database import async_session
    from app.models.core import User
    from app.services.audit_chain.forks import append_fork_ack
    from app.services.audit_chain.head import chain_key_of

    op_uuid = uuid.UUID(operator_id)
    surv_uuid = uuid.UUID(survivor_id)
    dead_uuid = uuid.UUID(dead_id)

    async with async_session() as db:
        # 验证 operator 是 admin
        user = (
            await db.execute(
                select(User).where(User.id == op_uuid)
            )
        ).scalar_one_or_none()
        if not user:
            print(f"❌ 用户 {operator_id} 不存在")
            sys.exit(1)
        if getattr(user, "role", None) != "admin":
            print(f"❌ 用户 {operator_id} 不是 admin（role={getattr(user, 'role', '?')}）")
            sys.exit(1)

        ck = chain_key or "__global__"
        entry = await append_fork_ack(
            db,
            chain_key=ck,
            survivor_entry_id=surv_uuid,
            dead_entry_id=dead_uuid,
            operator_id=op_uuid,
            reason=reason,
        )
        await db.commit()
        print(f"✅ 分叉确认已写入: entry_id={entry.id}, entry_hash={entry.entry_hash}")


def main() -> None:
    parser = argparse.ArgumentParser(description="审计链分叉确认工具")
    parser.add_argument("--apply", action="store_true", help="写入确认（默认只读扫描）")
    parser.add_argument("--chain-key", default=None, help="链键（默认扫描全部）")
    parser.add_argument("--operator", default=None, help="操作人 user_id（--apply 必需）")
    parser.add_argument("--survivor", default=None, help="保留分支条目 ID")
    parser.add_argument("--dead", default=None, help="废弃分支条目 ID")
    parser.add_argument("--reason", default=None, help="确认原因")
    args = parser.parse_args()

    if args.apply:
        for name in ("operator", "survivor", "dead", "reason"):
            if not getattr(args, name):
                print(f"❌ --apply 模式需要 --{name}")
                sys.exit(1)
        asyncio.run(_apply(
            args.operator, args.survivor, args.dead, args.reason, args.chain_key
        ))
    else:
        asyncio.run(_scan(args.chain_key))


if __name__ == "__main__":
    main()
