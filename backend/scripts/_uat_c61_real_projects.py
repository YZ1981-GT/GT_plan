"""C.6.1 真实项目综合 UAT 探查脚本.

直连 PG 检查项目元数据 + 附注章节状态，为综合 UAT 提供数据基础。
"""
from __future__ import annotations

import asyncio
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

DB_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/audit_platform"


async def main():
    engine = create_async_engine(DB_URL)
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

    async with SessionLocal() as db:
        # 1. 项目盘点
        print("=" * 70)
        print("1. 真实项目清单")
        print("=" * 70)
        # First check what columns exist
        cols_result = await db.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'projects'
            ORDER BY ordinal_position
        """))
        cols = [r.column_name for r in cols_result.fetchall()]
        print(f"  projects 表共 {len(cols)} 列")
        print(f"  全列名: {cols}")
        print()

        # Use only confirmed columns
        select_cols = ["id", "name"]
        for opt in ("template_type", "consol_level", "parent_project_id", "is_deleted", "year"):
            if opt in cols:
                select_cols.append(opt)

        result = await db.execute(text(f"""
            SELECT {', '.join(select_cols)}
            FROM projects
            ORDER BY name
        """))
        projects = result.fetchall()
        for p in projects:
            row_dict = dict(p._mapping)
            print(f"  {row_dict}")

        # 2. 附注章节统计
        print()
        print("=" * 70)
        print("2. 附注章节统计（按项目）")
        print("=" * 70)
        result = await db.execute(text("""
            SELECT p.id, p.name, COUNT(dn.id) as note_count,
                   COUNT(CASE WHEN dn.is_deleted=false THEN 1 END) as active_notes,
                   COUNT(CASE WHEN dn.section_id IS NOT NULL THEN 1 END) as with_section_id
            FROM projects p
            LEFT JOIN disclosure_notes dn ON dn.project_id = p.id
            WHERE p.name LIKE '%首汽%' OR p.name LIKE '%重庆%'
            GROUP BY p.id, p.name
            ORDER BY p.name
        """))
        for r in result.fetchall():
            print(f"  {r.name}: {r.note_count} total / {r.active_notes} active / "
                  f"{r.with_section_id} with section_id")

        # 3. TB 数据规模
        print()
        print("=" * 70)
        print("3. TB 数据规模（决定能否生成附注）")
        print("=" * 70)
        result = await db.execute(text("""
            SELECT p.name,
                   (SELECT COUNT(*) FROM tb_balance WHERE project_id=p.id) as tb_balance,
                   (SELECT COUNT(*) FROM tb_ledger WHERE project_id=p.id) as tb_ledger
            FROM projects p
            WHERE p.name LIKE '%首汽%' OR p.name LIKE '%重庆%' OR p.name LIKE '%shouqi%'
            ORDER BY p.name
        """))
        for r in result.fetchall():
            print(f"  {r.name}: tb_balance={r.tb_balance}, tb_ledger={r.tb_ledger}")

        # 4. 检查合并关系
        print()
        print("=" * 70)
        print("4. 合并项目关系")
        print("=" * 70)
        result = await db.execute(text("""
            SELECT id, name, consol_level, parent_project_id, template_type
            FROM projects
            WHERE consol_level >= 2 OR parent_project_id IS NOT NULL
            ORDER BY consol_level DESC NULLS LAST, name
        """))
        consol_projects = result.fetchall()
        if consol_projects:
            for r in consol_projects:
                print(f"  {r.name}: level={r.consol_level}, parent={r.parent_project_id}")
        else:
            print("  ❌ 当前数据库无合并项目（consol_level=2/3）— C.6.1 合并场景需先创建合并项目")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
