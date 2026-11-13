"""一致性门禁：全部登记分支由生产类实际触发（需求 16.2 末句 / 16.3，ADR-FHIC-14 第 4 点）。

``_branches.BRANCHES`` 与 ``_impl.py`` 出口的双射已由 ``test_consistency_gate_branches.py`` 守住；
本文件补「每个登记出口都真的跑到过、且产出登记的 branch_id 与五态」。

被测对象是生产入口 ``app.services.consistency_gate.ConsistencyGate``（= ``_impl.ConsistencyGate``，
签字 / 导出 / 看板 / 热力图都用它），不是 ``_gate.ConsistencyGate`` 组合壳。

触发方式（故障注入一律在被测检查方法调用的下一层，不替换被测方法本身）：

* ``empty``：空【测试】项目真实运行；
* ``none``：取数层（``_get_*`` / ``_extract_decimal``）返回空值 ⇒ 规则走「数据不完整」出口；
* ``raise``：取数层与会话 ``execute`` 抛错 ⇒ 规则级 ``try`` 走「检查异常」出口；
* ``partial``：利润表只有营业收入行（真实数据）、G7 只有持股比例 ⇒ 前一道判断通过、后一道缺数的出口；
* ``guard``：``@_guarded`` 打开的保存点抛错 ⇒ 方法级 ``.exception`` 出口；
* ``tb_unknown`` / ``tb_zero``：试算表查询层返回未知类别行 / 负债与权益全 0 ⇒ ``tb_balance`` 两个口径出口。

已知限制：生产 ``_impl`` 的 7 个 ``_get_*`` 取数函数自己吞异常返回 ``None``（``_get_dynamic_tolerance``
退回 1.0），真实 SQL 错误会被报成「数据不完整」而不是规则级「检查异常」。``raise`` 方式在取数层抛错，
证明的是「取数层抛错时出口可达」，不是「生产 SQL 错误会走到这里」；该口径差异登记在
formula-hub-integrity-closure tasks.md 收尾节，未在本 spec 改动。
"""
from __future__ import annotations

import uuid
from contextlib import ExitStack
from decimal import Decimal
from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.services.consistency_gate import ConsistencyGate
from app.services.consistency_gate._branches import BRANCHES

_YEAR = 2025
_CHECKS = sorted({spec.check for spec in BRANCHES.values()})
_GETTERS = sorted(n for n in dir(ConsistencyGate) if n.startswith("_get_") and n != "_get_dynamic_tolerance")


async def _run_all_methods(gate: ConsistencyGate, pid: uuid.UUID) -> list:
    items = []
    for check in _CHECKS:
        result = await getattr(gate, f"check_{check}")(pid, _YEAR)
        items.extend(result if isinstance(result, list) else [result])
    return items


async def _none(*_a, **_k):
    return None


async def _boom(*_a, **_k):
    raise RuntimeError("injected data-layer failure")


async def _tolerance(*_a, **_k):
    return Decimal("1.0")


async def _empty_dict(*_a, **_k):
    return {}


def _raise_extract(*_a, **_k):
    raise RuntimeError("injected extract failure")


_CACHE: dict[str, set[tuple[str, str]]] = {}


@pytest_asyncio.fixture
async def produced() -> dict[str, set[tuple[str, str]]]:
    """跑全部触发方式，返回 ``{branch_id: {(方式, status)}}``（同一进程只跑一次）。"""
    if not _CACHE:
        _CACHE.update(await _collect())
    return _CACHE


