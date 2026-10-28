"""函证路由的项目隔离（spec attachment-security-baseline 需求 2.1、2.2，design §5 前四行）。

改造前：17 个端点只校验登录、服务按 id 取数不带项目条件 ⇒ 任意登录用户可读写任意项目的函证与回函附件；
挂载 / 解绑 / 识别比对 / 自动匹配用的角色集不含审计员 ⇒ 审计员挂不了回函（403）。

经 HTTP 真发请求（权限世界：真实成员行、生产门禁、生产注册；只 override 当前用户与会话）。
权限矩阵用例把业务 service 换成计数桩，只测门；另有两条不打桩的真实挂载 / 解绑用例。
"""
from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pytest
import pytest_asyncio
import sqlalchemy as sa

from app.models.attachment_models import Attachment
from app.models.base import UserRole
from app.models.confirmation_models import ConfirmationActionLog, ConfirmationAttachmentLink
from app.routers import confirmations as confirmations_router_module
from app.services import confirmation_evidence_service as evidence_svc
from app.services import confirmation_service as confirmation_svc
from app.services.confirmation_scope_gate import confirmation_project_gate, required_level
from tests.attachment_security_baseline._world import (
    add_attachment,
    add_confirmation,
    add_outbound_link,
    add_wp,
    sqlite_attachment_world,
)

ROUTER = confirmations_router_module.router
PREFIX = "/projects/{project_id}/confirmations"
GATE = "app.deps.assert_project_permission"


@pytest_asyncio.fixture
async def world(monkeypatch):
    async with sqlite_attachment_world(monkeypatch) as w:
        yield w


# ── 对象与身份 ──


@dataclass
class Objs:
    pid: uuid.UUID
    cid: uuid.UUID
    aid: uuid.UUID
    lid: uuid.UUID
    wp: uuid.UUID


async def _objects(world) -> Objs:
    wp = await add_wp(world, world.target)
    conf = await add_confirmation(world, world.target, wp=wp)
    att = await add_attachment(world, world.target, attachment_type="confirmation")
    link = await add_outbound_link(world, conf, att)
    return Objs(world.target.id, conf.id, att.id, link.id, wp.id)


IDENTITIES = ("anonymous", "non_member", "readonly", "review", "edit_auditor", "manager", "admin", "archived_edit")


async def _user(world, key: str):
    if key == "anonymous":
        return None
    if key == "non_member":
        return (await world.non_member()).user
    if key == "readonly":
        return (await world.member("readonly", "readonly")).user
    if key == "review":
        return (await world.member("review", "qc", global_role=UserRole.qc)).user
    if key == "edit_auditor":
        return (await world.member("edit", "auditor")).user
    if key == "manager":
        return (await world.member("edit", "manager", global_role=UserRole.manager)).user
    if key == "admin":
        return (await world.admin_non_member()).user
    if key == "archived_edit":
        return (await world.archived_edit_member()).user
    raise KeyError(key)


# ── design §5 前四行 ──

_READ = {"anonymous": 401, "non_member": 403, "readonly": 200, "review": 200,
         "edit_auditor": 200, "manager": 200, "admin": 200, "archived_edit": 200}
_WRITE = {"anonymous": 401, "non_member": 403, "readonly": 403, "review": 403,
          "edit_auditor": 200, "manager": 200, "admin": 200, "archived_edit": 423}
_CONCLUDE = {**_WRITE, "edit_auditor": 403}


@dataclass(frozen=True)
class Recipe:
    name: str
    method: str
    path: str  # 路由里声明的路径（不含前缀），用于核对表格覆盖全部端点
    url: Callable[[Objs], str]
    expected: dict[str, int]
    counted: tuple[Any, str, Any]  # 判定通过后必被调用一次的业务 service（owner, attr, 桩返回值）
    body: Callable[[Objs], dict] | None = None
    extra_stubs: tuple[tuple[Any, str, Any], ...] = ()


def _base(o: Objs) -> str:
    return f"/api/projects/{o.pid}/confirmations"


_LINK = SimpleNamespace(
    id=uuid.uuid4(), confirmation_id=uuid.uuid4(), attachment_id=uuid.uuid4(), role="outbound",
    paired_outbound_attachment_id=None, match_status="manual",
)

