# Feature: procedure-delegation-visibility-isolation — Task 4 procedure→wp 统一解析 + sheet catalog
"""ProcedureWpResolver + SheetBindingCatalog 解析不变量测试。

Task 4 / Requirements 4.1–4.14, 5.8–5.11, 8.3–8.4 / Design 组件 C4。

属性编号以 **design.md 权威编号** 为准：
  - **Property 4**（"Procedure binding is unique or rejected without mutation"，
    Validates 4.1–4.14）：unique-or-reject、sheet_name 仅联合上下文（禁止全局推断）、零/多候选/
    来源冲突 fail-closed、无业务数据变更。任务描述称其为 "Property 6"，此处按 design 标 **Property 4**。
  - **Property 7**（"Page visibility follows role and immutable history"，Validates 5.8–5.11 等）：
    row-only 入口的 sheet_key 唯一映射 / 未映射拒绝（不退化整稿）。任务描述称其为 "Property 9"，
    此处按 design 标 **Property 7**。

实现采用 result-object fail-closed 契约（``WpBindingResolution.ok`` / ``SheetResolution.ok`` +
``audit_reason='binding_conflict'``），非抛异常；语义等价于 fail-closed 拒绝且不改业务数据。

SQL 语义在真实 PostgreSQL（audit_platform）验证，非 sqlite。每用例/每 example 事务隔离回滚。
"""
from __future__ import annotations

import pytest
import sqlalchemy as sa
from hypothesis import given, settings
from hypothesis import strategies as st

from app.models.procedure_models import ProcedureRowTask
from app.models.workpaper_models import WorkingPaper, WpIndex
from app.services.wp_visibility.procedure_wp_resolver import (
    BindingRejectReason,
    ProcedureBindingSources,
    ProcedureWpResolver,
)
from app.services.wp_visibility.sheet_binding_catalog import (
    SheetBindingCatalog,
    SheetResolveReason,
)

from ._factories import (
    IS_PG,
    mk_procedure_instance,
    mk_project,
    mk_row_task,
    mk_wp_index,
    mk_working_paper,
    run_isolated,
)


async def _count(s, model, **filters) -> int:
    q = sa.select(sa.func.count()).select_from(model)
    for col, val in filters.items():
        q = q.where(getattr(model, col) == val)
    return (await s.execute(q)).scalar_one()


