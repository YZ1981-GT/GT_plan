"""D4 导入乐观锁（CAS/If-Match）单元测试（P0-项4）

spec: .kiro/specs/d4-dual-mode-formula-governance/

验证 ``_upsert_checklist_response`` 的并发一致性口径：
  - 提供 base_version 且与服务端当前版本不符 → 409 VERSION_CONFLICT，**不写入**（无覆盖）。
  - base_version 相符 → content_version + 1 写入。
  - base_version=None（旧客户端）→ 按创建/覆盖处理（不冲突）。
  - 首次写（无既有行）→ 版本从 1 起算。

真实迁移证据：V161 已在真实 PG 应用（schema_version=161，checklist_responses.content_version 列存在）。
本文件用 mock AsyncSession 确定性验证乐观锁分支逻辑（不依赖真实并发环境）。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.routers.wp_render_strategies._d4_import_export import _upsert_checklist_response


def _db_with_current_version(current_version):
    """mock db：SELECT ... FOR UPDATE 返回既有版本；INSERT 记录参数。"""
    db = AsyncMock()
    inserts: list[dict] = []

    def _side(stmt, params=None, *a, **k):
        sql = str(getattr(stmt, "text", stmt)).lower()
        res = MagicMock()
        if "select content_version" in sql or "for update" in sql:
            if current_version is None:
                res.fetchone = MagicMock(return_value=None)
            else:
                res.fetchone = MagicMock(return_value=MagicMock(content_version=current_version))
        else:  # INSERT ... ON CONFLICT
            inserts.append(params or {})
            res.fetchone = MagicMock(return_value=None)
        return res

    db.execute = AsyncMock(side_effect=_side)
    db._inserts = inserts
    return db


@pytest.mark.asyncio
async def test_cas_mismatch_returns_409_no_write():
    """base_version 过期（!= 当前）→ 409，且不发生 INSERT/UPDATE。"""
    db = _db_with_current_version(current_version=5)
    with pytest.raises(HTTPException) as ei:
        await _upsert_checklist_response(
            db, project_id=str(uuid4()), wp_id=str(uuid4()),
            item_id="D4-2-rows", remark="{}", base_version=3,
        )
    assert ei.value.status_code == 409
    assert ei.value.detail["error_code"] == "VERSION_CONFLICT"
    assert ei.value.detail["current_version"] == 5
    assert db._inserts == [], "版本冲突后不应写入"


@pytest.mark.asyncio
async def test_cas_match_increments_version():
    """base_version 相符 → content_version + 1 写入，返回新版本。"""
    db = _db_with_current_version(current_version=5)
    new_version = await _upsert_checklist_response(
        db, project_id=str(uuid4()), wp_id=str(uuid4()),
        item_id="D4-2-rows", remark='{"rows":[]}', base_version=5,
    )
    assert new_version == 6
    assert len(db._inserts) == 1
    assert db._inserts[0]["version"] == 6


@pytest.mark.asyncio
async def test_cas_none_base_version_overwrites():
    """base_version=None（旧客户端）→ 不做冲突检测，按覆盖处理。"""
    db = _db_with_current_version(current_version=9)
    new_version = await _upsert_checklist_response(
        db, project_id=str(uuid4()), wp_id=str(uuid4()),
        item_id="D4-2-rows", remark="{}", base_version=None,
    )
    assert new_version == 10  # current+1
    assert len(db._inserts) == 1


@pytest.mark.asyncio
async def test_cas_first_write_starts_at_1():
    """无既有行（首次写）→ 版本从 1 起算，即便声明了 base_version 也不冲突。"""
    db = _db_with_current_version(current_version=None)
    new_version = await _upsert_checklist_response(
        db, project_id=str(uuid4()), wp_id=str(uuid4()),
        item_id="D4-2-rows", remark="{}", base_version=7,
    )
    assert new_version == 1
    assert len(db._inserts) == 1
    assert db._inserts[0]["version"] == 1
