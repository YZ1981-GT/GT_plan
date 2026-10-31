"""Draft Refresh 幂等判定的取数（spec formula-hub-integrity-closure 任务 20 第一段 A-2c-2；ADR-FHIC-08「幂等」）。

只读：不写库、不 flush、不 commit、不发事件。判定本身是 :mod:`refresh_idempotency` 的纯函数；编排器在项目锁内、执行段之前
调本模块取数（``DraftRefreshOrchestrator.generate``）。

- :func:`report_basis`：勾选报表范围时进计划指纹的四项 :class:`~refresh_idempotency.ReportBasis` —— 试算表本项目年度未删行
  （科目码, 审定, 未审, 期初）的行哈希、``report_freshness.load_effective_formulas`` 给出的有效报表定义（类型, 行次,
  ``normalize_formula(公式)``）的行哈希、``report_freshness.CALC_VERSION``、本项目年度未删报表行里满足 ``stale_clause()``
  的行数；
- :func:`find_records` / :func:`find_prior` / :func:`count_occupied`：本项目年度「属于某个有效键」的审计记录 —— 条件 =
  ``idempotency_key`` 列 = 有效键，或 ``detail`` 的 :data:`~refresh_idempotency.DETAIL_BASE_KEY` = 有效键；排序
  ``operated_at DESC NULLS LAST, id DESC``（与 ``refresh_idempotency.latest`` 同口径；PostgreSQL 的 DESC 默认 NULLS FIRST）。

JSON 取值写 ``detail[键].as_string()``：PostgreSQL 编译为 ``CAST((detail ->> '键') AS VARCHAR)``、SQLite 编译为
``JSON_EXTRACT(detail, '$."键"')``，同一条语句两边都能执行（A-2c-2 两个方言各编译核对过），故不在 Python 侧再筛 ``detail``。
"""

from __future__ import annotations

from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import TrialBalance
from app.models.report_models import FinancialReport
from app.models.workpaper_models import DraftRefreshAudit
from app.services.formula_management.refresh_idempotency import DETAIL_BASE_KEY, ReportBasis, rows_hash
from app.services.report_freshness import CALC_VERSION, load_effective_formulas, normalize_formula, stale_clause


async def report_basis(db: AsyncSession, project_id: UUID, year: int) -> ReportBasis:
    """勾选报表范围时进计划指纹的四项（只读）。

    试算表只按本项目年度 + ``is_deleted = false`` 取（``trial_balance`` 没有数据集列，与 ``get_active_filter`` 对它给出的条件
    相同，且不经那条查询失败即回滚的降级路径）；有效报表定义按项目真实准则取，与年度无关。
    """
    tb = TrialBalance
    tb_rows = (await db.execute(
        sa.select(tb.standard_account_code, tb.audited_amount, tb.unadjusted_amount, tb.opening_balance)
        .where(tb.project_id == project_id, tb.year == year, tb.is_deleted == sa.false())
    )).all()
    formulas = await load_effective_formulas(db, project_id)
    fr = FinancialReport
    stale_count = (await db.execute(
        sa.select(sa.func.count()).select_from(fr)
        .where(fr.project_id == project_id, fr.year == year, fr.is_deleted == sa.false(), stale_clause())
    )).scalar_one()
    return ReportBasis(
        tb_rows_hash=rows_hash(tuple(row) for row in tb_rows),
        definitions_hash=rows_hash((kind, code, normalize_formula(text)) for (kind, code), text in formulas.items()),
        calc_version=CALC_VERSION,
        stale_count=int(stale_count),
    )


def _belongs_to(effective: str) -> sa.ColumnElement[bool]:
    """「属于有效键 ``effective``」：``idempotency_key`` 列 = 有效键，或 ``detail.idempotency_base`` = 有效键。"""
    audit = DraftRefreshAudit
    return sa.or_(audit.idempotency_key == effective, audit.detail[DETAIL_BASE_KEY].as_string() == effective)


def _records_statement(project_id: UUID, year: int, effective: str) -> sa.Select:
    """本项目年度属于 ``effective`` 的审计记录，最近的在前（``operated_at DESC NULLS LAST, id DESC``）。"""
    audit = DraftRefreshAudit
    return (
        sa.select(audit)
        .where(audit.project_id == project_id, audit.year == year, _belongs_to(effective))
        .order_by(audit.operated_at.desc().nulls_last(), audit.id.desc())
    )


async def find_records(db: AsyncSession, project_id: UUID, year: int, effective: str) -> list[DraftRefreshAudit]:
    return list((await db.execute(_records_statement(project_id, year, effective))).scalars().all())


async def find_prior(db: AsyncSession, project_id: UUID, year: int, effective: str) -> DraftRefreshAudit | None:
    """最近一条（与 ``refresh_idempotency.latest`` 同口径）；没有 ⇒ None。"""
    return (await db.execute(_records_statement(project_id, year, effective).limit(1))).scalars().first()


async def count_occupied(db: AsyncSession, project_id: UUID, year: int, effective: str) -> int:
    """属于 ``effective`` 的记录条数（与查找同一条件），给 ``refresh_idempotency.write_key`` 算写入键。"""
    audit = DraftRefreshAudit
    stmt = (
        sa.select(sa.func.count()).select_from(audit)
        .where(audit.project_id == project_id, audit.year == year, _belongs_to(effective))
    )
    return int((await db.execute(stmt)).scalar_one())
