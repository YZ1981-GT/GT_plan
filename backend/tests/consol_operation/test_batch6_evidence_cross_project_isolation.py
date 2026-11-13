"""批 6.6 / recipe 2：证据跨项目隔离。

证明属于项目 A 的证据（``EvidenceLink`` + 附件）不能经项目 B 的合并薄壳端点读取 / 链接。

隔离链（ADR-CRW-006 / R8.3，复用附件 owner spec 的归属校验，不重建）：

1. 每个合并项目的薄壳 ``working_paper_id`` 项目私有——``get_consol_workpaper_shell(db, project_id)``
   按 ``WorkingPaper.project_id == project_id`` 过滤。
2. 薄壳证据坐标解析（``resolve_consol_evidence_target`` / ``evidence-target`` 端点）只会返回
   **本项目** 的 ``wp_id``；拿不到别的项目的 ``wp_id``。
3. 证据端点 ``load_workpaper(wp_id, project_id=...)`` 对「wp_id 不属于路径 project_id」一律 404
   （``workpaper_evidence_intake.load_workpaper`` 的归属校验）——这是真正的隔离闸。
4. ``WpEvidenceService.list_links(wp_id)`` 只按 ``EvidenceLink.wp_id`` 返回，A 的链接不会出现在
   B 的 wp_id 查询里。
5. ``assert_attachments_in_wp`` 要求附件与底稿同项目——A 的附件不能链接到 B 的壳。
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import tests.conftest  # noqa: F401
from app.models.attachment_models import Attachment, AttachmentWorkingPaper
from app.models.base import Base, ProjectStatus
from app.models.consol_workpaper_instance_models import ConsolWorkpaperInstance
from app.models.core import Project, User
from app.models.wp_optimization_models import EvidenceLink
from app.models.workpaper_models import WpIndex, WorkingPaper
from app.services.consol_workpaper_shell import (
    ensure_consol_workpaper_shell,
    get_consol_workpaper_shell,
    resolve_consol_evidence_target,
)
from app.services.wp_evidence_service import WpEvidenceService
from app.services.workpaper_evidence_intake import IntakeWorkpaper, load_workpaper

pytestmark = pytest.mark.asyncio

YEAR = 2025
_TABLES = [
    User.__table__, Project.__table__,
    WpIndex.__table__, WorkingPaper.__table__,
    ConsolWorkpaperInstance.__table__,
    Attachment.__table__, AttachmentWorkingPaper.__table__, EvidenceLink.__table__,
]


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=_TABLES)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


def _consol_project(name: str) -> Project:
    return Project(
        id=uuid.uuid4(), name=name, client_name=name, company_code="SH",
        audit_year=YEAR, report_scope="consolidated", status=ProjectStatus.execution,
    )


async def _attach_evidence(db: AsyncSession, project_id: uuid.UUID, wp_id: uuid.UUID) -> Attachment:
    """给 ``wp_id`` 挂一条行级证据链接（附件属于 ``project_id``）。"""
    att = Attachment(
        id=uuid.uuid4(), project_id=project_id, file_name="evidence.pdf",
        file_path=f"local://{project_id}/evidence.pdf", file_type="pdf",
        file_size=321, storage_type="local", state="available", is_deleted=False,
    )
    db.add(att)
    await db.flush()
    db.add(EvidenceLink(
        id=uuid.uuid4(), wp_id=wp_id, sheet_name="consol_trial",
        cell_ref="node:SH:consol/row:id:1001/col:consol_amount",
        attachment_id=att.id, created_by=uuid.uuid4(),
    ))
    await db.flush()
    return att


@pytest_asyncio.fixture
async def two_projects(db: AsyncSession):
    """两个合并项目 A / B，各自薄壳；A 的壳上挂一条证据。"""
    pa, pb = _consol_project("【测试】跨项目隔离_A_2025"), _consol_project("【测试】跨项目隔离_B_2025")
    db.add_all([pa, pb])
    await db.commit()
    shell_a = await ensure_consol_workpaper_shell(db, pa.id, year=YEAR)
    shell_b = await ensure_consol_workpaper_shell(db, pb.id, year=YEAR)
    await db.commit()
    wp_a = uuid.UUID(shell_a["working_paper_id"])
    wp_b = uuid.UUID(shell_b["working_paper_id"])
    att_a = await _attach_evidence(db, pa.id, wp_a)
    await db.commit()
    return pa, pb, wp_a, wp_b, att_a


async def test_shells_have_distinct_project_scoped_wp_ids(db: AsyncSession, two_projects):
    """两项目的薄壳 wp_id 不同，各自项目私有。"""
    pa, pb, wp_a, wp_b, _ = two_projects
    assert wp_a != wp_b
    sa = await get_consol_workpaper_shell(db, pa.id)
    sb = await get_consol_workpaper_shell(db, pb.id)
    assert sa["working_paper_id"] == str(wp_a)
    assert sb["working_paper_id"] == str(wp_b)


async def test_evidence_target_only_returns_own_project_wp_id(db: AsyncSession, two_projects):
    """项目 B 的证据坐标解析只会给出 B 自己的 wp_id，拿不到 A 的 wp_id。"""
    pa, pb, wp_a, wp_b, _ = two_projects
    target_b = await resolve_consol_evidence_target(
        db, pb.id, year=YEAR, sheet_type="trial", node_key="consol_trial",
        row_fields={"standard_account_code": "1001"},
    )
    assert target_b["wp_id"] == str(wp_b)
    assert target_b["wp_id"] != str(wp_a)


async def test_project_b_cannot_load_project_a_workpaper(db: AsyncSession, two_projects):
    """隔离闸：用项目 B 的 project_id 去 load 项目 A 的 wp_id ⇒ 404（证据端点据此拒绝跨项目挂载）。"""
    pa, pb, wp_a, wp_b, _ = two_projects
    # 本项目 load 正常
    loaded = await load_workpaper(db, wp_a, project_id=pa.id)
    assert isinstance(loaded, IntakeWorkpaper)
    assert loaded.id == wp_a
    # 跨项目 load ⇒ 404
    with pytest.raises(HTTPException) as exc:
        await load_workpaper(db, wp_a, project_id=pb.id)
    assert exc.value.status_code == 404


async def test_project_a_evidence_not_visible_through_project_b_wp(db: AsyncSession, two_projects):
    """A 的证据链接只在 A 的 wp_id 查询里出现，B 的 wp_id 查询为空。"""
    pa, pb, wp_a, wp_b, att_a = two_projects
    svc = WpEvidenceService(db)
    links_a = await svc.list_links(wp_a)
    links_b = await svc.list_links(wp_b)
    assert len(links_a) == 1
    assert links_a[0]["attachment"]["id"] == str(att_a.id)
    assert links_b == []  # B 的壳上没有任何证据，A 的证据绝不漏到 B


async def test_project_a_attachment_cannot_link_to_project_b_shell(db: AsyncSession, two_projects):
    """A 的附件不能链接到 B 的薄壳（附件与底稿必须同项目）⇒ 404。"""
    pa, pb, wp_a, wp_b, att_a = two_projects
    svc = WpEvidenceService(db)
    wp_b_intake = IntakeWorkpaper(id=wp_b, project_id=pb.id, wp_code="A3-CONSOL")
    with pytest.raises(HTTPException) as exc:
        await svc.assert_attachments_in_wp(wp_b_intake, [att_a.id])
    assert exc.value.status_code == 404
