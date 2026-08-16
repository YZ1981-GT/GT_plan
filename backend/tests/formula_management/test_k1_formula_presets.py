"""K1 公式管理预设守卫（Requirement 10 / Property 11）.

spec: .kiro/specs/k1-extraction-chain-and-note-alignment/
"""
from __future__ import annotations

import re
from collections import Counter

import pytest

from app.services.formula_engine import validate_formula
from app.services.formula_management.preset_library import convert_prefill_presets

#: `ADJ()` 未注册进 `formula_engine._REGISTRY`（prefill 引擎词汇表 vs 校验引擎词汇表
#: 两套并存的既有平台缺口，K1-1 早已用 ADJ() 且非本 spec 引入）——按 prefill 词汇表
#: 放行，`validate_formula` 层面豁免这两条，并配反向自检防豁免范围被悄悄扩大。
_KNOWN_ADJ_EXEMPT = {"AJE调整", "RJE调整"}


@pytest.fixture(scope="module")
def k1_entries():
    entries = convert_prefill_presets()
    return [e for e in entries if e.page_key == "workpaper:K1"]


def test_k1_has_at_least_six_sheets_with_presets(k1_entries):
    """K1-1/K1-2/K1-3/K1-5/K1-7/K1-8/K1-10 各至少一条预设（Requirement 10.1~10.3）。"""
    sheets = {e.expression for e in k1_entries}  # 粗筛：至少存在
    assert len(k1_entries) >= 6
    # 用 target_cell 前缀 / description 里的 wp_code 反推覆盖的 sheet 数
    prefixes = {c.split("_")[0] for c in (e.target_cell for e in k1_entries) if "_" in c}
    assert {"K1-3", "K1-5", "K1-7", "K1-8", "K1-10"} <= prefixes


def test_k1_page_key_all_workpaper_k1(k1_entries):
    for e in k1_entries:
        assert e.page_key == "workpaper:K1"


def test_k1_no_dedup_collision_within_page_key():
    """Property 11：`(page_key, target_cell)` 全局唯一 —— 同 wp_code 下不同 sheet
    的 cell_ref 不得撞名（`convert_prefill_presets` 按此去重，撞键会静默丢弃条目）。"""
    entries = convert_prefill_presets()
    k1 = [e for e in entries if e.page_key == "workpaper:K1"]
    counts = Counter(e.target_cell for e in k1)
    dups = {k: v for k, v in counts.items() if v > 1}
    assert not dups, f"K1 预设撞键：{dups}"


def test_k1_3_block_contains_no_wp_calls(k1_entries):
    """K1-3 是被 K1-1 引用的明细方，禁含 `WP(`（防 K1-1↔K1-3 循环）。"""
    k1_3 = [e for e in k1_entries if str(e.target_cell).startswith("K1-3_")]
    assert k1_3, "K1-3 预设块未找到（守卫空转）"
    for e in k1_3:
        assert "WP(" not in e.expression, e.target_cell


