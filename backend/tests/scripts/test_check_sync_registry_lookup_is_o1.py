# -*- coding: utf-8 -*-
"""`check_sync_registry_lookup_is_o1.py` 基准自测（P7 / D1-P7）。

spec: d1-sync-row-table-engine-and-d1-coverage · Task 4（可离线部分）· Requirements 3.5 / 8.2

覆盖：
  1. dict.get 查表耗时比(max/min) ≤ 容忍因子（O(1) 平坦）。
  2. 线性试探耗时比 > 容忍因子（反证：线性确实随规模上升）。
  3. run() 整体 ok=True。
  4. **批量校准真的把基准抬离 0**（下面那条修复的实证，见 §）。
  5. **`timer_resolution` 分支的确定性覆盖**。

═══ § 2026-09-28 修掉的一个「随机假红」缺陷 ═══

原实现每个计时样本只测**一次**查表。`time.perf_counter_ns()` 在 Windows 上粒度
约 100ns，而单次 dict `.get()` 只要十几到几十 ns ⇒ `t1 - t0` 经常是 **0**。
原代码用 `max(dict_medians[smallest], 1e-9)` 兜除零，于是比值变成
`100 / 1e-9 = 1e11`，本门以「dict 耗时比=100000000000.0」假红
（实测连跑 5 次：1 红 4 绿）。

修法是让每个样本测**一批**查表（`_calibrate_reps` 倍增到样本时长 ≥ `_MIN_SAMPLE_NS`），
再除以批量数还原单次均摊耗时；并把除零兜底换成**显式** `timer_resolution` 失败
—— 「测不出来」和「性能不达标」是两件事，报错必须分开说。

修复后 dict 比值落在 0.98~1.12（真正的 O(1) 形状），线性对照 608~666；
变异证明：把 dict 分支换成线性扫描后本门 rc=1 / 比值 694（真能抓它该抓的缺陷）。
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(_BACKEND))

_CHECK_PATH = _BACKEND / "scripts" / "check" / "check_sync_registry_lookup_is_o1.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("_check_sync_registry_lookup_is_o1", _CHECK_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_dict_lookup_is_flat_and_linear_scales() -> None:
    report = _load_module().run()
    assert report["dict_is_flat"], f"dict 查表不平坦：比={report['dict_ratio_max_over_min']}"
    assert report["linear_scales"], f"线性对照未随规模上升（反证不成立）：比={report['linear_ratio_max_over_min']}"
    assert report["ok"]


def test_batch_calibration_lifts_baseline_above_zero() -> None:
    """批量校准必须把最小规模的基准耗时抬离 0 —— 这是「比值有意义」的前提。

    🔴 这条是上面 § 那个缺陷的**正面判据**：基准为 0 时任何比值都是垃圾，
    原实现正是在这种情况下吐出 1e11。断言基准 > 0 才算「测到了东西」。
    """
    mod = _load_module()
    report = mod.run()
    smallest = mod._SIZES[0]
    assert report["dict_median_ns"][smallest] > 0.0, (
        "最小规模的 dict 基准耗时测出 0 —— 批量校准失效，比值不可信"
    )
    assert report["linear_median_ns"][smallest] > 0.0
    # 单次 dict 查表是亚微秒量级；若基准大到微秒级说明测的不是单次均摊耗时。
    assert report["dict_median_ns"][smallest] < 1000.0


def test_calibration_reaches_min_sample_duration() -> None:
    """`_calibrate_reps` 返回的批量数必须真的让样本时长达到目标下限。"""
    mod = _load_module()
    reg = {f"adapter-{i}": i for i in range(mod._SIZES[0])}
    target = f"adapter-{mod._SIZES[0] - 1}"
    reps = mod._calibrate_reps(reg, target, linear=False)
    assert reps > 1, (
        f"单次 dict 查表居然一次就跑够 {mod._MIN_SAMPLE_NS}ns（reps={reps}）—— "
        "要么 _MIN_SAMPLE_NS 被改小了，要么校准逻辑没生效"
    )
    import time

    t0 = time.perf_counter_ns()
    for _ in range(reps):
        mod._lookup_once(reg, target, linear=False)
    assert time.perf_counter_ns() - t0 >= mod._MIN_SAMPLE_NS * 0.5


def test_timer_resolution_branch_is_reported_as_measurement_failure(monkeypatch) -> None:
    """确定性覆盖 `timer_resolution` 分支：基准为 0 时必须报**测量失败**而非性能不达标。

    🔴 为什么要 monkeypatch 而不是「把 `_MIN_SAMPLE_NS` 调成 0 跑一次」：
    基准是否恰好测出 0 本身就是随机的（这正是原缺陷的性质），那样跑出来的绿
    不能证明分支正确。这里直接把测量函数钉成返回 0，让分支必然进入。
    """
    mod = _load_module()
    monkeypatch.setattr(mod, "_median_lookup_ns", lambda *a, **k: 0.0)
    report = mod.run()
    assert report["ok"] is False
    assert report["error"] == "timer_resolution"
    assert report["unmeasurable_baselines"] == ["dict", "linear"]
    # 🔴 关键：不得再吐出那个假性能比值（原实现会给 1e11）。
    assert report["dict_ratio_max_over_min"] is None
    assert report["linear_ratio_max_over_min"] is None


def test_healthy_run_does_not_claim_timer_resolution_error() -> None:
    """失效条目反向检查：正常一轮必须 `error is None`，否则上一条在裸奔。"""
    report = _load_module().run()
    assert report["error"] is None
