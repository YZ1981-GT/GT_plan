"""`/draft-refresh` 全局一键刷新端点改造测试.

公式管理库（formula-management-library）Task 16.2 / 设计 §18（Req 21.4 / 21.6）。

验证 ``POST /draft-refresh`` 由裸调 ``DraftRefreshService.refresh()``（不传 units → 零初稿）
改为经 ``DraftRefreshOrchestrator.generate(...)`` 生成**非空初稿**后的行为契约：

1. **经 orchestrator 生成非空初稿**：端点调 ``orchestrator.generate`` 而非 ``service.refresh``；
   响应含 ``affected_count``（> 0）+ ``preset_application``（PresetApplication.to_dict）+
   ``precheck_warnings``；orchestrator 收到端点透传的 ``scopes`` / ``confirm_overwrite``；
   之后 router 层 ``db.commit()``（service flush、router commit 铁律）。
2. **合伙人门禁 403**：非合伙人经 ``require_role(["partner","signing_partner"])`` 在依赖解析
   阶段抛 403，先于任何读写。
3. **precheck 阻断 422**：四表库不完整时 precheck 阻断返回 422 缺失清单，**不进 orchestrator**
   （orchestrator.generate 不被调用，零写入）。

以直接调用路由处理函数 ``one_click_draft_refresh`` 的方式测试（monkeypatch 模块级
``DraftRefreshService`` / ``DraftRefreshOrchestrator`` 为桩），避免 TestClient/DB 依赖，聚焦
端点编排契约本身。
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from fastapi import HTTPException

import app.routers.draft_refresh as endpoint
from app.routers.draft_refresh import (
    PARTNER_ROLES,
    one_click_draft_refresh,
)
from app.schemas.formula_runtime import DraftRefreshRequest as OneClickRefreshRequest
from app.services.draft_refresh_service import PresetApplication, RefreshResult, RefreshUnit


def _run(coro):
    """跑一个协程，**不依赖也不改动**主线程的全局 event loop 状态。

    🔴 原实现是 `asyncio.get_event_loop().run_until_complete(coro)`，它依赖
    「主线程存在一个当前 loop」这个隐含前提。该前提会被**同一次 pytest 运行里的
    其他测试文件**打破：本仓库有多个测试在模块/import 期直接调 `asyncio.run()`
    （`test_adjudication_adapter.py` L524/L559、`test_orchestrator_real_mutations.py`
    L477/L547、`test_prefill_wp_prev_resolution.py` L466），而 `asyncio.run` 结束时
    会关闭并**清空**主线程的 loop 状态 ⇒ 之后 `get_event_loop()` 直接抛
    `RuntimeError: There is no current event loop in thread 'MainThread'`。
    实测（2026-09-06）：本文件单跑 11 passed，与上述任一文件同批即 10 failed。
    另外 `get_event_loop()` 在无运行 loop 时的这种用法自 Python 3.12 起已废弃。

    → 自建自关：每次调用新建 loop、用完 close，既不读也不写全局状态。
    """
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class _FakeDb:
    """最小 AsyncSession 替身：仅需可 await 的 commit（记录是否被调用）。"""

    def __init__(self):
        self.committed = False

    async def commit(self):
        self.committed = True


class _Warning:
    def __init__(self, table: str):
        self.table = table

    def to_dict(self):
        return {"table": self.table, "label": self.table, "message": "缺 aux"}


class _Precheck:
    def __init__(self, *, can_refresh: bool, warnings=None, blocking=None):
        self.can_refresh = can_refresh
        self.warnings = warnings or []
        self._blocking = blocking or []

    def to_dict(self):
        return {
            "can_refresh": self.can_refresh,
            "blocking": [dict(b) for b in self._blocking],
            "warnings": [w.to_dict() for w in self.warnings],
        }


class _StubService:
    """DraftRefreshService 替身：只暴露 precheck；refresh 若被调即视为回归。"""

    _precheck_result: _Precheck = _Precheck(can_refresh=True)
    refresh_called = False

    async def precheck(self, db, *, project_id, year):
        return type(self)._precheck_result

    async def refresh(self, *a, **kw):  # pragma: no cover - 不应被调用
        type(self).refresh_called = True
        raise AssertionError("端点应经 orchestrator.generate，而非裸调 service.refresh")


class _StubOrchestrator:
    """DraftRefreshOrchestrator 替身：记录 generate 入参并返回既定结果。"""

    last_kwargs: dict | None = None
    called = False
    _result: tuple[RefreshResult, PresetApplication] | None = None

    def __init__(self, db):
        self.db = db

    async def generate(self, *, project_id, year, operator, scopes, confirm_overwrite=False):
        type(self).called = True
        type(self).last_kwargs = {
            "project_id": project_id,
            "year": year,
            "operator": operator,
            "scopes": list(scopes),
            "confirm_overwrite": confirm_overwrite,
        }
        return type(self)._result


def _install_stubs(monkeypatch, *, precheck: _Precheck, result):
    _StubService._precheck_result = precheck
    _StubService.refresh_called = False
    _StubOrchestrator.called = False
    _StubOrchestrator.last_kwargs = None
    _StubOrchestrator._result = result
    monkeypatch.setattr(endpoint, "DraftRefreshService", _StubService)
    monkeypatch.setattr(endpoint, "DraftRefreshOrchestrator", _StubOrchestrator)


# ─────────────────────────────────────────────────────────────────────────────
# 1. 经 orchestrator 生成非空初稿 + 响应契约
# ─────────────────────────────────────────────────────────────────────────────
def test_endpoint_routes_through_orchestrator_and_returns_nonempty_draft(monkeypatch):
    """端点经 orchestrator.generate 生成非空初稿；响应含 affected_count/preset_application。"""
    refreshed = ["report:BS-1", "report:BS-2", "note:cash!1:2"]
    result = RefreshResult(
        tb_snapshot_hash="hash-abc",
        scope="report,note",
        status="success",
        refresh_id=uuid.uuid4(),
        affected_count=len(refreshed),
        refreshed_units=list(refreshed),
    )
    application = PresetApplication(
        units=[RefreshUnit(unit_scope="report:BS-1")],
        presetted_pages=["report:*"],
        pending_pages=["note:cash"],
    )
    _install_stubs(
        monkeypatch,
        precheck=_Precheck(can_refresh=True, warnings=[_Warning("tb_aux_balance")]),
        result=(result, application),
    )

    db = _FakeDb()
    body = OneClickRefreshRequest(
        project_id=uuid.uuid4(),
        year=2025,
        scopes=["report", "note"],
        confirm_overwrite=True,
    )
    resp = _run(one_click_draft_refresh(body=body, db=db, _user=object()))

    # 经 orchestrator，而非裸 service.refresh
    assert _StubOrchestrator.called is True
    assert _StubService.refresh_called is False

    # 端点透传勾选范围 + confirm_overwrite 给 orchestrator
    assert _StubOrchestrator.last_kwargs["scopes"] == ["report", "note"]
    assert _StubOrchestrator.last_kwargs["confirm_overwrite"] is True

    # 非空初稿：affected_count > 0
    assert resp.affected_count == 3
    assert resp.status == "success"

    # preset_application（PresetApplication 属性）
    pa = resp.preset_application
    assert pa.preset_count == 1
    assert pa.presetted_pages == ["report:*"]
    assert pa.pending_pages == ["note:cash"]

    # service flush、router commit 铁律
    assert db.committed is True


def test_endpoint_defaults_scopes_when_empty(monkeypatch):
    """勾选范围为空 → Pydantic 422 拒绝（scopes min_length=1 设计决策）。"""
    with pytest.raises(Exception):
        # DraftRefreshRequest(scopes=[]) 应在 Pydantic 验证层直接拒绝
        OneClickRefreshRequest(project_id=uuid.uuid4(), year=2025, scopes=[])


# ─────────────────────────────────────────────────────────────────────────────
# 2. 合伙人门禁 403（复用 require_role）
# ─────────────────────────────────────────────────────────────────────────────
from types import SimpleNamespace  # noqa: E402

from app.deps import require_role  # noqa: E402


def _make_user(role: str):
    return SimpleNamespace(role=SimpleNamespace(value=role))


@pytest.mark.parametrize("role", ["auditor", "manager", "assistant", "readonly", "qc", ""])
def test_endpoint_gate_rejects_non_partner(role):
    """非合伙人调 /draft-refresh → require_role 依赖解析阶段抛 403，先于任何读写。"""
    dependency = require_role(PARTNER_ROLES)
    with pytest.raises(HTTPException) as exc:
        _run(dependency(current_user=_make_user(role)))
    assert exc.value.status_code == 403


@pytest.mark.parametrize("role", ["partner", "signing_partner"])
def test_endpoint_gate_allows_partner(role):
    """合伙人 / 签字合伙人放行（返回该用户），端点体方可执行编排。"""
    dependency = require_role(PARTNER_ROLES)
    user = _make_user(role)
    assert _run(dependency(current_user=user)) is user


# ─────────────────────────────────────────────────────────────────────────────
# 3. precheck 阻断 422，不进 orchestrator
# ─────────────────────────────────────────────────────────────────────────────
def test_endpoint_precheck_block_returns_422_and_skips_orchestrator(monkeypatch):
    """四表库不完整 → precheck 阻断 422，orchestrator.generate 不被调用（零写入）。"""
    _install_stubs(
        monkeypatch,
        precheck=_Precheck(
            can_refresh=False,
            blocking=[{"table": "trial_balance", "label": "试算表", "message": "缺未审数"}],
        ),
        result=None,
    )

    db = _FakeDb()
    body = OneClickRefreshRequest(project_id=uuid.uuid4(), year=2025, scopes=["report"])
    with pytest.raises(HTTPException) as exc:
        _run(one_click_draft_refresh(body=body, db=db, _user=object()))

    assert exc.value.status_code == 422
    assert exc.value.detail["message"] == "四表库数据不完整，无法一键刷新"
    assert exc.value.detail["can_refresh"] is False
    # 阻断不进 orchestrator，且不 commit
    assert _StubOrchestrator.called is False
    assert db.committed is False
