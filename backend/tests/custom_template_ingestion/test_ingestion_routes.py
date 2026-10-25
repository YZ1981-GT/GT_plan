"""Task 4 路由层守卫：三入口 multipart 摄取端点真的可达且行为正确。

Spec: custom-workpaper-template-ingestion-and-sync-closure
Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 3.1, 3.2, 3.6, 3.7

## 为什么需要这一层（不只是 service 单测）

service 单测全绿只证明 `PrivateQuarantine` 逻辑对；但 2026-09-08 实测发现
`backend/app/routers/custom_template_ingestion.py` 已完整实现而 **从未被
`include_router`** —— app 启动日志直接报「未注册的 router 模块（共 1 个）:
['app.routers.custom_template_ingestion']」，`/api/custom-template-ingestion/*`
零条路由。这就是 memory 里「假绿三源」第①种的**最贵变体**：代码存在、单测绿、
Volar/pytest/get_diagnostics 四层全绿，但用户点上传是 404。

本文件的判据一律落到**真实 FastAPI 路由表 + HTTP 语义**，不看字符串存在：

* `test_ingestion_router_is_registered` —— 直接从 `app.main.app` 读路由表，
  断言四条路径都在。若有人把 import 行删掉，这条立即红。
* `test_ingest_multipart_accepts_real_bytes` —— 真实 multipart 上传
  （``httpx.AsyncClient`` + ``files=``），断言落库 sha256 与状态。
* `test_ingest_rejects_non_excel_extension` —— 415 + 结构化 reason。
* `test_actions_endpoint_exposes_stable_action_ids` —— Requirement 1.4，
  UI 不得靠中文按钮文字区分入口。

🔴 不 mock `PrivateQuarantine`：注入临时 ``STORAGE_ROOT`` 让路由走真实隔离区，
否则测的是 mock 而不是接线。
"""
from __future__ import annotations

import hashlib
import io
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import custom_template_ingestion as ingestion_module
from app.routers.custom_template_ingestion import router as ingestion_router
from app.services.custom_template_ingestion.actions import (
    BATCH_CREATE_BLANK,
    INGEST_EXCEL_TEMPLATE,
    MAINTAIN_METADATA,
    ACTION_IDS,
)
from app.services.custom_template_ingestion.authorization import (
    Capability,
    is_permitted,
    role_of,
)


#: OOXML 最小合法载荷：ZIP magic + 16 KiB 填充。真实解析留给 Task 5/6。
ZIP_HEADER = b"PK\x03\x04" + b"\x00" * 16


class FakeUser:
    """认证用户替身。``role`` 是唯一真源（`users.role`）。"""

    def __init__(self, role: str = "manager", user_id: Any = 1, office_code: str = "BJ1") -> None:
        self.role = role
        self.id = user_id
        self.office_code = office_code
        self.user_id = user_id


@pytest.fixture()
def isolated_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """把 quarantine 根切到 tmp dir，避免测试污染真实 storage。"""
    root = tmp_path / "storage" / "custom_template_quarantine"
    monkeypatch.setattr(
        ingestion_module, "QUARANTINE_ROOT", root,
    )
    return root


@pytest.fixture()
def client(isolated_storage: Path) -> TestClient:
    """带鉴权覆盖的测试客户端。"""
    app = FastAPI()
    app.include_router(ingestion_router)
    app.dependency_overrides[
        ingestion_module.get_current_user
    ] = lambda: FakeUser()
    return TestClient(app)


# ─────────────────────────────────────────────────────────────────────────────
# Requirement 1.4 —— 路由真的被注册（假绿防线）
# ─────────────────────────────────────────────────────────────────────────────


