"""Unit tests for require_operation dependency factory.

验证 require_operation 结合 permission_matrix_service.can() 的授权逻辑。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.deps import require_operation, _resolve_project_role


# ─── Helper: 构建 mock user ──────────────────────────────────────────────────

def _make_user(role: str):
    """创建具有指定 system_role 的 mock User 对象。"""
    user = MagicMock()
    user.id = uuid4()
    user.role = MagicMock()
    user.role.value = role
    return user


# ─── Helper: 调用 require_operation 内部 dependency ─────────────────────────

async def _invoke_dependency(operation: str, user, project_id=None, project_role=None):
    """直接调用 require_operation 产生的内部 dependency 函数。

    模拟 FastAPI 注入的 current_user, project_id, db。
    """
    from fastapi import HTTPException

    dep_fn = require_operation(operation)
    # dep_fn 是工厂返回的 async dependency 函数
    # 获取内部函数（闭包中的第一个 co_consts 或直接调用）
    inner = dep_fn  # require_operation 返回的就是 async def dependency

    # mock db
    mock_db = AsyncMock()

    # patch _resolve_project_role 以控制返回值
    with patch("app.deps._resolve_project_role", return_value=project_role):
        try:
            result = await inner(
                current_user=user,
                project_id=project_id,
                db=mock_db,
            )
            return result
        except HTTPException as exc:
            return exc


# ─── Tests ───────────────────────────────────────────────────────────────────


class TestRequireOperation:
    """require_operation 权限矩阵集成测试。"""

    @pytest.mark.asyncio
    async def test_admin_passes_any_operation(self):
        """admin 系统角色对任何 operation 均通过。"""
        user = _make_user("admin")
        project_id = uuid4()

        for op in ["wp:edit", "report:sign", "archive:manage", "note:edit"]:
            result = await _invoke_dependency(op, user, project_id, project_role=None)
            assert result == user, f"admin should pass {op}"

    @pytest.mark.asyncio
    async def test_auditor_denied_report_sign(self):
        """auditor 无 report:sign 权限 → 403 OPERATION_NOT_ALLOWED。"""
        user = _make_user("auditor")
        project_id = uuid4()

        result = await _invoke_dependency(
            "report:sign", user, project_id, project_role="preparer"
        )
        # 应该是 HTTPException
        from fastapi import HTTPException
        assert isinstance(result, HTTPException)
        assert result.status_code == 403
        assert result.detail["error_code"] == "OPERATION_NOT_ALLOWED"
        assert result.detail["operation"] == "report:sign"

    @pytest.mark.asyncio
    async def test_manager_passes_wp_edit(self):
        """manager 有 wp:edit 权限 → 通过。"""
        user = _make_user("manager")
        project_id = uuid4()

        result = await _invoke_dependency(
            "wp:edit", user, project_id, project_role="manager"
        )
        assert result == user

    @pytest.mark.asyncio
    async def test_no_project_role_uses_system_role_only(self):
        """无 project_id 时 project_role=None，仅依据 system_role 判断。"""
        # manager 没有 report:sign 权限
        user = _make_user("manager")

        result = await _invoke_dependency(
            "report:sign", user, project_id=None, project_role=None
        )
        from fastapi import HTTPException
        assert isinstance(result, HTTPException)
        assert result.status_code == 403

    @pytest.mark.asyncio
    async def test_partner_passes_all(self):
        """partner 系统角色拥有全部操作权限。"""
        user = _make_user("partner")
        project_id = uuid4()

        for op in ["wp:edit", "report:sign", "archive:manage"]:
            result = await _invoke_dependency(op, user, project_id, project_role=None)
            assert result == user, f"partner should pass {op}"

    @pytest.mark.asyncio
    async def test_project_role_upgrades_permission(self):
        """项目职责可叠加提升权限：auditor + reviewer → wp:review 通过。"""
        user = _make_user("auditor")
        project_id = uuid4()

        # auditor 本身无 wp:review，但 reviewer 项目角色有
        result = await _invoke_dependency(
            "wp:review", user, project_id, project_role="reviewer"
        )
        assert result == user


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