# ---------------------------------------------------------------------------
# Property 4 examples: 单来源 / 多来源一致 / 零·多·冲突拒绝（含 binding_conflict 审计）
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not IS_PG, reason="need PostgreSQL")
@pytest.mark.asyncio
class TestResolverExamples:
    async def test_wp_index_source_resolves(self, session):
        proj = await mk_project(session)
        wi = await mk_wp_index(session, proj.id, wp_code="D2-1")
        res = await ProcedureWpResolver(session).resolve(
            ProcedureBindingSources(project_id=proj.id, wp_index_id=wi.id)
        )
        assert res.ok is True
        assert res.wp_index_id == wi.id
        assert res.audit_reason is None

    async def test_wp_id_source_resolves(self, session):
        proj = await mk_project(session)
        wi = await mk_wp_index(session, proj.id, wp_code="D2-1")
        wp = await mk_working_paper(session, proj.id, wi.id)
        res = await ProcedureWpResolver(session).resolve(
            ProcedureBindingSources(project_id=proj.id, wp_id=wp.id)
        )
        assert res.ok is True
        assert res.wp_index_id == wi.id

    async def test_wp_code_source_resolves(self, session):
        proj = await mk_project(session)
        wi = await mk_wp_index(session, proj.id, wp_code="D2-1")
        res = await ProcedureWpResolver(session).resolve(
            ProcedureBindingSources(project_id=proj.id, wp_code="D2-1")
        )
        assert res.ok is True
        assert res.wp_index_id == wi.id

    async def test_procedure_instance_by_wp_code(self, session):
        proj = await mk_project(session)
        wi = await mk_wp_index(session, proj.id, wp_code="D2-1")
        pi = await mk_procedure_instance(session, proj.id, wp_code="D2-1")
        res = await ProcedureWpResolver(session).resolve(
            ProcedureBindingSources(project_id=proj.id, procedure_instance_id=pi.id)
        )
        assert res.ok is True
        assert res.wp_index_id == wi.id

    async def test_procedure_instance_by_wp_id(self, session):
        proj = await mk_project(session)
        wi = await mk_wp_index(session, proj.id, wp_code="D2-1")
        wp = await mk_working_paper(session, proj.id, wi.id)
        pi = await mk_procedure_instance(session, proj.id, wp_code="D2-1", wp_id=wp.id)
        res = await ProcedureWpResolver(session).resolve(
            ProcedureBindingSources(project_id=proj.id, procedure_instance_id=pi.id)
        )
        assert res.ok is True
        assert res.wp_index_id == wi.id

    async def test_procedure_row_task_source_resolves(self, session):
        proj = await mk_project(session)
        wi = await mk_wp_index(session, proj.id, wp_code="D2-1")
        t = await mk_row_task(session, proj.id, wi.id, sheet_key="SHK", sheet_name="页")
        res = await ProcedureWpResolver(session).resolve(
            ProcedureBindingSources(project_id=proj.id, procedure_row_task_id=t.id)
        )
        assert res.ok is True
        assert res.wp_index_id == wi.id

    async def test_multiple_sources_agree(self, session):
        """Req 4.6：多来源各自唯一且全部一致 → 返回该唯一 wp_index。"""
        proj = await mk_project(session)
        wi = await mk_wp_index(session, proj.id, wp_code="D2-1")
        wp = await mk_working_paper(session, proj.id, wi.id)
        res = await ProcedureWpResolver(session).resolve(
            ProcedureBindingSources(
                project_id=proj.id, wp_index_id=wi.id, wp_id=wp.id, wp_code="D2-1"
            )
        )
        assert res.ok is True
        assert res.wp_index_id == wi.id
        assert set(res.per_source) == {"wp_index_id", "wp_id", "wp_code"}

    async def test_source_disagreement_rejected(self, session):
        """Req 4.10：来源解析到不同 wp_index → source_conflict + binding_conflict 审计。"""
        proj = await mk_project(session)
        wi_a = await mk_wp_index(session, proj.id, wp_code="D2-1")
        wi_b = await mk_wp_index(session, proj.id, wp_code="D3-1")
        wp_b = await mk_working_paper(session, proj.id, wi_b.id)
        res = await ProcedureWpResolver(session).resolve(
            ProcedureBindingSources(project_id=proj.id, wp_index_id=wi_a.id, wp_id=wp_b.id)
        )
        assert res.ok is False
        assert res.wp_index_id is None
        assert res.reason is BindingRejectReason.source_conflict
        assert res.audit_reason == "binding_conflict"
        # 已提供绑定标识符可靠回显（供 outbox 记 binding_conflict，Req 4.13）
        assert res.provided_identifiers["wp_index_id"] == str(wi_a.id)
        assert res.provided_identifiers["wp_id"] == str(wp_b.id)

    async def test_zero_candidate_rejected(self, session):
        """Req 4.8：wp_code 无匹配 → zero_candidate + binding_conflict。"""
        proj = await mk_project(session)
        res = await ProcedureWpResolver(session).resolve(
            ProcedureBindingSources(project_id=proj.id, wp_code="NOPE")
        )
        assert res.ok is False
        assert res.reason is BindingRejectReason.zero_candidate
        assert res.audit_reason == "binding_conflict"

    async def test_multiple_candidates_rejected(self, session):
        """Req 4.9：同 procedure_code 的两个实例落到不同 wp_index → multi_candidate。"""
        from app.models.procedure_models import ProcedureInstance

        proj = await mk_project(session)
        await mk_wp_index(session, proj.id, wp_code="X-1")
        await mk_wp_index(session, proj.id, wp_code="X-2")
        # 两个同 procedure_code 的实例，分别绑不同底稿 wp_code
        await mk_procedure_instance(session, proj.id, wp_code="X-1")
        await mk_procedure_instance(session, proj.id, wp_code="X-2")
        # 归一为同一 procedure_code "DUP" → 该来源产生两个不同 wp_index 候选
        await session.execute(
            sa.update(ProcedureInstance)
            .where(ProcedureInstance.project_id == proj.id)
            .values(procedure_code="DUP")
        )
        await session.flush()
        res = await ProcedureWpResolver(session).resolve(
            ProcedureBindingSources(project_id=proj.id, procedure_code="DUP")
        )
        assert res.ok is False
        assert res.reason is BindingRejectReason.multi_candidate
        assert res.audit_reason == "binding_conflict"

    async def test_sheet_name_only_rejected_global(self, session):
        """Req 4.5：仅提供 sheet_name（页面级，无 identity 源）→ sheet_only，禁止全局推断。"""
        proj = await mk_project(session)
        wi = await mk_wp_index(session, proj.id, wp_code="D2-1")
        await mk_row_task(session, proj.id, wi.id, sheet_key="SHK", sheet_name="唯一页")
        res = await ProcedureWpResolver(session).resolve(
            ProcedureBindingSources(project_id=proj.id, sheet_name="唯一页")
        )
        assert res.ok is False
        assert res.reason is BindingRejectReason.sheet_only
        assert res.audit_reason == "binding_conflict"

    async def test_sheet_key_only_rejected_global(self, session):
        """Req 4.5：仅提供 sheet_key（页面级，无 identity 源）→ sheet_only。"""
        proj = await mk_project(session)
        res = await ProcedureWpResolver(session).resolve(
            ProcedureBindingSources(project_id=proj.id, sheet_key="SHK")
        )
        assert res.ok is False
        assert res.reason is BindingRejectReason.sheet_only

    async def test_no_source_rejected(self, session):
        proj = await mk_project(session)
        res = await ProcedureWpResolver(session).resolve(
            ProcedureBindingSources(project_id=proj.id)
        )
        assert res.ok is False
        assert res.reason is BindingRejectReason.no_source

    async def test_cross_project_wp_index_rejected(self, session):
        """Req 4.8：wp_index 属于别的项目 → zero_candidate（不跨项目解析）。"""
        proj = await mk_project(session)
        other = await mk_project(session)
        wi = await mk_wp_index(session, other.id, wp_code="D2-1")
        res = await ProcedureWpResolver(session).resolve(
            ProcedureBindingSources(project_id=proj.id, wp_index_id=wi.id)
        )
        assert res.ok is False
        assert res.reason is BindingRejectReason.zero_candidate

    async def test_no_mutation_on_conflict(self, session):
        """Req 4.12：解析（拒绝）时不改任何业务数据（行数不变）。"""
        proj = await mk_project(session)
        wi_a = await mk_wp_index(session, proj.id, wp_code="D2-1")
        wi_b = await mk_wp_index(session, proj.id, wp_code="D3-1")
        wp_b = await mk_working_paper(session, proj.id, wi_b.id)
        await mk_row_task(session, proj.id, wi_a.id, sheet_key="SHK", sheet_name="页A")

        before = (
            await _count(session, WpIndex),
            await _count(session, WorkingPaper),
            await _count(session, ProcedureRowTask),
        )
        res = await ProcedureWpResolver(session).resolve(
            ProcedureBindingSources(project_id=proj.id, wp_index_id=wi_a.id, wp_id=wp_b.id)
        )
        assert res.ok is False
        after = (
            await _count(session, WpIndex),
            await _count(session, WorkingPaper),
            await _count(session, ProcedureRowTask),
        )
        assert before == after


