"""G0 公式预设守卫 —— Property 21 / 22 / 23

spec: g0-confirmation-source-alignment，Task 18（Requirement 9.1~9.6）

- **Property 21**：G0 预设块 `sheet` 在源 xlsx `wb.sheetnames` 内；8 条 cell 全为
  `PLACEHOLDER`（不含 `TB_SUM('a~b')` 跨科目族区间、**也不含 `=TB('`**）；formula 里
  **不出现任何科目码字面量**（码只许进 `description` 与块级 `account_codes`，R4.4）；
  8 个科目码都在标准科目表内且属 G 循环报表行引用集合；G0 与 H0 两个 fix 脚本口径一致。
- **Property 22**：`--check` 在已修正态 exit 0；连续两次 `--apply` 第二次 0 项变更；
  round-trip 自检失败即 exit 2 且不写盘。
- **Property 23**：守卫只扫语义字段（`formula`/`account_codes`/`cell_ref`/`sheet`），
  **不**对整块 `json.dumps` 做「不得出现 xxx」断言（`description` 会如实写出被纠正的
  反例）。含反向自检。

不连库、不改真实文件（Property 22 全部在 `tmp_path` 副本上跑）。

🔴 两条设计说明
---------------
1. **`cell_ref` 按 TS 函数的规则断言，不比对字面量** —— 真源是
   `g0MatrixDataSources.g0MatrixOverrideItemId()`，本文件读 TS 源码抽模板串后复刻拼接，
   并配反向自检（模板被改坏时必须打红，而不是静默沿用旧键）。
2. **live 态断言在 `--apply` 之前会挂 pending** —— 用 `_PENDING_CHANGES` 探测，
   并由 `test_pending_state_is_loud_and_frozen` 把「尚未 apply」这件事钉成显式基线：
   部分 apply / 变更清单漂移立即打红，杜绝 skip 变成假绿。
"""

from __future__ import annotations

import importlib.util
import io
import json
import re
import sys
import tokenize
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT_PATH = _REPO_ROOT / "backend" / "scripts" / "fix" / "fix_g0_prefill_presets.py"
#: H0 侧同族脚本（**只读**，用于口径交叉锁）
_H0_SCRIPT_PATH = _REPO_ROOT / "backend" / "scripts" / "fix" / "fix_h0_prefill_presets.py"
_JSON_PATH = _REPO_ROOT / "backend" / "data" / "prefill_formula_mapping.json"
_CHART_PATH = _REPO_ROOT / "backend" / "data" / "standard_account_chart.json"
_G_SPECS_PATH = (
    _REPO_ROOT / "backend" / "app" / "services" / "four_table" / "g_cycle_specs.py"
)
_PRESET_LIB_PATH = (
    _REPO_ROOT
    / "backend"
    / "app"
    / "services"
    / "formula_management"
    / "preset_library.py"
)
_TS_DIR = (
    _REPO_ROOT
    / "audit-platform"
    / "frontend"
    / "src"
    / "components"
    / "workpaper"
    / "g0-confirmation"
)


