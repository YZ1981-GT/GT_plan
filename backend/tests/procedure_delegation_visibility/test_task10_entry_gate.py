# Feature: procedure-delegation-visibility-isolation — Task 10 附件/文件/导入导出/批量/非 HTTP 执行器接入 gate
"""Task 10（组件 C10 EntryIntegration）附件 associate 多资源 / 批量 preflight-atomic /
可见集过滤 / 非 HTTP 执行器 re-gate 集成测试。

Requirements: 8.6–8.8, 8.13–8.17, 9, 13.13–13.15, 16.17。
Design: 组件 C10 / "Binding adapters ... 批量写在任何副作用前逐资源 preflight" /
  "callback/worker/retry/dead-letter callables RE-gate at actual execution time"。

真实 PostgreSQL（audit_platform）承载数据；C10 helper 内部调用真实 Wp_Bound_Gate（角色/scope/
grants/matrix 全链）。每用例事务隔离回滚；安全 outbox 用注入 CapturingResponder（不落 dev 库）。
另含一个真实 FastAPI app（ASGI in-process）的 associate 端点用例（dependency_overrides 复用同一
事务隔离 PG session）。
"""
from __future__ import annotations

import uuid
from uuid import uuid4

import pytest

from app.models.attachment_models import Attachment, AttachmentWorkingPaper
# 注册 Attachment FK 目标表（service_identities）到 ORM metadata，避免 NoReferencedTableError。
from app.models import evidence_governance_models as _evidence_governance_models  # noqa: F401
from app.services.wp_visibility.denial import (
    DenialReason,
    DenialResponder,
    ExternalNotFound,
)
from app.services.wp_visibility.entry_integration import (
    enforce_attachment_wp_visibility,
    gate_attachment_associate,
    make_bulk_preflight,
    make_bulk_visible_filter,
)

from ._factories import (
    IS_PG,
    mk_project,
    mk_project_user,
    mk_row_task,
    mk_staff,
    mk_user,
    mk_working_paper,
    mk_wp_index,
)


# ---------------------------------------------------------------------------
# capturing responder（不落 dev 库）
# ---------------------------------------------------------------------------
class CapturingResponder(DenialResponder):
    def __init__(self) -> None:
        super().__init__()
        self.captured: list[dict] = []

    async def _write_outbox(self, **fields) -> None:  # type: ignore[override]
        self.captured.append(fields)

    def last_reason(self) -> str | None:
        return self.captured[-1]["reason"] if self.captured else None


# ---------------------------------------------------------------------------
# attachment factories（_factories.py 无附件工厂，本文件内联）
# ---------------------------------------------------------------------------
async def mk_attachment(s, project_id, *, is_deleted: bool = False) -> Attachment:
    att = Attachment(
        project_id=project_id,
        file_name=f"ev_{uuid4().hex[:8]}.pdf",
        file_path=f"/tmp/{uuid4().hex[:8]}.pdf",
        file_type="pdf",
        file_size=1024,
    )
    att.is_deleted = is_deleted
    s.add(att)
    await s.flush()
    return att


async def mk_att_link(s, attachment_id, wp_id) -> AttachmentWorkingPaper:
    link = AttachmentWorkingPaper(
        attachment_id=attachment_id, wp_id=wp_id, association_type="evidence"
    )
    s.add(link)
    await s.flush()
    return link


async def _lead_scenario(s, *, scope="D", cycle="D"):
    """当前用户是 wp 的 Workpaper_Lead（scope 内）。"""
    proj = await mk_project(s)
    user = await mk_user(s)
    wi = await mk_wp_index(s, proj.id, wp_code="D2-1", audit_cycle=cycle)
    wp = await mk_working_paper(s, proj.id, wi.id)
    wp.assigned_to = user.id
    await mk_project_user(s, proj.id, user.id, scope_cycles=scope)
    await s.flush()
    return proj, user, wi, wp


async def _assignee_scenario(s, *, sheet="D2A", scope="D"):
    """当前用户仅是某程序行执行人（Row_Assignee），非 Lead。"""
    proj = await mk_project(s)
    user = await mk_user(s)
    staff = await mk_staff(s, user_id=user.id)
    wi = await mk_wp_index(s, proj.id, wp_code="D2-1", audit_cycle="D")
    wp = await mk_working_paper(s, proj.id, wi.id)
    await mk_row_task(
        s, proj.id, wi.id, sheet_key=sheet, sheet_name=f"n-{sheet}",
        assignee_staff_id=staff.id,
    )
    await mk_project_user(s, proj.id, user.id, scope_cycles=scope)
    await s.flush()
    return proj, user, wi, wp


