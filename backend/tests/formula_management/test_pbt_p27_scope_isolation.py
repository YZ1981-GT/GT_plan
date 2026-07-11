# Feature: formula-management-library, Property 27: 对任意跨多 Formula_Scope（7 类）
# 的公式全集 + 任意目标 scope，弹窗加载集合恰等于该 scope 子集（无泄漏）；全局页
# 展示 == 各 scope 并集；任两不同 scope，其一编辑不改另一列表。
"""P27 公式作用域隔离不串扰（formula-management-library Req 24 / Task 20.3）。

被测：``app.services.formula_management.formula_scope_query`` 的 Task 20.2 后端
scope 过滤（``classify_scope`` / ``FormulaScopeQueryService.list_by_scope`` /
``list_grouped_by_scope``）。

**Property 27（model-based，单一属性测试）**：对任意跨多 ``Formula_Scope``（7 类）
的公式全集 + 任意目标 scope：

1. **无泄漏（Req 24.1/24.2）**：``list_by_scope(scope)`` 返回集合恰等于按
   ``classify_scope`` 归入该 scope 的公式子集（不多、不少、不含他域）。
2. **全局并集（Req 24.3）**：``list_grouped_by_scope`` 的各作用域列表之并恰等于
   项目全部公式，且各作用域互不相交（无重叠）。
3. **编辑隔离（Req 24.5）**：任取一个作用域在其内新增/修改一条公式，**仅**改变该
   作用域列表，其余任一不同作用域的列表逐一不变（不串扰）。

model-based 手法：以内存 SQLite 种子随机公式（不同 ``wp_code`` → 不同 scope）建立
参照模型（scope → 期望公式 id 集），再对被测服务的三种查询逐一比对模型。

DB：内存 SQLite（``:memory:`` + ``aiosqlite``）+ SQLiteTypeCompiler patch 建
``wp_formula`` / ``working_paper`` / ``wp_index`` 三表（JOIN 派生作用域所需），
复用 Task 20.2 示例测试（``test_formula_scope_query.py``）的建表/种子范式；每个
Hypothesis example 独立引擎隔离（同步 ``_run(coro)`` 包装 async）。

**Validates: Requirements 24.1, 24.2, 24.3, 24.5**
"""

from __future__ import annotations

import asyncio
import uuid

from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler

# SQLite 测试方言：UUID → uuid 编译；JSONB → JSON 编译（建表所需）。
if hasattr(SQLiteTypeCompiler, "visit_uuid"):
    SQLiteTypeCompiler.visit_UUID = SQLiteTypeCompiler.visit_uuid
if not hasattr(SQLiteTypeCompiler, "visit_JSONB"):
    SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    create_async_engine,
)
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

# 代表性 (wp_code, wp_name) → 覆盖全部 7 类 Formula_Scope 的确定性映射锚点。
# 每个作用域至少 1 个 fixture，保证随机全集能横跨多 scope。
_SCOPE_FIXTURES: list[tuple[str, str]] = [
    ("D2-1", "应收账款明细表"),        # workpaper
    ("K10-3", "营业收入检查表"),        # workpaper
    ("TB", "试算平衡表"),               # tb
    ("TB-1", "科目余额表"),             # tb
    ("REPORT-BS", "资产负债表"),        # report
    ("RPT-IS", "利润表"),               # report
    ("NOTE-5", "应收账款附注"),         # note
    ("CONSOL-WS", "合并工作底稿"),      # consol_worksheet
    ("CONSOL-RPT", "合并资产负债表报表"),  # consol_report
    ("CONSOL-NOTE", "合并附注章节"),    # consol_note
]


# ─────────────────────────────────────────────────────────────────────────────
# 事件循环辅助 + 每 example 独立内存引擎（wp_formula/working_paper/wp_index）。
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
) -> str:
    f = WpFormula(
        project_id=project_id,
        wp_id=wp_id,
        sheet_name=sheet_name,
        target_cell=target_cell,
        expression="TB('1001')",
        formula_type="auto_calc",
        refs=[],
    )
    db.add(f)
    await db.flush()
    return str(f.id)


# ─── 随机跨多 scope 公式全集：每条公式 = 选一个 fixture 底稿 + 放几条公式 ──────────
#   plan: 每个 fixture index → 该底稿放几条公式（0..3）；至少 2 个底稿有公式，
#   使全集横跨多个作用域。
_PLAN = st.lists(
    st.integers(min_value=0, max_value=3),
    min_size=len(_SCOPE_FIXTURES),
    max_size=len(_SCOPE_FIXTURES),
).filter(lambda counts: sum(1 for c in counts if c > 0) >= 2)