# ---------------------------------------------------------------------------
# Property 7 examples: sheet binding catalog（row-only 唯一映射 / 未映射拒绝，不退化整稿）
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not IS_PG, reason="need PostgreSQL")
@pytest.mark.asyncio
class TestSheetCatalogExamples:
    async def test_resolve_row_task(self, session):
        proj = await mk_project(session)
        wi = await mk_wp_index(session, proj.id, wp_code="D2-1")
        t = await mk_row_task(session, proj.id, wi.id, sheet_key="SHK-9", sheet_name="页")
        cat = await SheetBindingCatalog.build(session, proj.id, wi.id)
        r = cat.resolve_row_task(t)
        assert r.ok is True
        assert r.sheet_key == "SHK-9"

    async def test_row_task_cross_index_rejected_not_whole_wp(self, session):
        """Req 5.9：task 的 sheet_key 不在本 wp_index catalog → unmapped（不退化整稿）。"""
        proj = await mk_project(session)
        wi_a = await mk_wp_index(session, proj.id, wp_code="D2-1")
        wi_b = await mk_wp_index(session, proj.id, wp_code="D3-1")
        await mk_row_task(session, proj.id, wi_b.id, sheet_key="OTHER", sheet_name="乙页")
        t_a = await mk_row_task(session, proj.id, wi_a.id, sheet_key="SHK", sheet_name="页")
        # 用 wi_b 的 catalog 解析属于 wi_a 的 task → 不在集合内 → unmapped
        cat_b = await SheetBindingCatalog.build(session, proj.id, wi_b.id)
        r = cat_b.resolve_row_task(t_a)
        assert r.ok is False
        assert r.reason is SheetResolveReason.unmapped

    async def test_resolve_sheet_name_unique(self, session):
        proj = await mk_project(session)
        wi = await mk_wp_index(session, proj.id, wp_code="D2-1")
        await mk_row_task(session, proj.id, wi.id, sheet_key="SHK-A", sheet_name="页甲")
        await mk_row_task(session, proj.id, wi.id, sheet_key="SHK-B", sheet_name="页乙")
        cat = await SheetBindingCatalog.build(session, proj.id, wi.id)
        r = cat.resolve_sheet_name("页甲")
        assert r.ok is True and r.sheet_key == "SHK-A"

    async def test_resolve_sheet_name_whitespace_insensitive(self, session):
        """render-config sheet 名常差空格；catalog 归一空白匹配。"""
        proj = await mk_project(session)
        wi = await mk_wp_index(session, proj.id, wp_code="J1-1")
        await mk_row_task(
            session, proj.id, wi.id, sheet_key="J1A", sheet_name="应付职工薪酬程序表 J1A"
        )
        cat = await SheetBindingCatalog.build(session, proj.id, wi.id)
        # 无空格查询仍命中
        r = cat.resolve_sheet_name("应付职工薪酬程序表J1A")
        assert r.ok is True and r.sheet_key == "J1A"

    async def test_resolve_sheet_name_ambiguous_rejected(self, session):
        """同名 sheet_name 映射到两个 sheet_key → ambiguous（不退化整稿）。"""
        proj = await mk_project(session)
        wi = await mk_wp_index(session, proj.id, wp_code="D2-1")
        await mk_row_task(session, proj.id, wi.id, sheet_key="SHK-A", sheet_name="重名页")
        await mk_row_task(session, proj.id, wi.id, sheet_key="SHK-B", sheet_name="重名页")
        cat = await SheetBindingCatalog.build(session, proj.id, wi.id)
        r = cat.resolve_sheet_name("重名页")
        assert r.ok is False
        assert r.reason is SheetResolveReason.ambiguous

    async def test_resolve_sheet_name_zero_rejected(self, session):
        proj = await mk_project(session)
        wi = await mk_wp_index(session, proj.id, wp_code="D2-1")
        await mk_row_task(session, proj.id, wi.id, sheet_key="SHK-A", sheet_name="页甲")
        cat = await SheetBindingCatalog.build(session, proj.id, wi.id)
        r = cat.resolve_sheet_name("不存在页")
        assert r.ok is False
        assert r.reason is SheetResolveReason.unmapped

    async def test_resolve_sheet_key_membership(self, session):
        """Req 8.3/8.4：sheet_key 成员校验（属于本 wp_index 才通过）。"""
        proj = await mk_project(session)
        wi = await mk_wp_index(session, proj.id, wp_code="D2-1")
        await mk_row_task(session, proj.id, wi.id, sheet_key="D2A", sheet_name="页甲")
        cat = await SheetBindingCatalog.build(session, proj.id, wi.id)
        assert cat.resolve_sheet_key("D2A").ok is True
        r = cat.resolve_sheet_key("NOT-IN-INDEX")
        assert r.ok is False and r.reason is SheetResolveReason.unmapped

    async def test_checklist_item_direct_hit(self, session):
        proj = await mk_project(session)
        wi = await mk_wp_index(session, proj.id, wp_code="D2-1")
        await mk_row_task(session, proj.id, wi.id, sheet_key="D2A", sheet_name="页")
        cat = await SheetBindingCatalog.build(session, proj.id, wi.id)
        r = cat.resolve_checklist_item("D2A-voucher-check-row-3")
        assert r.ok is True and r.sheet_key == "D2A"

    async def test_checklist_item_ambiguous_rejected(self, session):
        """item token 基码匹配到多个 sheet_key → ambiguous（不退化整稿）。"""
        proj = await mk_project(session)
        wi = await mk_wp_index(session, proj.id, wp_code="D3-1")
        await mk_row_task(session, proj.id, wi.id, sheet_key="D3A", sheet_name="页1")
        await mk_row_task(session, proj.id, wi.id, sheet_key="D3B", sheet_name="页2")
        cat = await SheetBindingCatalog.build(session, proj.id, wi.id)
        r = cat.resolve_checklist_item("D3-summary")
        assert r.ok is False
        assert r.reason is SheetResolveReason.ambiguous


