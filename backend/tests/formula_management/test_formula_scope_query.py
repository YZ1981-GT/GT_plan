# Feature: formula-management-library, Task 20.2 — 公式作用域过滤端点（Req 24.1/24.5）
"""公式作用域过滤查询服务测试（formula-management-library Req 24 / Task 20.2）。

被测：``app.services.formula_management.formula_scope_query`` 的
``classify_scope`` / ``FormulaScopeQueryService.list_by_scope`` /
``list_grouped_by_scope``。

覆盖三组：
- ``scope_filter``：按 Formula_Scope 过滤只返回该作用域公式（Req 24.1/24.2）；
  分类为确定性单值函数（含合并族/顶层他域/兜底底稿）。
- ``scope_isolation``：一个作用域的编辑（增/改）仅改该作用域列表，其余作用域
  列表逐一不变（Req 24.5）；作用域划分互斥（无泄漏）。
- ``scope_query``：全局并集分组恰等于各作用域列表之并、且互不相交（Req 24.3）。

DB：内存 SQLite（``:memory:`` + ``aiosqlite``）+ SQLiteTypeCompiler patch 建
``wp_formula`` / ``working_paper`` / ``wp_index`` 三表（JOIN 派生作用域所需）。
遵循本套件既有同步 ``_run(coro)`` + 每 example 独立引擎隔离范式。

**Validates: Requirements 24.1, 24.5**
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler

# SQLite 测试方言：UUID → uuid 编译；JSONB → JSON 编译（建表所需）。
if hasattr(SQLiteTypeCompiler, "visit_uuid"):
    SQLiteTypeCompiler.visit_UUID = SQLiteTypeCompiler.visit_uuid
if not hasattr(SQLiteTypeCompiler, "visit_JSONB"):
    SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

import sqlalchemy as sa  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.models.workpaper_models import (  # noqa: E402
    WorkingPaper,
    WpFormula,
    WpIndex,
    WpSourceType,
)
from app.services.formula_management.formula_scope_query import (  # noqa: E402
    FORMULA_SCOPES,
    FormulaScopeQueryService,
    classify_scope,
)


# ─────────────────────────────────────────────────────────────────────────────
# 事件循环辅助 + 每 example 独立内存引擎（含 wp_formula/working_paper/wp_index）。
# ─────────────────────────────────────────────────────────────────────────────
def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _make_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        for tbl in (WpIndex, WorkingPaper, WpFormula):
            await conn.run_sync(
                lambda sc, t=tbl: t.__table__.create(sc, checkfirst=True)
            )
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return factory, engine


async def _seed_wp(
    db: AsyncSession, project_id: uuid.UUID, wp_code: str, wp_name: str
) -> uuid.UUID:
    """建一条 wp_index + working_paper，返回其 wp_id（供 wp_formula.wp_id 引用）。"""
    idx_id = uuid.uuid4()
    wp_id = uuid.uuid4()
    db.add(
        WpIndex(
            id=idx_id, project_id=project_id, wp_code=wp_code, wp_name=wp_name
        )
    )
    db.add(
        WorkingPaper(
            id=wp_id,
            project_id=project_id,
            wp_index_id=idx_id,
            file_path=f"/tmp/{wp_code}.xlsx",
            source_type=WpSourceType.manual,
        )
    )
    await db.flush()
    return wp_id


async def _seed_formula(
    db: AsyncSession,
    project_id: uuid.UUID,
    wp_id: uuid.UUID,
    *,
    sheet_name: str,
    target_cell: str,
    expression: str = "TB('1001')",
) -> uuid.UUID:
    f = WpFormula(
        project_id=project_id,
        wp_id=wp_id,
        sheet_name=sheet_name,
        target_cell=target_cell,
        expression=expression,
        formula_type="auto_calc",
        refs=[],
    )
    db.add(f)
    await db.flush()
    return f.id


# 代表性 (wp_code, wp_name, 期望 scope) —— 覆盖 7 类的确定性映射锚点。
_SCOPE_FIXTURES = [
    ("D2-1", "应收账款明细表", "workpaper"),
    ("K10-3", "营业收入检查表", "workpaper"),
    ("TB", "试算平衡表", "tb"),
    ("TB-1", "科目余额表", "tb"),
    ("REPORT-BS", "资产负债表", "report"),
    ("RPT-IS", "利润表", "report"),
    ("NOTE-5", "应收账款附注", "note"),
    ("CONSOL-WS", "合并工作底稿", "consol_worksheet"),
    ("CONSOL-RPT", "合并资产负债表报表", "consol_report"),
    ("CONSOL-NOTE", "合并附注章节", "consol_note"),
]


# ═════════════════════════════════════════════════════════════════════════════
# scope_filter：分类确定性 + 按域过滤只返回该域
# ═════════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("wp_code,wp_name,expected", _SCOPE_FIXTURES)
def test_scope_filter_classify_deterministic(wp_code, wp_name, expected):
    """classify_scope 是确定性单值函数，把代表性底稿归入正确作用域。

    **Validates: Requirements 24.1**
    """
    first = classify_scope(wp_code, wp_name)
    assert first == expected
    # 确定性：同输入多次调用结果不变。
    assert classify_scope(wp_code, wp_name) == first
    assert first in FORMULA_SCOPES


def test_scope_filter_default_is_workpaper():
    """无 wp_code / 未命中显式他域标记 → 兜底底稿域（WP 域正确默认，不臆造）。

    **Validates: Requirements 24.1**
    """
    assert classify_scope(None, None) == "workpaper"
    assert classify_scope("", "") == "workpaper"
    assert classify_scope("D5", "固定资产明细表") == "workpaper"


def test_scope_filter_returns_only_that_scope():
    """list_by_scope 只返回该作用域公式，不含其他作用域（Req 24.1/24.2）。

    **Validates: Requirements 24.1**
    """

    async def _scenario():
        factory, engine = await _make_session()
        try:
            async with factory() as db:
                svc = FormulaScopeQueryService()
                pid = uuid.uuid4()
                # 每个 fixture 底稿放 1 条公式。
                for i, (code, name, _exp) in enumerate(_SCOPE_FIXTURES):
                    wp_id = await _seed_wp(db, pid, code, name)
                    await _seed_formula(
                        db, pid, wp_id,
                        sheet_name=f"S{i}", target_cell="B5",
                    )

                # 对每个作用域：list_by_scope 返回的每条其分类都恰为该 scope。
                for scope in FORMULA_SCOPES:
                    rows = await svc.list_by_scope(
                        db, project_id=pid, scope=scope
                    )
                    for f in rows:
                        # 重新查该公式底稿的 code/name 验证分类一致。
                        idx = (
                            await db.execute(
                                sa.select(WpIndex.wp_code, WpIndex.wp_name)
                                .select_from(WorkingPaper)
                                .join(
                                    WpIndex,
                                    WpIndex.id == WorkingPaper.wp_index_id,
                                )
                                .where(WorkingPaper.id == f.wp_id)
                            )
                        ).first()
                        assert classify_scope(idx[0], idx[1]) == scope
        finally:
            await engine.dispose()

    _run(_scenario())


def test_scope_filter_rejects_invalid_scope():
    """非法作用域 → ValueError（router 转 422）。"""

    async def _scenario():
        factory, engine = await _make_session()
        try:
            async with factory() as db:
                svc = FormulaScopeQueryService()
                with pytest.raises(ValueError):
                    await svc.list_by_scope(
                        db, project_id=uuid.uuid4(), scope="bogus_scope"
                    )
        finally:
            await engine.dispose()

    _run(_scenario())


# ═════════════════════════════════════════════════════════════════════════════
# scope_isolation：一个作用域的编辑不影响其他作用域列表（Req 24.5）
# ═════════════════════════════════════════════════════════════════════════════
# 随机选一批 fixture 底稿 + 随机在其中一个作用域内增/改一条公式。
_FIXTURE_IDX = st.lists(
    st.integers(min_value=0, max_value=len(_SCOPE_FIXTURES) - 1),
    min_size=2, max_size=len(_SCOPE_FIXTURES), unique=True,
)


@given(present=_FIXTURE_IDX, edit_pick=st.integers(min_value=0, max_value=999))
@settings(max_examples=60)
def test_scope_isolation_edit_one_scope_leaves_others_unchanged(
    present, edit_pick
):
    """在某作用域内新增一条公式，其余作用域列表逐一不变（Req 24.5 隔离）。

    **Validates: Requirements 24.5**
    """

    async def _scenario():
        factory, engine = await _make_session()
        try:
            async with factory() as db:
                svc = FormulaScopeQueryService()
                pid = uuid.uuid4()

                # 为选中的 fixture 各建一条公式，记录 wp_id 与其作用域。
                wp_by_scope: dict[str, list[uuid.UUID]] = {}
                for i in present:
                    code, name, exp = _SCOPE_FIXTURES[i]
                    wp_id = await _seed_wp(db, pid, code, name)
                    await _seed_formula(
                        db, pid, wp_id,
                        sheet_name=f"S{i}", target_cell="B5",
                    )
                    wp_by_scope.setdefault(exp, []).append(wp_id)

                # 编辑前：快照各作用域列表的公式 id 集合。
                before = {
                    s: {
                        str(f.id)
                        for f in await svc.list_by_scope(
                            db, project_id=pid, scope=s
                        )
                    }
                    for s in FORMULA_SCOPES
                }

                # 选一个存在公式的作用域，在其某底稿内新增一条公式（编辑）。
                edited_scope = sorted(wp_by_scope.keys())[
                    edit_pick % len(wp_by_scope)
                ]
                target_wp = wp_by_scope[edited_scope][0]
                await _seed_formula(
                    db, pid, target_wp,
                    sheet_name="EDIT", target_cell="Z9",
                )

                # 编辑后：再取各作用域列表。
                after = {
                    s: {
                        str(f.id)
                        for f in await svc.list_by_scope(
                            db, project_id=pid, scope=s
                        )
                    }
                    for s in FORMULA_SCOPES
                }

                # 被编辑作用域：新增了正好一条（超集且多 1）。
                assert before[edited_scope] < after[edited_scope]
                assert len(after[edited_scope]) == len(before[edited_scope]) + 1

                # 其余作用域：逐一不变（隔离）。
                for s in FORMULA_SCOPES:
                    if s == edited_scope:
                        continue
                    assert after[s] == before[s], (
                        f"作用域 {s} 在编辑 {edited_scope} 后发生串扰"
                    )
        finally:
            await engine.dispose()

    _run(_scenario())


def test_scope_isolation_partition_is_disjoint():
    """各作用域公式集互不相交（同一公式不会出现在两个作用域，Req 24.5）。

    **Validates: Requirements 24.5**
    """

    async def _scenario():
        factory, engine = await _make_session()
        try:
            async with factory() as db:
                svc = FormulaScopeQueryService()
                pid = uuid.uuid4()
                for i, (code, name, _exp) in enumerate(_SCOPE_FIXTURES):
                    wp_id = await _seed_wp(db, pid, code, name)
                    await _seed_formula(
                        db, pid, wp_id,
                        sheet_name=f"S{i}", target_cell="B5",
                    )

                seen: set[str] = set()
                for scope in FORMULA_SCOPES:
                    ids = {
                        str(f.id)
                        for f in await svc.list_by_scope(
                            db, project_id=pid, scope=scope
                        )
                    }
                    assert seen.isdisjoint(ids), (
                        f"作用域 {scope} 的公式与其他作用域重叠"
                    )
                    seen |= ids
        finally:
            await engine.dispose()

    _run(_scenario())


# ═════════════════════════════════════════════════════════════════════════════
# scope_query：全局并集分组 == 各作用域列表之并，且互斥（Req 24.3）
# ═════════════════════════════════════════════════════════════════════════════
def test_scope_query_grouped_union_equals_sum_of_scopes():
    """list_grouped_by_scope 的并集恰等于逐作用域 list_by_scope 之并且互斥。

    **Validates: Requirements 24.1, 24.5**
    """

    async def _scenario():
        factory, engine = await _make_session()
        try:
            async with factory() as db:
                svc = FormulaScopeQueryService()
                pid = uuid.uuid4()
                all_ids: set[str] = set()
                for i, (code, name, _exp) in enumerate(_SCOPE_FIXTURES):
                    wp_id = await _seed_wp(db, pid, code, name)
                    fid = await _seed_formula(
                        db, pid, wp_id,
                        sheet_name=f"S{i}", target_cell="B5",
                    )
                    all_ids.add(str(fid))

                grouped = await svc.list_grouped_by_scope(db, project_id=pid)

                # 分组含全部 7 类作用域键。
                assert set(grouped.keys()) == set(FORMULA_SCOPES)

                # 分组并集 == 逐作用域查询之并 == 项目全部公式。
                grouped_ids: set[str] = set()
                for scope, items in grouped.items():
                    per_scope = {
                        str(f.id)
                        for f in await svc.list_by_scope(
                            db, project_id=pid, scope=scope
                        )
                    }
                    assert {str(f.id) for f in items} == per_scope
                    assert grouped_ids.isdisjoint(per_scope)
                    grouped_ids |= per_scope

                assert grouped_ids == all_ids
        finally:
            await engine.dispose()

    _run(_scenario())


def test_scope_query_empty_project_returns_all_scope_keys_empty():
    """空项目：全局并集仍返回 7 类作用域键、各为空列表（供全局页渲染根节点）。

    **Validates: Requirements 24.3**
    """

    async def _scenario():
        factory, engine = await _make_session()
        try:
            async with factory() as db:
                svc = FormulaScopeQueryService()
                grouped = await svc.list_grouped_by_scope(
                    db, project_id=uuid.uuid4()
                )
                assert set(grouped.keys()) == set(FORMULA_SCOPES)
                assert all(v == [] for v in grouped.values())
        finally:
            await engine.dispose()

    _run(_scenario())
