"""上线前 SOD 冲突扫描脚本

扫描现有 ProjectAssignment 记录，标记潜在 EQCR 独立性冲突：
- 同一 staff 在同一项目同时担任 eqcr 和 signing_partner/manager/auditor

输出冲突列表供 admin 确认处理。

用法：
    python -m scripts.scan_eqcr_sod_conflicts

或直接运行：
    python scripts/scan_eqcr_sod_conflicts.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# 确保 backend 目录在 sys.path 中
_backend_dir = Path(__file__).resolve().parent.parent
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.core.config import settings
from app.models.staff_models import ProjectAssignment, StaffMember
from app.models.core import Project


# EQCR 独立性冲突角色
CONFLICTING_ROLES = {"signing_partner", "manager", "auditor"}


async def scan_conflicts():
    """扫描所有 ProjectAssignment，找出 EQCR SOD 冲突。"""
    # 使用配置的数据库 URL
    db_url = settings.DATABASE_URL
    if not db_url:
        print("❌ 未配置 DATABASE_URL，无法连接数据库")
        return []

    # 如果是同步 URL，转为异步
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif db_url.startswith("sqlite://"):
        db_url = db_url.replace("sqlite://", "sqlite+aiosqlite://", 1)

    engine = create_async_engine(db_url, echo=False)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    conflicts = []

    async with factory() as session:
        # 查找所有 role='eqcr' 的委派
        eqcr_q = select(ProjectAssignment).where(
            ProjectAssignment.role == "eqcr",
            ProjectAssignment.is_deleted == False,  # noqa: E712
        )
        eqcr_assignments = (await session.execute(eqcr_q)).scalars().all()

        if not eqcr_assignments:
            print("✅ 未找到任何 EQCR 委派记录，无需检查冲突。")
            return []

        print(f"📋 找到 {len(eqcr_assignments)} 条 EQCR 委派记录，开始检查冲突...")

        for eqcr_assign in eqcr_assignments:
            # 查找同一 staff 在同一项目的其他角色
            conflict_q = select(ProjectAssignment).where(
                ProjectAssignment.project_id == eqcr_assign.project_id,
                ProjectAssignment.staff_id == eqcr_assign.staff_id,
                ProjectAssignment.role.in_(CONFLICTING_ROLES),
                ProjectAssignment.is_deleted == False,  # noqa: E712
            )
            conflict_rows = (await session.execute(conflict_q)).scalars().all()

            if conflict_rows:
                # 获取 staff 和 project 信息
                staff = await session.get(StaffMember, eqcr_assign.staff_id)
                project = await session.get(Project, eqcr_assign.project_id)

                staff_name = staff.name if staff else str(eqcr_assign.staff_id)
                project_name = project.name if project else str(eqcr_assign.project_id)

                for conflict in conflict_rows:
                    conflicts.append({
                        "staff_id": str(eqcr_assign.staff_id),
                        "staff_name": staff_name,
                        "project_id": str(eqcr_assign.project_id),
                        "project_name": project_name,
                        "eqcr_assignment_id": str(eqcr_assign.id)
                        if hasattr(eqcr_assign, "id")
                        else "N/A",
                        "conflicting_role": conflict.role,
                        "conflict_assignment_id": str(conflict.id)
                        if hasattr(conflict, "id")
                        else "N/A",
                    })

    await engine.dispose()
    return conflicts


def print_report(conflicts: list[dict]):
    """打印冲突报告。"""
    print("\n" + "=" * 70)
    print("EQCR 独立性 SOD 冲突扫描报告")
    print("=" * 70)

    if not conflicts:
        print("\n✅ 未发现任何 SOD 冲突。系统可安全上线。\n")
        return

    print(f"\n⚠️  发现 {len(conflicts)} 条潜在 SOD 冲突，需 admin 确认：\n")
    print(f"{'序号':<4} {'员工':<12} {'项目':<20} {'冲突角色':<16} {'说明'}")
    print("-" * 70)

    for i, c in enumerate(conflicts, 1):
        desc = f"同时担任 EQCR 和 {c['conflicting_role']}"
        print(f"{i:<4} {c['staff_name']:<12} {c['project_name']:<20} {c['conflicting_role']:<16} {desc}")

    print("\n" + "-" * 70)
    print("处理建议：")
    print("  1. 对每条冲突，确认是否为数据录入错误")
    print("  2. 如确实存在冲突，需移除其中一个角色委派")
    print("  3. EQCR 不得同时担任同项目的 signing_partner / manager / auditor")
    print("  4. 处理完成后重新运行本脚本验证")
    print("=" * 70 + "\n")


async def main():
    """主入口。"""
    print("🔍 开始扫描 EQCR SOD 冲突...")
    try:
        conflicts = await scan_conflicts()
        print_report(conflicts)
        # 有冲突时退出码 1，方便 CI 集成
        if conflicts:
            sys.exit(1)
    except Exception as e:
        print(f"❌ 扫描失败: {e}")
        print("   请确认数据库连接配置正确（DATABASE_URL）")
        sys.exit(2)


if __name__ == "__main__":
    asyncio.run(main())
