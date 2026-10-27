"""附件破坏性操作守卫（spec attachment-security-baseline 需求 4，ADR-ASB-05/06，design §5 第五、六行）。

回归背景：删除按查询参数里的项目判权（不带参数 422）、不判归档 / 保全 / 引用；回收站三条永久删除路径
（单条 / 批量 / 清空）都不查保全与引用，管理员直接放行不判归档；版本列表与回滚是路由里另写的一份，
回滚不取链锁、不发失效信号，且前端调的 ``/versions/{vid}/rollback`` 后端从未注册。

保全判定的裸 SQL 按 ``str(uuid)`` 绑定，SQLite 上恒不命中 ⇒ 保全用例标 ``pg_only``。
"""
from __future__ import annotations

import ast
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
import sqlalchemy as sa

from app.models.attachment_lineage_model import AttachmentLineage
from app.models.attachment_models import Attachment, AttachmentWorkingPaper
from app.models.evidence_governance_models import AttachmentVersion, LegalHold, LegalHoldScope
from app.models.wp_optimization_models import EvidenceLink
from app.routers import attachments as attachments_router_module
from app.routers import recycle_bin as recycle_bin_module
from app.services import attachment_destructive_guard as guard
from app.services.attachment_service import AttachmentService
from tests.attachment_security_baseline._world import (
    add_attachment,
    add_confirmation,
    add_outbound_link,
    add_wp,
    pg_attachment_world,
    sqlite_attachment_world,
)

ATT_ROUTER = attachments_router_module.router
RB_ROUTER = recycle_bin_module.router
GATE = "app.deps.assert_project_permission"


@pytest_asyncio.fixture
async def world(monkeypatch):
    async with sqlite_attachment_world(monkeypatch) as w:
        yield w


async def _user(world, key: str):
    factories = {
        "non_member": world.non_member, "readonly": lambda: world.member("readonly", "readonly"),
        "review": lambda: world.member("review", "qc"), "edit": lambda: world.member("edit", "auditor"),
        "admin": world.admin_non_member, "archived_edit": world.archived_edit_member,
    }
    return None if key == "anonymous" else (await factories[key]()).user


async def _deleted_flag(world, att: Attachment) -> bool:
    await world.db.refresh(att)
    return att.is_deleted


async def _exists(world, att_id) -> bool:
    return (await world.db.execute(sa.select(Attachment.id).where(Attachment.id == att_id))).scalar_one_or_none() is not None


# ── 删除（进回收站） ──


@pytest.mark.parametrize(("identity", "expected"), [
    ("anonymous", 401), ("non_member", 403), ("readonly", 403), ("review", 403),
    ("edit", 200), ("admin", 200), ("archived_edit", 423),
])
async def test_delete_permission_matrix(world, identity, expected):
    att = await add_attachment(world, world.target)
    user = await _user(world, identity)
    async with world.client(ATT_ROUTER, user=user) as client:
        resp = await client.delete(f"/api/attachments/{att.id}")  # 不带 project_id 查询参数（原先 422）
    assert resp.status_code == expected, resp.text
    assert await _deleted_flag(world, att) is (expected == 200)
    if identity != "anonymous":
        client.assert_passed(GATE, times=1)


async def test_delete_ignores_forged_project_query_param(world):
    """项目 B 的 edit 成员带 ``?project_id=B`` 删项目 A 的附件 ⇒ 按附件真实项目判，403 且不改库。"""
    att = await add_attachment(world, world.target)
    other = await world.other_project()
    user = (await world.member("edit", "manager", project=other)).user
    async with world.client(ATT_ROUTER, user=user) as client:
        resp = await client.delete(f"/api/attachments/{att.id}", params={"project_id": str(other.id)})
    assert resp.status_code == 403, resp.text
    assert await _deleted_flag(world, att) is False


async def _reference(world, att: Attachment, kind: str) -> None:
    if kind == "confirmation_links":
        await add_outbound_link(world, await add_confirmation(world, world.target), att)
    elif kind == "paired_outbound":
        conf = await add_confirmation(world, world.target)
        reply = await add_attachment(world, world.target)
        from app.models.confirmation_models import ConfirmationAttachmentLink

        await world._add(ConfirmationAttachmentLink(confirmation_id=conf.id, attachment_id=reply.id, role="inbound",
                                                    paired_outbound_attachment_id=att.id, match_status="manual"))
    elif kind == "evidence_links":
        wp = await add_wp(world, world.target)
        await world._add(EvidenceLink(wp_id=wp.id, attachment_id=att.id, created_by=uuid.uuid4()))
    elif kind == "lineage_links":
        await world._add(AttachmentLineage(attachment_id=att.id, target_type="wp_cell", target_ref="D2-3!B5"))
    elif kind == "business_reference":
        wp = await add_wp(world, world.target)
        att.reference_type, att.reference_id = "working_paper", wp.id
        await world.db.flush()
    elif kind == "workpaper_links":
        wp = await add_wp(world, world.target)
        await world._add(AttachmentWorkingPaper(attachment_id=att.id, wp_id=wp.id, association_type="evidence"))
    else:
        raise KeyError(kind)


