"""审计链链尾列表工具

默认只读：列出每条链的条目数、未确认链尾数（与写链内核 ``head.read_head`` 同一定义：
同链内没有后继、且未被 ``audit.fork_ack`` 确认为死端）与链尾 ID。

用法:
    python -m scripts.ops.audit_chain_heads
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from collections import defaultdict

from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


async def _list_heads() -> None:
    from sqlalchemy import select

    from app.core.database import async_session
    from app.models.audit_log_models import AuditLogEntry
    from app.services.audit_chain.forks import FORK_ACK_ACTION, ChainRow, _tail_ids
    from app.services.audit_chain.head import chain_key_of

    ale = AuditLogEntry
    async with async_session() as db:
        rows = (
            await db.execute(select(ale.id, ale.entry_hash, ale.prev_hash, ale.action_type, ale.payload))
        ).all()

    if not rows:
        print("📭 审计链为空")
        return

    chains: dict[str, list[ChainRow]] = defaultdict(list)
    dead: dict[str, set[uuid.UUID]] = defaultdict(set)
    for row in rows:
        payload = row.payload if isinstance(row.payload, dict) else {}
        key = chain_key_of(payload.get("project_id") or None)
        chains[key].append(ChainRow(row.id, row.entry_hash, row.prev_hash, None, row.action_type))
        raw = payload.get("dead_entry_id") if row.action_type == FORK_ACK_ACTION else None
        if raw:
            try:
                dead[key].add(uuid.UUID(str(raw)))
            except (TypeError, ValueError):
                continue

    print(f"📊 共 {len(chains)} 条链, {len(rows)} 个条目\n")
    print(f"{'链键':<50} {'条目数':>6} {'链尾数':>6} {'链尾 ID'}")
    print("-" * 120)
    total_tails = 0
    blocked = 0
    for key in sorted(chains):
        tails = sorted(str(t) for t in _tail_ids(chains[key], dead[key]))
        total_tails += len(tails)
        blocked += len(tails) != 1
        shown = ", ".join(t[:12] + "…" for t in tails[:5])
        if len(tails) > 5:
            shown += f" (+{len(tails) - 5})"
        status = "✅" if len(tails) == 1 else "⚠️"
        key_display = key if len(key) <= 48 else key[:45] + "…"
        print(f"{status} {key_display:<48} {len(chains[key]):>6} {len(tails):>6}  {shown}")
    print(f"\n合计未确认链尾: {total_tails}, 写入被拒的链（未确认链尾 ≠ 1）: {blocked}")


def main() -> None:
    parser = argparse.ArgumentParser(description="审计链链尾列表工具")
    parser.parse_args()  # 目前无额外参数
    asyncio.run(_list_heads())


if __name__ == "__main__":
    main()
