"""入口上传与证据链接的角色矩阵：真 PG + 生产注册参数（含 ``dedicated_wp_gate``）（需求 1.4，ADR-AEI-04）。

编制人（程序行执行人）能在自己的底稿上传新证据、增删行级链接；复核人只读；底稿负责人全权。
已有附件的整稿关联仍只给负责人（``test_task10_entry_gate.py::test_associate_assignee_denied`` 钉住，本 spec 不放宽）。
"""
from __future__ import annotations

import pytest
import sqlalchemy as sa
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import PermissionLevel
from app.models.wp_optimization_models import EvidenceLink
from app.routers.wp_evidence import router as evidence_router
from app.services.wp_visibility.denial import DenialResponder
from tests.attachment_evidence_intake._helpers import pdf, use_local_storage
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


async def _scenario(s, kind: str):
    proj = await mk_project(s)
    user = await mk_user(s)
    staff = await mk_staff(s, user_id=user.id)
    wi = await mk_wp_index(s, proj.id, wp_code="D2-1", audit_cycle="D")
    wp = await mk_working_paper(s, proj.id, wi.id)
    member = await mk_project_user(s, proj.id, user.id, scope_cycles="D")
    member.permission_level = PermissionLevel.edit  # 项目级可编辑：区分只落在统一门上
    if kind == "lead":
        wp.assigned_to = user.id
    elif kind == "assignee":
        await mk_row_task(s, proj.id, wi.id, sheet_key="D2A", sheet_name="n-D2A", assignee_staff_id=staff.id)
    elif kind == "reviewer":
        await mk_row_task(s, proj.id, wi.id, sheet_key="D2A", sheet_name="n-D2A", reviewer_staff_id=staff.id)
    await s.flush()
    return proj, user, wp


@pytest.fixture
def denials(monkeypatch) -> list[str]:
    """统一门拒绝时写安全 outbox：记下原因，不连共享库。"""
    reasons: list[str] = []

    async def _capture(self, **fields):
        reasons.append(fields.get("reason"))

    monkeypatch.setattr(DenialResponder, "_write_outbox", _capture)
    return reasons


async def _client(session, user, monkeypatch):
    async def _flush_only() -> None:
        await session.flush()

    monkeypatch.setattr(session, "commit", _flush_only)
    api = build_app(evidence_router)

    async def _db():
        yield session

    api.dependency_overrides[get_db] = _db
    api.dependency_overrides[get_current_user] = lambda: user
    return AsyncClient(transport=ASGITransport(app=api), base_url="http://role-matrix")


async def _links(session, wp) -> int:
    return int((await session.execute(
        sa.select(sa.func.count()).select_from(EvidenceLink).where(EvidenceLink.wp_id == wp.id)
    )).scalar_one())


@pytest.mark.parametrize(("kind", "expected"), [("lead", 200), ("assignee", 200), ("reviewer", 404)])
async def test_row_upload_by_role(pg_session, monkeypatch, tmp_path, denials, kind, expected):
    use_local_storage(tmp_path, monkeypatch)
    proj, user, wp = await _scenario(pg_session, kind)
    async with await _client(pg_session, user, monkeypatch) as client:
        resp = await client.post(
            f"/api/projects/{proj.id}/workpapers/{wp.id}/evidence/upload",
            files=pdf(), data={"sheet_name": "D2A", "cell_ref": "item:1"},
        )
    assert resp.status_code == expected, resp.text
    assert await _links(pg_session, wp) == (1 if expected == 200 else 0)
    if expected == 404:
        assert denials == ["action_denied"]


@pytest.mark.parametrize(("kind", "expected"), [("assignee", 200), ("reviewer", 404)])
async def test_remove_row_link_by_role(pg_session, monkeypatch, tmp_path, denials, kind, expected):
    use_local_storage(tmp_path, monkeypatch)
    proj, user, wp = await _scenario(pg_session, kind)
    lead = await mk_user(pg_session)
    link_id = await _seed_row_evidence(pg_session, proj, wp, lead)
    async with await _client(pg_session, user, monkeypatch) as client:
        listed = await client.get(f"/api/projects/{proj.id}/workpapers/{wp.id}/evidence")
        removed = await client.delete(f"/api/projects/{proj.id}/workpapers/{wp.id}/evidence/{link_id}")
    assert listed.status_code == 200, listed.text  # 复核人也能看
    assert removed.status_code == expected, removed.text
    assert await _links(pg_session, wp) == (0 if expected == 200 else 1)


async def _seed_row_evidence(session, proj, wp, creator) -> str:
    from app.models.attachment_models import Attachment

    att = Attachment(project_id=proj.id, file_name="行证据.pdf", file_path="x/行证据.pdf", file_type="pdf",
                     file_size=10, storage_type="local")
    session.add(att)
    await session.flush()
    link = EvidenceLink(wp_id=wp.id, attachment_id=att.id, sheet_name="D2A", cell_ref="item:1",
                        created_by=creator.id)
    session.add(link)
    await session.flush()
    return str(link.id)
