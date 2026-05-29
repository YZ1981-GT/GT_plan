"""Phase 16 验收脚本：五层一致性复算检查

调用 replay_consistency，断言五层结果均有返回 + blocking_count 与实际差异一致。
用法: python -m scripts.phase16.check_consistency_replay --project-id <uuid>
"""
import asyncio
import sys


async def main(project_id: str):
    from app.core.database import async_engine
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.services.consistency_replay_engine import consistency_replay_engine
    import uuid

    async with AsyncSession(async_engine) as db:
        result = await consistency_replay_engine.replay_consistency(db, uuid.UUID(project_id))

        print(f"  snapshot_id: {result.snapshot_id}")
        print(f"  overall_status: {result.overall_status}")
        print(f"  blocking_count: {result.blocking_count}")
        print(f"  trace_id: {result.trace_id}")
        print(f"  layers: {len(result.layers)}")

        if len(result.layers) != 5:
            print(f"  [FAIL] Expected 5 layers, got {len(result.layers)}")
            sys.exit(1)

        for i, layer in enumerate(result.layers):
            status_icon = "✅" if layer.status == "consistent" else "❌"
            print(f"  Layer {i+1}: {layer.from_table} → {layer.to_table} {status_icon} ({len(layer.diffs)} diffs)")

        # 验证 blocking_count 一致
        actual_blocking = sum(
            1 for l in result.layers for d in l.diffs if d.severity == "blocking"
        )
        if actual_blocking == result.blocking_count:
            print(f"  [PASS] blocking_count={result.blocking_count} matches actual diffs")
        else:
            print(f"  [FAIL] blocking_count={result.blocking_count} != actual={actual_blocking}")
            sys.exit(1)

    print(f"\n[RESULT] Consistency replay check complete")


if __name__ == "__main__":
    pid = None
    for i, arg in enumerate(sys.argv):
        if arg == "--project-id" and i + 1 < len(sys.argv):
            pid = sys.argv[i + 1]
    if not pid:
        print("用法: python -m scripts.phase16.check_consistency_replay --project-id <uuid>")
        sys.exit(1)
    asyncio.run(main(pid))
