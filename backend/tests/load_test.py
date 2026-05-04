"""
压力测试脚本 — 使用 Locust 模拟并发用户

运行方式：
  pip install locust
  locust -f backend/tests/load_test.py --host http://localhost:9980

Web UI 默认在 http://localhost:8089

目标：验证 6000 并发用户下的系统表现
"""

import json
import random

from locust import HttpUser, between, task, tag


class AuditPlatformUser(HttpUser):
    """模拟审计平台用户的典型操作流程"""

    wait_time = between(1, 3)  # 每次操作间隔 1-3 秒

    token: str = ""
    project_id: str = ""

    def on_start(self):
        """登录获取 token"""
        resp = self.client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "admin123"},
            name="/api/auth/login",
        )
        if resp.status_code == 200:
            data = resp.json()
            # 兼容 ResponseWrapperMiddleware 包装
            payload = data.get("data", data) if isinstance(data, dict) else data
            self.token = payload.get("access_token", "")
        else:
            self.token = ""

    @property
    def auth_headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    # ── 高频读操作 ──────────────────────────────────────────

    @tag("read", "project")
    @task(10)
    def list_projects(self):
        """列出项目（最高频操作）"""
        self.client.get(
            "/api/projects/",
            headers=self.auth_headers,
            name="/api/projects/",
        )

    @tag("read", "trial_balance")
    @task(8)
    def get_trial_balance(self):
        """获取试算平衡表"""
        if not self.project_id:
            self._pick_project()
        if self.project_id:
            self.client.get(
                f"/api/trial-balance/{self.project_id}",
                headers=self.auth_headers,
                params={"year": 2024},
                name="/api/trial-balance/[project_id]",
            )

    @tag("read", "report")
    @task(6)
    def get_report(self):
        """获取财务报表"""
        if not self.project_id:
            self._pick_project()
        if self.project_id:
            report_type = random.choice([
                "balance_sheet", "income_statement",
                "cash_flow_statement", "equity_statement",
            ])
            self.client.get(
                f"/api/reports/{self.project_id}/{report_type}",
                headers=self.auth_headers,
                params={"year": 2024},
                name="/api/reports/[project_id]/[type]",
            )

    @tag("read", "workpaper")
    @task(5)
    def list_workpapers(self):
        """列出底稿"""
        if not self.project_id:
            self._pick_project()
        if self.project_id:
            self.client.get(
                f"/api/workpapers/{self.project_id}",
                headers=self.auth_headers,
                name="/api/workpapers/[project_id]",
            )

    @tag("read", "adjustment")
    @task(4)
    def list_adjustments(self):
        """列出调整分录"""
        if not self.project_id:
            self._pick_project()
        if self.project_id:
            self.client.get(
                f"/api/adjustments/{self.project_id}",
                headers=self.auth_headers,
                params={"year": 2024},
                name="/api/adjustments/[project_id]",
            )

    @tag("read", "dict")
    @task(3)
    def get_dicts(self):
        """获取字典数据"""
        self.client.get(
            "/api/system/dicts",
            headers=self.auth_headers,
            name="/api/system/dicts",
        )

    # ── 中频写操作 ──────────────────────────────────────────

    @tag("write", "adjustment")
    @task(2)
    def create_adjustment(self):
        """创建调整分录"""
        if not self.project_id:
            self._pick_project()
        if self.project_id:
            self.client.post(
                f"/api/adjustments/{self.project_id}",
                headers=self.auth_headers,
                json={
                    "year": 2024,
                    "description": f"压力测试分录-{random.randint(1, 10000)}",
                    "entry_type": "reclassification",
                    "lines": [
                        {
                            "account_code": "6001",
                            "account_name": "主营业务收入",
                            "debit_amount": 1000,
                            "credit_amount": 0,
                        },
                        {
                            "account_code": "6051",
                            "account_name": "其他业务收入",
                            "debit_amount": 0,
                            "credit_amount": 1000,
                        },
                    ],
                },
                name="/api/adjustments/[project_id] [POST]",
            )

    @tag("write", "report")
    @task(1)
    def recalculate_report(self):
        """触发报表重算"""
        if not self.project_id:
            self._pick_project()
        if self.project_id:
            self.client.post(
                f"/api/reports/{self.project_id}/recalculate",
                headers=self.auth_headers,
                json={"year": 2024},
                name="/api/reports/[project_id]/recalculate [POST]",
            )

    # ── SSE 长连接 ──────────────────────────────────────────

    @tag("sse")
    @task(1)
    def sse_connect(self):
        """模拟 SSE 连接（短暂连接后断开）"""
        if self.project_id:
            with self.client.get(
                f"/api/events/{self.project_id}",
                headers=self.auth_headers,
                stream=True,
                timeout=3,
                name="/api/events/[project_id] [SSE]",
                catch_response=True,
            ) as resp:
                resp.success()

    # ── 辅助方法 ────────────────────────────────────────────

    def _pick_project(self):
        """从项目列表中随机选一个项目"""
        resp = self.client.get(
            "/api/projects/",
            headers=self.auth_headers,
            name="/api/projects/ [pick]",
        )
        if resp.status_code == 200:
            data = resp.json()
            items = data.get("data", data) if isinstance(data, dict) else data
            if isinstance(items, list) and items:
                self.project_id = items[0].get("id", "")
            elif isinstance(items, dict) and "rows" in items:
                rows = items["rows"]
                if rows:
                    self.project_id = rows[0].get("id", "")
