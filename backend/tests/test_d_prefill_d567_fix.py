"""测试 D5/D6/D7 三联审定表 prefill 取数科目修正后状态。

Validates: Requirements F1（D 销售循环 spec — D5/D6/D7 wp_code 错位修正）

修正前（错误状态）：
  - wp_code='D5' / wp_name='合同资产审定表' / formula 含 '1141'   ← 错（D5 应该是应收款项融资）
  - wp_code='D6' / wp_name='合同负债审定表' / formula 含 '2205'   ← 错
  - wp_code='D7' / wp_name='应收款项融资审定表' / formula 含 '1124' ← 错

修正后（业务对齐）：
  - wp_code='D5' / wp_name='应收款项融资审定表' / formula 含 '1124'
  - wp_code='D6' / wp_name='合同资产审定表' / formula 含 '1141'
  - wp_code='D7' / wp_name='合同负债审定表' / formula 含 '2205'

注：每个 wp_code 在文件中还有第二段（分析程序，cells_count=2）和 D5 还有第三段
（应收款项融资子科目明细），本测试只针对第一段"审定表" entry 验证。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

# 项目根 → backend/data/prefill_formula_mapping.json
_REPO_ROOT = Path(__file__).resolve().parents[2]
PREFILL_FILE = _REPO_ROOT / "backend" / "data" / "prefill_formula_mapping.json"

# 提取 =TB('科目编码',...) 中的科目编码
TB_ACCOUNT_PATTERN = re.compile(r"=TB\('(\d+)'")

# F1 修正后的业务对齐预期
EXPECTED_AUDITED_MAPPING = {
    "D5": {"wp_name_keyword": "应收款项融资", "account_code": "1124"},
    "D6": {"wp_name_keyword": "合同资产", "account_code": "1141"},
    "D7": {"wp_name_keyword": "合同负债", "account_code": "2205"},
}


@pytest.fixture(scope="module")
def prefill_data() -> dict:
    """加载 prefill_formula_mapping.json 一次，给所有测试共用。"""
    assert PREFILL_FILE.exists(), f"prefill 配置文件不存在: {PREFILL_FILE}"
    with PREFILL_FILE.open(encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def all_entries(prefill_data: dict) -> list[dict]:
    """提取 mappings 数组下所有 entry。"""
    entries = prefill_data.get("mappings") or prefill_data.get("entries") or []
    assert entries, f"prefill 配置 mappings/entries 为空: {PREFILL_FILE}"
    return entries


def _extract_audited_entries(entries: list[dict]) -> dict[str, dict]:
    """筛选 wp_code∈{D5,D6,D7} 且 wp_name 含 '审定' 的 entry。

    返回 {wp_code: entry} 映射；同 wp_code 多条则报错。
    """
    result: dict[str, dict] = {}
    for entry in entries:
        wp_code = entry.get("wp_code")
        wp_name = entry.get("wp_name", "")
        if wp_code in {"D5", "D6", "D7"} and "审定" in wp_name:
            assert wp_code not in result, (
                f"wp_code={wp_code} 且 wp_name 含'审定' 的 entry 重复出现："
                f"已有 wp_name='{result[wp_code]['wp_name']}', 又出现 wp_name='{wp_name}'"
            )
            result[wp_code] = entry
    return result


def _collect_tb_accounts(entry: dict) -> set[str]:
    """提取 entry.cells 所有 formula 中 TB() 的科目编码集合。"""
    accounts: set[str] = set()
    for cell in entry.get("cells", []):
        formula = cell.get("formula", "")
        accounts.update(TB_ACCOUNT_PATTERN.findall(formula))
    return accounts


# -----------------------------------------------------------------------------
# Acceptance #1: 审定表 entry 三连科目集合 = {1124, 1141, 2205} 不重不漏
# -----------------------------------------------------------------------------


def test_d567_audited_entries_aligned(all_entries: list[dict]) -> None:
    """D5/D6/D7 审定表 entry 各 1 条，三者 TB 取数科目集合 = {1124, 1141, 2205}。"""
    audited = _extract_audited_entries(all_entries)

    # 各 wp_code 各 1 条
    assert set(audited.keys()) == {"D5", "D6", "D7"}, (
        f"D5/D6/D7 审定表 entry 缺失或多出，实际找到 wp_code: {sorted(audited.keys())}"
    )

    # 收集三个 entry 的全部 TB 科目
    union_accounts: set[str] = set()
    for wp_code, entry in audited.items():
        accounts = _collect_tb_accounts(entry)
        assert accounts, f"wp_code={wp_code} 的 cells 中未找到 =TB() 公式"
        union_accounts.update(accounts)

    # 不重不漏：三者并集恰为 {1124, 1141, 2205}
    assert union_accounts == {"1124", "1141", "2205"}, (
        f"D5/D6/D7 审定表 TB 科目集合不等于 {{1124,1141,2205}}，实际为 {sorted(union_accounts)}"
    )


# -----------------------------------------------------------------------------
# Acceptance #2: 单个 wp_code 与科目语义对应正确
# -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "wp_code,expected_account,expected_name_keyword",
    [
        ("D5", "1124", "应收款项融资"),
        ("D6", "1141", "合同资产"),
        ("D7", "2205", "合同负债"),
    ],
)
def test_d567_wp_code_to_account_mapping(
    all_entries: list[dict],
    wp_code: str,
    expected_account: str,
    expected_name_keyword: str,
) -> None:
    """语义验证：wp_code → wp_name 关键字 → 主科目编码 三者一致。"""
    audited = _extract_audited_entries(all_entries)
    entry = audited.get(wp_code)
    assert entry is not None, f"未找到 wp_code={wp_code} 的审定表 entry"

    # wp_name 关键字
    assert expected_name_keyword in entry["wp_name"], (
        f"wp_code={wp_code} 的 wp_name='{entry['wp_name']}' 应含关键字 '{expected_name_keyword}'"
    )

    # 主科目编码出现在 formula
    accounts = _collect_tb_accounts(entry)
    assert expected_account in accounts, (
        f"wp_code={wp_code} ({expected_name_keyword}) 的 formula 应含科目 {expected_account}，"
        f"实际 TB 科目集合: {sorted(accounts)}"
    )

    # 该 entry 不应混入其他两个 wp_code 的主科目
    other_accounts = {"1124", "1141", "2205"} - {expected_account}
    polluted = accounts & other_accounts
    assert not polluted, (
        f"wp_code={wp_code} ({expected_name_keyword}) 的 formula 串入了其他底稿主科目 {polluted}，"
        f"业务错位未修复"
    )


# -----------------------------------------------------------------------------
# Acceptance #3: 第二段分析程序 + 第三段子明细 wp_code/wp_name 业务一致
# -----------------------------------------------------------------------------


def test_d567_no_other_d_entries_corrupted(all_entries: list[dict]) -> None:
    """非审定表的 D5/D6/D7 衍生 entry（分析程序 / 子明细）应保持业务一致。

    - 分析程序：cells_count==2 且 wp_name 含 "分析程序"，三条业务对齐：
        D5 → 应收款项融资分析程序 / D6 → 合同资产分析程序 / D7 → 合同负债分析程序
    - 子明细：D5 → 应收款项融资子科目明细（cells_count==2）
    """
    # 分析程序 3 条
    analysis_expected = {
        "D5": "应收款项融资分析程序",
        "D6": "合同资产分析程序",
        "D7": "合同负债分析程序",
    }
    found_analysis: dict[str, dict] = {}
    found_subdetail: dict[str, dict] = {}

    for entry in all_entries:
        wp_code = entry.get("wp_code")
        wp_name = entry.get("wp_name", "")
        if wp_code not in {"D5", "D6", "D7"}:
            continue
        cells_count = len(entry.get("cells", []))

        if "分析程序" in wp_name:
            assert cells_count == 2, (
                f"wp_code={wp_code} 分析程序 entry 的 cells_count 应为 2，实际 {cells_count}"
            )
            assert wp_code not in found_analysis, (
                f"wp_code={wp_code} 分析程序 entry 重复"
            )
            found_analysis[wp_code] = entry
        elif "子科目明细" in wp_name:
            assert cells_count == 2, (
                f"wp_code={wp_code} 子明细 entry 的 cells_count 应为 2，实际 {cells_count}"
            )
            assert wp_code not in found_subdetail, (
                f"wp_code={wp_code} 子明细 entry 重复"
            )
            found_subdetail[wp_code] = entry

    # 分析程序三条齐全且 wp_name 业务对齐
    assert set(found_analysis.keys()) == {"D5", "D6", "D7"}, (
        f"分析程序 entry 缺失，找到的 wp_code: {sorted(found_analysis.keys())}"
    )
    for wp_code, expected_name in analysis_expected.items():
        actual_name = found_analysis[wp_code]["wp_name"]
        assert actual_name == expected_name, (
            f"wp_code={wp_code} 分析程序 wp_name 业务错位：期望 '{expected_name}'，实际 '{actual_name}'"
        )

    # 子明细 D5-1 存在且 wp_name 业务对齐
    assert "D5" in found_subdetail, "D5 子科目明细 entry 缺失"
    assert found_subdetail["D5"]["wp_name"] == "应收款项融资子科目明细", (
        f"D5 子明细 wp_name 业务错位：实际 '{found_subdetail['D5']['wp_name']}'"
    )
    # D6/D7 在第三段无对应子明细（业务设计如此），不应出现
    assert "D6" not in found_subdetail, "D6 不应出现在子明细段"
    assert "D7" not in found_subdetail, "D7 不应出现在子明细段"
