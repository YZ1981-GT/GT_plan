"""E5/E6 稳态窗口逐请求统计（不依赖 Locust history CSV 的滚动分位）。

Locust ``--csv-full-history`` 的历史行里，分位列是最近约 10 秒的滚动窗口，计数列却是全程
累计：拿「阶段最后一行」判 30 分钟稳态的 p95/p99 等于只看最后 10 秒，错误率还被前面阶段
稀释。这里在 ``events.request`` 上按 StepLoadShape 的稳态窗口逐请求累计直方图，原始桶计数
落盘，runner 从桶里复算分位；分布式负载（E4）只需把各 worker 同名同桶的计数相加。

本模块只用标准库：pytest 里绝不能 ``import locust``（gevent 猴子补丁会卡死整个测试进程）。
"""
from __future__ import annotations

import json
import math
import threading
import time
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any

from tests.load.load_contract import LOAD_STAGES, STEADY_SETTLE_SECONDS

SCHEMA_VERSION = 1
STAGE_STATS_ENV = "GT_LOAD_STAGE_STATS_FILE"
STAGE_STATS_FILE_NAME = "stage_stats.json"


def stage_timeline(
    stages: Iterable[Mapping[str, Any]] = LOAD_STAGES,
    *,
    settle_seconds: float = STEADY_SETTLE_SECONDS,
) -> list[dict[str, Any]]:
    """StepLoadShape 与稳态窗口共用的时间线（单一来源）。

    第 i 阶段占 ``[begin_s, end_s)``：先按 ``users / spawn_rate`` 的标称时长加压，再稳态
    ``duration`` 秒；稳态窗口从标称加压结束后再过 ``settle_seconds`` 开始计入。
    """
    timeline: list[dict[str, Any]] = []
    elapsed = 0.0
    for stage in stages:
        users = int(stage["users"])
        ramp = users / float(stage["spawn_rate"])
        end = elapsed + ramp + float(stage["duration"])
        steady_start = elapsed + ramp + settle_seconds
        if steady_start >= end:
            raise ValueError(f"{users} 用户阶段稳态时长不足 {settle_seconds} 秒")
        timeline.append({
            "users": users,
            "spawn_rate": float(stage["spawn_rate"]),
            "duration": int(stage["duration"]),
            "begin_s": elapsed,
            "steady_start_s": steady_start,
            "end_s": end,
            "required_seconds": end - steady_start,
        })
        elapsed = end
    return timeline


def bucket_ms(response_time: float) -> int:
    """与 Locust 同一取整口径：<100ms 精确到 1ms，<1s 到 10ms，<10s 到 100ms，再往上到 1s。"""
    value = max(0.0, float(response_time))
    if value < 100:
        return int(round(value))
    if value < 1000:
        return int(round(value, -1))
    if value < 10000:
        return int(round(value, -2))
    return int(round(value, -3))


def percentile(histogram: Mapping[int, int], fraction: float) -> float | None:
    """直方图上的 nearest-rank 分位；无样本返回 None（不写 0ms 假绿）。"""
    total = sum(int(count) for count in histogram.values())
    if total <= 0:
        return None
    # 减一个极小量：0.07 * 100 == 7.000000000000001，直接 ceil 会把秩错推到 8。
    rank = max(1, math.ceil(fraction * total - 1e-9))
    seen = 0
    for value in sorted(histogram):
        seen += int(histogram[value])
        if seen >= rank:
            return float(value)
    return float(max(histogram))


def _empty_counter() -> dict[str, Any]:
    return {"requests": 0, "failures": 0, "histogram": {}}


def _add(counter: dict[str, Any], response_time: float, failed: bool) -> None:
    counter["requests"] += 1
    if failed:
        counter["failures"] += 1
    bucket = bucket_ms(response_time)
    counter["histogram"][bucket] = counter["histogram"].get(bucket, 0) + 1


def _export_counter(counter: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "requests": int(counter["requests"]),
        "failures": int(counter["failures"]),
        "histogram": {str(key): int(value) for key, value in sorted(counter["histogram"].items())},
    }


