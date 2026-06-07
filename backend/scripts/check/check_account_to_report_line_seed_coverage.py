"""Seed 覆盖率检查脚本。

校验 account_to_report_line_seed.json 的四套 Seed_Dimension：
1. 校验四套 Seed_Dimension 均存在且各自完整
2. 找出 standard_account_code 重复
3. 找出不合法的 report_line_code
4. 以标准科目全集输出未覆盖科目
5. 输出 coverage baseline JSON（CI 初期只阻断新增缺口）

Requirements: 5.1, 5.2, 5.3, 5.5, 5.6, 5.7
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

REQUIRED_DIMENSIONS = ["soe_standalone", "soe_consolidated", "listed_standalone", "listed_consolidated"]

# report_line_code 合法格式：BS-NNN / PL-NNN / CF-NNN
REPORT_LINE_CODE_PATTERN = re.compile(r"^(BS|PL|CF)-\d{3}$")

# report_type 合法值
VALID_REPORT_TYPES = {"balance_sheet", "profit_loss", "cash_flow"}


# ---------------------------------------------------------------------------
# 核心检查函数
# ---------------------------------------------------------------------------


def load_seed(seed_path: str | Path) -> dict[str, Any]:
    """加载 seed JSON 文件。"""
    path = Path(seed_path)
    if not path.exists():
        raise FileNotFoundError(f"Seed file not found: {seed_path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_standard_accounts(chart_path: str | Path) -> list[dict]:
    """加载标准科目全集。"""
    path = Path(chart_path)
    if not path.exists():
        raise FileNotFoundError(f"Standard account chart not found: {chart_path}")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("accounts", [])


def check_dimensions_exist(seed_data: dict) -> list[str]:
    """校验四套 Seed_Dimension 均存在。

    Returns:
        缺失的维度列表（空列表表示全部存在）
    """
    mappings = seed_data.get("mappings", {})
    missing = [dim for dim in REQUIRED_DIMENSIONS if dim not in mappings]
    return missing


def find_duplicate_account_codes(entries: list[dict]) -> list[str]:
    """找出单个维度中 standard_account_code 重复的科目编码。

    Returns:
        重复的科目编码列表
    """
    seen: dict[str, int] = {}
    for entry in entries:
        code = entry.get("standard_account_code", "")
        seen[code] = seen.get(code, 0) + 1
    return [code for code, count in seen.items() if count > 1]


def find_invalid_report_line_codes(entries: list[dict]) -> list[str]:
    """找出不合法的 report_line_code。

    合法格式：BS-NNN / PL-NNN / CF-NNN

    Returns:
        不合法的 report_line_code 列表（去重）
    """
    invalid = set()
    for entry in entries:
        code = entry.get("report_line_code", "")
        if code and not REPORT_LINE_CODE_PATTERN.match(code):
            invalid.add(code)
    return sorted(invalid)


def find_invalid_report_types(entries: list[dict]) -> list[str]:
    """找出非法 report_type。

    Returns:
        非法 report_type 列表（去重）
    """
    invalid = set()
    for entry in entries:
        rt = entry.get("report_type", "")
        if rt and rt not in VALID_REPORT_TYPES:
            invalid.add(rt)
    return sorted(invalid)


def find_uncovered_accounts(
    entries: list[dict],
    standard_accounts: list[dict],
) -> list[dict]:
    """找出标准科目全集中未被 seed 覆盖的科目。

    Args:
        entries: seed 维度中的映射条目
        standard_accounts: 标准科目全集

    Returns:
        未覆盖的科目列表 [{code, name}]
    """
    covered_codes = {e.get("standard_account_code", "") for e in entries}
    uncovered = []
    for acc in standard_accounts:
        code = acc.get("code", "")
        if code and code not in covered_codes:
            uncovered.append({"code": code, "name": acc.get("name", "")})
    return uncovered


def check_single_dimension(
    dimension_name: str,
    entries: list[dict],
    standard_accounts: list[dict],
) -> dict:
    """对单个维度执行全部检查。

    Returns:
        检查结果 dict
    """
    return {
        "dimension": dimension_name,
        "entry_count": len(entries),
        "standard_account_count": len(standard_accounts),
        "coverage_rate": len(entries) / max(len(standard_accounts), 1),
        "duplicate_account_codes": find_duplicate_account_codes(entries),
        "invalid_report_line_codes": find_invalid_report_line_codes(entries),
        "invalid_report_types": find_invalid_report_types(entries),
        "uncovered_accounts": find_uncovered_accounts(entries, standard_accounts),
    }


def run_full_check(
    seed_path: str | Path,
    chart_path: str | Path,
) -> dict:
    """运行完整覆盖率检查。

    Returns:
        {
            "missing_dimensions": [...],
            "dimensions": {dim_name: check_result, ...},
            "overall_issues": int,
        }
    """
    seed_data = load_seed(seed_path)
    standard_accounts = load_standard_accounts(chart_path)

    missing_dims = check_dimensions_exist(seed_data)
    mappings = seed_data.get("mappings", {})

    dimensions: dict[str, dict] = {}
    total_issues = 0

    for dim in REQUIRED_DIMENSIONS:
        entries = mappings.get(dim, [])
        result = check_single_dimension(dim, entries, standard_accounts)
        dimensions[dim] = result
        total_issues += (
            len(result["duplicate_account_codes"])
            + len(result["invalid_report_line_codes"])
            + len(result["invalid_report_types"])
            + len(result["uncovered_accounts"])
        )

    return {
        "missing_dimensions": missing_dims,
        "dimensions": dimensions,
        "overall_issues": total_issues + len(missing_dims),
    }


def generate_baseline(check_result: dict) -> dict:
    """从检查结果生成 coverage baseline JSON。

    baseline 记录当前已知缺口，CI 初期只阻断新增缺口。
    """
    from datetime import date

    baseline: dict[str, Any] = {
        "generated_at": date.today().isoformat(),
        "dimensions": {},
    }

    for dim_name, dim_result in check_result.get("dimensions", {}).items():
        baseline["dimensions"][dim_name] = {
            "known_missing_accounts": [
                a["code"] for a in dim_result.get("uncovered_accounts", [])
            ],
            "known_duplicates": dim_result.get("duplicate_account_codes", []),
            "entry_count": dim_result.get("entry_count", 0),
        }

    return baseline


# ---------------------------------------------------------------------------
# CLI 入口
# ---------------------------------------------------------------------------


def main() -> None:
    """命令行入口：执行完整检查并输出结果。"""
    import sys

    base_dir = Path(__file__).resolve().parent.parent.parent  # backend/
    seed_path = base_dir / "data" / "account_to_report_line_seed.json"
    chart_path = base_dir / "data" / "standard_account_chart.json"

    result = run_full_check(seed_path, chart_path)

    print("=" * 60)
    print("Seed 覆盖率检查报告")
    print("=" * 60)

    if result["missing_dimensions"]:
        print(f"\n⚠️  缺失维度: {result['missing_dimensions']}")

    for dim_name, dim_result in result["dimensions"].items():
        print(f"\n--- {dim_name} ---")
        print(f"  映射条目数: {dim_result['entry_count']}")
        print(f"  标准科目数: {dim_result['standard_account_count']}")
        print(f"  覆盖率: {dim_result['coverage_rate']:.1%}")

        if dim_result["duplicate_account_codes"]:
            print(f"  重复科目: {dim_result['duplicate_account_codes']}")
        if dim_result["invalid_report_line_codes"]:
            print(f"  非法行次编码: {dim_result['invalid_report_line_codes']}")
        if dim_result["invalid_report_types"]:
            print(f"  非法 report_type: {dim_result['invalid_report_types']}")
        if dim_result["uncovered_accounts"]:
            print(f"  未覆盖科目 ({len(dim_result['uncovered_accounts'])}): "
                  f"{[a['code'] for a in dim_result['uncovered_accounts'][:10]]}...")

    print(f"\n总问题数: {result['overall_issues']}")

    # 生成 baseline
    baseline = generate_baseline(result)
    baseline_path = base_dir / "scripts" / "check" / "baselines" / "seed_coverage_baseline.json"
    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    with open(baseline_path, "w", encoding="utf-8") as f:
        json.dump(baseline, f, ensure_ascii=False, indent=2)
    print(f"\nBaseline 已写入: {baseline_path}")

    sys.exit(0 if result["overall_issues"] == 0 else 1)


if __name__ == "__main__":
    main()