RECIPES: tuple[Recipe, ...] = (
    # 读
    Recipe("列表", "GET", "", lambda o: _base(o), _READ, (confirmation_svc, "list_confirmations", [])),
    Recipe("候选", "GET", "/candidates", lambda o: f"{_base(o)}/candidates?confirm_type=bank&year=2025", _READ,
           (confirmation_svc, "list_confirmation_candidates", [])),
    Recipe("匹配队列", "GET", "/match-queue", lambda o: f"{_base(o)}/match-queue", _READ,
           (evidence_svc, "list_match_queue", [])),
    Recipe("详情", "GET", "/{confirmation_id}", lambda o: f"{_base(o)}/{o.cid}", _READ,
           (confirmation_svc, "get_confirmation", {"id": "x"})),
    Recipe("附件列表", "GET", "/{confirmation_id}/attachments", lambda o: f"{_base(o)}/{o.cid}/attachments", _READ,
           (evidence_svc, "list_attachments", [])),
    # 写
    Recipe("创建", "POST", "", lambda o: _base(o), _WRITE, (confirmation_svc, "create_confirmation", {"id": "x"}),
           body=lambda o: {"confirm_type": "receivable", "counterparty": "客户甲", "wp_id": str(o.wp)}),
    Recipe("更新", "PUT", "/{confirmation_id}", lambda o: f"{_base(o)}/{o.cid}", _WRITE,
           (confirmation_svc, "update_confirmation", {"id": "x"}), body=lambda o: {"counterparty": "客户乙"}),
    Recipe("删除", "DELETE", "/{confirmation_id}", lambda o: f"{_base(o)}/{o.cid}", _WRITE,
           (confirmation_svc, "delete_confirmation", {"deleted": True})),
    Recipe("推进", "POST", "/{confirmation_id}/transition", lambda o: f"{_base(o)}/{o.cid}/transition", _WRITE,
           (confirmation_svc, "transition_status", {"id": "x"}), body=lambda o: {"target_status": "sent"}),
    Recipe("撤回（非终态）", "POST", "/{confirmation_id}/reverse", lambda o: f"{_base(o)}/{o.cid}/reverse", _WRITE,
           (confirmation_svc, "reverse_status", {"id": "x"}), body=lambda o: {"target_status": "pending"},
           extra_stubs=((confirmation_svc, "get_confirmation", {"status": "sent"}),)),
    Recipe("批量同步", "POST", "/batch-sync", lambda o: f"{_base(o)}/batch-sync", _WRITE,
           (confirmation_svc, "list_confirmations", []), body=lambda o: {"items": [], "wp_id": str(o.wp)}),
    # 函证附件
    Recipe("挂载", "POST", "/{confirmation_id}/attachments", lambda o: f"{_base(o)}/{o.cid}/attachments", _WRITE,
           (evidence_svc, "link_attachment", _LINK), body=lambda o: {"attachment_id": str(o.aid), "role": "outbound"}),
    Recipe("解绑", "DELETE", "/{confirmation_id}/attachments/{link_id}",
           lambda o: f"{_base(o)}/{o.cid}/attachments/{o.lid}", _WRITE, (evidence_svc, "unlink_attachment", None)),
    # 识别前置（spec attachment-confirmation-evidence-loop 需求 2.1）也是业务步骤：矩阵只测门，一并打桩
    Recipe("识别比对", "POST", "/attachments/{attachment_id}/extract-compare",
           lambda o: f"{_base(o)}/attachments/{o.aid}/extract-compare", _WRITE,
           (evidence_svc, "extract_and_compare", {"status": "matched"}),
           extra_stubs=((confirmations_router_module, "ensure_reply_text", "回函全文"),)),
    Recipe("自动匹配", "POST", "/auto-match", lambda o: f"{_base(o)}/auto-match", _WRITE,
           (evidence_svc, "auto_match", {"status": "no_hit"}), body=lambda o: {"attachment_id": str(o.aid)}),
    Recipe("人工指派", "POST", "/match-queue/{attachment_id}/assign",
           lambda o: f"{_base(o)}/match-queue/{o.aid}/assign", _WRITE, (evidence_svc, "assign_match", {"ok": True}),
           body=lambda o: {"confirmation_id": str(o.cid), "paired_outbound_id": str(o.aid)}),
    # 回填结论
    Recipe("回填结论", "POST", "/{confirmation_id}/apply-reply", lambda o: f"{_base(o)}/{o.cid}/apply-reply", _CONCLUDE,
           (evidence_svc, "apply_reply", {"status": "matched"}),
           body=lambda o: {"attachment_id": str(o.aid), "confirmed_amount": 100, "target_status": "matched"}),
)


