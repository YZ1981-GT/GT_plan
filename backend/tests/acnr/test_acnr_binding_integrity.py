"""集成测试: wp_id binding 三元组匹配 — 不匹配 → 403 [P4]

Property 4 (P4): 携带 explicit_wp_id 时，端点校验该 wp_id 属于请求的
    project_id 且对应 WpIndex.wp_code 与 sheet_code 匹配。
    任一不匹配 → 403。

测试策略:
- Mock DB 模拟各种 binding 不匹配场景
- 验证 verify_wp_binding 对不匹配情况 raise 403
- 验证匹配情况正常通过

Validates: Requirements 3.2, 3.3
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_BACKEND_ROOT))

from fastapi import HTTPException

from app.services.acnr.auth import verify_wp_binding


# ─── Fixtures / Helpers ───────────────────────────────────────────────────────

_PROJECT_ID = uuid4()
_WP_ID = uuid4()
_SHEET_CODE = "D2-2"


def _mock_session_binding_ok(wp_code: str = "D2-2") -> AsyncMock:
    """模拟 DB: wp_id 属于 project_id 且 wp_code 匹配。"""
    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.fetchone.return_value = (wp_code,)
    session.execute.return_value = mock_result
    return session


def _mock_session_wp_not_in_project() -> AsyncMock:
    """模拟 DB: wp_id 不属于 project_id（查询返回 None）。"""
    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.fetchone.return_value = None
    session.execute.return_value = mock_result
    return session


def _mock_session_wp_code_mismatch(actual_wp_code: str = "K1-12") -> AsyncMock:
    """模拟 DB: wp_id 属于 project 但 wp_code 与 sheet_code 不匹配。"""
    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.fetchone.return_value = (actual_wp_code,)
    session.execute.return_value = mock_result
    return session


# ═══════════════════════════════════════════════════════════════════════════════
# Property 4: wp_id binding 三元组匹配 — 集成测试
# ═══════════════════════════════════════════════════════════════════════════════


class TestP4BindingIntegrity:
    """P4: wp_id binding 三元组 (wp_id, project_id, sheet_code) 不匹配 → 403。

    **Validates: Requirements 3.2**
    """

    def test_valid_binding_passes(self):
        """三元组匹配时正常通过，不 raise。"""
        session = _mock_session_binding_ok("D2-2")

        # 不应 raise
        asyncio.new_event_loop().run_until_complete(
            verify_wp_binding(_WP_ID, _PROJECT_ID, "D2-2", session)
        )

    def test_wp_not_in_project_raises_403(self):
        """wp_id 不属于 project_id → 403。"""
        session = _mock_session_wp_not_in_project()

        with pytest.raises(HTTPException) as exc_info:
            asyncio.new_event_loop().run_until_complete(
                verify_wp_binding(_WP_ID, _PROJECT_ID, _SHEET_CODE, session)
            )

        assert exc_info.value.status_code == 403

    def test_sheet_code_mismatch_raises_403(self):
        """wp_id 属于 project 但 wp_code 与请求的 sheet_code 不匹配 → 403。"""
        session = _mock_session_wp_code_mismatch("K1-12")

        with pytest.raises(HTTPException) as exc_info:
            asyncio.new_event_loop().run_until_complete(
                verify_wp_binding(_WP_ID, _PROJECT_ID, "D2-2", session)
            )

        assert exc_info.value.status_code == 403

    def test_403_does_not_leak_wp_id(self):
        """403 响应不泄露 wp_id 信息 (Req-3.3)。"""
        session = _mock_session_wp_not_in_project()

        with pytest.raises(HTTPException) as exc_info:
            asyncio.new_event_loop().run_until_complete(
                verify_wp_binding(_WP_ID, _PROJECT_ID, _SHEET_CODE, session)
            )

        detail = str(exc_info.value.detail)
        assert str(_WP_ID) not in detail
        assert "wp_id" not in detail
        assert "jump_route" not in detail

    def test_different_sheet_codes_mismatch(self):
        """各种 sheet_code 不匹配场景均 → 403。"""
        # DB 中 wp_code 是 "F1-2"，请求的 sheet_code 是 "D2-2"
        session = _mock_session_wp_code_mismatch("F1-2")

        with pytest.raises(HTTPException) as exc_info:
            asyncio.new_event_loop().run_until_complete(
                verify_wp_binding(_WP_ID, _PROJECT_ID, "D2-2", session)
            )

        assert exc_info.value.status_code == 403

    def test_deleted_wp_treated_as_not_found(self):
        """已删除的 working_paper (is_deleted=true) 在 SQL 中被过滤 → 返回 None → 403。"""
        # 模拟：即使 wp_id 存在但 is_deleted=true → fetchone returns None
        session = _mock_session_wp_not_in_project()

        with pytest.raises(HTTPException) as exc_info:
            asyncio.new_event_loop().run_until_complete(
                verify_wp_binding(_WP_ID, _PROJECT_ID, _SHEET_CODE, session)
            )

        assert exc_info.value.status_code == 403

    def test_binding_with_matching_uuid_strings(self):
        """UUID 以 string 传入时正常工作。"""
        session = _mock_session_binding_ok("D2-2")

        # 传 string 形式的 UUID
        asyncio.new_event_loop().run_until_complete(
            verify_wp_binding(str(_WP_ID), str(_PROJECT_ID), "D2-2", session)
        )

    def test_multiple_scenarios_sequential(self):
        """依次测试多个场景确保无状态泄露。"""
        # 1. 匹配通过
        session_ok = _mock_session_binding_ok("K1-12")
        asyncio.new_event_loop().run_until_complete(
            verify_wp_binding(_WP_ID, _PROJECT_ID, "K1-12", session_ok)
        )

        # 2. 不匹配 → 403
        session_fail = _mock_session_wp_code_mismatch("K1-12")
        with pytest.raises(HTTPException) as exc_info:
            asyncio.new_event_loop().run_until_complete(
                verify_wp_binding(_WP_ID, _PROJECT_ID, "D2-2", session_fail)
            )
        assert exc_info.value.status_code == 403