async def _collect() -> dict[str, set[tuple[str, str]]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    seen: dict[str, set[tuple[str, str]]] = {}

    def record(tag: str, items) -> None:
        for item in items:
            if item.branch_id:
                seen.setdefault(item.branch_id, set()).add((tag, item.status))

    try:
        async with factory() as db:
            gate = ConsistencyGate(db)
            pid = uuid.uuid4()
            record("empty", await _run_all_methods(gate, pid))

            with ExitStack() as stack:
                stack.enter_context(patch.object(ConsistencyGate, "_get_dynamic_tolerance", _tolerance))
                for name in _GETTERS:
                    stack.enter_context(patch.object(ConsistencyGate, name, _none))
                stack.enter_context(patch.object(ConsistencyGate, "_extract_decimal",
                                                 staticmethod(lambda *_a, **_k: None)))
                record("none", await _run_all_methods(gate, pid))

            with ExitStack() as stack:
                stack.enter_context(patch.object(ConsistencyGate, "_get_dynamic_tolerance", _tolerance))
                for name in _GETTERS:
                    # 在规则 try 之外先取数的方法（D4 / 循环）给空底稿，让规则内的提取层抛错
                    stack.enter_context(patch.object(
                        ConsistencyGate, name, _empty_dict if name == "_get_wp_parsed_data" else _boom))
                stack.enter_context(patch.object(ConsistencyGate, "_extract_decimal", staticmethod(_raise_extract)))
                stack.enter_context(patch.object(db, "execute", _boom))
                record("raise", await _run_all_methods(gate, pid))

            # partial：前一道判断通过、后一道缺数的出口
            from app.models.report_models import FinancialReport, FinancialReportType

            db.add(FinancialReport(project_id=pid, year=_YEAR, report_type=FinancialReportType.income_statement,
                                   row_code="IS-001", row_name="营业收入", current_period_amount=Decimal("100")))
            await db.flush()

            async def _g7_ratio_only(_self, _pid, wp_code):
                return {"shareholding_ratio": "0.3"} if wp_code == "G7" else None

            with ExitStack() as stack:
                stack.enter_context(patch.object(ConsistencyGate, "_get_wp_parsed_data", _g7_ratio_only))
                record("partial", await _run_all_methods(gate, pid))
            await db.rollback()

            # tb_rows：试算表查询层返回构造行（PG 上 account_category 是枚举，未知类别造不出真实行）
            for tag, rows in (("tb_unknown", [("9999", "alien_type", Decimal("100")),
                                              ("1001", "asset", Decimal("100"))]),
                              ("tb_zero", [("1001", "asset", Decimal("0")),
                                           ("2001", "liability", Decimal("0")),
                                           ("4001", "equity", Decimal("0"))])):
                class _Rows:
                    def __init__(self, data):
                        self._data = data

                    def all(self):
                        return list(self._data)

                async def _tb_query(*_a, _rows=rows, **_k):
                    return _Rows(_rows)

                with patch.object(db, "execute", _tb_query):
                    record(tag, [await gate.check_tb_balance(pid, _YEAR)])

            def _bad_savepoint(*_a, **_k):
                raise RuntimeError("injected savepoint failure")

            with patch.object(db, "begin_nested", _bad_savepoint):
                record("guard", await _run_all_methods(gate, pid))
    finally:
        await engine.dispose()
    return seen


_EXPECTED_STATUS = {"missing": {"not_executed"}, "unknown_category": {"not_executed"},
                    "sign_unknown": {"not_executed"}}


def _expected_statuses(branch_id: str) -> set[str]:
    kind = BRANCHES[branch_id].kind
    if kind == "exception":
        # 方法级（check.exception）由 @_guarded 产出 error；规则级（check.N.exception）由规则 try 产出 not_executed
        return {"error"} if branch_id.count(".") == 1 else {"not_executed"}
    return _EXPECTED_STATUS.get(kind, {"not_executed"})


@pytest.mark.parametrize("branch_id", sorted(BRANCHES))
async def test_every_registered_branch_is_triggered_by_production_gate(produced, branch_id):
    hits = produced.get(branch_id)
    assert hits, f"登记分支 {branch_id} 在全部触发方式下都没有出现（出口不可达或登记错误）"
    statuses = {status for _tag, status in hits}
    assert statuses & _expected_statuses(branch_id), (
        f"{branch_id} 产出状态 {sorted(statuses)}，预期 {sorted(_expected_statuses(branch_id))}")


async def test_no_unregistered_branch_ids_are_produced(produced):
    assert set(produced) - set(BRANCHES) == set()


def test_production_entry_is_the_impl_class():
    """被测对象必须是生产入口（签字 / 导出 / 看板都从包导入），不是 ``_gate`` 组合壳。"""
    from app.services.consistency_gate import _impl

    assert ConsistencyGate is _impl.ConsistencyGate


async def test_every_trigger_mode_contributes(produced):
    """每种触发方式都至少独占贡献一个分支，否则该方式是空转（删掉它或修好它）。"""
    modes = {tag for hits in produced.values() for tag, _ in hits}
    for mode in ("empty", "none", "raise", "partial", "tb_unknown", "tb_zero", "guard"):
        assert mode in modes, f"触发方式 {mode} 一个分支都没产出"
