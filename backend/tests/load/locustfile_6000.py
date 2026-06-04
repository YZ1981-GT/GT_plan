"""6000 并发压测脚本（pg-pooling-and-load-test spec Task 11）。

覆盖只读热路径：dashboard / 底稿列表 / TB 余额表 / 序时账。
全部 read-only，避免污染真实数据。

用法:
  # 基础压测（100 用户）
  locust -f backend/tests/load/locustfile_6000.py --host http://localhost:9980

  # 阶梯加压到 6000（spawn-rate 100 用户/秒）
  locust -f backend/tests/load/locustfile_6000.py \
      --host http://localhost:9980 \
      --users 6000 --spawn-rate 100 --run-time 5m

  # 分步加压（需 locust-plugins 或 custom shape）:
  #   100 → 1000 → 3000 → 6000，每级持续 2 分钟
  # 使用 LoadTestShape 子类或 --step-users / --step-time:
  #   locust -f locustfile_6000.py --host http://localhost:9980 \
  #       --users 6000 --spawn-rate 100

  # 环境变量:
  #   LOAD_TEST_USER=admin              # 登录用户名（默认 admin）
  #   LOAD_TEST_PASSWORD=admin123       # 登录密码（默认 admin123）
  #   LOAD_TEST_PROJECT_ID=df5b8403...  # 目标项目 ID（首汽租车_2025）

Validates: Requirements 4.1, 4.2, 4.3
"""

from __future__ import annotations

import os

from locust import HttpUser, between, task


# 目标项目 ID（首汽租车_2025，tb 最全）
_PROJECT_ID = os.getenv(
    "LOAD_TEST_PROJECT_ID",
    "df5b8403-0000-0000-0000-000000000000",
)


class AuditUser(HttpUser):
    """模拟审计人员的只读操作热路径。

    权重分配（反映真实使用频率）:
      view_dashboard(5)       — 首页/健康检查（最频繁）
      list_workpapers(3)      — 底稿列表浏览
      query_trial_balance(2)  — TB 余额表查询（中等耗时）
      read_ledger(1)          — 序时账/明细账查询（重查询，82384 行）
    """

    wait_time = between(1, 3)

    def on_start(self) -> None:
        """登录获取 JWT token。"""
        self.token: str | None = None
        username = os.getenv("LOAD_TEST_USER", "admin")
        password = os.getenv("LOAD_TEST_PASSWORD", "admin123")

        with self.client.post(
            "/api/auth/login",
            json={"username": username, "password": password},
            name="login",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                body = resp.json()
                # 解信封：ResponseWrapperMiddleware 包装为 {code, message, data}
                data = body.get("data") if isinstance(body, dict) else body
                if isinstance(data, dict):
                    self.token = data.get("access_token")
                if self.token:
                    resp.success()
                else:
                    resp.failure("login OK but no access_token in response")
            else:
                resp.failure(f"login failed: {resp.status_code}")

    @property
    def _headers(self) -> dict[str, str]:
        """带 Authorization 的请求头。"""
        if self.token:
            return {"Authorization": f"Bearer {self.token}"}
        return {}

    # ------------------------------------------------------------------
    # 只读热路径任务
    # ------------------------------------------------------------------

    @task(5)
    def view_dashboard(self) -> None:
        """健康检查 + 项目概览（最高频）。"""
        self.client.get("/api/health", name="health")
        if _PROJECT_ID:
            self.client.get(
                f"/api/projects/{_PROJECT_ID}",
                headers=self._headers,
                name="project_overview",
            )

    @task(3)
    def list_workpapers(self) -> None:
        """底稿列表（分页第一页）。"""
        if not _PROJECT_ID:
            return
        self.client.get(
            f"/api/projects/{_PROJECT_ID}/working-papers",
            headers=self._headers,
            name="list_workpapers",
        )

    @task(2)
    def query_trial_balance(self) -> None:
        """TB 余额表查询。"""
        if not _PROJECT_ID:
            return
        self.client.get(
            f"/api/projects/{_PROJECT_ID}/trial-balance",
            headers=self._headers,
            name="query_trial_balance",
        )

    @task(1)
    def read_ledger(self) -> None:
        """序时账查询（重查询，生产 82384 行分页返回）。"""
        if not _PROJECT_ID:
            return
        self.client.get(
            f"/api/projects/{_PROJECT_ID}/ledger?page=1&page_size=50",
            headers=self._headers,
            name="read_ledger",
        )
