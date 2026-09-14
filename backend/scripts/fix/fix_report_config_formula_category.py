"""回填 ``report_config.formula_category``（有公式但无分类的行）。

用法（从仓库根或 backend/ 执行均可）::

    python backend/scripts/fix/fix_report_config_formula_category.py            # 只看计划（默认 dry-run）
    python backend/scripts/fix/fix_report_config_formula_category.py --apply    # 真写库
    python backend/scripts/fix/fix_report_config_formula_category.py --standard soe_standalone --apply

--------------------------------------------------------------------------------
为什么需要
--------------------------------------------------------------------------------
公式看板里大量行显示「未分类」不是渲染 bug，是种子数据本身 ``formula_category``
为空。实测（2026-09-11，模板级口径，不含 ``project:{id}``）：

===================  ==========  ==============
applicable_standard  有公式行数  缺分类行数
===================  ==========  ==============
listed_consolidated  118         0
listed_standalone    118         0
soe_consolidated     159         3
soe_standalone       183         38
===================  ==========  ==============

--------------------------------------------------------------------------------
影响面（**默认 dry-run 的原因**）
--------------------------------------------------------------------------------
``report_config`` 是**模板级共享**数据（唯一键不含 project_id），改它波及所有使用
同一适用准则的项目；而且 ``formula_category`` 不只是展示字段 —— 「应用自动运算」
按 ``auto_calc`` 挑行执行。所以：

* 判据只用**公式形态**推导，且判不准就留空（见 ``derive_formula_category``）；
* 默认 dry-run，只打印计划；``--apply`` 才写；
* 幂等：只碰「有公式且分类为空」的行，重复执行第二次 filled=0。

薄壳约定：分类判据的单一真源在
:func:`app.services.report_config_service.derive_formula_category`，
本脚本不得自带第二份规则。
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.core.database import async_session  # noqa: E402
from app.services.report_config_service import ReportConfigService  # noqa: E402


async def _run(standard: str | None, apply: bool, include_project: bool) -> int:
    async with async_session() as session:
        svc = ReportConfigService(session)
        result = await svc.backfill_formula_categories(
            applicable_standard=standard,
            include_project_scoped=include_project,
        )
        if apply:
            await session.commit()
            action = "已写入"
        else:
            await session.rollback()
            action = "计划（未写入，加 --apply 才生效）"

        print(f"{action}：扫描 {result['scanned']} 行，可回填 {result['filled']} 行，"
              f"判不准保持为空 {result['undecided']} 行")
        for category, count in sorted(result["by_category"].items()):
            print(f"  - {category}: {count} 行")
        if not apply and result["filled"]:
            print("\n注意：report_config 是模板级共享数据，写入会影响同准则的所有项目。")
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="回填 report_config.formula_category")
    parser.add_argument(
        "--standard",
        default=None,
        help="限定 applicable_standard（如 soe_standalone）；省略则处理全部非项目级口径",
    )
    parser.add_argument("--apply", action="store_true", help="真正写库（默认只打印计划）")
    parser.add_argument(
        "--include-project-scoped",
        action="store_true",
        help="一并处理 project:{id} 项目级行（默认跳过）",
    )
    args = parser.parse_args()
    return asyncio.run(_run(args.standard, args.apply, args.include_project_scoped))


if __name__ == "__main__":
    raise SystemExit(main())
