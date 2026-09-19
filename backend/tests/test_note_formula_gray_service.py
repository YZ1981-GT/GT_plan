"""Property 12 + 13: 公式灰度按项目 + 就绪度暴露 PBT。

**Validates: Requirements 5.1, 5.2, 5.3, 5.4, 6.1, 7.5**

Property 12 (公式灰度按项目 + 关闭态零改动 + fail-open):
  - `is_note_formula_enabled` 在全局 False + 无项目 override 时返 False（逐字节等价当前）
  - 项目 override=True 时该项目返 True
  - 异常 fail-open 返 False

Property 13 (就绪度暴露公式状态):
  - `build_readiness().summary` 含 `formula_enabled`，与 `is_note_formula_enabled` 判定一致
"""
from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import given, settings as h_settings
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SETTINGS_PATCH_TARGET = "app.core.config.settings"


def _make_mock_db(wizard_state: dict | None = None, row_exists: bool = True):
    """Create a mock async session that returns the given wizard_state."""
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


# ---------------------------------------------------------------------------
# Property 12: 公式灰度按项目 + 关闭态零改动 + fail-open
# ---------------------------------------------------------------------------


class TestProperty12GrayServicePerProject:
    """Property 12: is_note_formula_enabled 按项目 + 关闭态零改动 + fail-open。

    **Validates: Requirements 5.1, 5.3, 5.4, 6.1**
    """

    @pytest.mark.asyncio
    async def test_global_false_no_override_returns_false(self):
        """全局 False + 无项目 override → False（逐字节等价当前）。"""
        from app.services.note_formula_gray_service import is_note_formula_enabled

        db = _make_mock_db(wizard_state={})
        pid = uuid.uuid4()

        with patch(_SETTINGS_PATCH_TARGET) as mock_s:
            mock_s.DISCLOSURE_NOTE_FORMULA_ENABLED = False
            result = await is_note_formula_enabled(db, pid)

        assert result is False

    @pytest.mark.asyncio
    async def test_global_false_override_true_returns_true(self):
        """全局 False + 项目 override=True → 该项目返 True。"""
        from app.services.note_formula_gray_service import is_note_formula_enabled

        db = _make_mock_db(wizard_state={"disclosure_note_formula_enabled": True})
        pid = uuid.uuid4()

        with patch(_SETTINGS_PATCH_TARGET) as mock_s:
            mock_s.DISCLOSURE_NOTE_FORMULA_ENABLED = False
            result = await is_note_formula_enabled(db, pid)

        assert result is True

    @pytest.mark.asyncio
    async def test_global_false_override_false_returns_false(self):
        """全局 False + 项目 override=False → False。"""
        from app.services.note_formula_gray_service import is_note_formula_enabled

        db = _make_mock_db(wizard_state={"disclosure_note_formula_enabled": False})
        pid = uuid.uuid4()

        with patch(_SETTINGS_PATCH_TARGET) as mock_s:
            mock_s.DISCLOSURE_NOTE_FORMULA_ENABLED = False
            result = await is_note_formula_enabled(db, pid)

        assert result is False

    @pytest.mark.asyncio
    async def test_global_true_returns_true_regardless_of_override(self):
        """全局 True → True（向后兼容全开，不查项目级）。"""
        from app.services.note_formula_gray_service import is_note_formula_enabled

        db = _make_mock_db(wizard_state={})
        pid = uuid.uuid4()

        with patch(_SETTINGS_PATCH_TARGET) as mock_s:
            mock_s.DISCLOSURE_NOTE_FORMULA_ENABLED = True
            result = await is_note_formula_enabled(db, pid)

        assert result is True
        # Should not query DB when global is True
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_project_not_found_returns_false(self):
        """项目不存在（row=None）→ False。"""
        from app.services.note_formula_gray_service import is_note_formula_enabled

        db = _make_mock_db(row_exists=False)
        pid = uuid.uuid4()

        with patch(_SETTINGS_PATCH_TARGET) as mock_s:
            mock_s.DISCLOSURE_NOTE_FORMULA_ENABLED = False
            result = await is_note_formula_enabled(db, pid)

        assert result is False

    @pytest.mark.asyncio
    async def test_wizard_state_not_dict_returns_false(self):
        """wizard_state 非 dict（如 None）→ False。"""
        from app.services.note_formula_gray_service import is_note_formula_enabled

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.first.return_value = (None,)  # wizard_state is None
        db.execute.return_value = mock_result
        pid = uuid.uuid4()

        with patch(_SETTINGS_PATCH_TARGET) as mock_s:
            mock_s.DISCLOSURE_NOTE_FORMULA_ENABLED = False
            result = await is_note_formula_enabled(db, pid)

        assert result is False

    @pytest.mark.asyncio
    async def test_exception_fail_open_returns_false(self):
        """异常 fail-open → False（绝不误开）。"""
        from app.services.note_formula_gray_service import is_note_formula_enabled

        db = AsyncMock()
        db.execute.side_effect = RuntimeError("DB connection lost")
        pid = uuid.uuid4()

        result = await is_note_formula_enabled(db, pid)

        assert result is False

    @h_settings(max_examples=5)
    @given(
        global_on=st.booleans(),
        override_val=st.one_of(st.none(), st.booleans()),
        project_exists=st.booleans(),
    )
    @pytest.mark.asyncio
    async def test_pbt_never_accidentally_enables(
        self, global_on: bool, override_val: bool | None, project_exists: bool
    ):
        """PBT: 非全局 True 且非项目 override=True 时，绝不返 True。

        **Validates: Requirements 5.3, 5.4**
        """
        from app.services.note_formula_gray_service import is_note_formula_enabled

        ws: dict[str, Any] = {}
        if override_val is not None:
            ws["disclosure_note_formula_enabled"] = override_val

        db = _make_mock_db(wizard_state=ws, row_exists=project_exists)
        pid = uuid.uuid4()

        with patch(_SETTINGS_PATCH_TARGET) as mock_s:
            mock_s.DISCLOSURE_NOTE_FORMULA_ENABLED = global_on
            result = await is_note_formula_enabled(db, pid)

        # If global off and (project doesn't exist or override is not True),
        # result MUST be False
        if not global_on and (not project_exists or override_val is not True):
            assert result is False