@pytest.mark.parametrize(("kind", "category"), [
    ("confirmation_links", "confirmation_links"), ("paired_outbound", "confirmation_links"),
    ("evidence_links", "evidence_links"), ("lineage_links", "lineage_links"),
    ("business_reference", "business_reference"),
])
async def test_delete_referenced_attachment_is_409(world, kind, category):
    att = await add_attachment(world, world.target)
    await _reference(world, att, kind)
    user = await _user(world, "edit")
    async with world.client(ATT_ROUTER, user=user) as client:
        resp = await client.delete(f"/api/attachments/{att.id}")
    assert resp.status_code == 409, resp.text
    detail = resp.json()["detail"]
    assert detail["error_code"] == "ATTACHMENT_IN_USE" and detail["references"] == {category: 1}
    assert guard.REFERENCE_LABELS[category] in detail["message"]
    assert await _deleted_flag(world, att) is False


async def test_count_references_sees_workpaper_links(world):
    """底稿关联（权威链表）计入引用（删除端点先过底稿可见性门，这里直接测计数）。"""
    att = await add_attachment(world, world.target)
    await _reference(world, att, "workpaper_links")
    counts = await guard.count_references(world.db, att)
    assert counts == {"workpaper_links": 1, "confirmation_links": 0, "evidence_links": 0,
                      "lineage_links": 0, "business_reference": 0}


# ── 其他附件写端点：归档 423 ──


async def _archived_world_user(world):
    return (await world.archived_edit_member()).user


async def test_write_endpoints_on_archived_project_are_423(world):
    att = await add_attachment(world, world.target, ocr_status="failed")
    v1 = await add_attachment(world, world.target, file_name="合同.pdf")
    v2 = await add_attachment(world, world.target, file_name="合同.pdf", version=2, previous_version_id=v1.id)
    user = await _archived_world_user(world)
    async with world.client(ATT_ROUTER, user=user) as client:
        status = await client.put(f"/api/attachments/{att.id}/ocr-status", json={"status": "pending"})
        retry = await client.post(f"/api/attachments/{att.id}/retry-ocr")
        rollback = await client.post(f"/api/attachments/{v2.id}/versions/{v1.id}/rollback")
        reads = await client.get(f"/api/attachments/{v2.id}/versions")
    assert [r.status_code for r in (status, retry, rollback)] == [423, 423, 423]
    assert reads.status_code == 200  # 只读不受归档影响
    await world.db.refresh(att)
    assert att.ocr_status == "failed"


async def test_associate_and_unlink_on_archived_project_are_423(world):
    """关联 / 解除关联：可见性门（additive，另有 procedure_delegation_visibility 套件）换成放行桩，只观测归档判定。"""
    att = await add_attachment(world, world.target)
    wp = await add_wp(world, world.target)
    world.stub(attachments_router_module, "gate_attachment_associate", None)
    world.stub(attachments_router_module, "gate_wp", None)
    associate = world.stub(AttachmentService, "associate_with_wp", {"id": "x"})
    unlink = world.stub(AttachmentService, "unlink_wp_attachment", {"ok": True})
    user = await _archived_world_user(world)
    async with world.client(ATT_ROUTER, user=user) as client:
        a = await client.post(f"/api/attachments/{att.id}/associate", json={"wp_id": str(wp.id)})
        u = await client.delete(f"/api/working-papers/{wp.id}/attachments/{att.id}/link")
    assert (a.status_code, u.status_code) == (423, 423), (a.text, u.text)
    assert (associate.count, unlink.count) == (0, 0)


# ── 版本：委托服务层 ──


async def _chain(world, user) -> tuple[dict, dict]:
    svc = AttachmentService(world.db)
    base = {"file_name": "合同.pdf", "file_path": "storage/x/合同.pdf", "storage_type": "local"}
    v1 = await svc.create_attachment(world.target.id, dict(base), created_by=user.id)
    v2 = await svc.create_attachment(world.target.id, dict(base), created_by=user.id)
    await world.db.commit()
    return v1, v2


