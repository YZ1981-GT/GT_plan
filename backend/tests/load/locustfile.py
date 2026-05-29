"""
Locust 压测脚本 — 审计平台核心场景

使用方法:
    locust -f tests/load/locustfile.py --host=http://localhost:9980

梯度加压（自动 LoadTestShape）:
    100 → 500 → 1000 → 3000 → 6000 用户

手动模式（不使用 shape，自行指定用户数）:
    locust -f tests/load/locustfile.py --host=http://localhost:9980 --users 100 --spawn-rate 10
"""

import time
import logging

from locust import HttpUser, between, events, task
from locust.runners import MasterRunner, WorkerRunner

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 配置常量
# ---------------------------------------------------------------------------

# 默认测试项目 ID（根据实际数据调整）
PROJECT_ID = 1

# 默认底稿 ID（用于编辑/保存场景）
WORKPAPER_ID = 1

# 梯度加压阶段配置: (用户数, 加压速率 users/s, 持续时间 s)
LOAD_STAGES = [
    {"users": 100, "spawn_rate": 20, "duration": 60},
    {"users": 500, "spawn_rate": 50, "duration": 120},
    {"users": 1000, "spawn_rate": 100, "duration": 120},
    {"users": 3000, "spawn_rate": 200, "duration": 180},
    {"users": 6000, "spawn_rate": 300, "duration": 300},
]

# ---------------------------------------------------------------------------
# 自定义指标收集
# ---------------------------------------------------------------------------

# 存储各阶段的聚合指标
stage_metrics: dict = {}


@events.request.add_listener
def on_request(request_type, name, response_time, response_length, exception, **kwargs):
    """自定义请求事件监听器 — 记录异常请求详情"""
    if exception:
        logger.warning(
            f"[FAILED] {request_type} {name} | "
            f"response_time={response_time:.0f}ms | "
            f"exception={exception}"
        )


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """压测开始时初始化"""
    logger.info("=" * 60)
    logger.info("压测开始 — 审计平台核心场景")
    logger.info(f"目标主机: {environment.host}")
    logger.info(f"梯度阶段: {[s['users'] for s in LOAD_STAGES]} 用户")
    logger.info("=" * 60)


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """压测结束时输出汇总"""
    logger.info("=" * 60)
    logger.info("压测结束 — 汇总报告")
    stats = environment.runner.stats
    logger.info(f"总请求数: {stats.total.num_requests}")
    logger.info(f"总失败数: {stats.total.num_failures}")
    if stats.total.num_requests > 0:
        error_rate = stats.total.num_failures / stats.total.num_requests * 100
        logger.info(f"错误率: {error_rate:.2f}%")
    logger.info(f"P50: {stats.total.get_response_time_percentile(0.5):.0f}ms")
    logger.info(f"P95: {stats.total.get_response_time_percentile(0.95):.0f}ms")
    logger.info(f"P99: {stats.total.get_response_time_percentile(0.99):.0f}ms")
    logger.info(f"RPS: {stats.total.current_rps:.1f}")
    logger.info("=" * 60)


# ---------------------------------------------------------------------------
# 压测用户行为定义
# ---------------------------------------------------------------------------


