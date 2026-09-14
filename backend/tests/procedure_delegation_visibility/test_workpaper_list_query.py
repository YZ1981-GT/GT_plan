# Feature: procedure-delegation-visibility-isolation — Task 8 List/Views (组件 C13)
"""WorkpaperListQueryService（组件 C13）分页 / 状态拆分 / 独立主编视图不变量测试。

Task 8 / Requirements 11.1–11.13, 12.1–12.9 / Design 组件 C13
"Lists, editor, coverage and frontend" / Property 14 / Property 15。

- **Property 14**（"Filtering, deduplication, statistics, sorting and paging are ordered"，
  Validates 11.1–11.13）：严格 filter→dedupe→total/stats→stable sort→page；两个"我的"视图各自
  身份边界；按 wp_index 去重；nullable wp 计入；空集 stats=两空字典。
- **Property 15**（"Display parameters and client identity never authorize"，Validates 12.1–12.10）：
  ``visibility_mode`` / 客户端身份不改变授权（授权只来自服务端 context）；非法 page/page_size/sort
  在底稿查询前返回 422（``InvalidListParams``）。

SQL 语义在真实 PostgreSQL（audit_platform）验证，非 sqlite。每用例/每 example 事务隔离回滚。
"""
from __future__ import annotations

from uuid import UUID

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.models.workpaper_models import WpFileStatus, WpStatus
from app.services.wp_visibility.contracts import VisibilityContext, VisibilityRole
from app.services.wp_visibility.workpaper_list_query import (
    DEFAULT_PAGE_SIZE,
    FILE_STATUS_NOT_GENERATED,
    MAX_PAGE_SIZE,
    InvalidListParams,
    ListParams,
    WorkpaperListFilters,
    WorkpaperListQueryService,
)

from ._factories import (
    IS_PG,
    mk_project,
    mk_row_task,
    mk_staff,
    mk_user,
    mk_working_paper,
    mk_wp_index,
    run_isolated,
)


def _ctx(user_id: UUID, project_id: UUID, role: VisibilityRole, scope) -> VisibilityContext:
    is_admin = role is VisibilityRole.admin
    return VisibilityContext(
        user_id=user_id,
        project_id=project_id,
        role=role,
        is_admin=is_admin,
        scope_cycles=frozenset() if is_admin else frozenset(scope),
    )


async def _mk_lead_wp(s, project_id, wp_index_id, user_id, *, file_status=None, file_version=1):
    wp = await mk_working_paper(s, project_id, wp_index_id, file_version=file_version)
    wp.assigned_to = user_id
    if file_status is not None:
        wp.status = file_status
    await s.flush()
    return wp


# ===========================================================================
# ListParams.parse — 参数校验（Req 11.7；纯函数，无 DB）
# ===========================================================================
class TestListParamsValidation:
    def test_valid_defaults(self):
        p = ListParams.parse(1, DEFAULT_PAGE_SIZE, "wp_code", "asc")
        assert p.page == 1 and p.page_size == DEFAULT_PAGE_SIZE
        assert p.sort == "wp_code" and p.sort_dir == "asc"
        assert p.offset == 0

    @pytest.mark.parametrize("page", [0, -1, -100])
    def test_non_positive_page_rejected(self, page):
        with pytest.raises(InvalidListParams):
            ListParams.parse(page, 20, "wp_code")

    def test_bool_page_rejected(self):
        # bool 是 int 子类，须显式拒绝
        with pytest.raises(InvalidListParams):
            ListParams.parse(True, 20, "wp_code")

    @pytest.mark.parametrize("ps", [0, -1, MAX_PAGE_SIZE + 1, 9999])
    def test_page_size_out_of_range_rejected(self, ps):
        with pytest.raises(InvalidListParams):
            ListParams.parse(1, ps, "wp_code")

    def test_unregistered_sort_rejected(self):
        with pytest.raises(InvalidListParams):
            ListParams.parse(1, 20, "; DROP TABLE working_paper")
        with pytest.raises(InvalidListParams):
            ListParams.parse(1, 20, "unknown_field")

    def test_unregistered_sort_dir_rejected(self):
        with pytest.raises(InvalidListParams):
            ListParams.parse(1, 20, "wp_code", "sideways")

    def test_offset_computation(self):
        assert ListParams.parse(3, 10, "wp_code").offset == 20


