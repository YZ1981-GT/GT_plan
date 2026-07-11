# Feature: formula-management-library, Property 7: 悬空引用拒绝保存并返回问题清单
"""属性测试 P7：含悬空引用的公式保存被拒绝，返回问题清单且不写库（Task 3.3）。

**Property 7: 悬空引用拒绝保存并返回问题清单**

*对任意*含悬空引用（full_resolve found=false）的公式，保存被拒绝：不写库、
返回 ``(None, issues)`` 且 issues 非空（HTTP 422），保持 ``WpFormulaService.save``
契约；审定表回写与弹窗提交同样在悬空时拒绝。

**Validates: Requirements 8.4, 9.5, 13.4, 14.4**

被测：``app.services.wp_formula_service.WpFormulaService.save``。
- monkeypatch ``validate_refs_via_acnr`` 返回非空 issues（含至少一条 ``not_found``），
  模拟 ACNR full_resolve 检出悬空引用。
- 断言：``save`` 返回 ``(None, issues)``；issues 非空且含 ``not_found``；
  未写库（``list_by_wp`` 为空）。
- 用内存 sqlite（参考 test_wp_formula_three_type.py）。

Framework: hypothesis（遵循 conftest fast profile，max_examples 可经
HYPOTHESIS_MAX_EXAMPLES 覆盖）。
"""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, patch

from hypothesis import given
from hypothesis import strategies as st
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler

# sqlite 无原生 UUID：复用 uuid 编译器（与 test_wp_formula_three_type.py 一致）。
SQLiteTypeCompiler.visit_UUID = SQLiteTypeCompiler.visit_uuid
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.models.workpaper_models import WpFormula
from app.services.wp_formula_service import WpFormulaService


# ─────────────────────────────────────────────────────────────────────────────
# 事件循环辅助 + 独立内存 sqlite 会话（每个 example 全新库，隔离写库副作用）。
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
        await conn.run_sync(
            lambda sc: WpFormula.__table__.create(sc, checkfirst=True)
        )
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return factory, engine


# ─────────────────────────────────────────────────────────────────────────────
# 智能生成器：随机三类型公式 + 随机含悬空引用的表达式与 issues 清单。
# ─────────────────────────────────────────────────────────────────────────────
_FORMULA_TYPES = st.sampled_from(["auto_calc", "logic_check", "reasonability"])

# 悬空引用的候选形态（WP / addr_id / 跨 sheet）——桩视为 not_found。
_DANGLING_REFS = st.sampled_from(
    [
        "WP('X','Z99')",
        "WP('D9','不存在表','ZZ1')",
        "=不存在表!A1",
        "ROW('__missing__')",
        "TB('9999','期末余额')",
        "D9/D9-1/ZZ1",
    ]
)


@st.composite
def _dangling_case(draw):
    """抽取（表达式, formula_type, issues 清单）。

    表达式必含至少一条悬空引用；issues 由桩返回，含至少一条 ``not_found``，
    并可混入其它状态项（模拟 full_resolve 的多问题聚合）。
    """
    n_refs = draw(st.integers(min_value=1, max_value=3))
    refs = [draw(_DANGLING_REFS) for _ in range(n_refs)]
    # 混入一个可能有效的算术项，但整体因含悬空引用被拒。
    expression = " + ".join(refs + [draw(st.sampled_from(["1", "42", "B5"]))])
    ftype = draw(_FORMULA_TYPES)

    # 构造 issues：至少一条 not_found，其余状态项随机混入。
    issues: list[dict] = [
        {"ref": r, "uri": r, "status": "not_found", "reason": "dangling_ref",
         "message": f"引用 {r} 不存在"}
        for r in refs
    ]
    if draw(st.booleans()):
        issues.append(
            {"ref": None, "uri": None, "status": "ambiguous",
             "reason": "multiple_candidates", "message": "候选多义"}
        )
    return expression, ftype, issues


@given(case=_dangling_case())
def test_p7_dangling_ref_rejects_save_and_returns_issues(case):
    """P7：含悬空引用 → save 返回 (None, issues) 且 issues 非空、未写库。

    **Validates: Requirements 8.4, 9.5, 13.4, 14.4**
    """
    expression, ftype, stub_issues = case

    async def _scenario():
        factory, engine = await _make_session()
        try:
            async with factory() as db:
                svc = WpFormulaService()
                wp_id = uuid.uuid4()
                with patch(
                    "app.services.wp_formula_service.validate_refs_via_acnr",
                    new_callable=AsyncMock,
                    return_value=stub_issues,
                ):
                    saved, issues = await svc.save(
                        db,
                        project_id=uuid.uuid4(),
                        wp_id=wp_id,
                        sheet_name="审定表",
                        target_cell="B5",
                        expression=expression,
                        year=2025,
                        formula_type=ftype,
                    )
                # 保存被拒：返回 (None, issues)。
                assert saved is None, "含悬空引用的公式不应保存成功"
                # issues 非空且含 not_found（问题清单可供 router 转 422）。
                assert issues, "被拒时必须返回非空问题清单"
                assert any(i.get("status") == "not_found" for i in issues), (
                    "问题清单必须含 not_found 悬空引用项"
                )
                # 未写库：目标 wp_id 无任何公式记录。
                loaded = await svc.list_by_wp(db, wp_id)
                assert loaded == [], "悬空引用被拒后不得写库"
        finally:
            await engine.dispose()

    _run(_scenario())