class StageRecorder:
    """按稳态窗口累计请求；窗口外（加压期、阶段切换、结束后）的请求不进阶段统计。"""

    def __init__(
        self,
        timeline: Iterable[Mapping[str, Any]] | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.timeline = [dict(item) for item in (timeline if timeline is not None else stage_timeline())]
        self._clock = clock
        self._lock = threading.Lock()
        self._started_at: float | None = None
        self._stopped_at: float | None = None
        self._stages = self._fresh_stages()

    def _fresh_stages(self) -> list[dict[str, Any]]:
        return [
            {"aggregate": _empty_counter(), "endpoints": {}, "user_min": None, "user_max": None}
            for _ in self.timeline
        ]

    def start(self) -> None:
        with self._lock:
            self._started_at = self._clock()
            self._stopped_at = None
            self._stages = self._fresh_stages()

    def stop(self) -> None:
        with self._lock:
            if self._started_at is not None and self._stopped_at is None:
                self._stopped_at = self._clock()

    def _stage_index(self, run_time: float) -> int | None:
        for index, item in enumerate(self.timeline):
            if item["steady_start_s"] <= run_time < item["end_s"]:
                return index
        return None

    def record(
        self,
        *,
        name: str,
        request_type: str,
        response_time: float,
        failed: bool,
        user_count: int,
    ) -> None:
        with self._lock:
            if self._started_at is None or self._stopped_at is not None:
                return
            index = self._stage_index(self._clock() - self._started_at)
            if index is None:
                return
            stage = self._stages[index]
            _add(stage["aggregate"], response_time, failed)
            key = f"{request_type} {name}"
            endpoint = stage["endpoints"].get(key)
            if endpoint is None:
                endpoint = {"name": name, "type": request_type, **_empty_counter()}
                stage["endpoints"][key] = endpoint
            _add(endpoint, response_time, failed)
            users = int(user_count)
            stage["user_min"] = users if stage["user_min"] is None else min(stage["user_min"], users)
            stage["user_max"] = users if stage["user_max"] is None else max(stage["user_max"], users)

    def to_payload(self) -> dict[str, Any]:
        """原始桶计数快照；未 stop 时按当前时刻计覆盖时长。"""
        with self._lock:
            if self._started_at is None:
                run_seconds = 0.0
            else:
                ended = self._stopped_at if self._stopped_at is not None else self._clock()
                run_seconds = max(0.0, ended - self._started_at)
            stages = []
            for item, stage in zip(self.timeline, self._stages):
                covered = max(0.0, min(item["end_s"], run_seconds) - item["steady_start_s"])
                stages.append({
                    **item,
                    "covered_seconds": round(covered, 3),
                    "user_count_min": stage["user_min"],
                    "user_count_max": stage["user_max"],
                    "aggregate": _export_counter(stage["aggregate"]),
                    "endpoints": [
                        {"name": value["name"], "type": value["type"], **_export_counter(value)}
                        for _, value in sorted(stage["endpoints"].items())
                    ],
                })
            return {
                "schema_version": SCHEMA_VERSION,
                "source": "locust events.request（稳态窗口逐请求直方图）",
                "run_seconds": round(run_seconds, 3),
                "stages": stages,
            }

    def write(self, path: Path) -> Path:
        payload = self.to_payload()
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(f"{path.suffix}.tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)
        return path


def _histogram(counter: Mapping[str, Any]) -> dict[int, int]:
    raw = counter.get("histogram")
    if not isinstance(raw, Mapping):
        raise ValueError("稳态统计缺 histogram")
    histogram = {int(key): int(value) for key, value in raw.items()}
    if sum(histogram.values()) != int(counter.get("requests", -1)):
        raise ValueError("稳态统计 histogram 计数与 requests 不一致")
    return histogram


def _metrics(counter: Mapping[str, Any], covered: float) -> dict[str, Any]:
    histogram = _histogram(counter)
    requests = int(counter["requests"])
    return {
        "requests": requests,
        "failures": int(counter["failures"]),
        "p50": percentile(histogram, 0.50),
        "p95": percentile(histogram, 0.95),
        "p99": percentile(histogram, 0.99),
        "rps": requests / covered if covered > 0 else 0.0,
    }


def summarize_stage_payload(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    """把 recorder 原始桶复算成 evaluate_results 读取的阶段列表。"""
    if not isinstance(payload, Mapping) or payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"稳态统计 schema_version 必须是 {SCHEMA_VERSION}")
    stages = payload.get("stages")
    if not isinstance(stages, list):
        raise ValueError("稳态统计缺 stages 列表")
    summary: list[dict[str, Any]] = []
    for stage in stages:
        covered = float(stage.get("covered_seconds") or 0.0)
        summary.append({
            "users": int(stage["users"]),
            "duration": int(stage["duration"]),
            "user_count_actual": int(stage.get("user_count_min") or 0),
            "user_count_max": int(stage.get("user_count_max") or 0),
            "covered_seconds": covered,
            **_metrics(stage["aggregate"], covered),
            "endpoints": [
                {"name": item["name"], "type": item.get("type", ""), **_metrics(item, covered)}
                for item in stage.get("endpoints") or []
            ],
        })
    return summary


def load_stage_stats(path: Path) -> list[dict[str, Any]]:
    """读取 recorder 落盘文件；缺失或损坏一律抛 ValueError，由 runner 记为证据错误。"""
    if not path.is_file():
        raise ValueError(f"未生成 {path.name}（Locust 未写出稳态窗口统计）")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path.name} 不是合法 JSON：{exc}") from exc
    try:
        return summarize_stage_payload(payload)
    except (KeyError, TypeError) as exc:
        raise ValueError(f"{path.name} 结构不完整：{exc!r}") from exc