# ===========================================================================
# associate 多资源 gate（headline）
# ===========================================================================
@pytest.mark.skipif(not IS_PG, reason="need PostgreSQL")
@pytest.mark.asyncio
class TestAssociateMultiResource:
    async def test_associate_allow_lead_same_project(self, session):
        """Lead + 同项目附件 → 全部通过，返回 lead grant。"""
        proj, user, wi, wp = await _lead_scenario(session)
        att = await mk_attachment(session, proj.id)
        ctx = await gate_attachment_associate(
            session, user, attachment_id=att.id, target_wp_id=wp.id,
            responder=CapturingResponder(),
        )
        assert "lead" in ctx.access_kinds
        assert ctx.wp_id == wp.id

    async def test_associate_cross_project_denied(self, session):
        """附件属于其他项目 → cross_project → 统一 404，副作用前失败。"""
        proj, user, wi, wp = await _lead_scenario(session)
        other = await mk_project(session)
        att_other = await mk_attachment(session, other.id)
        resp = CapturingResponder()
        with pytest.raises(ExternalNotFound) as ei:
            await gate_attachment_associate(
                session, user, attachment_id=att_other.id, target_wp_id=wp.id,
                responder=resp,
            )
        assert ei.value.status_code == 404
        assert resp.last_reason() == DenialReason.cross_project.value

    async def test_associate_missing_attachment_404(self, session):
        proj, user, wi, wp = await _lead_scenario(session)
        resp = CapturingResponder()
        with pytest.raises(ExternalNotFound):
            await gate_attachment_associate(
                session, user, attachment_id=uuid4(), target_wp_id=wp.id,
                responder=resp,
            )
        assert resp.last_reason() == DenialReason.not_found.value

    async def test_associate_assignee_denied(self, session):
        """仅程序行执行人（非 Lead）不得 associate（矩阵未登记 assignee 的 attach_associate）。"""
        proj, user, wi, wp = await _assignee_scenario(session)
        att = await mk_attachment(session, proj.id)
        resp = CapturingResponder()
        with pytest.raises(ExternalNotFound) as ei:
            await gate_attachment_associate(
                session, user, attachment_id=att.id, target_wp_id=wp.id,
                responder=resp,
            )
        assert ei.value.status_code == 404
        assert resp.last_reason() == DenialReason.action_denied.value


# ===========================================================================
# 附件 wp-link 隔离层
# ===========================================================================
@pytest.mark.skipif(not IS_PG, reason="need PostgreSQL")
@pytest.mark.asyncio
class TestAttachmentWpLinkIsolation:
    async def test_download_linked_visible_wp_allows(self, session):
        proj, user, wi, wp = await _lead_scenario(session)
        att = await mk_attachment(session, proj.id)
        await mk_att_link(session, att.id, wp.id)
        ctx = await enforce_attachment_wp_visibility(
            session, user, attachment_id=att.id,
            action="attach_download", method="GET", entrypoint="attachment.download",
            responder=CapturingResponder(),
        )
        assert ctx is not None and "lead" in ctx.access_kinds

    async def test_download_linked_invisible_wp_denied(self, session):
        """附件只关联到当前用户不可见的底稿 → 404（不泄露存在性）。"""
        proj, user, wi, wp = await _lead_scenario(session)
        # 另一个当前用户无委派、无 scope 的底稿
        other_wi = await mk_wp_index(session, proj.id, wp_code="K1-1", audit_cycle="K")
        other_wp = await mk_working_paper(session, proj.id, other_wi.id)
        att = await mk_attachment(session, proj.id)
        await mk_att_link(session, att.id, other_wp.id)
        resp = CapturingResponder()
        with pytest.raises(ExternalNotFound):
            await enforce_attachment_wp_visibility(
                session, user, attachment_id=att.id,
                action="attach_download", method="GET", entrypoint="attachment.download",
                responder=resp,
            )
        assert resp.last_reason() == DenialReason.not_delegated.value

    async def test_unlinked_attachment_returns_none(self, session):
        """未关联底稿的项目级附件 → 隔离层放行（返回 None，交既有项目级授权）。"""
        proj, user, wi, wp = await _lead_scenario(session)
        att = await mk_attachment(session, proj.id)
        ctx = await enforce_attachment_wp_visibility(
            session, user, attachment_id=att.id,
            action="attach_read", method="GET", entrypoint="attachment.read",
            responder=CapturingResponder(),
        )
        assert ctx is None


