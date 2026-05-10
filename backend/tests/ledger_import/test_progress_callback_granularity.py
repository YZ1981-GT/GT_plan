"""F13 / Sprint 11.3: pipeline progress callback 节流粒度单元测试

覆盖 ProgressState + _maybe_report_progress 的行为契约（对齐 requirements F13）：

1. 大文档导入（50k 行 / 5 chunks 递增）至少触发 ≥ 5 次进度回调
   （按 5% 或 10k 行间隔，先达到者触发）
2. 百分比严格递增，不会倒退
3. cb=None 时不抛异常
4. total=0 时不触发回调（避免除零）
5. 连续 rows 不变时不会重复触发（防抖语义）
6. 跨 10k 行阈值触发（百分比 delta <5% 场景）
"""
from __future__ import annotations

import pytest

from app.services.ledger_import.pipeline import (
    ProgressState,
    _maybe_report_progress,
)


class _Recorder:
    """收集 progress callback 调用历史。"""

    def __init__(self) -> None:
        self.calls: list[tuple[int, str]] = []

    async def __call__(self, pct: int, msg: str) -> None:
        self.calls.append((pct, msg))


def _msg(pct: int) -> str:
    return f"pct={pct}"


# ---------------------------------------------------------------------------
# Case 1: 50k 行分 5 个 10k chunk 递增 → 至少 5 次回调
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_50k_rows_triggers_at_least_five_callbacks():
    state = ProgressState(total_rows_est=50_000)
    rec = _Recorder()

    for target in (10_000, 20_000, 30_000, 40_000, 50_000):
        state.rows_processed = target
        await _maybe_report_progress(state, rec, _msg)

    assert len(rec.calls) >= 5, (
        f"50k 行 5 chunk 递增应触发 ≥5 次进度回调，实际 {len(rec.calls)}"
    )
    # 百分比严格递增
    pcts = [c[0] for c in rec.calls]
    assert pcts == sorted(pcts), f"百分比应单调递增，实际 {pcts}"
    # 最后一次到 100%
    assert pcts[-1] == 100


# ---------------------------------------------------------------------------
# Case 2: 连续小步进（每次 +500 行）累积到 10k 触发一次
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_small_steps_aggregate_to_10k_threshold():
    state = ProgressState(total_rows_est=100_000)
    rec = _Recorder()

    # 连续每次 +500 行推进到 9_500 — 仍小于 10k 阈值，也小于 5% 阈值（5000 行）
    for i in range(1, 20):
        state.rows_processed = i * 500
        await _maybe_report_progress(state, rec, _msg)

    # 5_000 行达到 5% 时应首次触发；再过 5_000 行（10_000 总）到 10% 再触发
    # 第一次触发在 rows_processed=5_000（首次到 5% 阈值）
    assert len(rec.calls) >= 1
    assert all(c[0] >= 0 for c in rec.calls)


# ---------------------------------------------------------------------------
# Case 3: cb=None / total=0 不抛异常
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_none_callback_is_noop():
    state = ProgressState(total_rows_est=10_000)
    state.rows_processed = 5_000
    await _maybe_report_progress(state, None, _msg)  # 不应抛


@pytest.mark.asyncio
async def test_zero_total_does_not_trigger():
    state = ProgressState(total_rows_est=0)
    state.rows_processed = 100
    rec = _Recorder()
    await _maybe_report_progress(state, rec, _msg)
    assert len(rec.calls) == 0, "total=0 时不应触发（避免除零 / 无意义 pct）"


# ---------------------------------------------------------------------------
# Case 4: 同一进度重复调用不重复触发
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_repeat_same_progress_no_duplicate_callback():
    state = ProgressState(total_rows_est=100_000)
    rec = _Recorder()

    state.rows_processed = 20_000  # 20%
    await _maybe_report_progress(state, rec, _msg)
    baseline = len(rec.calls)

    # 立即再次调用，rows_processed 不变
    await _maybe_report_progress(state, rec, _msg)
    await _maybe_report_progress(state, rec, _msg)

    assert len(rec.calls) == baseline, (
        "同一 rows_processed 重复调用不应触发新的回调"
    )


# ---------------------------------------------------------------------------
# Case 5: 10k 行阈值触发（跨大文档场景 pct delta < 5%）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_10k_row_threshold_fires_even_when_pct_delta_small():
    # 2M 行文档，每 10k 行 = 0.5% pct delta（远小于 5%）
    state = ProgressState(total_rows_est=2_000_000)
    rec = _Recorder()

    # 先到 100_000 行（5%）→ 首次触发
    state.rows_processed = 100_000
    await _maybe_report_progress(state, rec, _msg)
    first_count = len(rec.calls)
    assert first_count >= 1

    # 再加 10_000 行 → 0.5% pct delta，按 10k 行阈值应该仍触发
    state.rows_processed = 110_000
    await _maybe_report_progress(state, rec, _msg)
    assert len(rec.calls) == first_count + 1, (
        "rows_delta >= 10k 时应触发一次（即使 pct_delta < 5%）"
    )


# ---------------------------------------------------------------------------
# Case 6: last_pct_reported 跟踪正确（百分比回调准确）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_last_pct_tracking():
    state = ProgressState(total_rows_est=100_000)
    rec = _Recorder()

    state.rows_processed = 5_000  # 5%
    await _maybe_report_progress(state, rec, _msg)
    assert state.last_pct_reported == 5
    assert state.last_rows_reported == 5_000

    state.rows_processed = 10_500  # 10%（+5% delta，触发）
    await _maybe_report_progress(state, rec, _msg)
    # pct 上报 10（int min 保护）
    assert state.last_pct_reported == 10


# ---------------------------------------------------------------------------
# Case 7: rows_processed > total 时 pct 不超过 100
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_overflow_rows_capped_at_100_pct():
    state = ProgressState(total_rows_est=10_000)
    rec = _Recorder()

    state.rows_processed = 15_000  # 超出 total → 按 min(150, 100) = 100
    await _maybe_report_progress(state, rec, _msg)

    assert len(rec.calls) >= 1
    assert all(c[0] <= 100 for c in rec.calls)