# ===========================================================================
# 示例：filter→dedupe→total/stats→stable sort→page（Property 14）
# ===========================================================================
@pytest.mark.skipif(not IS_PG, reason="need PostgreSQL")
@pytest.mark.asyncio
class TestListExamples:
    async def test_empty_visible_set_two_empty_stat_dicts(self, session):
        """空 scope → 空可见集 → total 0 + stats 两空字典（Req 11.5）。"""
        proj = await mk_project(session)
        user = await mk_user(session)
        wi = await mk_wp_index(session, proj.id, wp_code="D2-1", audit_cycle="D")
        await _mk_lead_wp(session, proj.id, wi.id, user.id)
        ctx = _ctx(user.id, proj.id, VisibilityRole.restricted, set())  # 空 scope
        out = await WorkpaperListQueryService(session).list_workpapers(ctx)
        assert out["total"] == 0
        assert out["items"] == []
        assert out["stats"] == {"by_index_status": {}, "by_file_status": {}}
        assert set(out.keys()) == {"items", "total", "stats", "page", "page_size"}

    async def test_payload_only_five_top_level_fields(self, session):
        proj = await mk_project(session)
        user = await mk_user(session)
        wi = await mk_wp_index(session, proj.id, wp_code="D2-1", audit_cycle="D")
        await _mk_lead_wp(session, proj.id, wi.id, user.id)
        ctx = _ctx(user.id, proj.id, VisibilityRole.restricted, {"D"})
        out = await WorkpaperListQueryService(session).list_workpapers(ctx)
        assert set(out.keys()) == {"items", "total", "stats", "page", "page_size"}
        assert out["total"] == 1
        assert out["items"][0]["wp_code"] == "D2-1"

    async def test_dedupe_by_wp_index_multi_identity(self, session):
        """同一 wp_index 经多身份（lead + 多张 assignee 行任务）可见 → 列表去重为一项（Req 11.2）。

        DB 约束 uq_working_paper_project_index 保证 working_paper↔wp_index 为 1:1，
        故去重风险来自"同一 wp_index 多个 grant/多张行任务" → 列表必须仍只出一行。
        """
        proj = await mk_project(session)
        user = await mk_user(session)
        staff = await mk_staff(session, user_id=user.id)
        wi = await mk_wp_index(session, proj.id, wp_code="D2-1", audit_cycle="D")
        await _mk_lead_wp(session, proj.id, wi.id, user.id, file_version=1)
        # 同 wp_index 上多张我负责的行任务（多个 assignee grant 来源）
        await mk_row_task(
            session, proj.id, wi.id, sheet_key="D2A", sheet_name="甲",
            assignee_staff_id=staff.id,
        )
        await mk_row_task(
            session, proj.id, wi.id, sheet_key="D2B", sheet_name="乙",
            assignee_staff_id=staff.id,
        )
        ctx = _ctx(user.id, proj.id, VisibilityRole.restricted, {"D"})
        out = await WorkpaperListQueryService(session).list_workpapers(ctx)
        assert out["total"] == 1
        assert len(out["items"]) == 1
        assert out["items"][0]["wp_index_id"] == str(wi.id)

    async def test_nullable_wp_counted(self, session):
        """assignee 行任务 wp_id=NULL：wp_index 计入 total / by_index_status / by_file_status。"""
        proj = await mk_project(session)
        user = await mk_user(session)
        staff = await mk_staff(session, user_id=user.id)
        wi = await mk_wp_index(session, proj.id, wp_code="D2-1", audit_cycle="D")
        await mk_row_task(
            session, proj.id, wi.id, sheet_key="D2A", sheet_name="页",
            wp_id=None, assignee_staff_id=staff.id,
        )
        ctx = _ctx(user.id, proj.id, VisibilityRole.restricted, {"D"})
        out = await WorkpaperListQueryService(session).list_workpapers(ctx)
        assert out["total"] == 1
        item = out["items"][0]
        assert item["wp_id"] is None
        assert item["file_status"] is None
        assert item["wp_generated"] is False
        # index_status 恒有（WpIndex.status NOT NULL）；file_status → not_generated sentinel
        assert out["stats"]["by_index_status"].get("not_started") == 1
        assert out["stats"]["by_file_status"].get(FILE_STATUS_NOT_GENERATED) == 1

    async def test_stats_split_index_and_file(self, session):
        proj = await mk_project(session)
        user = await mk_user(session)
        wi1 = await mk_wp_index(session, proj.id, wp_code="D2-1", audit_cycle="D")
        wi1.status = WpStatus.in_progress
        wi2 = await mk_wp_index(session, proj.id, wp_code="D2-2", audit_cycle="D")
        wi2.status = WpStatus.in_progress
        await session.flush()
        await _mk_lead_wp(session, proj.id, wi1.id, user.id, file_status=WpFileStatus.draft)
        await _mk_lead_wp(session, proj.id, wi2.id, user.id, file_status=WpFileStatus.edit_complete)
        ctx = _ctx(user.id, proj.id, VisibilityRole.restricted, {"D"})
        out = await WorkpaperListQueryService(session).list_workpapers(ctx)
        assert out["total"] == 2
        assert out["stats"]["by_index_status"] == {"in_progress": 2}
        assert out["stats"]["by_file_status"] == {"draft": 1, "edit_complete": 1}

    async def test_business_filter_index_status(self, session):
        proj = await mk_project(session)
        user = await mk_user(session)
        wi1 = await mk_wp_index(session, proj.id, wp_code="D2-1", audit_cycle="D")
        wi1.status = WpStatus.in_progress
        wi2 = await mk_wp_index(session, proj.id, wp_code="D2-2", audit_cycle="D")
        wi2.status = WpStatus.archived
        await session.flush()
        await _mk_lead_wp(session, proj.id, wi1.id, user.id)
        await _mk_lead_wp(session, proj.id, wi2.id, user.id)
        ctx = _ctx(user.id, proj.id, VisibilityRole.restricted, {"D"})
        out = await WorkpaperListQueryService(session).list_workpapers(
            ctx, filters=WorkpaperListFilters(index_status="archived")
        )
        assert out["total"] == 1
        assert out["items"][0]["wp_code"] == "D2-2"

    async def test_stable_sort_wp_code_asc(self, session):
        proj = await mk_project(session)
        user = await mk_user(session)
        codes = ["D2-3", "D2-1", "D2-2"]
        for c in codes:
            wi = await mk_wp_index(session, proj.id, wp_code=c, audit_cycle="D")
            await _mk_lead_wp(session, proj.id, wi.id, user.id)
        ctx = _ctx(user.id, proj.id, VisibilityRole.restricted, {"D"})
        out = await WorkpaperListQueryService(session).list_workpapers(ctx, sort="wp_code")
        got = [it["wp_code"] for it in out["items"]]
        assert got == ["D2-1", "D2-2", "D2-3"]

    async def test_stable_sort_nulls_last_and_wp_index_tiebreak(self, session):
        """sort=file_status：nullable wp（file_status NULL）排最后；相等键按 wp_index_id ASC。"""
        proj = await mk_project(session)
        user = await mk_user(session)
        staff = await mk_staff(session, user_id=user.id)
        # 两张有文件（同 file_status=draft）+ 一张 nullable wp
        wi_a = await mk_wp_index(session, proj.id, wp_code="D2-1", audit_cycle="D")
        wi_b = await mk_wp_index(session, proj.id, wp_code="D2-2", audit_cycle="D")
        await _mk_lead_wp(session, proj.id, wi_a.id, user.id, file_status=WpFileStatus.draft)
        await _mk_lead_wp(session, proj.id, wi_b.id, user.id, file_status=WpFileStatus.draft)
        wi_null = await mk_wp_index(session, proj.id, wp_code="D2-9", audit_cycle="D")
        await mk_row_task(
            session, proj.id, wi_null.id, sheet_key="D2A", sheet_name="页",
            wp_id=None, assignee_staff_id=staff.id,
        )
        ctx = _ctx(user.id, proj.id, VisibilityRole.restricted, {"D"})
        out = await WorkpaperListQueryService(session).list_workpapers(
            ctx, sort="file_status", sort_dir="asc"
        )
        items = out["items"]
        assert len(items) == 3
        # nullable wp（file_status None）排最后（NULLS LAST）
        assert items[-1]["wp_index_id"] == str(wi_null.id)
        # 前两个 file_status 相等 → wp_index_id 升序稳定 tiebreak
        first_two = [it["wp_index_id"] for it in items[:2]]
        assert first_two == sorted(first_two)

    async def test_pagination_slices(self, session):
        proj = await mk_project(session)
        user = await mk_user(session)
        for i in range(5):
            wi = await mk_wp_index(session, proj.id, wp_code=f"D2-{i}", audit_cycle="D")
            await _mk_lead_wp(session, proj.id, wi.id, user.id)
        ctx = _ctx(user.id, proj.id, VisibilityRole.restricted, {"D"})
        svc = WorkpaperListQueryService(session)
        p1 = await svc.list_workpapers(ctx, page=1, page_size=2, sort="wp_code")
        p2 = await svc.list_workpapers(ctx, page=2, page_size=2, sort="wp_code")
        p3 = await svc.list_workpapers(ctx, page=3, page_size=2, sort="wp_code")
        assert p1["total"] == p2["total"] == p3["total"] == 5
        assert [it["wp_code"] for it in p1["items"]] == ["D2-0", "D2-1"]
        assert [it["wp_code"] for it in p2["items"]] == ["D2-2", "D2-3"]
        assert [it["wp_code"] for it in p3["items"]] == ["D2-4"]

    async def test_admin_sees_all_ignoring_scope(self, session):
        proj = await mk_project(session)
        admin = await mk_user(session)
        wi_d = await mk_wp_index(session, proj.id, wp_code="D2-1", audit_cycle="D")
        wi_k = await mk_wp_index(session, proj.id, wp_code="K1-1", audit_cycle="K")
        await session.flush()
        ctx = _ctx(admin.id, proj.id, VisibilityRole.admin, set())
        out = await WorkpaperListQueryService(session).list_workpapers(ctx)
        codes = {it["wp_code"] for it in out["items"]}
        assert codes == {"D2-1", "K1-1"}
        assert out["total"] == 2


