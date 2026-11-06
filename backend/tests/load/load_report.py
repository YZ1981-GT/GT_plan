"""E5/E6 容量 Markdown 报告（只呈现真实证据，不留手填占位）。"""
from __future__ import annotations

import math
from typing import Any

from tests.load.load_contract import (
    ALL_SCENARIO_ERROR_RATE_PCT,
    CORE_ERROR_RATE_PCT,
    CORE_READ_P95_MS,
    CORE_READ_P99_MS,
    ESTIMATED_TOTAL_SECONDS,
    LOAD_STAGES,
    SAFETY_ZERO_KEYS,
    STEADY_SETTLE_SECONDS,
)
from tests.load.load_evaluation import evaluate_results


def _pass(value: bool) -> str:
    return "✅ PASS" if value else "❌ FAIL"


def _finite(value: Any, digits: int = 3) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "无证据"
    return f"{number:.{digits}f}" if math.isfinite(number) else "无证据"


def generate_final_report(stats: dict[str, Any], args: Any) -> str:
    evaluation = evaluate_results(stats)
    stages = stats.get("stages") or []
    comparison = stats.get("comparison")
    verdict = "PASS ✅" if evaluation["overall_pass"] else "FAIL ❌"
    evidence_detail = "；".join(evaluation["evidence_errors"]) or "所有阶段均有真实样本"

    stage_rows = []
    for stage in stages:
        requests = int(stage.get("requests", 0) or 0)
        failures = int(stage.get("failures", 0) or 0)
        error = failures / requests * 100 if requests else float("inf")
        stage_rows.append(
            f"| {stage.get('users', 0)} | {stage.get('duration', 0)} | "
            f"{_finite(stage.get('covered_seconds'), 0)} | {stage.get('user_count_actual', 0)} | "
            f"{requests} | {_finite(stage.get('p95'), 0)} | {_finite(stage.get('p99'), 0)} | "
            f"{_finite(stage.get('rps'), 1)} | {_finite(error)}% |"
        )
    if not stage_rows:
        stage_rows.append("| 无数据 | — | — | — | — | — | — | — | — |")

    core_rows = []
    for item in evaluation["core_results"]:
        core_rows.append(
            f"| `{item['name']}` | {item['requests']} | {_finite(item['p95'])} | "
            f"{_finite(item['p99'])} | {_finite(item['error_rate'])}% | "
            f"{_pass(item['p95'] <= CORE_READ_P95_MS and item['p99'] <= CORE_READ_P99_MS and item['error_rate'] < CORE_ERROR_RATE_PCT)} |"
        )

    safety_rows = []
    for key in SAFETY_ZERO_KEYS:
        value = evaluation["safety"].get(key, "缺失")
        safety_rows.append(f"| `{key}` | {value} | {_pass(value == 0)} |")

    comparison_rows = []
    if comparison:
        for metric in ("p95", "p99", "rps", "failures"):
            data = comparison.get("total", {}).get(metric) or {}
            comparison_rows.append(
                f"| 聚合 {metric} | {_finite(data.get('baseline'))} | "
                f"{_finite(data.get('current'))} | {_finite(data.get('delta'))} |"
            )
        comparison_text = (
            "| 指标 | 基线 | 当前 | 差值 |\n|---|---:|---:|---:|\n"
            + "\n".join(comparison_rows)
            + f"\n\n业务 hash 相等：`{comparison.get('business_hashes_equal')}`"
        )
    else:
        comparison_text = "本次未提供 `--baseline <上一轮 summary.json>`，不声称已完成 A/B。"

    safety_detail = "；".join(evaluation["safety_errors"]) or "六类安全/完整性计数均为 0"
    resource_file = stats.get("resource_samples_file") or "未生成"
    stage_chain = " → ".join(str(stage["users"]) for stage in LOAD_STAGES)
    first = f"""# 最终容量验收报告

## 测试概要

| 项目 | 值 |
|---|---|
| 测试日期 | {stats.get('timestamp', '未知')} |
| 目标主机 | {args.host} |
| 正式梯度 | {stage_chain} |
| {LOAD_STAGES[-1]['users']} VU 稳态 | {LOAD_STAGES[-1]['duration']} 秒 |
| 预估总运行时长 | {ESTIMATED_TOTAL_SECONDS / 60:.1f} 分钟 |
| 原始资源样本 | `{resource_file}` |

## 阶段样本（稳态窗口逐请求统计）

| 目标 VU | 稳态秒数 | 实际覆盖秒数 | 窗口内最低 VU | 请求数 | P95 ms | P99 ms | RPS | 错误率 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
{chr(10).join(stage_rows)}

分位来自 `stage_stats.json` 的稳态窗口直方图（标称加压结束后 {STEADY_SETTLE_SECONDS:.0f} 秒起算，窗口外请求不计入）；
`locust_stats_history.csv` 的分位列只是最近约 10 秒的滚动值，只作曲线归档、不参与判定。

样本完整性：**{_pass(evaluation['samples_pass'])}**。{evidence_detail}

## 6000 VU 核心读 SLO

| 端点 | 请求数 | P95 ms | P99 ms | 错误率 | 判定 |
|---|---:|---:|---:|---:|---|
{chr(10).join(core_rows)}

- 核心读 P95 ≤ {CORE_READ_P95_MS:.0f}ms：**{_pass(evaluation['core_p95_pass'])}**
- 核心读 P99 ≤ {CORE_READ_P99_MS:.0f}ms：**{_pass(evaluation['core_p99_pass'])}**
- 核心成功请求错误率 < {CORE_ERROR_RATE_PCT}%：**{_pass(evaluation['core_error_pass'])}**
- 全场景错误率 < {ALL_SCENARIO_ERROR_RATE_PCT}%（全程与 6000 VU 取较差值）：**{_pass(evaluation['all_error_pass'])}**，实测 {_finite(evaluation['all_error_rate'])}%
"""

    return first + f"""
## 零泄露 / 零损坏证明

| 证据键 | 计数 | 判定 |
|---|---:|---|
{chr(10).join(safety_rows)}

安全证据：**{_pass(evaluation['safety_pass'])}**。{safety_detail}

## 与基线 A/B（只展示，不参与 PASS 判定）

{comparison_text}

## 最终判定

```
最终结果:  {verdict}
样本完整:  {_pass(evaluation['samples_pass'])}
核心 P95:  {_pass(evaluation['core_p95_pass'])}
核心 P99:  {_pass(evaluation['core_p99_pass'])}
核心错误率: {_pass(evaluation['core_error_pass'])}
全场景错误率: {_pass(evaluation['all_error_pass'])}
安全与完整性: {_pass(evaluation['safety_pass'])}
```

PASS 必须同时满足：所有阶段达到至少 90% 目标并发且有请求样本、三个核心读端点有
6000 VU 快照并满足 P95/P99/核心错误率、全场景错误率达标、六类安全计数完整且为 0。
任一项失败都返回退出码 2，不允许用缺失值或 0ms 假绿。
"""
