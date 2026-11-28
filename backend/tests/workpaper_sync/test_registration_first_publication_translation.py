"""`_registration(translate_unpublished=True)`：首版破环的回报口径。

背景：entry 级注册要靠「某张可见底稿已有首版」冻结定义。全库一张都没有（或唯一那张在已删
项目上）时 adapter 注册不上，pending-mutations / materialize / materialize-from-store 在注册
这一步就 422 `adapter_not_registered`，而前端的按需首版只认
`materialize_substrate_not_published` ⇒ 首版永远触发不了（死锁，D4 真库实测）。

判据：
1. 开关打开 + adapter 未注册 + 目标底稿尚无首版 ⇒ 回报 `materialize_substrate_not_published`；
2. 目标底稿**已有**首版时注册失败照旧原样回报（不得把真故障洗成「再发一版」）；
3. 不是「未注册」类的失败（如契约漂移）照旧原样回报；
4. 开关关闭（只读入口）照旧原样回报。
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.routers import wp_sync_router as SR
from app.services.workpaper_sync.adapters.registry import (
    AdapterNotRegisteredError,
    RegistryError,
)

ENTRY = "xlsx/gt-d4-operating-revenue"
WP = uuid.UUID("00000000-0000-0000-0000-000000000042")


def _scope() -> SimpleNamespace:
    return SimpleNamespace(entry_id=ENTRY, wp_id=WP)


def _svc() -> SimpleNamespace:
    return SimpleNamespace(session=object(), registry=object())


@pytest.fixture
def failing_bind(monkeypatch: pytest.MonkeyPatch):
    """注册接线全部打桩：attach 成功、bind 抛给定异常、首版指针按参数返回。"""

    def install(exc: BaseException, *, published: bool) -> None:
        monkeypatch.setattr(SR, "_attach_pilot_adapters", AsyncMock(return_value=()))
        monkeypatch.setattr(SR, "bind_registration_to_target", AsyncMock(side_effect=exc))
        monkeypatch.setattr(
            SR,
            "current_publication",
            AsyncMock(return_value=object() if published else None),
        )

    return install


async def _error_code(**kwargs) -> str:
    with pytest.raises(HTTPException) as raised:
        await SR._registration(_svc(), _scope(), **kwargs)
    assert raised.value.status_code == 422
    return raised.value.detail["error_code"]


@pytest.mark.asyncio
async def test_unpublished_target_reports_substrate_not_published(failing_bind) -> None:
    failing_bind(AdapterNotRegisteredError("未注册 adapter"), published=False)
    assert await _error_code(translate_unpublished=True) == "materialize_substrate_not_published"


@pytest.mark.asyncio
async def test_published_target_keeps_the_real_failure(failing_bind) -> None:
    failing_bind(AdapterNotRegisteredError("未注册 adapter"), published=True)
    assert await _error_code(translate_unpublished=True) == "adapter_not_registered"


@pytest.mark.asyncio
async def test_other_registry_failures_are_not_translated(failing_bind) -> None:
    class _Drift(RegistryError):
        error_code = "contract_drift"

    failing_bind(_Drift("契约漂移"), published=False)
    assert await _error_code(translate_unpublished=True) == "contract_drift"


@pytest.mark.asyncio
async def test_switch_off_keeps_the_real_failure(failing_bind) -> None:
    failing_bind(AdapterNotRegisteredError("未注册 adapter"), published=False)
    assert await _error_code() == "adapter_not_registered"


def test_only_online_edit_write_entry_points_enable_translation() -> None:
    """开关只在在线编辑写入口打开：pending-mutations / materialize 经 `_materialize_request`，
    外加 materialize-from-store；其余调用 `_registration` 的端点（读投影、冲突、回滚等）不开。"""
    import ast
    import inspect

    # 按 AST 数真实调用（docstring / 注释里提到这个参数不算）。
    tree = ast.parse(inspect.getsource(SR))
    enabled_in: list[str] = []
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for node in ast.walk(fn):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "_registration"
                and any(
                    kw.arg == "translate_unpublished"
                    and isinstance(kw.value, ast.Constant)
                    and kw.value.value is True
                    for kw in node.keywords
                )
            ):
                enabled_in.append(fn.name)
    assert sorted(enabled_in) == ["_materialize_request", "materialize_from_store"]
