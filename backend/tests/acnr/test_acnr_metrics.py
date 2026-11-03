"""ACNR 计数指标（spec acnr-foundation-defect-closure T26，非功能·可观测）。

``/api/acnr/metrics`` 的 ``counters`` 段在各自路径自增（都走生产函数，不替换被测的计数调用）：

- 版本锁：``full_resolve`` 与 ``wp_cell_target.effective_catalog`` 对锁定项目计 ``version_lock_hit``（版本相同也算）、
  锁定快照缺失计 ``version_lock_snapshot_missing``（仍拒绝解析、仍记 version_mismatch 告警）、带项目而无会话计
  ``version_lock_unchecked``；不带项目三项都不动。锁定来源现为进程内登记（T17 / T18 改落库）。
- ``acnr_targets_rejected{error_code}``：``resolve_acnr_targets`` 的 422 逐项按拒绝码计；全部接受与 503 都不计。
- ``deprecated_ref_saved``：``validate_refs_via_acnr`` 接受停用条目引用时计数（silent 告警保留）。
- ``stale_start_unresolved{code}``：stale 写入口 ``on_change`` 起点身份算不出时按原因码计；只读预览不计。
- 带原因码的两项只收已登记码，其余记 ``other``；端点经 HTTP 返回全部键。
"""
from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fastapi import HTTPException

from app.routers import acnr as acnr_module
from app.services.acnr import wp_cell_target
from app.services.acnr.catalog import get_catalog
from app.services.acnr.formula_validation import validate_refs_via_acnr
from app.services.acnr.metrics import get_acnr_metrics, reset_acnr_metrics
from app.services.acnr.resolver import VersionNotFoundError, full_resolve
from app.services.custom_query.acnr_target_values import resolve_acnr_targets
from app.services.custom_query.addressing_service import AddressingService, ResolvedTarget
from app.services.stale_propagation_engine import StalePropagationEngine
from tests.authz_world import sqlite_world

_MISSING_VERSION = "19990101000000"  # 14 位、无快照
_COUNTER_KEYS = {"version_lock_hit", "version_lock_snapshot_missing", "version_lock_unchecked",
                 "deprecated_ref_saved", "acnr_targets_rejected", "stale_start_unresolved"}


_TEST_LOCKS: dict[str, str] = {}


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    reset_acnr_metrics()
    _TEST_LOCKS.clear()

    async def _locked(_db, project_id):
        return _TEST_LOCKS.get(str(project_id))

    monkeypatch.setattr("app.services.acnr.resolver.get_locked_version", _locked)
    monkeypatch.setattr("app.services.acnr.wp_cell_target.get_locked_version", _locked)
    yield
    _TEST_LOCKS.clear()
    reset_acnr_metrics()


def _counters() -> dict:
    return get_acnr_metrics().get_aggregated_metrics()["counters"]


def _lock(version: str) -> str:
    pid = str(uuid.uuid4())
    _TEST_LOCKS[pid] = version
    return pid


def _locks() -> tuple[int, int, int]:
    c = _counters()
    return c["version_lock_hit"], c["version_lock_snapshot_missing"], c["version_lock_unchecked"]


# ─── 计数段结构 ───────────────────────────────────────────────────────────────


def test_fresh_counters_have_all_keys_zero():
    assert _counters() == {"version_lock_hit": 0, "version_lock_snapshot_missing": 0, "version_lock_unchecked": 0,
                           "deprecated_ref_saved": 0, "acnr_targets_rejected": {}, "stale_start_unresolved": {}}


def test_labelled_counters_bound_unknown_codes_to_other():
    m = get_acnr_metrics()
    m.record_acnr_target_rejected("sheet_level")
    m.record_acnr_target_rejected("不存在的码")
    m.record_stale_start_unresolved("sheet_not_in_catalog")
    m.record_stale_start_unresolved(None)
    c = _counters()
    assert c["acnr_targets_rejected"] == {"sheet_level": 1, "other": 1}
    assert c["stale_start_unresolved"] == {"sheet_not_in_catalog": 1, "other": 1}
    with pytest.raises(KeyError):
        m.record_version_lock("typo")


# ─── 版本锁：full_resolve ────────────────────────────────────────────────────


async def test_full_resolve_project_without_db_is_unchecked_and_does_not_read_lock():
    pid = _lock(get_catalog().registry_version)
    result = await full_resolve(addr_id="E1/E1-14/I18", project_id=pid)
    assert result.found is True and result.version_lock_checked is False
    assert _locks() == (0, 0, 1)


async def test_full_resolve_with_session_is_not_unchecked():
    """有会话：只计命中（未命中目录的输入在首步返回，不触达会话）。"""
    pid = _lock(get_catalog().registry_version)
    result = await full_resolve(addr_id="ZZ/ZZ-不存在/Z1", project_id=pid, db=object())
    assert result.found is False and result.version_lock_checked is True
    assert _locks() == (1, 0, 0)


async def test_full_resolve_missing_snapshot_counts_and_still_raises():
    pid = _lock(_MISSING_VERSION)
    with pytest.raises(VersionNotFoundError):
        await full_resolve(addr_id="E1/E1-14/I18", project_id=pid, db=object())
    assert _locks() == (0, 1, 0)
    assert get_acnr_metrics().get_aggregated_metrics()["alerts"]["by_type"].get("version_mismatch") == 1


