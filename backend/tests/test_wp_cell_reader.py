"""``WpCellRead`` 的 J1 两字段 ``reason_code`` / ``raw``（acnr-foundation-defect-closure T11，design §2.4 回退流程 B）。

两字段默认 None、只增不改：三态与中文原因由 ``test_wp_cell_reader_contract.py`` 钉住，这里逐条返回路径钉
``reason_code`` 与 reason 一一对应、``raw`` 在找到单元格时为原文。另有 AST 守卫：模块里每个非 ok 的
``WpCellRead(...)`` 构造都显式给了 ``reason_code``（新增返回路径忘填即红）。
"""
from __future__ import annotations

import ast
import dataclasses
import inspect
from decimal import Decimal

import pytest
from tests.test_wp_cell_reader_contract import _read, world  # noqa: F401  (fixture)

from app.services import wp_cell_reader
from app.services.wp_cell_reader import CatalogSheetKeys, WpCellRead

#: 机器码 ↔ 中文原因（前缀）；year_unknown 是 §8.2「项目未设置审计年度」那条，T11 原文七个码之外的第八个
REASON_CODES = {
    "year_unknown": "项目未设置审计年度",
    "year_mismatch": "底稿年度与项目年度不符",
    "wp_missing": "项目中没有底稿",
    "wp_ambiguous": "底稿记录有歧义",
    "sheet_ambiguous": ("工作表名有歧义", "该别名不能用于取值", "同一工作表有多份数据"),
    "sheet_missing": "没有该工作表的数据",
    "cell_empty": "单元格未录入",
    "non_numeric": "单元格内容不是数值",
}


def _assert_pair(read: WpCellRead, code: str) -> None:
    assert read.reason_code == code, (read.reason_code, read.reason)
    prefixes = REASON_CODES[code]
    prefixes = prefixes if isinstance(prefixes, tuple) else (prefixes,)
    assert read.reason and read.reason.startswith(prefixes), (code, read.reason)


def test_two_fields_default_none():
    fields = {f.name: f for f in dataclasses.fields(WpCellRead)}
    assert fields["reason_code"].default is None and fields["raw"].default is None
    assert WpCellRead("ok", Decimal("1"), None, None, None).reason_code is None


@pytest.mark.parametrize("audit_year, code", [(None, "year_unknown"), (2024, "year_mismatch")])
async def test_year_paths(world, monkeypatch, audit_year, code):
    async def _fake(db, project_id):
        return audit_year

    monkeypatch.setattr(wp_cell_reader, "fetch_project_audit_year", _fake)
    read = await _read(world, "E1", "货币资金审定表E1-1", "C10", year=2025)
    _assert_pair(read, code)
    assert read.raw is None


@pytest.mark.parametrize("wp_code, sheet, cell, code", [
    ("Z9", None, "A1", "wp_missing"),
    ("D2", None, "A1", "wp_ambiguous"),
    ("E1", None, "Z99", "cell_empty"),
    ("E1", "不存在的表", "C10", "sheet_missing"),
    ("E1", "货币资金审定表E1-1", "Z99", "cell_empty"),
])
async def test_paths_without_cell_have_no_raw(world, wp_code, sheet, cell, code):
    read = await _read(world, wp_code, sheet, cell)
    _assert_pair(read, code)
    assert read.raw is None


@pytest.mark.parametrize("verdict", ["ambiguous", "alias_forbidden"])
async def test_catalog_verdict_paths(world, monkeypatch, verdict):
    monkeypatch.setattr(wp_cell_reader, "_catalog_sheet_keys",
                        lambda wp_code, key: CatalogSheetKeys(frozenset(), verdict, ("E1/E1-1",)))
    read = await _read(world, "E1", "货币资金", "C10")
    _assert_pair(read, "sheet_ambiguous")
    assert read.raw is None


async def test_multiple_values_path(world, monkeypatch):
    monkeypatch.setattr(wp_cell_reader, "_catalog_sheet_keys", lambda wp_code, key: CatalogSheetKeys(
        frozenset({"货币资金审定表E1-1", "货币资金分析表E1-14"}), "found"))
    read = await _read(world, "E1", "货币资金审定表E1-1", "C10")
    _assert_pair(read, "sheet_ambiguous")
    assert read.raw is None


async def test_found_cell_paths_carry_raw(world):
    empty = await _read(world, "E1", "货币资金审定表E1-1", "E3")
    _assert_pair(empty, "cell_empty")
    assert empty.raw == ""
    text = await _read(world, "E1", "货币资金审定表E1-1", "D5")
    _assert_pair(text, "non_numeric")
    assert text.raw == "结论：无异常"
    ok = await _read(world, "E1", "货币资金审定表E1-1", "C10")
    assert (ok.state, ok.value, ok.reason, ok.reason_code, ok.raw) == ("ok", Decimal("100.50"), None, None, "100.50")
    two_arg = await _read(world, "E1", None, "F2")
    assert (two_arg.state, two_arg.reason_code, two_arg.raw) == ("ok", None, "7")


def _constructions() -> list[ast.Call]:
    tree = ast.parse(inspect.getsource(wp_cell_reader))
    return [n for n in ast.walk(tree) if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "WpCellRead"]


def test_every_non_ok_construction_sets_reason_code():
    calls = _constructions()
    non_ok = [c for c in calls if not (isinstance(c.args[0], ast.Constant) and c.args[0].value == "ok")]
    assert len(calls) >= 12 and len(non_ok) >= 11, (len(calls), len(non_ok))  # 防扫描器空转
    missing = [ast.unparse(c)[:80] for c in non_ok
               if not any(k.arg == "reason_code" and not (isinstance(k.value, ast.Constant) and k.value.value is None)
                          for k in c.keywords)]
    assert not missing, missing
    codes = {k.value.value for c in non_ok for k in c.keywords if k.arg == "reason_code"}
    assert codes == set(REASON_CODES), codes
