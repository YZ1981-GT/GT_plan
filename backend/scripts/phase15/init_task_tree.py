"""Phase 15: 从现有数据构建初始任务树

从 projects + trial_balance + working_papers + attachments 构建四级 task_tree_nodes。

用法: python -m scripts.phase15.init_task_tree --project-id <uuid> [--dry-run]
"""
import asyncio
import sys
import uuid
from datetime import datetime


async def main(project_id: str, dry_run: bool = False):
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy import text
    from app.core.database import async_engine

    async with AsyncSession(async_engine) as db:
        pid = project_id
        created = 0

        # Level 1: unit (从 projects 取)
        unit_id = uuid.uuid4()
        if not dry_run:
            await db.execute(text("""
                INSERT INTO task_tree_nodes (id, project_id, node_level, ref_id, status, created_at, updated_at)
                VALUES (:id, :pid, 'unit', :pid, 'pending', NOW(), NOW())
                ON CONFLICT DO NOTHING
            """), {"id": str(unit_id), "pid": pid})
        print(f"  [UNIT] id={unit_id}")
        created += 1

        # Level 2: account (从 trial_balance distinct account_code)
        result = await db.execute(text("""
            SELECT DISTINCT standard_account_code, id FROM trial_balance
            WHERE project_id = :pid AND is_deleted = false
            LIMIT 500
        """), {"pid": pid})
        accounts = result.fetchall()
        for acc_code, acc_id in accounts:
            node_id = uuid.uuid4()
            if not dry_run:
                await db.execute(text("""
                    INSERT INTO task_tree_nodes (id, project_id, node_level, parent_id, ref_id, status, meta, created_at, updated_at)
                    VALUES (:id, :pid, 'account', :parent, :ref, 'pending', :meta, NOW(), NOW())
                    ON CONFLICT DO NOTHING
                """), {"id": str(node_id), "pid": pid, "parent": str(unit_id),
                       "ref": str(acc_id), "meta": f'{{"account_code": "{acc_code}"}}'})
            created += 1

        # Level 3: workpaper (从 working_paper)
        result = await db.execute(text("""
            SELECT id, wp_code FROM working_paper
            WHERE project_id = :pid AND is_deleted = false
            LIMIT 1000
        """), {"pid": pid})
        workpapers = result.fetchall()
        for wp_id, wp_code in workpapers:
            node_id = uuid.uuid4()
            if not dry_run:
                await db.execute(text("""
                    INSERT INTO task_tree_nodes (id, project_id, node_level, parent_id, ref_id, status, meta, created_at, updated_at)
                    VALUES (:id, :pid, 'workpaper', :parent, :ref, 'pending', :meta, NOW(), NOW())
                    ON CONFLICT DO NOTHING
                """), {"id": str(node_id), "pid": pid, "parent": str(unit_id),
                       "ref": str(wp_id), "meta": f'{{"wp_code": "{wp_code}"}}'})
            created += 1

        if not dry_run:
            await db.commit()

        print(f"[INIT_TREE] 完成: project={pid} 创建 {created} 个节点{'（dry-run）' if dry_run else ''}")


if __name__ == "__main__":
    pid = None
    dry_run = "--dry-run" in sys.argv
    for i, arg in enumerate(sys.argv):
        if arg == "--project-id" and i + 1 < len(sys.argv):
            pid = sys.argv[i + 1]
    if not pid:
        print("用法: python -m scripts.phase15.init_task_tree --project-id <uuid> [--dry-run]")
        sys.exit(1)
    asyncio.run(main(pid, dry_run))
