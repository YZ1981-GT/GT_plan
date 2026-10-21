"""公式设置测试共享环境（非测试模块）：SQLite 真 ORM，表只建本 spec 用到的。"""
from __future__ import annotations

import uuid
from contextlib import asynccontextmanager

import sqlalchemy as sa
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

import app.models  # noqa: E402, F401  全量注册（外键引用的表要在 metadata 里）
from app.models.audit_log_models import AuditLogEntry  # noqa: E402
from app.models.base import Base, PermissionLevel, ProjectStatus  # noqa: E402
from app.models.core import Project, ProjectUser, User  # noqa: E402
from app.models.formula_setting_models import (  # noqa: E402
    FormulaPublish,
    FormulaSetting,
    FormulaSyncItem,
    FormulaTemplate,
    FormulaTemplateSubscription,
    FormulaTemplateVersion,
)
from app.models.report_models import FinancialReport, FinancialReportType, ReportConfig  # noqa: E402

MODELS = [User, Project, ProjectUser, ReportConfig, FinancialReport, FormulaSetting, FormulaSyncItem, FormulaPublish,
          FormulaTemplate, FormulaTemplateVersion, FormulaTemplateSubscription, AuditLogEntry]
STD = "soe_standalone"
BS = FinancialReportType.balance_sheet


@asynccontextmanager
async def make_db(extra_models=()):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(
            c, tables=[m.__table__ for m in (*MODELS, *extra_models)]))
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


async def add_project(db: AsyncSession, name: str, *, template_type: str = "soe", report_scope: str = "standalone",
                      status: ProjectStatus = ProjectStatus.execution, parent: uuid.UUID | None = None) -> uuid.UUID:
    pid = uuid.uuid4()
    db.add(Project(id=pid, name=name, client_name=name, status=status, template_type=template_type,
                   report_scope=report_scope, audit_year=2025, parent_project_id=parent))
    await db.flush()
    return pid


async def add_user(db: AsyncSession, username: str, role: str = "auditor") -> User:
    from app.models.base import UserRole

    user = User(id=uuid.uuid4(), username=username, email=f"{username}@example.com",
                hashed_password="x", role=UserRole(role), is_active=True)
    db.add(user)
    await db.flush()
    return user


async def add_member(db: AsyncSession, project_id: uuid.UUID, user: User, level: str = "edit") -> None:
    from app.models.base import ProjectUserRole

    db.add(ProjectUser(project_id=project_id, user_id=user.id, role=ProjectUserRole.auditor,
                       permission_level=PermissionLevel(level)))
    await db.flush()


async def add_global_row(db: AsyncSession, row_code: str, formula: str | None, *, standard: str = STD,
                         row_number: int = 1, row_name: str | None = None, report_type=BS) -> ReportConfig:
    row = ReportConfig(report_type=report_type, row_code=row_code, row_name=row_name or row_code,
                       row_number=row_number, indent_level=0, formula=formula, formula_category="auto_calc",
                       applicable_standard=standard, formula_version=1)
    db.add(row)
    await db.flush()
    return row


async def add_project_row(db: AsyncSession, project_id: uuid.UUID, row_code: str, formula: str | None, *,
                          base_formula: str | None = None, pinned: bool = False, base_version: int = 1,
                          report_type=BS, base_origin: str = "global") -> ReportConfig:
    base = None if base_formula is None else {"formula": base_formula, "formula_category": "auto_calc"}
    row = ReportConfig(report_type=report_type, row_code=row_code, row_name=row_code, row_number=1,
                       indent_level=0, formula=formula, formula_category="auto_calc",
                       applicable_standard=f"project:{project_id}", formula_version=1,
                       base_definition=base, base_version=base_version if base else None, pinned=pinned,
                       base_origin=base_origin if base else None)
    db.add(row)
    await db.flush()
    return row


async def project_rows(db: AsyncSession, project_id: uuid.UUID) -> dict[str, ReportConfig]:
    rows = (await db.execute(sa.select(ReportConfig).where(
        ReportConfig.applicable_standard == f"project:{project_id}"))).scalars().all()
    return {r.row_code: r for r in rows}


async def pending_items(db: AsyncSession, project_id: uuid.UUID | None = None) -> list[FormulaSyncItem]:
    q = sa.select(FormulaSyncItem).where(FormulaSyncItem.status == "pending")
    if project_id is not None:
        q = q.where(FormulaSyncItem.project_id == project_id)
    return list((await db.execute(q)).scalars().all())


async def audit_actions(db: AsyncSession) -> list[tuple[str, dict]]:
    rows = (await db.execute(sa.select(AuditLogEntry.action_type, AuditLogEntry.payload))).all()
    return [(r[0], r[1]) for r in rows]


def rdef(formula: str | None) -> dict:
    return {"formula": formula}
