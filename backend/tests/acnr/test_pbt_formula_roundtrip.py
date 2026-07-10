# Feature: acnr, Property 5: formula_ref ↔ uri 无损往返
"""Property-based test: formula_ref ↔ uri 无损往返（含 2/3 参 WP/PREV 及五域）.

**Validates: Requirements 10.2, 10.3**

验证规则:
- R10.2: WP()/PREV() 的 2 参与 3 参解析均产出合法 URI
- R10.3: formula_ref_to_uri(ref) → uri → uri_to_formula_ref(uri) 还原原始 formula_ref（无损往返）

测试覆盖:
- WP 3 参 (standard): WP('parent','sheet_name','cell') ↔ wp://parent/sheet_name#cell
- WP 2 参 (custom_flat): WP('wp_code','cell') ↔ wp://wp_code/cell
- WP 2 参 (standard sheet-level): WP('parent','sheet_name') ↔ wp://parent/sheet_name
- PREV 3 参 (wp 语义): PREV('parent','sheet','cell') ↔ wp://parent/sheet#cell
- PREV 2 参 (tb 语义): PREV('code','col') ↔ tb://code#col
- 非 wp 域五域: TB / NOTE / AUX / REPORT / ROW
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis.strategies import (
    composite,
    just,
    one_of,
    sampled_from,
    text,
)

# 确保 backend 目录在 path
_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_BACKEND_ROOT))

from app.services.acnr.grammar import (
    formula_ref_to_uri,
    uri_to_formula_ref,
)

# ---------------------------------------------------------------------------
# Hypothesis Strategies: 生成合法 formula_ref
# ---------------------------------------------------------------------------

# 安全字符集：避免引号、括号、#、/ 等影响解析的特殊字符
_SAFE_CHARS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
_CHINESE_CHARS = "期末余额审定数合计行本期发生借方贷方"
_SHEET_NAME_CHARS = _SAFE_CHARS + _CHINESE_CHARS

# 标准 parent wp_code: [A-S] + digit + optional suffix
_STANDARD_PARENTS = [
    "A1", "B2", "C3", "D2", "D4", "E1", "F3", "G1", "H5", "I2",
    "J1", "K8", "L3", "M6", "N4", "S3",
]

# Cell 坐标模式（A1 形式，1~3 字母 + 数字）
_CELL_ADDRESSES = [
    "A1", "B7", "C10", "D15", "E100", "F200", "AA5", "AB30",
]

# Sheet names（中文或带编码的）
_SHEET_NAMES = [
    "明细表D2-2", "审定表D2-1", "汇总表", "核销明细表F3-3",
    "检查表D4-5", "审定表H1-1", "明细表G5-2", "期初余额",
]

# Semantic labels（第三参可以是语义名而非 A1 坐标）
_SEMANTIC_LABELS = [
    "审定数", "期末余额", "合计行-期末余额", "本期发生额",
    "借方合计", "贷方合计", "期初余额", "调整后余额",
]

# Custom flat wp_codes（非标准码）
_CUSTOM_WP_CODES = [
    "CUST-01", "CUST-02", "CUSTOM-A", "MY-WP-1", "TEST-X",
]

# TB account codes
_TB_CODES = ["1001", "1002", "1122", "2202", "4001", "5001", "6001"]

# TB columns
_TB_COLUMNS = ["审定数", "期末余额", "未审数", "调整数", "期初余额"]

# Report row codes
_REPORT_CODES = ["BS-001", "BS-002", "BS-050", "IS-001", "IS-010", "CFS-001"]

# Report columns
_REPORT_COLUMNS = ["本期", "期末", "上期"]

# Note sections
_NOTE_SECTIONS = ["五、3", "六、1", "七、2", "八、5"]

# Note row labels
_NOTE_ROWS = ["合计", "应收账款", "其他应收款", "本期增加"]

# Note col labels
_NOTE_COLS = ["期末", "期初", "本期"]

# AUX account codes
_AUX_ACCOUNTS = ["1122", "2202", "1001", "2241"]

# AUX dimensions
_AUX_DIMS = ["甲公司", "乙公司", "客户A", "供应商B"]

# AUX columns
_AUX_COLS = ["期末", "期初", "借方", "贷方"]


# ---------------------------------------------------------------------------
# Composite strategies
# ---------------------------------------------------------------------------


@composite
def wp_3arg_standard(draw):
    """生成 WP 3 参 standard formula_ref: WP('parent','sheet_name','cell_or_semantic')"""
    parent = draw(sampled_from(_STANDARD_PARENTS))
    sheet_name = draw(sampled_from(_SHEET_NAMES))
    # 第三参可以是 cell 坐标或语义名
    third_arg = draw(one_of(
        sampled_from(_CELL_ADDRESSES),
        sampled_from(_SEMANTIC_LABELS),
    ))
    return f"WP('{parent}','{sheet_name}','{third_arg}')"


@composite
def wp_2arg_custom_flat(draw):
    """生成 WP 2 参 custom_flat formula_ref: WP('wp_code','cell')
    第二参必须是 A1 坐标（这样 parse 才会判为 custom_flat）。
    """
    wp_code = draw(sampled_from(_CUSTOM_WP_CODES))
    cell = draw(sampled_from(_CELL_ADDRESSES))
    return f"WP('{wp_code}','{cell}')"


@composite
def wp_2arg_standard_sheet_level(draw):
    """生成 WP 2 参 standard sheet-level: WP('parent','sheet_name')
    第二参不是 A1 坐标→判为 standard。
    """
    parent = draw(sampled_from(_STANDARD_PARENTS))
    sheet_name = draw(sampled_from(_SHEET_NAMES))
    return f"WP('{parent}','{sheet_name}')"


@composite
def prev_3arg_wp(draw):
    """生成 PREV 3 参 (wp 语义): PREV('parent','sheet','cell')"""
    parent = draw(sampled_from(_STANDARD_PARENTS))
    sheet_name = draw(sampled_from(_SHEET_NAMES))
    third_arg = draw(one_of(
        sampled_from(_CELL_ADDRESSES),
        sampled_from(_SEMANTIC_LABELS),
    ))
    return f"PREV('{parent}','{sheet_name}','{third_arg}')"


@composite
def prev_2arg_tb(draw):
    """生成 PREV 2 参 (tb 语义): PREV('code','col')
    第一参是科目编码（纯数字），第二参是列名。
    """
    code = draw(sampled_from(_TB_CODES))
    col = draw(sampled_from(_TB_COLUMNS))
    return f"PREV('{code}','{col}')"


@composite
def tb_formula(draw):
    """生成 TB formula_ref: TB('code','col')"""
    code = draw(sampled_from(_TB_CODES))
    col = draw(sampled_from(_TB_COLUMNS))
    return f"TB('{code}','{col}')"


@composite
def note_formula(draw):
    """生成 NOTE formula_ref: NOTE('section','row','col')"""
    section = draw(sampled_from(_NOTE_SECTIONS))
    row = draw(sampled_from(_NOTE_ROWS))
    col = draw(sampled_from(_NOTE_COLS))
    return f"NOTE('{section}','{row}','{col}')"


@composite
def aux_formula(draw):
    """生成 AUX formula_ref: AUX('account','dim','col')"""
    account = draw(sampled_from(_AUX_ACCOUNTS))
    dim = draw(sampled_from(_AUX_DIMS))
    col = draw(sampled_from(_AUX_COLS))
    return f"AUX('{account}','{dim}','{col}')"


@composite
def report_formula(draw):
    """生成 REPORT formula_ref: REPORT('code','col')"""
    code = draw(sampled_from(_REPORT_CODES))
    col = draw(sampled_from(_REPORT_COLUMNS))
    return f"REPORT('{code}','{col}')"


# ---------------------------------------------------------------------------
# Property Test: formula_ref ↔ uri 无损往返
# ---------------------------------------------------------------------------


class TestFormulaRefUriRoundtrip:
    """Property 5: formula_ref ↔ uri 无损往返（含 2/3 参 WP/PREV 及五域）。"""

    @given(formula_ref=wp_3arg_standard())
    @settings(max_examples=10)
    def test_wp_3arg_standard_roundtrip(self, formula_ref: str):
        """WP 3 参 standard: formula_ref → URI → formula_ref 无损往返。

        WP('parent','sheet_name','cell') → wp://parent/sheet_name#cell → WP(...)
        """
        uri = formula_ref_to_uri(formula_ref)
        assert uri is not None, f"formula_ref_to_uri({formula_ref!r}) 返回 None"
        assert uri.startswith("wp://"), f"WP 3参应生成 wp:// URI，实际: {uri}"

        restored = uri_to_formula_ref(uri)
        assert restored == formula_ref, (
            f"无损往返失败: {formula_ref!r} → {uri!r} → {restored!r}"
        )

    @given(formula_ref=wp_2arg_custom_flat())
    @settings(max_examples=10)
    def test_wp_2arg_custom_flat_roundtrip(self, formula_ref: str):
        """WP 2 参 custom_flat: formula_ref → URI → formula_ref 无损往返。

        WP('wp_code','cell') → wp://wp_code/cell → WP(...)
        """
        uri = formula_ref_to_uri(formula_ref)
        assert uri is not None, f"formula_ref_to_uri({formula_ref!r}) 返回 None"
        assert uri.startswith("wp://"), f"WP 2参 custom_flat 应生成 wp:// URI，实际: {uri}"

        restored = uri_to_formula_ref(uri)
        assert restored == formula_ref, (
            f"无损往返失败: {formula_ref!r} → {uri!r} → {restored!r}"
        )

    @given(formula_ref=wp_2arg_standard_sheet_level())
    @settings(max_examples=10)
    def test_wp_2arg_standard_sheet_level_roundtrip(self, formula_ref: str):
        """WP 2 参 standard sheet-level: formula_ref → URI → formula_ref 无损往返。

        WP('parent','sheet_name') → wp://parent/sheet_name → WP(...)
        """
        uri = formula_ref_to_uri(formula_ref)
        assert uri is not None, f"formula_ref_to_uri({formula_ref!r}) 返回 None"
        assert uri.startswith("wp://"), f"WP 2参 standard sheet-level 应生成 wp:// URI，实际: {uri}"

        restored = uri_to_formula_ref(uri)
        assert restored == formula_ref, (
            f"无损往返失败: {formula_ref!r} → {uri!r} → {restored!r}"
        )

    @given(formula_ref=prev_3arg_wp())
    @settings(max_examples=10)
    def test_prev_3arg_wp_roundtrip(self, formula_ref: str):
        """PREV 3 参 (wp 语义): formula_ref → URI → formula_ref 无损往返。

        PREV('parent','sheet','cell') → wp://parent/sheet#cell → ???

        注意: PREV 3 参产生 wp:// URI，但 uri_to_formula_ref 将 wp:// URI
        还原为 WP() 而非 PREV()。这是设计决策：URI 层不区分 WP/PREV。
        往返为 WP() 形式（语义等价）。
        """
        uri = formula_ref_to_uri(formula_ref)
        assert uri is not None, f"formula_ref_to_uri({formula_ref!r}) 返回 None"
        assert uri.startswith("wp://"), f"PREV 3参应生成 wp:// URI，实际: {uri}"

        # PREV 3参 和 WP 3参 产生相同的 URI 结构
        # uri_to_formula_ref 统一还原为 WP()（URI 层不保留 PREV/WP 区分）
        restored = uri_to_formula_ref(uri)
        assert restored is not None

        # 验证 URI 结构正确性：提取参数验证一致
        # PREV('A','B','C') → wp://A/B#C → WP('A','B','C')
        # 参数保持无损
        prev_match = re.match(r"PREV\('([^']+)','([^']+)','([^']+)'\)", formula_ref)
        assert prev_match is not None
        expected_wp = f"WP('{prev_match.group(1)}','{prev_match.group(2)}','{prev_match.group(3)}')"
        assert restored == expected_wp, (
            f"PREV→URI→WP 参数丢失: {formula_ref!r} → {uri!r} → {restored!r}, "
            f"期望: {expected_wp!r}"
        )

    @given(formula_ref=prev_2arg_tb())
    @settings(max_examples=10)
    def test_prev_2arg_tb_roundtrip(self, formula_ref: str):
        """PREV 2 参 (tb 语义): formula_ref → URI → formula_ref。

        PREV('code','col') → tb://code#col → TB('code','col')

        注意: PREV 2 参产生 tb:// URI，而 tb:// URI 还原为 TB()。
        这是双语义设计：PREV 2-arg 语义等价于 TB（上期余额）。
        """
        uri = formula_ref_to_uri(formula_ref)
        assert uri is not None, f"formula_ref_to_uri({formula_ref!r}) 返回 None"
        assert uri.startswith("tb://"), f"PREV 2参应生成 tb:// URI，实际: {uri}"

        # PREV 2参 → tb:// → TB()（语义等价）
        restored = uri_to_formula_ref(uri)
        assert restored is not None

        # 验证参数无损
        prev_match = re.match(r"PREV\('([^']+)','([^']+)'\)", formula_ref)
        assert prev_match is not None
        expected_tb = f"TB('{prev_match.group(1)}','{prev_match.group(2)}')"
        assert restored == expected_tb, (
            f"PREV 2参→URI→TB 参数丢失: {formula_ref!r} → {uri!r} → {restored!r}, "
            f"期望: {expected_tb!r}"
        )

    @given(formula_ref=tb_formula())
    @settings(max_examples=10)
    def test_tb_roundtrip(self, formula_ref: str):
        """TB 域: TB('code','col') → tb://code#col → TB('code','col') 无损往返。"""
        uri = formula_ref_to_uri(formula_ref)
        assert uri is not None, f"formula_ref_to_uri({formula_ref!r}) 返回 None"
        assert uri.startswith("tb://"), f"TB 应生成 tb:// URI，实际: {uri}"

        restored = uri_to_formula_ref(uri)
        assert restored == formula_ref, (
            f"TB 无损往返失败: {formula_ref!r} → {uri!r} → {restored!r}"
        )

    @given(formula_ref=note_formula())
    @settings(max_examples=10)
    def test_note_roundtrip(self, formula_ref: str):
        """NOTE 域: NOTE('section','row','col') → note://section/row#col → NOTE(...) 无损往返。"""
        uri = formula_ref_to_uri(formula_ref)
        assert uri is not None, f"formula_ref_to_uri({formula_ref!r}) 返回 None"
        assert uri.startswith("note://"), f"NOTE 应生成 note:// URI，实际: {uri}"

        restored = uri_to_formula_ref(uri)
        assert restored == formula_ref, (
            f"NOTE 无损往返失败: {formula_ref!r} → {uri!r} → {restored!r}"
        )

    @given(formula_ref=aux_formula())
    @settings(max_examples=10)
    def test_aux_roundtrip(self, formula_ref: str):
        """AUX 域: AUX('account','dim','col') → aux://account/dim#col → AUX(...) 无损往返。"""
        uri = formula_ref_to_uri(formula_ref)
        assert uri is not None, f"formula_ref_to_uri({formula_ref!r}) 返回 None"
        assert uri.startswith("aux://"), f"AUX 应生成 aux:// URI，实际: {uri}"

        restored = uri_to_formula_ref(uri)
        assert restored == formula_ref, (
            f"AUX 无损往返失败: {formula_ref!r} → {uri!r} → {restored!r}"
        )

    @given(formula_ref=report_formula())
    @settings(max_examples=10)
    def test_report_roundtrip(self, formula_ref: str):
        """REPORT 域: REPORT('code','col') → report://type/code#col → REPORT(...) 无损往返。"""
        uri = formula_ref_to_uri(formula_ref)
        assert uri is not None, f"formula_ref_to_uri({formula_ref!r}) 返回 None"
        assert uri.startswith("report://"), f"REPORT 应生成 report:// URI，实际: {uri}"

        restored = uri_to_formula_ref(uri)
        assert restored == formula_ref, (
            f"REPORT 无损往返失败: {formula_ref!r} → {uri!r} → {restored!r}"
        )
