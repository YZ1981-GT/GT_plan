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

    🔴 2026-08-01 修正（spec d-cycle-extraction-chain-completion Wave 5）：原断言
    强制要求 D5/D6「分析程序」与 D5「子科目明细」entry 存在，但 openpyxl 直读源模板
    实证——`D5 应收款项融资.xlsx` 与 `D6 合同资产.xlsx` 都**没有独立的分析程序 sheet**
    （D5 sheets = 底稿目录/D5A/审定表D5/附注×2/明细表D5-2/调整分录D5-3/公允价值测算D5-4；
    D6 sheets 同理只有明细表/减值明细/调整分录/关联方/检查表/测算表，无「分析程序」）；
    D5 的「票据类/应收账款类子科目」（112401/112402）在审定表/明细表均无对应子科目
    编码结构。原条目的 `sheet` 字段全部是虚构值（`分析程序D5-3`/`分析程序D6-3`/
    `审定表D5-1`，源模板均不存在），且与 D7 的真实 sheet 名环形错位
    （D5→抄D7、D6→抄D5、D7→抄D6 的 sheet 名与 `PREV()` wp_code）。

    按 Requirement 7.1（sheet 名须与源模板真实 sheet 名逐字一致）与「宁缺勿造」原则，
    已删除这些虚构条目而非修正到另一个虚构值。D7 的分析程序 entry（`合同负债分析表D7-4`，
    源模板真实存在）保留且已核实 sheet 名。
    """
    for entry in all_entries:
        wp_code = entry.get("wp_code")
        wp_name = entry.get("wp_name", "")
        sheet = entry.get("sheet", "")
        if wp_code not in {"D5", "D6", "D7"}:
            continue
        # D5/D6 不应再有「分析程序」/「子科目明细」条目（源模板无对应 sheet）
        if wp_code in {"D5", "D6"}:
            assert "分析程序" not in wp_name, (
                f"wp_code={wp_code} 不应有分析程序 entry（源模板无此 sheet），"
                f"发现 wp_name='{wp_name}' sheet='{sheet}'"
            )
        if wp_code == "D5":
            assert "子科目明细" not in wp_name, (
                f"D5 不应有子科目明细 entry（112401/112402 无对应实现），"
                f"发现 sheet='{sheet}'"
            )
        # D7 的分析程序条目若存在，sheet 名必须是源模板真实值
        if wp_code == "D7" and "分析程序" in wp_name:
            assert sheet == "合同负债分析表D7-4", (
                f"D7 分析程序 sheet 名错位：实际 '{sheet}'（源模板真实 sheet 名为 "
                f"合同负债分析表D7-4）"
            )


def test_d567_sheet_names_match_source_template(all_entries: list[dict]) -> None:
    """D5/D6/D7 全部条目的 `sheet` 字段必须与源模板真实 sheet 名逐字一致。

    补的守卫：原 `test_d567_audited_entries_aligned` 只校验 wp_code/wp_name/科目码
    三元组，**从未读过 `sheet` 字段** —— 这正是三循环环形错位（D5→抄D7 的 sheet 名、
    D6→抄D5 的、D7→抄D6 的）能存在的根因，靠 openpyxl 直读源 xlsx 交叉锁死。
    """
    openpyxl = pytest.importorskip("openpyxl")
    root = _REPO_ROOT / "backend" / "wp_templates" / "D"
    source_sheets = {
        "D5": set(openpyxl.load_workbook(root / "D5 应收款项融资.xlsx", read_only=True).sheetnames),
        "D6": set(openpyxl.load_workbook(root / "D6 合同资产.xlsx", read_only=True).sheetnames),
        "D7": set(openpyxl.load_workbook(root / "D7 合同负债.xlsx", read_only=True).sheetnames),
    }
    # 反向自检：源模板真的读到了内容（防止路径错导致空集合让断言恒真）
    for wp_code, sheets in source_sheets.items():
        assert len(sheets) > 3, f"{wp_code} 源模板 sheet 集合过小：{sheets}"

    checked = 0
    for entry in all_entries:
        wp_code = entry.get("wp_code")
        if wp_code not in source_sheets:
            continue
        sheet = str(entry.get("sheet", ""))
        assert sheet in source_sheets[wp_code], (
            f"wp_code={wp_code} 的 sheet「{sheet}」不在源模板真实 sheet 集合中"
        )
        checked += 1
    assert checked >= 3, "反向自检：至少应检查到 D5/D6/D7 各一条 entry"
