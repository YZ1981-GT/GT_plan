"""一致性门禁取数失败如实报「检查异常」，不冒充「数据不完整」（formula-hub-integrity-closure 第 3 轮发现 ①）。

原状：``_impl.ConsistencyGate`` 的 7 个 ``_get_*`` 取数函数自己吞异常返回 ``None``（容差退回 1.0），真实 SQL 错误
被报成「数据不完整，跳过检查」；PG 上取数失败后保存点已中止，同方法后续规则也连带报「数据不完整」。
"""
from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from unittest.mock import MagicMock

import pytest

from app.services.consistency_gate import ConsistencyGate


class _BoomDb:
    """``execute`` 一律抛错；``begin_nested`` 记录保存点次数。"""

    def __init__(self) -> None:
        self.savepoints = 0

    async def execute(self, *_a, **_k):
        raise RuntimeError("relation does not exist")

    @asynccontextmanager
    async def _nested(self):
        self.savepoints += 1
        yield MagicMock()

    def begin_nested(self):
        return self._nested()


@pytest.mark.asyncio
async def test_e1_cfs_fetch_error_reports_exception_not_missing():
    db = _BoomDb()
    gate = ConsistencyGate(db)  # type: ignore[arg-type]
    items = await gate.check_e1_cfs_reconciliation(uuid.uuid4(), 2025)
    # 容差取数即失败 ⇒ 整条检查一个「检查异常」，不是三条「数据不完整」；多规则检查异常时仍返回列表
    assert isinstance(items, list) and len(items) == 1
    item = items[0]
    assert getattr(item, "status", None) in {"error", "not_executed"}
    assert "检查异常" in (item.reason or "")
    assert "数据不完整" not in (item.reason or "")


@pytest.mark.asyncio
async def test_wp_parsed_data_fetch_error_reports_exception():
    db = _BoomDb()
    gate = ConsistencyGate(db)  # type: ignore[arg-type]
    items = await gate.check_d4_revenue_reconciliation(uuid.uuid4(), 2025)
    assert isinstance(items, list)
    assert any("检查异常" in (i.reason or "") for i in items)
    assert not any("数据不完整" in (i.reason or "") for i in items)


@pytest.mark.asyncio
async def test_run_all_checks_survives_fetch_errors():
    """取数全部失败时整次运行不抛（多规则检查异常返回列表，``checks.extend`` 不 TypeError），每项都不报「通过」。"""
    db = _BoomDb()
    gate = ConsistencyGate(db)  # type: ignore[arg-type]
    items = (await gate.run_all_checks(uuid.uuid4(), 2025)).checks
    assert items
    assert not any(getattr(i, "status", None) == "passed" for i in items)
