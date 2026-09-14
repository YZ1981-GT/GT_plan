"""G6 其他债权投资 — 科目定位单一真源守卫.

🔴 **2026-08-01 重写**：本文件原先钉死的是**错值**。

原断言 ``_G6_ACCOUNT_PREFIX == "1505"``（依据 `report_config` 的
``BS-022 = TB('1505','期末余额')``），但 `account_chart` + `trial_balance.account_name`
双向实证 **``1505`` 实为「债权投资减值准备」**，其他债权投资的真实科目是 **``1506``**。
根因是 `report_config` 的 BS-022 / BS-025 / BS-026 **连续偏移一位**
（平台标准科目表在 ``1504 债权投资`` 与 ``1506 其他债权投资`` 之间插了
``1505 债权投资减值准备``，且其他非流动金融资产跳到 ``1519``）。

更进一步：**不再断言任何写死的科目码常量**。标准码在项目间并不一致
（`account_mapping` 同一原始码在不同项目映射到不同标准码；标准科目表本身各项目也不同），
科目一律由 `four_table/g_cycle_specs.G6_SPEC` 按**科目名**逐项目解析。
本文件因此改为断言：① 语义规格声明正确 ② render 源码不含任何写死的科目码
③ 公式预设的科目码是实证真值。

spec: .kiro/specs/g-cycle-extraction-mapping-and-disclosure-alignment/
      Requirements 2, 4 / Property 4, 8
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from app.services.four_table.g_cycle_specs import G6_SPEC
from app.services.four_table.semantic_account_resolver import (
    ChartRow,
    match_slot_in_chart,
)

_BACKEND = Path(__file__).resolve().parents[2]
_RENDER_MAIN = (
    _BACKEND / "app/routers/wp_render_strategies/_g6_other_bond_investment_main.py"
)
_RENDER_SERVICE = (
    _BACKEND
    / "app/routers/wp_render_strategies/_g6_other_bond_investment_main_service.py"
)
_RENDER_ECL = (
    _BACKEND / "app/routers/wp_render_strategies/_g6_other_bond_investment_ecl.py"
)
_PRESETS = _BACKEND / "data/prefill_formula_mapping.json"

#: 实证真值：其他债权投资 = 1506
G6_TRUE_CODE = "1506"

#: 禁止出现在 G6 源码 / 预设里的科目码（旧准则 + 别循环 + 自身错值）
G6_FORBIDDEN_CODES = (
    "1501",  # 持有至到期投资（旧准则）
    "1502",  # 持有至到期投资减值准备（旧准则）
    "1503",  # 可供出售金融资产（旧准则）—— G6 原实现用的就是它
    "1504",  # 债权投资（G4）
    "1505",  # 债权投资减值准备（G4 的备抵）—— 2026-08-01 曾误"纠正"为它
    "1507",  # 其他权益工具投资（G8）
    "1510",
    "1519",  # 其他非流动金融资产（G9）
    "1531",  # 长期应收款（G5）
)


def _strip_py_comments(src: str) -> str:
    """剥 Python 注释与 docstring（缺陷说明里会写反例科目码，不剥必误判）。"""
    out = re.sub(r'"""[\s\S]*?"""', "", src)
    out = re.sub(r"'''[\s\S]*?'''", "", out)
    return re.sub(r"(?m)#.*$", "", out)


# ─── 语义规格声明 ──────────────────────────────────────────────────────


class TestSemanticSpec:
    def test_row_code_is_bs_022(self):
        """报表行仍是 BS-022（只作提示 + 冲突检测，不是定位依据）。"""
        assert G6_SPEC.row_code == "BS-022"

    def test_single_gross_slot_no_provision(self):
        """G6 无备抵槽（CAS22 FVOCI-Debt 减值在 OCI 确认，不冲减账面价值）。"""
        assert [s.key for s in G6_SPEC.slots] == ["gross"]
        assert G6_SPEC.slots[0].is_provision is False

    def test_slot_declares_account_name_not_code(self):
        assert G6_SPEC.slots[0].names == ("其他债权投资",)

    def test_fallback_is_evidenced_true_code(self):
        """兜底码必须是实证真值 1506（原为 1505 = 债权投资减值准备）。"""
        assert G6_SPEC.slots[0].fallback_standard_codes == (G6_TRUE_CODE,)

    def test_legacy_accounts_flagged_for_manual_mapping(self):
        """旧准则科目需人工按 SPPI 拆分 → 声明在 legacy_standard_names，不自动归槽。"""
        assert "可供出售金融资产" in G6_SPEC.legacy_standard_names
        assert "持有至到期投资" in G6_SPEC.legacy_standard_names


class TestNameMatching:
    #: 平台标准科目表实证片段（同一份 6 个项目一致）
    CHART = [
        ChartRow("1503", "可供出售金融资产", "standard", "debit"),
        ChartRow("1504", "债权投资", "standard", "debit"),
        ChartRow("1505", "债权投资减值准备", "standard", "debit"),
        ChartRow("1506", "其他债权投资", "standard", "debit"),
        ChartRow("1507", "其他权益工具投资", "standard", "debit"),
    ]

    def test_hits_1506_exactly(self):
        rows, exact = match_slot_in_chart(G6_SPEC.slots[0], self.CHART)
        assert exact is True
        assert [r.account_code for r in rows] == [G6_TRUE_CODE]

    def test_never_hits_g4_or_g8_accounts(self):
        rows, _ = match_slot_in_chart(G6_SPEC.slots[0], self.CHART)
        codes = {r.account_code for r in rows}
        for bad in ("1503", "1504", "1505", "1507"):
            assert bad not in codes, f"G6 命中了外来科目 {bad}"

    def test_reverse_check_债权投资_would_match_without_exact_priority(self):
        """反向自检：`其他债权投资` **包含** `债权投资` —— 证明精确优先是必要的。"""
        from app.services.four_table.semantic_account_resolver import (
            SemanticAccountSlot,
        )

        loose = SemanticAccountSlot(key="x", names=("债权投资",))
        rows, exact = match_slot_in_chart(loose, self.CHART)
        # 精确匹配命中 1504（债权投资本身），若无精确优先则包含匹配会同时命中 1506
        assert exact is True and [r.account_code for r in rows] == ["1504"]


# ─── 源码不得写死科目码 ────────────────────────────────────────────────


class TestNoHardcodedCodes:
    def test_sources_readable(self):
        for p in (_RENDER_MAIN, _RENDER_SERVICE, _RENDER_ECL):
            assert p.exists(), f"缺文件 {p}"
            assert len(p.read_text(encoding="utf-8")) > 500

    def test_no_forbidden_code_literals_in_any_g6_source(self):
        """三个 G6 render 源码（去注释后）均不得出现被禁科目码字面量。"""
        for p in (_RENDER_MAIN, _RENDER_SERVICE, _RENDER_ECL):
            clean = _strip_py_comments(p.read_text(encoding="utf-8"))
            found = {
                c for c in G6_FORBIDDEN_CODES if re.search(rf"['\"]{c}['\"]", clean)
            }
            assert not found, f"{p.name} 残留被禁科目码 {sorted(found)}"

    def test_no_prefix_constant_remains(self):
        """不得再留 ``_G6_ACCOUNT_PREFIX`` 之类的写死常量（单一真源在 G6_SPEC）。"""
        for p in (_RENDER_MAIN, _RENDER_SERVICE):
            clean = _strip_py_comments(p.read_text(encoding="utf-8"))
            assert "_G6_ACCOUNT_PREFIX" not in clean, f"{p.name} 仍有写死前缀常量"
            assert "_ACCOUNT_PREFIX =" not in clean, f"{p.name} 仍有写死前缀常量"

    def test_sources_reference_the_single_source_spec(self):
        for p in (_RENDER_MAIN, _RENDER_SERVICE, _RENDER_ECL):
            src = p.read_text(encoding="utf-8")
            assert "G6_SPEC" in src, f"{p.name} 未引用语义规格单一真源"

    def test_service_uses_leaf_aggregation_not_naked_startswith(self):
        """service 层的 tb_balance 聚合必须走共享件（点号边界 + 叶子口径）。"""
        clean = _strip_py_comments(_RENDER_SERVICE.read_text(encoding="utf-8"))
        assert "select_leaves" in clean and "filter_by_prefixes" in clean
        assert "startswith(_ACCOUNT_PREFIX)" not in clean

    def test_reverse_check_strip_comments_actually_strips(self):
        """反向自检：剥注释前源码确实含被禁码（缺陷说明保留在 docstring 里）。"""
        raw = _RENDER_MAIN.read_text(encoding="utf-8")
        assert "1503" in raw, "docstring 应保留缺陷说明（含 1503）"
        assert "1503" not in _strip_py_comments(raw)

    def test_reverse_check_regex_catches_planted_literal(self):
        planted = "code = '1505'\n"
        found = {c for c in G6_FORBIDDEN_CODES if re.search(rf"['\"]{c}['\"]", planted)}
        assert found == {"1505"}


# ─── 公式预设 ──────────────────────────────────────────────────────────


class TestFormulaPresets:
    @staticmethod
    def _g6_blocks() -> list[dict]:
        data = json.loads(_PRESETS.read_text(encoding="utf-8"))
        return [e for e in data.get("mappings", []) if e.get("wp_code") == "G6"]

    @classmethod
    def _all_codes(cls) -> set[str]:
        codes: set[str] = set()
        for entry in cls._g6_blocks():
            codes.update(entry.get("account_codes", []))
            for cell in entry.get("cells", []):
                codes.update(re.findall(r"'(\d{4}[\d.]*)'", cell.get("formula", "")))
        return codes

    def test_has_blocks(self):
        assert len(self._g6_blocks()) >= 2, "G6 至少应有审定表与明细表两块预设"

    def test_uses_evidenced_true_code(self):
        codes = self._all_codes()
        assert any(c.startswith(G6_TRUE_CODE) for c in codes), (
            f"G6 预设必须引用实证真值 {G6_TRUE_CODE}，实得 {sorted(codes)}"
        )

    def test_no_forbidden_codes(self):
        codes = self._all_codes()
        forbidden = {c for c in codes if c.split(".")[0] in G6_FORBIDDEN_CODES}
        assert not forbidden, f"G6 预设仍含被禁科目码：{sorted(forbidden)}"

    def test_no_hardcoded_aux(self):
        """不得含硬编码客户 / 项目名的 AUX 公式（项目专属污染）。"""
        for entry in self._g6_blocks():
            for cell in entry.get("cells", []):
                formula = cell.get("formula", "")
                assert "AUX(" not in formula, (
                    f"G6 预设含硬编码 AUX：{cell.get('cell_ref')}: {formula}"
                )

    def test_sheets_exist_in_source_template(self):
        """每个预设块的 sheet 必须存在于源 xlsx（防幽灵 sheet 永不命中）。"""
        try:
            from openpyxl import load_workbook
        except ImportError:  # pragma: no cover
            return
        src = _BACKEND / "wp_templates/G/G6 其他债权投资.xlsx"
        if not src.exists():  # pragma: no cover
            return
        wb = load_workbook(src, read_only=True)
        names = set(wb.sheetnames)
        wb.close()
        for entry in self._g6_blocks():
            sheet = entry.get("sheet")
            assert sheet in names, f"G6 预设 sheet「{sheet}」不在源 xlsx（幽灵块）"