def test_table_covers_every_route():
    """表格与路由一一对应：新增端点必须先进表（否则矩阵对它没有断言）。"""
    declared = {
        (method, route.path.removeprefix(PREFIX))
        for route in ROUTER.routes for method in route.methods
    }
    assert {(r.method, r.path) for r in RECIPES} == declared
    assert len(declared) == 17


def test_gate_is_router_level():
    assert [d.dependency for d in ROUTER.dependencies] == [confirmation_project_gate]
    assert all(route.path.startswith(PREFIX) for route in ROUTER.routes)


@pytest.mark.parametrize(("method", "level"), [("GET", "readonly"), ("HEAD", "readonly"), ("POST", "edit"),
                                               ("PUT", "edit"), ("PATCH", "edit"), ("DELETE", "edit"), ("", "edit")])
def test_required_level_by_method(method, level):
    assert required_level(method) == level


def _install(world, recipe: Recipe):
    for owner, attr, returns in recipe.extra_stubs:
        world.stub(owner, attr, returns)
    owner, attr, returns = recipe.counted
    return world.stub(owner, attr, returns)


@pytest.mark.parametrize("identity", IDENTITIES)
@pytest.mark.parametrize("recipe", RECIPES, ids=lambda r: r.name)
async def test_permission_matrix(world, recipe: Recipe, identity: str):
    objs = await _objects(world)
    user = await _user(world, identity)
    stub = _install(world, recipe)
    kwargs = {"json": recipe.body(objs)} if recipe.body else {}
    async with world.client(ROUTER, user=user) as client:
        resp = await client.request(recipe.method, recipe.url(objs), **kwargs)
    expected = recipe.expected[identity]
    assert resp.status_code == expected, f"{recipe.name} / {identity}: {resp.status_code} {resp.text}"
    assert stub.count == (1 if expected == 200 else 0)
    if identity != "anonymous":
        client.assert_passed(GATE, times=1)


async def test_reverse_terminal_still_needs_manager(world):
    """撤回终态（相符 / 差异）仍要求经理及以上：edit 审计员 403，经理 200。"""
    objs = await _objects(world)
    results = {}
    for key in ("edit_auditor", "manager"):
        user = await _user(world, key)
        world.stub(confirmation_svc, "get_confirmation", {"status": "matched"})
        stub = world.stub(confirmation_svc, "reverse_status", {"id": "x"})
        async with world.client(ROUTER, user=user) as client:
            resp = await client.post(f"{_base(objs)}/{objs.cid}/reverse", json={"target_status": "returned"})
        results[key] = (resp.status_code, stub.count)
    assert results == {"edit_auditor": (403, 0), "manager": (200, 1)}


# ── 需求 2.2：对象必须属于路径项目 ──


@dataclass
class Foreign:
    a: Objs
    cid_b: uuid.UUID
    aid_b: uuid.UUID
    lid_b: uuid.UUID
    wp_b: uuid.UUID
    lid_a2: uuid.UUID  # 同项目另一笔函证上的挂载
    aid_deleted: uuid.UUID


async def _foreign(world) -> Foreign:
    a = await _objects(world)
    other = await world.other_project()
    wp_b = await add_wp(world, other, wp_code="D1")
    conf_b = await add_confirmation(world, other, wp=wp_b)
    att_b = await add_attachment(world, other, attachment_type="confirmation")
    link_b = await add_outbound_link(world, conf_b, att_b)
    conf_a2 = await add_confirmation(world, world.target)
    att_a2 = await add_attachment(world, world.target)
    link_a2 = await add_outbound_link(world, conf_a2, att_a2)
    deleted = await add_attachment(world, world.target, is_deleted=True)
    return Foreign(a, conf_b.id, att_b.id, link_b.id, wp_b.id, link_a2.id, deleted.id)


