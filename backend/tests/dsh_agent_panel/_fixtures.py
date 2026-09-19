# Feature: dsh-agent-panel-integration — Task 1 共享授权夹具
"""五角色 × 跨项目 × 跨循环 × private/project_group 的共享测试夹具。

Requirements: 2.2, 2.6, 2.7（五角色矩阵至少覆盖允许 / 拒绝 / 跨项目 / 跨循环 /
private+project_group 知识库五类边界）。

**真实 PostgreSQL + 事务隔离**：授权判定链路里 ``VisibilityQueryService`` 的
``UNION ALL`` / ``= ANY(CAST(:scope AS varchar[]))`` 与 ``knowledge_*`` 的 JSONB
语义都必须在 PG 上验证，sqlite 会给出假绿。每个用例在独立连接 + 独立事务内插入并
**整体回滚**，绝不污染 dev 库。

夹具拓扑（一次构建，供全部矩阵用例复用）::

    project_a（当前项目，audit_year=2025）      project_b（跨项目对照）
      ├─ wp_d      audit_cycle="D"（在 scope 内）  ├─ wp_other  audit_cycle="D"
      ├─ wp_e      audit_cycle="E"（越出 scope）   └─ note_b    附注实例（跨项目）
      ├─ note_a    附注实例（disclosure_notes）
      ├─ report_row_a  报表行次（financial_report / balance_sheet）
      └─ 成员：partner / manager / auditor / qc / eqcr
              ProjectUser.scope_cycles = "D"
              partner/manager/qc/eqcr → supervisor（唯一 staff+assignment+project_user 链路）
              auditor                 → restricted（仅凭 working_paper.assigned_to 的 lead 委派可见）

    知识库
      ├─ folder_public          public
      ├─ folder_group_a         project_group → [project_a]
      ├─ folder_group_b         project_group → [project_b]
      └─ folder_private_auditor private（created_by = auditor）

角色到分类的映射由平台既有 ``VisibilityRoleClassifier`` 决定，本夹具不复制该逻辑：
只负责把"唯一 active StaffMember + 唯一 active ProjectAssignment + 唯一 active
ProjectUser"这三条链路按角色摆好，让分类器自己产出 supervisor / restricted。
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import settings as app_settings
from app.models.base import ProjectUserRole, UserRole
from app.models.core import Project, ProjectUser, User
from app.models.knowledge_models import (
    KnowledgeAccessLevel,
    KnowledgeDocument,
    KnowledgeFolder,
)
from app.models.report_models import (
    DisclosureNote,
    FinancialReport,
    FinancialReportType,
)
from app.models.staff_models import ProjectAssignment, StaffMember
from app.models.workpaper_models import WorkingPaper, WpIndex, WpSourceType
from app.services.wp_visibility.denial import DenialResponder

IS_PG = app_settings.DATABASE_URL.startswith("postgresql")

#: 五角色（系统角色 = capability actor；与 Requirements §2 角色表一一对应）。
AUDIT_ROLES: tuple[str, ...] = ("auditor", "manager", "partner", "qc", "eqcr")

#: 角色的中文名（断言失败信息可读；取自平台冻结的显示名）。
ROLE_LABELS: dict[str, str] = {
    "auditor": "审计助理",
    "manager": "现场经理",
    "partner": "业务合伙人",
    "qc": "质量控制复核合伙人",
    "eqcr": "EQCR 技术复核人",
}

#: 在 scope 内 / 越出 scope 的审计循环。
IN_SCOPE_CYCLE = "D"
OUT_OF_SCOPE_CYCLE = "E"
SCOPE_CYCLES = IN_SCOPE_CYCLE


class RecordingDenialResponder(DenialResponder):
    """记录型 denial 审计器：走真实 ``deny()`` 代码路径（含 detail 脱敏），但不写库。

    ``DenialResponder._enqueue`` 用**独立 session** 提交 outbox；测试若使用默认实现会真的
    写进 dev 库。此处只覆写 ``_enqueue`` 记录字段，``deny()`` 依旧以 ``ExternalNotFound``
    结束，因此"审计先于抛出"的顺序仍被真实执行。
    """

    def __init__(self) -> None:
        super().__init__()
        self.records: list[dict[str, Any]] = []

    async def _enqueue(self, **fields: Any) -> None:  # noqa: D401
        from app.services.wp_visibility.denial import _scrub_identifiers

        record = dict(fields)
        record["detail"] = _scrub_identifiers(fields.get("detail"))
        self.records.append(record)


@dataclass
class RoleActor:
    """一个角色对应的用户 + 其映射链路。"""

    role: str
    user: User
    staff: StaffMember

    @property
    def id(self) -> UUID:
        return self.user.id

    @property
    def label(self) -> str:
        return ROLE_LABELS.get(self.role, self.role)


#: 夹具项目的权威审计年度（``projects.audit_year``）。Task 2 的 year 断言一致性判据依赖它：
#: 服务端反查出该年度后，客户端断言任何别的年度都必须被判 ``host_context_mismatch``。
FIXTURE_AUDIT_YEAR = 2025

#: 夹具报表宿主的 report type（取值域真源 = ``contracts.REPORT_HOST_IDS``）。
FIXTURE_REPORT_TYPE = "balance_sheet"


@dataclass
class AccessFixture:
    """五角色 × 跨项目 × 跨循环 × 知识库权限的完整夹具。"""

    session: AsyncSession
    project_a: Project
    project_b: Project
    actors: dict[str, RoleActor]
    outsider: User
    wp_d: WpIndex
    wp_d_file: WorkingPaper
    wp_e: WpIndex
    wp_e_file: WorkingPaper
    wp_other: WpIndex
    wp_other_file: WorkingPaper
    folder_public: KnowledgeFolder
    folder_group_a: KnowledgeFolder
    folder_group_b: KnowledgeFolder
    folder_private_auditor: KnowledgeFolder
    doc_public: KnowledgeDocument
    doc_group_a: KnowledgeDocument
    doc_group_b: KnowledgeDocument
    doc_private_auditor: KnowledgeDocument
    doc_private_explicit: KnowledgeDocument
    # ── Task 2 宿主反查用的附注 / 报表实例（每宿主钉在自己的业务模型上） ──
    note_a: DisclosureNote
    note_b: DisclosureNote
    report_row_a: FinancialReport
    responder: RecordingDenialResponder = field(default_factory=RecordingDenialResponder)

    def actor(self, role: str) -> RoleActor:
        return self.actors[role]

    @property
    def all_actors(self) -> list[RoleActor]:
        return [self.actors[r] for r in AUDIT_ROLES]


async def _mk_user(s: AsyncSession, role: str) -> User:
    u = User(
        username=f"ai_{role}_{uuid.uuid4().hex[:10]}",
        email=f"{uuid.uuid4().hex[:12]}@ai.example",
        hashed_password="x",
        role=UserRole(role),
        is_active=True,
    )
    s.add(u)
    await s.flush()
    return u


async def _mk_project(s: AsyncSession, name: str) -> Project:
    p = Project(
        name=f"{name}_{uuid.uuid4().hex[:8]}",
        client_name="AI 授权夹具客户",
        # 权威审计年度：Task 2 的 year 断言一致性判据从这里反查（不是客户端传什么算什么）。
        audit_year=FIXTURE_AUDIT_YEAR,
    )
    s.add(p)
    await s.flush()
    return p


async def _mk_note(
    s: AsyncSession,
    project_id: UUID,
    *,
    year: int = FIXTURE_AUDIT_YEAR,
    section: str | None = None,
) -> DisclosureNote:
    """附注章节实例（``disclosure_notes``）—— note 宿主的权威业务模型。"""
    note_section = section or f"五、{uuid.uuid4().hex[:4]}"
    n = DisclosureNote(
        project_id=project_id,
        year=year,
        note_section=note_section,
        section_title="货币资金（授权夹具）",
        section_id=f"sec_{uuid.uuid4().hex[:8]}",
        text_content="附注正文（授权通过后才允许读取）",
        table_data={"rows": [{"label": "银行存款", "values": ["1000.00", "900.00"]}]},
    )
    s.add(n)
    await s.flush()
    return n


async def _mk_report_row(
    s: AsyncSession,
    project_id: UUID,
    *,
    year: int = FIXTURE_AUDIT_YEAR,
    report_type: str = FIXTURE_REPORT_TYPE,
) -> FinancialReport:
    """报表行次（``financial_report``）—— report 宿主的权威业务模型。

    报表实例由 ``(project, year, report_type)`` 唯一确定，没有 instance UUID：
    宿主反查靠"该组合下是否存在行次"判定是否已实例化。
    """
    r = FinancialReport(
        project_id=project_id,
        year=year,
        report_type=FinancialReportType(report_type),
        row_code="1001",
        row_name="货币资金",
        current_period_amount=1000,
        prior_period_amount=900,
    )
    s.add(r)
    await s.flush()
    return r


async def _mk_wp(
    s: AsyncSession,
    project_id: UUID,
    cycle: str,
    *,
    assigned_to: UUID | None = None,
) -> tuple[WpIndex, WorkingPaper]:
    wi = WpIndex(
        project_id=project_id,
        wp_code=f"AI-{uuid.uuid4().hex[:8]}",
        wp_name="授权夹具底稿",
        audit_cycle=cycle,
    )
    s.add(wi)
    await s.flush()
    wp = WorkingPaper(
        project_id=project_id,
        wp_index_id=wi.id,
        file_path=f"/tmp/{uuid.uuid4().hex[:8]}.xlsx",
        source_type=WpSourceType.template,
        file_version=1,
        assigned_to=assigned_to,
    )
    s.add(wp)
    await s.flush()
    return wi, wp


async def _mk_folder(
    s: AsyncSession,
    *,
    access_level: KnowledgeAccessLevel,
    project_ids: list[str] | None = None,
    created_by: UUID | None = None,
) -> KnowledgeFolder:
    f = KnowledgeFolder(
        id=uuid.uuid4(),
        name=f"folder_{uuid.uuid4().hex[:8]}",
        parent_id=None,
        access_level=access_level,
        project_ids=project_ids,
        created_by=created_by,
    )
    s.add(f)
    await s.flush()
    return f


async def _mk_doc(
    s: AsyncSession,
    folder_id: UUID,
    *,
    access_level: KnowledgeAccessLevel | None = None,
    project_ids: list[str] | None = None,
    created_by: UUID | None = None,
) -> KnowledgeDocument:
    d = KnowledgeDocument(
        id=uuid.uuid4(),
        folder_id=folder_id,
        name=f"doc_{uuid.uuid4().hex[:8]}.md",
        content_text="夹具正文（授权通过后才允许读取）",
        content_summary="夹具摘要",
        access_level=access_level,
        project_ids=project_ids,
        created_by=created_by,
    )
    s.add(d)
    await s.flush()
    return d


async def build_access_fixture(s: AsyncSession) -> AccessFixture:
    """在给定（可回滚）session 内构建完整夹具。"""
    project_a = await _mk_project(s, "ai_project_a")
    project_b = await _mk_project(s, "ai_project_b")

    actors: dict[str, RoleActor] = {}
    for role in AUDIT_ROLES:
        user = await _mk_user(s, role)
        staff = StaffMember(name=f"staff_{role}_{uuid.uuid4().hex[:6]}", user_id=user.id)
        s.add(staff)
        await s.flush()
        # 角色权威 = ProjectAssignment.role；scope 权威 = ProjectUser.scope_cycles。
        s.add(ProjectAssignment(project_id=project_a.id, staff_id=staff.id, role=role))
        s.add(
            ProjectUser(
                project_id=project_a.id,
                user_id=user.id,
                role=ProjectUserRole(role),
                scope_cycles=SCOPE_CYCLES,
            )
        )
        await s.flush()
        actors[role] = RoleActor(role=role, user=user, staff=staff)

    # 跨项目对照：只属于 project_b 的用户（对 project_a 的一切资源都应不可见）。
    outsider = await _mk_user(s, "auditor")
    outsider_staff = StaffMember(
        name=f"staff_outsider_{uuid.uuid4().hex[:6]}", user_id=outsider.id
    )
    s.add(outsider_staff)
    await s.flush()
    s.add(
        ProjectUser(
            project_id=project_b.id,
            user_id=outsider.id,
            role=ProjectUserRole.auditor,
            scope_cycles=SCOPE_CYCLES,
        )
    )
    await s.flush()

    auditor_id = actors["auditor"].id
    # auditor 是 restricted：靠 working_paper.assigned_to 的 lead 委派才可见。
    wp_d, wp_d_file = await _mk_wp(
        s, project_a.id, IN_SCOPE_CYCLE, assigned_to=auditor_id
    )
    # 同样委派给 auditor，但循环越出 scope_cycles → 任何角色都不可见（跨循环边界）。
    wp_e, wp_e_file = await _mk_wp(
        s, project_a.id, OUT_OF_SCOPE_CYCLE, assigned_to=auditor_id
    )
    # 跨项目底稿：project_a 的五个成员都不应可见。
    wp_other, wp_other_file = await _mk_wp(
        s, project_b.id, IN_SCOPE_CYCLE, assigned_to=outsider.id
    )

    folder_public = await _mk_folder(s, access_level=KnowledgeAccessLevel.public)
    folder_group_a = await _mk_folder(
        s,
        access_level=KnowledgeAccessLevel.project_group,
        project_ids=[str(project_a.id)],
    )
    folder_group_b = await _mk_folder(
        s,
        access_level=KnowledgeAccessLevel.project_group,
        project_ids=[str(project_b.id)],
    )
    folder_private_auditor = await _mk_folder(
        s, access_level=KnowledgeAccessLevel.private, created_by=auditor_id
    )

    # 附注 / 报表实例：note 与 report 宿主必须从自己的业务模型反查项目与年度（Req 3.2/3.7）。
    note_a = await _mk_note(s, project_a.id)
    note_b = await _mk_note(s, project_b.id)
    report_row_a = await _mk_report_row(s, project_a.id)

    doc_public = await _mk_doc(s, folder_public.id)
    doc_group_a = await _mk_doc(s, folder_group_a.id)
    doc_group_b = await _mk_doc(s, folder_group_b.id)
    doc_private_auditor = await _mk_doc(s, folder_private_auditor.id)
    # 显式 private 文档挂在 public 文件夹下（文档级权限优先于文件夹继承）。
    doc_private_explicit = await _mk_doc(
        s,
        folder_public.id,
        access_level=KnowledgeAccessLevel.private,
        created_by=actors["manager"].id,
    )

    return AccessFixture(
        session=s,
        project_a=project_a,
        project_b=project_b,
        actors=actors,
        outsider=outsider,
        wp_d=wp_d,
        wp_d_file=wp_d_file,
        wp_e=wp_e,
        wp_e_file=wp_e_file,
        wp_other=wp_other,
        wp_other_file=wp_other_file,
        folder_public=folder_public,
        folder_group_a=folder_group_a,
        folder_group_b=folder_group_b,
        folder_private_auditor=folder_private_auditor,
        doc_public=doc_public,
        doc_group_a=doc_group_a,
        doc_group_b=doc_group_b,
        doc_private_auditor=doc_private_auditor,
        doc_private_explicit=doc_private_explicit,
        note_a=note_a,
        note_b=note_b,
        report_row_a=report_row_a,
    )


def run_with_fixture(coro_fn, *, capture_sql: bool = False):
    """在独立引擎/连接/事务内构建夹具、执行 ``coro_fn(fixture)``，结束整体回滚。

    ``capture_sql=True`` 时额外挂 ``before_cursor_execute`` 监听器，把 **夹具构建之后**
    发出的每条 SQL 收集到 ``fixture_sql_log``（供"拒绝前零读取"断言）。
    """
    sql_log: list[str] = []

    async def _wrap():
        engine = create_async_engine(app_settings.DATABASE_URL)
        conn = await engine.connect()
        trans = await conn.begin()
        s = AsyncSession(bind=conn)
        listener = None
        try:
            fixture = await build_access_fixture(s)
            if capture_sql:
                from sqlalchemy import event

                sync_engine = conn.sync_engine

                def _on_exec(_c, _cur, statement, _p, _ctx, _m):  # noqa: ANN001
                    sql_log.append(statement)

                event.listen(sync_engine, "before_cursor_execute", _on_exec)
                listener = (sync_engine, _on_exec)
            return await coro_fn(fixture, sql_log)
        finally:
            if listener is not None:
                from sqlalchemy import event

                event.remove(listener[0], "before_cursor_execute", listener[1])
            await s.close()
            await trans.rollback()
            await conn.close()
            await engine.dispose()

    return asyncio.run(_wrap())
