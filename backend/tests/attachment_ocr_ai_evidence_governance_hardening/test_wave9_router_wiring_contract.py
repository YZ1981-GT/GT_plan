"""Wave 9 thin-router HTTP wiring contract tests.

Spec: attachment-ocr-ai-evidence-governance-hardening
Requirements: R7, R8, R10, R11, R13
Design: §6.2 主要端点 (RAG/AI, Review, Archive/Hold), §7.2 稳定失败类别
UAT: UAT-09/10/11/12/13（这些域此前无 HTTP router → 现经网络契约可达）

本文件是 **DB-free** 契约测试（不连 PostgreSQL）：只证明 Wave 9 新接线的五个域
（AI 门禁 / Citation / Review / Archive / Legal Hold）：

  1. 每条端点都出现在 ``app.openapi()['paths']``（路由已注册、可达、非 404-because-missing）。
  2. 未认证 / 不存在输入时返回 **coded 非-500** 响应（认证前置 → 401/403，非 500 崩溃）。

即 memory 记录的 "service 有但无 HTTP router" 缺口已闭合。功能性（真实 PG 落库、
scope 否决、四条件门禁、离线 hash）由伴生的 PG integration / Playwright UAT 覆盖。
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

import app.main as _main

_PID = str(uuid.uuid4())
_YEAR = 2025
_ID = str(uuid.uuid4())
_BASE = f"/api/projects/{_PID}/years/{_YEAR}/evidence"


# (method, path) — 全部 Wave 9 新端点。path 已填充占位 UUID/年度。
_NEW_ROUTES: list[tuple[str, str]] = [
    # AI 门禁 / FormalOutput
    ("POST", f"{_BASE}/ai/generations"),
    ("GET", f"{_BASE}/ai/generations/{_ID}"),
    ("POST", f"{_BASE}/ai/generations/{_ID}/confirm"),
    ("POST", f"{_BASE}/ai/generations/{_ID}/revise"),
    ("POST", f"{_BASE}/ai/generations/{_ID}/reject"),
    ("GET", f"{_BASE}/ai/generations/{_ID}/eligibility"),
    ("POST", f"{_BASE}/ai/formal-output/preflight"),
    ("POST", f"{_BASE}/ai/formal-output/finalize"),
    # Citation
    ("GET", f"{_BASE}/citations"),
    ("GET", f"{_BASE}/citations/{_ID}/locate"),
    ("POST", f"{_BASE}/citations/validate"),
    # Review
    ("POST", f"{_BASE}/reviews/{_ID}/evidence"),
    ("POST", f"{_BASE}/reviews/{_ID}/close"),
    ("POST", f"{_BASE}/reviews/{_ID}/reopen"),
    ("GET", f"{_BASE}/reviews/completion-block"),
    ("GET", f"{_BASE}/reviews/{_ID}"),
    # Archive
    ("POST", f"{_BASE}/archive/preflight"),
    ("POST", f"{_BASE}/archive/manifests"),
    ("GET", f"{_BASE}/archive/manifests"),
    ("GET", f"{_BASE}/archive/manifests/{_ID}"),
    ("POST", f"{_BASE}/archive/verify"),
    # Legal Hold / Retention
    ("POST", f"{_BASE}/legal-holds"),
    ("GET", f"{_BASE}/legal-holds"),
    ("GET", f"{_BASE}/legal-holds/{_ID}/scope"),
    ("POST", f"{_BASE}/legal-holds/{_ID}/release"),
    ("POST", f"{_BASE}/legal-holds/purge-jobs"),
]

# OpenAPI path templates (占位符形态) 对应上面的具体路由。
_EXPECTED_OPENAPI_PATHS: set[str] = {
    "/api/projects/{project_id}/years/{year}/evidence/ai/generations",
    "/api/projects/{project_id}/years/{year}/evidence/ai/generations/{content_id}",
    "/api/projects/{project_id}/years/{year}/evidence/ai/generations/{content_id}/confirm",
    "/api/projects/{project_id}/years/{year}/evidence/ai/generations/{content_id}/revise",
    "/api/projects/{project_id}/years/{year}/evidence/ai/generations/{content_id}/reject",
    "/api/projects/{project_id}/years/{year}/evidence/ai/generations/{content_id}/eligibility",
    "/api/projects/{project_id}/years/{year}/evidence/ai/formal-output/preflight",
    "/api/projects/{project_id}/years/{year}/evidence/ai/formal-output/finalize",
    "/api/projects/{project_id}/years/{year}/evidence/citations",
    "/api/projects/{project_id}/years/{year}/evidence/citations/{citation_id}/locate",
    "/api/projects/{project_id}/years/{year}/evidence/citations/validate",
    "/api/projects/{project_id}/years/{year}/evidence/reviews/{review_id}/evidence",
    "/api/projects/{project_id}/years/{year}/evidence/reviews/{review_id}/close",
    "/api/projects/{project_id}/years/{year}/evidence/reviews/{review_id}/reopen",
    "/api/projects/{project_id}/years/{year}/evidence/reviews/completion-block",
    "/api/projects/{project_id}/years/{year}/evidence/reviews/{review_id}",
    "/api/projects/{project_id}/years/{year}/evidence/archive/preflight",
    "/api/projects/{project_id}/years/{year}/evidence/archive/manifests",
    "/api/projects/{project_id}/years/{year}/evidence/archive/manifests/{manifest_id}",
    "/api/projects/{project_id}/years/{year}/evidence/archive/verify",
    "/api/projects/{project_id}/years/{year}/evidence/legal-holds",
    "/api/projects/{project_id}/years/{year}/evidence/legal-holds/{hold_id}/scope",
    "/api/projects/{project_id}/years/{year}/evidence/legal-holds/{hold_id}/release",
    "/api/projects/{project_id}/years/{year}/evidence/legal-holds/purge-jobs",
}


@pytest.fixture(scope="module")
def openapi_paths() -> set[str]:
    return set(_main.app.openapi()["paths"].keys())


def test_all_new_routes_present_in_openapi(openapi_paths: set[str]) -> None:
    """每条 Wave 9 端点都必须出现在 OpenAPI paths（路由已注册）。"""
    missing = _EXPECTED_OPENAPI_PATHS - openapi_paths
    assert not missing, f"Wave 9 端点未注册到 OpenAPI: {sorted(missing)}"


@pytest.mark.parametrize("method,path", _NEW_ROUTES)
def test_new_route_unauth_is_coded_not_500(method: str, path: str) -> None:
    """未认证请求应返回 coded 非-500（认证前置 → 401/403，绝不 500 崩溃、绝不误 404）。"""
    # 不进入 lifespan（无需 startup warmup / DB）；仅验证认证前置与路由可达。
    client = TestClient(_main.app, raise_server_exceptions=False)
    resp = client.request(method, path, json={})
    assert resp.status_code != 500, (
        f"{method} {path} 返回 500（应为认证前置的 coded 4xx）: {resp.text[:300]}"
    )
    # 路由存在（非 "未匹配路由" 的 404）——未认证时通常 401/403。
    assert resp.status_code in (401, 403, 422), (
        f"{method} {path} 期望 401/403/422（未认证），实得 {resp.status_code}: {resp.text[:200]}"
    )
