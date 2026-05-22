"""Phase 4 PBT — RLS 隔离性 + YoY 边界 property-based tests.

PBT-P1: RLS 隔离性 — set_rls_context 设置的 project_id 与查询过滤一致
PBT-P2: YoY 计算边界 — _calc_yoy 单调性 + 除零安全 + 符号正确性
"""

from hypothesis import given, settings, assume
from hypothesis import strategies as st
from decimal import Decimal
from unittest.mock import AsyncMock, call
from uuid import uuid4

import pytest


# ═══════════════════════════════════════════════════════════════════════════════
# PBT-P1: RLS 隔离性
# ═══════════════════════════════════════════════════════════════════════════════

class TestRlsIsolationProperty:
    """RLS 隔离性 property: set_rls_context 总是将 project_id 转为字符串传入 SET LOCAL。"""

    @given(
        project_id=st.uuids(),
    )
    @settings(max_examples=200)
    async def test_set_rls_context_always_converts_to_string(self, project_id):
        """任意 UUID → SET LOCAL 参数始终是字符串形式。"""
        from app.core.database import set_rls_context

        mock_session = AsyncMock()
        await set_rls_context(mock_session, project_id)

        mock_session.execute.assert_called_once()
        call_args = mock_session.execute.call_args
        params = call_args[0][1]
        # 参数必须是字符串
        assert isinstance(params["pid"], str)
        # 字符串内容必须等于 str(project_id)
        assert params["pid"] == str(project_id)

    @given(
        project_id_str=st.text(min_size=1, max_size=100),
    )
    @settings(max_examples=100)
    async def test_set_rls_context_string_input_passthrough(self, project_id_str):
        """字符串输入 → 原样传入（不做额外转换）。"""
        from app.core.database import set_rls_context

        mock_session = AsyncMock()
        await set_rls_context(mock_session, project_id_str)

        call_args = mock_session.execute.call_args
        params = call_args[0][1]
        assert params["pid"] == project_id_str


# ═══════════════════════════════════════════════════════════════════════════════
# PBT-P2: YoY 计算边界
# ═══════════════════════════════════════════════════════════════════════════════

class TestYoYBoundaryProperty:
    """YoY 计算 property: _calc_yoy 满足数学不变量。"""

    @given(
        current=st.floats(min_value=-1e12, max_value=1e12, allow_nan=False, allow_infinity=False),
        previous=st.floats(min_value=-1e12, max_value=1e12, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=200, deadline=None)
    def test_yoy_division_by_zero_safe(self, current, previous):
        """previous=0 时永远返回 None（不抛异常）。"""
        from app.routers.reports import _calc_yoy

        if previous == 0.0:
            result = _calc_yoy(current, previous)
            assert result is None

    @given(
        current=st.floats(min_value=-1e12, max_value=1e12, allow_nan=False, allow_infinity=False),
        previous=st.floats(min_value=-1e12, max_value=1e12, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=200)
    def test_yoy_sign_correctness(self, current, previous):
        """YoY 符号正确性: current > previous → 非负, current < previous → 非正（量化容忍）。"""
        from app.routers.reports import _calc_yoy

        assume(previous != 0.0)
        assume(current != previous)  # 排除相等情况
        # 排除量化边界（差异太小被 round(2) 吃掉）
        assume(abs(current - previous) / abs(previous) > 0.005)  # > 0.5% 才有意义

        result = _calc_yoy(current, previous)
        assert result is not None

        if previous > 0:
            # 正 previous: current > previous → 正增长
            if current > previous:
                assert result >= 0
            elif current < previous:
                assert result <= 0

    @given(
        current=st.floats(min_value=0.01, max_value=1e12, allow_nan=False, allow_infinity=False),
        previous=st.floats(min_value=0.01, max_value=1e12, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=200)
    def test_yoy_monotonicity_positive_previous(self, current, previous):
        """正 previous 时，current 越大 → YoY 越大（单调性）。"""
        from app.routers.reports import _calc_yoy

        assume(previous > 0)

        result = _calc_yoy(current, previous)
        assert result is not None

        # current + delta 应产生更大的 YoY
        delta = abs(previous) * 0.1  # 10% 增量
        result_higher = _calc_yoy(current + delta, previous)
        assert result_higher is not None
        assert result_higher > result

    @given(
        value=st.floats(min_value=0.01, max_value=1e12, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100)
    def test_yoy_zero_change(self, value):
        """current == previous → YoY == 0。"""
        from app.routers.reports import _calc_yoy

        result = _calc_yoy(value, value)
        assert result == 0.0

    def test_yoy_none_inputs(self):
        """None 输入永远返回 None。"""
        from app.routers.reports import _calc_yoy

        assert _calc_yoy(None, 100.0) is None
        assert _calc_yoy(100.0, None) is None
        assert _calc_yoy(None, None) is None

    @pytest.mark.parametrize("current,previous,expected_sign", [
        (150.0, 100.0, 1),    # +50%
        (50.0, 100.0, -1),    # -50%
        (100.0, 100.0, 0),    # 0%
        (200.0, 100.0, 1),    # +100%
        (0.01, 100.0, -1),    # -99.99%
        (1000.0, 1.0, 1),     # +99900%
    ])
    def test_yoy_boundary_cases(self, current, previous, expected_sign):
        """显式边界用例。"""
        from app.routers.reports import _calc_yoy

        result = _calc_yoy(current, previous)
        assert result is not None
        if expected_sign > 0:
            assert result > 0
        elif expected_sign < 0:
            assert result < 0
        else:
            assert result == 0.0