@given(
    plan=_PLAN,
    scope_pick=st.integers(min_value=0, max_value=9_999),
    edit_pick=st.integers(min_value=0, max_value=9_999),
)
@settings(max_examples=5)
def test_p27_scope_isolation_no_crosstalk(plan, scope_pick, edit_pick):
    """P27：无泄漏 + 全局并集 + 编辑隔离（三合一 model-based 属性）。

    **Validates: Requirements 24.1, 24.2, 24.3, 24.5**
    """

    async def _scenario():
        factory, engine = await _make_session()
        try:
            async with factory() as db:
                svc = FormulaScopeQueryService()
                pid = uuid.uuid4()

                # ── 种子随机公式全集，同时构建参照模型 model[scope] = {ids} ──
                model: dict[str, set[str]] = {s: set() for s in FORMULA_SCOPES}
                all_ids: set[str] = set()
                # scope → 该 scope 下已建的 wp_id（供后续编辑挑选）。
                wp_by_scope: dict[str, list[uuid.UUID]] = {}
                for i, count in enumerate(plan):
                    if count <= 0:
                        continue
                    code, name = _SCOPE_FIXTURES[i]
                    scope = classify_scope(code, name)
                    wp_id = await _seed_wp(db, pid, code, name)
                    wp_by_scope.setdefault(scope, []).append(wp_id)
                    for j in range(count):
                        fid = await _seed_formula(
                            db, pid, wp_id,
                            sheet_name=f"S{i}", target_cell=f"B{j + 1}",
                        )
                        model[scope].add(fid)
                        all_ids.add(fid)

                # ── 属性①（无泄漏，Req 24.1/24.2）：每个 scope 的 list_by_scope
                #     恰等于模型该 scope 子集，且返回项分类回验一致（不含他域）。
                for scope in FORMULA_SCOPES:
                    rows = await svc.list_by_scope(
                        db, project_id=pid, scope=scope
                    )
                    got = {str(f.id) for f in rows}
                    assert got == model[scope], (
                        f"作用域 {scope} 加载集合与模型不符：泄漏或缺失"
                    )
                    # 返回的每条公式都真属该 scope（无跨域泄漏）。
                    for f in rows:
                        assert f.project_id == pid

                # ── 属性②（全局并集 + 互斥，Req 24.3）：grouped 各域之并 == 全集，
                #     且各域互不相交。
                grouped = await svc.list_grouped_by_scope(db, project_id=pid)
                assert set(grouped.keys()) == set(FORMULA_SCOPES)
                union: set[str] = set()
                for scope, items in grouped.items():
                    ids = {str(f.id) for f in items}
                    assert ids == model[scope], (
                        f"全局分组作用域 {scope} 与模型/弹窗加载不一致"
                    )
                    assert union.isdisjoint(ids), (
                        f"作用域 {scope} 公式与其他作用域重叠（非互斥）"
                    )
                    union |= ids
                assert union == all_ids, "全局并集不等于项目公式全集"

                # ── 属性③（编辑隔离，Req 24.5）：在某个有公式的作用域内新增一条，
                #     仅该作用域列表变化，其余作用域逐一不变。
                editable = sorted(wp_by_scope.keys())
                if editable:
                    edited_scope = editable[edit_pick % len(editable)]
                    target_wp = wp_by_scope[edited_scope][0]

                    before = {
                        s: {
                            str(f.id)
                            for f in await svc.list_by_scope(
                                db, project_id=pid, scope=s
                            )
                        }
                        for s in FORMULA_SCOPES
                    }
                    new_fid = await _seed_formula(
                        db, pid, target_wp,
                        sheet_name="EDIT", target_cell="Z99",
                    )
                    after = {
                        s: {
                            str(f.id)
                            for f in await svc.list_by_scope(
                                db, project_id=pid, scope=s
                            )
                        }
                        for s in FORMULA_SCOPES
                    }

                    # 被编辑作用域：恰好多出新增那一条。
                    assert after[edited_scope] == before[edited_scope] | {
                        new_fid
                    }
                    # 其余任一不同作用域：列表逐一不变（不串扰）。
                    for s in FORMULA_SCOPES:
                        if s == edited_scope:
                            continue
                        assert after[s] == before[s], (
                            f"编辑作用域 {edited_scope} 后作用域 {s} 发生串扰"
                        )
        finally:
            await engine.dispose()

    _run(_scenario())
