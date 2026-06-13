"""编辑锁 v2 全链路 E2E 测试 — 打真实后端 localhost:9980

运行方式:
    .venv/Scripts/python.exe -m pytest backend/tests/e2e/test_editing_lock_e2e.py -v --tb=short

前置条件:
    - 后端运行在 localhost:9980（start-dev.bat）
    - DB 有 admin/admin123 测试用户
    - DB 有至少一条 workpaper 记录（resource_id 取已有底稿 UUID）

验证场景:
    1. 登录 → acquire workpaper 锁 → 200 + locked=False
    2. heartbeat 续期 → refreshed=True
    3. release 释放 → released=True
    4. force-acquire 强抢 → 新锁创建 + previous_holder_id

Feature: editing-lock-v1-v2-consolidation, Task 7
Requirements: 4.4, 6.1, 6.2
"""

from __future__ import annotations

import httpx
import pytest

BASE_URL = "http://localhost:9980"
TEST_USER = "admin"
TEST_PASS = "admin123"


# ---------------------------------------------------------------------------
# 后端探活 — 不可达则整文件跳过
# ---------------------------------------------------------------------------
def _backend_reachable() -> bool:
    try:
        r = httpx.get(f"{BASE_URL}/api/health", timeout=3, trust_env=False)
        return r.status_code < 500
    except Exception:
        return False


pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        not _backend_reachable(),
        reason=f"Backend not running at {BASE_URL} — skip E2E editing lock tests",
    ),
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def admin_session() -> httpx.Client:
    """登录 admin 获取 JWT，返回带认证的同步 httpx 客户端。"""
    c = httpx.Client(base_url=BASE_URL, timeout=30, trust_env=False)
    resp = c.post("/api/auth/login", json={"username": TEST_USER, "password": TEST_PASS})
    assert resp.status_code == 200, f"Login failed: {resp.status_code} {resp.text[:200]}"

    data = resp.json()
    # ResponseWrapperMiddleware 可能将 payload 包裹在 data.data 中
    payload = data.get("data", data)
    token = payload.get("access_token") or payload.get("token")
    assert token, f"No access_token in login response: {data}"
    c.headers["Authorization"] = f"Bearer {token}"
    yield c
    c.close()


@pytest.fixture(scope="module")
def workpaper_id(admin_session: httpx.Client) -> str:
    """获取一个可用的底稿 UUID 用于锁测试。

    策略优先级:
    1. 查活跃锁列表获取已有 workpaper resource_id
    2. 查项目底稿列表取第一个
    3. 使用固定 fallback UUID（可能 404，但不阻塞测试结构验证）
    """
    # 尝试从活跃锁列表获取
    resp = admin_session.get("/api/editing-locks/active", params={"resource_type": "workpaper"})
    if resp.status_code == 200:
        body = resp.json()
        payload = body.get("data", body)
        locks = payload.get("locks", [])
        if locks:
            return locks[0].get("resource_id", locks[0].get("id", ""))

    # 尝试从项目列表中找一个底稿
    resp = admin_session.get("/api/projects")
    if resp.status_code == 200:
        body = resp.json()
        projects = body.get("data", body) if isinstance(body, dict) else body
        if isinstance(projects, list) and projects:
            pid = projects[0].get("id") or projects[0].get("project_id")
            if pid:
                wp_resp = admin_session.get(f"/api/projects/{pid}/working-papers")
                if wp_resp.status_code == 200:
                    wp_body = wp_resp.json()
                    wps = wp_body.get("data", wp_body) if isinstance(wp_body, dict) else wp_body
                    if isinstance(wps, list) and wps:
                        return str(wps[0].get("id") or wps[0].get("wp_id", ""))

    # Fallback：使用一个合成 UUID（测试仍可运行，acquire 会创建新锁）
    return "e2e-test-00000000-0000-0000-0000-000000000001"


