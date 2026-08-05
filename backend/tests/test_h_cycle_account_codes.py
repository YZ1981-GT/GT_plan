"""H 类循环科目码平台级守卫 — Property 7。

条件①：各循环声明的兜底码若在 `standard_account_chart.json` 范围内，则必须存在
条件②：旧错误码（属「真科目但不属本循环」或「不存在的码」）被规则判否

🔴 `1525`/`1526`/`1527` **不在公共 JSON 里**（它们是特定客户项目扩展，只在 DB 的
`account_chart` 存在）→ 条件①只验证**声明的兜底码 ∩ JSON 已有码**的子集非空，
不要求 JSON 有全部兜底码。真正的全集校验在运行态由 `resolve_semantic_accounts`
的「要求在本项目存在」逻辑兜底。

spec: .kiro/specs/h-cycle-four-table-extraction-and-account-mapping/
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.four_table.h_cycle_specs import H_CYCLE_SPECS

# ──────────────────────────────────────────────────────────────────────────────
# Load standard account chart (static JSON, no DB, CI-safe)
# ──────────────────────────────────────────────────────────────────────────────

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_CHART_PATH = _DATA_DIR / "standard_account_chart.json"


@pytest.fixture(scope="module")
def standard_codes() -> set[str]:
    """公共标准科目表的编码集合。"""
    with open(_CHART_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return {a["code"] for a in data["accounts"] if isinstance(a, dict) and "code" in a}


# ──────────────────────────────────────────────────────────────────────────────
# 条件①：兜底码若在 JSON 范围内则必须存在
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("cycle", sorted(H_CYCLE_SPECS.keys()))
def test_fallback_codes_exist_in_standard_chart(cycle: str, standard_codes: set[str]):
    """各循环的兜底码中，至少有一个在公共标准科目表中存在。

    注意：部分码（如 H3 的 `1525`/`1526`/`1527`）只在特定项目的 DB 中有，
    公共 JSON 不含 → 对这些循环只要求 **gross 槽**的兜底码存在。
    """
    spec = H_CYCLE_SPECS[cycle]
    # 至少 gross 槽应有存在于标准表的兜底码
    gross_slot = next((s for s in spec.slots if s.key == "gross"), None)
    if gross_slot is None:
        pytest.skip(f"{cycle} 无 gross 槽")
    fallbacks = gross_slot.fallback_standard_codes or ()
    if not fallbacks:
        # H5 impairment 等无兜底码的情况 → 跳过
        pytest.skip(f"{cycle}.gross 无兜底码（宁缺勿造）")
    hits = [c for c in fallbacks if c in standard_codes]
    assert hits, (
        f"{cycle}.gross 的兜底码 {fallbacks} 在标准科目表中不存在，"
        "可能是旧准则编码或打字错误"
    )


# ──────────────────────────────────────────────────────────────────────────────
# 条件②：旧错误码被判否（反向自检）
# ──────────────────────────────────────────────────────────────────────────────

# 类型 A：真科目但不属于本循环（在标准表中存在）
_OLD_ERRORS_REAL_BUT_WRONG_CYCLE = {
    "1503": "可供出售金融资产（G6 域）",
    "1504": "债权投资（G4 域）",
    "1901": "待处理财产损溢（K2 域）",
    "2205": "合同负债（D7 域）",
    "1611": "融资租赁资产（旧准则，H8 不应直接取）",
}

# 类型 B：不存在的码（标准科目表中无）
_OLD_ERRORS_NONEXISTENT = {
    "1522": "（不存在）",
    "1523": "（不存在）",
    "2802": "（不存在）",
    "2803": "（不存在）",
}


def test_old_error_codes_not_in_any_fallback():
    """旧错误码不得出现在任何 H 循环的兜底码中。"""
    all_errors = set(_OLD_ERRORS_REAL_BUT_WRONG_CYCLE) | set(_OLD_ERRORS_NONEXISTENT)

    for cycle, spec in H_CYCLE_SPECS.items():
        for slot in spec.slots:
            for code in (slot.fallback_standard_codes or ()):
                assert code not in all_errors, (
                    f"{cycle}.{slot.key} 的兜底码含旧错误码 {code}"
                )


def test_type_a_errors_exist_in_chart(standard_codes: set[str]):
    """反向自检：类型 A 旧错误码确实在标准表中（否则该类测试空转）。"""
    for code in _OLD_ERRORS_REAL_BUT_WRONG_CYCLE:
        assert code in standard_codes, (
            f"反向自检失败：旧错误码 {code} 不在标准表中，该用例空转"
        )


def test_type_b_errors_not_in_chart(standard_codes: set[str]):
    """反向自检：类型 B 旧错误码确实不在标准表中。"""
    for code in _OLD_ERRORS_NONEXISTENT:
        assert code not in standard_codes, (
            f"反向自检失败：{code} 竟然存在于标准表中，需重新归类"
        )


# ──────────────────────────────────────────────────────────────────────────────
# 跨循环互斥：同一兜底码不在两个循环的同语义槽出现
# ──────────────────────────────────────────────────────────────────────────────

def test_no_gross_fallback_overlap_across_cycles():
    """不同循环的 gross 槽兜底码无交集（否则两循环取同一科目→双算）。

    例外：H2.gross(`1604`) 与 H4.cip(`1604`) 是有意跨引（互为核对参照），
    但 H2.gross 与 H4.gross 不应撞。
    """
    gross_by_cycle: dict[str, set[str]] = {}
    for cycle, spec in H_CYCLE_SPECS.items():
        gross = next((s for s in spec.slots if s.key == "gross"), None)
        if gross and gross.fallback_standard_codes:
            gross_by_cycle[cycle] = set(gross.fallback_standard_codes)

    cycles = sorted(gross_by_cycle.keys())
    for i in range(len(cycles)):
        for j in range(i + 1, len(cycles)):
            overlap = gross_by_cycle[cycles[i]] & gross_by_cycle[cycles[j]]
            assert not overlap, (
                f"{cycles[i]} 与 {cycles[j]} 的 gross 兜底码有交集 {overlap}，"
                "两循环取同一科目会导致双算"
            )