# ===========================================================================
# 两个"我的"视图独立身份边界（Property 14 / Req 11.10–11.13）
# ===========================================================================
@pytest.mark.skipif(not IS_PG, reason="need PostgreSQL")
@pytest.mark.asyncio
class TestTwoViewIdentityBoundary:
    async def test_my_lead_only_lead_not_assignee(self, session):
        """MyLeadWorkpapers 仅含主编底稿；不含仅 assignee 的底稿。"""
        proj = await mk_project(session)
        user = await mk_user(session)
        staff = await mk_staff(session, user_id=user.id)
        # wi_lead：主编（assigned_to==user）
        wi_lead = await mk_wp_index(session, proj.id, wp_code="D2-1", audit_cycle="D")
        await _mk_lead_wp(session, proj.id, wi_lead.id, user.id)
        # wi_row：仅程序行 assignee，无主编
        wi_row = await mk_wp_index(session, proj.id, wp_code="D2-2", audit_cycle="D")
        await mk_row_task(
            session, proj.id, wi_row.id, sheet_key="D2A", sheet_name="页",
            assignee_staff_id=staff.id,
        )
        ctx = _ctx(user.id, proj.id, VisibilityRole.restricted, {"D"})
        svc = WorkpaperListQueryService(session)
        lead_out = await svc.list_lead_workpapers(ctx)
        main_out = await svc.list_workpapers(ctx)
        lead_codes = {it["wp_code"] for it in lead_out["items"]}
        main_codes = {it["wp_code"] for it in main_out["items"]}
        assert lead_codes == {"D2-1"}  # 仅主编
        assert main_codes == {"D2-1", "D2-2"}  # 主编 + assignee 都可见

    async def test_my_lead_reuses_pagination_stats_contract(self, session):
        proj = await mk_project(session)
        user = await mk_user(session)
        for i in range(3):
            wi = await mk_wp_index(session, proj.id, wp_code=f"D2-{i}", audit_cycle="D")
            await _mk_lead_wp(session, proj.id, wi.id, user.id, file_status=WpFileStatus.draft)
        ctx = _ctx(user.id, proj.id, VisibilityRole.restricted, {"D"})
        out = await WorkpaperListQueryService(session).list_lead_workpapers(
            ctx, page=1, page_size=2, sort="wp_code"
        )
        assert set(out.keys()) == {"items", "total", "stats", "page", "page_size"}
        assert out["total"] == 3
        assert len(out["items"]) == 2  # 分页生效
        assert out["stats"]["by_file_status"] == {"draft": 3}

    async def test_my_lead_ignores_history_only(self, session):
        """仅历史参与（无当前主编）不进 MyLeadWorkpapers。"""
        from app.models.wp_visibility_models import WorkpaperDelegationHistory

        proj = await mk_project(session)
        user = await mk_user(session)
        actor = await mk_user(session)
        wi = await mk_wp_index(session, proj.id, wp_code="D2-1", audit_cycle="D")
        session.add(
            WorkpaperDelegationHistory(
                project_id=proj.id, wp_index_id=wi.id, layer="lead",
                target_role="lead", action="assign",
                new_user_id=user.id, actor_user_id=actor.id,
            )
        )
        await session.flush()
        ctx = _ctx(user.id, proj.id, VisibilityRole.restricted, {"D"})
        out = await WorkpaperListQueryService(session).list_lead_workpapers(ctx)
        assert out["total"] == 0  # 历史只读不是当前主编


