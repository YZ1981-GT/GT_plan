"""一次性补数据脚本：为已有项目补充 skip 子底稿的 wp_index + working_paper 记录。

用法: python -m scripts.fix_skip_sub_workpapers

背景：
chain_orchestrator 原逻辑将子表(如 A1-11)折叠到主底稿(A1)，不创建独立 wp_index。
但前端聚合组件(GtA1Dashboard 等)需要通过 getWpIndex 查找这些子底稿的 wp_id。
此脚本为所有已有项目补充缺失的 skip 子底稿记录。
"""
import asyncio
import sys
import os
import uuid

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.core.config import settings


async def main():
    engine = create_async_engine(settings.DATABASE_URL, pool_size=5, max_overflow=0)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # Load wp_code_overrides to find all skip entries
    import json
    overrides_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "app", "data", "wp_code_overrides.json"
    )
    with open(overrides_path, "r", encoding="utf-8") as f:
        overrides = json.load(f)

    skip_codes = {code for code, ct in overrides.items() if ct == "skip"}
    print(f"Found {len(skip_codes)} skip codes in wp_code_overrides.json")

    async with async_session() as db:
        # Get all projects
        result = await db.execute(text("SELECT id FROM projects WHERE is_deleted = false"))
        projects = [row[0] for row in result.fetchall()]
        print(f"Processing {len(projects)} projects...")

        total_created = 0

        for project_id in projects:
            # Get existing wp_index codes for this project
            result = await db.execute(text(
                "SELECT wp_code FROM wp_index WHERE project_id = :pid"
            ), {"pid": str(project_id)})
            existing_codes = {row[0] for row in result.fetchall()}

            # Find skip codes whose primary exists but they themselves don't
            to_create = []
            for skip_code in skip_codes:
                if skip_code in existing_codes:
                    continue  # already exists
                # Check if primary exists
                primary = skip_code.split("-")[0]
                if primary in existing_codes:
                    to_create.append(skip_code)

            if not to_create:
                continue

            for sub_code in sorted(to_create):
                try:
                    wp_index_id = uuid.uuid4()
                    wp_id = uuid.uuid4()
                    cycle = sub_code[0] if sub_code and sub_code[0].isalpha() else None

                    await db.execute(text("""
                        INSERT INTO wp_index (id, project_id, wp_code, wp_name, audit_cycle, status)
                        VALUES (:id, :pid, :code, :name, :cycle, 'not_started')
                        ON CONFLICT (project_id, wp_code) DO NOTHING
                    """), {
                        "id": str(wp_index_id),
                        "pid": str(project_id),
                        "code": sub_code,
                        "name": f"底稿{sub_code}",
                        "cycle": cycle,
                    })

                    await db.execute(text("""
                        INSERT INTO working_paper (id, wp_index_id, project_id, source_type, file_path, parsed_data)
                        VALUES (:id, :wpi_id, :pid, 'template', :path, '{}')
                        ON CONFLICT DO NOTHING
                    """), {
                        "id": str(wp_id),
                        "wpi_id": str(wp_index_id),
                        "pid": str(project_id),
                        "path": f"storage/projects/{project_id}/workpapers/{sub_code}.xlsx",
                    })

                    total_created += 1
                except Exception as e:
                    print(f"  Warning: {sub_code} for project {project_id}: {e}")

            await db.commit()
            print(f"  Project {project_id}: created {len(to_create)} skip sub-workpapers")

        print(f"\nDone! Total created: {total_created}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
