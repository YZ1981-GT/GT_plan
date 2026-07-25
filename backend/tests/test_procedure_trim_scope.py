# -*- coding: utf-8 -*-
"""procedure_trim_scope 单测：科目/循环数据可用性判断。

覆盖：
- registry 映射构建（数字码 / 多码 / 排除 null 与非 D~N）
- 科目码前缀匹配（母码 ↔ 子科目码）
- resolve：科目级 with/no data + 循环级兜底 + tb_empty + 查询失败 fail-safe
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from app.services import procedure_trim_scope as pts


def _row(name, code, unadjusted, audited):
    return SimpleNamespace(
        account_name=name,
        standard_account_code=code,
        unadjusted_amount=unadjusted,
        audited_amount=audited,
    )


def test_load_wp_account_map():
    m = pts._load_wp_account_map()
    assert m.get("D2") == ["1122"]
    assert set(m.get("E1", [])) == {"1001", "1002", "1012"}
    # account_code=null 的包（B1 业务承接）被排除
    assert "B1" not in m
    # 非 D~N 循环 / 非数字伪科目码（C2 控制测试）被排除
    assert "C2" not in m
    # 全部保留项的 account_code 均为纯数字
    for codes in m.values():
        assert all(c.isdigit() for c in codes)


def test_supplement_covers_hijklmn():
    """裁剪专用补充映射覆盖 registry 未登记的 H/I/J/K/L/M/N 科目底稿。"""
    m = pts._load_wp_account_map()
    # H 循环
    assert m.get("H1") == ["1601", "1602"]
    assert m.get("H8") == ["1901"]
    # I 循环
    assert m.get("I3") == ["1711"]
    assert m.get("I1") == ["1701", "1702", "1703"]
    # J / K / L / M / N 各抽样
    assert m.get("J1") == ["2211"]
    assert m.get("K1") == ["1221", "1231"]
    assert m.get("K11") == ["6701"]
    assert m.get("L3") == ["2501"]
    assert m.get("L8") == ["6603"]
    assert m.get("M3") == ["4002"]
    assert m.get("N1") == ["1811"]
    assert m.get("N5") == ["6801"]


def test_supplement_does_not_override_registry():
    """registry 优先：补充映射不覆盖 registry 已登记的科目（如 D2）。"""
    m = pts._load_wp_account_map()
    assert m.get("D2") == ["1122"]  # registry 值，非补充
    # 补充映射键首字母必属 D~N
    for wp in m:
        assert wp[:1] in "DEFGHIJKLMN"


def test_package_has_data_prefix_match():
    # 母码等值
    assert pts._package_has_data(["1122"], {"1122"}) is True
    # 子科目码前缀匹配
    assert pts._package_has_data(["1122"], {"112201"}) is True
    assert pts._package_has_data(["1122"], {"1122.01"}) is True
    # 不同科目不匹配
    assert pts._package_has_data(["1122"], {"6001"}) is False
    # 多码任一命中即有数据
    assert pts._package_has_data(["1001", "1002", "1012"], {"1002"}) is True
    # 空集合无数据
    assert pts._package_has_data(["1122"], set()) is False


def _patch_filter(monkeypatch):
    async def _fake_filter(db, tb, pid, year):  # noqa: ANN001
        return True
    monkeypatch.setattr("app.services.dataset_query.get_active_filter", _fake_filter)


def _mapping_result(pairs):
    """构造 account_mapping 查询结果（original->standard 对）。"""
    r = MagicMock()
    r.fetchall = MagicMock(return_value=[
        SimpleNamespace(original_account_code=o, standard_account_code=s) for o, s in pairs
    ])
    return r


def _mock_db(rows, mapping_pairs=None):
    """db.execute 第一次调用返回 trial_balance 行，第二次返回 account_mapping。"""
    db = AsyncMock()
    tb_result = MagicMock()
    tb_result.fetchall = MagicMock(return_value=rows)
    db.execute = AsyncMock(side_effect=[tb_result, _mapping_result(mapping_pairs or [])])
    return db


def test_resolve_subject_and_cycle(monkeypatch):
    _patch_filter(monkeypatch)
    rows = [
        _row("应收账款", "1122", 0, 500000),    # D2 有数据（审定优先）
        _row("预收账款", "2203", 0, 0),          # D3 无数据（金额 0）
        _row("货币资金", "1001", 100000, None),  # E1 有数据（回退未审）
    ]
    out = asyncio.run(pts.resolve_subject_data_availability(_mock_db(rows), uuid4(), 2025))
    assert out["tb_empty"] is False
    assert "D2" in out["subject_with_data"]
    assert "E1" in out["subject_with_data"]
    assert "D3" in out["subject_no_data"]      # 2203 无非零余额
    # 循环级兜底：应收账款使 D 循环有数据
    assert "D" in out["cycles_with_data"]


def test_resolve_tb_empty(monkeypatch):
    _patch_filter(monkeypatch)
    out = asyncio.run(pts.resolve_subject_data_availability(_mock_db([]), uuid4(), 2025))
    assert out["tb_empty"] is True
    assert out["subject_with_data"] == []
    assert out["cycles_with_data"] == []


def test_resolve_query_failure_failsafe(monkeypatch):
    _patch_filter(monkeypatch)
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=RuntimeError("db down"))
    out = asyncio.run(pts.resolve_subject_data_availability(db, uuid4(), 2025))
    # 查询失败 → tb_empty=True，调用方据此 fail-safe 不裁
    assert out["tb_empty"] is True
    assert out["subject_no_data"] == []


def test_resolve_uses_account_mapping_for_unstandardized_tb(monkeypatch):
    """企业原始码未标准化的 trial_balance：经科目规则映射归一到标准码后正确判定。"""
    _patch_filter(monkeypatch)
    # trial_balance 存的是企业原始码（非标准码）：'A001' 应收账款、'A002' 固定资产
    rows = [
        _row("应收账款", "A001", 0, 800000),
        _row("固定资产", "A002", 0, 0),  # 无数据
    ]
    # 科目规则映射：A001->1122(D2 应收账款)、A002->1601(H1 固定资产)
    db = _mock_db(rows, mapping_pairs=[("A001", "1122"), ("A002", "1601")])
    out = asyncio.run(pts.resolve_subject_data_availability(db, uuid4(), 2025))
    assert out["tb_empty"] is False
    # A001 有数据 → 归一到 1122 → D2 有数据
    assert "D2" in out["subject_with_data"]
    # A002 金额 0 → 不计入 → H1 无数据
    assert "H1" in out["subject_no_data"]