# ===========================================================================
# 批量：可见集过滤 + 逐资源 preflight 原子
# ===========================================================================
@pytest.mark.skipif(not IS_PG, reason="need PostgreSQL")
@pytest.mark.asyncio
class TestBulkGate:
    async def test_visible_filter_includes_only_visible(self, session):
        proj, user, wi, wp = await _lead_scenario(session)
        other_wi = await mk_wp_index(session, proj.id, wp_code="K1-1", audit_cycle="K")
        other_wp = await mk_working_paper(session, proj.id, other_wi.id)
        vf = make_bulk_visible_filter(session, user)
        assert await vf(wp.id, None) is True          # 可见（lead）
        assert await vf(other_wp.id, None) is False    # 不可见 → 剔除
        assert await vf(None, None) is False           # 无 wp_id

    async def test_preflight_allows_visible(self, session):
        proj, user, wi, wp = await _lead_scenario(session)
        pf = make_bulk_preflight(session, user, responder=CapturingResponder())
        # 可见资源 → 不抛
        await pf(wp.id, None)

    async def test_preflight_atomic_deny_on_invisible(self, session):
        """显式请求含不可见资源 → preflight 抛 ExternalNotFound（副作用前整请求失败）。"""
        proj, user, wi, wp = await _lead_scenario(session)
        other_wi = await mk_wp_index(session, proj.id, wp_code="K1-1", audit_cycle="K")
        other_wp = await mk_working_paper(session, proj.id, other_wi.id)
        resp = CapturingResponder()
        pf = make_bulk_preflight(session, user, responder=resp)
        with pytest.raises(ExternalNotFound):
            await pf(other_wp.id, None)
        assert resp.last_reason() == DenialReason.not_delegated.value


# ===========================================================================
# 非 HTTP 执行器 re-gate（撤权后排队任务被拒）
# ===========================================================================
@pytest.mark.skipif(not IS_PG, reason="need PostgreSQL")
@pytest.mark.asyncio
class TestWorkerRegateAfterRevocation:
    async def test_worker_preflight_rejects_after_revocation(self, session):
        """worker 用 entry_kind='worker' 执行时 re-gate：撤销 Lead 后同一资源被拒（Req 8.16/16.17）。"""
        proj, user, wi, wp = await _lead_scenario(session)
        # 执行前：Lead 可见 → worker preflight 放行
        pf = make_bulk_preflight(session, user, entry_kind="worker",
                                 responder=CapturingResponder())
        await pf(wp.id, None)

        # 模拟排队期间撤权：清空 Workpaper_Lead
        wp.assigned_to = None
        await session.flush()

        # 执行时 re-gate：不再可见 → 拒绝（排队任务被拒）
        resp = CapturingResponder()
        pf2 = make_bulk_preflight(session, user, entry_kind="worker", responder=resp)
        with pytest.raises(ExternalNotFound):
            await pf2(wp.id, None)
        assert resp.last_reason() == DenialReason.not_delegated.value


# ===========================================================================
# 真实 FastAPI app（ASGI in-process）associate 端点
# ===========================================================================
@pytest.mark.skipif(not IS_PG, reason="need PostgreSQL")
@pytest.mark.asyncio
async def test_associate_endpoint_real_app_allow(session, monkeypatch):
    """真实 attachments 路由 + 事务隔离 PG：Lead associate → 200 并建立关联。"""
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from app.core.database import get_db
    from app.deps import get_current_user
    from app.routers.attachments import router as attachments_router

    proj, user, wi, wp = await _lead_scenario(session)
    att = await mk_attachment(session, proj.id)

    # 路由内 db.commit() 会结束外层隔离事务导致落库；改为 flush 以保持事务隔离回滚。
    async def _flush_only() -> None:
        await session.flush()

    monkeypatch.setattr(session, "commit", _flush_only)

    app = FastAPI()
    app.include_router(attachments_router)

    async def _override_db():
        yield session

    def _override_user():
        return user

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user

    # 路由内 associate 成功后调 db.commit()；事务隔离 session 的 commit 不落 dev 库（外层回滚）。
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            f"/api/attachments/{att.id}/associate",
            json={"wp_id": str(wp.id), "association_type": "evidence"},
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # ResponseWrapperMiddleware 未挂在最小 app 上 → 直接返回 service dict
    payload = body.get("data", body)
    assert payload["wp_id"] == str(wp.id)
    assert payload["attachment_id"] == str(att.id)