def _load_script():
    spec = importlib.util.spec_from_file_location("fix_g0_prefill_presets", _SCRIPT_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    # 🔴 必须先注册进 sys.modules —— 否则模块内的 @dataclass 在解析注解时
    #    拿 sys.modules.get(cls.__module__) 得到 None 而抛 AttributeError
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


fix = _load_script()

_LIVE_DATA = json.loads(_JSON_PATH.read_text(encoding="utf-8"))
_CELL_REF_TEMPLATE = fix.read_ts_cell_ref_template()
_G0_IDX, _PENDING_CHANGES = fix.plan(_LIVE_DATA, _CELL_REF_TEMPLATE)
_LIVE_BLOCK = _LIVE_DATA["mappings"][_G0_IDX]
_TARGET_BLOCK = fix.build_expected_block(_LIVE_BLOCK, _CELL_REF_TEMPLATE)

_pending = pytest.mark.skipif(
    bool(_PENDING_CHANGES),
    reason=(
        "G0 块尚未 --apply（用户明确本轮只跑 --check/--dry-run）；"
        "apply 后本类断言自动生效。pending 状态由 "
        "test_pending_state_is_loud_and_frozen 显式钉死"
    ),
)


# ─────────────────────────── 语义字段扫描器（Property 23 核心） ───────────────────


_RANGE_RE = re.compile(r"TB_SUM\(\s*'[^']*~[^']*'")

#: 按码取数调用（裁决后 8 条 formula 一律不得命中）
_TB_CALL_RE = re.compile(r"\bTB\(\s*'")

#: 科目码字面量（4 位及以上连续数字）——formula 里一律不许出现（R4.4 / Property 11）
_CODE_LITERAL_RE = re.compile(r"\d{4,}")

#: 语义字段白名单 —— 守卫只对这四个字段取值判定，绝不 dump 整块
SEMANTIC_FIELDS = ("sheet", "account_codes", "cell_ref", "formula")


def formula_account_code_literals(block: dict) -> list[str]:
    """列出 `cells[].formula` 里出现的科目码字面量（只读 `formula` / `cell_ref`）。

    🔴 与 `fix.selfcheck_no_account_code_in_formula` 同口径，两侧互为旁证。
    """
    bad: list[str] = []
    for cell in block.get("cells") or []:
        hits = sorted(set(_CODE_LITERAL_RE.findall(str(cell.get("formula") or ""))))
        if hits:
            bad.append(f"{cell.get('cell_ref')!r}: {hits}")
    return bad


def semantic_violations(
    block: dict,
    *,
    sheetnames: tuple[str, ...],
    chart_codes: dict[str, str],
) -> list[str]:
    """只扫 `sheet` / `account_codes` / `cell_ref` / `formula` 四个语义字段。

    🔴 有意不看 `description` / `formula_type` / `wp_name` —— `description` 会如实写出
    被纠正的反例（`TB_SUM('1101~1511')`、`TB('1101','期末余额')`），扫它必产假红。

    🔴 「`TB(...)` 引用的码必须登记在 `account_codes`」那条分支在 8 条 PLACEHOLDER 下
    **不会命中**（PLACEHOLDER 无码引用），但**有意保留** —— 它是防「将来有人把公式改回
    `TB()` 却忘了登记码」的闸。配 `test_tb_code_registration_branch_still_fires`
    反向自检，确保它不是空转。
    """
    bad: list[str] = []

    sheet = block.get("sheet")
    if sheet not in sheetnames:
        bad.append(f"sheet={sheet!r} 不在源 xlsx sheetnames 内")

    codes = list(block.get("account_codes") or [])
    for code in codes:
        if code not in chart_codes:
            bad.append(f"account_codes 含非标准科目码 {code!r}")

    for cell in block.get("cells") or []:
        formula = str(cell.get("formula") or "")
        ref = cell.get("cell_ref")
        if _RANGE_RE.search(formula):
            bad.append(f"cell_ref={ref!r} 的 formula 含跨科目族区间: {formula}")
        for code in re.findall(r"TB\(\s*'(\d+)'", formula):
            if code not in codes:
                bad.append(f"cell_ref={ref!r} 引用的 {code!r} 未登记在 account_codes")
    return bad


def _chart_codes() -> dict[str, str]:
    chart = json.loads(_CHART_PATH.read_text(encoding="utf-8"))
    return {a["code"]: a["name"] for a in chart["accounts"]}


def _sheetnames() -> tuple[str, ...]:
    return fix.source_sheetnames()


# ═══════════════════════════ Property 21 ══════════════════════════════════════


class TestProperty21TargetState:
    """纠偏目标态必须自洽（改造前即可跑，证明「要改成什么」是对的）。"""

    def test_sheet_name_exists_in_source_workbook(self) -> None:
        names = _sheetnames()
        assert fix.EXPECTED_SHEET in names, f"{fix.EXPECTED_SHEET} 不在 {names}"
        assert _TARGET_BLOCK["sheet"] == fix.EXPECTED_SHEET

    def test_legacy_sheet_name_really_absent(self) -> None:
        """反向自检：`审定表G0-1` 确实不存在，纠偏前提成立。"""
        assert "审定表G0-1" not in _sheetnames()

    def test_target_block_has_no_semantic_violation(self) -> None:
        bad = semantic_violations(
            _TARGET_BLOCK, sheetnames=_sheetnames(), chart_codes=_chart_codes()
        )
        assert bad == []

    def test_target_has_exactly_eight_placeholder_cells(self) -> None:
        """8 条 PLACEHOLDER —— 与 H0 口径统一（见 fix 脚本文件头「裁决」）。

        ``TB()`` 取不到时返 0，会把「本项目无此科目」与「余额为 0」混同（R4.3）；
        且 cell_ref 是手工覆盖键，写 TB() 等于让 0 伪装成手填值压住 undefined（R3.5）。
        """
        cells = _TARGET_BLOCK["cells"]
        assert len(cells) == 8
        assert all(c["formula_type"] == "PLACEHOLDER" for c in cells)
        assert all(c["formula"].startswith("=PLACEHOLDER('") for c in cells)
        assert not any(_RANGE_RE.search(c["formula"]) for c in cells)
        # 正向断言：不得含按码取数
        assert not any("=TB('" in c["formula"] for c in cells)
        assert not any(_TB_CALL_RE.search(c["formula"]) for c in cells)

    def test_tb_call_scanner_actually_fires(self) -> None:
        """反向自检：塞一条 `=TB('1101',...)` 必须被上一条的检测式抓到。"""
        broken = "=TB('1101','期末余额')"
        assert "=TB('" in broken
        assert _TB_CALL_RE.search(broken)
        # 且 PLACEHOLDER 形态不得被误报
        assert not _TB_CALL_RE.search("=PLACEHOLDER('交易性金融资产本期（期末）账面金额')")

    def test_no_account_code_literal_in_any_formula(self) -> None:
        """R4.4 / Property 11：科目码只许进 description 与块级 account_codes。"""
        assert formula_account_code_literals(_TARGET_BLOCK) == []
        assert fix.selfcheck_no_account_code_in_formula(
            {"mappings": [_TARGET_BLOCK]}, 0
        ) is None

    def test_account_code_literal_scanner_actually_fires(self) -> None:
        """反向自检：formula 里写回科目码必须打红（含脚本侧同名自检）。"""
        broken = json.loads(json.dumps(_TARGET_BLOCK))
        broken["cells"][0]["formula"] = "=TB('1101','期末余额')"
        assert formula_account_code_literals(broken) != []
        assert fix.selfcheck_no_account_code_in_formula({"mappings": [broken]}, 0) is not None

    def test_codes_still_present_in_description_and_block_level(self) -> None:
        """码没有被「清干净」—— 它们仍须在 description 与 account_codes 里可见。"""
        assert _TARGET_BLOCK["account_codes"] == [
            s.account_code for s in fix.BOOK_AMOUNT_SPECS
        ]
        for spec, cell in zip(fix.BOOK_AMOUNT_SPECS, _TARGET_BLOCK["cells"]):
            assert spec.account_code in cell["description"]
            assert spec.row_code in cell["description"]
            assert spec.wp_code in cell["description"]

    def test_description_states_semantic_source_and_absent_wording(self) -> None:
        """每条 description 三件事齐备（真源 / 仅展示 / 「本项目无此科目」）。"""
        for cell in _TARGET_BLOCK["cells"]:
            desc = cell["description"]
            assert "project_context.tb_amount" in desc
            assert "semantic_account_resolver" in desc
            assert "loadG0MatrixSources" in desc
            assert "运行态不据此取数" in desc
            assert "本项目无此科目" in desc

    def test_legacy_anchors_removed(self) -> None:
        """`期初余额`/`未审数` 是审定表锚点，G0-1 是函证汇总表、没有双期结构。"""
        refs = [c["cell_ref"] for c in _TARGET_BLOCK["cells"]]
        assert "期初余额" not in refs
        assert "未审数" not in refs

    def test_eight_codes_in_standard_chart_with_matching_names(self) -> None:
        chart = _chart_codes()
        for spec in fix.BOOK_AMOUNT_SPECS:
            assert spec.account_code in chart, f"{spec.account_code} 不在标准科目表"
            assert chart[spec.account_code] == spec.category, (
                f"{spec.account_code} 标准科目名 {chart[spec.account_code]!r} "
                f"≠ 品种名 {spec.category!r}"
            )

    def test_codes_belong_to_g_cycle_report_rows(self) -> None:
        """Req 9.6：每个码都属 G 循环报表行引用集合（交叉锁 g_cycle_specs.py，不连库）。"""
        src = _G_SPECS_PATH.read_text(encoding="utf-8")
        for spec in fix.BOOK_AMOUNT_SPECS:
            block = _extract_spec_block(src, spec.wp_code)
            assert f'row_code="{spec.row_code}"' in block, (
                f"{spec.wp_code}_SPEC 的 row_code 与 {spec.row_code} 不符"
            )
            assert f'("{spec.account_code}",)' in block, (
                f"{spec.wp_code}_SPEC 未把 {spec.account_code} 作为兜底科目码"
            )

    def test_g_cycle_cross_lock_reverse_selfcheck(self) -> None:
        """反向自检：故意错配必须打红（防上一条正则失效空转）。"""
        src = _G_SPECS_PATH.read_text(encoding="utf-8")
        block = _extract_spec_block(src, "G1")
        assert 'row_code="BS-024"' not in block  # BS-024 是 G7
        assert '("1511",)' not in block  # 1511 是 G7

    def test_no_range_formula_scanner_actually_fires(self) -> None:
        """反向自检：把旧区间公式塞回去，扫描器必须报出来。"""
        broken = json.loads(json.dumps(_TARGET_BLOCK))
        broken["cells"][0]["formula"] = "=TB_SUM('1101~1511','期末余额')"
        bad = semantic_violations(
            broken, sheetnames=_sheetnames(), chart_codes=_chart_codes()
        )
        assert any("跨科目族区间" in b for b in bad)

    def test_tb_code_registration_branch_is_vacuous_on_placeholder(self) -> None:
        """PLACEHOLDER 形态下「码须登记」分支不命中（无码引用）—— 但分支仍在。"""
        bad = semantic_violations(
            _TARGET_BLOCK, sheetnames=_sheetnames(), chart_codes=_chart_codes()
        )
        assert not any("未登记在 account_codes" in b for b in bad)

    def test_tb_code_registration_branch_still_fires(self) -> None:
        """反向自检：改回 `TB()` 且引用未登记的码，那条闸必须打红（不是空转）。"""
        broken = json.loads(json.dumps(_TARGET_BLOCK))
        broken["cells"][0]["formula"] = "=TB('9999','期末余额')"
        bad = semantic_violations(
            broken, sheetnames=_sheetnames(), chart_codes=_chart_codes()
        )
        assert any("未登记在 account_codes" in b for b in bad)

        # 已登记的码则不报（证明判据是「是否登记」而非「是否用了 TB」）
        ok = json.loads(json.dumps(_TARGET_BLOCK))
        ok["cells"][0]["formula"] = "=TB('1101','期末余额')"
        assert not any(
            "未登记在 account_codes" in b
            for b in semantic_violations(
                ok, sheetnames=_sheetnames(), chart_codes=_chart_codes()
            )
        )


class TestProperty21H0CalibrationCrossLock:
    """G0 与 H0 两个 fix 脚本的口径交叉锁（同 Property 7 的同源守卫思路）。

    收敛友好：两 spec 已统一为「语义定位 + PLACEHOLDER」口径。任一侧改回按码 `TB()`
    即打红提醒复核，而不是让两份副本各自漂移。
    """

    _MSG = (
        "两 spec 已统一为语义定位口径（G0 逐品种 8 条 / H0 期初+期末 2 条），"
        "若 H0 侧改回 TB() 则此处打红提醒复核 —— 请连同 G0 侧一并裁决，勿单侧漂移"
    )

    def test_h0_script_exists(self) -> None:
        assert _H0_SCRIPT_PATH.exists(), f"H0 fix 脚本缺失: {_H0_SCRIPT_PATH}"

    def test_h0_target_cells_are_placeholder(self) -> None:
        cells = _h0_target_cells()
        assert cells, "从 fix_h0_prefill_presets.py 抽 TARGET_CELLS 为空（正则失效）"
        # 锚点：H0 是 2 条（期初 + 期末未审）。抽取器正则漂移会让集合悄悄变小 = 假绿。
        assert len(cells) == 2, f"H0 侧应恰 2 条 cell，抽到 {len(cells)} 条：{cells}"
        assert all(c["formula_type"] == "PLACEHOLDER" for c in cells), self._MSG
        assert all(c["formula"].startswith("=PLACEHOLDER('") for c in cells), self._MSG
        assert not any(_TB_CALL_RE.search(c["formula"]) for c in cells), self._MSG

    def test_h0_formulas_carry_no_account_code_literal(self) -> None:
        assert formula_account_code_literals({"cells": _h0_target_cells()}) == [], self._MSG

    def test_both_sides_agree_on_formula_type(self) -> None:
        g0_types = {c["formula_type"] for c in _TARGET_BLOCK["cells"]}
        h0_types = {c["formula_type"] for c in _h0_target_cells()}
        assert g0_types == h0_types == {"PLACEHOLDER"}, self._MSG

    def test_extraction_reverse_selfcheck(self) -> None:
        """反向自检：抽取器对 TB() 形态必须判出差异（否则本类恒绿 = 空转）。"""
        fake = [{"formula": "=TB('1601','期初余额')", "formula_type": "TB"}]
        assert not all(c["formula_type"] == "PLACEHOLDER" for c in fake)
        assert _TB_CALL_RE.search(fake[0]["formula"])
        assert formula_account_code_literals({"cells": fake}) != []


def _h0_target_cells() -> list[dict]:
    """读 `fix_h0_prefill_presets.py` **源码**抽 `TARGET_CELLS` 的 formula/formula_type。

    🔴 只读源码不 import —— 本会话硬约束「不碰 fix_h0_prefill_presets.py（只读它）」，
    且 import 会连带跑它的模块级路径解析。
    """
    src = _H0_SCRIPT_PATH.read_text(encoding="utf-8")
    start = src.find("TARGET_CELLS")
    assert start >= 0, "fix_h0_prefill_presets.py 未找到 TARGET_CELLS"
    block = src[start:]
    out: list[dict] = []
    for m in re.finditer(
        r'"formula":\s*"([^"]+)",\s*\n\s*"formula_type":\s*"([^"]+)"', block
    ):
        out.append({"formula": m.group(1), "formula_type": m.group(2)})
    return out


def _extract_spec_block(src: str, wp_code: str) -> str:
    """截取 `{wp_code}_SPEC = SemanticAccountSpec(...)` 的实参体（花括号/圆括号配对）。"""
    marker = f"{wp_code}_SPEC = SemanticAccountSpec("
    start = src.find(marker)
    assert start >= 0, f"g_cycle_specs.py 未找到 {marker}"
    i = start + len(marker)
    depth = 1
    while i < len(src) and depth:
        if src[i] == "(":
            depth += 1
        elif src[i] == ")":
            depth -= 1
        i += 1
    body = src[start + len(marker) : i - 1]
    assert body.strip(), f"{wp_code}_SPEC 实参体为空（截取失效）"
    return body


class TestProperty21CellRefKeyTruthSource:
    """cell_ref 必须按 TS 函数的规则产出，而不是照抄字面量。"""

    def test_template_extracted_from_ts_source(self) -> None:
        assert _CELL_REF_TEMPLATE == "G0-1-matrix-${category}-${metric}"

    def test_rendered_refs_match_ts_rule(self) -> None:
        for spec, cell in zip(fix.BOOK_AMOUNT_SPECS, _TARGET_BLOCK["cells"]):
            expected = fix.render_cell_ref(
                _CELL_REF_TEMPLATE, spec.category, fix.EDITABLE_METRIC
            )
            assert cell["cell_ref"] == expected

    def test_obsolete_design_key_shape_not_used(self) -> None:
        """design.md 立项时的 `G0-1-lower-book-amount-{category}` 已作废。"""
        refs = [c["cell_ref"] for c in _TARGET_BLOCK["cells"]]
        assert not any(r.startswith("G0-1-lower-book-amount-") for r in refs)
        assert all(r.startswith("G0-1-matrix-") and r.endswith("-book_amount") for r in refs)

    def test_ts_extraction_reverse_selfcheck(self) -> None:
        """反向自检：TS 侧模板被改坏时必须打红，而不是静默回退旧键。"""
        fake_ok = (
            "export function g0MatrixOverrideItemId(category: string, "
            "metric: G0MetricKey): string {\n"
            "  return `X-${category}::${metric}`\n}\n"
        )
        assert fix.read_ts_cell_ref_template(fake_ok) == "X-${category}::${metric}"
        with pytest.raises(SystemExit):
            fix.read_ts_cell_ref_template("export function somethingElse() {}")

    def test_editable_metric_matches_ts(self) -> None:
        ts = (_TS_DIR / "g0MatrixDataSources.ts").read_text(encoding="utf-8")
        m = re.search(r"const EDITABLE_METRIC:\s*G0MetricKey\s*=\s*'([^']+)'", ts)
        assert m, "未从 TS 抽出 EDITABLE_METRIC（正则失效）"
        assert m.group(1) == fix.EDITABLE_METRIC

    def test_categories_cross_locked_with_frontend(self) -> None:
        ts = fix.read_ts_matrix_categories()
        mine = [(s.category, s.row_code, s.wp_code) for s in fix.BOOK_AMOUNT_SPECS]
        assert ts == mine


class TestProperty21PageKeyUniqueness:
    """`page_key = f"workpaper:{wp_code}"` 忽略 sheet → 同 wp_code 下 cell_ref 必须唯一。"""

    def test_preset_page_key_ignores_sheet(self) -> None:
        """交叉锁死撞键前提：确认 convert_prefill_presets 真的不含 sheet。"""
        src = _PRESET_LIB_PATH.read_text(encoding="utf-8")
        assert 'page_key = f"workpaper:{wp_code}"' in src

    def test_eight_refs_unique_under_workpaper_g0(self) -> None:
        refs = [c["cell_ref"] for c in _TARGET_BLOCK["cells"]]
        assert len(refs) == len(set(refs)) == 8

    def test_no_other_g0_block_shadows_these_refs(self) -> None:
        """全文件其余 G0 块（若并发会话新增）不得占用这 8 个 cell_ref。"""
        target = {c["cell_ref"] for c in _TARGET_BLOCK["cells"]}
        for i, m in enumerate(_LIVE_DATA["mappings"]):
            if i == _G0_IDX or m.get("wp_code") != fix.WP_CODE:
                continue
            others = {c.get("cell_ref") for c in m.get("cells") or []}
            assert not (target & others), f"mappings[{i}] 与 G0 目标 cell_ref 撞键"


@_pending
class TestProperty21LiveState:
    """落盘后生效：live JSON 的 G0 块本身必须满足 Property 21。"""

    def test_live_block_has_no_semantic_violation(self) -> None:
        bad = semantic_violations(
            _LIVE_BLOCK, sheetnames=_sheetnames(), chart_codes=_chart_codes()
        )
        assert bad == []

    def test_live_block_equals_target(self) -> None:
        assert _LIVE_BLOCK == _TARGET_BLOCK


# ═══════════════════════════ Property 22 ══════════════════════════════════════


#: 纠偏**前**的 G0 块形态（源自 git 历史实证：2 条跨科目族区间 + 两个审定表锚点）。
#: 🔴 Property 22 的「未修正态」fixture 必须**显式构造**，不能拿 `_LIVE_DATA` 充当 ——
#:    `--apply` 落盘后 live 就是修正态，靠 live 当未修正态的用例会在落盘那一刻反转失败。
LEGACY_G0_BLOCK: dict = {
    "wp_code": "G0",
    "wp_name": "投资循环函证",
    "sheet": "审定表G0-1",
    "account_codes": ["1101", "1511"],
    "cells": [
        {
            "cell_ref": "期初余额",
            "formula": "=TB_SUM('1101~1511','期初余额')",
            "formula_type": "TB_SUM",
            "description": "从试算表取投资循环函证期初余额合计",
        },
        {
            "cell_ref": "未审数",
            "formula": "=TB_SUM('1101~1511','期末余额')",
            "formula_type": "TB_SUM",
            "description": "从试算表取投资循环函证期末余额合计（未审）",
        },
    ],
}


def _copy_json(
    tmp_path: Path,
    *,
    indent: int = 2,
    trailing_nl: bool = True,
    legacy_g0: bool = False,
) -> Path:
    """把 live JSON 拷到 tmp_path。

    `legacy_g0=True` 时把 G0 块换成纠偏前形态，用于「未修正态」路径的断言 ——
    与 live 是否已 `--apply` 无关，故落盘前后行为一致。
    """
    data = json.loads(json.dumps(_LIVE_DATA))
    if legacy_g0:
        data["mappings"][_G0_IDX] = json.loads(json.dumps(LEGACY_G0_BLOCK))
    dst = tmp_path / "prefill_formula_mapping.json"
    text = json.dumps(data, indent=indent, ensure_ascii=False)
    dst.write_text(text + ("\n" if trailing_nl else ""), encoding="utf-8")
    return dst


def _invoke(monkeypatch: pytest.MonkeyPatch, json_path: Path, flag: str) -> int:
    monkeypatch.setattr(fix, "_JSON_PATH", json_path)
    monkeypatch.setattr(sys, "argv", ["fix_g0_prefill_presets.py", flag])
    return fix.main()


class TestProperty22ScriptIdempotenceAndRoundTrip:
    def test_real_file_roundtrip_reproduces_source_byte_for_byte(self) -> None:
        """实测本文件形态 = indent=2 + 默认分隔符 + 尾换行（别假设）。"""
        raw = _JSON_PATH.read_text(encoding="utf-8")
        assert fix.selfcheck_roundtrip(raw, json.loads(raw)) is None

    def test_roundtrip_selfcheck_reverse(self) -> None:
        """反向自检：换缩进即判失败（证明该自检非空转）。"""
        raw = json.dumps(_LIVE_DATA, indent=4, ensure_ascii=False) + "\n"
        assert fix.selfcheck_roundtrip(raw, json.loads(raw)) is not None

    def test_check_exits_1_when_pending_and_0_when_fixed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        target = _copy_json(tmp_path, legacy_g0=True)
        assert _invoke(monkeypatch, target, "--check") == 1, "未修正态 --check 应 exit 1"
        assert _invoke(monkeypatch, target, "--apply") == 0
        assert _invoke(monkeypatch, target, "--check") == 0, "已修正态 --check 应 exit 0"

    def test_legacy_fixture_really_is_unfixed(self) -> None:
        """反向自检：`LEGACY_G0_BLOCK` 确实是「未修正态」，否则上一条断言恒空转。

        🔴 这条是上一条的支点 —— 若哪天有人把 LEGACY_G0_BLOCK 顺手"修好"，
        「未修正态 --check 应 exit 1」会变成拿修正态去要求 exit 1 而莫名打红。
        """
        data = json.loads(json.dumps(_LIVE_DATA))
        data["mappings"][_G0_IDX] = json.loads(json.dumps(LEGACY_G0_BLOCK))
        _, changes = fix.plan(data, _CELL_REF_TEMPLATE)
        assert len(changes) == 12, f"遗留态应恰有 12 项欠账，实为 {len(changes)}：{changes}"

    def test_apply_from_legacy_reaches_target(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """从遗留态 --apply 必须精确到达目标态（不依赖 live 的当前状态）。"""
        target = _copy_json(tmp_path, legacy_g0=True)
        assert _invoke(monkeypatch, target, "--apply") == 0
        block = json.loads(target.read_text(encoding="utf-8"))["mappings"][_G0_IDX]
        assert block == fix.build_expected_block(LEGACY_G0_BLOCK, _CELL_REF_TEMPLATE)
        assert block["sheet"] == fix.EXPECTED_SHEET
        assert [c["cell_ref"] for c in block["cells"]] == [
            fix.render_cell_ref(_CELL_REF_TEMPLATE, s.category) for s in fix.BOOK_AMOUNT_SPECS
        ]

    def test_second_apply_is_zero_change(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        target = _copy_json(tmp_path)
        assert _invoke(monkeypatch, target, "--apply") == 0
        first = target.read_bytes()
        assert _invoke(monkeypatch, target, "--apply") == 0
        assert target.read_bytes() == first, "第二次 --apply 不应改变任何字节"
        _, changes = fix.plan(json.loads(target.read_text(encoding="utf-8")), _CELL_REF_TEMPLATE)
        assert changes == []

    def test_apply_only_touches_g0_block(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        target = _copy_json(tmp_path)
        before = fix.non_g0_snapshot(json.loads(target.read_text(encoding="utf-8")), _G0_IDX)
        assert _invoke(monkeypatch, target, "--apply") == 0
        after_data = json.loads(target.read_text(encoding="utf-8"))
        assert fix.non_g0_snapshot(after_data, _G0_IDX) == before
        assert len(after_data["mappings"]) == len(_LIVE_DATA["mappings"])

    def test_roundtrip_failure_exits_2_without_writing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        target = _copy_json(tmp_path, indent=4)
        before = target.read_bytes()
        assert _invoke(monkeypatch, target, "--apply") == 2
        assert target.read_bytes() == before, "round-trip 自检失败时绝不写盘"

    def test_dry_run_does_not_write(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        target = _copy_json(tmp_path)
        before = target.read_bytes()
        assert _invoke(monkeypatch, target, "--dry-run") == 0
        assert target.read_bytes() == before

    def test_multiple_g0_blocks_refuse_to_run(self) -> None:
        """并发会话若新增第二个 G0 块，脚本必须拒绝而不是任选一个改。"""
        data = json.loads(json.dumps(_LIVE_DATA))
        data["mappings"].append(json.loads(json.dumps(_LIVE_BLOCK)))
        with pytest.raises(SystemExit):
            fix.plan(data, _CELL_REF_TEMPLATE)

    def test_pending_state_is_loud_and_frozen(self) -> None:
        """把「尚未 apply」钉成显式基线 —— 部分 apply / 清单漂移立即打红。

        🔴 这条永不 skip，是 `TestProperty21LiveState` 的 skipif 不会变成假绿的支点。
        """
        if not _PENDING_CHANGES:
            # 已 apply：live 必须等于目标态，且 --check 干净
            assert _LIVE_BLOCK == _TARGET_BLOCK
            return
        kinds = [c.split(":")[0].split(" ")[0] for c in _PENDING_CHANGES]

        # 🔴 pending 基线有两种合法形态，取决于 live 落到了哪一轮：
        #    ① 遗留态（sheet=审定表G0-1 + 两个审定表锚点）→ 12 项 = 1/1/2/8
        #    ② 第一轮已 apply（sheet 与 8 个 cell_ref 已正确、formula 仍是按码 TB()）
        #       → 8 项全为 `cells~`（本轮 PLACEHOLDER 裁决的距离）
        #    ①的 12 项分布由 `test_legacy_fixture_really_is_unfixed` 独立钉死。
        if _LIVE_BLOCK["sheet"] == "审定表G0-1":
            assert len(_PENDING_CHANGES) == 12, (
                f"遗留态 pending 应恰为 12 项（sheet 1 + account_codes 1 + 删 2 + 增 8），"
                f"实为 {len(_PENDING_CHANGES)}：{_PENDING_CHANGES}"
            )
            assert kinds.count("sheet") == 1
            assert kinds.count("account_codes") == 1
            assert kinds.count("cells-") == 2
            assert kinds.count("cells+") == 8
            assert [c["cell_ref"] for c in _LIVE_BLOCK["cells"]] == ["期初余额", "未审数"]
            return

        assert _LIVE_BLOCK["sheet"] == fix.EXPECTED_SHEET
        assert len(_PENDING_CHANGES) == 8, (
            f"第二轮（PLACEHOLDER 裁决）pending 应恰为 8 项 cells~ 改公式，"
            f"实为 {len(_PENDING_CHANGES)}：{_PENDING_CHANGES}"
        )
        assert kinds.count("cells~") == 8
        assert kinds.count("cells+") == kinds.count("cells-") == 0
        assert kinds.count("sheet") == kinds.count("account_codes") == 0
        # live 仍是按码 TB()：cell_ref 与 account_codes 已对，只有 formula 待改
        assert [c["cell_ref"] for c in _LIVE_BLOCK["cells"]] == [
            c["cell_ref"] for c in _TARGET_BLOCK["cells"]
        ]
        assert all(c["formula_type"] == "TB" for c in _LIVE_BLOCK["cells"])
        assert all(_TB_CALL_RE.search(c["formula"]) for c in _LIVE_BLOCK["cells"])


# ═══════════════════════════ Property 23 ══════════════════════════════════════


def strip_py_comments_and_strings(src: str) -> str:
    """去掉注释与字符串字面量（含 docstring）—— 只留可执行代码形态。

    用 `tokenize` 而非正则：反向自检里的违规样例是字符串字面量，正则会把它数成真实断言。
    """
    out: list[str] = []
    last_line = 1
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type in (tokenize.COMMENT, tokenize.STRING):
            continue
        if tok.start[0] > last_line:
            out.append("\n" * (tok.start[0] - last_line))
            last_line = tok.start[0]
        out.append(tok.string)
        last_line = tok.end[0]
    return "".join(out)


def whole_block_dump_assertions(src: str) -> list[str]:
    """找出「对整块序列化结果做『不得出现』断言」的行（Req 9.5 禁止形态）。"""
    code = strip_py_comments_and_strings(src)
    bad: list[str] = []
    for line in code.splitlines():
        if "json.dumps" in line and (" not in " in line or "notin" in line):
            bad.append(line.strip())
    return bad


class TestProperty23GuardScansSemanticFieldsOnly:
    def test_guard_never_asserts_over_whole_block_dump(self) -> None:
        src = Path(__file__).read_text(encoding="utf-8")
        assert whole_block_dump_assertions(src) == []

    def test_detector_reverse_selfcheck(self) -> None:
        """反向自检：内联 fixture 里的违规形态必须被检出（不依赖真实文件恰好含反例）。"""
        fixture = 'assert "TB_SUM" not in json.dumps(block, ensure_ascii=False)\n'
        assert whole_block_dump_assertions(fixture) != []

    def test_strip_helper_reverse_selfcheck(self) -> None:
        """反向自检：注释与字符串确实被剥掉（否则上一条断言恒为空 = 空转）。"""
        fixture = '# json.dumps not in x\ny = "json.dumps not in z"\nw = 1\n'
        code = strip_py_comments_and_strings(fixture)
        assert "json.dumps" not in code
        assert "w" in code

    def test_scanner_reads_only_whitelisted_fields(self) -> None:
        body = _extract_py_function_body(Path(__file__).read_text(encoding="utf-8"),
                                        "def semantic_violations(")
        for field in ("sheet", "account_codes", "cell_ref", "formula"):
            assert field in body
        for forbidden in ("description", "formula_type", "wp_name", "wp_code"):
            assert forbidden not in body, f"语义扫描器不应读 {forbidden}"

    def test_description_with_banned_wording_still_passes(self) -> None:
        """核心反向自检：`description` 内写入被禁字样，守卫仍应通过。"""
        block = json.loads(json.dumps(_TARGET_BLOCK))
        block["cells"][0]["description"] = (
            "纠偏说明：原 TB_SUM('1101~1511','期末余额') 会把存货扫进投资循环，"
            "且原 sheet 写成 审定表G0-1（源 xlsx 无此 tab）"
        )
        bad = semantic_violations(
            block, sheetnames=_sheetnames(), chart_codes=_chart_codes()
        )
        assert bad == []

    def test_shipped_description_actually_carries_the_counterexample(self) -> None:
        """交付的描述确实写了反例 —— 让上一条自检落在真实数据上而非只在 fixture。"""
        descs = " ".join(c["description"] for c in _TARGET_BLOCK["cells"])
        assert "TB_SUM('1101~1511'" in descs
        assert _RANGE_RE.search(descs)
        # 本轮追加的第二个反例：连「按码 TB()」也不适用
        assert "按码 TB() 亦不适用" in descs
        assert "1504/1506/1507/1519/2101 全库零非零行" in descs
        assert "R4.3" in descs and "R3.5" in descs
        # 且这些反例只在 description 里，formula 侧仍然干净
        assert formula_account_code_literals(_TARGET_BLOCK) == []
        assert not any(_TB_CALL_RE.search(c["formula"]) for c in _TARGET_BLOCK["cells"])

    def test_script_selfcheck_also_scans_formula_only(self) -> None:
        data = json.loads(json.dumps(_LIVE_DATA))
        data["mappings"][_G0_IDX] = json.loads(json.dumps(_TARGET_BLOCK))
        assert fix.selfcheck_no_range_formula(data, _G0_IDX) is None
        data["mappings"][_G0_IDX]["cells"][0]["formula"] = "=TB_SUM('1101~1511','期末余额')"
        assert fix.selfcheck_no_range_formula(data, _G0_IDX) is not None


def _extract_py_function_body(src: str, marker: str) -> str:
    start = src.find(marker)
    assert start >= 0, f"未找到 {marker}"
    rest = src[start:]
    lines = rest.splitlines()
    body = [lines[0]]
    for line in lines[1:]:
        if line and not line[0].isspace() and not line.startswith(")"):
            break
        body.append(line)
    joined = "\n".join(body)
    assert len(body) > 5, "函数体截取失效（行数过少）"
    return strip_py_comments_and_strings(joined + "\n")
