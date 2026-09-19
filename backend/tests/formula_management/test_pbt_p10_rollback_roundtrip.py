# Feature: formula-management-library, Property 10: 一键刷新回滚往返
"""属性测试 P10：一键刷新回滚往返（Task 5.10）。

**Property 10: 一键刷新回滚往返**

*对任意*刷新前数据状态，执行一键刷新后再依据该次刷新的回滚快照回滚，数据恢复到
刷新前状态（round-trip：``rollback(refresh(s)) == s``）；被覆盖内容在覆盖前必已纳入
回滚快照（Req 4.2）。

被测：``app.services.draft_refresh_service.DraftRefreshService`` 的 ``refresh`` + ``rollback``
（design §Components 1）。本属性以 Hypothesis 随机生成刷新前的 ``draft_marker`` 状态集
（含三类初始形态）：

- **new**（无既有标记）：刷新新建 ``draft`` 标记 → 回滚应删除，恢复"无标记"；
- **既有 draft / human_edited**（``before_value=None``，快照落 ``marker_state`` 元信息）：
  回滚应精确还原刷新前 ``state``；
- **覆盖人工编辑**（``before_value`` 为业务数据 + ``editor_id``）：快照落业务数据 +
  ``editor_id`` → 回滚应依 ``editor_id`` 还原为 ``human_edited``。

断言 round-trip：刷新+回滚后每个单元的 ``draft_marker`` 状态精确等于刷新前状态
（既有→还原、新建→删除、覆盖人工编辑→依 editor_id 还原 human_edited）；被覆盖单元
在覆盖前均已进入回滚快照（``snapshotted_units``）；审计记录标 ``rolled_back``。

Framework: hypothesis（遵循 conftest fast profile，max_examples 可经
HYPOTHESIS_MAX_EXAMPLES 覆盖）。用内存 sqlite（参考 test_draft_refresh_rollback.py），
每个 example 独立建库以隔离状态。

**Validates: Requirements 4.2, 4.5**
"""
from __future__ import annotations

import asyncio
import uuid
from decimal import Decimal

import sqlalchemy as sa
from hypothesis import given
from hypothesis import strategies as st
from sqlalchemy import MetaData
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.models.audit_platform_models import (
    AccountCategory,
    TbAuxBalance,
    TbBalance,
    TbLedger,
    TrialBalance,
)
from app.models.dataset_models import LedgerDataset
from app.models.workpaper_models import (
    DraftMarker,
    DraftRefreshAudit,
    DraftRefreshSnapshot,
)
from app.services.draft_refresh_service import DraftRefreshService, RefreshUnit

# JSONB / ARRAY 在 sqlite 上的编译适配（与 test_draft_refresh_rollback.py 一致）。
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
if not hasattr(SQLiteTypeCompiler, "visit_ARRAY"):
    SQLiteTypeCompiler.visit_ARRAY = lambda self, type_, **kw: "TEXT"

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


class _Operator:
    """最小 User 替身：refresh / rollback 只取 id / role。"""

    def __init__(self, role: str = "partner"):
        self.id = uuid.uuid4()
        self.role = role


def _seed_core():
    """四表库核心种子：使 precheck 不阻断（tb_balance + trial_balance 非空）。"""
    return [
        TbBalance(
            project_id=PROJECT_ID, year=YEAR, company_code="C1",
            account_code="1001", account_name="库存现金",
            closing_balance=Decimal("100"),
        ),
        TrialBalance(
            project_id=PROJECT_ID, year=YEAR, company_code="C1",
            standard_account_code="1001", account_name="库存现金",
            account_category=AccountCategory.asset, unadjusted_amount=Decimal("100"),
        ),
    ]


# ── 生成器：随机刷新前 draft_marker 状态集（含三类初始形态）─────────────────
#
# 每个单元一个 kind，决定刷新前状态与刷新时的 before_value / editor_id：
#   "new"          → 刷新前无标记；          before_value=None
#   "draft_meta"   → 刷新前 state='draft';   before_value=None（快照落 marker_state）
#   "human_meta"   → 刷新前 state='human';   before_value=None（快照落 marker_state）
#   "human_editor" → 刷新前 state='human';   before_value=业务数据 + editor_id
_KINDS = ["new", "draft_meta", "human_meta", "human_editor"]


@st.composite
def _marker_sets(draw):
    """随机 1..6 个单元的初始形态列表；unit_scope 以下标保证唯一。"""
    kinds = draw(st.lists(st.sampled_from(_KINDS), min_size=1, max_size=6))
    units = []
    for i, kind in enumerate(kinds):
        unit_scope = f"report:U{i}"
        editor_id = uuid.uuid4() if kind == "human_editor" else None
        before_value = {"v": draw(st.integers(min_value=-1000, max_value=1000))} \
            if kind == "human_editor" else None
        units.append(
            {
                "kind": kind,
                "unit_scope": unit_scope,
                "editor_id": editor_id,
                "before_value": before_value,
            }
        )
    return units


