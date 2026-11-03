"""Microbenchmark Observability normal-2xx fast path (diagnostic, not a CI gate)."""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import statistics
import sys
import time
from pathlib import Path

from starlette.datastructures import Headers, MutableHeaders

BACKEND = Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.middleware._asgi import request_path
from app.middleware.observability import ObservabilityMiddleware


async def endpoint(scope, receive, send):
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"{}"})


class EagerBaseline:
    """Change 前 normal-2xx 分支：DEBUG 关闭也构造 dict + Headers + round。"""
    def __init__(self, app):
        self.app = app
        self.logger = logging.getLogger("bench.observability.baseline")

    async def __call__(self, scope, receive, send):
        path = request_path(scope)
        started = time.perf_counter()

        async def wrapped(message):
            if message["type"] == "http.response.start":
                duration_ms = (time.perf_counter() - started) * 1000
                data = {
                    "method": scope["method"], "path": path, "status": message["status"],
                    "duration_ms": round(duration_ms, 1),
                    "user_agent": Headers(scope=scope).get("user-agent", "")[:50],
                }
                self.logger.debug("REQUEST %s", data)
                MutableHeaders(scope=message)["X-Response-Time"] = f"{duration_ms:.0f}ms"
            await send(message)

        await self.app(scope, receive, wrapped)


async def one(middleware, iterations: int) -> float:
    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(_message):
        return None

    started = time.perf_counter()
    for _ in range(iterations):
        scope = {
            "type": "http", "method": "GET", "path": "/api/version", "raw_path": b"/api/version",
            "root_path": "", "query_string": b"", "headers": [(b"user-agent", b"bench")],
            "scheme": "http", "server": ("t", 80), "client": ("127.0.0.1", 1),
            "http_version": "1.1", "asgi": {"version": "3.0"},
        }
        await middleware(scope, receive, send)
    return (time.perf_counter() - started) * 1e9 / iterations


async def main_async(iterations: int, rounds: int) -> dict:
    logging.getLogger("audit_platform.metrics").setLevel(logging.WARNING)
    current = ObservabilityMiddleware(endpoint)
    baseline = EagerBaseline(endpoint)
    samples = {"baseline_ns": [], "fast_ns": []}
    for round_no in range(rounds):
        order = (("baseline_ns", baseline), ("fast_ns", current))
        if round_no % 2:
            order = tuple(reversed(order))
        for key, middleware in order:
            samples[key].append(await one(middleware, iterations))
    old = statistics.median(samples["baseline_ns"])
    new = statistics.median(samples["fast_ns"])
    return {
        "iterations_per_round": iterations,
        "rounds": rounds,
        "baseline_median_ns": round(old, 1),
        "fast_median_ns": round(new, 1),
        "saved_ns": round(old - new, 1),
        "saved_percent": round((old - new) * 100 / old, 1),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=50000)
    parser.add_argument("--rounds", type=int, default=5)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(main_async(args.iterations, args.rounds)), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
