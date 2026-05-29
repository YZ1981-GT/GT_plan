"""从 2025人员情况.xlsx 导入种子数据到 staff_members 表

Phase 9 Task 1.1a
用法: python -m scripts.seed_staff
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# 确保 backend 目录在 sys.path 中
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))


async def main():
    import openpyxl
    from app.core.database import async_session
    from app.models.staff_models import StaffMember
    import sqlalchemy as sa

    # 查找 Excel 文件
    xlsx_path = backend_dir.parent / "2025人员情况.xlsx"
    if not xlsx_path.exists():
        print(f"❌ 文件不存在: {xlsx_path}")
        return

    wb = openpyxl.load_workbook(str(xlsx_path), read_only=True)
    ws = wb.active
    if not ws:
        print("❌ 工作表为空")
        return

    rows = list(ws.iter_rows(min_row=2, values_only=True))  # 跳过表头
    print(f"📊 读取到 {len(rows)} 行数据")

    async with async_session() as db:
        # 检查是否已有数据
        count = (await db.execute(
            sa.select(sa.func.count()).select_from(StaffMember)
            .where(StaffMember.is_deleted == False)  # noqa
        )).scalar() or 0

        if count > 0:
            print(f"⚠️ staff_members 表已有 {count} 条数据，跳过导入（增量模式）")
            # 增量：只导入不存在的
            existing_names = set(
                (await db.execute(
                    sa.select(StaffMember.name).where(StaffMember.is_deleted == False)  # noqa
                )).scalars().all()
            )
        else:
            existing_names = set()

        imported = 0
        seq = count  # 工号序号从已有数量开始

        for row in rows:
            if not row or not row[0]:
                continue

            name = str(row[0]).strip()
            if name in existing_names:
                continue

            department = str(row[1]).strip() if row[1] else None
            title = str(row[2]).strip() if row[2] else None
            partner_name = str(row[3]).strip() if row[3] else None

            seq += 1
            employee_no = f"SJ2-{seq:03d}"

            staff = StaffMember(
                name=name,
                employee_no=employee_no,
                department=department,
                title=title,
                partner_name=partner_name,
            )
            db.add(staff)
            imported += 1

        await db.commit()
        print(f"✅ 成功导入 {imported} 名人员（工号 SJ2-{count+1:03d} ~ SJ2-{count+imported:03d}）")

    wb.close()


if __name__ == "__main__":
    asyncio.run(main())
