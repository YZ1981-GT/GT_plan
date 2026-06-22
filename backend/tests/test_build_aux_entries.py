# Feature: address-registry aux 域 builder（P0-1 修复）
"""build_aux_entries 单元测试 + AUX 公式校验不再误报回归。

修复前：_get_domain() 无 aux 分支 → AUX(...) 公式经 validate_formula_refs
因 aux entries 为空而误报 not_found（悬空引用）。
"""
from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from app.services.address_registry import build_aux_entries, formula_ref_to_uri


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _aux_row(account_code, account_name, aux_type, aux_type_name, aux_code, aux_name):
    return SimpleNamespace(
        account_code=account_code,
        account_name=account_name,
        aux_type=aux_type,
        aux_type_name=aux_type_name,
        aux_code=aux_code,
        aux_name=aux_name,
    )


def test_build_aux_entries_basic():
    """正常辅助余额行 → 期末/期初两条 aux 域条目，formula_ref/uri 对齐。"""
    rows = [
        _aux_row("1122", "应收账款", "customer", "往来单位", "C001", "甲公司"),
    ]
    db = AsyncMock()
    db.execute = AsyncMock(return_value=MagicMock(all=lambda: rows))

    entries = _run(build_aux_entries(db, str(uuid.uuid4()), 2025))

    assert len(entries) == 4  # 期末/期末余额/期初/期初余额
    e = entries[0]
    assert e.domain == "aux"
    assert e.account_code == "1122"
    assert e.path == "甲公司"
    assert e.formula_ref == "AUX('1122','甲公司','期末')"
    # formula_ref 经 formula_ref_to_uri 应还原回同一 uri
    assert formula_ref_to_uri(e.formula_ref) == e.uri
    # 列维度覆盖期末/期初及其规范别名（不含 aux 不存在的 AJE/RJE/审定列）
    cells = {e.cell for e in entries}
    assert cells == {"期末", "期末余额", "期初", "期初余额"}


def test_build_aux_entries_dedup_and_fallback():
    """同三元组去重；aux_name 缺失降级 aux_code；维度全空跳过。"""
    rows = [
        _aux_row("1122", "应收账款", "customer", "往来单位", "C001", "甲公司"),
        _aux_row("1122", "应收账款", "customer", "往来单位", "C001", "甲公司"),  # 重复
        _aux_row("1122", "应收账款", "customer", "往来单位", "C002", None),       # 降级 aux_code
        _aux_row("1122", "应收账款", "customer", "往来单位", None, None),          # 维度全空→跳过
    ]
    db = AsyncMock()
    db.execute = AsyncMock(return_value=MagicMock(all=lambda: rows))

    entries = _run(build_aux_entries(db, str(uuid.uuid4()), 2025))

    dims = {e.path for e in entries}
    assert dims == {"甲公司", "C002"}  # 去重 + 降级 + 跳过空维度


def test_build_aux_entries_bad_project_id():
    """非法 project_id → 返回空列表，不抛异常。"""
    db = AsyncMock()
    entries = _run(build_aux_entries(db, "not-a-uuid", 2025))
    assert entries == []


def test_aux_formula_ref_roundtrip():
    """AUX 公式语法 → uri 转换链路完整（修复前 aux 域无 builder 才暴露）。"""
    uri = formula_ref_to_uri("AUX('1122','甲公司','期末')")
    assert uri == "aux://1122/甲公司#期末"


# ─── 闭环集成测试：validate_formula_refs 走 AUX 全链路（复盘缺口①）──────────────
# 此前只测了零件（build_aux_entries / formula_ref_to_uri），未测"整机"——
# 即修复目标本身：AUX 公式经 validate_formula_refs 不再误报悬空。


def _aux_db_with_rows(rows):
    """构造 mock db：execute 返回 .all()=rows（aux builder 用 .all()）。"""
    db = AsyncMock()
    db.execute = AsyncMock(return_value=MagicMock(all=lambda: rows))
    return db


def test_validate_formula_refs_aux_existing_no_false_positive():
    """修复目标闭环：存在的 AUX 维度 → validate 不报 not_found。"""
    from app.services.address_registry import AddressRegistryService

    rows = [_aux_row("1122", "应收账款", "customer", "往来单位", "C001", "甲公司")]
    db = _aux_db_with_rows(rows)
    svc = AddressRegistryService()  # 独立实例，避免单例缓存串扰

    async def _inner():
        return await svc.validate_formula_refs(
            db, str(uuid.uuid4()), 2025, "AUX('1122','甲公司','期末')",
        )

    issues = _run(_inner())
    assert issues == [], f"存在的 AUX 维度不应被报悬空，实际: {issues}"


def test_validate_formula_refs_aux_missing_still_flags():
    """反向保证：不存在的 AUX 维度仍应被检出 not_found（校验未失效）。"""
    from app.services.address_registry import AddressRegistryService

    rows = [_aux_row("1122", "应收账款", "customer", "往来单位", "C001", "甲公司")]
    db = _aux_db_with_rows(rows)
    svc = AddressRegistryService()

    async def _inner():
        return await svc.validate_formula_refs(
            db, str(uuid.uuid4()), 2025, "AUX('1122','不存在的维度','期末')",
        )

    issues = _run(_inner())
    assert len(issues) == 1
    assert issues[0]["status"] == "not_found"


def test_validate_formula_refs_aux_alias_column_no_false_positive():
    """列维度对齐（复盘缺口②）：期末余额/期初余额 别名写法也不误报。"""
    from app.services.address_registry import AddressRegistryService

    rows = [_aux_row("1122", "应收账款", "customer", "往来单位", "C001", "甲公司")]
    svc = AddressRegistryService()

    async def _check(formula):
        db = _aux_db_with_rows(rows)
        return await svc.validate_formula_refs(
            db, str(uuid.uuid4()), 2025, formula,
        )

    for formula in (
        "AUX('1122','甲公司','期末余额')",
        "AUX('1122','甲公司','期初')",
        "AUX('1122','甲公司','期初余额')",
    ):
        issues = _run(_check(formula))
        assert issues == [], f"{formula} 不应误报，实际: {issues}"
