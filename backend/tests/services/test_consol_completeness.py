"""子公司完整度校验单测（consol-phase3-frontend-drilldown / 需求 6 / 属性 T5 / EH5）.

覆盖：
- T5：数据不全 → warnings 非空，但 can_refresh 恒为 True（不阻断刷新）
- 数据齐全 → warnings 空，can_refresh True
- 没有下级企业 → 只校验母公司本体，completed True
- 数据叶子没有单户项目 → 直接提示（金额按 0 计），不拿空 project_id 去查库
- EH5：超时 → completed False + 提示 warning，can_refresh 仍 True
- hypothesis：任意完整度组合下 can_refresh 恒 True（T5 不变式）

口径变更（spec consol-tree-three-code-autobuild 任务 7.5，有意）：校验对象从「根的全部后代」改为企业树
**数据叶子**（母公司/本部、分公司、子公司）；树改用三码推导的真实 TreeNode（旧用例用无 kind 的替身）。

Validates: Requirements 6.1, 6.2, 6.3; Property T5; Error scenario EH5.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from hypothesis import given, settings, strategies as st

from app.services import consol_completeness_service as svc
from app.services.consol_group_tree import ProjectRecord, derive_group_tree

Y = 2025


def _tree(n_subs: int, *, parent_standalone: bool = True, branch: bool = False):
    """某集团（合并）+ 可选母公司单户 + n 家子公司（+ 可选一家分公司）的三码树。"""
    consol = ProjectRecord(id=uuid4(), company_code="G", client_name="某集团", report_scope="consolidated", audit_year=Y)
    records = [consol]
    if parent_standalone:
        records.append(ProjectRecord(id=uuid4(), company_code="G", client_name="某集团",
                                     report_scope="standalone", audit_year=Y))
    for i in range(n_subs):
        records.append(ProjectRecord(
            id=uuid4(), company_code=f"S{i}", client_name=f"子公司{i}", report_scope="standalone",
            audit_year=Y, parent_company_code="G", relation_to_parent="subsidiary",
        ))
    if branch:
        records.append(ProjectRecord(
            id=uuid4(), company_code="B", client_name="某集团上海分公司", report_scope="standalone",
            audit_year=Y, parent_company_code="G", relation_to_parent="branch",
        ))
    return derive_group_tree(records, consol, Y).root


def _patch_tree(tree):
    return patch("app.services.consol_tree_service.build_tree", new=AsyncMock(return_value=tree))


@pytest.mark.asyncio
async def test_incomplete_data_warns_but_not_blocks():
    """T5：数据不全 → warnings 非空，can_refresh 仍 True（母公司本体 + 2 家子公司 = 3 个数据叶子）."""
    with _patch_tree(_tree(2)), \
         patch.object(svc, "_has_audited_tb", new=AsyncMock(return_value=False)), \
         patch.object(svc, "_has_notes", new=AsyncMock(return_value=False)):
        result = await svc.check_subsidiary_completeness(AsyncMock(), uuid4(), Y)

    assert result["can_refresh"] is True
    assert result["completed"] is True
    assert result["total_count"] == 3
    # 每个数据叶子 2 条 warning（无 TB + 无附注）
    assert len(result["warnings"]) == 6
    assert "某集团（母公司） 无审定试算数据，合并结果可能不准确" in result["warnings"]
    assert "子公司 子公司0 未生成附注" in result["warnings"]


@pytest.mark.asyncio
async def test_complete_data_no_warnings():
    """数据齐全 → warnings 空，can_refresh True."""
    with _patch_tree(_tree(1)), \
         patch.object(svc, "_has_audited_tb", new=AsyncMock(return_value=True)), \
         patch.object(svc, "_has_notes", new=AsyncMock(return_value=True)):
        result = await svc.check_subsidiary_completeness(AsyncMock(), uuid4(), Y)

    assert result["warnings"] == []
    assert result["can_refresh"] is True
    assert result["completed"] is True


@pytest.mark.asyncio
async def test_no_member_checks_parent_only():
    """没有下级企业 → 只校验母公司本体一个数据叶子（旧版此时 total 为 0）."""
    with _patch_tree(_tree(0)), \
         patch.object(svc, "_has_audited_tb", new=AsyncMock(return_value=True)), \
         patch.object(svc, "_has_notes", new=AsyncMock(return_value=True)):
        result = await svc.check_subsidiary_completeness(AsyncMock(), uuid4(), Y)

    assert result["total_count"] == 1
    assert result["warnings"] == []
    assert result["can_refresh"] is True


@pytest.mark.asyncio
async def test_missing_standalone_warns_without_querying():
    """数据叶子没有单户项目（母公司未建单体）→ 直接提示金额按 0 计，不拿空 project_id 查库."""
    has_tb = AsyncMock(return_value=True)
    has_notes = AsyncMock(return_value=True)
    with _patch_tree(_tree(1, parent_standalone=False, branch=True)), \
         patch.object(svc, "_has_audited_tb", new=has_tb), \
         patch.object(svc, "_has_notes", new=has_notes):
        result = await svc.check_subsidiary_completeness(AsyncMock(), uuid4(), Y)

    # 母公司有分公司 ⇒ 数据叶子 = 本部（无单户）+ 分公司 + 子公司
    assert result["total_count"] == 3 and result["checked_count"] == 3
    assert result["warnings"] == ["某集团（本部） 没有本年度单户项目，合并时金额按 0 计"]
    assert has_tb.await_count == 2
    assert all(call.args[1] is not None for call in has_tb.await_args_list)


@pytest.mark.asyncio
async def test_branch_label():
    """分公司数据叶子的提示带「分公司」前缀."""
    with _patch_tree(_tree(0, branch=True)), \
         patch.object(svc, "_has_audited_tb", new=AsyncMock(return_value=False)), \
         patch.object(svc, "_has_notes", new=AsyncMock(return_value=True)):
        result = await svc.check_subsidiary_completeness(AsyncMock(), uuid4(), Y)
    assert "分公司 某集团上海分公司 无审定试算数据，合并结果可能不准确" in result["warnings"]


@pytest.mark.asyncio
async def test_no_tree_returns_can_refresh():
    """build_tree 返回 None（非合并项目）→ 不阻断."""
    with _patch_tree(None):
        result = await svc.check_subsidiary_completeness(AsyncMock(), uuid4(), Y)
    assert result["can_refresh"] is True
    assert result["completed"] is True


@pytest.mark.asyncio
async def test_timeout_degrades_not_blocks():
    """EH5：校验超时 → completed False + 提示，can_refresh 仍 True."""
    async def _slow(*_a, **_k):
        await asyncio.sleep(1)
        return ([], 0)

    with _patch_tree(_tree(1)), patch.object(svc, "_check_all", new=_slow):
        result = await svc.check_subsidiary_completeness(AsyncMock(), uuid4(), Y, timeout=0.05)

    assert result["completed"] is False
    assert result["can_refresh"] is True
    assert any("未完成" in w for w in result["warnings"])


@settings(max_examples=5, deadline=None)
@given(
    tb_flags=st.lists(st.booleans(), min_size=0, max_size=6),
    notes_flags=st.lists(st.booleans(), min_size=0, max_size=6),
)
def test_can_refresh_always_true_property(tb_flags, notes_flags):
    """T5 不变式：任意完整度组合下 can_refresh 恒为 True（不阻断）."""
    n = min(len(tb_flags), len(notes_flags))
    tree = _tree(n)
    tb_iter = iter(tb_flags[:n])
    notes_iter = iter(notes_flags[:n])

    async def _has_tb(_db, _pid, _year):
        return next(tb_iter, True)

    async def _has_notes(_db, _pid, _year):
        return next(notes_iter, True)

    async def _run():
        with _patch_tree(tree), \
             patch.object(svc, "_has_audited_tb", new=_has_tb), \
             patch.object(svc, "_has_notes", new=_has_notes):
            return await svc.check_subsidiary_completeness(AsyncMock(), uuid4(), Y)

    result = asyncio.run(_run())
    assert result["can_refresh"] is True
    assert result["total_count"] == n + 1