# ===========================================================================
# Property 15: visibility_mode / client identity never authorize + 非法参数 422 前置
# Validates: Requirements 12.1–12.3, 11.7
# ===========================================================================
@pytest.mark.skipif(not IS_PG, reason="need PostgreSQL")
@pytest.mark.asyncio
class TestProperty15DisplayNeverAuthorizes:
    async def test_authorization_only_from_server_context(self, session):
        """Restricted 只见被委派底稿；scope 内未委派底稿不可见（授权只来自 context）。"""
        proj = await mk_project(session)
        user = await mk_user(session)
        # 已委派主编底稿
        wi_mine = await mk_wp_index(session, proj.id, wp_code="D2-1", audit_cycle="D")
        await _mk_lead_wp(session, proj.id, wi_mine.id, user.id)
        # scope 内但未委派给我（别人主编）
        other = await mk_user(session)
        wi_other = await mk_wp_index(session, proj.id, wp_code="D2-2", audit_cycle="D")
        await _mk_lead_wp(session, proj.id, wi_other.id, other.id)
        ctx = _ctx(user.id, proj.id, VisibilityRole.restricted, {"D"})
        out = await WorkpaperListQueryService(session).list_workpapers(ctx)
        codes = {it["wp_code"] for it in out["items"]}
        assert codes == {"D2-1"}  # 只见被委派的；未委派不可见

    async def test_illegal_params_reject_before_any_query(self, session):
        """非法 page/page_size/sort → InvalidListParams，且未触达 grants/底稿查询（Req 11.7）。"""
        proj = await mk_project(session)
        user = await mk_user(session)
        wi = await mk_wp_index(session, proj.id, wp_code="D2-1", audit_cycle="D")
        await _mk_lead_wp(session, proj.id, wi.id, user.id)
        ctx = _ctx(user.id, proj.id, VisibilityRole.restricted, {"D"})
        svc = WorkpaperListQueryService(session)

        # 若参数校验先于查询，则可见集/主编集解析绝不应被调用。
        calls = {"n": 0}

        async def _boom(*_a, **_k):  # noqa: ANN002, ANN003
            calls["n"] += 1
            raise AssertionError("visibility query 不应在参数校验前被调用")

        svc.visibility.visible_wp_index_ids = _boom  # type: ignore[assignment]
        svc._lead_wp_index_ids = _boom  # type: ignore[assignment]

        for bad in (dict(page=0), dict(page_size=MAX_PAGE_SIZE + 1),
                    dict(sort="bad_field"), dict(sort_dir="up")):
            with pytest.raises(InvalidListParams):
                await svc.list_workpapers(ctx, **bad)
            with pytest.raises(InvalidListParams):
                await svc.list_lead_workpapers(ctx, **bad)
        assert calls["n"] == 0  # 校验先于任何 grants/底稿查询


