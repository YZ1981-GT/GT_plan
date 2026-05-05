"""
压力测试脚本 — 使用 Locust 模拟并发用户 + 独立报告生成器

两种运行方式：
  1) Locust UI（推荐做探索式压测）：
     pip install locust
     locust -f backend/tests/load_test.py --host http://localhost:9980
     Web UI: http://localhost:8089

  2) 独立批量压测 + 结构化报告（CI/CD 推荐）：
     python backend/tests/load_test.py --users 100 --duration 60 \
       --host http://localhost:9980 --out report.json

目标：验证 6000 并发用户下的系统表现（需求 12）
性能目标：
  - 平均响应 ≤ 2000ms，P99 ≤ 5000ms
  - 错误率 < 1%（HTTP 5xx）

需求 12.1 覆盖的 5 个核心接口：
  - POST /api/auth/login
  - GET  /api/projects/{id}/working-papers
  - GET  /api/projects/{id}/working-papers/{wp_id}
  - GET  /api/projects/{id}/disclosure-notes
  - GET  /api/dashboard/overview
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import statistics
import time
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Locust 用户类（可选依赖，仅在有 locust 时导入）
# ---------------------------------------------------------------------------

try:
    from locust import HttpUser, between, task, tag  # type: ignore
    _LOCUST_AVAILABLE = True
except ImportError:
    _LOCUST_AVAILABLE = False
    HttpUser = object  # type: ignore
    def between(*a, **k):  # type: ignore
        return lambda *a2, **k2: None
    def task(*a, **k):  # type: ignore
        return lambda f: f
    def tag(*a, **k):  # type: ignore
        return lambda f: f


class AuditPlatformUser(HttpUser):
    """模拟审计平台用户的典型操作流程（Locust 场景）"""

    wait_time = between(1, 3)

    token: str = ""
    project_id: str = ""
    wp_id: str = ""

    def on_start(self):
        """登录获取 token + 预抓一个项目/底稿 ID 供后续读接口使用"""
        resp = self.client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "admin123"},
            name="POST /api/auth/login",
        )
        if resp.status_code == 200:
            data = resp.json()
            payload = data.get("data", data) if isinstance(data, dict) else data
            self.token = payload.get("access_token", "")

        self._pick_project()
        self._pick_workpaper()

    @property
    def auth_headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    # ── 需求 12.1 核心接口（高权重） ─────────────────────────

    @tag("core", "workpaper")
    @task(8)
    def list_workpapers_v2(self):
        """GET /api/projects/{id}/working-papers — 底稿列表"""
        if not self.project_id:
            return
        self.client.get(
            f"/api/projects/{self.project_id}/working-papers",
            headers=self.auth_headers,
            name="GET /api/projects/[id]/working-papers",
        )

    @tag("core", "workpaper")
    @task(6)
    def get_workpaper_detail(self):
        """GET /api/projects/{id}/working-papers/{wp_id} — 底稿详情"""
        if not (self.project_id and self.wp_id):
            return
        self.client.get(
            f"/api/projects/{self.project_id}/working-papers/{self.wp_id}",
            headers=self.auth_headers,
            name="GET /api/projects/[id]/working-papers/[wp_id]",
        )

    @tag("core", "disclosure")
    @task(5)
    def list_disclosure_notes(self):
        """GET /api/projects/{id}/disclosure-notes — 附注查询"""
        if not self.project_id:
            return
        self.client.get(
            f"/api/projects/{self.project_id}/disclosure-notes",
            headers=self.auth_headers,
            name="GET /api/projects/[id]/disclosure-notes",
        )

    @tag("core", "dashboard")
    @task(4)
    def dashboard_overview(self):
        """GET /api/dashboard/overview — 仪表盘概览"""
        self.client.get(
            "/api/dashboard/overview",
            headers=self.auth_headers,
            name="GET /api/dashboard/overview",
        )

    # ── 其它常用读操作（参考基线） ──────────────────────────

    @tag("read", "project")
    @task(4)
    def list_projects(self):
        self.client.get(
            "/api/projects/",
            headers=self.auth_headers,
            name="GET /api/projects/",
        )

    @tag("read", "trial_balance")
    @task(3)
    def get_trial_balance(self):
        if not self.project_id:
            return
        self.client.get(
            f"/api/projects/{self.project_id}/trial-balance",
            headers=self.auth_headers,
            params={"year": 2024},
            name="GET /api/projects/[id]/trial-balance",
        )

    # ── 中频写 ──────────────────────────────────────────────

    @tag("write", "adjustment")
    @task(1)
    def create_adjustment(self):
        if not self.project_id:
            return
        self.client.post(
            f"/api/adjustments/{self.project_id}",
            headers=self.auth_headers,
            json={
                "year": 2024,
                "description": f"压力测试分录-{random.randint(1, 10000)}",
                "entry_type": "reclassification",
                "lines": [
                    {"account_code": "6001", "account_name": "主营业务收入",
                     "debit_amount": 1000, "credit_amount": 0},
                    {"account_code": "6051", "account_name": "其他业务收入",
                     "debit_amount": 0, "credit_amount": 1000},
                ],
            },
            name="POST /api/adjustments/[id]",
        )

    # ── 辅助 ────────────────────────────────────────────────

    def _pick_project(self):
        resp = self.client.get(
            "/api/projects/",
            headers=self.auth_headers,
            name="GET /api/projects/ [pick]",
        )
        if resp.status_code == 200:
            items = resp.json()
            if isinstance(items, dict):
                items = items.get("data", items.get("rows", []))
            if isinstance(items, list) and items:
                self.project_id = items[0].get("id", "") or ""

    def _pick_workpaper(self):
        if not self.project_id:
            return
        resp = self.client.get(
            f"/api/projects/{self.project_id}/working-papers",
            headers=self.auth_headers,
            name="GET /api/projects/[id]/working-papers [pick]",
        )
        if resp.status_code == 200:
            items = resp.json()
            if isinstance(items, dict):
                items = items.get("data", items.get("rows", []))
            if isinstance(items, list) and items:
                self.wp_id = items[0].get("id", "") or ""


# ===========================================================================
# 独立批量压测模式（不依赖 locust）
# 用途：CI/CD 里跑一轮压测并输出结构化 JSON 报告
# ===========================================================================

@dataclass
class EndpointStats:
    path: str
    method: str
    samples: list[float] = field(default_factory=list)  # 响应时间（ms）
    errors: int = 0
    status_codes: dict[int, int] = field(default_factory=dict)

    def record(self, elapsed_ms: float, status: int) -> None:
        self.samples.append(elapsed_ms)
        self.status_codes[status] = self.status_codes.get(status, 0) + 1
        if status >= 500:
            self.errors += 1

    def summary(self) -> dict[str, Any]:
        if not self.samples:
            return {
                "path": self.path,
                "method": self.method,
                "count": 0,
                "avg_ms": 0.0,
                "p95_ms": 0.0,
                "p99_ms": 0.0,
                "error_rate": 0.0,
                "status_codes": {},
            }
        sorted_samples = sorted(self.samples)
        n = len(sorted_samples)

        def pct(p: float) -> float:
            idx = min(n - 1, int(n * p))
            return sorted_samples[idx]

        return {
            "path": self.path,
            "method": self.method,
            "count": n,
            "avg_ms": round(statistics.mean(sorted_samples), 2),
            "p95_ms": round(pct(0.95), 2),
            "p99_ms": round(pct(0.99), 2),
            "error_rate": round(self.errors / n, 4),
            "status_codes": self.status_codes,
        }


# 需求 12.1 定义的 5 个核心接口（实际 URL 在运行时带入变量）
CORE_ENDPOINTS = [
    ("POST", "/api/auth/login"),
    ("GET", "/api/projects/{project_id}/working-papers"),
    ("GET", "/api/projects/{project_id}/working-papers/{wp_id}"),
    ("GET", "/api/projects/{project_id}/disclosure-notes"),
    ("GET", "/api/dashboard/overview"),
]


async def _run_user_session(
    host: str,
    username: str,
    password: str,
    duration: float,
    stats: dict[str, EndpointStats],
    slow_threshold_ms: float,
) -> list[dict[str, Any]]:
    """单个用户会话：持续 `duration` 秒轮询核心接口。"""
    import httpx  # 运行时依赖
    slow_queries: list[dict[str, Any]] = []

    async with httpx.AsyncClient(base_url=host, timeout=15.0) as client:
        # 登录
        t0 = time.perf_counter()
        try:
            resp = await client.post(
                "/api/auth/login",
                json={"username": username, "password": password},
            )
            elapsed = (time.perf_counter() - t0) * 1000
            stats["POST /api/auth/login"].record(elapsed, resp.status_code)
            if elapsed > slow_threshold_ms:
                slow_queries.append({
                    "path": "/api/auth/login", "elapsed_ms": elapsed,
                    "status": resp.status_code,
                })
            if resp.status_code != 200:
                return slow_queries
            data = resp.json()
            payload = data.get("data", data) if isinstance(data, dict) else data
            token = payload.get("access_token", "") if isinstance(payload, dict) else ""
        except Exception:
            return slow_queries

        headers = {"Authorization": f"Bearer {token}"} if token else {}

        # 预取 project_id 和 wp_id（不计入核心接口统计）
        project_id = ""
        wp_id = ""
        try:
            resp = await client.get("/api/projects/", headers=headers)
            items = resp.json() if resp.status_code == 200 else []
            if isinstance(items, dict):
                items = items.get("data", items.get("rows", []))
            if isinstance(items, list) and items:
                project_id = items[0].get("id", "") or ""
        except Exception:
            pass

        if project_id:
            try:
                resp = await client.get(
                    f"/api/projects/{project_id}/working-papers", headers=headers
                )
                items = resp.json() if resp.status_code == 200 else []
                if isinstance(items, dict):
                    items = items.get("data", items.get("rows", []))
                if isinstance(items, list) and items:
                    wp_id = items[0].get("id", "") or ""
            except Exception:
                pass

        # 主循环：轮询 4 个核心读接口
        deadline = time.perf_counter() + duration
        while time.perf_counter() < deadline:
            paths = [
                ("GET", f"/api/projects/{project_id}/working-papers",
                 "GET /api/projects/{project_id}/working-papers") if project_id else None,
                ("GET", f"/api/projects/{project_id}/working-papers/{wp_id}",
                 "GET /api/projects/{project_id}/working-papers/{wp_id}") if (project_id and wp_id) else None,
                ("GET", f"/api/projects/{project_id}/disclosure-notes",
                 "GET /api/projects/{project_id}/disclosure-notes") if project_id else None,
                ("GET", "/api/dashboard/overview", "GET /api/dashboard/overview"),
            ]
            for item in paths:
                if item is None:
                    continue
                method, url, key = item
                t0 = time.perf_counter()
                try:
                    r = await client.get(url, headers=headers)
                    elapsed = (time.perf_counter() - t0) * 1000
                    stats[key].record(elapsed, r.status_code)
                    if elapsed > slow_threshold_ms:
                        slow_queries.append({
                            "path": url, "elapsed_ms": elapsed, "status": r.status_code,
                        })
                except Exception:
                    elapsed = (time.perf_counter() - t0) * 1000
                    stats[key].record(elapsed, 599)  # 本地异常视为 5xx
            await asyncio.sleep(random.uniform(0.2, 0.6))

    return slow_queries


async def run_standalone(
    host: str,
    users: int,
    duration: float,
    username: str = "admin",
    password: str = "admin123",
    slow_threshold_ms: float = 2000.0,
) -> dict[str, Any]:
    """并发启动 `users` 个会话，运行 `duration` 秒后生成报告。"""
    # 初始化每个核心端点的统计槽
    key_for = {
        "POST /api/auth/login": ("POST", "/api/auth/login"),
        "GET /api/projects/{project_id}/working-papers": ("GET", "/api/projects/{project_id}/working-papers"),
        "GET /api/projects/{project_id}/working-papers/{wp_id}": ("GET", "/api/projects/{project_id}/working-papers/{wp_id}"),
        "GET /api/projects/{project_id}/disclosure-notes": ("GET", "/api/projects/{project_id}/disclosure-notes"),
        "GET /api/dashboard/overview": ("GET", "/api/dashboard/overview"),
    }
    stats = {k: EndpointStats(path=v[1], method=v[0]) for k, v in key_for.items()}

    started = time.perf_counter()
    tasks = [
        _run_user_session(host, username, password, duration, stats, slow_threshold_ms)
        for _ in range(users)
    ]
    slow_query_lists = await asyncio.gather(*tasks, return_exceptions=True)
    elapsed = time.perf_counter() - started

    # 聚合
    endpoint_summaries = [s.summary() for s in stats.values()]
    total_requests = sum(s["count"] for s in endpoint_summaries)
    total_errors = sum(s["count"] * s["error_rate"] for s in endpoint_summaries)
    all_samples = [t for s in stats.values() for t in s.samples]
    tps = total_requests / elapsed if elapsed > 0 else 0

    def agg_pct(p: float) -> float:
        if not all_samples:
            return 0.0
        arr = sorted(all_samples)
        return round(arr[min(len(arr) - 1, int(len(arr) * p))], 2)

    # 需求 12.3：未达标时标注瓶颈
    bottlenecks = [
        s["path"] for s in endpoint_summaries
        if s["count"] > 0 and (s["avg_ms"] > 2000 or s["p99_ms"] > 5000 or s["error_rate"] > 0.01)
    ]

    # 合并慢查询日志（来自所有用户会话）
    slow_queries: list[dict[str, Any]] = []
    for sq in slow_query_lists:
        if isinstance(sq, list):
            slow_queries.extend(sq)
    # 只保留最慢的 20 条
    slow_queries.sort(key=lambda x: x.get("elapsed_ms", 0), reverse=True)
    slow_queries = slow_queries[:20]

    report = {
        "summary": {
            "host": host,
            "users": users,
            "target_duration_seconds": duration,
            "total_requests": total_requests,
            "duration_seconds": round(elapsed, 2),
            "tps": round(tps, 2),
            "avg_response_ms": round(
                statistics.mean(all_samples), 2
            ) if all_samples else 0.0,
            "p95_response_ms": agg_pct(0.95),
            "p99_response_ms": agg_pct(0.99),
            "error_rate": round(
                total_errors / total_requests, 4
            ) if total_requests else 0.0,
        },
        "endpoints": sorted(endpoint_summaries, key=lambda e: -e["count"]),
        "bottlenecks": bottlenecks,
        "slow_queries": slow_queries,
        "performance_targets": {
            "avg_response_ms": 2000,
            "p99_response_ms": 5000,
            "error_rate": 0.01,
        },
    }
    report["summary"]["meets_targets"] = (
        report["summary"]["avg_response_ms"] <= 2000
        and report["summary"]["p99_response_ms"] <= 5000
        and report["summary"]["error_rate"] < 0.01
    )
    return report


def main():
    parser = argparse.ArgumentParser(
        description="审计平台压测：运行独立批量压测并生成结构化报告"
    )
    parser.add_argument("--host", default="http://localhost:9980",
                        help="目标服务器 URL，默认 http://localhost:9980")
    parser.add_argument("--users", type=int, default=50,
                        help="并发用户数，默认 50")
    parser.add_argument("--duration", type=float, default=30.0,
                        help="每个用户持续运行秒数，默认 30")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", default="admin123")
    parser.add_argument("--out", default="load_test_report.json",
                        help="报告输出路径，默认 load_test_report.json")
    parser.add_argument("--slow-threshold", type=float, default=2000.0,
                        help="慢查询阈值（ms），默认 2000")
    args = parser.parse_args()

    print(f"[载入压测] host={args.host} users={args.users} duration={args.duration}s")
    report = asyncio.run(
        run_standalone(
            host=args.host,
            users=args.users,
            duration=args.duration,
            username=args.username,
            password=args.password,
            slow_threshold_ms=args.slow_threshold,
        )
    )

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    # 终端简报
    s = report["summary"]
    print(f"\n=== 压测结果 ===")
    print(f"  总请求数      : {s['total_requests']}")
    print(f"  持续时长      : {s['duration_seconds']}s")
    print(f"  TPS           : {s['tps']}")
    print(f"  平均响应      : {s['avg_response_ms']}ms")
    print(f"  P95 响应      : {s['p95_response_ms']}ms")
    print(f"  P99 响应      : {s['p99_response_ms']}ms")
    print(f"  错误率        : {s['error_rate'] * 100:.2f}%")
    print(f"  达到性能目标  : {'✓ 是' if s['meets_targets'] else '✗ 否'}")
    if report["bottlenecks"]:
        print(f"\n瓶颈接口：")
        for b in report["bottlenecks"]:
            print(f"  - {b}")
    print(f"\n完整报告已保存到: {args.out}")

    # 未达标时退出码 1，便于 CI 判断
    return 0 if s["meets_targets"] else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
