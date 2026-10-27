"""只挂在行上的证据按其底稿做可见性隔离（真 PG + 真实统一门，spec attachment-evidence-intake 需求 3.7）。

回归背景：可见性隔离只看整稿关联表；只有行级证据链接的附件被当成「项目级证据」，任何项目成员都能读写，
受限用户（只被委派了别的底稿）也能下载这一行的原件。
"""
from __future__ import annotations

import pytest

from app.models.attachment_models import Attachment
from app.models.wp_optimization_models import EvidenceLink
from app.services.wp_visibility.denial import DenialResponder, ExternalNotFound
from app.services.wp_visibility.entry_integration import enforce_attachment_wp_visibility
from tests.procedure_delegation_visibility._factories import (
    mk_project,
    mk_project_user,
    mk_user,
    mk_working_paper,
    mk_wp_index,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture
def denials(monkeypatch) -> list[str]:
    reasons: list[str] = []

    async def _capture(self, **fields):
        reasons.append(fields.get("reason"))

    monkeypatch.setattr(DenialResponder, "_write_outbox", _capture)
    return reasons


async def _row_evidence(s, proj, wp, creator):
    att = Attachment(project_id=proj.id, file_name="行证据.pdf", file_path="x/行证据.pdf", file_type="pdf",
                     file_size=10, storage_type="local")
    s.add(att)
    await s.flush()
    s.add(EvidenceLink(wp_id=wp.id, attachment_id=att.id, sheet_name="D2A", cell_ref="item:1", created_by=creator.id))
    await s.flush()
    return att


async def _lead_of(s, proj, *, code: str, cycle: str):
    user = await mk_user(s)
    wi = await mk_wp_index(s, proj.id, wp_code=code, audit_cycle=cycle)
    wp = await mk_working_paper(s, proj.id, wi.id)
    wp.assigned_to = user.id
    await mk_project_user(s, proj.id, user.id, scope_cycles=cycle)
    await s.flush()
    return user, wp


async def test_row_only_evidence_follows_its_workpaper(pg_session, denials):
    proj = await mk_project(pg_session)
    owner, wp = await _lead_of(pg_session, proj, code="D2-1", cycle="D")
    outsider, _other_wp = await _lead_of(pg_session, proj, code="K1-1", cycle="K")
    att = await _row_evidence(pg_session, proj, wp, owner)

    allowed = await enforce_attachment_wp_visibility(
        pg_session, owner, attachment_id=att.id, action="attach_download", method="GET",
        entrypoint="attachment.download",
    )
    assert allowed is not None and allowed.wp_id == wp.id

    with pytest.raises(ExternalNotFound):
        await enforce_attachment_wp_visibility(
            pg_session, outsider, attachment_id=att.id, action="attach_download", method="GET",
            entrypoint="attachment.download",
        )
    assert denials == ["not_delegated"]


async def test_attachment_workpapers_lists_only_visible_ones(pg_session, denials):
    """侧栏悬停清单（需求 4.3）：附件同时出现在 D、K 两张底稿时，各人只看到自己看得到的那张；非成员 403。"""
    from fastapi import HTTPException

    from app.models.attachment_models import AttachmentWorkingPaper
    from app.routers.process_record import get_attachment_workpapers

    proj = await mk_project(pg_session)
    d_user, d_wp = await _lead_of(pg_session, proj, code="D2-1", cycle="D")
    k_user, k_wp = await _lead_of(pg_session, proj, code="K1-1", cycle="K")
    att = await _row_evidence(pg_session, proj, k_wp, k_user)          # K 底稿上的行级证据
    pg_session.add(AttachmentWorkingPaper(attachment_id=att.id, wp_id=d_wp.id, association_type="evidence"))
    await pg_session.flush()

    seen_by_d = await get_attachment_workpapers(attachment_id=att.id, db=pg_session, current_user=d_user)
    seen_by_k = await get_attachment_workpapers(attachment_id=att.id, db=pg_session, current_user=k_user)
    assert [w["wp_code"] for w in seen_by_d] == ["D2-1"]
    assert [w["wp_code"] for w in seen_by_k] == ["K1-1"]

    stranger = await mk_user(pg_session)
    with pytest.raises(HTTPException) as exc:
        await get_attachment_workpapers(attachment_id=att.id, db=pg_session, current_user=stranger)
    assert exc.value.status_code == 403