def _amount(aid) -> dict:
    return {"attachment_id": str(aid), "confirmed_amount": 100, "target_status": "matched"}


CROSS: tuple[tuple[str, str, Callable[[Foreign], str], Callable[[Foreign], dict] | None, int, tuple[Any, str]], ...] = (
    ("详情：他项目函证", "GET", lambda f: f"{_base(f.a)}/{f.cid_b}", None, 404, (confirmation_svc, "get_confirmation")),
    ("详情：非法 id", "GET", lambda f: f"{_base(f.a)}/not-a-uuid", None, 404, (confirmation_svc, "get_confirmation")),
    ("更新：他项目函证", "PUT", lambda f: f"{_base(f.a)}/{f.cid_b}", lambda f: {"counterparty": "x"}, 404,
     (confirmation_svc, "update_confirmation")),
    ("删除：他项目函证", "DELETE", lambda f: f"{_base(f.a)}/{f.cid_b}", None, 404,
     (confirmation_svc, "delete_confirmation")),
    ("推进：他项目函证", "POST", lambda f: f"{_base(f.a)}/{f.cid_b}/transition", lambda f: {"target_status": "sent"},
     404, (confirmation_svc, "transition_status")),
    ("附件列表：他项目函证", "GET", lambda f: f"{_base(f.a)}/{f.cid_b}/attachments", None, 404,
     (evidence_svc, "list_attachments")),
    ("挂载：他项目附件", "POST", lambda f: f"{_base(f.a)}/{f.a.cid}/attachments",
     lambda f: {"attachment_id": str(f.aid_b), "role": "outbound"}, 404, (evidence_svc, "link_attachment")),
    ("挂载：配对他项目发函件", "POST", lambda f: f"{_base(f.a)}/{f.a.cid}/attachments",
     lambda f: {"attachment_id": str(f.a.aid), "role": "inbound", "paired_outbound_id": str(f.aid_b)}, 404,
     (evidence_svc, "link_attachment")),
    ("挂载：已删除附件", "POST", lambda f: f"{_base(f.a)}/{f.a.cid}/attachments",
     lambda f: {"attachment_id": str(f.aid_deleted), "role": "outbound"}, 404, (evidence_svc, "link_attachment")),
    ("挂载：非法附件 id", "POST", lambda f: f"{_base(f.a)}/{f.a.cid}/attachments",
     lambda f: {"attachment_id": "../x", "role": "outbound"}, 404, (evidence_svc, "link_attachment")),
    ("解绑：他项目挂载记录", "DELETE", lambda f: f"{_base(f.a)}/{f.a.cid}/attachments/{f.lid_b}", None, 404,
     (evidence_svc, "unlink_attachment")),
    ("解绑：同项目另一笔函证的挂载", "DELETE", lambda f: f"{_base(f.a)}/{f.a.cid}/attachments/{f.lid_a2}", None, 404,
     (evidence_svc, "unlink_attachment")),
    ("识别比对：他项目附件", "POST", lambda f: f"{_base(f.a)}/attachments/{f.aid_b}/extract-compare", None, 404,
     (evidence_svc, "extract_and_compare")),
    ("自动匹配：他项目附件", "POST", lambda f: f"{_base(f.a)}/auto-match", lambda f: {"attachment_id": str(f.aid_b)},
     404, (evidence_svc, "auto_match")),
    ("人工指派：他项目回函件", "POST", lambda f: f"{_base(f.a)}/match-queue/{f.aid_b}/assign",
     lambda f: {"confirmation_id": str(f.a.cid)}, 404, (evidence_svc, "assign_match")),
    ("人工指派：指到他项目函证", "POST", lambda f: f"{_base(f.a)}/match-queue/{f.a.aid}/assign",
     lambda f: {"confirmation_id": str(f.cid_b)}, 404, (evidence_svc, "assign_match")),
    ("回填：他项目回函件", "POST", lambda f: f"{_base(f.a)}/{f.a.cid}/apply-reply", lambda f: _amount(f.aid_b), 404,
     (evidence_svc, "apply_reply")),
    ("创建：他项目底稿", "POST", lambda f: _base(f.a),
     lambda f: {"confirm_type": "bank", "counterparty": "银行", "wp_id": str(f.wp_b)}, 422,
     (confirmation_svc, "create_confirmation")),
    ("更新：改挂他项目底稿", "PUT", lambda f: f"{_base(f.a)}/{f.a.cid}", lambda f: {"wp_id": str(f.wp_b)}, 422,
     (confirmation_svc, "update_confirmation")),
    ("批量同步：行内他项目底稿", "POST", lambda f: f"{_base(f.a)}/batch-sync",
     lambda f: {"items": [{"confirm_type": "bank", "counterparty": "银行", "wp_id": str(f.wp_b)}]}, 422,
     (confirmation_svc, "list_confirmations")),
    ("批量同步：整体他项目底稿", "POST", lambda f: f"{_base(f.a)}/batch-sync",
     lambda f: {"items": [], "wp_id": str(f.wp_b)}, 422, (confirmation_svc, "list_confirmations")),
)


