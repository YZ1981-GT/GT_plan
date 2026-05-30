"""批量模板版本升级迁移脚本

对比旧/新模板 xlsx → 生成 diff → 批量迁移所有已编制底稿的 parsed_data。
幂等：已迁移的底稿（含 _migrated_at 标记）自动跳过。

Spec: wp-template-migration
Requirements: 2.1

用法::

    python backend/scripts/migrate/migrate_template_version.py \\
        --old-template path/to/old.xlsx \\
        --new-template path/to/new.xlsx \\
        [--project-id UUID] \\
        [--dry-run] \\
        [--report-dir docs/uat]

参数：
    --old-template: 旧版本模板 xlsx 路径
    --new-template: 新版本模板 xlsx 路径
    --project-id: 可选，限定迁移某个项目的底稿
    --dry-run: 只打印将要执行的操作，不提交
    --report-dir: 报告输出目录（默认 docs/uat）

回滚::

    通过 WpMigrationService.rollback(wp_id, snapshot_id) 逐个回滚，
    或使用快照表 wp_migration_snapshots 批量恢复。
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

# 确保 backend 包可导入
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import sqlalchemy as sa  # noqa: E402

import app.models  # noqa: E402,F401
from app.core.database import async_session  # noqa: E402
from app.services.wp_migration_report_service import (  # noqa: E402
    MigrationReport,
    MigrationResult,
    classify_migration_result,
    generate_migration_report_markdown,
    save_migration_report,
)
from app.services.wp_migration_service import WpMigrationService  # noqa: E402
from app.services.wp_template_diff_service import (  # noqa: E402
    _read_template_structure,
    generate_template_diff,
)


async def migrate(
    old_template: str,
    new_template: str,
    project_id: str | None = None,
    dry_run: bool = False,
    report_dir: str = "docs/uat",
) -> MigrationReport:
    """批量执行模板版本迁移

    Args:
        old_template: 旧模板路径
        new_template: 新模板路径
        project_id: 可选，限定项目
        dry_run: 是否只预览
        report_dir: 报告输出目录

    Returns:
        MigrationReport
    """
    old_path = Path(old_template)
    new_path = Path(new_template)

    if not old_path.exists():
        print(f"❌ 旧模板文件不存在: {old_path}")
        sys.exit(1)
    if not new_path.exists():
        print(f"❌ 新模板文件不存在: {new_path}")
        sys.exit(1)

    # 生成 diff
    print(f"📊 生成模板 diff...")
    print(f"   旧版本: {old_path.name}")
    print(f"   新版本: {new_path.name}")

    diff = generate_template_diff(old_path, new_path)
    summary = diff.summary()
    print(f"   变化: {summary}")

    if not diff.has_changes:
        print("✅ 无变化，无需迁移。")
        return MigrationReport(
            template_old_version=old_path.name,
            template_new_version=new_path.name,
            started_at=datetime.now(timezone.utc).isoformat(),
            finished_at=datetime.now(timezone.utc).isoformat(),
        )

    # 读取新模板结构（用于填充新增 sheet 的默认值）
    from app.services.wp_parsed_data_service import _read_xlsx_structure

    new_structure = _read_xlsx_structure(new_path)

    # 初始化报告
    report = MigrationReport(
        template_old_version=old_path.name,
        template_new_version=new_path.name,
        started_at=datetime.now(timezone.utc).isoformat(),
    )

    # 查询待迁移底稿
    async with async_session() as session:
        svc = WpMigrationService(session)

        query = """
            SELECT wp.id, wi.wp_code, wi.wp_name
            FROM working_paper wp
            JOIN wp_index wi ON wp.wp_index_id = wi.id
            WHERE wp.is_deleted = false
              AND wp.parsed_data IS NOT NULL
        """
        params: dict = {}

        if project_id:
            query += " AND wp.project_id = :pid"
            params["pid"] = project_id

        query += " ORDER BY wi.wp_code"

        rows = (await session.execute(sa.text(query), params)).fetchall()
        print(f"\n📋 待处理底稿: {len(rows)} 个")

        if dry_run:
            print("\n[DRY RUN] 以下底稿将被迁移（不实际执行）:")
            for row in rows[:20]:
                print(f"  {row.wp_code} - {row.wp_name}")
            if len(rows) > 20:
                print(f"  ... 及其他 {len(rows) - 20} 个")
            report.finished_at = datetime.now(timezone.utc).isoformat()
            return report

        # 批量迁移
        for i, row in enumerate(rows, 1):
            wp_id = UUID(str(row.id))
            result = await svc.migrate_workpaper(
                wp_id=wp_id,
                diff=diff,
                new_template_structure=new_structure,
            )

            migration_result = classify_migration_result(
                wp_id=str(wp_id),
                wp_code=row.wp_code or "",
                wp_name=row.wp_name or "",
                migrate_result=result,
            )
            report.add_result(migration_result)

            # 进度输出
            status_icon = {
                "success": "✅",
                "skipped": "⏭️",
                "manual_required": "⚠️",
                "error": "❌",
            }.get(migration_result.status, "?")
            if i % 50 == 0 or i == len(rows):
                print(f"  进度: {i}/{len(rows)}")

        # 提交
        await session.commit()

    report.finished_at = datetime.now(timezone.utc).isoformat()

    # 保存报告
    report_path = save_migration_report(report, output_dir=report_dir)
    print(f"\n📄 报告已保存: {report_path}")
    print(f"\n汇总:")
    print(f"  ✅ 成功: {report.success_count}")
    print(f"  ⏭️ 跳过: {report.skipped_count}")
    print(f"  ⚠️ 需人工: {report.manual_required_count}")
    print(f"  ❌ 错误: {report.error_count}")

    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="批量模板版本升级迁移（幂等）",
    )
    parser.add_argument(
        "--old-template",
        required=True,
        help="旧版本模板 xlsx 路径",
    )
    parser.add_argument(
        "--new-template",
        required=True,
        help="新版本模板 xlsx 路径",
    )
    parser.add_argument(
        "--project-id",
        default=None,
        help="可选：限定迁移某个项目",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只预览，不实际执行",
    )
    parser.add_argument(
        "--report-dir",
        default="docs/uat",
        help="报告输出目录（默认 docs/uat）",
    )
    args = parser.parse_args()

    asyncio.run(migrate(
        old_template=args.old_template,
        new_template=args.new_template,
        project_id=args.project_id,
        dry_run=args.dry_run,
        report_dir=args.report_dir,
    ))


if __name__ == "__main__":
    main()
