# Feature: formula-management-library, Property 18: 审计留痕完整且不可篡改
"""属性测试 P18：审计留痕完整且不可篡改（Task 5.11）。

**Property 18: 审计留痕完整且不可篡改**

*对任意*成功的一键刷新场景，``DraftRefreshService.refresh`` 写入的
``draft_refresh_audit`` 记录必须：

1. **完整（Req 4.1）**：记录操作者身份（``operator_id`` + ``operator_role``）、
   操作时间（``operated_at``）、目标 ``project_id`` 与 ``year``、触发范围（``scope``）
   与受影响记录数（``affected_count``），且各字段值与本次刷新输入/结果一致；
   幂等键 ``tb_snapshot_hash`` 非空、``result_status='success'``。
2. **不可篡改 / append-only（Req 4.6）**：
   - ``DraftRefreshService`` **不暴露任何删除/篡改审计的方法**（普通用户无从删改）——
     以内省断言 service 公共方法名不含 delete/remove/drop/purge/erase/tamper 等语义；
   - 审计为 **append-only**：后续（数据变更后的）刷新只 **追加** 新审计行，行数单调
     不减（1 → 2），且**先前写入的审计行按主键回查其所有字段逐字不变**（操作者/时间/
     scope/affected_count/result_status/hash 均未被覆盖），体现"变更产生新记录而非改写
     旧记录"的不可篡改语义。

被测：``app.services.draft_refresh_service.DraftRefreshService.refresh``
写入的 ``draft_refresh_audit``（design §Components 1；模型 append-only、不暴露
UPDATE/DELETE 端点给普通用户，见 ``DraftRefreshAudit`` docstring）。

- 用内存 SQLite（``:memory:`` + ``aiosqlite``）建四表库
  （trial_balance / tb_balance / tb_ledger / tb_aux_balance）+ ``ledger_datasets``
  + ``draft_marker`` / ``draft_refresh_audit`` / ``draft_refresh_snapshot`` 三表，
  参考 ``backend/tests/test_draft_refresh_refresh.py`` 的 fixture / 种子模式。
- Hypothesis 随机生成"成功刷新"场景：非零金额四表库快照（保证 precheck 通过）、
  scope（单值 / 多值）与初稿单元集合（units）。

Framework: hypothesis（遵循 conftest fast profile，max_examples 可经
HYPOTHESIS_MAX_EXAMPLES 覆盖），每个 example 独立建库以隔离状态。

**Validates: Requirements 4.1, 4.6**
"""

from __future__ import annotations

import asyncio
import re
import uuid
from datetime import datetime
from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy import MetaData
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler

# SQLite 测试方言：JSONB → JSON 编译；PG ARRAY → TEXT 兜底（建表所需）。
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
if not hasattr(SQLiteTypeCompiler, "visit_ARRAY"):
    SQLiteTypeCompiler.visit_ARRAY = lambda self, type_, **kw: "TEXT"

import sqlalchemy as sa  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.models.audit_platform_models import (  # noqa: E402
    AccountCategory,
    TbAuxBalance,
    TbBalance,
    TbLedger,
    TrialBalance,
)
from app.models.dataset_models import LedgerDataset  # noqa: E402
from app.models.workpaper_models import (  # noqa: E402
    DraftMarker,
    DraftRefreshAudit,
    DraftRefreshSnapshot,
)
from app.services.draft_refresh_service import (  # noqa: E402
    DraftRefreshService,
    RefreshUnit,
)

PROJECT_ID = uuid.uuid4()
YEAR = 2025

_TEST_TABLES = [
    TbBalance.__table__,
    TbLedger.__table__,
    TbAuxBalance.__table__,
    TrialBalance.__table__,
    LedgerDataset.__table__,
    DraftMarker.__table__,
    DraftRefreshAudit.__table__,
    DraftRefreshSnapshot.__table__,
]

# 禁止在 service 上出现的"删除/篡改审计"方法语义（Req 4.6 append-only）。
_FORBIDDEN_MUTATION_VERBS = re.compile(
    r"(delete|remove|drop|purge|erase|destroy|truncate|wipe|tamper|falsif)",
    re.IGNORECASE,
)


class _Operator:
    """最小 User 替身：refresh 只取 id / role。"""

    def __init__(self, role: str = "partner"):
        self.id = uuid.uuid4()
        self.role = role


# ─────────────────────────────────────────────────────────────────────────────
# 独立内存 sqlite：refresh 为协程；每个 example 用独立引擎隔离状态。
# ─────────────────────────────────────────────────────────────────────────────
async def _make_session():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: MetaData().create_all(sync_conn, tables=_TEST_TABLES)
        )
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return factory, engine


def _seed_rows(accounts: list[tuple[str, int]]):
    """由 (account_code, amount) 列表种子四表库核心两表（保证 precheck 通过）。

    - tb_balance：closing_balance = amount。
    - trial_balance：unadjusted_amount = amount（正整数 → 存在非零未审数）。
    """
    rows: list = []
    for code, amount in accounts:
        rows.append(
            TbBalance(
                project_id=PROJECT_ID,
                year=YEAR,
                company_code="C1",
                account_code=code,
                account_name=f"科目{code}",
                closing_balance=Decimal(amount),
            )
        )
        rows.append(
            TrialBalance(
                project_id=PROJECT_ID,
                year=YEAR,
                company_code="C1",
                standard_account_code=code,
                account_name=f"科目{code}",
                account_category=AccountCategory.asset,
                unadjusted_amount=Decimal(amount),
            )
        )
    return rows


async def _count(db, model) -> int:
    return int(
        (await db.execute(sa.select(sa.func.count()).select_from(model))).scalar() or 0
    )


