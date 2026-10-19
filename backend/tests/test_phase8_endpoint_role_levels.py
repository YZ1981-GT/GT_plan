"""Phase 8 Task 8 鉴权定级的端点级守卫：该放行的角色真能用，该拦的真拦住。

背景（2026-10-19 复核）：补项目级鉴权时，复核 / 发起签署 / 程序裁剪 / 执行校验也被挂成 edit。
``assignment_service.ROLE_MAP`` 给签字合伙人、经理、质控、EQCR 的项目级别都是 review，edit 门只放行
edit 级与 admin ⇒ 这些复核人会被 403。``test_phase8_endpoint_auth_fires`` 只测「不带令牌被拒」，
测不出「该放行的人被拦」这一类，所以单独钉住。

做法（memory ㉕）：不 override ``require_project_access``（依赖工厂每次返回新函数对象，key 对不上会静默失效）。
只替换它下面的取数点 —— ``get_current_user`` 返回假用户、权限缓存返回指定级别、归档守卫与 RLS 置空 ——
让真实的 ``assert_project_permission`` 照常判定；业务 service 打桩，只看鉴权结论。
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.deps as deps
from app.core.database import get_db
from app.routers import review_workflow, wp_cross_check, wp_procedures
from app.services.assignment_service import ROLE_MAP

PID = "2aa00f57-1df4-4fe8-9840-2d65d0fd8749"
ME = uuid.UUID("11111111-1111-1111-1111-111111111111")
OTHER = uuid.UUID("22222222-2222-2222-2222-222222222222")
WP = "33333333-3333-3333-3333-333333333333"
PROC = "44444444-4444-4444-4444-444444444444"

GATE_DENIED = "权限不足"  # assert_project_permission 的 403 文案
NOT_SELF = "只能签署或查看本人的独立性声明"


class _NoRow:
    def scalar_one_or_none(self):
        return None


class _FakeDB:
    """业务 service 已打桩；只有「非项目成员」分支会查 project_users，这里恒返回查无此人。"""

    async def execute(self, *_a, **_k):
        return _NoRow()

    async def commit(self):
        return None

    async def rollback(self):
        return None


async def _noop(*_a, **_k):
    return None


def _async_return(value):
    async def _f(*_a, **_k):
        return value

    return _f


def _client(monkeypatch: pytest.MonkeyPatch, level: str | None, *, authenticated: bool = True) -> TestClient:
    """level=None 表示不是项目成员（缓存未命中 → 查库查无此人）。"""
    monkeypatch.setattr(deps, "_get_cached_permission", _async_return(level))
    monkeypatch.setattr(deps, "_set_cached_permission", _noop)
    monkeypatch.setattr(deps, "_check_project_not_archived", _noop)
    monkeypatch.setattr(deps, "set_rls_context", _noop)

    rw, sig = review_workflow.ReviewWorkflowService, review_workflow.IndependenceSigningService
    monkeypatch.setattr(rw, "save_review", _async_return({"saved": True}))
    monkeypatch.setattr(rw, "link_conversation", _async_return(True))
    monkeypatch.setattr(rw, "unlink_conversation", _async_return(True))
    monkeypatch.setattr(sig, "initiate_signing", _async_return({"created": 0}))
    monkeypatch.setattr(sig, "sign", _async_return({"success": True}))
    monkeypatch.setattr(sig, "get_my_pending_tasks", _async_return([]))
    monkeypatch.setattr(wp_procedures.WpProcedureService, "trim_procedure", _async_return({"id": PROC}))
    monkeypatch.setattr(wp_procedures.WpProcedureService, "mark_complete", _async_return({"id": PROC}))
    monkeypatch.setattr(wp_procedures, "recalc_quality_score", _noop)
    monkeypatch.setattr(wp_cross_check.CrossCheckService, "execute", _async_return([]))

    app = FastAPI()
    for r in (
        review_workflow.router, review_workflow.signing_router, review_workflow.my_signing_router,
        wp_procedures.router, wp_cross_check.router,
    ):
        app.include_router(r)

    async def _db():
        yield _FakeDB()

    app.dependency_overrides[get_db] = _db
    if authenticated:
        user = SimpleNamespace(id=ME, role=SimpleNamespace(value="partner"))

        async def _user():  # 🔴 override 不能带 *args/**kwargs：FastAPI 会把它们当成必填查询参数（422）
            return user

        app.dependency_overrides[deps.get_current_user] = _user
    return TestClient(app, raise_server_exceptions=False)


# (说明, METHOD, 路径, 请求体) —— 复核人（review 级）必须能用的写操作
_REVIEW_WRITES = [
    ("复核保存", "post", f"/api/projects/{PID}/review-workflow/2025/save",
     {"template_code": "A17-1", "items": [], "opinion": "", "submit": False}),
    ("关联复核对话", "post", f"/api/projects/{PID}/review-workflow/2025/link-conversation",
     {"conversation_id": str(OTHER), "checklist_ref": "1"}),
    ("取消关联", "post", f"/api/projects/{PID}/review-workflow/2025/unlink-conversation?conversation_id={OTHER}", None),
    ("发起独立性签署", "post", f"/api/projects/{PID}/signing/2025/initiate?template_code=A17-7", None),
    ("程序裁剪", "patch", f"/api/projects/{PID}/workpapers/{WP}/procedures/{PROC}/trim", {"reason": "不适用"}),
    ("执行跨表校验", "post", f"/api/projects/{PID}/cross-check/execute", {"year": 2025, "trigger": "sign_off"}),
]
_IDS = [c[0] for c in _REVIEW_WRITES]


def _call(client: TestClient, method: str, path: str, body):
    return getattr(client, method)(path, json=body) if body is not None else getattr(client, method)(path)


def test_premise_reviewer_roles_are_review_level() -> None:
    """前提：复核人在项目里是 review 级、编制人是 edit 级。ROLE_MAP 一变，本文件的定级理由就要重审。"""
    for role in ("signing_partner", "partner", "manager", "qc", "eqcr"):
        assert ROLE_MAP[role][1].value == "review", role
    for role in ("auditor", "assistant"):
        assert ROLE_MAP[role][1].value == "edit", role


@pytest.mark.parametrize("name,method,path,body", _REVIEW_WRITES, ids=_IDS)
def test_review_level_member_can_use(monkeypatch, name, method, path, body) -> None:
    resp = _call(_client(monkeypatch, "review"), method, path, body)
    assert resp.status_code == 200, f"{name}：review 级成员（合伙人/经理/质控/EQCR）被拒 {resp.status_code} {resp.text}"


@pytest.mark.parametrize("name,method,path,body", _REVIEW_WRITES, ids=_IDS)
def test_edit_level_member_can_use(monkeypatch, name, method, path, body) -> None:
    resp = _call(_client(monkeypatch, "edit"), method, path, body)
    assert resp.status_code == 200, f"{name}：edit 级成员（审计员/助理）被拒 {resp.status_code} {resp.text}"


@pytest.mark.parametrize("name,method,path,body", _REVIEW_WRITES, ids=_IDS)
def test_readonly_member_is_blocked(monkeypatch, name, method, path, body) -> None:
    resp = _call(_client(monkeypatch, "readonly"), method, path, body)
    assert resp.status_code == 403 and GATE_DENIED in resp.text, f"{name}：只读成员未被拦 {resp.status_code}"


def test_edit_endpoints_still_block_reviewers(monkeypatch) -> None:
    """对照：编制类写操作（标记程序完成）仍是 edit 门，没有被一起放宽。"""
    path = f"/api/projects/{PID}/workpapers/{WP}/procedures/{PROC}/complete"
    body = {"user_id": str(ME)}
    denied = _client(monkeypatch, "review").patch(path, json=body)
    assert denied.status_code == 403 and GATE_DENIED in denied.text
    assert _client(monkeypatch, "edit").patch(path, json=body).status_code == 200


def test_member_signs_only_for_self(monkeypatch) -> None:
    client = _client(monkeypatch, "readonly")  # 签署只要求是项目成员
    base = f"/api/projects/{PID}/signing/2025/sign?template_code=A17-7&user_id="
    assert client.post(base + str(ME)).status_code == 200
    other = client.post(base + str(OTHER))
    assert other.status_code == 403 and NOT_SELF in other.text
    assert client.post(base + "undefined").status_code == 422


def test_non_member_cannot_sign(monkeypatch) -> None:
    resp = _client(monkeypatch, None).post(f"/api/projects/{PID}/signing/2025/sign?user_id={ME}")
    assert resp.status_code == 403 and GATE_DENIED in resp.text


def test_my_signing_tasks_requires_login_and_self(monkeypatch) -> None:
    client = _client(monkeypatch, None)  # 无 project_id，不看项目级别
    assert client.get(f"/api/my/signing-tasks?user_id={ME}").status_code == 200
    other = client.get(f"/api/my/signing-tasks?user_id={OTHER}")
    assert other.status_code == 403 and NOT_SELF in other.text
    anonymous = _client(monkeypatch, None, authenticated=False).get(f"/api/my/signing-tasks?user_id={ME}")
    assert anonymous.status_code in (401, 403)
