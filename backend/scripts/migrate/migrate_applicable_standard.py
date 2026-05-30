"""一次性 DB backfill：projects.applicable_standard_v2（多准则状态统一）

Spec: multi-standard-unification
Requirements: 6.1, 6.2, 6.3

**目的**：
  把 V0XX 新增的结构化统一准则字段 ``projects.applicable_standard_v2``
  从现有 4 套散落口径推断填充：

    - ``wizard_state.basic_info.data.template_type``（项目向导）
    - ``projects.template_type``（旧专用列，迁移期权威）
    - ``projects.report_scope``（旧专用列）
    - ``projects.scenario``（底稿场景列）

  填充后的结构化值形如::

      {"entity_type": "soe"|"listed"|"private",
       "scope": "standalone"|"consolidated",
       "stage": "normal"|"ipo"|"transfer"|"restructure"|"fraud_response"}

**推断逻辑**：
  直接复用 ``StandardUnificationService._derive_from_project(project)``——它
  以 ``wizard_state`` 推断为基础，再用项目旧专用列
  （template_type / report_scope / scenario）覆盖，三个维度均缺失或非法时
  回退到默认值 ``{entity_type: "soe", scope: "standalone", stage: "normal"}``
  （满足需求 6.3）。复用服务的派生逻辑可避免逻辑漂移。

**幂等性**（需求 6.1）：
  已有非空 ``applicable_standard_v2`` 的项目会被**跳过**（不覆盖用户/向导
  已写入的权威值）。多次执行安全，且不影响已正确填充的项目。

**完成态**（需求 6.2）：
  迁移完成后，所有现有项目（含软删除）的 ``applicable_standard_v2`` 均非空。

**用法**::

    python backend/scripts/migrate/migrate_applicable_standard.py [--dry-run]

  ``--dry-run``：只打印将要写入的内容，不提交任何变更。

**回滚**::

    UPDATE projects SET applicable_standard_v2 = NULL;
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# 确保 backend 包可导入（本文件位于 backend/scripts/migrate/ 下，
# parent.parent.parent 即 backend/）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import sqlalchemy as sa  # noqa: E402

# 导入全部 ORM 模型注册 metadata，确保 flush 时能解析
# projects.accounting_standard_id -> accounting_standards 等外键
# （extension_models 含 AccountingStandard，未被 app.models.__init__ 聚合，需显式导入）
import app.models  # noqa: E402,F401
import app.models.extension_models  # noqa: E402,F401
from app.core.database import async_session  # noqa: E402
from app.models.core import Project  # noqa: E402
from app.services.standard_unification_service import (  # noqa: E402
    StandardUnificationService,
)


async def migrate(dry_run: bool = False) -> dict[str, int]:
    """对所有项目回填 applicable_standard_v2（幂等）。

    返回统计 dict：``{"total": N, "filled": N, "skipped": N}``。
    """
    stats = {"total": 0, "filled": 0, "skipped": 0}

    async with async_session() as session:
        svc = StandardUnificationService(session)

        # 查所有项目（含软删除，确保每个项目都拿到值，满足需求 6.2）
        result = await session.execute(sa.select(Project))
        projects = list(result.scalars().all())
        stats["total"] = len(projects)
        print(f"Projects found: {stats['total']}")

        if not projects:
            print("Nothing to do.")
            return stats

        preview: list[tuple[str, dict]] = []

        for project in projects:
            existing = project.applicable_standard_v2
            # 幂等：已有非空 dict → 跳过，不覆盖（需求 6.1）
            if isinstance(existing, dict) and existing:
                stats["skipped"] += 1
                continue

            # 从旧字段 + wizard_state 推断（无法推断时服务内部回退默认值，需求 6.3）
            derived = svc._derive_from_project(project)
            project.applicable_standard_v2 = dict(derived)
            stats["filled"] += 1
            preview.append((str(project.id), derived))

        if dry_run:
            print("\n[DRY RUN] No changes written. Would fill:")
            for pid, derived in preview[:20]:
                print(f"  {pid[:8]}... -> {derived}")
            if len(preview) > 20:
                print(f"  ... and {len(preview) - 20} more")
        else:
            await session.commit()
            print(f"\nBackfill complete: {stats['filled']} projects updated.")

    print(
        f"Summary: total={stats['total']} / "
        f"filled={stats['filled']} / skipped={stats['skipped']}"
    )
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(
        description="回填 projects.applicable_standard_v2（多准则状态统一，幂等）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只打印将要写入的内容，不提交任何变更",
    )
    args = parser.parse_args()
    asyncio.run(migrate(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
