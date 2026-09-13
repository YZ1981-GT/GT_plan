# -*- coding: utf-8 -*-
"""D4-1 营业收入审定表公式预设守卫（Requirement 3.1 / Property 2）。

spec: .kiro/specs/d4-1-adjudication-bidirectional-writeback-and-formula-io/ Task 3.1

守卫目标（纯后端 seed 预设 + 守卫，不碰前端/共享保存链）：
- D4-1 预设集覆盖 Req 3.1 要求的每一类公式：审定数 / 上期审定数 / 小计 / 合计 /
  TB核对 / 差异 / 变动率 / D4-2 引用 / D4-3 引用，逐条断言存在。
- 每条 `(page_key, target_cell)` 唯一（build_preset_library 对 D4-1 条目 skipped=0）。
- 每条 expression 过 `validate_expression`（schema 白名单，禁 eval/外链）。
- `resolve_effective_formula` 用 D4-1 的 FormulaKey 能解析出 state=preset、expression 非空。
- 反向自检 / 变异自检：故意注入 `eval(` / `import` 必须被 validate 判红。

target_cell 命名与前端 `useD4Adjudication.ts` 字段语义对齐（`审定数` / 小计 /
`营业收入合计` / 试算平衡表数 6001·6051 / 差异 / 变动率），且带 `D4-1-` 前缀避免
与其它循环在平台级 `(page_key, target_cell)` 空间撞键。
"""
from __future__ import annotations

from collections import Counter

import pytest

from app.services.formula_management.effective_formula import (
    FormulaKey,
    resolve_effective_formula,
    validate_expression,
)
from app.services.formula_management.preset_library import (
    PresetEntry,
    build_preset_library,
    load_seed_presets,
)

#: D4-1 审定表的 page_key（与 `workpaper:{wp_code}` 口径一致）。
D4_PAGE_KEY = "workpaper:D4"

#: Req 3.1 要求覆盖的每一类公式 → 该类应存在的 D4-1 预设 target_cell。
#: 每条注释标明覆盖的公式类别，用于「逐类断言存在」。
D4_1_REQUIRED_TARGET_CELLS: dict[str, str] = {
    "审定数": "本期审定数（E列，未审+AJE+RJE）",
    "D4-1-上期审定数": "上期审定数（I列）",
    "D4-1-主营业务收入小计-审定数": "主营小计（R12）",
    "D4-1-其他业务收入小计-审定数": "其他小计（R18）",
    "D4-1-营业收入合计-审定数": "合计（R19）",
    "D4-1-试算平衡表数-主营": "TB核对 6001",
    "D4-1-试算平衡表数-其他": "TB核对 6051",
    "D4-1-试算平衡表数": "TB核对合计（R20）",
    "D4-1-差异数": "差异（R21）",
    "D4-1-未审变动率": "本期未审变动率",
    "D4-1-审定变动率": "审定变动率",
    "D4-1-主营业务收入-未审数": "D4-2 主营明细 WP 引用",
    "D4-1-其他业务收入-未审数": "D4-3 其他明细 WP 引用",
}


@pytest.fixture(scope="module")
def d4_seed_entries() -> list[PresetEntry]:
    """D4-1 在 seed 里显式登记的预设条目（source=d_cycle_audited_structure）。"""
    return [
        e
        for e in load_seed_presets()
        if e.page_key == D4_PAGE_KEY
        and (e.target_cell == "审定数" or e.target_cell.startswith("D4-1-"))
    ]


@pytest.fixture(scope="module")
def d4_seed_by_cell(d4_seed_entries: list[PresetEntry]) -> dict[str, PresetEntry]:
    return {e.target_cell: e for e in d4_seed_entries}


# ── 覆盖度：逐类公式存在（Req 3.1）────────────────────────────────────────────
@pytest.mark.parametrize(
    "target_cell", sorted(D4_1_REQUIRED_TARGET_CELLS), ids=list(sorted(D4_1_REQUIRED_TARGET_CELLS))
)
def test_d4_1_required_formula_class_present(
    d4_seed_by_cell: dict[str, PresetEntry], target_cell: str
):
    """Req 3.1：D4-1 预设覆盖每一类要求的公式，逐条断言存在。"""
    assert target_cell in d4_seed_by_cell, (
        f"D4-1 缺少必需预设 {target_cell!r}"
        f"（覆盖类别：{D4_1_REQUIRED_TARGET_CELLS[target_cell]}）"
    )