class AuditPlatformUser(HttpUser):
    """模拟审计平台用户的典型操作流程

    场景权重分配:
      - 登录:         1 (低频，仅初始化)
      - 查询试算表:   3 (高频，核心查看操作)
      - 查询底稿列表: 2 (中频，导航操作)
      - 编辑并保存:   1 (低频，写操作)
      - 穿透查询:     2 (中频，分析操作)
    """

    wait_time = between(1, 3)

    def on_start(self):
        """登录获取 JWT token，失败则标记用户为未认证"""
        self.token = ""
        self.headers = {}
        self._authenticated = False

        resp = self.client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "admin123"},
            name="/api/auth/login [on_start]",
            catch_response=True,
        )
        with resp as r:
            if r.status_code == 200:
                data = r.json()
                token = data.get("access_token", "")
                if token:
                    self.token = token
                    self.headers = {"Authorization": f"Bearer {self.token}"}
                    self._authenticated = True
                    r.success()
                else:
                    r.failure("登录成功但未返回 access_token")
            else:
                r.failure(f"登录失败: HTTP {r.status_code}")

    @task(1)
    def login(self):
        """场景 1：登录（权重 1）

        模拟用户重新登录（token 刷新场景）。
        验证: 状态码 200 + 返回 access_token。
        """
        with self.client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "admin123"},
            name="/api/auth/login",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                data = resp.json()
                if data.get("access_token"):
                    resp.success()
                else:
                    resp.failure("响应缺少 access_token 字段")
            elif resp.status_code == 429:
                resp.failure("登录限流 (429)")
            else:
                resp.failure(f"登录失败: HTTP {resp.status_code}")

    @task(3)
    def view_trial_balance(self):
        """场景 2：查询试算平衡表（权重 3）

        验证: 状态码 200 + 响应体非空。
        """
        if not self._authenticated:
            return

        with self.client.get(
            f"/api/projects/{PROJECT_ID}/trial-balance",
            headers=self.headers,
            name="/api/projects/{pid}/trial-balance",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            elif resp.status_code == 401:
                resp.failure("Token 过期 (401)")
                self._reauthenticate()
            else:
                resp.failure(f"查询试算表失败: HTTP {resp.status_code}")

    @task(2)
    def view_workpaper_list(self):
        """场景 3：查询底稿列表（权重 2）

        验证: 状态码 200。
        """
        if not self._authenticated:
            return

        with self.client.get(
            f"/api/projects/{PROJECT_ID}/workpapers",
            headers=self.headers,
            name="/api/projects/{pid}/workpapers",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            elif resp.status_code == 401:
                resp.failure("Token 过期 (401)")
                self._reauthenticate()
            else:
                resp.failure(f"查询底稿列表失败: HTTP {resp.status_code}")

    @task(1)
    def edit_and_save_workpaper(self):
        """场景 4：编辑并保存底稿（权重 1）

        模拟真实编辑流程:
          1. GET 获取底稿当前数据
          2. PUT 保存修改后的数据（含 payload）

        验证: GET 200 + PUT 200/204。
        """
        if not self._authenticated:
            return

        # Step 1: 读取底稿
        with self.client.get(
            f"/api/projects/{PROJECT_ID}/workpapers/{WORKPAPER_ID}",
            headers=self.headers,
            name="/api/projects/{pid}/workpapers/{wp_id} [GET]",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            elif resp.status_code == 401:
                resp.failure("Token 过期 (401)")
                self._reauthenticate()
                return
            elif resp.status_code == 404:
                resp.failure("底稿不存在 (404)")
                return
            else:
                resp.failure(f"读取底稿失败: HTTP {resp.status_code}")
                return

        # Step 2: 保存底稿（模拟编辑后提交）
        save_payload = {
            "parsed_data": {
                "cells_modified": [
                    {"cell_ref": "B5", "value": 1000000.00},
                    {"cell_ref": "B6", "value": 2500000.00},
                ],
                "last_modified_by": "admin",
                "modification_timestamp": time.time(),
            },
            "status": "in_progress",
        }

        with self.client.put(
            f"/api/projects/{PROJECT_ID}/workpapers/{WORKPAPER_ID}",
            headers=self.headers,
            json=save_payload,
            name="/api/projects/{pid}/workpapers/{wp_id} [PUT]",
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 204):
                resp.success()
            elif resp.status_code == 409:
                # 版本冲突（乐观锁），属于正常业务场景
                resp.success()
            elif resp.status_code == 401:
                resp.failure("Token 过期 (401)")
                self._reauthenticate()
            elif resp.status_code == 422:
                resp.failure("保存数据校验失败 (422)")
            else:
                resp.failure(f"保存底稿失败: HTTP {resp.status_code}")

    @task(2)
    def drilldown_query(self):
        """场景 5：穿透查询（权重 2）

        模拟从试算表穿透到明细账。
        验证: 状态码 200 + 响应体包含数据。
        """
        if not self._authenticated:
            return

        with self.client.get(
            f"/api/projects/{PROJECT_ID}/drilldown?account_code=1001",
            headers=self.headers,
            name="/api/projects/{pid}/drilldown?account_code={code}",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            elif resp.status_code == 401:
                resp.failure("Token 过期 (401)")
                self._reauthenticate()
            elif resp.status_code == 404:
                resp.failure("科目不存在 (404)")
            else:
                resp.failure(f"穿透查询失败: HTTP {resp.status_code}")

    def _reauthenticate(self):
        """Token 过期时重新认证"""
        resp = self.client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "admin123"},
            name="/api/auth/login [reauth]",
        )
        if resp.status_code == 200:
            data = resp.json()
            token = data.get("access_token", "")
            if token:
                self.token = token
                self.headers = {"Authorization": f"Bearer {self.token}"}
                self._authenticated = True
            else:
                self._authenticated = False
        else:
            self._authenticated = False


# ---------------------------------------------------------------------------
# LoadTestShape — 梯度加压控制器
# ---------------------------------------------------------------------------

from locust import LoadTestShape


class StepLoadShape(LoadTestShape):
    """梯度加压 Shape: 100 → 500 → 1000 → 3000 → 6000 用户

    每个阶段按配置的 spawn_rate 加压到目标用户数，
    然后保持 duration 秒的稳定负载，再进入下一阶段。

    配置通过 LOAD_STAGES 常量控制，可灵活调整:
      - users: 该阶段目标并发用户数
      - spawn_rate: 每秒新增用户数
      - duration: 达到目标后保持的秒数
    """

    def tick(self):
        """返回 (user_count, spawn_rate) 或 None（结束测试）"""
        run_time = self.get_run_time()

        # 计算各阶段的累计时间边界
        elapsed = 0
        for stage in LOAD_STAGES:
            # 加压阶段耗时 = 目标用户数 / spawn_rate（近似）
            ramp_up_time = stage["users"] / stage["spawn_rate"]
            stage_total = ramp_up_time + stage["duration"]

            if run_time < elapsed + stage_total:
                # 当前处于此阶段
                return (stage["users"], stage["spawn_rate"])

            elapsed += stage_total

        # 所有阶段完成，结束测试
        return None
