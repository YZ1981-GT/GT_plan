"""H6 固定资产清理：层③（报表公式给的码）必须关闭；BS-028 补齐后 H1 / H6 的假冲突消失。

spec formula-fetch-followup-defect-closure R6.4。BS-028 是固定资产行，不是 H6 自己的行：2026-10-24 起四个准则的公式
都是 1601 − 1602 − 1603 + 1606。单槽规格允许层③时，客户科目表里没有叫「固定资产清理」的科目，就会把固定资产原值、
累计折旧、减值准备一并当成清理科目（层③排在层④兜底码之前）。
"""
from __future__ import annotations

import dataclasses
from types import SimpleNamespace

import pytest

from app.services.four_table.h1_account_scope import H1_ACCOUNT_SPEC
from app.services.four_table.h6_account_scope import H6_ACCOUNT_SPEC
from app.services.four_table.semantic_account_resolver import (
    RESOLVED_FROM_FALLBACK,
    RESOLVED_FROM_REPORT_CONFIG,
    resolve_semantic_accounts,
)

NEW_BS028 = "TB('1601','期末余额') - TB('1602','期末余额') - TB('1603','期末余额') + TB('1606','期末余额')"
OLD_BS028 = "TB('1601','期末余额') - TB('1602','期末余额')"  # 上市 / 国企合并原公式


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None


class _Session:
    """按 SQL 分派：科目表 / 报表公式；科目映射查无记录（标准码原样当原始码）。"""

    def __init__(self, chart, formula):
        self.chart = [SimpleNamespace(account_code=c, account_name=n, direction=d, source="standard")
                      for c, n, d in chart]
        self.formula = formula

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        if "account_chart" in sql:
            return _Result(self.chart)
        if "report_config" in sql:
            return _Result([SimpleNamespace(formula=self.formula)])
        return _Result([])


def _ctx(chart, formula):
    return SimpleNamespace(db=_Session(chart, formula), project_id="00000000-0000-0000-0000-000000000001", year=2025)


#: 本项目把清理科目建成别的名字（按名称两层都匹配不上「固定资产清理」）
_RENAMED_CHART = [("1601", "固定资产", "debit"), ("1602", "累计折旧", "credit"),
                  ("1603", "固定资产减值准备", "credit"), ("1606", "待清理资产", "debit")]
_FULL_CHART = [("1601", "固定资产", "debit"), ("1602", "累计折旧", "credit"),
               ("1603", "固定资产减值准备", "credit"), ("1606", "固定资产清理", "debit")]


def test_h6_spec_does_not_trust_the_fixed_assets_row():
    assert H6_ACCOUNT_SPEC.row_code == "BS-028" and H6_ACCOUNT_SPEC.trust_report_config is False


@pytest.mark.asyncio
async def test_h6_falls_back_to_its_own_code_not_to_the_whole_fixed_assets_row():
    got = await resolve_semantic_accounts(_ctx(_RENAMED_CHART, NEW_BS028), H6_ACCOUNT_SPEC)
    gross = got.slots["gross"]
    assert (gross.standard_codes, gross.resolved_from) == (["1606"], RESOLVED_FROM_FALLBACK)


@pytest.mark.asyncio
async def test_contrast_with_report_tier_open_takes_fixed_asset_accounts():
    """对照：同一项目、层③打开，固定资产原值 / 累计折旧 / 减值准备都被当成清理科目（关闭层③的理由）。"""
    trusting = dataclasses.replace(H6_ACCOUNT_SPEC, trust_report_config=True)
    got = await resolve_semantic_accounts(_ctx(_RENAMED_CHART, NEW_BS028), trusting)
    gross = got.slots["gross"]
    assert gross.resolved_from == RESOLVED_FROM_REPORT_CONFIG
    assert gross.standard_codes == ["1601", "1602", "1603", "1606"]


@pytest.mark.asyncio
@pytest.mark.parametrize(("spec", "formula", "expected"), [
    (H6_ACCOUNT_SPEC, OLD_BS028, [("gross", "1601,1602", "1606")]),
    (H6_ACCOUNT_SPEC, NEW_BS028, []),
    (H1_ACCOUNT_SPEC, OLD_BS028, [("impairment", "1601,1602", "1603")]),
    (H1_ACCOUNT_SPEC, NEW_BS028, []),
])
async def test_full_fixed_assets_formula_clears_false_conflicts(spec, formula, expected):
    """原公式不含 1603 / 1606：H1 的减值准备槽、H6 的清理槽恒报「报表公式与科目不一致」；补齐后不再报。"""
    got = await resolve_semantic_accounts(_ctx(_FULL_CHART, formula), spec)
    assert got.conflicts == expected
