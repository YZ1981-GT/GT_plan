"""底稿→附注同步的目标年度语义（回归守卫）。

背景（真实缺陷）：各披露组件历史上普遍不传 ``year``，而 ``_derive_year(None)``
fallback 到服务器当前自然年 → 2026 年做 2025 年报审计时，同步写到 year=2026 的
附注记录，审计师在附注模块（按 ``projects.audit_year`` 渲染）永远看不到。
DB 实证曾有 4 条 year=2026 孤儿记录（F3 五、36/八、36、H9 五、47、H10 三、资产处置收益）。

修复：同步路径统一走 ``_resolve_target_year``，以 ``projects.audit_year`` 为权威；
payload 显式 year 仍优先；两者都取不到才回落当前自然年。

Properties:
- P-Y1 payload 显式 year 优先（不查库）
- P-Y2 payload 无 year → 用 projects.audit_year
- P-Y3 audit_year 缺失/非法 → 回落当前自然年（fail-open，不抛）
- P-Y4 查询异常 → fail-open 回落当前自然年
- P-Y5 纯函数 _derive_year 行为不变（零回归）
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.wp_disclosure_sync_service import (
    _derive_year,
    _resolve_project_audit_year,
    _resolve_target_year,
)

PROJECT_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
CURRENT_YEAR = datetime.now(timezone.utc).year


def _db_returning(value: object, *, raises: bool = False) -> MagicMock:
    """构造只需 execute().scalar_one_or_none() 的 mock session。"""
    db = MagicMock(spec=AsyncSession)
    if raises:
        db.execute = AsyncMock(side_effect=RuntimeError("db down"))
    else:
        result = MagicMock()
        result.scalar_one_or_none = MagicMock(return_value=value)
        db.execute = AsyncMock(return_value=result)
    return db


class TestDeriveYearPure:
    """P-Y5：纯兜底函数行为不变（零回归）。"""

    def test_payload_year_wins(self):
        assert _derive_year(2025) == 2025

    def test_none_falls_back_to_current_natural_year(self):
        assert _derive_year(None) == CURRENT_YEAR

    def test_zero_and_bool_fall_back(self):
        assert _derive_year(0) == CURRENT_YEAR


class TestResolveProjectAuditYear:
    @pytest.mark.asyncio
    async def test_returns_audit_year(self):
        db = _db_returning(2025)
        assert await _resolve_project_audit_year(db, PROJECT_ID) == 2025

    @pytest.mark.asyncio
    async def test_none_when_missing(self):
        db = _db_returning(None)
        assert await _resolve_project_audit_year(db, PROJECT_ID) is None

    @pytest.mark.asyncio
    async def test_none_when_invalid(self):
        assert await _resolve_project_audit_year(_db_returning(0), PROJECT_ID) is None
        assert await _resolve_project_audit_year(_db_returning("2025"), PROJECT_ID) is None

    @pytest.mark.asyncio
    async def test_fail_open_on_db_error(self):
        """P-Y4：查询异常不抛，返回 None 交由上层回落。"""
        db = _db_returning(None, raises=True)
        assert await _resolve_project_audit_year(db, PROJECT_ID) is None


class TestResolveTargetYear:
    @pytest.mark.asyncio
    async def test_payload_year_wins_without_db_query(self):
        """P-Y1：显式 year 优先，且不触库。"""
        db = _db_returning(2099)
        assert await _resolve_target_year(db, PROJECT_ID, 2025) == 2025
        db.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_uses_project_audit_year_when_payload_missing(self):
        """P-Y2：这是修复的核心——不传 year 时落项目审计年度而非服务器当前年。"""
        db = _db_returning(2025)
        assert await _resolve_target_year(db, PROJECT_ID, None) == 2025

    @pytest.mark.asyncio
    async def test_falls_back_to_current_year_when_audit_year_missing(self):
        """P-Y3：审计年度缺失时回落当前自然年（保持旧行为，不抛）。"""
        db = _db_returning(None)
        assert await _resolve_target_year(db, PROJECT_ID, None) == CURRENT_YEAR

    @pytest.mark.asyncio
    async def test_falls_back_to_current_year_on_db_error(self):
        db = _db_returning(None, raises=True)
        assert await _resolve_target_year(db, PROJECT_ID, None) == CURRENT_YEAR