def test_ingestion_router_is_registered_in_main_app() -> None:
    """🔴 从**真实** app 路由表断言四条路径存在。

    这是本 spec 最贵的一条守卫：service 单测全绿而 router 未注册时，只有这条
    能红。判据是路由路径集合的**成员检查**，不是 grep 字符串。
    """
    from app.main import app

    paths = {route.path for route in app.routes if getattr(route, "path", "")}
    expected = {
        "/api/custom-template-ingestion/actions",
        "/api/custom-template-ingestion/ingest",
        "/api/custom-template-ingestion/artifacts/{artifact_id}",
        "/api/custom-template-ingestion/quota",
    }
    missing = expected - paths
    assert not missing, f"摄取路由未注册（假绿！）: {sorted(missing)}"


def test_three_actions_have_distinct_ids_and_binary_semantics(client: TestClient) -> None:
    """三条 action id 互斥，且只有摄取链接收二进制（Requirement 1.1–1.4）。"""
    resp = client.get("/api/custom-template-ingestion/actions")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    listed = {a["actionId"] for a in body["actions"]}
    assert listed <= set(ACTION_IDS)
    assert listed, "无可用 action（权限过滤把全部入口隐藏了）"
    # 摄取链必须被标为 consumes_binary=True，其余两条为 False
    binary_flags = {a["actionId"]: a["consumesBinary"] for a in body["actions"]}
    if INGEST_EXCEL_TEMPLATE in binary_flags:
        assert binary_flags[INGEST_EXCEL_TEMPLATE] is True
    for other in (BATCH_CREATE_BLANK, MAINTAIN_METADATA):
        if other in binary_flags:
            assert binary_flags[other] is False


# ─────────────────────────────────────────────────────────────────────────────
# Requirement 1.3 / 3.1 —— 真实 multipart 摄取
# ─────────────────────────────────────────────────────────────────────────────


