"""0.1/E5 容量运行期资源采样器（标准库线程，不阻塞 Locust 子进程）。

每个样本读取目标后端 ``/api/health`` 与 ``/metrics``，并记录负载机本机 CPU/内存。
无法读取时保留 error，不写 0（读不到 ≠ 指标为零）。输出与 Locust CSV 放同一 evidence-dir。
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

_PROMETHEUS_PREFIXES = (
    "db_pool_",
    "event_loop_",
    "platform_",
    "ledger_import_",
    "process_",
    "redis_",
    "http_requests_",
)


def _fetch(url: str, *, expect_json: bool) -> Any:
    request = Request(url, headers={"Accept": "application/json" if expect_json else "text/plain"})
    try:
        with urlopen(request, timeout=3.0) as response:  # noqa: S310 — URL 由验收命令显式给出
            body = response.read().decode("utf-8", errors="replace")
        if expect_json:
            payload = json.loads(body)
            if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
                return payload["data"]
            return payload
        return body
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
        return {"available": False, "error": f"{type(exc).__name__}: {exc}"}


def _selected_metrics(body: Any) -> dict[str, Any]:
    if not isinstance(body, str):
        return body if isinstance(body, dict) else {"available": False, "error": "metrics 非文本"}
    lines = [
        line for line in body.splitlines()
        if line and not line.startswith("#") and line.startswith(_PROMETHEUS_PREFIXES)
    ]
    return {"available": True, "lines": lines}


def _local_resources() -> dict[str, Any]:
    try:
        import psutil
        memory = psutil.virtual_memory()
        return {
            "available": True,
            "cpu_percent": float(psutil.cpu_percent(interval=None)),
            "memory_used_bytes": int(memory.used),
            "memory_available_bytes": int(memory.available),
            "memory_percent": float(memory.percent),
        }
    except Exception as exc:  # noqa: BLE001 — psutil 是可选依赖
        return {"available": False, "error": f"{type(exc).__name__}: {exc}"}

def collect_resource_snapshot(host: str) -> dict[str, Any]:
    """采集一个只读快照。目标端点不可用时保留错误，不阻断负载本身。"""
    base = host.rstrip("/")
    health = _fetch(f"{base}/api/health", expect_json=True)
    metrics = _selected_metrics(_fetch(f"{base}/metrics", expect_json=False))
    return {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "health": health,
        "metrics": metrics,
        "load_generator": _local_resources(),
    }


class ResourceSampler:
    """后台周期采样；``stop`` 总会补一个终态样本并原子写 JSON。"""

    def __init__(self, host: str, output: Path, *, interval_s: float = 15.0) -> None:
        if interval_s <= 0:
            raise ValueError("资源采样间隔必须大于 0")
        self.host = host
        self.output = output
        self.interval_s = interval_s
        self.samples: list[dict[str, Any]] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError("ResourceSampler 已启动")
        self.samples.append(collect_resource_snapshot(self.host))
        self._thread = threading.Thread(
            target=self._run,
            name="capacity-resource-sampler",
            daemon=True,
        )
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.wait(self.interval_s):
            self.samples.append(collect_resource_snapshot(self.host))

    def stop(self) -> Path:
        if self._thread is None:
            raise RuntimeError("ResourceSampler 尚未启动")
        self._stop.set()
        self._thread.join(timeout=max(5.0, self.interval_s + 5.0))
        self.samples.append(collect_resource_snapshot(self.host))
        self.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.output.with_suffix(f"{self.output.suffix}.tmp")
        temporary.write_text(
            json.dumps({
                "schema_version": 1,
                "host": self.host,
                "interval_seconds": self.interval_s,
                "samples": self.samples,
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(self.output)
        return self.output
