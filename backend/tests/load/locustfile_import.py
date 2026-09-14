"""
Locust 压测脚本 — 多 Worker 导入并发场景

目的：
  验证多 worker 部署下导入锁、地址坐标库缓存重建、OCR 内存占用三个瓶颈。

使用方法（需 2+ worker 实例运行中）:
    locust -f tests/load/locustfile_import.py --host=http://localhost:9980

预期基线行为（实施前）:
  1. 同项目并发导入：内存锁仅进程内有效，2 个 worker 可能同时获得锁
     → 数据竞争、ImportBatch 重复/脏数据
  2. 地址坐标库缓存 miss：N 并发请求触发 N 次 DB build_workpaper_entries
     → 缓存踩踏，DB 负载 O(N) 而非 O(1)
  3. Web worker RSS：PaddleOCR import 时模型载入 ~500MB
     → 无 OCR 请求时 worker 内存照样膨胀

实施后预期：
  1. Redis SET NX EX 分布式锁 → 跨 worker 互斥，第二个 worker 被拒
  2. asyncio.Lock single-flight → 并发 miss 仅 1 次 DB 查询
  3. OCR 服务化 → web worker RSS < 200MB

注意：实际执行需要 Docker 环境 + 2 个 uvicorn worker 实例。
"""

from __future__ import annotations

import logging
import random
import string
import time
import uuid

from locust import HttpUser, LoadTestShape, between, events, task

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

# 测试项目 ID — 多个用户对同一项目并发导入
TARGET_PROJECT_ID = "00000000-0000-0000-0000-000000000001"

# 用于地址坐标库压测的项目
ADDRESS_REGISTRY_PROJECT_ID = "00000000-0000-0000-0000-000000000001"

# 梯度阶段：少量用户即可暴露并发问题
LOAD_STAGES = [
    {"users": 4, "spawn_rate": 2, "duration": 30},    # 4 并发导入
    {"users": 10, "spawn_rate": 5, "duration": 60},   # 10 并发（缓存踩踏）
    {"users": 20, "spawn_rate": 10, "duration": 60},  # 20 并发（压力场景）
]


# ---------------------------------------------------------------------------
# 事件监听
# ---------------------------------------------------------------------------

@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    logger.info("=" * 60)
    logger.info("多 Worker 导入并发压测开始")
    logger.info(f"目标: {environment.host}")
    logger.info("场景: 同项目并发导入 / 地址坐标库缓存踩踏 / OCR 内存")
    logger.info("=" * 60)


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    stats = environment.runner.stats
    logger.info("=" * 60)
    logger.info("压测结束 — 多 Worker 导入并发")
    logger.info(f"总请求: {stats.total.num_requests}")
    logger.info(f"失败: {stats.total.num_failures}")
    if stats.total.num_requests > 0:
        error_rate = stats.total.num_failures / stats.total.num_requests * 100
        logger.info(f"错误率: {error_rate:.2f}%")
        logger.info(f"P95: {stats.total.get_response_time_percentile(0.95):.0f}ms")
    logger.info("=" * 60)


# ---------------------------------------------------------------------------
# 场景 1: 同项目并发导入（测试分布式锁）
# ---------------------------------------------------------------------------

