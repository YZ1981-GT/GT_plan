"""子公司完整度校验单测（consol-phase3-frontend-drilldown / 需求 6 / 属性 T5 / EH5）.

覆盖：
- T5：数据不全 → warnings 非空，但 can_refresh 恒为 True（不阻断刷新）
- 数据齐全 → warnings 空，can_refresh True
- 空树（无子公司）→ completed True，warnings 空
- EH5：超时 → completed False + 提示 warning，can_refresh 仍 True
- hypothesis：任意子公司完整度组合下 can_refresh 恒 True（T5 不变式）

Validates: Requirements 6.1, 6.2, 6.3; Property T5; Error scenario EH5.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from hypothesis import given, settings, strategies as st

from app.services import consol_completeness_service as svc


def _leaf(name: str):
    return SimpleNamespace(project_id=uuid4(), company_code=name, company_name=name)


@pytest.mark.asyncio
async def test_incomplete_data_warns_but_not_blocks():
    """T5：子公司数据不全 → warnings 非空，can_refresh 仍 True."""
    leaves = [_leaf("子公司A"), _leaf("子公司B")]
    fake_root = SimpleNamespace(children=leaves)

    with patch("app.services.consol_tree_service.build_tree", new=AsyncMock(return_value=fake_root)), \
         patch("app.services.consol_tree_service.get_descendants", return_value=leaves), \
         patch.object(svc, "_has_audited_tb", new=AsyncMock(return_value=False)), \
         patch.object(svc, "_has_notes", new=AsyncMock(return_value=False)):
        result = await svc.check_subsidiary_completeness(AsyncMock(), uuid4(), 2025)

    assert result["can_refresh"] is True
    assert result["completed"] is True
    assert result["total_count"] == 2
    # 每家子公司 2 条 warning（无 TB + 无附注）
    assert len(result["warnings"]) == 4


@pytest.mark.asyncio
async def test_complete_data_no_warnings():
    """数据齐全 → warnings 空，can_refresh True."""
    leaves = [_leaf("子公司A")]
    fake_root = SimpleNamespace(children=leaves)

    with patch("app.services.consol_tree_service.build_tree", new=AsyncMock(return_value=fake_root)), \
         patch("app.services.consol_tree_service.get_descendants", return_value=leaves), \
         patch.object(svc, "_has_audited_tb", new=AsyncMock(return_value=True)), \
         patch.object(svc, "_has_notes", new=AsyncMock(return_value=True)):
        result = await svc.check_subsidiary_completeness(AsyncMock(), uuid4(), 2025)

    assert result["warnings"] == []
    assert result["can_refresh"] is True
    assert result["completed"] is True


@pytest.mark.asyncio
async def test_empty_tree():
    """无子公司（空树）→ completed True，warnings 空."""
    fake_root = SimpleNamespace(children=[])
    with patch("app.services.consol_tree_service.build_tree", new=AsyncMock(return_value=fake_root)), \
         patch("app.services.consol_tree_service.get_descendants", return_value=[]):
        result = await svc.check_subsidiary_completeness(AsyncMock(), uuid4(), 2025)

    assert result["total_count"] == 0
    assert result["warnings"] == []
    assert result["can_refresh"] is True


@pytest.mark.asyncio
async def test_no_tree_returns_can_refresh():
    """build_tree 返回 None（非合并项目）→ 不阻断."""
    with patch("app.services.consol_tree_service.build_tree", new=AsyncMock(return_value=None)):
        result = await svc.check_subsidiary_completeness(AsyncMock(), uuid4(), 2025)
    assert result["can_refresh"] is True
    assert result["completed"] is True


@pytest.mark.asyncio
async def test_timeout_degrades_not_blocks():
    """EH5：校验超时 → completed False + 提示，can_refresh 仍 True."""
    leaves = [_leaf("子公司A")]
    fake_root = SimpleNamespace(children=leaves)

    async def _slow(*_a, **_k):
        await asyncio.sleep(1)
        return ([], 0)

    with patch("app.services.consol_tree_service.build_tree", new=AsyncMock(return_value=fake_root)), \
         patch("app.services.consol_tree_service.get_descendants", return_value=leaves), \
         patch.object(svc, "_check_all", new=_slow):
        result = await svc.check_subsidiary_completeness(AsyncMock(), uuid4(), 2025, timeout=0.05)

    assert result["completed"] is False
    assert result["can_refresh"] is True
    assert any("未完成" in w for w in result["warnings"])


@settings(max_examples=15, deadline=None)
@given(
    tb_flags=st.lists(st.booleans(), min_size=0, max_size=6),
    notes_flags=st.lists(st.booleans(), min_size=0, max_size=6),
)
def test_can_refresh_always_true_property(tb_flags, notes_flags):
    """T5 不变式：任意子公司完整度组合下 can_refresh 恒为 True（不阻断）."""
    n = min(len(tb_flags), len(notes_flags))
    leaves = [_leaf(f"子{i}") for i in range(n)]
    fake_root = SimpleNamespace(children=leaves)

    tb_iter = iter(tb_flags[:n])
    notes_iter = iter(notes_flags[:n])

    async def _has_tb(_db, _pid, _year):
        return next(tb_iter, True)

    async def _has_notes(_db, _pid, _year):
        return next(notes_iter, True)

    async def _run():
        with patch("app.services.consol_tree_service.build_tree", new=AsyncMock(return_value=fake_root)), \
             patch("app.services.consol_tree_service.get_descendants", return_value=leaves), \
             patch.object(svc, "_has_audited_tb", new=_has_tb), \
             patch.object(svc, "_has_notes", new=_has_notes):
            return await svc.check_subsidiary_completeness(AsyncMock(), uuid4(), 2025)

    result = asyncio.run(_run())
    assert result["can_refresh"] is True