# ---------------------------------------------------------------------------
# PBT Property 4: procedure binding is unique or rejected without mutation
# Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9, 4.10,
#            4.11, 4.12, 4.13, 4.14
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not IS_PG, reason="need PostgreSQL")
class TestProperty4ProcedureBindingUniqueOrReject:
    @given(
        give_index=st.booleans(),
        give_wp_id=st.booleans(),
        give_wp_code=st.booleans(),
        give_sheet_name_only=st.booleans(),
        wp_id_same=st.booleans(),
        wp_code_exists=st.booleans(),
        nonce=st.integers(min_value=0, max_value=2_000_000_000),  # Task14: correctness>=100 有效样例（宽域防早停）
    )
    @settings(deadline=None)  # Task 14: profile-driven max_examples (smoke=5 / correctness>=100)
    def test_unique_or_reject_no_mutation(
        self,
        give_index,
        give_wp_id,
        give_wp_code,
        give_sheet_name_only,
        wp_id_same,
        wp_code_exists,
        nonce,
    ):
        async def scenario(s):
            proj = await mk_project(s)
            wi_a = await mk_wp_index(s, proj.id, wp_code="D2-1")
            wi_b = await mk_wp_index(s, proj.id, wp_code="D3-1")
            wp_a = await mk_working_paper(s, proj.id, wi_a.id)
            wp_b = await mk_working_paper(s, proj.id, wi_b.id)
            await mk_row_task(s, proj.id, wi_a.id, sheet_key="SHK", sheet_name="页")

            kwargs: dict = {"project_id": proj.id}
            candidates: set[str] = set()
            if give_index:
                kwargs["wp_index_id"] = wi_a.id
                candidates.add(str(wi_a.id))
            if give_wp_id:
                kwargs["wp_id"] = wp_a.id if wp_id_same else wp_b.id
                candidates.add(str(wi_a.id if wp_id_same else wi_b.id))
            wp_code_zero = False
            if give_wp_code:
                if wp_code_exists:
                    kwargs["wp_code"] = "D2-1"
                    candidates.add(str(wi_a.id))
                else:
                    kwargs["wp_code"] = "GHOST"
                    wp_code_zero = True  # 该来源零候选 → 拒绝
            if give_sheet_name_only and not (give_index or give_wp_id or give_wp_code):
                kwargs["sheet_name"] = "页"

            has_identity = give_index or give_wp_id or give_wp_code
            expect_ok = has_identity and not wp_code_zero and len(candidates) == 1

            before = (
                await _count(s, WpIndex),
                await _count(s, WorkingPaper),
                await _count(s, ProcedureRowTask),
            )
            res = await ProcedureWpResolver(s).resolve(ProcedureBindingSources(**kwargs))
            if expect_ok:
                assert res.ok is True
                # 唯一一致候选即期望结果（可能是 wi_a，也可能仅由 wp_id→wi_b 唯一确定）
                from uuid import UUID as _UUID

                assert res.wp_index_id == _UUID(next(iter(candidates)))
            else:
                assert res.ok is False
                assert res.wp_index_id is None
                # 拒绝一律记 binding_conflict（sheet_only/zero/multi/conflict/no_source 均在集合内）
                assert res.audit_reason == "binding_conflict"
            after = (
                await _count(s, WpIndex),
                await _count(s, WorkingPaper),
                await _count(s, ProcedureRowTask),
            )
            # 无论成功或拒绝，解析都不改业务数据（Req 4.12）
            assert before == after

        run_isolated(scenario)


