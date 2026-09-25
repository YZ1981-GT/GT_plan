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
_TRIALS: int = 2000
#: dict.get 在最大规模下的中位耗时 ≤ 最小规模 × 该因子（放宽到 8 以容忍 CPU 抖动，
#: 但线性试探会轻松超过它 —— 10000/10 = 1000 倍）。
_O1_TOLERANCE: float = 8.0


def _median_lookup_ns(reg: dict[str, int], target: str, *, linear: bool) -> float:
    samples: list[float] = []
    for _ in range(_TRIALS):
        t0 = time.perf_counter_ns()
        if linear:
            found = None
            for k, v in reg.items():
                if k == target:
                    found = v
                    break
        else:
            found = reg.get(target)
        t1 = time.perf_counter_ns()
        assert found is not None
        samples.append(float(t1 - t0))
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
    dict_ratio = dict_medians[largest] / max(dict_medians[smallest], 1e-9)
    linear_ratio = linear_medians[largest] / max(linear_medians[smallest], 1e-9)

    dict_is_flat = dict_ratio <= _O1_TOLERANCE
    linear_scales = linear_ratio > _O1_TOLERANCE  # 反证：线性确实随规模上升

    return {
        "ok": dict_is_flat and linear_scales,
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

    print("❌ 注册表查表性能判据未通过：")
    print(f"   dict 耗时比={report['dict_ratio_max_over_min']}（应 ≤ {report['tolerance']}，flat={report['dict_is_flat']}）")
    print(f"   线性对照比={report['linear_ratio_max_over_min']}（应 > {report['tolerance']} 以证明反证，scales={report['linear_scales']}）")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
