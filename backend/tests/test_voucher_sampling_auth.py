"""抽凭端点服务端授权校验测试（voucher-sampling-hardening Task 11）

Property 15：跨项目底稿 / 非审计期年度 / 无编辑权 → 端点拒绝（不依赖前端隐藏按钮）。

Validates: Requirements 8.1, 8.2, 8.3, 8.4
Properties: Property 15
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.models.base import UserRole
from app.routers.voucher_sampling import _authorize_and_validate_extract

_PID = uuid.uuid4()
_WP = uuid.uuid4()


class _FakeUser:
    id = uuid.uuid4()
    username = "审计助理"
    role = UserRole.auditor


def _db_with_project_row(row) -> AsyncMock:
    db = AsyncMock()
    result = MagicMock()
    result.one_or_none.return_value = row
    db.execute = AsyncMock(return_value=result)
    return db


class TestAuthorizeAndValidateExtract:
    @pytest.mark.asyncio
    async def test_cross_project_rejected_403(self):
        # 底稿所属项目 != URL 项目 → 403
        other_project = uuid.uuid4()
        db = _db_with_project_row((2025, None, None))
        with patch(
            "app.routers.voucher_sampling.authorize_wp_edit",
            new=AsyncMock(return_value=other_project),
        ):
            with pytest.raises(HTTPException) as ei:
                await _authorize_and_validate_extract(db, _FakeUser(), _PID, _WP, 2025)
        assert ei.value.status_code == 403

    @pytest.mark.asyncio
    async def test_year_mismatch_rejected_400(self):
        # 审计年度 2024 vs 请求 2025 → 400
        db = _db_with_project_row((2024, None, None))
        with patch(
            "app.routers.voucher_sampling.authorize_wp_edit",
            new=AsyncMock(return_value=_PID),
        ):
            with pytest.raises(HTTPException) as ei:
                await _authorize_and_validate_extract(db, _FakeUser(), _PID, _WP, 2025)
        assert ei.value.status_code == 400

    @pytest.mark.asyncio
    async def test_no_edit_permission_propagates_403(self):
        # authorize_wp_edit 抛 403 → 透传
        db = _db_with_project_row((2025, None, None))
        with patch(
            "app.routers.voucher_sampling.authorize_wp_edit",
            new=AsyncMock(side_effect=HTTPException(status_code=403, detail="无底稿编辑权限")),
        ):
            with pytest.raises(HTTPException) as ei:
                await _authorize_and_validate_extract(db, _FakeUser(), _PID, _WP, 2025)
        assert ei.value.status_code == 403

    @pytest.mark.asyncio
    async def test_happy_path_matching_year(self):
        # 同项目 + 审计年度匹配 → 不抛
        db = _db_with_project_row((2025, None, None))
        with patch(
            "app.routers.voucher_sampling.authorize_wp_edit",
            new=AsyncMock(return_value=_PID),
        ):
            await _authorize_and_validate_extract(db, _FakeUser(), _PID, _WP, 2025)

    @pytest.mark.asyncio
    async def test_no_project_row_does_not_block(self):
        # 项目行取不到 → 不做年度阻断（无从校验），仅归属已通过
        db = _db_with_project_row(None)
        with patch(
            "app.routers.voucher_sampling.authorize_wp_edit",
            new=AsyncMock(return_value=_PID),
        ):
            await _authorize_and_validate_extract(db, _FakeUser(), _PID, _WP, 2025)

    @pytest.mark.asyncio
    async def test_period_range_fallback_when_no_audit_year(self):
        # audit_year 为空 → 回退审计期起止年份区间
        from datetime import date

        db = _db_with_project_row((None, date(2025, 1, 1), date(2025, 12, 31)))
        with patch(
            "app.routers.voucher_sampling.authorize_wp_edit",
            new=AsyncMock(return_value=_PID),
        ):
            # 2025 在区间内 → 通过
            await _authorize_and_validate_extract(db, _FakeUser(), _PID, _WP, 2025)
            # 2023 不在区间 → 400
            with pytest.raises(HTTPException) as ei:
                await _authorize_and_validate_extract(db, _FakeUser(), _PID, _WP, 2023)
        assert ei.value.status_code == 400
