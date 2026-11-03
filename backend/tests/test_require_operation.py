"""Unit tests for require_operation dependency factory.

验证 require_operation 结合 permission_matrix_service.can() 的授权逻辑，以及矩阵放行后
「请求带项目 id 时须为本项目成员」（spec consol-autotree-residual-closure R3）。

成员判定走真实的 ``assert_project_permission``，只把它下一层的成员级别查询 ``_load_member_level``
与 RLS 设置换成记录桩（不替换门禁本身）。端点级的真库 / 真门禁测试见
``test_report_domain_project_authz.py``。
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.deps import require_operation, _resolve_project_role
from app.models.base import ProjectStatus


# ─── Helper: 构建 mock user ──────────────────────────────────────────────────

def _make_user(role: str):
    """创建具有指定 system_role 的 mock User 对象。"""
    user = MagicMock()
    user.id = uuid4()
    user.role = MagicMock()
    user.role.value = role
    return user


# ─── Helper: 调用 require_operation 内部 dependency ─────────────────────────

async def _invoke_dependency(
    operation: str, user, project_id=None, project_role=None, member_level: str | None = None,
    project_status: ProjectStatus = ProjectStatus.execution,
):
    """直接调用 require_operation 产生的 dependency，返回（结果或 HTTPException，下层调用记录）。

    - ``project_role``：``_resolve_project_role`` 的返回（矩阵用的项目职责）
    - ``member_level``：成员行级别（``_load_member_level`` 的返回，None = 不是本项目成员）
    - ``project_status``：归档守卫读到的项目状态
    """
    calls: dict[str, list] = {"member": [], "rls": []}

    async def _level(_db, user_id, pid):
        calls["member"].append((user_id, pid))
        return member_level

    async def _rls(_db, pid):
        calls["rls"].append(pid)

    db = AsyncMock()
    # 归档守卫读项目行：默认是未归档项目
    db.get = AsyncMock(return_value=SimpleNamespace(status=project_status))
    dependency = require_operation(operation)
    with patch("app.deps._resolve_project_role", AsyncMock(return_value=project_role)), \
            patch("app.deps._load_member_level", _level), \
            patch("app.deps.set_rls_context", _rls):
        try:
            return await dependency(current_user=user, project_id=project_id, db=db), calls
        except HTTPException as exc:
            return exc, calls


def _assert_member_denied(result) -> None:
    assert isinstance(result, HTTPException), f"应被拒绝，实际放行：{result!r}"
    assert (result.status_code, result.detail) == (403, "权限不足")


def _assert_operation_denied(result, operation: str) -> None:
    assert isinstance(result, HTTPException), f"应被拒绝，实际放行：{result!r}"
    assert result.status_code == 403
    assert result.detail == {"error_code": "OPERATION_NOT_ALLOWED", "operation": operation}


# ─── Tests ───────────────────────────────────────────────────────────────────


class TestRequireOperation:
    """require_operation 权限矩阵 + 项目成员。"""

    @pytest.mark.asyncio
    async def test_admin_passes_any_operation(self):
        """admin 系统角色对任何 operation、任何项目均通过（不要求成员行），RLS 设到本项目。"""
        user = _make_user("admin")
        project_id = uuid4()

        for op in ["wp:edit", "report:sign", "archive:manage", "note:edit"]:
            result, calls = await _invoke_dependency(op, user, project_id, project_role=None)
            assert result == user, f"admin should pass {op}"
            assert calls["rls"] == [project_id]

    @pytest.mark.asyncio
    async def test_auditor_denied_report_sign(self):
        """auditor 无 report:sign 权限 → 403 OPERATION_NOT_ALLOWED（是成员也一样）。"""
        user = _make_user("auditor")

        result, _calls = await _invoke_dependency(
            "report:sign", user, uuid4(), project_role="preparer", member_level="edit"
        )
        _assert_operation_denied(result, "report:sign")

    @pytest.mark.asyncio
    async def test_manager_member_passes_wp_edit(self):
        """本项目成员、manager 有 wp:edit 权限 → 通过，成员查询用的是请求里的项目。"""
        user = _make_user("manager")
        project_id = uuid4()

        result, calls = await _invoke_dependency(
            "wp:edit", user, project_id, project_role="manager", member_level="edit"
        )
        assert result == user
        assert calls["member"] == [(user.id, project_id)]
        assert calls["rls"] == [project_id]

    @pytest.mark.asyncio
    async def test_manager_non_member_denied_wp_edit(self):
        """🔴 系统角色 manager、不是本项目成员 ⇒ 403：原先矩阵放行即通过，可往任何项目建调整分录。"""
        user = _make_user("manager")

        result, calls = await _invoke_dependency("wp:edit", user, uuid4(), project_role=None, member_level=None)
        _assert_member_denied(result)
        assert calls["rls"] == []

    @pytest.mark.asyncio
    async def test_no_project_id_uses_system_role_only(self):
        """无 project_id（全局端点）时只按 system_role 判断，不查成员行。"""
        manager = _make_user("manager")
        result, calls = await _invoke_dependency("report:sign", manager, project_id=None)
        _assert_operation_denied(result, "report:sign")

        partner = _make_user("partner")
        result, calls = await _invoke_dependency("report:sign", partner, project_id=None)
        assert result == partner
        assert calls == {"member": [], "rls": []}

    @pytest.mark.asyncio
    async def test_partner_member_passes_all(self):
        """partner 系统角色拥有全部操作权限；是本项目成员（任一级别）即通过。"""
        user = _make_user("partner")

        for op in ["wp:edit", "report:sign", "archive:manage"]:
            result, _calls = await _invoke_dependency(
                op, user, uuid4(), project_role=None, member_level="readonly"
            )
            assert result == user, f"partner should pass {op}"

    @pytest.mark.asyncio
    async def test_partner_non_member_denied(self):
        """🔴 partner 不是本项目成员 ⇒ 403（与 require_project_access 同口径：只有 admin 不看成员行）。"""
        user = _make_user("partner")

        for op in ["wp:edit", "report:sign", "archive:manage"]:
            result, _calls = await _invoke_dependency(op, user, uuid4(), project_role=None, member_level=None)
            _assert_member_denied(result)

    @pytest.mark.asyncio
    async def test_project_role_upgrades_permission(self):
        """项目职责可叠加提升权限：auditor + reviewer → wp:review 通过。"""
        user = _make_user("auditor")

        # auditor 本身无 wp:review，但 reviewer 项目角色有
        result, _calls = await _invoke_dependency(
            "wp:review", user, uuid4(), project_role="reviewer", member_level="review"
        )
        assert result == user

    @pytest.mark.asyncio
    @pytest.mark.parametrize("role", ["admin", "partner", "qc"])
    async def test_write_operation_on_archived_project_is_423_first(self, role):
        """🔴 已归档项目 + 会改数据的操作 ⇒ 423，先于矩阵与成员判定（任何角色、是否成员都一样）。"""
        user = _make_user(role)

        for op in ["wp:edit", "wp:review", "report:edit", "report:sign", "note:edit"]:
            result, calls = await _invoke_dependency(
                op, user, uuid4(), project_role=None, member_level=None, project_status=ProjectStatus.archived
            )
            assert isinstance(result, HTTPException) and result.status_code == 423, f"{role} {op}: {result!r}"
            assert result.detail["error_code"] == "PROJECT_ARCHIVED"
            assert calls == {"member": [], "rls": []}

    @pytest.mark.asyncio
    async def test_view_and_archive_manage_allowed_on_archived_project(self):
        """只读查看、归档编排（要对已归档项目幂等重入）不受归档守卫限制，仍要过成员判定。"""
        user = _make_user("partner")

        for op in ["project:view", "archive:manage"]:
            result, _calls = await _invoke_dependency(
                op, user, uuid4(), member_level="edit", project_status=ProjectStatus.archived
            )
            assert result == user, op
            result, _calls = await _invoke_dependency(
                op, user, uuid4(), member_level=None, project_status=ProjectStatus.archived
            )
            _assert_member_denied(result)


class TestResolveProjectRole:
    """_resolve_project_role helper 单元测试。"""

    @pytest.mark.asyncio
    async def test_returns_none_when_no_project_id(self):
        """project_id=None 时直接返回 None。"""
        mock_db = AsyncMock()
        result = await _resolve_project_role(mock_db, uuid4(), None)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_no_record(self):
        """查无记录时返回 None。"""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await _resolve_project_role(mock_db, uuid4(), uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_role_value_string(self):
        """查到记录时返回 role.value 字符串。"""
        mock_db = AsyncMock()
        mock_role = MagicMock()
        mock_role.value = "manager"
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_role
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await _resolve_project_role(mock_db, uuid4(), uuid4())
        assert result == "manager"