def test_d4_1_covers_all_req_3_1_categories(d4_seed_by_cell: dict[str, PresetEntry]):
    """Req 3.1：整体覆盖清单一次性核对（防某类被整体遗漏）。"""
    missing = sorted(set(D4_1_REQUIRED_TARGET_CELLS) - set(d4_seed_by_cell))
    assert not missing, f"D4-1 未覆盖 Req 3.1 的公式类别：{missing}"


def test_d4_1_tb_check_uses_single_account_codes(d4_seed_by_cell: dict[str, PresetEntry]):
    """Req 3.1/3.3：TB 核对取单科目码 6001/6051 发生额（损益类），不用未核定范围。"""
    assert "TB('6001', '发生额')" == d4_seed_by_cell["D4-1-试算平衡表数-主营"].expression
    assert "TB('6051', '发生额')" == d4_seed_by_cell["D4-1-试算平衡表数-其他"].expression


def test_d4_1_difference_is_audited_minus_tb(d4_seed_by_cell: dict[str, PresetEntry]):
    """Req 3.1：差异数 = 审定合计 − 试算平衡表数。"""
    expr = d4_seed_by_cell["D4-1-差异数"].expression
    assert "营业收入合计-审定数" in expr
    assert "试算平衡表数" in expr
    assert "-" in expr


def test_d4_1_references_d4_2_and_d4_3(d4_seed_by_cell: dict[str, PresetEntry]):
    """Req 3.1：D4-2 / D4-3 明细表 WP 引用（真名 sheet）。"""
    assert "主营业务收入明细表D4-2" in d4_seed_by_cell["D4-1-主营业务收入-未审数"].expression
    assert "其他业务收入明细表D4-3" in d4_seed_by_cell["D4-1-其他业务收入-未审数"].expression


# ── 唯一性：(page_key, target_cell) 唯一（Property 2 / dedup skipped=0）────────
def test_d4_1_seed_target_cells_unique(d4_seed_entries: list[PresetEntry]):
    """每条 `(page_key, target_cell)` 唯一（用 dedup_key 计数）。"""
    counts = Counter(e.dedup_key() for e in d4_seed_entries)
    dups = {k: v for k, v in counts.items() if v > 1}
    assert not dups, f"D4-1 seed 预设撞键：{dups}"


def test_d4_1_no_dedup_collision_in_library():
    """D4-1 条目进入 build_preset_library 后无撞键（skipped 未吃掉任何 D4-1 条目）。

    判据：库中 D4-1 全体 target_cell 无重复，且我的 13 条 D4-1 语义 cell 全部以
    `d_cycle_audited_structure` 源存在（未被 prefill 收敛源同键覆盖/顶掉）。
    """
    entries, _stats = build_preset_library()
    d4 = [e for e in entries if e.page_key == D4_PAGE_KEY]
    counts = Counter(e.target_cell for e in d4)
    dups = {k: v for k, v in counts.items() if v > 1}
    assert not dups, f"库内 D4 撞键：{dups}"

    by_cell = {e.target_cell: e for e in d4}
    for cell in D4_1_REQUIRED_TARGET_CELLS:
        assert cell in by_cell, f"D4-1 预设 {cell!r} 未进入预设库"
        assert by_cell[cell].source == "d_cycle_audited_structure", (
            f"D4-1 预设 {cell!r} 被非 d_cycle 源覆盖：{by_cell[cell].source}"
        )


# ── 白名单：每条 expression 过 validate_expression（Req 3.1）──────────────────
def test_d4_1_all_expressions_pass_validate(d4_seed_entries: list[PresetEntry]):
    """每条 D4-1 预设 expression 过 schema 白名单（只用 TB/WP/SUM/ABS/ROUND 等）。"""
    assert d4_seed_entries, "D4-1 seed 预设为空（守卫空转）"
    for e in d4_seed_entries:
        ok, reason = validate_expression(e.expression)
        assert ok, f"{e.target_cell}: {reason} | {e.expression}"


def test_d4_1_formula_types_are_legal(d4_seed_entries: list[PresetEntry]):
    """formula_type 均在三类型内。"""
    legal = {"auto_calc", "logic_check", "reasonability"}
    for e in d4_seed_entries:
        assert e.formula_type in legal, f"{e.target_cell}: {e.formula_type}"


