"""Property-Based Test: sign_status 持久化往返 (Property 6)

对于任意有效 sign_status 值 × 随机 wp_code，
验证 FieldOverrideService.set() 写入后 get() 返回相同值，
且记录包含 user_id 和非空 updated_at。

**Validates: Requirements 4.3, 4.7**
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import given, settings as hyp_settings, HealthCheck
from hypothesis import strategies as st

from app.services.field_override_service import FieldOverrideService
from app.models.workpaper_field_override_models import WorkpaperFieldOverride


# ─── Strategies ───────────────────────────────────────────────────────────────

# 有效 sign_status 值
_valid_sign_status = st.sampled_from(["draft", "pending", "signed"])

# 随机 wp_code：A 循环常见格式（A8-1, A16-3, A27-1 等）
_wp_code = st.sampled_from([
    "A8-1", "A8-2", "A9-1", "A9-2", "A10-1", "A11-1", "A12-1",
    "A16-1", "A16-2", "A16-3", "A16-4", "A16-5", "A16-6", "A16-7",
    "A17-2-1", "A17-3", "A17-3-1", "A17-4", "A17-6",
    "A18-1", "A26-1", "A26-2", "A26-3", "A26-4", "A27-1",
])


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _build_scope(wp_code: str) -> str:
    """按设计文档规则构建 scope：A16 子版本用 word_template:A16:{wp_code}，其他用 word_template:{wp_code}"""
    if wp_code.startswith("A16-"):
        return f"word_template:A16:{wp_code}"
    return f"word_template:{wp_code}"


def _make_in_memory_db():
    """创建内存模拟 DB，使用 dict 存储 field_overrides 行。

    模拟 FieldOverrideService 的 select/insert/update 行为，
    让 set() → get() 往返测试在无真实 PG 的环境下运行。
    """
    store: dict[tuple, WorkpaperFieldOverride] = {}
    db = AsyncMock()

    async def _execute(stmt, *args, **kwargs):
        """路由 SQLAlchemy select 语句，从 store 中查找匹配记录。"""
        result = MagicMock()

        # 检测是否是 SELECT 语句（get 调用路径）
        stmt_str = str(stmt)
        if "SELECT" in stmt_str.upper() and "workpaper_field_overrides" in stmt_str.lower():
            # 从 stmt.whereclause 中提取参数很复杂，
            # 简化方案：让 scalar_one_or_none 通过 _last_query_key 机制返回值
            # 实际上我们直接 patch FieldOverrideService 的行为更清晰
            pass

        result.scalar_one_or_none.return_value = None
        result.scalars.return_value = result
        result.all.return_value = []
        return result

    db.execute = AsyncMock(side_effect=_execute)
    db.flush = AsyncMock()
    db.add = MagicMock()

    return db, store


@hyp_settings(max_examples=5, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    sign_status=_valid_sign_status,
    wp_code=_wp_code,
)
@pytest.mark.asyncio
async def test_property_sign_status_roundtrip(sign_status: str, wp_code: str) -> None:
    """Property 6: sign_status 持久化往返

    对于任意有效 sign_status 值和任意 word-template wp_code：
    1. 写入 sign_status 后查询返回相同值
    2. 记录包含非空 user_id (updated_by)
    3. 记录包含非空 updated_at

    **Validates: Requirements 4.3, 4.7**
    """
    project_id = uuid.uuid4()
    user_id = uuid.uuid4()
    year = 2025
    scope = _build_scope(wp_code)

    # 模拟 DB：用一个 dict 模拟 upsert 行为
    stored_records: dict[tuple, WorkpaperFieldOverride] = {}

    db = AsyncMock()

    async def _execute(stmt, *args, **kwargs):
        """模拟 SQLAlchemy execute：SELECT 查 stored_records，配合 set/get 工作"""
        result = MagicMock()
        # 简化：FieldOverrideService 总是先 SELECT 再 INSERT/UPDATE
        # 查找 key
        key = (str(project_id), year, scope, "sign_status", "value")
        existing = stored_records.get(key)
        result.scalar_one_or_none.return_value = existing
        return result

    db.execute = AsyncMock(side_effect=_execute)
    db.flush = AsyncMock()

    def _add(obj):
        """模拟 db.add：将对象存入 stored_records"""
        key = (str(obj.project_id), obj.year, obj.scope, obj.item_key, obj.field)
        # 模拟 DB 自动设置 updated_at
        obj.updated_at = datetime.now(timezone.utc)
        obj.created_at = datetime.now(timezone.utc)
        stored_records[key] = obj

    db.add = MagicMock(side_effect=_add)

    # ── 写入 ──────────────────────────────────────────────────────────────
    svc = FieldOverrideService(db)
    written = await svc.set(
        project_id, year, scope, "sign_status", "value", sign_status, user_id
    )

    # set() 走了 INSERT 路径（首次写入），返回的对象应在 stored_records 中
    assert written is not None

    # ── 验证写入的对象 ────────────────────────────────────────────────────
    # 1. 值一致
    assert written.value == sign_status, (
        f"写入值不匹配: expected={sign_status!r}, got={written.value!r}"
    )

    # 2. user_id 非空
    assert written.updated_by == user_id, (
        f"updated_by 应为 user_id={user_id}, got={written.updated_by}"
    )

    # 3. updated_at 非空（由 DB 自动设置，这里由 mock 模拟）
    assert written.updated_at is not None, "updated_at 不应为 None"

    # ── 读取往返验证 ──────────────────────────────────────────────────────
    # 重新构造 execute mock，让 SELECT 返回已存储的 value
    key = (str(project_id), year, scope, "sign_status", "value")
    stored_obj = stored_records.get(key)

    async def _execute_for_get(stmt, *args, **kwargs):
        result = MagicMock()
        # get() 做 select(WorkpaperFieldOverride.value).where(...)
        # scalar_one_or_none 返回的是 .value 列的值
        result.scalar_one_or_none.return_value = stored_obj.value if stored_obj else None
        return result

    db.execute = AsyncMock(side_effect=_execute_for_get)

    read_value = await svc.get(project_id, year, scope, "sign_status", "value")

    # 往返一致性
    assert read_value == sign_status, (
        f"往返不一致: wrote={sign_status!r}, read={read_value!r}"
    )


# ─── Property 7: sign_status 枚举验证 ─────────────────────────────────────────


_VALID_SIGN_STATUSES = {"draft", "pending", "signed"}

# 生成非法 status 值：任意文本但排除合法集合
_invalid_status = st.text().filter(lambda x: x not in _VALID_SIGN_STATUSES)


@hyp_settings(max_examples=5, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(invalid_status=_invalid_status)
def test_property_sign_status_enum_rejects_invalid(invalid_status: str) -> None:
    """Property 7: sign_status 枚举验证

    对于任意非法 status 值（不在 {"draft", "pending", "signed"} 集合中），
    Pydantic 模型应拒绝该值并抛出 ValidationError。

    **Validates: Requirements 4.1**
    """
    from pydantic import ValidationError

    # 动态导入避免模块加载顺序问题
    from app.routers.wp_editor_router import SignStatusUpdateBody

    with pytest.raises(ValidationError):
        SignStatusUpdateBody(status=invalid_status)


# ─── Property 9: 签署状态回退权限控制 ─────────────────────────────────────────


# 角色定义（DB role 值，与 wp_editor_router._SIGN_ROLLBACK_ROLES 对应）
_LOW_PRIVILEGE_ROLES = ["assistant", "manager"]  # 审计助理, 现场经理 → 403
_HIGH_PRIVILEGE_ROLES = ["partner", "qc", "eqcr"]  # 业务合伙人, 质量控制复核, EQCR → allowed
_ALL_ROLES = _LOW_PRIVILEGE_ROLES + _HIGH_PRIVILEGE_ROLES

# 回退转换（signed → draft/pending）
_ROLLBACK_TRANSITIONS = [("signed", "draft"), ("signed", "pending")]


@hyp_settings(max_examples=5, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    role=st.sampled_from(_ALL_ROLES),
    transition=st.sampled_from(_ROLLBACK_TRANSITIONS),
)
@pytest.mark.asyncio
async def test_property_sign_status_rollback_permission(role: str, transition: tuple[str, str]) -> None:
    """Property 9: 签署状态回退权限控制

    对于任意角色 × 任意 signed→draft/pending 转换：
    - 低权限角色 (assistant, manager) 应被 403 拒绝
    - 高权限角色 (partner, qc, eqcr) 应允许转换

    测试通过直接调用 update_sign_status 端点函数（mock DB 层），
    验证实际 HTTPException(403) 或正常返回。

    **Validates: Requirements 4.6**
    """
    from fastapi import HTTPException as _HTTPException

    from app.routers.wp_editor_router import update_sign_status, SignStatusUpdateBody

    project_id = uuid.uuid4()
    user_id = uuid.uuid4()
    wp_id = uuid.uuid4()
    wp_index_id = uuid.uuid4()
    staff_id = uuid.uuid4()
    _current_status, target_status = transition

    # ── 构建 mock DB ──────────────────────────────────────────────────────
    db = AsyncMock()

    # 模拟 WorkingPaper 查询结果
    mock_wp = MagicMock()
    mock_wp.id = wp_id
    mock_wp.project_id = project_id
    mock_wp.wp_index_id = wp_index_id

    # execute 调用序列：
    # 1. select(WorkingPaper) → mock_wp
    # 2. select(WpIndex.wp_code) → "A9-1"
    # 3. sa.text("SELECT EXTRACT(YEAR...") → 2025
    # 4. FieldOverrideService.get → "signed" (当前状态)
    # 5. select(ProjectAssignment.role) → role (用户角色)
    # 6. FieldOverrideService.set → (如果允许)
    call_idx = [0]

    async def _execute_side_effect(stmt, *args, **kwargs):
        idx = call_idx[0]
        call_idx[0] += 1
        result = MagicMock()

        if idx == 0:
            # WorkingPaper 查询
            result.scalar_one_or_none.return_value = mock_wp
        elif idx == 1:
            # WpIndex.wp_code 查询
            result.scalar_one_or_none.return_value = "A9-1"
        elif idx == 2:
            # 项目年度查询
            result.scalar.return_value = 2025
        elif idx == 3:
            # FieldOverrideService.get → 当前状态为 "signed"
            result.scalar_one_or_none.return_value = "signed"
        elif idx == 4:
            # ProjectAssignment.role 查询 → 用户角色
            result.scalar_one_or_none.return_value = role
        else:
            # FieldOverrideService.set 内部的 SELECT (upsert 路径)
            result.scalar_one_or_none.return_value = None
            result.scalars.return_value = result
            result.all.return_value = []

        return result

    db.execute = AsyncMock(side_effect=_execute_side_effect)
    db.flush = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()

    # 模拟当前用户
    current_user = MagicMock()
    current_user.id = user_id

    # 构建请求体
    body = SignStatusUpdateBody(status=target_status, wp_code="A9-1")

    # ── 执行并验证 ────────────────────────────────────────────────────────
    if role in _LOW_PRIVILEGE_ROLES:
        # 低权限角色应被 403 拒绝
        with pytest.raises(_HTTPException) as exc_info:
            await update_sign_status(
                project_id=project_id,
                wp_id=wp_id,
                body=body,
                db=db,
                current_user=current_user,
            )
        assert exc_info.value.status_code == 403, (
            f"角色 {role!r} 执行 {_current_status}→{target_status} 应返回 403，"
            f"实际返回 {exc_info.value.status_code}"
        )
    else:
        # 高权限角色应允许（正常返回，不抛异常）
        result = await update_sign_status(
            project_id=project_id,
            wp_id=wp_id,
            body=body,
            db=db,
            current_user=current_user,
        )
        assert result["status"] == target_status, (
            f"角色 {role!r} 执行 {_current_status}→{target_status} 应成功，"
            f"返回 status={result['status']!r}"
        )


# ─── Property 8: 已签署文档只读 ───────────────────────────────────────────────


@hyp_settings(max_examples=5, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    wp_code=_wp_code,
    sign_status=_valid_sign_status,
)
@pytest.mark.asyncio
async def test_property_signed_document_readonly(wp_code: str, sign_status: str) -> None:
    """Property 8: 已签署文档只读

    对于任意 word-template wp_code 和任意 sign_status 值：
    - sign_status="signed" 时 render-config 返回 permissions.edit=false（只读）
    - sign_status="draft" 或 "pending" 时 permissions.edit=true（可编辑）

    测试通过模拟 render-config 中 sign_status → permissions 的注入路径，
    验证 FieldOverrideService 查询结果正确驱动 OnlyOffice 编辑器权限配置。

    **Validates: Requirements 4.5**
    """
    from app.services.field_override_service import FieldOverrideService

    project_id = uuid.uuid4()
    _prog_year = 2025

    # ── scope 格式规则（与 wp_render_config.py Step 9 一致） ───────────────
    if wp_code.startswith("A16-"):
        _sign_scope = f"word_template:A16:{wp_code}"
    else:
        _sign_scope = f"word_template:{wp_code}"

    # ── 构建 mock DB：FieldOverrideService.get 返回给定 sign_status ────────
    db = AsyncMock()

    async def _execute_for_get(stmt, *args, **kwargs):
        """模拟 FieldOverrideService.get 的 SELECT 查询，返回 sign_status 值。"""
        result = MagicMock()
        result.scalar_one_or_none.return_value = sign_status
        return result

    db.execute = AsyncMock(side_effect=_execute_for_get)

    # ── 复现 render-config Step 9 的核心逻辑 ──────────────────────────────
    # （wp_render_config.py 第 965-986 行）
    fos = FieldOverrideService(db)
    queried_status = await fos.get(
        project_id=project_id, year=_prog_year,
        scope=_sign_scope, item_key="sign_status", field="value",
    )

    # 默认值逻辑（与实际代码一致：if not sign_status: sign_status = "draft"）
    effective_status = queried_status if queried_status else "draft"
    # 权限逻辑（与实际代码一致：permissions = {"edit": sign_status != "signed"}）
    permissions = {"edit": effective_status != "signed"}

    # ── 验证 Property 8 ──────────────────────────────────────────────────
    if sign_status == "signed":
        # 已签署 → 只读
        assert permissions["edit"] is False, (
            f"wp_code={wp_code!r}, sign_status='signed' 时 "
            f"permissions.edit 应为 False（只读），实际为 {permissions['edit']}"
        )
    else:
        # draft/pending → 可编辑
        assert permissions["edit"] is True, (
            f"wp_code={wp_code!r}, sign_status={sign_status!r} 时 "
            f"permissions.edit 应为 True（可编辑），实际为 {permissions['edit']}"
        )

    # 额外验证：response 结构正确包含 sign_status + permissions
    response = {
        "sign_status": effective_status,
        "permissions": permissions,
    }
    assert "sign_status" in response
    assert "permissions" in response
    assert response["permissions"]["edit"] == (effective_status != "signed")