def test_ingest_multipart_accepts_real_bytes(client: TestClient) -> None:
    """真实 multipart 字节流 → QUARANTINED，sha256 可复现。"""
    payload = ZIP_HEADER + b"\x00" * 2048
    resp = client.post(
        "/api/custom-template-ingestion/ingest",
        files={"file": ("客户报表.xlsx", io.BytesIO(payload), "application/octet-stream")},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["state"] == "QUARANTINED"
    assert body["sizeBytes"] == len(payload)
    assert body["sha256"] == hashlib.sha256(payload).hexdigest()
    assert body["actionId"] == INGEST_EXCEL_TEMPLATE
    assert body["displayName"] == "客户报表.xlsx"
    # 成功文案必须只描述真实副作用（Requirement 1.6）
    assert "未发布" in body["message"]
    assert "未生成项目底稿" in body["message"]
    # 不得泄露 storage 绝对路径
    serialized = str(body)
    assert "C:\\" not in serialized and "D:\\" not in serialized


def test_ingest_returns_structured_rejection_for_non_excel(client: TestClient) -> None:
    """非白名单扩展名 → 415 + 结构化 reason，不落盘。"""
    resp = client.post(
        "/api/custom-template-ingestion/ingest",
        files={"file": ("malware.exe", io.BytesIO(b"MZ\x90\x00"), "application/x-dosexec")},
    )
    assert resp.status_code == 415, resp.text
    detail = resp.json()["detail"]
    assert detail["code"] == "EXTENSION_NOT_ALLOWED"
    # 结构化拒绝不得含文件名正文（Requirement 3.7）
    assert "malware" not in str(detail)


def test_ingest_rejects_non_zip_magic(client: TestClient) -> None:
    """扩展名是 .xlsx 但正文不是 ZIP → 415 + ZIP_MAGIC_MISMATCH。"""
    resp = client.post(
        "/api/custom-template-ingestion/ingest",
        files={"file": ("fake.xlsx", io.BytesIO(b"<html><script>alert(1)</script>"), "application/octet-stream")},
    )
    assert resp.status_code == 415, resp.text
    assert resp.json()["detail"]["code"] == "ZIP_MAGIC_MISMATCH"


def test_ingest_rejects_empty_file(client: TestClient) -> None:
    """零字节 → 415 + EMPTY_FILE（Requirement 3.6：不得 valid=true）。"""
    resp = client.post(
        "/api/custom-template-ingestion/ingest",
        files={"file": ("empty.xlsx", io.BytesIO(b""), "application/octet-stream")},
    )
    assert resp.status_code == 415, resp.text
    assert resp.json()["detail"]["code"] == "EMPTY_FILE"


def test_ingest_without_file_returns_422(client: TestClient) -> None:
    """缺 multipart 文件 → 422（FastAPI 原生校验）。"""
    resp = client.post("/api/custom-template-ingestion/ingest")
    assert resp.status_code == 422


# ─────────────────────────────────────────────────────────────────────────────
# Requirement 2.6 / 16.1 —— 权限前置 + storage 不枚举
# ─────────────────────────────────────────────────────────────────────────────


def test_ingest_enforces_upload_capability(monkeypatch: pytest.MonkeyPatch,
                                           isolated_storage: Path) -> None:
    """无 UPLOAD capability 的角色 → 403，字节不进隔离区。"""
    app = FastAPI()
    app.include_router(ingestion_router)
    app.dependency_overrides[
        ingestion_module.get_current_user
    ] = lambda: FakeUser(role="readonly")
    tc = TestClient(app)
    resp = tc.post(
        "/api/custom-template-ingestion/ingest",
        files={"file": ("a.xlsx", io.BytesIO(ZIP_HEADER + b"\x00" * 100), "application/octet-stream")},
    )
    assert resp.status_code == 403, resp.text
    # 🔴 拒绝后隔离区不得有任何字节文件
    assert not list(isolated_storage.rglob("artifact.bin"))
    assert not is_permitted(role_of(FakeUser(role="readonly")), Capability.UPLOAD)


def test_artifact_lookup_does_not_enumerate_storage(client: TestClient,
                                                    isolated_storage: Path) -> None:
    """查询产物只按 id 精确命中；不存在时 404，绝不返回列表。"""
    # 先上传一个
    payload = ZIP_HEADER + b"\x00" * 512
    created = client.post(
        "/api/custom-template-ingestion/ingest",
        files={"file": ("a.xlsx", io.BytesIO(payload), "application/octet-stream")},
    ).json()

    found = client.get(f"/api/custom-template-ingestion/artifacts/{created['artifactId']}")
    assert found.status_code == 200, found.text
    artifact = found.json()["artifact"]
    assert artifact["artifactId"] == created["artifactId"]
    # 不泄露相对路径
    assert "relativePath" not in artifact
    assert "org" not in artifact.get("relativePath", "")

    missing = client.get("/api/custom-template-ingestion/artifacts/deadbeef")
    assert missing.status_code == 404


def test_quota_endpoint_reports_policy_version(client: TestClient) -> None:
    resp = client.get("/api/custom-template-ingestion/quota")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "limitBytes" in body and body["limitBytes"] > 0
    assert "policyVersion" in body


# ─────────────────────────────────────────────────────────────────────────────
# Requirement 1.5 —— 旧链与新链并列，不得混用
# ─────────────────────────────────────────────────────────────────────────────


def test_legacy_chain_is_parallel_and_marked_for_removal(client: TestClient) -> None:
    """旧 /api/custom-templates 仍在（存量前端依赖），但新链有明确迁移删除门。"""
    from app.main import app

    paths = {route.path for route in app.routes if getattr(route, "path", "")}
    assert "/api/custom-templates" in paths, "旧链应保留以兼容存量前端"
    assert "/api/custom-template-ingestion/ingest" in paths, "新链应已注册"
    # 迁移删除门存在且是合法日期
    deadline = ingestion_module.LEGACY_MIGRATION_DEADLINE
    assert deadline and len(deadline) == 10 and deadline[4] == "-" and deadline[7] == "-"
