"""真 PG：凭证证据的可见性（真实统一门）与 V230 唯一索引（spec attachment-voucher-evidence-binding 需求 1.3、2、8.1）。

会话在共享库的一个事务里、结束整体回滚；统一门拒绝时写安全 outbox 的一步截住（不连共享库）。
"""
from __future__ import annotations

import pytest
import sqlalchemy as sa
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import IntegrityError

from app.core.database import get_db
from app.deps import get_current_user
from app.models.attachment_models import Attachment
from app.models.core import PermissionLevel
from app.models.wp_optimization_models import EvidenceLink
from app.routers.wp_evidence import router as evidence_router
from app.services.voucher_evidence import reuse_voucher_evidence, voucher_evidence_by_keys
from app.services.workpaper_evidence_intake import IntakeWorkpaper
from app.services.wp_visibility.denial import DenialResponder
from tests.attachment_voucher_evidence._vk import vk
from tests.authz_world import build_app
from tests.procedure_delegation_visibility._factories import (
    mk_project,
    mk_project_user,
    mk_row_task,
    mk_staff,
    mk_user,
    mk_working_paper,
    mk_wp_index,
)

pytestmark = pytest.mark.asyncio
VK = vk()


@pytest.fixture(autouse=True)
def denials(monkeypatch) -> list[str]:
    """统一门拒绝时写安全 outbox 的一步截住：记下原因，不连共享库。"""
    reasons: list[str] = []

    async def _capture(self, **fields):
        reasons.append(fields.get("reason"))

    monkeypatch.setattr(DenialResponder, "_write_outbox", _capture)
    return reasons


async def _lead_of(s, proj, *, code: str, cycle: str):
    user = await mk_user(s)
    wi = await mk_wp_index(s, proj.id, wp_code=code, audit_cycle=cycle)
    wp = await mk_working_paper(s, proj.id, wi.id)
    wp.assigned_to = user.id
    await mk_project_user(s, proj.id, user.id, scope_cycles=cycle)
    await s.flush()
    return user, wp


async def _voucher_evidence(s, proj, wp, creator, *, cell: str | None = None):
    att = Attachment(project_id=proj.id, file_name="凭证.pdf", file_path="x/凭证.pdf", file_type="pdf",
                     file_size=10, storage_type="local")
    s.add(att)
    await s.flush()
    s.add(EvidenceLink(wp_id=wp.id, attachment_id=att.id, sheet_name="D2-1" if cell else None, cell_ref=cell,
                       evidence_type="voucher", voucher_key=VK, created_by=creator.id))
    await s.flush()
    return att


async def test_query_and_reuse_follow_workpaper_visibility(pg_session):
    proj = await mk_project(pg_session)
    d_user, d_wp = await _lead_of(pg_session, proj, code="D2-1", cycle="D")
    k_user, k_wp = await _lead_of(pg_session, proj, code="K1-1", cycle="K")
    att = await _voucher_evidence(pg_session, proj, d_wp, d_user, cell="row:r1")

    seen_by_d = await voucher_evidence_by_keys(pg_session, d_user, proj.id, 2025, [VK])
    seen_by_k = await voucher_evidence_by_keys(pg_session, k_user, proj.id, 2025, [VK])
    assert [e["wp_code"] for e in seen_by_d[VK]] == ["D2-1"]
    assert seen_by_k == {}  # K 循环负责人看不到 D 底稿上的原件

    target = IntakeWorkpaper(id=k_wp.id, project_id=proj.id, wp_code="K1-1")
    with pytest.raises(HTTPException) as exc:
        await reuse_voucher_evidence(pg_session, k_user, target, VK, att.id)
    assert exc.value.status_code == 404


async def test_unique_index_allows_other_position_only(pg_session):
    proj = await mk_project(pg_session)
    user, wp = await _lead_of(pg_session, proj, code="D2-1", cycle="D")
    att = await _voucher_evidence(pg_session, proj, wp, user)        # 凭证级（表页、单元格为空）
    pg_session.add(EvidenceLink(wp_id=wp.id, attachment_id=att.id, sheet_name="D2-1", cell_ref="row:2",
                                evidence_type="voucher", voucher_key=VK, created_by=user.id))
    await pg_session.flush()                                         # 另一个位置：允许（删行前移先建后删）
    with pytest.raises(IntegrityError):
        async with pg_session.begin_nested():
            pg_session.add(EvidenceLink(wp_id=wp.id, attachment_id=att.id, evidence_type="voucher",
                                        voucher_key=VK, created_by=user.id))
            await pg_session.flush()
    total = (await pg_session.execute(
        sa.select(sa.func.count()).select_from(EvidenceLink).where(EvidenceLink.wp_id == wp.id)
    )).scalar_one()
    assert total == 2


async def _role_scenario(s, kind: str):
    """本底稿 D2-1 上的三种身份（项目级都可编辑，区分只落在统一门上）；源底稿 D4-1 由同一人负责、有这张凭证的原件。"""
    proj = await mk_project(s)
    user = await mk_user(s)
    staff = await mk_staff(s, user_id=user.id)
    member = await mk_project_user(s, proj.id, user.id, scope_cycles="D")
    member.permission_level = PermissionLevel.edit
    src_wi = await mk_wp_index(s, proj.id, wp_code="D4-1", audit_cycle="D")
    src = await mk_working_paper(s, proj.id, src_wi.id)
    src.assigned_to = user.id
    wi = await mk_wp_index(s, proj.id, wp_code="D2-1", audit_cycle="D")
    wp = await mk_working_paper(s, proj.id, wi.id)
    if kind == "lead":
        wp.assigned_to = user.id
    elif kind == "assignee":
        await mk_row_task(s, proj.id, wi.id, sheet_key="D2A", sheet_name="n-D2A", assignee_staff_id=staff.id)
    else:
        await mk_row_task(s, proj.id, wi.id, sheet_key="D2A", sheet_name="n-D2A", reviewer_staff_id=staff.id)
    await s.flush()
    att = await _voucher_evidence(s, proj, src, user)
    return proj, user, wp, att


@pytest.mark.parametrize(("kind", "expected"), [("lead", 200), ("assignee", 200), ("reviewer", 404)])
async def test_reuse_by_role(pg_session, monkeypatch, denials, kind, expected):
    """引用走底稿统一门的写判定（生产注册参数，含 ``dedicated_wp_gate``）：负责人 / 编制人可引用，复核人 404（design §5）。"""
    proj, user, wp, att = await _role_scenario(pg_session, kind)

    async def _flush_only() -> None:
        await pg_session.flush()

    monkeypatch.setattr(pg_session, "commit", _flush_only)
    api = build_app(evidence_router)

    async def _db():
        yield pg_session

    api.dependency_overrides[get_db] = _db
    api.dependency_overrides[get_current_user] = lambda: user
    async with AsyncClient(transport=ASGITransport(app=api), base_url="http://voucher-reuse") as client:
        resp = await client.post(f"/api/projects/{proj.id}/workpapers/{wp.id}/evidence/voucher-reuse",
                                 json={"voucher_key": VK, "attachment_id": str(att.id)})
    assert resp.status_code == expected, resp.text
    linked = (await pg_session.execute(
        sa.select(sa.func.count()).select_from(EvidenceLink).where(EvidenceLink.wp_id == wp.id)
    )).scalar_one()
    assert linked == (1 if expected == 200 else 0)
    assert denials == (["action_denied"] if expected == 404 else [])