def test_d4_1_refs_match_expression_calls(d4_seed_entries: list[PresetEntry]):
    """refs 数组按 expression 里的 WP()/TB() 声明（非空、可追溯）。"""
    for e in d4_seed_entries:
        if "WP(" in e.expression or "TB(" in e.expression:
            assert e.refs, f"{e.target_cell} 含 WP/TB 调用但 refs 为空"
            for r in e.refs:
                assert isinstance(r, dict) and r.get("formula_ref"), (
                    f"{e.target_cell} 的 ref 缺 formula_ref：{r}"
                )


# ── resolve：FormulaKey 可解析出 preset 态（Property 2）──────────────────────
@pytest.mark.parametrize(
    "target_cell", sorted(D4_1_REQUIRED_TARGET_CELLS), ids=list(sorted(D4_1_REQUIRED_TARGET_CELLS))
)
def test_d4_1_resolve_effective_formula_preset(target_cell: str):
    """`resolve_effective_formula`（field_key=target_cell）解析出 state=preset、expression 非空。"""
    key = FormulaKey(
        wp_id="D4",
        stable_sheet_key=D4_PAGE_KEY,
        row_key="",
        field_key=target_cell,
    )
    result = resolve_effective_formula(key)
    assert result.state == "preset", (
        f"{target_cell} 解析态应为 preset，实得 {result.state}（reason={result.reason}）"
    )
    assert result.expression, f"{target_cell} preset expression 为空"


def test_d4_1_resolve_custom_overrides_preset():
    """custom 优先：传 custom_expression 时 state=custom（预设作可恢复底稿）。"""
    key = FormulaKey(
        wp_id="D4",
        stable_sheet_key=D4_PAGE_KEY,
        row_key="",
        field_key="D4-1-差异数",
    )
    result = resolve_effective_formula(
        key, custom_expression="WP('D4','营业收入审定表D4-1','营业收入合计-审定数')"
    )
    assert result.state == "custom"
    assert result.preset_expression, "删除 custom 应可回落到 preset（preset_expression 非空）"


# ── 反向自检 / 变异自检（守卫必须有分辨力）────────────────────────────────────
def test_validate_rejects_eval_injection():
    """反向自检：含 `eval(` 的表达式必须被 validate 判红（证明校验有分辨力）。"""
    ok, reason = validate_expression("eval(WP('D4','营业收入审定表D4-1','审定数'))")
    assert not ok, "含 eval( 的表达式竟通过白名单（守卫失效）"
    assert "eval" in reason


def test_validate_rejects_import_injection():
    """变异自检：把 D4-1 预设 expression 改成含 `import` 必须被判红（RED）。

    取一条真实 D4-1 预设，注入 `import`，断言 validate 打红——若守卫无分辨力，
    这里会 GREEN（测试反被通过）而暴露缺陷。
    """
    seed = {
        e.target_cell: e
        for e in load_seed_presets()
        if e.page_key == D4_PAGE_KEY
    }
    base = seed["D4-1-营业收入合计-审定数"].expression
    ok_base, _ = validate_expression(base)
    assert ok_base, "基线 D4-1 预设本应合法"

    mutated = base + " import os"
    ok_mut, reason = validate_expression(mutated)
    assert not ok_mut, f"注入 import 后竟仍合法（守卫失效）：{mutated}"
    assert "import" in reason


def test_guard_detects_dedup_collision_regression():
    """反向自检：手工构造撞键条目，断言必被 dedup_key 计数抓到（防守卫空转）。"""
    fake = [
        PresetEntry(
            page_key=D4_PAGE_KEY,
            source="test",
            target_cell="D4-1-差异数",
            expression="WP('D4','营业收入审定表D4-1','审定数')",
            formula_type="auto_calc",
        ),
        PresetEntry(
            page_key=D4_PAGE_KEY,
            source="test",
            target_cell="D4-1-差异数",
            expression="WP('D4','营业收入审定表D4-1','未审数')",
            formula_type="auto_calc",
        ),
    ]
    counts = Counter(e.dedup_key() for e in fake)
    dups = {k: v for k, v in counts.items() if v > 1}
    assert dups == {(D4_PAGE_KEY, "D4-1-差异数"): 2}
