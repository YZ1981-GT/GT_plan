"""sync 端点 guard：平台可见性门判定「只读」的用户不得执行写 action。

🔴 2026-11-25 发现的授权缺口：`WpGateVisibilityProbe` 一直把 `enforce_wp_gate` 的
`readonly`（复核人 / History_Only）带回来，但 `SyncEndpointGuard` 阶段 ⑤ 只按
`workflow_locked` 拦写、`authorize` 回调只校验 action 词汇表 ⇒ 只读用户能调用
materialize / resolve / rollback 等写端点。修复后：readonly + 写 action ⇒ 403
（`SyncReadonlyAccessError`），readonly + 登记的只读 action ⇒ 放行；workflow 锁定仍优先 423。
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

import pytest

from app.services.workpaper_sync import endpoint_guard as G

PROJECT = uuid.UUID("11111111-1111-4111-8111-111111111111")
WP = uuid.UUID("22222222-2222-4222-8222-222222222222")
USER = uuid.UUID("44444444-4444-4444-8444-444444444444")
ENTRY = "xlsx/gt-d2-accounts-receivable"
READ_ONLY = frozenset({"read_timeline"})


@dataclass
class _Probe:
    readonly: bool = False
    workflow_locked: bool = False

    async def observe(self, *, project_id, wp_id, entry_id) -> dict[str, Any]:  # noqa: ANN001
        return {
            "project_visible": True,
            "workflow_locked": self.workflow_locked,
            "readonly": self.readonly,
        }


class _EmptyRepo:
    """无 refs 的请求不查 scope index；任何查询都说明测试前提变了。"""

    async def lookup_scope_attributions(self, *_a: Any, **_k: Any):  # pragma: no cover
        raise AssertionError("unexpected scope index lookup")


def _guard(probe: _Probe) -> G.SyncEndpointGuard:
    return G.SyncEndpointGuard(
        repository=_EmptyRepo(),  # type: ignore[arg-type]
        visibility=probe,
        authorize=lambda scope: True,
        read_only_actions=READ_ONLY,
    )


def _request(action: str) -> G.SyncEndpointRequest:
    return G.SyncEndpointRequest(
        project_id=PROJECT, wp_id=WP, entry_id=ENTRY, action=action, user_id=USER
    )


@pytest.mark.asyncio
async def test_readonly_user_write_action_is_403() -> None:
    with pytest.raises(G.SyncReadonlyAccessError) as info:
        await _guard(_Probe(readonly=True)).enforce(_request("forcesave"))
    assert G.http_status_for_refusal(info.value) == 403
    assert info.value.error_code == "sync_readonly_access"


@pytest.mark.asyncio
async def test_readonly_user_registered_read_action_passes() -> None:
    scope = await _guard(_Probe(readonly=True)).enforce(_request("read_timeline"))
    scope.assert_complete()


@pytest.mark.asyncio
async def test_writable_user_write_action_passes() -> None:
    """反向对照：非只读用户的写 action 不受影响（防新判据把所有写都拦掉）。"""
    scope = await _guard(_Probe(readonly=False)).enforce(_request("forcesave"))
    scope.assert_complete()


@pytest.mark.asyncio
async def test_workflow_lock_still_takes_precedence_as_423() -> None:
    """复核锁定/归档是业务终态（423），与访问只读（403）分型，锁定优先判。"""
    with pytest.raises(G.SyncWorkflowLockedError):
        await _guard(_Probe(readonly=True, workflow_locked=True)).enforce(_request("forcesave"))


def test_router_wires_the_production_probe_that_reports_readonly() -> None:
    """生产装配必须用会回报 readonly 的探针，否则新判据在生产上空转。"""
    import inspect

    from app.routers import wp_sync_router as R

    src = inspect.getsource(R.WpGateVisibilityProbe.observe)
    assert '"readonly"' in src, "生产 visibility 探针不再回报 readonly ⇒ 只读拦写判据空转"
    assert "WpGateVisibilityProbe(db, user)" in inspect.getsource(R.build_sync_services)
