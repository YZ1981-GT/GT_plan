"""Phase 16: 从现有数据构建初始版本链

从 working_papers.file_version + report_snapshots 构建 version_line_stamps。

用法: python -m scripts.phase16.init_version_line --project-id <uuid> [--dry-run]
"""
import asyncio
import sys
import uuid


async def main(project_id: str, dry_run: bool = False):
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy import text
    from app.core.database import async_engine

    async with AsyncSession(async_engine) as db:
        pid = project_id
        created = 0

        # 从 working_paper 构建 workpaper 版本戳
        result = await db.execute(text("""
            SELECT id, file_version FROM working_paper
            WHERE project_id = :pid AND is_deleted = false AND file_version > 0
            LIMIT 2000
        """), {"pid": pid})
        workpapers = result.fetchall()
        for wp_id, version in workpapers:
            stamp_id = uuid.uuid4()
            trace_id = f"trc_init_migration_{str(uuid.uuid4())[:12]}"
            if not dry_run:
                await db.execute(text("""
                    INSERT INTO version_line_stamps (id, project_id, object_type, object_id, version_no, trace_id, created_at)
                    VALUES (:id, :pid, 'workpaper', :oid, :ver, :tid, NOW())
                    ON CONFLICT DO NOTHING
                """), {"id": str(stamp_id), "pid": pid, "oid": str(wp_id),
                       "ver": version, "tid": trace_id})
            created += 1

        # 从 report_snapshots 构建 report 版本戳（如果表存在）
        try:
            result = await db.execute(text("""
                SELECT id, project_id, snapshot_version FROM report_snapshots
                WHERE project_id = :pid
                LIMIT 500
            """), {"pid": pid})
            snapshots = result.fetchall()
            for snap_id, _, version in snapshots:
                stamp_id = uuid.uuid4()
                trace_id = f"trc_init_migration_{str(uuid.uuid4())[:12]}"
                if not dry_run:
                    await db.execute(text("""
                        INSERT INTO version_line_stamps (id, project_id, object_type, object_id, version_no, trace_id, created_at)
                        VALUES (:id, :pid, 'report', :oid, :ver, :tid, NOW())
                        ON CONFLICT DO NOTHING
                    """), {"id": str(stamp_id), "pid": pid, "oid": str(snap_id),
                           "ver": version or 1, "tid": trace_id})
                created += 1
        except Exception as e:
            print(f"  [SKIP] report_snapshots: {e}")

        if not dry_run:
            await db.commit()

        print(f"[INIT_VERSION] 完成: project={pid} 创建 {created} 个版本戳{'（dry-run）' if dry_run else ''}")


if __name__ == "__main__":
    pid = None
    dry_run = "--dry-run" in sys.argv
    for i, arg in enumerate(sys.argv):
        if arg == "--project-id" and i + 1 < len(sys.argv):
            pid = sys.argv[i + 1]
    if not pid:
        print("用法: python -m scripts.phase16.init_version_line --project-id <uuid> [--dry-run]")
        sys.exit(1)
    asyncio.run(main(pid, dry_run))
