"""合并附注 V2 灰度按项目服务 属性测试（consol-disclosure-note-persistence Req5）。

镜像 test_note_formula_gray_service Property 12：
  - `is_consol_note_v2_enabled` 全局 False + 无项目 opt-in → False（逐字节等价当前，零回归）
  - 全局 True → True（向后兼容全开，不查项目级）
  - 项目 opt-in=True → 该项目 True
  - 项目不存在 / wizard_state 非 dict / 异常 → fail-open False（绝不误开）

Validates: Requirements 5.1, 5.3, 5.4, 6.1
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import given, settings as h_settings
from hypothesis import strategies as st

_SETTINGS_PATCH_TARGET = "app.core.config.settings"


def _make_mock_db(wizard_state: dict | None = None, row_exists: bool = True):
    """构造返回指定 wizard_state 的 mock async session。"""
    mock_db = AsyncMock()
    mock_result = MagicMock()
    if row_exists and wizard_state is not None:
        mock_result.first.return_value = (wizard_state,)
    elif row_exists:
        mock_result.first.return_value = (None,)
    else:
        mock_result.first.return_value = None
    mock_db.execute.return_value = mock_result
    return mock_db


class TestConsolNoteGrayPerProject:
    """is_consol_note_v2_enabled 按项目 + 关闭态零改动 + fail-open。"""

    @pytest.mark.asyncio
    async def test_global_false_no_optin_returns_false(self):
        """全局 False + 无项目 opt-in → False（零回归）。"""
        from app.services.consol_note_gray_service import is_consol_note_v2_enabled

        db = _make_mock_db(wizard_state={})
        with patch(_SETTINGS_PATCH_TARGET) as mock_s:
            mock_s.CONSOL_NOTES_V2_ENABLED = False
            result = await is_consol_note_v2_enabled(db, uuid.uuid4())
        assert result is False

    @pytest.mark.asyncio
    async def test_global_false_optin_true_returns_true(self):
        """全局 False + 项目 opt-in=True → 该项目 True。"""
        from app.services.consol_note_gray_service import is_consol_note_v2_enabled

        db = _make_mock_db(wizard_state={"consol_notes_v2_enabled": True})
        with patch(_SETTINGS_PATCH_TARGET) as mock_s:
            mock_s.CONSOL_NOTES_V2_ENABLED = False
            result = await is_consol_note_v2_enabled(db, uuid.uuid4())
        assert result is True

    @pytest.mark.asyncio
    async def test_global_false_optin_false_returns_false(self):
        """全局 False + 项目 opt-in=False → False。"""
        from app.services.consol_note_gray_service import is_consol_note_v2_enabled

        db = _make_mock_db(wizard_state={"consol_notes_v2_enabled": False})
        with patch(_SETTINGS_PATCH_TARGET) as mock_s:
            mock_s.CONSOL_NOTES_V2_ENABLED = False
            result = await is_consol_note_v2_enabled(db, uuid.uuid4())
        assert result is False

    @pytest.mark.asyncio
    async def test_global_true_returns_true_regardless_of_optin(self):
        """全局 True → True（向后兼容全开，不查项目级）。"""
        from app.services.consol_note_gray_service import is_consol_note_v2_enabled

        db = _make_mock_db(wizard_state={})
        with patch(_SETTINGS_PATCH_TARGET) as mock_s:
            mock_s.CONSOL_NOTES_V2_ENABLED = True
            result = await is_consol_note_v2_enabled(db, uuid.uuid4())
        assert result is True

    @pytest.mark.asyncio
    async def test_project_not_found_returns_false(self):
        """项目不存在（row=None）→ False。"""
        from app.services.consol_note_gray_service import is_consol_note_v2_enabled

        db = _make_mock_db(row_exists=False)
        with patch(_SETTINGS_PATCH_TARGET) as mock_s:
            mock_s.CONSOL_NOTES_V2_ENABLED = False
            result = await is_consol_note_v2_enabled(db, uuid.uuid4())
        assert result is False

    @pytest.mark.asyncio
    async def test_wizard_state_not_dict_returns_false(self):
        """wizard_state 非 dict（如 None）→ False。"""
        from app.services.consol_note_gray_service import is_consol_note_v2_enabled

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.first.return_value = (None,)  # wizard_state = None
        db.execute.return_value = mock_result
        with patch(_SETTINGS_PATCH_TARGET) as mock_s:
            mock_s.CONSOL_NOTES_V2_ENABLED = False
            result = await is_consol_note_v2_enabled(db, uuid.uuid4())
        assert result is False

    @pytest.mark.asyncio
    async def test_exception_fail_open_returns_false(self):
        """异常 fail-open → False（绝不误开）。"""
        from app.services.consol_note_gray_service import is_consol_note_v2_enabled

        db = AsyncMock()
        db.execute.side_effect = RuntimeError("boom")
        with patch(_SETTINGS_PATCH_TARGET) as mock_s:
            mock_s.CONSOL_NOTES_V2_ENABLED = False
            result = await is_consol_note_v2_enabled(db, uuid.uuid4())
        assert result is False

    @given(global_on=st.booleans(), optin=st.booleans())
    @h_settings(max_examples=5, deadline=None)
    @pytest.mark.asyncio
    async def test_pbt_effective_equals_global_or_optin(self, global_on: bool, optin: bool):
        """PBT：生效值 == 全局 OR 项目 opt-in。"""
        from app.services.consol_note_gray_service import is_consol_note_v2_enabled

        db = _make_mock_db(wizard_state={"consol_notes_v2_enabled": optin})
        with patch(_SETTINGS_PATCH_TARGET) as mock_s:
            mock_s.CONSOL_NOTES_V2_ENABLED = global_on
            result = await is_consol_note_v2_enabled(db, uuid.uuid4())
        assert result is (global_on or optin)
