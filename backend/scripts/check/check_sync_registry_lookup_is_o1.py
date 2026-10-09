# -*- coding: utf-8 -*-
"""注册表查表 O(1) 性能基准（P7 / D1-P7 + 性能基线的可离线部分）。

spec: d1-sync-row-table-engine-and-d1-coverage · Task 4（性能基线，可离线部分）
Requirements 3.5 / 8.2

═══ 这条基准钉的是什么 ═══

需求 3.5：注册表查表必须 O(1) dict 命中，**不得**退化成 `for spec in REGISTRY: if spec.matches()`
线性试探（那是 `field_by_stable_key` O(n²) 的同款错误）。本基准以**规模递增**的合成注册表
测查表耗时：dict.get 的均摊耗时不随规模上升，而线性试探随规模线性上升。

判据（离线，纯 CPU，不连库、不依赖真栈）：
  1. 用 N ∈ {10, 100, 1000, 10000} 构造合成注册表；
  2. dict.get 查末位 key 的每次均摊耗时（多次取中位数）在各 N 间**基本平坦**
     （最大 N 的中位耗时 ≤ 最小 N 的中位耗时 × 上限因子）；
  3. 反证：同样规模下线性试探（for k in reg: if k==target）耗时**随 N 线性上升**。

🔴 三端点真实耗时（store-projection / pending-mutations / materialize）需真栈 + 真库，
   属外部依赖（D1 adapter 尚未注册，见 spec design §上游锚定）；那部分由
   `measure_sync_endpoints_timing.py`（真栈脚手架）承接，本脚本只覆盖 O(1) 查表这条可离线判据。

命中即 exit 1。自测：`backend/tests/scripts/test_check_sync_registry_lookup_is_o1.py`。
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover
        pass

_SIZES: tuple[int, ...] = (10, 100, 1000, 10000)
#: 取中位数用的样本数。每个样本内部跑 `_calibrate_reps()` 次查表，
#: 因此样本数不需要很大（中位数在 21 个样本上已经稳）。
_SAMPLES: int = 21
#: dict.get 在最大规模下的中位耗时 ≤ 最小规模 × 该因子（放宽到 8 以容忍 CPU 抖动，
#: 但线性试探会轻松超过它 —— 10000/10 = 1000 倍）。
_O1_TOLERANCE: float = 8.0

#: 单个计时样本的最短时长（纳秒）。
#:
#: 🔴 这个常量修的是一个会让本门**随机假红**的真缺陷：
#:    `time.perf_counter_ns()` 在 Windows 上的粒度约 100ns，而单次 dict `.get()`
#:    只要十几到几十 ns ⇒ `t1 - t0` 经常测出 **0**。原实现用
#:    `max(dict_medians[smallest], 1e-9)` 兜除零，于是比值变成
#:    `100 / 1e-9 = 1e11`，门以「dict 耗时比=100000000000.0」假红。
#:    （实测：连跑 5 次有 1 次红 4 次绿 —— 典型的计时分辨率抖动，不是性能回归。）
#:
#:    正解不是把容差调大（那会同时放过真回归），而是让**每个样本测一批查表**，
#:    把样本时长抬到远高于时钟粒度，再除以批量数还原单次耗时。
_MIN_SAMPLE_NS: int = 50_000


def _lookup_once(reg: dict[str, int], target: str, *, linear: bool) -> int | None:
    if linear:
        for k, v in reg.items():
            if k == target:
                return v
        return None
    return reg.get(target)


def _calibrate_reps(reg: dict[str, int], target: str, *, linear: bool) -> int:
    """倍增批量数，直到一个样本的时长 ≥ `_MIN_SAMPLE_NS`（timeit 的标准做法）。

    返回的批量数对 dict 会很大（查表极快），对大规模线性试探会很小（本身就慢）——
    两边最终都以「单次均摊耗时」入比值，量纲一致。
    """
    reps = 1
    while reps <= 1 << 22:
        t0 = time.perf_counter_ns()
        for _ in range(reps):
            _lookup_once(reg, target, linear=linear)
        elapsed = time.perf_counter_ns() - t0
        if elapsed >= _MIN_SAMPLE_NS:
            return reps
        reps *= 2
    return reps


def _median_lookup_ns(reg: dict[str, int], target: str, *, linear: bool) -> float:
    """单次查表的均摊耗时中位数（纳秒，可为小数）。"""
    reps = _calibrate_reps(reg, target, linear=linear)
    samples: list[float] = []
    for _ in range(_SAMPLES):
        t0 = time.perf_counter_ns()
        for _ in range(reps):
            found = _lookup_once(reg, target, linear=linear)
        elapsed = time.perf_counter_ns() - t0
        assert found is not None
        samples.append(elapsed / reps)
    return statistics.median(samples)


def run() -> dict[str, Any]:
    dict_medians: dict[int, float] = {}
    linear_medians: dict[int, float] = {}
    for n in _SIZES:
        reg = {f"adapter-{i}": i for i in range(n)}
        target = f"adapter-{n - 1}"  # 末位 key（线性试探的最坏情形）
        dict_medians[n] = _median_lookup_ns(reg, target, linear=False)
        linear_medians[n] = _median_lookup_ns(reg, target, linear=True)

    smallest, largest = _SIZES[0], _SIZES[-1]

    # 🔴 分辨率不足时**显式失败**，不再用 `max(x, 1e-9)` 兜除零。
    #    原实现那个兜底会把「测不出来」静默变成「比值 1e11」，读起来像性能爆炸 ——
    #    诊断信息把排查带向错误方向。批量校准之后基准时长必然远大于 0，
    #    真的还是 0 只能是计时器坏了，那时应该报计时问题而不是报性能不达标。
    baselines = {
        "dict": dict_medians[smallest],
        "linear": linear_medians[smallest],
    }
    unmeasurable = sorted(name for name, value in baselines.items() if value <= 0.0)
    if unmeasurable:
        return {
            "ok": False,
            "error": "timer_resolution",
            "unmeasurable_baselines": unmeasurable,
            "min_sample_ns": _MIN_SAMPLE_NS,
            "dict_median_ns": dict_medians,
            "linear_median_ns": linear_medians,
            "dict_ratio_max_over_min": None,
            "linear_ratio_max_over_min": None,
            "tolerance": _O1_TOLERANCE,
            "dict_is_flat": False,
            "linear_scales": False,
        }

    dict_ratio = dict_medians[largest] / dict_medians[smallest]
    linear_ratio = linear_medians[largest] / linear_medians[smallest]

    dict_is_flat = dict_ratio <= _O1_TOLERANCE
    linear_scales = linear_ratio > _O1_TOLERANCE  # 反证：线性确实随规模上升

    return {
        "ok": dict_is_flat and linear_scales,
        "error": None,
        "dict_median_ns": dict_medians,
        "linear_median_ns": linear_medians,
        "dict_ratio_max_over_min": round(dict_ratio, 2),
        "linear_ratio_max_over_min": round(linear_ratio, 2),
        "tolerance": _O1_TOLERANCE,
        "dict_is_flat": dict_is_flat,
        "linear_scales": linear_scales,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=str, default=None)
    args = parser.parse_args()

    report = run()
    if args.json:
        Path(args.json).write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    if report["ok"]:
        print(f"✅ 注册表查表 O(1)：dict 耗时比(max/min)={report['dict_ratio_max_over_min']} "
              f"≤ {report['tolerance']}；线性对照比={report['linear_ratio_max_over_min']}（随规模上升，反证成立）")
        return 0

    if report.get("error") == "timer_resolution":
        print("❌ 计时分辨率不足，本次测量无效（**不是**性能回归）：")
        print(f"   基准耗时测出 0 的项：{report['unmeasurable_baselines']}")
        print(f"   每样本目标时长 = {report['min_sample_ns']}ns，批量校准后仍测出 0 ⇒ 请检查计时器")
        return 1

    print("❌ 注册表查表性能判据未通过：")
    print(f"   dict 耗时比={report['dict_ratio_max_over_min']}（应 ≤ {report['tolerance']}，flat={report['dict_is_flat']}）")
    print(f"   线性对照比={report['linear_ratio_max_over_min']}（应 > {report['tolerance']} 以证明反证，scales={report['linear_scales']}）")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
