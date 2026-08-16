"""填充 report_config 表的 formula 字段（**CLI 薄壳**，逻辑全在 service）。

用法（从 backend/ 目录执行）::

    python scripts/fix/fill_report_formulas.py [--dry-run] [--standard soe|listed|all]

--------------------------------------------------------------------------------
🔴🔴 2026-08-05 改为薄壳：删掉本文件自带的 357 行策略实现与三张名索引表副本
--------------------------------------------------------------------------------

**背景**：归档 spec `_archive/05-business-features/e2e-business-flow/` 的 Task 9 已把
本脚本的核心逻辑封装成 :meth:`ReportFormulaService.fill_all_formulas`，其 design.md
明确写「保留作 CLI 入口，**内部调 service**」—— 但那次重构只做了前半截：
service 建好了，脚本却仍是一份**独立副本**，从未改成委托。

于是本文件长期是 `report_config.formula` 的**第三条写入路径**，且带着 service 已修掉的错码。
2026-08-05 spec `report-config-account-code-integrity` Task 7 复盘实测：

* `专项储备` 两处仍是 `TB('4103')` —— 4103 实为**本年利润**（正解 4301）；
* `开发支出` 仍是 `TB('1703')` —— 1703 实为**无形资产减值准备**（正解 1704）；
* `一年内到期的非流动资产` → `1503`（可供出售金融资产）与 `其他流动负债` → `2301`
  （码与名全库均零命中）两条**仍作为键存在**，而 V138 已把对应报表行置 NULL；
* **完全没有派生行拦截门** —— 跑一次就把 V138 置 NULL 的行全填回错码。

表对比进一步证明它只是 service 的旧快照：
``BS_SPECIAL(49) ⊂ _BS_SPECIAL(71)``，且脚本"独有"的那 2 条恰恰是 Task 7 从 service
删掉的两个派生行；``IS_SPECIAL`` / ``EQ_SPECIAL`` 是 service 对应表的真子集。

**处置**：改薄壳而非删除 —— CLI 的 `--dry-run` / `--standard` 有运维价值，
但**判据必须单一真源**。`--dry-run` 现在靠事务回滚实现（比再抄一遍策略可靠：
它验的是"真跑一遍会写什么"，而不是"另一份实现认为会写什么"）。

🔴 **不要再往本文件加策略或科目码**。名索引表、镜像修正、派生行拦截一律改
:mod:`app.services.report_formula_service` 与
:mod:`app.services.four_table.report_config_account_names`；
守卫 ``backend/tests/four_table/test_report_formula_filler_mirror.py`` 会拦住副本回归。
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.core.database import async_session  # noqa: E402
from app.services.report_formula_service import report_formula_service  # noqa: E402

_STANDARD_CHOICES = [
    "all",
    "soe",
    "listed",
    "soe_consolidated",
    "soe_standalone",
    "listed_consolidated",
    "listed_standalone",
]


async def fill_formulas(dry_run: bool = False, standard_filter: str = "all") -> dict:
    """委托 service 填充；`dry_run` 用回滚实现（不提交）。

    Returns:
        service 返回的统计 dict（``total`` / ``updated`` / ``skipped`` / ``no_formula``）。
    """
    async with async_session() as db:
        stats = await report_formula_service.fill_all_formulas(db, standard=standard_filter)

        if dry_run:
            await db.rollback()
            print("\n⚠️  DRY RUN 模式，已回滚，未写入数据库")
        else:
            await db.commit()
            print("\n✅ 已提交到数据库")

    print("=" * 60)
    print(
        "统计: 总={total} 填充={updated} 跳过={skipped} 无公式={no_formula}".format(
            total=stats.get("total", 0),
            updated=stats.get("updated", 0),
            skipped=stats.get("skipped", 0),
            no_formula=stats.get("no_formula", 0),
        )
    )
    if "coverage_pct" in stats:
        print(f"覆盖率: {stats['coverage_pct']}")
    print("=" * 60)
    print(
        "判据真源：app/services/report_formula_service.py"
        " + app/services/four_table/report_config_account_names.py"
    )
    return stats


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="填充 report_config formula（薄壳，逻辑在 service）")
    parser.add_argument("--dry-run", action="store_true", help="只跑不写（事务回滚）")
    parser.add_argument("--standard", default="all", choices=_STANDARD_CHOICES)
    args = parser.parse_args()
    asyncio.run(fill_formulas(dry_run=args.dry_run, standard_filter=args.standard))
