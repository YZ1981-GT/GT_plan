# -*- coding: utf-8 -*-
"""D567 Property 3/12: 四组双区红判据 + 历史残留 sheet 排除。

spec: d567-sync-coverage-via-row-table-engine · Task 4 · Requirements 2.3, 2.5, 3.1, 3.4, 6.6

═══ Property 3: 四组双区各自受管区数正确，两键均读回等值 ═══

现阶段是**红基线**：四组双区（D6-6/D6-9/D7-4/D7-7）尚未接入 ⇒ 当前受管区只有 1。
Task 14-17 接入时从红转绿（归因于接入改动）。

═══ Property 12: 历史残留 sheet 被显式排除且分派正则不误判 ═══

D6 册的 `合同资产实质性程序表 D7A（原）`（104r）与 D7 册的 `合同负债实质性程序表 D8A（原）`（66r）
是历史残留，不得进入受管 sheet 清单。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.workpaper_sync.phase5_d5_receivables_financing import (
    load_contract_from_disk as d5_contract,
)
from app.services.workpaper_sync.phase5_d6_contract_assets import (
    load_contract_from_disk as d6_contract,
)
from app.services.workpaper_sync.phase5_d7_contract_liabilities import (
    load_contract_from_disk as d7_contract,
)


def _table_count(contract) -> int:
    return sum(len(s.tables) for s in contract.sheets)


def _sheet_keys(contract) -> list[str]:
    return [s.sheet_key for s in contract.sheets]


def _sheet_names(contract) -> list[str]:
    return [s.excel_name for s in contract.sheets]


# ═══════════════════════════════════════════════════════════════════════════════
# Property 3: 四组双区红基线（现状各 1 table ⇒ 必红）
# ═══════════════════════════════════════════════════════════════════════════════


class TestProperty3DualZoneRedBaseline:
    """Property 3 红基线：四组双区尚未接入，当前契约只有已接明细。"""

    def test_d6_current_managed_region_count(self) -> None:
        """D6 现状 11 table（d62 1 + d63 1 + d65 1 + d68 1 + d66 2 + d69 2 + d61-adj 3 sections）。"""
        c = d6_contract()
        count = _table_count(c)
        assert count == 11, f"D6 应为 11 table，实得 {count}"

    def test_d7_current_managed_region_count(self) -> None:
        """D7 现状 9 table（d72 1 + d75 1 + d76 1 + d74 2 + d77 2 + d71-adj 2 sections）。"""
        c = d7_contract()
        count = _table_count(c)
        assert count == 9, f"D7 应为 9 table，实得 {count}"

    def test_d5_current_managed_region_count(self) -> None:
        """D5 现状 3 个 table（d52 1 + d54 1 + d51-adj 1 section）。"""
        c = d5_contract()
        count = _table_count(c)
        assert count == 3, f"D5 应为 3 table，实得 {count}"

    def test_d6_6_dual_zone_now_present(self) -> None:
        """D6-6 合同资产检查表已接入 ⇒ 契约中有 d66-managed（2 tables）。"""
        c = d6_contract()
        assert "d66-managed" in _sheet_keys(c)

    def test_d6_9_dual_zone_now_present(self) -> None:
        """D6-9 转回核销检查表已接入 ⇒ 契约中有 d69-managed（2 tables）。"""
        c = d6_contract()
        assert "d69-managed" in _sheet_keys(c)

    def test_d7_4_dual_zone_now_present(self) -> None:
        """D7-4 分析表已接入 ⇒ 契约中有 d74-managed（2 tables）。"""
        c = d7_contract()
        assert "d74-managed" in _sheet_keys(c)

    def test_d7_7_dual_zone_now_present(self) -> None:
        """D7-7 检查表已接入 ⇒ 契约中有 d77-managed（2 tables）。"""
        c = d7_contract()
        assert "d77-managed" in _sheet_keys(c)


# ═══════════════════════════════════════════════════════════════════════════════
# Property 12: 历史残留 sheet 排除
# ═══════════════════════════════════════════════════════════════════════════════

# 残留 sheet 的实测真名（openpyxl 直读确认）
_D6_RESIDUAL = "合同资产实质性程序表 D7A（原）"
_D7_RESIDUAL = "合同负债实质性程序表 D8A（原）"


class TestProperty12ResidualSheetExclusion:
    """Property 12: 历史残留 sheet 不得进入受管清单。"""

    def test_d6_residual_not_in_contract(self) -> None:
        """D6 册的 `合同资产实质性程序表 D7A（原）` 不在契约 sheets 中。"""
        c = d6_contract()
        names = _sheet_names(c)
        assert _D6_RESIDUAL not in names, f"残留 sheet {_D6_RESIDUAL!r} 不应在契约中"

    def test_d7_residual_not_in_contract(self) -> None:
        """D7 册的 `合同负债实质性程序表 D8A（原）` 不在契约 sheets 中。"""
        c = d7_contract()
        names = _sheet_names(c)
        assert _D7_RESIDUAL not in names, f"残留 sheet {_D7_RESIDUAL!r} 不应在契约中"

    def test_residual_sheet_names_contain_marker(self) -> None:
        """残留 sheet 名含（原）标记，分派正则据此排除。"""
        assert "（原）" in _D6_RESIDUAL
        assert "（原）" in _D7_RESIDUAL

    def test_d6_residual_exists_in_template(self) -> None:
        """确认残留 sheet 真实存在于模板中（不是凭空断言）。"""
        from openpyxl import load_workbook
        tpl = _BACKEND / "wp_templates" / "D" / "D6 合同资产.xlsx"
        wb = load_workbook(tpl, read_only=True)
        assert _D6_RESIDUAL in wb.sheetnames, f"模板中未找到 {_D6_RESIDUAL!r}"
        wb.close()

    def test_d7_residual_exists_in_template(self) -> None:
        """确认残留 sheet 真实存在于模板中。"""
        from openpyxl import load_workbook
        tpl = _BACKEND / "wp_templates" / "D" / "D7 合同负债.xlsx"
        wb = load_workbook(tpl, read_only=True)
        assert _D7_RESIDUAL in wb.sheetnames, f"模板中未找到 {_D7_RESIDUAL!r}"
        wb.close()