async def test_versions_list_and_rollback_delegate_to_service(world):
    user = (await world.member("edit", "auditor")).user
    v1, v2 = await _chain(world, user)
    assert (v1["version"], v2["version"]) == (1, 2)
    async with world.client(ATT_ROUTER, user=user) as client:
        listed = await client.get(f"/api/attachments/{v2['id']}/versions")
        latest = await client.post(f"/api/attachments/{v2['id']}/versions/{v2['id']}/rollback")
        rolled = await client.post(f"/api/attachments/{v2['id']}/versions/{v1['id']}/rollback")
        after = await client.get(f"/api/attachments/{v2['id']}/versions")
    versions = listed.json()["versions"]
    assert [v["version"] for v in versions] == [2, 1]
    assert [v["is_current"] for v in versions] == [True, False]
    assert versions[0]["uploaded_by"] == str(user.id) and versions[0]["uploaded_at"]
    assert latest.json()["message"] == "已是最新版本，无需回退"
    assert rolled.status_code == 200, rolled.text
    body = rolled.json()
    assert (body["version"], body["rolled_back_to"], body["previous_version_id"]) == (3, 1, v2["id"])
    new_row = await world.db.get(Attachment, uuid.UUID(body["id"]))
    assert new_row.created_by == user.id  # 写回滚人
    assert [v["version"] for v in after.json()["versions"]] == [3, 2, 1]


async def test_rollback_to_version_outside_chain_is_404(world):
    user = (await world.member("edit", "auditor")).user
    v1, v2 = await _chain(world, user)
    stranger = await add_attachment(world, world.target, file_name="别的.pdf")
    async with world.client(ATT_ROUTER, user=user) as client:
        resp = await client.post(f"/api/attachments/{v2['id']}/versions/{stranger.id}/rollback")
        old = await client.post(f"/api/attachments/{v1['id']}/rollback")
    assert resp.status_code == 404
    assert old.status_code in (404, 405)  # 旧路由已删除（前端从未调用）
    count = (await world.db.execute(sa.select(sa.func.count()).select_from(Attachment)
                                    .where(Attachment.file_name == "合同.pdf"))).scalar_one()
    assert count == 2


def test_router_versions_code_has_no_private_chain_query():
    """版本端点只经服务层：路由模块里不再自己查 ``Attachment.version``。"""
    tree = ast.parse(Path(attachments_router_module.__file__).read_text(encoding="utf-8"))
    funcs = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef)}
    for name in ("list_attachment_versions", "rollback_attachment_version"):
        attrs = {n.attr for n in ast.walk(funcs[name]) if isinstance(n, ast.Attribute)}
        assert {"list_versions"} <= attrs and "version" not in attrs - {"list_versions", "rollback_to_version"}, name


# ── 回收站永久删除 ──


async def test_purge_single(world):
    ok = await add_attachment(world, world.target, is_deleted=True)
    referenced = await add_attachment(world, world.target, is_deleted=True)
    await _reference(world, referenced, "workpaper_links")
    user = await _user(world, "edit")
    async with world.client(RB_ROUTER, user=user) as client:
        purged = await client.delete(f"/api/recycle-bin/attachment/{ok.id}")
        blocked = await client.delete(f"/api/recycle-bin/attachment/{referenced.id}")
    assert purged.status_code == 200, purged.text
    assert blocked.status_code == 409 and blocked.json()["detail"]["references"] == {"workpaper_links": 1}
    assert (await _exists(world, ok.id), await _exists(world, referenced.id)) == (False, True)


async def test_purge_single_on_archived_project_is_423_even_for_admin(world):
    att = await add_attachment(world, world.target, is_deleted=True)
    await world.archived_edit_member()  # 目标项目置为已归档
    admin = (await world.admin_non_member()).user
    async with world.client(RB_ROUTER, user=admin) as client:
        resp = await client.delete(f"/api/recycle-bin/attachment/{att.id}")
    assert resp.status_code == 423, resp.text
    assert await _exists(world, att.id)