# ---------------------------------------------------------------------------
# Property 13: 就绪度暴露公式状态
# ---------------------------------------------------------------------------


class TestProperty13ReadinessFormulaStatus:
    """Property 13: build_readiness().summary 含 formula_enabled，与 is_note_formula_enabled 一致。

    **Validates: Requirements 5.2**
    """

    @pytest.mark.asyncio
    async def test_summary_contains_formula_enabled_false(self):
        """公式未启用时 summary.formula_enabled = False。"""
        from app.services.note_readiness_service import build_readiness

        db = AsyncMock()
        pid = uuid.uuid4()

        # Mock DB calls:
        # 1. notes query (empty scalars)
        mock_notes_result = MagicMock()
        mock_notes_result.scalars.return_value.all.return_value = []

        # 2. validation findings query (sa.text)
        mock_findings_result = MagicMock()
        mock_findings_result.fetchone.return_value = None

        # 3. formula gray check (sa.select Project.wizard_state)
        mock_formula_result = MagicMock()
        mock_formula_result.first.return_value = None

        call_count = [0]

        async def _execute_side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return mock_notes_result
            elif call_count[0] == 2:
                return mock_findings_result
            else:
                return mock_formula_result

        db.execute.side_effect = _execute_side_effect

        with patch(_SETTINGS_PATCH_TARGET) as mock_s:
            mock_s.DISCLOSURE_NOTE_FORMULA_ENABLED = False
            result = await build_readiness(db, pid, 2025)

        assert "summary" in result
        assert "formula_enabled" in result["summary"]
        assert result["summary"]["formula_enabled"] is False

    @pytest.mark.asyncio
    async def test_summary_contains_formula_enabled_true_when_global_on(self):
        """公式全局启用时 summary.formula_enabled = True。"""
        from app.services.note_readiness_service import build_readiness

        db = AsyncMock()
        pid = uuid.uuid4()

        # Mock notes empty + validation empty
        mock_notes_result = MagicMock()
        mock_notes_result.scalars.return_value.all.return_value = []
        mock_findings_result = MagicMock()
        mock_findings_result.fetchone.return_value = None

        call_count = [0]

        async def _execute_side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return mock_notes_result
            else:
                return mock_findings_result

        db.execute.side_effect = _execute_side_effect

        with patch(_SETTINGS_PATCH_TARGET) as mock_s:
            mock_s.DISCLOSURE_NOTE_FORMULA_ENABLED = True
            result = await build_readiness(db, pid, 2025)

        assert result["summary"]["formula_enabled"] is True

    @pytest.mark.asyncio
    async def test_formula_enabled_fail_open_returns_false_in_readiness(self):
        """is_note_formula_enabled 异常时 summary.formula_enabled = False（fail-open）。"""
        from app.services.note_readiness_service import build_readiness

        db = AsyncMock()
        pid = uuid.uuid4()

        # Mock notes OK, validation OK, formula check will fail
        mock_notes_result = MagicMock()
        mock_notes_result.scalars.return_value.all.return_value = []
        mock_findings_result = MagicMock()
        mock_findings_result.fetchone.return_value = None

        call_count = [0]

        async def _execute_side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return mock_notes_result
            elif call_count[0] == 2:
                return mock_findings_result
            else:
                raise RuntimeError("simulated failure")

        db.execute.side_effect = _execute_side_effect

        result = await build_readiness(db, pid, 2025)
        assert result["summary"]["formula_enabled"] is False

    @h_settings(max_examples=5)
    @given(global_on=st.booleans())
    @pytest.mark.asyncio
    async def test_pbt_readiness_formula_consistent_with_service(self, global_on: bool):
        """PBT: readiness.formula_enabled 与 is_note_formula_enabled 判定一致。

        **Validates: Requirements 5.2**
        """
        from app.services.note_formula_gray_service import is_note_formula_enabled
        from app.services.note_readiness_service import build_readiness

        pid = uuid.uuid4()

        # Build two mocks that behave identically for the formula path
        db_readiness = AsyncMock()
        db_direct = AsyncMock()

        mock_notes_result = MagicMock()
        mock_notes_result.scalars.return_value.all.return_value = []
        mock_findings_result = MagicMock()
        mock_findings_result.fetchone.return_value = None
        mock_formula_result = MagicMock()
        mock_formula_result.first.return_value = None

        call_count_r = [0]

        async def _execute_readiness(*args, **kwargs):
            call_count_r[0] += 1
            if call_count_r[0] == 1:
                return mock_notes_result
            elif call_count_r[0] == 2:
                return mock_findings_result
            else:
                return mock_formula_result

        db_readiness.execute.side_effect = _execute_readiness

        mock_formula_result_2 = MagicMock()
        mock_formula_result_2.first.return_value = None
        db_direct.execute.return_value = mock_formula_result_2

        with patch(_SETTINGS_PATCH_TARGET) as mock_s:
            mock_s.DISCLOSURE_NOTE_FORMULA_ENABLED = global_on
            readiness = await build_readiness(db_readiness, pid, 2025)
            direct = await is_note_formula_enabled(db_direct, pid)

        assert readiness["summary"]["formula_enabled"] == direct
