"""Phase 15 验收脚本：任务树完整性检查

断言所有节点 parent_id 引用有效 + status 枚举值合法。
用法: python -m scripts.phase15.check_task_tree_integrity
"""
import asyncio
import sys


async def main():
    from app.core.database import async_engine
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy import text

    fail = 0
    async with AsyncSession(async_engine) as db:
        # 检查 parent_id 引用有效性
        result = await db.execute(text("""
            SELECT t.id, t.parent_id FROM task_tree_nodes t
            WHERE t.parent_id IS NOT NULL
              AND NOT EXISTS (SELECT 1 FROM task_tree_nodes p WHERE p.id = t.parent_id)
        """))
        orphans = result.fetchall()
        if orphans:
            print(f"  [FAIL] {len(orphans)} orphan nodes with invalid parent_id")
            fail += len(orphans)
        else:
            print("  [PASS] All parent_id references valid")

        # 检查 status 枚举值合法
        valid_statuses = {'pending', 'in_progress', 'blocked', 'done'}
        result = await db.execute(text("""
            SELECT DISTINCT status FROM task_tree_nodes
        """))
        statuses = {r[0] for r in result.fetchall()}
        invalid = statuses - valid_statuses
        if invalid:
            print(f"  [FAIL] Invalid status values: {invalid}")
            fail += 1
        else:
            print(f"  [PASS] All status values valid: {statuses}")

        # 检查 node_level 枚举值合法
        valid_levels = {'unit', 'account', 'workpaper', 'evidence'}
        result = await db.execute(text("SELECT DISTINCT node_level FROM task_tree_nodes"))
        levels = {r[0] for r in result.fetchall()}
        invalid_levels = levels - valid_levels
        if invalid_levels:
            print(f"  [FAIL] Invalid node_level values: {invalid_levels}")
            fail += 1
        else:
            print(f"  [PASS] All node_level values valid: {levels}")

    print(f"\n[RESULT] {'ALL PASS' if fail == 0 else f'{fail} FAILURES'}")
    sys.exit(0 if fail == 0 else 1)


if __name__ == "__main__":
    asyncio.run(main())