async def test_full_resolve_unlocked_or_projectless_counts_nothing():
    await full_resolve(addr_id="E1/E1-14/I18", project_id=str(uuid.uuid4()), db=object())
    await full_resolve(addr_id="E1/E1-14/I18")
    assert _locks() == (0, 0, 0)


# ─── 版本锁：effective_catalog（单元格取值与跨 sheet 追溯取目录处）──────────────


async def test_effective_catalog_counts_same_as_full_resolve():
    cat = get_catalog()
    assert await wp_cell_target.effective_catalog(None, _lock(cat.registry_version)) is cat
    assert _locks() == (0, 0, 1)
    with pytest.raises(VersionNotFoundError):
        await wp_cell_target.effective_catalog(object(), _lock(_MISSING_VERSION))
    assert _locks() == (0, 1, 1)
    await wp_cell_target.effective_catalog(object(), str(uuid.uuid4()))
    await wp_cell_target.effective_catalog(None, None)
    assert _locks() == (0, 1, 1)


# ─── acnr_targets 拒绝 ───────────────────────────────────────────────────────


async def test_rejected_targets_counted_per_error_code():
    raws = ["E1/E1-14", "adj:aje", "E1/E1-14/I18", "ZZZ/不存在/A1", "E1/E1-15"]
    with pytest.raises(HTTPException) as info:
        await resolve_acnr_targets(raws, project_id=None, db=None)
    assert info.value.status_code == 422
    assert _counters()["acnr_targets_rejected"] == {"sheet_level": 2, "external_namespace": 1, "unresolvable": 1}


async def test_accepted_and_unavailable_are_not_rejections():
    await resolve_acnr_targets(["E1/E1-14/I18"], project_id=None, db=None)

    class _Unavailable(AddressingService):
        async def resolve_target(self, raw, *, project_id=None, db=None, timeout_s=5.0):
            return ResolvedTarget(raw=raw, found=False, error="resolve_unavailable")

    with pytest.raises(HTTPException) as info:
        await resolve_acnr_targets(["x"], project_id=None, db=None, addressing=_Unavailable())
    assert info.value.status_code == 503
    assert _counters()["acnr_targets_rejected"] == {}


# ─── 停用引用保存 ────────────────────────────────────────────────────────────


async def test_deprecated_ref_saved_counted_on_save_validation():
    cat = get_catalog()
    refs = sorted(c["formula_ref"] for c in cat.cells_by_addr_id.values() if c.get("deprecated") and c.get("formula_ref"))
    assert refs  # 防空转（真实目录有停用 cell）
    assert await validate_refs_via_acnr(None, str(uuid.uuid4()), 2025, refs[0]) == []
    agg = get_acnr_metrics().get_aggregated_metrics()
    assert agg["counters"]["deprecated_ref_saved"] == 1
    assert agg["alerts"]["by_type"].get("deprecated_ref_saved") == 1  # silent 告警保留


async def test_live_ref_is_not_deprecated_ref_saved():
    live = next(c["formula_ref"] for c in get_catalog().cells_by_addr_id.values()
                if not c.get("deprecated") and c.get("formula_ref"))
    assert await validate_refs_via_acnr(None, str(uuid.uuid4()), 2025, live) == []
    assert _counters()["deprecated_ref_saved"] == 0


# ─── stale 起点身份算不出 ─────────────────────────────────────────────────────

_G12_OWN = "WP:G12:净敞口套期收益审计程序表G12A-修订前:B5"
_PID = "00000000-0000-0000-0000-000000000001"


def _engine() -> StalePropagationEngine:
    eng = StalePropagationEngine()
    eng._graph = {_G12_OWN: ["NOTE:own"]}
    eng._identity_version = None
    eng._mark_stale_by_uri = AsyncMock(return_value={})
    eng._notify_frontend = AsyncMock()
    eng._write_audit_log = AsyncMock()
    return eng


def test_stale_write_entry_counts_unresolved_start_by_code():
    eng = _engine()
    result = asyncio.run(eng.on_change("WP:G12:净敞口套期收益审计程序表G12A-修订:B5", _PID, 2025))
    assert result["unresolved_code"] == "sheet_not_in_catalog"
    assert _counters()["stale_start_unresolved"] == {"sheet_not_in_catalog": 1}
    assert eng._mark_stale_by_uri.await_count == 0


def test_stale_resolved_start_and_preview_do_not_count():
    eng = _engine()
    assert asyncio.run(eng.on_change(_G12_OWN, _PID, 2025))["affected"] == ["NOTE:own"]
    assert eng.preview_impact("WP:G12:净敞口套期收益审计程序表G12A-修订:B5")["unresolved_code"] == "sheet_not_in_catalog"
    assert _counters()["stale_start_unresolved"] == {}


# ─── 端点 ────────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def world(monkeypatch: pytest.MonkeyPatch):
    async with sqlite_world(monkeypatch) as w:
        yield w


async def test_metrics_endpoint_returns_counters(world):
    get_acnr_metrics().record_acnr_target_rejected("deprecated")
    get_acnr_metrics().record_version_lock("hit")
    user = (await world.admin_non_member()).user
    async with world.client(acnr_module.router, user=user) as client:
        resp = await client.get("/api/acnr/metrics")
    assert resp.status_code == 200, resp.text
    counters = resp.json()["counters"]
    assert set(counters) == _COUNTER_KEYS
    assert counters["acnr_targets_rejected"] == {"deprecated": 1} and counters["version_lock_hit"] == 1
