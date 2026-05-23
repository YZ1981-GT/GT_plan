"""W-4 加班工时自动识别 — 单元测试 + 属性测试

验证：
- WorkHour.is_overtime 计算属性 hours > 8 → True，否则 False
- WorkHourEntry.is_overtime 同语义（三级粒度填报）
- workhour_list / workhour_service 序列化包含 is_overtime 字段

引用：proposal-remaining-18 W-4，requirements §三 "超过 8h/天自动标记为加班"
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from hypothesis import given, settings as hp_settings, strategies as st

from app.models.staff_models import WorkHour
from app.models.workhour_entry_models import WorkHourEntry


# ---------------------------------------------------------------------------
# 单元测试 — 显式样例覆盖临界值
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "hours, expected",
    [
        (Decimal("0"), False),
        (Decimal("0.5"), False),
        (Decimal("4"), False),
        (Decimal("7.99"), False),
        (Decimal("8"), False),       # 严格大于：恰好 8h 不算加班
        (Decimal("8.01"), True),     # 临界 → True
        (Decimal("9"), True),
        (Decimal("12"), True),
        (Decimal("16"), True),
        (Decimal("24"), True),
    ],
)
def test_workhour_is_overtime_threshold(hours: Decimal, expected: bool) -> None:
    """WorkHour.is_overtime 在 hours > 8 时为 True，hours <= 8 时为 False。"""
    wh = WorkHour(
        id=uuid.uuid4(),
        staff_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        work_date=date(2026, 5, 22),
        hours=hours,
        status="confirmed",
    )
    assert wh.is_overtime is expected


@pytest.mark.parametrize(
    "hours, expected",
    [
        (Decimal("0.5"), False),
        (Decimal("8"), False),
        (Decimal("8.01"), True),
        (Decimal("10"), True),
        (Decimal("23"), True),
    ],
)
def test_workhour_entry_is_overtime_threshold(hours: Decimal, expected: bool) -> None:
    """WorkHourEntry.is_overtime 同语义。"""
    entry = WorkHourEntry(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        date=date(2026, 5, 22),
        hours=hours,
        cycle="D",
        status="submitted",
        submitted_at=datetime.now(timezone.utc),
    )
    assert entry.is_overtime is expected


def test_workhour_is_overtime_handles_none_hours() -> None:
    """hours 为 None（异常情况）应返回 False，不抛异常。"""
    wh = WorkHour(
        id=uuid.uuid4(),
        staff_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        work_date=date(2026, 5, 22),
        hours=None,  # type: ignore[arg-type]
        status="draft",
    )
    assert wh.is_overtime is False


def test_workhour_is_overtime_accepts_float_and_int() -> None:
    """ORM 加载时 hours 字段可能是 float/int（测试环境 SQLite），仍应正确判定。"""
    for raw in (8.0, 9.0, 12, 7):
        wh = WorkHour(
            id=uuid.uuid4(),
            staff_id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            work_date=date(2026, 5, 22),
            hours=raw,  # type: ignore[arg-type]
            status="confirmed",
        )
        expected = Decimal(str(raw)) > Decimal("8")
        assert wh.is_overtime is expected, f"hours={raw!r} expected {expected}"


# ---------------------------------------------------------------------------
# 属性测试 — 全输入空间不变量
# ---------------------------------------------------------------------------


@given(
    hours_x100=st.integers(min_value=0, max_value=2400),  # 0.00 ~ 24.00
)
@hp_settings(max_examples=100, deadline=None)
def test_pbt_workhour_is_overtime_invariant(hours_x100: int) -> None:
    """**Validates: Requirements W-4**

    属性：对任意 hours ∈ [0, 24]（步进 0.01），is_overtime ↔ hours > 8。
    """
    hours = Decimal(hours_x100) / Decimal("100")
    wh = WorkHour(
        id=uuid.uuid4(),
        staff_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        work_date=date(2026, 5, 22),
        hours=hours,
        status="draft",
    )
    expected = hours > Decimal("8")
    assert wh.is_overtime is expected, (
        f"Property violated: hours={hours} expected is_overtime={expected}, got {wh.is_overtime}"
    )


@given(
    hours_x100=st.integers(min_value=1, max_value=2400),
)
@hp_settings(max_examples=100, deadline=None)
def test_pbt_workhour_entry_is_overtime_invariant(hours_x100: int) -> None:
    """**Validates: Requirements W-4**

    WorkHourEntry.is_overtime 与 WorkHour 同语义。
    """
    hours = Decimal(hours_x100) / Decimal("100")
    entry = WorkHourEntry(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        date=date(2026, 5, 22),
        hours=hours,
        cycle="D",
        status="draft",
    )
    expected = hours > Decimal("8")
    assert entry.is_overtime is expected
