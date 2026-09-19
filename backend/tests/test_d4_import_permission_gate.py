"""D4 导入/导出端点权限门禁单元测试（P0-项5）

spec: .kiro/specs/d4-dual-mode-formula-governance/

背景（实测发现，修正契约报告结论）：
    ``/api/workpapers/{wp_id}/d4/*`` 路由在 router_registry 注册时已附加 router-level
    依赖 ``dedicated_wp_gate``（Wp_Bound_Gate 可见性/委派门，按 HTTP method 分 read/write）。
    故这些端点**并非"零权限"**——此前契约报告只看函数签名 Depends（get_current_user+get_db），
    漏看了 router-level 依赖。本次新增的项目级编辑权（``authorize_wp_edit``）+ 合并锁
    （``check_consol_lock``）是**额外**的纵深防御，且补上了可见性门**不覆盖的合并锁**。

测试口径：
    ``dedicated_wp_gate`` 用真实 DB 连接做可见性判定，全 ASGI 集成测试需真实 seed 的 wp
    才能穿过它——本地无该 fixture。因此本文件**直接单元测试新增的授权逻辑**：
      - ``authorize_wp_edit`` / ``authorize_wp_read``（对 readonly/qc/非成员/admin 的判定）。
      - ``d4_import_data`` 函数体：门禁先于 xlsx 解析与任何 DB 写（校验失败 → 无 commit）。
    这些是本次改动引入的安全代码，直调即可确定性验证（不经 router-level 门）。
"""

from __future__ import annotations

import io
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException, UploadFile
from openpyxl import Workbook

from app.deps import authorize_wp_edit, authorize_wp_read
from app.models.base import UserRole
from app.routers.wp_render_strategies._d4_import_export import d4_import_data


_WP_ID = uuid4()
_PROJECT_ID = uuid4()


def _make_user(role: UserRole):
    u = MagicMock()
    u.id = uuid4()
    u.role = MagicMock(value=role.value)
    return u


def _scalar_result(value):
    res = MagicMock()
    res.scalar_one_or_none = MagicMock(return_value=value)
    return res


def _d4_2_xlsx_bytes() -> bytes:
    from app.routers.wp_render_strategies._d4_import_export import _get_headers

    wb = Workbook()
    ws = wb.active
    ws.title = "D4-2"
    ws.append(_get_headers("D4-2"))
    ws.append(["产品A"] + [100] * 12 + [1200, 0, 1200, 1000, 0, 1000, 0, 0, ""])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _upload() -> UploadFile:
    return UploadFile(filename="D4-2.xlsx", file=io.BytesIO(_d4_2_xlsx_bytes()))


# ═══════════════════════════════════════════════════════════════════════════════
# authorize_wp_edit — 写权限
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
@pytest.mark.parametrize("role", [UserRole.readonly, UserRole.qc])
async def test_authorize_wp_edit_denies_non_write_roles_before_db(role):
    """readonly/qc 无 WORKPAPER_WRITE → 403，且**查库前**即拒（execute 零调用）。"""
    db = AsyncMock()
    db.execute = AsyncMock()
    with pytest.raises(HTTPException) as ei:
        await authorize_wp_edit(db, _make_user(role), _WP_ID)
    assert ei.value.status_code == 403
    assert db.execute.await_count == 0  # 未查库 = 无副作用


@pytest.mark.asyncio
async def test_authorize_wp_edit_denies_non_member():
    """auditor（有 WORKPAPER_WRITE）但非项目成员 → 403。"""
    db = AsyncMock()

    def _side(stmt, *a, **k):
        sql = str(getattr(stmt, "text", stmt)).lower()
        if "working_paper" in sql:
            return _scalar_result(_PROJECT_ID)  # 底稿存在
        return _scalar_result(None)  # project_users → 非成员

    db.execute = AsyncMock(side_effect=_side)
    with pytest.raises(HTTPException) as ei:
        await authorize_wp_edit(db, _make_user(UserRole.auditor), _WP_ID)
    assert ei.value.status_code == 403


