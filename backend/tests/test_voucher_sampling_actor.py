"""真实操作者留痕测试（voucher-sampling-hardening Task 8 / Property 16）

cutoff_fill 端点持久化的日志 actor 必须来自服务端认证用户（current_user.id），
不采用任何客户端可声明的身份，绝不为 'current_user' 占位符。

Validates: Requirements 9.1, 9.2
Properties: Property 16
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.models.base import UserRole
from app.routers.cutoff_sampling import CutoffFillRequest, cutoff_fill

_USER_ID = uuid.uuid4()
_PID = uuid.uuid4()
_WP = uuid.uuid4()


class _FakeUser:
    id = _USER_ID
    username = "审计助理王五"
    role = UserRole.auditor


class TestRealActorInLog:
    @pytest.mark.asyncio
    async def test_cutoff_fill_records_authenticated_actor(self):
        captured: dict = {}

        async def _capture_log(db, log_data):
            captured["user_id"] = log_data.user_id
            return {"id": str(uuid.uuid4()), "created_at": "2025-01-01T00:00:00"}

        req = CutoffFillRequest(
            workpaper_id=_WP,
            extraction_type="voucher_sampling",
            extraction_criteria={"sampling_method": "random"},
            total_matched=30,
            filled_count=10,
            fill_mode="append",
            before_data=[],
            filled_voucher_nos=["记-1", "记-2"],
        )
        db = AsyncMock()
        with patch(
            "app.routers.cutoff_sampling.VersionTrailService.create_snapshot_fire_and_forget",
            new=AsyncMock(return_value=None),
        ), patch(
            "app.routers.cutoff_sampling.LedgerSamplingService.record_extraction_log",
            new=_capture_log,
        ):
            await cutoff_fill(pid=_PID, req=req, db=db, current_user=_FakeUser())

        # 权威 actor = 认证用户 id，绝非 'current_user' 占位符
        assert captured["user_id"] == _USER_ID
        assert str(captured["user_id"]) != "current_user"