async def test_batch_purge_skips_and_counts(world):
    ok = await add_attachment(world, world.target, is_deleted=True)
    referenced = await add_attachment(world, world.target, is_deleted=True)
    await _reference(world, referenced, "confirmation_links")
    missing = uuid.uuid4()
    user = await _user(world, "edit")
    async with world.client(RB_ROUTER, user=user) as client:
        resp = await client.post("/api/recycle-bin/batch-delete", params={"item_type": "attachment"},
                                 json={"ids": [str(ok.id), str(referenced.id), str(missing)]})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["succeeded"] == [str(ok.id)]
    assert {f["id"]: f["error"] for f in body["failed"]} == {str(referenced.id): "仍被引用", str(missing): "记录不存在"}
    assert (body["total"], body["fail_count"], body["skipped"]) == (3, 2, {"referenced": 1})
    assert (await _exists(world, ok.id), await _exists(world, referenced.id)) == (False, True)


async def test_empty_attachments_only_purges_purgeable(world):
    ok = await add_attachment(world, world.target, is_deleted=True)
    referenced = await add_attachment(world, world.target, is_deleted=True)
    await _reference(world, referenced, "evidence_links")
    other = await world.other_project()
    other.status = type(world.target.status).archived
    archived_att = await add_attachment(world, other, is_deleted=True)
    live = await add_attachment(world, world.target)
    admin = (await world.admin_non_member()).user
    async with world.client(RB_ROUTER, user=admin) as client:
        resp = await client.post("/api/recycle-bin/empty", params={"item_type": "attachment"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert (body["deleted_count"], body["skipped"]) == (1, {"archived": 1, "referenced": 1})
    assert "未删除" in body["message"]
    remaining = {aid for aid in (ok.id, referenced.id, archived_att.id, live.id) if await _exists(world, aid)}
    assert remaining == {referenced.id, archived_att.id, live.id}


def test_empty_all_routes_attachments_through_guard():
    """清空全部的循环里附件走 ``_purge_deleted_attachments``（不再整表 DELETE）。"""
    src = Path(recycle_bin_module.__file__).read_text(encoding="utf-8")
    fn = next(n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.AsyncFunctionDef) and n.name == "empty_recycle_bin")
    calls = [n.func.id for n in ast.walk(fn) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]
    assert calls.count("_purge_deleted_attachments") == 2


# ── 法定保全（真 PG） ──


async def _hold(world, project, node_type: str, node_id) -> None:
    holder = await world.user()
    hold = await world._add(LegalHold(project_id=project.id, reason="【测试】诉讼保全", state="active",
                                      actor_type="user", actor_user_id=holder.id))
    await world._add(LegalHoldScope(legal_hold_id=hold.id, project_id=project.id, node_type=node_type,
                                    node_id=str(node_id), scope_kind="direct", is_active=True))


@pytest_asyncio.fixture
async def pg_world(monkeypatch):
    async with pg_attachment_world(monkeypatch) as w:
        yield w


@pytest.mark.pg_only
async def test_delete_under_legal_hold_is_423(pg_world):
    world = pg_world
    held = await add_attachment(world, world.target)
    free = await add_attachment(world, world.target)
    await _hold(world, world.target, "attachment", held.id)
    admin = (await world.admin_non_member()).user
    async with world.client(ATT_ROUTER, user=admin) as client:
        blocked = await client.delete(f"/api/attachments/{held.id}")
        ok = await client.delete(f"/api/attachments/{free.id}")
    assert blocked.status_code == 423 and blocked.json()["detail"]["error_code"] == "LEGAL_HOLD_ACTIVE"
    assert ok.status_code == 200, ok.text
    assert (await _deleted_flag(world, held), await _deleted_flag(world, free)) == (False, True)


@pytest.mark.pg_only
async def test_purge_under_legal_hold_on_version_node_is_423_and_batch_skips(pg_world):
    world = pg_world
    held = await add_attachment(world, world.target, is_deleted=True)
    holder = await world.user()
    version = await world._add(AttachmentVersion(attachment_id=held.id, project_id=world.target.id, version_no=1,
                                                 actor_type="user", actor_user_id=holder.id))
    await _hold(world, world.target, "attachment_version", version.id)
    free = await add_attachment(world, world.target, is_deleted=True)
    admin = (await world.admin_non_member()).user
    async with world.client(RB_ROUTER, user=admin) as client:
        single = await client.delete(f"/api/recycle-bin/attachment/{held.id}")
        batch = await client.post("/api/recycle-bin/batch-delete", params={"item_type": "attachment"},
                                  json={"ids": [str(held.id), str(free.id)]})
    assert single.status_code == 423, single.text
    assert batch.json()["skipped"] == {"legal_hold": 1} and batch.json()["succeeded"] == [str(free.id)]
    assert (await _exists(world, held.id), await _exists(world, free.id)) == (True, False)