# ---------------------------------------------------------------------------
# PBT Property 7: row-only sheet_key mapping is unique or rejected (no whole-wp fallback)
# Validates: Requirements 5.8, 5.9, 5.10, 5.11, 8.3, 8.4
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not IS_PG, reason="need PostgreSQL")
class TestProperty7RowOnlySheetMapping:
    @given(
        duplicate_name=st.booleans(),
        query_name=st.sampled_from(["页甲", "页乙", "不存在"]),
        nonce=st.integers(min_value=0, max_value=2_000_000_000),  # Task14: correctness>=100 有效样例（宽域防早停）
    )
    @settings(deadline=None)  # Task 14: profile-driven max_examples (smoke=5 / correctness>=100)
    def test_sheet_name_maps_unique_or_rejects(self, duplicate_name, query_name, nonce):
        async def scenario(s):
            proj = await mk_project(s)
            wi = await mk_wp_index(s, proj.id, wp_code="D2-1")
            await mk_row_task(s, proj.id, wi.id, sheet_key="SHK-A", sheet_name="页甲")
            await mk_row_task(s, proj.id, wi.id, sheet_key="SHK-B", sheet_name="页乙")
            if duplicate_name:
                # 让 "页甲" 变歧义（映射到两个 sheet_key）
                await mk_row_task(s, proj.id, wi.id, sheet_key="SHK-C", sheet_name="页甲")

            cat = await SheetBindingCatalog.build(s, proj.id, wi.id)
            unique = query_name == "页乙" or (query_name == "页甲" and not duplicate_name)
            r = cat.resolve_sheet_name(query_name)
            if unique:
                assert r.ok is True
                assert r.sheet_key == ("SHK-A" if query_name == "页甲" else "SHK-B")
            else:
                # 歧义或不存在都必须拒绝（fail-closed），绝不退化整稿
                assert r.ok is False
                assert r.reason in (
                    SheetResolveReason.ambiguous,
                    SheetResolveReason.unmapped,
                )

        run_isolated(scenario)
