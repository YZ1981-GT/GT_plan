"""验证 report_config_seed.json 的行次覆盖率（CI 卡点）。

确保 soe/listed × consolidated/standalone 四组合 standard 对四表
（balance_sheet / income_statement / cash_flow_statement / equity_statement）
行次无缺漏：每个组合必须覆盖全部四张财务报表，且每张表的 row_code 序列连续无空洞。

enterprise 标准为兜底/catch-all，不纳入严格覆盖率校验。

复用 report-module-enhancement validate_formula_coverage 模式 + CI 卡点。

用法：
    python scripts/check/validate_report_config_coverage.py [--verbose]

运行环境：从 backend/ 目录执行，或指定 cwd=backend
退出码：0=通过，1=覆盖率缺漏
"""

import argparse
import json
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

# 四组合 standard（排除 enterprise 兜底）
REQUIRED_STANDARDS = [
    "soe_consolidated",
    "soe_standalone",
    "listed_consolidated",
    "listed_standalone",
]

# 四张核心财务报表（对应 FinancialReportType 枚举前四项）
REQUIRED_REPORT_TYPES = [
    "balance_sheet",
    "income_statement",
    "cash_flow_statement",
    "equity_statement",
]

# seed 文件路径：脚本在 backend/scripts/check/，seed 在 backend/data/
SEED_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "report_config_seed.json"


# ---------------------------------------------------------------------------
# 核心校验逻辑
# ---------------------------------------------------------------------------


def load_seed_data(seed_path: Path) -> list[dict]:
    """加载 report_config_seed.json"""
    if not seed_path.exists():
        # 尝试从 backend/ cwd 相对路径
        alt_path = Path("data/report_config_seed.json")
        if alt_path.exists():
            seed_path = alt_path
        else:
            print(f"ERROR: seed 文件不存在: {seed_path}", file=sys.stderr)
            sys.exit(2)
    with open(seed_path, "r", encoding="utf-8") as f:
        return json.load(f)


def validate_coverage(seed_data: list[dict], verbose: bool = False) -> dict:
    """校验四组合 × 四表覆盖率。

    Returns:
        {
            "gaps": [
                {"standard": str, "report_type": str, "issue": str, "details": list},
                ...
            ],
            "summary": {
                "total_combinations": int,
                "covered_combinations": int,
                "total_rows_checked": int,
            }
        }
    """
    # 构建索引: (standard, report_type) -> [row_codes]
    index: dict[tuple[str, str], list[dict]] = {}
    for section in seed_data:
        std = section["applicable_standard"]
        rt = section["report_type"]
        # 跳过 enterprise 兜底
        if "enterprise" in std:
            continue
        index[(std, rt)] = section["rows"]

    gaps: list[dict] = []
    total_combinations = len(REQUIRED_STANDARDS) * len(REQUIRED_REPORT_TYPES)
    covered_combinations = 0
    total_rows_checked = 0

    for std in REQUIRED_STANDARDS:
        for rt in REQUIRED_REPORT_TYPES:
            key = (std, rt)
            rows = index.get(key)

            if rows is None:
                # 整个组合缺失
                gaps.append({
                    "standard": std,
                    "report_type": rt,
                    "issue": "missing_combination",
                    "details": [f"组合 {std} × {rt} 在 seed 中完全缺失"],
                })
                continue

            covered_combinations += 1
            total_rows_checked += len(rows)

            # 校验 1: row_code 不为空
            empty_codes = [
                r for r in rows
                if not r.get("row_code") or not r["row_code"].strip()
            ]
            if empty_codes:
                gaps.append({
                    "standard": std,
                    "report_type": rt,
                    "issue": "empty_row_code",
                    "details": [
                        f"第 {r.get('row_number', '?')} 行 row_code 为空"
                        for r in empty_codes
                    ],
                })

            # 校验 2: row_number 连续性（1-based，无跳号）
            row_numbers = sorted(r["row_number"] for r in rows)
            expected = list(range(1, len(rows) + 1))
            if row_numbers != expected:
                missing_nums = set(expected) - set(row_numbers)
                duplicate_nums = [
                    n for n in row_numbers if row_numbers.count(n) > 1
                ]
                details = []
                if missing_nums:
                    details.append(
                        f"缺失行号: {sorted(missing_nums)}"
                    )
                if duplicate_nums:
                    details.append(
                        f"重复行号: {sorted(set(duplicate_nums))}"
                    )
                if not details:
                    details.append(
                        f"行号不连续: 期望 1~{len(rows)}，实际 {row_numbers[:5]}...{row_numbers[-3:]}"
                    )
                gaps.append({
                    "standard": std,
                    "report_type": rt,
                    "issue": "row_number_discontinuity",
                    "details": details,
                })

            # 校验 3: row_code 唯一性（同一组合内不重复）
            codes = [r["row_code"] for r in rows]
            seen = set()
            duplicates = set()
            for c in codes:
                if c in seen:
                    duplicates.add(c)
                seen.add(c)
            if duplicates:
                gaps.append({
                    "standard": std,
                    "report_type": rt,
                    "issue": "duplicate_row_code",
                    "details": [f"重复 row_code: {sorted(duplicates)}"],
                })

    return {
        "gaps": gaps,
        "summary": {
            "total_combinations": total_combinations,
            "covered_combinations": covered_combinations,
            "total_rows_checked": total_rows_checked,
        },
    }


# ---------------------------------------------------------------------------
# 输出 + 主入口
# ---------------------------------------------------------------------------


def print_results(result: dict, verbose: bool) -> bool:
    """打印校验结果，返回是否全部通过。"""
    gaps = result["gaps"]
    summary = result["summary"]

    print("=" * 60)
    print("报表配置覆盖率校验 (report_config_seed.json)")
    print("=" * 60)
    print(f"  校验范围: {REQUIRED_STANDARDS}")
    print(f"  报表类型: {REQUIRED_REPORT_TYPES}")
    print(f"  组合覆盖: {summary['covered_combinations']}/{summary['total_combinations']}")
    print(f"  总行数:   {summary['total_rows_checked']}")
    print()

    if not gaps:
        print("✅ 四组合 × 四表行次覆盖完整，无缺漏")
        return True

    print(f"❌ 发现 {len(gaps)} 处覆盖缺漏：")
    print()

    for gap in gaps:
        std = gap["standard"]
        rt = gap["report_type"]
        issue = gap["issue"]
        print(f"  ❌ [{std}] × [{rt}] — {issue}")
        if verbose:
            for detail in gap["details"]:
                print(f"      {detail}")

    return False


def main():
    parser = argparse.ArgumentParser(
        description="验证 report_config_seed.json 四组合×四表行次覆盖率（CI 卡点）"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="输出缺漏详情",
    )
    parser.add_argument(
        "--seed-file",
        type=str,
        default=None,
        help="指定 seed 文件路径（默认自动定位 backend/data/report_config_seed.json）",
    )
    args = parser.parse_args()

    # 定位 seed 文件
    if args.seed_file:
        seed_path = Path(args.seed_file)
    else:
        seed_path = SEED_FILE

    seed_data = load_seed_data(seed_path)
    result = validate_coverage(seed_data, verbose=args.verbose)
    all_pass = print_results(result, verbose=args.verbose)

    if not all_pass:
        print(f"\n❌ 覆盖率校验失败，退出码 1（CI 卡点）")
        sys.exit(1)
    else:
        print(f"\n✅ 覆盖率校验通过")
        sys.exit(0)


if __name__ == "__main__":
    main()
