"""半自动推断 functional_type — sheet 名关键词→functional_type 映射

根据 sheet_name 和 wp_code 关键词规则，推断每行 workpaper_sheet_classification
的 functional_type 值。

规则优先级：
1. wp_code 前缀精确匹配（如 D2-8 → aging）
2. sheet_name 关键词匹配（如 "账龄" → aging）
3. class_code 推断（如 e-control-test → control_test）

用法：
    # 预览（不写库）
    python backend/scripts/seed/infer_functional_type.py --dry-run

    # 执行写库
    python backend/scripts/seed/infer_functional_type.py

    # 仅处理特定循环
    python backend/scripts/seed/infer_functional_type.py --cycle D
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# 确保 backend 在 sys.path
_backend_dir = Path(__file__).resolve().parent.parent.parent
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))


# ─── 关键词→functional_type 映射规则 ─────────────────────────────────────────

# wp_code 精确/前缀映射（优先级最高）
WP_CODE_RULES: list[tuple[re.Pattern, str]] = [
    # 截止测试
    (re.compile(r"^D2-8$"), "cutoff"),
    (re.compile(r"^D4-8$"), "cutoff"),
    # 账龄分析
    (re.compile(r"^D2-13$"), "aging"),
    (re.compile(r"^D4-13$"), "aging"),
    # 抽凭
    (re.compile(r"^D2-9$"), "sampling"),
    (re.compile(r"^D4-9$"), "sampling"),
    (re.compile(r"^D2-10$"), "sampling"),
    (re.compile(r"^D4-10$"), "sampling"),
    (re.compile(r"^F2-9$"), "sampling"),
    (re.compile(r"^F2-10$"), "sampling"),
    # 月度分析
    (re.compile(r"^D2-3$"), "monthly_analysis"),
    (re.compile(r"^D4-3$"), "monthly_analysis"),
    (re.compile(r"^F2-3$"), "monthly_analysis"),
    # 合同台账
    (re.compile(r"^D2-14$"), "contract_ledger"),
    # 函证
    (re.compile(r"^D2-11$"), "confirmation"),
    (re.compile(r"^D2-12$"), "confirmation"),
    (re.compile(r"^D4-11$"), "confirmation"),
    (re.compile(r"^D4-12$"), "confirmation"),
    (re.compile(r"^E1-3$"), "confirmation"),
    # 减值测试
    (re.compile(r"^G\d+-\d+$"), "impairment"),
    # 折旧/摊销
    (re.compile(r"^H\d+-\d+$"), "depreciation"),
    (re.compile(r"^I\d+-\d+$"), "amortization"),
]

# sheet_name 关键词映射（优先级次之）
SHEET_NAME_RULES: list[tuple[re.Pattern, str]] = [
    # 截止测试
    (re.compile(r"截止|cutoff", re.IGNORECASE), "cutoff"),
    # 账龄分析
    (re.compile(r"账龄|aging|帐龄", re.IGNORECASE), "aging"),
    # 抽凭/抽样
    (re.compile(r"抽凭|抽样|sampling|样本", re.IGNORECASE), "sampling"),
    # 月度分析
    (re.compile(r"月度|月份|monthly|逐月|按月", re.IGNORECASE), "monthly_analysis"),
    # 合同台账
    (re.compile(r"合同台账|合同清单|contract", re.IGNORECASE), "contract_ledger"),
    # 函证
    (re.compile(r"函证|询证|confirmation", re.IGNORECASE), "confirmation"),
    # 对账/调节
    (re.compile(r"调节表|对账|reconcil", re.IGNORECASE), "reconciliation"),
    # 明细表
    (re.compile(r"明细表|明细清单|detail", re.IGNORECASE), "detail_table"),
    # 减值
    (re.compile(r"减值|impairment|坏账", re.IGNORECASE), "impairment"),
    # 折旧
    (re.compile(r"折旧|depreciation", re.IGNORECASE), "depreciation"),
    # 摊销
    (re.compile(r"摊销|amortization", re.IGNORECASE), "amortization"),
]

# class_code → functional_type 兜底映射
CLASS_CODE_RULES: dict[str, str] = {
    "e-control-test": "control_test",
    "c-note-table": "disclosure",
    "a-program-console": "program_console",
    "b-index": "index",
    "h-static-doc": "static_doc",
}


def infer_functional_type(
    wp_code: str,
    sheet_name: str,
    class_code: str | None,
) -> str | None:
    """推断单行的 functional_type

    Returns:
        functional_type 字符串，或 None（无法推断）
    """
    # 1. wp_code 精确匹配
    for pattern, ft in WP_CODE_RULES:
        if pattern.match(wp_code):
            return ft

    # 2. sheet_name 关键词
    for pattern, ft in SHEET_NAME_RULES:
        if pattern.search(sheet_name):
            return ft

    # 3. class_code 兜底
    if class_code and class_code in CLASS_CODE_RULES:
        return CLASS_CODE_RULES[class_code]

    return None


def main():
    parser = argparse.ArgumentParser(
        description="半自动推断 functional_type 并写入 workpaper_sheet_classification"
    )
    parser.add_argument("--dry-run", action="store_true", help="仅预览不写库")
    parser.add_argument("--cycle", type=str, default=None, help="仅处理特定循环前缀（如 D）")
    args = parser.parse_args()

    import asyncio
    asyncio.run(_run(args.dry_run, args.cycle))


async def _run(dry_run: bool, cycle_filter: str | None):
    from sqlalchemy import text
    from app.core.database import engine as async_engine

    async with async_engine.begin() as conn:
        # 查询所有行
        where_clause = ""
        if cycle_filter:
            where_clause = f"WHERE wp_code LIKE '{cycle_filter}%'"

        result = await conn.execute(text(
            f"SELECT id, wp_code, sheet_name, class_code, functional_type "
            f"FROM workpaper_sheet_classification {where_clause} "
            f"ORDER BY wp_code, sheet_name"
        ))
        rows = result.fetchall()

        updated = 0
        skipped = 0
        stats: dict[str, int] = {}

        for row in rows:
            row_id, wp_code, sheet_name, class_code, existing_ft = row

            # 跳过已有值的行
            if existing_ft:
                skipped += 1
                continue

            ft = infer_functional_type(wp_code, sheet_name, class_code)
            if ft:
                stats[ft] = stats.get(ft, 0) + 1
                if not dry_run:
                    await conn.execute(text(
                        "UPDATE workpaper_sheet_classification "
                        "SET functional_type = :ft WHERE id = :id"
                    ), {"ft": ft, "id": str(row_id)})
                updated += 1

        mode = "[DRY-RUN]" if dry_run else "[APPLIED]"
        print(f"\n{mode} 推断结果：")
        print(f"  总行数: {len(rows)}")
        print(f"  已有值跳过: {skipped}")
        print(f"  新推断: {updated}")
        print(f"\n  按 functional_type 分布:")
        for ft, count in sorted(stats.items(), key=lambda x: -x[1]):
            print(f"    {ft}: {count}")


if __name__ == "__main__":
    main()
