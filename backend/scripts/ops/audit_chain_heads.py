"""审计链链尾列表工具

默认只读：列出每条链的链尾条目与统计。

用法:
    python -m scripts.ops.audit_chain_heads
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from collections import defaultdict

from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


async def _list_heads() -> None:
    from sqlalchemy import func, select

    from app.core.database import async_session_factory
    from app.models.audit_log_models import AuditLogEntry
    from app.services.audit_chain.head import chain_key_of

    ALE = AuditLogEntry

    async with async_session_factory() as db:
        # 取全部条目的 id, entry_hash, prev_hash, payload->project_id
        stmt = select(ALE.id, ALE.entry_hash, ALE.prev_hash, ALE.payload)
        rows = (await db.execute(stmt)).all()

        if not rows:
            print("📭 审计链为空")
            return

        # 按链键分组
        chains: dict[str, list] = defaultdict(list)
        for row in rows:
            payload = row.payload or {}
            pid = payload.get("project_id") if isinstance(payload, dict) else None
            ck = chain_key_of(pid)
            chains[ck].append({
                "id": str(row.id),
                "entry_hash": row.entry_hash,
                "prev_hash": row.prev_hash,
            })

        # 找每条链的链尾
        print(f"📊 共 {len(chains)} 条链, {len(rows)} 个条目\n")
        print(f"{'链键':<50} {'条目数':>6} {'链尾数':>6} {'链尾 ID'}")
        print("-" * 120)

        for ck in sorted(chains.keys()):
            entries = chains[ck]
            all_hashes = {e["entry_hash"] for e in entries}
            referenced = {e["prev_hash"] for e in entries if e["prev_hash"] in all_hashes}
            tails = [e for e in entries if e["entry_hash"] not in referenced]

            tail_ids = ", ".join(e["id"][:12] + "…" for e in tails[:5])
            if len(tails) > 5:
                tail_ids += f" (+{len(tails) - 5})"

            status = "⚠️" if len(tails) > 1 else "✅"
            ck_display = ck if len(ck) <= 48 else ck[:45] + "…"
            print(f"{status} {ck_display:<48} {len(entries):>6} {len(tails):>6}  {tail_ids}")

        total_tails = sum(
            1 for ck, entries in chains.items()
            for e in entries
            if e["entry_hash"] not in {
                ee["prev_hash"] for ee in entries if ee["prev_hash"] in {eee["entry_hash"] for eee in entries}
            }
        )
        multi = sum(
            1 for ck, entries in chains.items()
            if sum(
                1 for e in entries
                if e["entry_hash"] not in {
                    ee["prev_hash"] for ee in entries if ee["prev_hash"] in {eee["entry_hash"] for eee in entries}
                }
            ) > 1
        )
        print(f"\n合计链尾: {total_tails}, 多链尾链: {multi}")


def main() -> None:
    parser = argparse.ArgumentParser(description="审计链链尾列表工具")
    parser.parse_args()  # 目前无额外参数
    asyncio.run(_list_heads())


if __name__ == "__main__":
    main()