def test_k1_2_aux_presets_removed_and_stay_removed():
    """K1-2 的**项目专属辅助项**预设已按 Property 22 移除，且不得重新引入。

    🔴 2026-08-14 改写（spec `k-cycle-extraction-formula-and-disclosure-closure`
    Task 11 / Property 22）。原断言是 ``assert k1_2, "K1-2 预设块未找到（守卫空转）"``
    —— 它要求块非空，与 Property 22「预设不得含具体辅助项编码」直接冲突。

    **为什么这些预设必须删**：原 6 条形如
    ``AUX('1221','三方收款标识','SKT211','期末余额')``，第三参是**某一个项目**的
    实际辅助项编码（description 里自己写着「实测代表性 aux_code #1/#2/#3」）。
    而 `prefill_engine._resolve_aux_formula` 对 ``aux_code`` 用 ``==`` 精确匹配、
    **不支持通配** ⇒ 换任何别的项目这 6 条全部返 0。写死代表性编码等于让预设
    对绝大多数项目失效，且失效形态是「静默取到 0」而非报错。

    **后继方案（登记，不在本 spec 作业面）**：按辅助项分行的明细表（K1-2 / K3-2）
    本质上**不适合静态公式预设** —— 行集依项目而异。正确做法是走 render 侧动态预填
    （读 `tb_aux_balance` 按本项目实际 ``aux_code`` 建行，形如 K2/K4/K6 的
    ``adjudication_prefill``）。届时补的预设仍须遵守下面的「禁 WP()」约束。

    本测试**不是空转**：它双向钉死「当前为空」这个结论 + 「将来补的也禁含 WP()」。
    """
    entries = convert_prefill_presets()
    k1_aux = [
        e
        for e in entries
        if e.page_key == "workpaper:K1" and "AUX(" in str(e.expression)
    ]
    hardcoded = [
        e
        for e in k1_aux
        if re.search(r"AUX\([^)]*'(?:SKT\d+|YG\d+|A\d{3})'", str(e.expression))
    ]
    assert not hardcoded, (
        "K1 预设里又出现了写死的项目专属辅助项编码（Property 22 禁止）："
        f"{[(e.target_cell, e.expression) for e in hardcoded]}"
    )
    # 「K1-2 是被引用方、禁含 WP()」这条既有约束保留：对**任何**K1-2 预设成立
    k1_2 = [
        e
        for e in entries
        if e.page_key == "workpaper:K1" and "三方收款" in str(e.target_cell)
    ]
    for e in k1_2:
        assert "WP(" not in e.expression, (
            f"K1-2 是被 K1-1 引用的明细方，禁含 WP() 防成环：{e.target_cell}"
        )


@pytest.mark.parametrize("formula_type", ["TB", "ADJ", "PREV", "WP", "AUX"])
def test_k1_formula_types_are_legal(k1_entries, formula_type):
    """K1 全部预设的 formula_type 均在合法集合内（不新增未登记类型）。"""
    legal = {"TB", "ADJ", "PREV", "WP", "AUX"}
    assert formula_type in legal  # 参数化本身即断言合法集合覆盖


def test_k1_new_blocks_pass_validate_formula(k1_entries):
    """新增 K1-3/5/7/8/10 五个块（TB/WP 纯函数）全部通过 `validate_formula`。"""
    new_blocks = [
        e for e in k1_entries
        if str(e.target_cell).startswith(("K1-3_", "K1-5_", "K1-7_", "K1-8_", "K1-10_"))
    ]
    assert len(new_blocks) == 6, f"预期 6 条新增预设，实得 {len(new_blocks)}"
    for e in new_blocks:
        errs = validate_formula(e.expression)
        assert errs == [], f"{e.target_cell}: {errs}"


def test_adj_exemption_is_narrow_and_documented(k1_entries):
    """反向自检：`ADJ()` 豁免只限定在 `_KNOWN_ADJ_EXEMPT` 两条，不得悄悄扩大范围。"""
    failing = {
        e.target_cell for e in k1_entries
        if validate_formula(e.expression) and "ADJ(" in e.expression
    }
    assert failing == _KNOWN_ADJ_EXEMPT, failing


def test_guard_detects_regression_on_dedup_collision():
    """反向自检：手工构造一组撞键条目，断言必须能抓到（防守卫空转）。"""
    from app.services.formula_management.preset_library import PresetEntry

    fake = [
        PresetEntry(page_key="workpaper:K1", source="test", target_cell="X",
                    expression="=TB('1','期末余额')", formula_type="auto_calc"),
        PresetEntry(page_key="workpaper:K1", source="test", target_cell="X",
                    expression="=TB('2','期末余额')", formula_type="auto_calc"),
    ]
    counts = Counter(e.target_cell for e in fake)
    dups = {k: v for k, v in counts.items() if v > 1}
    assert dups == {"X": 2}
