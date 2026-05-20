"""Property-Based Test PBT-3: D5/D6/D7 审定表 prefill 取数科目集合不重不漏

Validates: Requirements F1 (D 销售循环 spec — D5/D6/D7 wp_code 错位修正)
ADR: D1 (F1 修复方式 — 一次性脚本 + git 备份)
Property: P3 - 在 F1 修复后，D5+D6+D7 审定表 entry 的 TB 取数科目并集
            严格等于 {1124, 1141, 2205}（不重不漏）

属性测试覆盖 4 个不变量：

  P3.1 全集守恒：随机打乱 / 子排列 / 任意非破坏性变换后，
       D5/D6/D7 审定表 TB 科目并集 == {1124, 1141, 2205}
  P3.2 单 wp_code 子集：每个 wp_code 取数科目 ⊆ {1124, 1141, 2205}
  P3.3 单 wp_code 一一对应：D5→{1124}, D6→{1141}, D7→{2205}（语义对齐）
  P3.4 子集封闭：任意 D5/D6/D7 子集的取数并集 ⊆ {1124, 1141, 2205}

max_examples=50（spec design.md §四 P0 关键属性规约）
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

# 项目根 → backend/data/prefill_formula_mapping.json
_REPO_ROOT = Path(__file__).resolve().parents[2]
PREFILL_FILE = _REPO_ROOT / "backend" / "data" / "prefill_formula_mapping.json"

# 提取 =TB('科目编码', ...) 中的科目编码
TB_ACCOUNT_PATTERN = re.compile(r"=TB\('(\d+)'")

# F1 修正后业务对齐预期（design.md §一 数据流 + §二 ADR D1）
EXPECTED_ACCOUNTS = {"1124", "1141", "2205"}
EXPECTED_WP_TO_ACCOUNT = {
    "D5": "1124",  # 应收款项融资
    "D6": "1141",  # 合同资产
    "D7": "2205",  # 合同负债
}


# ---------------------------------------------------------------------------
# Fixture：模块级加载 prefill_formula_mapping.json 一次（IO 不重复）
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def audited_entries() -> dict[str, dict]:
    """加载 prefill 配置，返回 {wp_code: entry} 仅包含 D5/D6/D7 审定表 entry。"""
    assert PREFILL_FILE.exists(), f"prefill 配置文件不存在: {PREFILL_FILE}"
    with PREFILL_FILE.open(encoding="utf-8") as f:
        data = json.load(f)
    entries = data.get("mappings") or data.get("entries") or []
    result: dict[str, dict] = {}
    for entry in entries:
        wp_code = entry.get("wp_code")
        wp_name = entry.get("wp_name", "")
        if wp_code in {"D5", "D6", "D7"} and "审定" in wp_name:
            assert wp_code not in result, (
                f"同 wp_code={wp_code} 重复审定表 entry — 数据已损坏"
            )
            result[wp_code] = entry
    assert set(result.keys()) == {"D5", "D6", "D7"}, (
        f"D5/D6/D7 审定表 entry 不齐：实际 {sorted(result.keys())}"
    )
    return result


def _collect_tb_accounts(entry: dict) -> frozenset[str]:
    """提取 entry.cells 所有 formula 中 TB() 的科目编码集合。"""
    accounts: set[str] = set()
    for cell in entry.get("cells", []):
        formula = cell.get("formula", "")
        accounts.update(TB_ACCOUNT_PATTERN.findall(formula))
    return frozenset(accounts)


# ---------------------------------------------------------------------------
# P3.1 全集守恒：任意打乱 D5/D6/D7 顺序，并集都恒为 {1124, 1141, 2205}
# ---------------------------------------------------------------------------


@given(perm=st.permutations(["D5", "D6", "D7"]))
@settings(max_examples=50, deadline=None)
def test_property_p3_1_full_union_invariant(
    audited_entries: dict[str, dict],
    perm: list[str],
) -> None:
    """对任意排列 D5/D6/D7 的处理顺序，TB 取数并集恒等于 {1124, 1141, 2205}。

    属性等价于：F1 修复后取数集合不依赖于 entry 在 JSON 文件中的物理顺序。

    Validates: Property P3 (D5/D6/D7 取数科目集合不重不漏 — 全集守恒)
    """
    union: set[str] = set()
    for wp_code in perm:
        union.update(_collect_tb_accounts(audited_entries[wp_code]))
    assert union == EXPECTED_ACCOUNTS, (
        f"D5/D6/D7 (perm={perm}) TB 并集 != {EXPECTED_ACCOUNTS}，实际 {sorted(union)}"
    )


# ---------------------------------------------------------------------------
# P3.2 单 wp_code 子集：每个 wp_code 取数科目 ⊆ {1124, 1141, 2205}
# ---------------------------------------------------------------------------


@given(wp_code=st.sampled_from(["D5", "D6", "D7"]))
@settings(max_examples=50, deadline=None)
def test_property_p3_2_individual_subset(
    audited_entries: dict[str, dict],
    wp_code: str,
) -> None:
    """单个 D5/D6/D7 审定表 entry 的 TB 取数科目 ⊆ {1124, 1141, 2205}。

    属性意义：F1 修复后没有 entry 引入第 4 个 D 循环外科目。

    Validates: Property P3 (D5/D6/D7 取数科目集合不重不漏 — 子集封闭)
    """
    accounts = _collect_tb_accounts(audited_entries[wp_code])
    assert accounts, f"wp_code={wp_code} 审定表 entry 未提取到任何 TB 科目"
    assert accounts <= EXPECTED_ACCOUNTS, (
        f"wp_code={wp_code} TB 科目 {sorted(accounts)} 越界，"
        f"应 ⊆ {EXPECTED_ACCOUNTS}"
    )


# ---------------------------------------------------------------------------
# P3.3 单 wp_code 一一对应：每个 wp_code 仅含且必含其语义主科目
# ---------------------------------------------------------------------------


@given(wp_code=st.sampled_from(["D5", "D6", "D7"]))
@settings(max_examples=50, deadline=None)
def test_property_p3_3_one_to_one_mapping(
    audited_entries: dict[str, dict],
    wp_code: str,
) -> None:
    """D5→{1124}, D6→{1141}, D7→{2205}：单 entry 主科目 == 业务期望，
    且不混入其他两个底稿的主科目。

    Validates: Property P3 (D5/D6/D7 取数科目集合不重不漏 — 一一对应)
    """
    expected = EXPECTED_WP_TO_ACCOUNT[wp_code]
    accounts = _collect_tb_accounts(audited_entries[wp_code])

    # 必含其主科目
    assert expected in accounts, (
        f"wp_code={wp_code} 审定表应含主科目 {expected}，实际 {sorted(accounts)}"
    )
    # 其他两个 wp_code 主科目不应混入
    other_main = EXPECTED_ACCOUNTS - {expected}
    polluted = accounts & other_main
    assert not polluted, (
        f"wp_code={wp_code} 串入了其他底稿主科目 {polluted}（业务错位未修复）"
    )


# ---------------------------------------------------------------------------
# P3.4 子集封闭：任意非空 D5/D6/D7 子集的并集 ⊆ {1124, 1141, 2205}
# ---------------------------------------------------------------------------


@given(
    subset_idx=st.lists(
        st.sampled_from(["D5", "D6", "D7"]),
        min_size=1,
        max_size=3,
        unique=True,
    )
)
@settings(max_examples=50, deadline=None)
def test_property_p3_4_subset_union_closed(
    audited_entries: dict[str, dict],
    subset_idx: list[str],
) -> None:
    """任意非空 D5/D6/D7 子集的取数并集都 ⊆ {1124, 1141, 2205}，
    且当且仅当子集 = {D5,D6,D7} 全集时并集 == {1124, 1141, 2205}。

    Validates: Property P3 (D5/D6/D7 取数科目集合不重不漏 — 子集封闭 + 全集守恒等价)
    """
    union: set[str] = set()
    for wp_code in subset_idx:
        union.update(_collect_tb_accounts(audited_entries[wp_code]))

    # 子集封闭
    assert union <= EXPECTED_ACCOUNTS, (
        f"subset={subset_idx} 取数并集 {sorted(union)} 越界，应 ⊆ {EXPECTED_ACCOUNTS}"
    )

    # 全集等价：子集 == {D5,D6,D7} ⇔ 并集 == {1124,1141,2205}
    if set(subset_idx) == {"D5", "D6", "D7"}:
        assert union == EXPECTED_ACCOUNTS, (
            f"全集子集 union={sorted(union)} != {EXPECTED_ACCOUNTS}（漏取）"
        )
    else:
        # 非全集子集严格小于 {1124,1141,2205}（每个 wp_code 一一对应保证）
        assert union < EXPECTED_ACCOUNTS, (
            f"非全集 subset={subset_idx} union={sorted(union)} == 全集，"
            f"违反一一对应（D5/D6/D7 应各自对应唯一主科目）"
        )
