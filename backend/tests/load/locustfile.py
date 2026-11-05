"""审计平台容量压测：真实 UUID/账号池、信封登录与写环境硬闸门。

必填配置（二选一使用 JSON 字符串或文件）：
- GT_LOAD_ACCOUNTS_JSON / GT_LOAD_ACCOUNTS_FILE
- GT_LOAD_SCENARIOS_JSON / GT_LOAD_SCENARIOS_FILE

写请求默认关闭；仅 GT_LOAD_ALLOW_WRITES=1 且 GT_LOAD_DISPOSABLE_ENV=YES 时启用。
"""
from __future__ import annotations

import itertools
import logging
import threading
import time
from typing import Any
from uuid import uuid4

from locust import HttpUser, LoadTestShape, between, events, task

from tests.load.load_config import LoadConfig, load_config

logger = logging.getLogger(__name__)

LOAD_STAGES = [
    {"users": 100, "spawn_rate": 20, "duration": 60},
    {"users": 500, "spawn_rate": 50, "duration": 120},
    {"users": 1000, "spawn_rate": 100, "duration": 120},
    {"users": 3000, "spawn_rate": 200, "duration": 180},
    {"users": 6000, "spawn_rate": 300, "duration": 300},
]

_CONFIG: LoadConfig | None = None
_USER_SEQUENCE = itertools.count()
_USER_SEQUENCE_LOCK = threading.Lock()