@pytest.mark.asyncio
async def test_authorize_wp_edit_404_when_wp_missing():
    """底稿不存在 → 404（auditor 有写能力，走到查底稿分支）。"""
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_scalar_result(None))  # WorkingPaper.project_id → None
    with pytest.raises(HTTPException) as ei:
        await authorize_wp_edit(db, _make_user(UserRole.auditor), _WP_ID)
    assert ei.value.status_code == 404


@pytest.mark.asyncio
async def test_authorize_wp_edit_admin_allowed():
    """admin 全局放行（底稿存在时返回 project_id）。"""
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_scalar_result(_PROJECT_ID))
    pid = await authorize_wp_edit(db, _make_user(UserRole.admin), _WP_ID)
    assert pid == _PROJECT_ID


# ═══════════════════════════════════════════════════════════════════════════════
# authorize_wp_read — 读权限（不误伤 readonly）
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_authorize_wp_read_allows_readonly_member():
    """readonly 项目成员 → 放行（读操作不被提到 edit）。"""
    db = AsyncMock()

    def _side(stmt, *a, **k):
        sql = str(getattr(stmt, "text", stmt)).lower()
        if "working_paper" in sql:
            return _scalar_result(_PROJECT_ID)
        pu = MagicMock()
        pu.permission_level = MagicMock(value="readonly")
        return _scalar_result(pu)

    db.execute = AsyncMock(side_effect=_side)
    pid = await authorize_wp_read(db, _make_user(UserRole.readonly), _WP_ID)
    assert pid == _PROJECT_ID


@pytest.mark.asyncio
async def test_authorize_wp_read_denies_non_member():
    """非项目成员读 → 403。"""
    db = AsyncMock()

    def _side(stmt, *a, **k):
        sql = str(getattr(stmt, "text", stmt)).lower()
        if "working_paper" in sql:
            return _scalar_result(_PROJECT_ID)
        return _scalar_result(None)

    db.execute = AsyncMock(side_effect=_side)
    with pytest.raises(HTTPException) as ei:
        await authorize_wp_read(db, _make_user(UserRole.readonly), _WP_ID)
    assert ei.value.status_code == 403


# ═══════════════════════════════════════════════════════════════════════════════
# d4_import_data 函数体：门禁先于解析与写入
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_d4_import_gate_blocks_before_write_for_readonly():
    """readonly 直调 d4_import_data → 403，且 commit 从未发生（无 DB 变更）。"""
    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    with pytest.raises(HTTPException) as ei:
        await d4_import_data(
            wp_id=str(_WP_ID),
            sheet="D4-2",
            file=_upload(),
            db=db,
            current_user=_make_user(UserRole.readonly),
        )
    assert ei.value.status_code == 403
    db.commit.assert_not_awaited()
    assert db.execute.await_count == 0  # 门禁在查库前拦下 = xlsx 未解析、行未写


@pytest.mark.asyncio
async def test_d4_import_gate_blocks_when_consol_locked():
    """项目被合并锁定 → 423，且无写入。"""
    db = AsyncMock()

    def _side(stmt, *a, **k):
        sql = str(getattr(stmt, "text", stmt)).lower()
        if "consol_lock" in sql:
            return _scalar_result(True)  # 已锁定
        # authorize_wp_edit：admin → 查底稿 project_id
        return _scalar_result(_PROJECT_ID)

    db.execute = AsyncMock(side_effect=_side)
    db.commit = AsyncMock()
    with pytest.raises(HTTPException) as ei:
        await d4_import_data(
            wp_id=str(_WP_ID),
            sheet="D4-2",
            file=_upload(),
            db=db,
            current_user=_make_user(UserRole.admin),
        )
    assert ei.value.status_code == 423
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_d4_import_invalid_wp_uuid_404():
    """非法 wp_id UUID → 404（不泄露内部错误）。"""
    db = AsyncMock()
    db.commit = AsyncMock()
    with pytest.raises(HTTPException) as ei:
        await d4_import_data(
            wp_id="not-a-uuid",
            sheet="D4-2",
            file=_upload(),
            db=db,
            current_user=_make_user(UserRole.admin),
        )
    assert ei.value.status_code == 404
    db.commit.assert_not_awaited()
