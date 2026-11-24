"""A2 冒烟假后端：纯标准库 HTTP 服务器，按 Locust 压测契约返回信封响应。

用途：在没有真实后端/真实 PG 的机器上验证 **编排层**（master/worker 启动、
stage_stats 落盘、逐 worker 合并判定）的正确性 —— 不验证业务性能。

契约（与 locustfile.py / safety_probes.py 对齐）：
- ``POST /api/auth/login``                     → 200 ``{"code":0,"data":{"access_token":"..."}}``
- ``GET  /api/projects/{pid}/trial-balance``   → 200 信封（可选人工延迟）
- ``GET  /api/projects/{pid}/working-papers``  → 200 信封
- ``GET  /api/projects/{pid}/ledger/window/*`` → 200 信封
- ``GET  /api/projects/{pid}/events/stream``   → SSE，id 连续递增（event_loss 探针）
- 其余路径                                     → 404

延迟注入：``FAKE_LATENCY_MS`` 环境变量给读端点加固定延迟（默认 0），
用于让 p95/p99 有非零样本，验证分位复算链路。
"""
from __future__ import annotations

import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

_SSE_COUNTER_LOCK = threading.Lock()
_SSE_COUNTER = 0


def _latency_ms() -> float:
    raw = (os.environ.get("FAKE_LATENCY_MS") or "0").strip()
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 0.0


class FakeAuditHandler(BaseHTTPRequestHandler):
    """只读假后端；每个请求独立线程（ThreadingHTTPServer）。"""

    protocol_version = "HTTP/1.1"

    # 静默访问日志：冒烟只看汇总，不刷屏。
    def log_message(self, format: str, *args) -> None:  # noqa: A002
        return

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _envelope(self, data: dict | list | None = None) -> None:
        self._send_json(200, {"code": 0, "message": "ok", "data": data if data is not None else {}})

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            self.rfile.read(length)
        if self.path.rstrip("/").endswith("/api/auth/login"):
            self._envelope({"access_token": "fake-token", "token_type": "bearer"})
            return
        self._send_json(404, {"code": 404, "message": "not found"})

    def do_GET(self) -> None:
        path = self.path.split("?")[0]
        delay = _latency_ms()
        if delay:
            time.sleep(delay / 1000.0)
        if path.endswith("/events/stream"):
            self._serve_sse()
            return
        if "/api/projects/" in path:
            self._envelope({"rows": [], "probe": "fake"})
            return
        self._send_json(404, {"code": 404, "message": "not found"})

    def _serve_sse(self) -> None:
        """发 40 条 id 连续的 SSE 事件后结束（event_loss 探针按 id 对账）。"""
        global _SSE_COUNTER
        with _SSE_COUNTER_LOCK:
            start = _SSE_COUNTER + 1
            _SSE_COUNTER = start + 40
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.end_headers()
        try:
            for event_id in range(start, start + 40):
                chunk = f"id: {event_id}\nevent: message\ndata: {{}}\n\n".encode("utf-8")
                self.wfile.write(chunk)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass


def serve(host: str = "127.0.0.1", port: int = 0) -> tuple[ThreadingHTTPServer, int]:
    """启动假后端；port=0 时由内核分配。返回 (server, actual_port)。"""
    server = ThreadingHTTPServer((host, port), FakeAuditHandler)
    server.daemon_threads = True
    return server, server.server_address[1]


def main() -> int:
    """独立进程入口：``python -m tests.load.fakeserver --port 19990``。"""
    import argparse

    parser = argparse.ArgumentParser(description="A2 冒烟假后端")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args()
    server, actual = serve(args.host, args.port)
    print(f"FAKESERVER_READY {args.host}:{actual}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