# ===========================================================================
# PBT Property 14: filter→dedupe→total/stats→stable sort→page 有序性
# Validates: Requirements 11.1–11.9
# ===========================================================================
@pytest.mark.skipif(not IS_PG, reason="need PostgreSQL")
class TestProperty14OrderedPipeline:
    @given(
        n_wp=st.integers(min_value=0, max_value=6),
        n_null=st.integers(min_value=0, max_value=3),
        page_size=st.integers(min_value=1, max_value=4),
        sort_dir=st.sampled_from(["asc", "desc"]),
    )
    @settings(deadline=None)  # Task 14: profile-driven max_examples (smoke=5 / correctness>=100)
    def test_pipeline_invariants(self, n_wp, n_null, page_size, sort_dir):
        async def scenario(s):
            proj = await mk_project(s)
            user = await mk_user(s)
            staff = await mk_staff(s, user_id=user.id)
            all_wpx: list[UUID] = []
            for i in range(n_wp):
                wi = await mk_wp_index(s, proj.id, wp_code=f"D2-A{i:02d}", audit_cycle="D")
                await _mk_lead_wp(s, proj.id, wi.id, user.id, file_status=WpFileStatus.draft)
                all_wpx.append(wi.id)
            for j in range(n_null):
                wi = await mk_wp_index(s, proj.id, wp_code=f"D2-B{j:02d}", audit_cycle="D")
                await mk_row_task(
                    s, proj.id, wi.id, sheet_key=f"S{j}", sheet_name="页",
                    wp_id=None, assignee_staff_id=staff.id,
                )
                all_wpx.append(wi.id)
            total_expected = len(set(all_wpx))

            ctx = _ctx(user.id, proj.id, VisibilityRole.restricted, {"D"})
            svc = WorkpaperListQueryService(s)
            out = await svc.list_workpapers(
                ctx, page=1, page_size=page_size, sort="wp_code", sort_dir=sort_dir
            )
            # total = 去重后完整集合（Req 11.3）
            assert out["total"] == total_expected
            # stats（by_index_status）总和 = total（index_status 恒有；Req 11.4）
            assert sum(out["stats"]["by_index_status"].values()) == total_expected
            # by_file_status 总和 = total（含 not_generated sentinel 计入 nullable wp）
            assert sum(out["stats"]["by_file_status"].values()) == total_expected
            # 当前页大小 ≤ page_size
            assert len(out["items"]) <= page_size
            # 空集 → 两空字典（Req 11.5）
            if total_expected == 0:
                assert out["stats"] == {"by_index_status": {}, "by_file_status": {}}
            # 遍历全部页，聚合应等于去重全集且无重复（去重 + 稳定分页）
            seen: list[str] = []
            page = 1
            while True:
                po = await svc.list_workpapers(
                    ctx, page=page, page_size=page_size, sort="wp_code", sort_dir=sort_dir
                )
                if not po["items"]:
                    break
                seen.extend(it["wp_index_id"] for it in po["items"])
                page += 1
                if page > 50:
                    break
            assert len(seen) == total_expected
            assert len(set(seen)) == total_expected  # 无重复（去重）

        run_isolated(scenario)
