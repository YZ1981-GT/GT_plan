"""pipeline `_perf` 字典 → `StagedProfiler` 报告的 adapter（C4 骨架伴生模块）。

从 `pipeline.py` 拆出，避免 pipeline 单文件再膨胀。接口保持不变：

- ``_PHASE_ROWS_SOURCE``：phase 名 → rows 来源键。
- ``_build_profiler_report(perf, perf_start_ts, *, staging_rows, rebuild_rows)``：
  不发任何新调用，只把 pipeline 已经测好的每 phase 结束时点平移成 profiler report。

pipeline.py 顶部 `re-export`，调用方（含既有测试）可继续用
``from app.services.ledger_import.pipeline import _build_profiler_report``。
"""

from __future__ import annotations

from typing import Any


__all__ = [
    "_PHASE_ROWS_SOURCE",
    "_build_profiler_report",
]


# phase → 是否带 rows 的信源；True 时由调用方从 pipeline 局部变量传入
_PHASE_ROWS_SOURCE: dict[str, str] = {
    # staging_write = parse_write_streaming 的 rows（_perf 名字来自 _mark）
    "parse_write_streaming_done": "staging_rows",
    # rebuild_aux_summary 的 rows = balance + aux_balance（汇总行数）
    "rebuild_aux_summary_done": "rebuild_rows",
}


def _build_profiler_report(
    perf: dict[str, float],
    perf_start_ts: float,
    *,
    staging_rows: int = 0,
    rebuild_rows: int = 0,
) -> dict[str, Any] | None:
    """把 pipeline 的 ``_perf`` 字典翻译成 ``StagedProfiler`` 报告结构。

    pipeline 原有 ``_mark()`` 已经把每个阶段结束时点写进 ``_perf``；本函数
    不发任何新调用、不改任何业务路径，只做一次 dict → dict 的平移。``_perf``
    为空时返回 None（调用方 pipeline_result.profiler_report 保持 None）。
    """
    from app.services.ledger_import.profiler import StagedProfiler

    if not perf:
        return None
    profiler = StagedProfiler()
    rows_map = {
        "staging_rows": max(0, int(staging_rows)),
        "rebuild_rows": max(0, int(rebuild_rows)),
    }
    phase_items = list(perf.items())
    # _mark("start") 没有「上一个时点」，用 pipeline 起点 perf_start_ts。
    prev_t = perf_start_ts
    for name, t in phase_items:
        duration = max(0.0, t - prev_t)
        rows_key = _PHASE_ROWS_SOURCE.get(name)
        rows = rows_map.get(rows_key, 0) if rows_key else 0
        profiler.record_stage_manual(name, duration_s=duration, rows=rows)
        prev_t = t
    return profiler.to_dict()