# ---------------------------------------------------------------------------
# 测试场景
# ---------------------------------------------------------------------------
class TestEditingLockLifecycle:
    """编辑锁完整生命周期：acquire → heartbeat → release"""

    def test_acquire_lock(self, admin_session: httpx.Client, workpaper_id: str):
        """场景 1：acquire 获取锁 → 200 + locked=False"""
        resp = admin_session.post(f"/api/editing-locks/workpaper/{workpaper_id}")
        # 可能 200（新锁或同人续期）
        assert resp.status_code == 200, (
            f"Acquire failed: {resp.status_code} {resp.text[:300]}"
        )
        body = resp.json()
        payload = body.get("data", body)
        # locked=False 表示成功获取（非冲突）
        assert payload.get("locked") is False or payload.get("locked") is None, (
            f"Expected locked=False, got: {payload}"
        )
        assert "lock_id" in payload, f"Missing lock_id in response: {payload}"

    def test_heartbeat(self, admin_session: httpx.Client, workpaper_id: str):
        """场景 2：heartbeat 续期 → refreshed=True"""
        resp = admin_session.patch(
            f"/api/editing-locks/workpaper/{workpaper_id}/heartbeat"
        )
        assert resp.status_code == 200, (
            f"Heartbeat failed: {resp.status_code} {resp.text[:300]}"
        )
        body = resp.json()
        payload = body.get("data", body)
        assert payload.get("refreshed") is True, (
            f"Expected refreshed=True, got: {payload}"
        )

    def test_release(self, admin_session: httpx.Client, workpaper_id: str):
        """场景 3：release 释放锁 → released=True"""
        resp = admin_session.delete(f"/api/editing-locks/workpaper/{workpaper_id}")
        assert resp.status_code == 200, (
            f"Release failed: {resp.status_code} {resp.text[:300]}"
        )
        body = resp.json()
        payload = body.get("data", body)
        assert payload.get("released") is True, (
            f"Expected released=True, got: {payload}"
        )


class TestEditingLockForceAcquire:
    """强抢锁场景：用户 A 持锁 → 用户 B（同为 admin）强抢 → previous_holder_id 返回

    注：真实双用户测试需 DB 有第二个用户。此处用同一 admin 验证 force 端点流程完整性。
    """

    def test_force_acquire_flow(self, admin_session: httpx.Client, workpaper_id: str):
        """场景 4：acquire → force-acquire → 验证 previous_holder_id"""
        # Step 1: 先 acquire 建锁
        resp = admin_session.post(f"/api/editing-locks/workpaper/{workpaper_id}")
        assert resp.status_code == 200, (
            f"Initial acquire failed: {resp.status_code} {resp.text[:300]}"
        )
        body = resp.json()
        payload = body.get("data", body)
        original_lock_id = payload.get("lock_id")

        # Step 2: force-acquire 强抢（同用户强抢自己，验证端点可用）
        resp = admin_session.post(
            f"/api/editing-locks/workpaper/{workpaper_id}/force"
        )
        assert resp.status_code == 200, (
            f"Force acquire failed: {resp.status_code} {resp.text[:300]}"
        )
        body = resp.json()
        payload = body.get("data", body)

        # 验证返回包含 previous_holder_id
        assert "previous_holder_id" in payload, (
            f"Missing previous_holder_id in force response: {payload}"
        )
        # 验证新锁 ID 不同于原锁
        new_lock_id = payload.get("lock_id")
        assert new_lock_id, f"Missing lock_id in force response: {payload}"
        if original_lock_id:
            assert new_lock_id != original_lock_id, (
                "Force-acquire should create a new lock, "
                f"but got same lock_id: {new_lock_id}"
            )

        # Step 3: 清理 — release 新锁
        admin_session.delete(f"/api/editing-locks/workpaper/{workpaper_id}")


class TestEditingLockActiveListing:
    """活跃锁列表端点验证"""

    def test_active_locks_endpoint(self, admin_session: httpx.Client, workpaper_id: str):
        """GET /api/editing-locks/active?resource_type=workpaper 可达"""
        # 先创建一个锁确保列表非空
        admin_session.post(f"/api/editing-locks/workpaper/{workpaper_id}")

        resp = admin_session.get(
            "/api/editing-locks/active",
            params={"resource_type": "workpaper"},
        )
        assert resp.status_code == 200, (
            f"Active locks listing failed: {resp.status_code} {resp.text[:300]}"
        )
        body = resp.json()
        payload = body.get("data", body)
        assert "locks" in payload, f"Missing 'locks' key: {payload}"
        assert isinstance(payload["locks"], list)

        # 清理
        admin_session.delete(f"/api/editing-locks/workpaper/{workpaper_id}")