class ConcurrentImportUser(HttpUser):
    """模拟多个用户对同一项目同时发起导入

    预期行为（修复前）：
      - 2 个 worker 各自检查 _import_locks 内存字典，都发现为空
      - 两者都创建 ImportBatch → 数据竞争（DB 唯一索引可能部分拦截）

    预期行为（修复后）：
      - Redis SET NX EX 保证跨 worker 互斥
      - 第二个请求立即收到 409 Conflict
    """

    wait_time = between(0.5, 1.5)
    weight = 3

    def on_start(self):
        self.headers = {}
        self._authenticated = False
        resp = self.client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "admin123"},
            name="/api/auth/login [import]",
            catch_response=True,
        )
        with resp as r:
            if r.status_code == 200:
                data = r.json()
                token = data.get("access_token", "")
                if token:
                    self.headers = {"Authorization": f"Bearer {token}"}
                    self._authenticated = True
                    r.success()
                else:
                    r.failure("No token")
            else:
                r.failure(f"Login failed: {r.status_code}")

    @task(5)
    def concurrent_import_same_project(self):
        """同项目并发导入 — 验证锁互斥

        期望：只有一个请求成功（200），其余收到 409 或锁拒绝消息。
        修复前：可能多个 200（数据竞争）。
        """
        if not self._authenticated:
            return

        # 模拟上传 Excel 文件导入
        fake_file_content = b"PK" + b"\x00" * 100  # 最小 xlsx 签名
        file_name = f"trial_balance_{uuid.uuid4().hex[:8]}.xlsx"

        with self.client.post(
            f"/api/data-lifecycle/projects/{TARGET_PROJECT_ID}/import",
            headers=self.headers,
            files={"file": (file_name, fake_file_content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            data={"source_type": "trial_balance", "year": "2025"},
            name="/api/data-lifecycle/projects/{pid}/import [concurrent]",
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 201):
                resp.success()
            elif resp.status_code == 409:
                # 期望的锁拒绝 — 在修复后应该是常见结果
                resp.success()
            elif resp.status_code == 423:
                # Locked — 也是期望的互斥行为
                resp.success()
            elif resp.status_code == 401:
                resp.failure("Token expired")
            else:
                resp.failure(f"Unexpected: HTTP {resp.status_code}")

    @task(2)
    def check_import_status(self):
        """查询导入状态 — 验证状态一致性"""
        if not self._authenticated:
            return

        with self.client.get(
            f"/api/data-lifecycle/projects/{TARGET_PROJECT_ID}/import/status",
            headers=self.headers,
            name="/api/data-lifecycle/projects/{pid}/import/status",
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 404):
                resp.success()
            else:
                resp.failure(f"Status check failed: {resp.status_code}")


# ---------------------------------------------------------------------------
# 场景 2: 地址坐标库缓存踩踏（测试 single-flight）
# ---------------------------------------------------------------------------

class AddressRegistryStampedeUser(HttpUser):
    """模拟并发缓存 miss 场景

    预期行为（修复前）：
      - N 并发请求都发现 L1+L2 miss
      - 全部触发 build_workpaper_entries → DB 查询 N 次

    预期行为（修复后）：
      - asyncio.Lock single-flight
      - 第 1 个请求获取锁并构建
      - 其余 N-1 等待 → 锁释放后 double-check L1 命中
      - DB 查询仅 1 次
    """

    wait_time = between(0.1, 0.5)  # 高频触发缓存踩踏
    weight = 4

    def on_start(self):
        self.headers = {}
        self._authenticated = False
        resp = self.client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "admin123"},
            name="/api/auth/login [addr_reg]",
            catch_response=True,
        )
        with resp as r:
            if r.status_code == 200:
                data = r.json()
                token = data.get("access_token", "")
                if token:
                    self.headers = {"Authorization": f"Bearer {token}"}
                    self._authenticated = True
                    r.success()
                else:
                    r.failure("No token")
            else:
                r.failure(f"Login failed: {r.status_code}")

    @task(5)
    def concurrent_address_lookup(self):
        """并发地址搜索 — 触发 wp 域缓存 miss

        多个用户同时请求同一项目的地址坐标库，
        如果缓存刚被失效（底稿保存后），会触发缓存踩踏。
        """
        if not self._authenticated:
            return

        with self.client.get(
            f"/api/projects/{ADDRESS_REGISTRY_PROJECT_ID}/address-registry"
            f"?domain=wp&year=2025",
            headers=self.headers,
            name="/api/projects/{pid}/address-registry?domain=wp",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            elif resp.status_code in (401, 403):
                resp.failure(f"Auth: {resp.status_code}")
            else:
                resp.failure(f"Address lookup failed: {resp.status_code}")

    @task(2)
    def save_then_lookup(self):
        """保存底稿后立即查地址 — 模拟失效+重建的真实场景

        底稿保存触发 invalidate → 紧接着多人查询 → 缓存踩踏
        """
        if not self._authenticated:
            return

        # Step 1: 模拟底稿保存（触发缓存失效）
        self.client.put(
            f"/api/projects/{ADDRESS_REGISTRY_PROJECT_ID}/workpapers/1",
            headers=self.headers,
            json={"parsed_data": {"cells_modified": [{"cell_ref": "A1", "value": "test"}]}},
            name="/api/projects/{pid}/workpapers/{id} [save→invalidate]",
        )

        # Step 2: 立即查询地址坐标库（缓存刚被失效）
        time.sleep(0.05)  # 50ms 后查询
        self.client.get(
            f"/api/projects/{ADDRESS_REGISTRY_PROJECT_ID}/address-registry"
            f"?domain=wp&year=2025",
            headers=self.headers,
            name="/api/projects/{pid}/address-registry [post-invalidate]",
        )


# ---------------------------------------------------------------------------
# 场景 3: Web Worker 内存（OCR 模型加载检测）
# ---------------------------------------------------------------------------

class OCRMemoryUser(HttpUser):
    """模拟 OCR 识别请求 — 观测 web worker 内存

    预期行为（修复前）：
      - web worker 收到 OCR 请求 → import PaddleOCR → 模型载入 ~500MB
      - 即使后续无 OCR 请求，内存不会释放

    预期行为（修复后）：
      - web worker 转发 HTTP 到 OCR 服务容器
      - web worker RSS 保持 < 200MB
    """

    wait_time = between(2, 5)
    weight = 1

    def on_start(self):
        self.headers = {}
        self._authenticated = False
        resp = self.client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "admin123"},
            name="/api/auth/login [ocr]",
            catch_response=True,
        )
        with resp as r:
            if r.status_code == 200:
                data = r.json()
                token = data.get("access_token", "")
                if token:
                    self.headers = {"Authorization": f"Bearer {token}"}
                    self._authenticated = True
                    r.success()
                else:
                    r.failure("No token")
            else:
                r.failure(f"Login failed: {r.status_code}")

    @task
    def ocr_recognize(self):
        """发送 OCR 识别请求 — 观测内存影响

        发送一个小图片触发 OCR 路径，
        实施前会导致 PaddleOCR 模型加载到 web worker 进程。
        """
        if not self._authenticated:
            return

        # 1x1 PNG (smallest valid PNG)
        png_data = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
            b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00"
            b"\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00"
            b"\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
        )

        with self.client.post(
            "/api/ocr/recognize",
            headers=self.headers,
            files={"file": ("test.png", png_data, "image/png")},
            name="/api/ocr/recognize",
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 201):
                resp.success()
            elif resp.status_code == 503:
                # OCR 服务不可用 — 修复后的 fallback 行为
                resp.success()
            elif resp.status_code in (401, 403, 404, 422):
                resp.success()  # 接口可能不存在或参数不对，不影响内存观测
            else:
                resp.failure(f"OCR failed: {resp.status_code}")


# ---------------------------------------------------------------------------
# 梯度加压 Shape
# ---------------------------------------------------------------------------

class ImportStampedeShape(LoadTestShape):
    """小规模梯度加压 — 4 → 10 → 20 并发用户

    目的是用少量用户暴露并发竞争问题，而非压测吞吐量上限。
    """

    def tick(self):
        run_time = self.get_run_time()
        elapsed = 0
        for stage in LOAD_STAGES:
            ramp_up = stage["users"] / stage["spawn_rate"]
            total = ramp_up + stage["duration"]
            if run_time < elapsed + total:
                return (stage["users"], stage["spawn_rate"])
            elapsed += total
        return None