def _unwrap(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    data = payload.get("data")
    return data if "code" in payload and isinstance(data, dict) else payload


def _next_identity():
    if _CONFIG is None:
        raise RuntimeError("压测配置尚未通过启动校验")
    with _USER_SEQUENCE_LOCK:
        index = next(_USER_SEQUENCE)
    return (
        _CONFIG.accounts[index % len(_CONFIG.accounts)],
        _CONFIG.scenarios[index % len(_CONFIG.scenarios)],
    )


@events.request.add_listener
def on_request(request_type, name, response_time, response_length, exception, **kwargs):
    if exception:
        logger.warning(
            "[FAILED] %s %s | response_time=%.0fms | exception=%s",
            request_type,
            name,
            response_time,
            exception,
        )


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    global _CONFIG
    try:
        # 专用库硬闸门：无论用哪个 runner / 裸 locust 命令发起，写压测都必须指向
        # 显式声明的可销毁库，否则在发任何请求之前就退出（R1.2）。
        from tests.load.load_guard import require_safe_load_target

        require_safe_load_target()
        _CONFIG = load_config()
    except Exception as exc:
        logger.error("容量测试启动校验失败：%s", exc)
        environment.process_exit_code = 2
        if environment.runner is not None:
            environment.runner.quit()
        return
    logger.info(
        "压测开始：目标=%s，账号=%d，场景=%d，写压测=%s，梯度=%s",
        environment.host,
        len(_CONFIG.accounts),
        len(_CONFIG.scenarios),
        _CONFIG.allow_writes,
        [stage["users"] for stage in LOAD_STAGES],
    )


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    stats = environment.runner.stats
    total = stats.total
    logger.info(
        "压测结束：requests=%d failures=%d p95=%.0fms p99=%.0fms rps=%.1f",
        total.num_requests,
        total.num_failures,
        total.get_response_time_percentile(0.95),
        total.get_response_time_percentile(0.99),
        total.current_rps,
    )
    if total.num_requests <= 0:
        environment.process_exit_code = 2
        logger.error("压测没有产生请求样本，强制失败")


class AuditPlatformUser(HttpUser):
    """按账号池和 UUID 场景池轮转的核心业务用户。"""

    wait_time = between(1, 3)

    def on_start(self):
        self.account, self.scenario = _next_identity()
        self.headers: dict[str, str] = {}
        self.authenticated = False
        self._login("/api/auth/login [on_start]")

    def _login(self, metric_name: str) -> None:
        with self.client.post(
            "/api/auth/login",
            json={
                "username": self.account.username,
                "password": self.account.password,
            },
            name=metric_name,
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(f"登录失败: HTTP {response.status_code}")
                self.authenticated = False
                return
            try:
                token = str(_unwrap(response.json()).get("access_token") or "")
            except Exception:
                token = ""
            if not token:
                response.failure("登录成功但业务信封中缺 access_token")
                self.authenticated = False
                return
            self.headers = {"Authorization": f"Bearer {token}"}
            self.authenticated = True
            response.success()

    def _handle_read(self, response, label: str) -> bool:
        if response.status_code == 200:
            response.success()
            return True
        if response.status_code == 401:
            response.failure("Token 过期 (401)")
            self._login("/api/auth/login [reauth]")
            return False
        response.failure(f"{label}: HTTP {response.status_code}")
        return False

    @task(1)
    def login(self):
        self._login("/api/auth/login")


    @task(3)
    def view_trial_balance(self):
        if not self.authenticated:
            return
        project = self.scenario.project_id
        with self.client.get(
            f"/api/projects/{project}/trial-balance",
            params={"year": self.scenario.year},
            headers=self.headers,
            name="/api/projects/{pid}/trial-balance",
            catch_response=True,
        ) as response:
            self._handle_read(response, "查询试算表失败")

    @task(2)
    def view_workpaper_list(self):
        if not self.authenticated:
            return
        project = self.scenario.project_id
        with self.client.get(
            f"/api/projects/{project}/working-papers",
            headers=self.headers,
            name="/api/projects/{pid}/working-papers",
            catch_response=True,
        ) as response:
            self._handle_read(response, "查询底稿列表失败")

    @task(2)
    def ledger_window(self):
        if not self.authenticated:
            return
        project = self.scenario.project_id
        code = self.scenario.account_code
        with self.client.get(
            f"/api/projects/{project}/ledger/window/{code}",
            params={"year": self.scenario.year, "limit": 200},
            headers=self.headers,
            name="/api/projects/{pid}/ledger/window/{account_code}",
            catch_response=True,
        ) as response:
            self._handle_read(response, "查询序时账窗口失败")


    @task(1)
    def edit_and_save_workpaper(self):
        if not self.authenticated or _CONFIG is None or not _CONFIG.allow_writes:
            return
        workpaper = self.scenario.workpaper_id
        if workpaper is None:
            return
        project = self.scenario.project_id
        with self.client.get(
            f"/api/projects/{project}/working-papers/{workpaper}",
            headers=self.headers,
            name="/api/projects/{pid}/working-papers/{wp_id} [GET]",
            catch_response=True,
        ) as response:
            if not self._handle_read(response, "读取底稿失败"):
                return

        operation_id = str(uuid4())
        payload = {
            "load_test_probe": {
                "operation_id": operation_id,
                "timestamp": time.time(),
            }
        }
        with self.client.put(
            f"/api/projects/{project}/working-papers/{workpaper}/parsed-data",
            headers={**self.headers, "Idempotency-Key": operation_id},
            json=payload,
            name="/api/projects/{pid}/working-papers/{wp_id}/parsed-data [PUT]",
            catch_response=True,
        ) as response:
            if response.status_code in (200, 204, 409):
                response.success()
            else:
                response.failure(f"保存底稿失败: HTTP {response.status_code}")


class StepLoadShape(LoadTestShape):
    """100 → 500 → 1000 → 3000 → 6000 用户梯度。"""

    def tick(self):
        run_time = self.get_run_time()
        elapsed = 0.0
        for stage in LOAD_STAGES:
            ramp_seconds = stage["users"] / stage["spawn_rate"]
            stage_seconds = ramp_seconds + stage["duration"]
            if run_time < elapsed + stage_seconds:
                return stage["users"], stage["spawn_rate"]
            elapsed += stage_seconds
        return None