@pytest.mark.parametrize("case", CROSS, ids=lambda c: c[0])
async def test_objects_must_belong_to_path_project(world, case):
    name, method, url, body, expected, (owner, attr) = case
    f = await _foreign(world)
    user = await _user(world, "manager")  # 经理：回填结论也能走到对象核对
    stub = world.stub(owner, attr, {"id": "x"})
    async with world.client(ROUTER, user=user) as client:
        resp = await client.request(method, url(f), **({"json": body(f)} if body else {}))
    assert resp.status_code == expected, f"{name}: {resp.status_code} {resp.text}"
    assert stub.count == 0
    client.assert_passed(GATE, times=1)


# ── 不打桩：审计员真实挂载与解绑 ──


async def test_edit_auditor_links_outbound_and_reply_for_real(world):
    """改造前审计员挂回函一律 403（角色集不含 auditor）；现在本项目 edit 即可，且服务真实落库。"""
    conf = await add_confirmation(world, world.target)
    outbound = await add_attachment(world, world.target, attachment_type="confirmation", file_name="发函.pdf")
    reply = await add_attachment(world, world.target, attachment_type="confirmation", file_name="回函.pdf")
    user = await _user(world, "edit_auditor")
    url = f"/api/projects/{world.target.id}/confirmations/{conf.id}/attachments"
    async with world.client(ROUTER, user=user) as client:
        first = await client.post(url, json={"attachment_id": str(outbound.id), "role": "outbound"})
        second = await client.post(url, json={"attachment_id": str(reply.id), "role": "inbound"})
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert second.json()["paired_outbound_attachment_id"] == str(outbound.id)

    links = (await world.db.execute(
        sa.select(ConfirmationAttachmentLink.attachment_id, ConfirmationAttachmentLink.role)
        .where(ConfirmationAttachmentLink.confirmation_id == conf.id)
    )).all()
    assert sorted((str(a), r) for a, r in links) == sorted([(str(outbound.id), "outbound"), (str(reply.id), "inbound")])
    logs = (await world.db.execute(
        sa.select(ConfirmationActionLog.actor_user_id).where(ConfirmationActionLog.confirmation_id == conf.id)
    )).scalars().all()
    assert logs == [user.id, user.id]
    await world.db.refresh(reply)
    assert (reply.reference_type, reply.reference_id) == ("confirmation_list", conf.id)


async def test_unlink_removes_only_the_named_link_for_real(world):
    f = await _foreign(world)
    user = await _user(world, "edit_auditor")
    async with world.client(ROUTER, user=user) as client:
        denied = await client.delete(f"{_base(f.a)}/{f.a.cid}/attachments/{f.lid_a2}")
        ok = await client.delete(f"{_base(f.a)}/{f.a.cid}/attachments/{f.a.lid}")
    assert (denied.status_code, ok.status_code) == (404, 200), (denied.text, ok.text)
    remaining = set((await world.db.execute(sa.select(ConfirmationAttachmentLink.id))).scalars())
    assert f.lid_a2 in remaining and f.lid_b in remaining and f.a.lid not in remaining
    att = await world.db.get(Attachment, f.a.aid)
    assert att is not None and not att.is_deleted