def _audit_field_snapshot(a: DraftRefreshAudit) -> dict:
    """把一条审计行的所有可核字段抽成纯值字典，供 append-only 逐字比对。"""
    return {
        "id": a.id,
        "project_id": a.project_id,
        "year": a.year,
        "operator_id": a.operator_id,
        "operator_role": a.operator_role,
        "operated_at": a.operated_at,
        "scope": a.scope,
        "tb_snapshot_hash": a.tb_snapshot_hash,
        "affected_count": a.affected_count,
        "result_status": a.result_status,
        "detail": dict(a.detail or {}),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 智能生成器：约束到"成功刷新"的输入空间。
# ─────────────────────────────────────────────────────────────────────────────

# 账户快照：唯一 code + 正整数金额（保证 precheck 通过、hash 确定）。
_SNAPSHOT = st.lists(
    st.tuples(
        st.integers(min_value=1000, max_value=9999).map(str),
        st.integers(min_value=1, max_value=1_000_000),
    ),
    min_size=1,
    max_size=5,
    unique_by=lambda t: t[0],
)

# scope：单值 或 多值序列（多值验证归一化排序后写入 scope 列）。
_SCOPE = st.sampled_from(
    [
        "report",
        "note",
        "audit_sheet",
        ("report", "note"),
        ("note", "report"),
    ]
)

# units：初稿单元集合（unit_scope 唯一，至少 1 个）。
_UNITS = st.lists(
    st.builds(lambda i: f"report:R-{i}", st.integers(min_value=0, max_value=50)),
    min_size=1,
    max_size=5,
    unique=True,
)


def _scope_key(scope) -> str:
    """复刻 service 的 scope 归一化：单值原样；多值排序去重后逗号连接。"""
    if isinstance(scope, str):
        return scope
    return ",".join(sorted({str(s) for s in scope if str(s)}))


@given(accounts=_SNAPSHOT, scope=_SCOPE, unit_scopes=_UNITS)
@settings(max_examples=100)
def test_p18_audit_trail_complete_and_immutable(accounts, scope, unit_scopes):
    """P18：成功刷新写入的审计记录完整（Req 4.1）且 append-only 不可篡改（Req 4.6）。

    **Validates: Requirements 4.1, 4.6**
    """

    # ── Req 4.6（结构层）：service 不暴露任何删除/篡改审计的方法 ──
    svc = DraftRefreshService()
    for name in dir(svc):
        if name.startswith("_"):
            continue
        if not callable(getattr(svc, name)):
            continue
        assert not _FORBIDDEN_MUTATION_VERBS.search(name), (
            f"DraftRefreshService 暴露了疑似删除/篡改方法 {name!r}，"
            f"违反审计 append-only 不可篡改（Req 4.6）"
        )

    async def _scenario():
        factory, engine = await _make_session()
        try:
            async with factory() as db:
                db.add_all(_seed_rows(accounts))
                await db.commit()

                operator = _Operator()
                units = [RefreshUnit(s) for s in unit_scopes]
                expected_scope = _scope_key(scope)

                # ── 第一次刷新：成功 ──
                first = await svc.refresh(
                    db,
                    project_id=PROJECT_ID,
                    year=YEAR,
                    operator=operator,
                    scope=scope,
                    units=units,
                )
                await db.commit()

                assert first.status == "success", first.blocking
                assert await _count(db, DraftRefreshAudit) == 1

                audit = (
                    await db.execute(
                        sa.select(DraftRefreshAudit).where(
                            DraftRefreshAudit.id == first.refresh_id
                        )
                    )
                ).scalar_one()

                # ── Req 4.1：审计记录完整且各字段与输入/结果一致 ──
                # 操作者身份
                assert audit.operator_id == operator.id
                assert audit.operator_role == operator.role
                # 操作时间
                assert isinstance(audit.operated_at, datetime)
                # 目标 project_id 与 year
                assert audit.project_id == PROJECT_ID
                assert audit.year == YEAR
                # 触发范围（归一化后的 scope 键）
                assert audit.scope == expected_scope
                # 受影响记录数 == 实际刷新单元数
                assert audit.affected_count == first.affected_count
                assert audit.affected_count == len(set(unit_scopes))
                # 幂等键非空 + 成功状态
                assert audit.tb_snapshot_hash
                assert audit.result_status == "success"

                # 记下第一条审计的全字段快照，供 append-only 逐字比对。
                before = _audit_field_snapshot(audit)

                # ── Req 4.6（行为层）：数据变更 → 再刷新只 append 新行，旧行不被改写 ──
                tb = (
                    await db.execute(sa.select(TrialBalance).limit(1))
                ).scalars().first()
                tb.unadjusted_amount = (tb.unadjusted_amount or Decimal(0)) + Decimal(1)
                await db.commit()

                second = await svc.refresh(
                    db,
                    project_id=PROJECT_ID,
                    year=YEAR,
                    operator=_Operator(),
                    scope=scope,
                    units=units,
                )
                await db.commit()

                # append-only：新增一条审计行（行数单调不减：1 → 2），无删除。
                assert second.status == "success"
                assert second.refresh_id != first.refresh_id
                assert await _count(db, DraftRefreshAudit) == 2

                # 先前写入的审计行按主键回查，所有字段逐字不变（未被覆盖/篡改）。
                reloaded = (
                    await db.execute(
                        sa.select(DraftRefreshAudit).where(
                            DraftRefreshAudit.id == first.refresh_id
                        )
                    )
                ).scalar_one()
                after = _audit_field_snapshot(reloaded)
                assert after == before, (
                    "先前审计记录在后续刷新后发生变化，违反 append-only 不可篡改（Req 4.6）"
                )
        finally:
            await engine.dispose()

    asyncio.run(_scenario())