def _pre_state(kind: str) -> str | None:
    """刷新前 draft_marker 状态（None 表示无标记）。"""
    if kind == "new":
        return None
    if kind == "draft_meta":
        return "draft"
    return "human_edited"  # human_meta / human_editor


async def _run_scenario(units: list[dict]) -> dict:
    """在独立内存 sqlite 中执行 refresh → rollback，返回断言所需的纯数据快照。

    每个 example 新建 engine（StaticPool 使 :memory: 在连接间共享），执行后 dispose，
    彻底隔离 example 间状态。
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    try:
        async with engine.begin() as conn:
            await conn.run_sync(
                lambda sc: MetaData().create_all(sc, tables=_TEST_TABLES)
            )
        session_factory = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )
        async with session_factory() as db:
            # 种子 + 刷新前 draft_marker 状态集
            db.add_all(_seed_core())
            for u in units:
                pre = _pre_state(u["kind"])
                if pre is not None:
                    db.add(
                        DraftMarker(
                            project_id=PROJECT_ID, year=YEAR,
                            unit_scope=u["unit_scope"], state=pre,
                        )
                    )
            await db.commit()

            svc = DraftRefreshService()

            # 一键刷新（confirm_overwrite=True 使人工编辑单元也被覆盖）
            refresh_units = [
                RefreshUnit(
                    u["unit_scope"],
                    before_value=u["before_value"],
                    editor_id=u["editor_id"],
                )
                for u in units
            ]
            refreshed = await svc.refresh(
                db, project_id=PROJECT_ID, year=YEAR, operator=_Operator(),
                scope="report", units=refresh_units, confirm_overwrite=True,
            )
            await db.commit()

            # 刷新后：所有单元均应为 draft（刷新已覆盖/新建）
            post_refresh_states = await _marker_states(db)

            # 依据本次刷新回滚
            result = await svc.rollback(
                db, refresh_id=refreshed.refresh_id, operator=_Operator(),
            )
            await db.commit()

            # 回滚后 marker 状态集（缺失表示被删除）
            post_rollback_states = await _marker_states(db)

            audit = (
                await db.execute(
                    sa.select(DraftRefreshAudit).where(
                        DraftRefreshAudit.id == refreshed.refresh_id
                    )
                )
            ).scalar_one()

            return {
                "snapshotted_units": sorted(refreshed.snapshotted_units),
                "refreshed_units": sorted(refreshed.refreshed_units),
                "post_refresh_states": post_refresh_states,
                "rollback_status": result.status,
                "restored_markers": sorted(result.restored_markers),
                "removed_markers": sorted(result.removed_markers),
                "post_rollback_states": post_rollback_states,
                "audit_status": audit.result_status,
            }
    finally:
        await engine.dispose()


async def _marker_states(db: AsyncSession) -> dict[str, str]:
    """当前所有 draft_marker 的 unit_scope → state 映射（缺失即无标记）。"""
    rows = (await db.execute(sa.select(DraftMarker))).scalars().all()
    return {m.unit_scope: m.state for m in rows}


@given(units=_marker_sets())
def test_p10_rollback_refresh_roundtrip(units):
    """P10：rollback(refresh(s)) == s —— 刷新+回滚精确还原刷新前状态。

    **Validates: Requirements 4.2, 4.5**
    """
    out = asyncio.run(_run_scenario(units))

    # 刷新前状态 s（以 unit_scope 唯一去重：同 unit_scope 取最后一次形态）。
    pre_states: dict[str, str | None] = {}
    overwrite_units: set[str] = set()
    for u in units:
        pre = _pre_state(u["kind"])
        pre_states[u["unit_scope"]] = pre
        # 覆盖 = 刷新前已有标记（marker 存在） or 带 before_value
        if pre is not None or u["before_value"] is not None:
            overwrite_units.add(u["unit_scope"])

    # ── 前提：刷新确实把所有单元置为 draft（否则往返无意义）──
    for scope in pre_states:
        assert out["post_refresh_states"].get(scope) == "draft", (
            f"刷新后 {scope} 应为 draft，实际 {out['post_refresh_states'].get(scope)}"
        )

    # ── Req 4.2：被覆盖内容在覆盖前必已纳入回滚快照 ──
    assert out["snapshotted_units"] == sorted(overwrite_units), (
        "被覆盖单元必须在覆盖前全部进入回滚快照"
    )

    # ── 回滚成功且审计标 rolled_back（Req 4.5）──
    assert out["rollback_status"] == "rolled_back"
    assert out["audit_status"] == "rolled_back"

    # ── round-trip：回滚后每个单元状态精确等于刷新前状态 s ──
    for scope, pre in pre_states.items():
        post = out["post_rollback_states"].get(scope)
        assert post == pre, (
            f"往返未还原 {scope}：刷新前={pre!r}，回滚后={post!r}"
        )

    # ── marker 变更分类正确：新建→删除、既有→还原 ──
    expected_removed = sorted(s for s, p in pre_states.items() if p is None)
    expected_restored = sorted(s for s, p in pre_states.items() if p is not None)
    assert out["removed_markers"] == expected_removed
    assert out["restored_markers"] == expected_restored
