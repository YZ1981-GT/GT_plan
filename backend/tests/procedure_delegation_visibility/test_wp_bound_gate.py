# Feature: procedure-delegation-visibility-isolation — Task 6 Wp_Bound_Gate / Action Matrix / 统一拒绝
"""Wp_Bound_Gate（组件 C6 ActionMatrix + C8 WpBoundGate）授权流水线不变量测试。

Task 6 / Requirements 7.1–7.10, 8.1–8.4, 8.18–8.19, 9.1–9.11, 14.18–14.19 /
Design 组件 C6/C8 "Core contracts and gate" / Error Handling / Property 8/9/10/11/12。

属性编号以 **prompt 权威编号** 为准：
  - **Property 8**（grant single kind, no dimension splice）：每个 AccessGrant 独立完整命中矩阵后
    才并集页面/动作；缺少完整条目的身份绝不与其他身份拼接维度。
  - **Property 9**（reviewer whitelist only）：Operation_Reviewer 只能命中 Review_Whitelist
    （submitted→reviewed / submitted→changes_requested[reason 必填] + 同 task/sheet 复核会话读评论），
    通用 status/checklist/parsed_data/associate/version restore/editor write 一律拒绝。
  - **Property 10**（binding/claim conflict fail-closed）：project/wp/sheet/version/token claim 任一
    冲突在读正文/副作用前拒绝。
  - **Property 11**（rate-limit 429 pre-resolve + 全部 deny → 相同 404 wire body）：资源无关 429 在
    解析前产生（不表明存在性）；进入 gate 后全部不可见原因对外恒 404 + 固定 detail。
  - **Property 12**（audit outbox failure never changes 404/429）：安全审计写入失败不改变对外响应。

SQL 语义在真实 PostgreSQL（audit_platform）验证，非 sqlite。每用例/每 example 事务隔离回滚；
审计 outbox 用注入的 capturing responder（不落 dev 库）。
"""
from __future__ import annotations

from uuid import uuid4

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.wp_visibility.denial import (
    EXTERNAL_NOT_FOUND_DETAIL,
    DenialReason,
    DenialResponder,
    ExternalNotFound,
    RateLimited,
)
from app.services.wp_visibility.wp_bound_gate import (
    BindingAdapters,
    RateLimitDecision,
    resolve_wp_binding_and_access,
)

from ._factories import (
    IS_PG,
    mk_project,
    mk_project_user,
    mk_row_task,
    mk_staff,
    mk_user,
    mk_working_paper,
    mk_wp_index,
    run_isolated,
)

_BA = BindingAdapters()


# ---------------------------------------------------------------------------
# 测试替身：capturing / failing responder；denying rate limiter
# ---------------------------------------------------------------------------
class CapturingResponder(DenialResponder):
    """把 outbox 写入捕获到内存（不落 dev 库）；可选模拟写入失败。"""

    def __init__(self, fail: bool = False) -> None:
        super().__init__()
        self.captured: list[dict] = []
        self._fail = fail

    async def _write_outbox(self, **fields) -> None:  # type: ignore[override]
        if self._fail:
            raise RuntimeError("simulated outbox failure")
        self.captured.append(fields)

    def last_reason(self) -> str | None:
        return self.captured[-1]["reason"] if self.captured else None


class _DenyRateLimiter:
    def __init__(self, retry_after: int = 7) -> None:
        self.retry_after = retry_after
        self.calls: list[tuple] = []

    def check(self, *, principal, project_id, entry_family):
        self.calls.append((principal, project_id, entry_family))
        return RateLimitDecision(allowed=False, retry_after=self.retry_after)


class _RecordingAllowLimiter:
    """放行但记录调用（证明限流在资源解析前依据 principal/project/family）。"""

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def check(self, *, principal, project_id, entry_family):
        self.calls.append((principal, project_id, entry_family))
        return RateLimitDecision(allowed=True)


# ---------------------------------------------------------------------------
# 场景搭建 helper
# ---------------------------------------------------------------------------
async def _lead_scenario(s, *, scope="D", cycle="D"):
    proj = await mk_project(s)
    user = await mk_user(s)
    wi = await mk_wp_index(s, proj.id, wp_code="D2-1", audit_cycle=cycle)
    wp = await mk_working_paper(s, proj.id, wi.id)
    wp.assigned_to = user.id
    await mk_project_user(s, proj.id, user.id, scope_cycles=scope)
    await s.flush()
    return proj, user, wi, wp


async def _reviewer_scenario(s, *, sheet="D2A", scope="D"):
    proj = await mk_project(s)
    user = await mk_user(s)
    staff = await mk_staff(s, user_id=user.id)
    wi = await mk_wp_index(s, proj.id, wp_code="D2-1", audit_cycle="D")
    wp = await mk_working_paper(s, proj.id, wi.id)
    await mk_row_task(
        s, proj.id, wi.id, sheet_key=sheet, sheet_name=f"n-{sheet}",
        reviewer_staff_id=staff.id,
    )
    await mk_project_user(s, proj.id, user.id, scope_cycles=scope)
    await s.flush()
    return proj, user, wi, wp


# ===========================================================================
# Property 8：每个 grant 独立完整命中矩阵后才并集；禁止跨身份拼接
# Validates: Requirements 5.15, 5.16, 7.1, 7.2, 7.3, 7.4, 7.6, 7.7, 7.9, 7.10
# ===========================================================================
@pytest.mark.skipif(not IS_PG, reason="need PostgreSQL")
@pytest.mark.asyncio
class TestProperty8GrantMatrixUnion:
    async def test_lead_read_all_pages(self, session):
        proj, user, wi, wp = await _lead_scenario(session)
        req = _BA.wp(
            entrypoint="workpaper.render_config", action="read_render", method="GET",
            wp_id=wp.id, project_id=proj.id,
        )
        ctx = await resolve_wp_binding_and_access(
            session, user, req, responder=CapturingResponder()
        )
        assert ctx.access_kinds == frozenset({"lead"})
        assert ctx.allowed_sheet_keys == "all"
        assert ctx.readonly is False
        assert ctx.wp_id == wp.id
        assert ctx.current_version == str(wp.file_version)

    async def test_multi_identity_union_read(self, session):
        """同一 wp 既是 lead 又是 assignee → 读动作并集两身份完整条目（Req 7.10）。"""
        proj, user, wi, wp = await _lead_scenario(session)
        staff = await mk_staff(session, user_id=user.id)
        await mk_row_task(
            session, proj.id, wi.id, sheet_key="D2A", sheet_name="甲",
            assignee_staff_id=staff.id,
        )
        await session.flush()
        req = _BA.wp(
            entrypoint="workpaper.render_config", action="read_render", method="GET",
            wp_id=wp.id, project_id=proj.id,
        )
        ctx = await resolve_wp_binding_and_access(
            session, user, req, responder=CapturingResponder()
        )
        assert ctx.access_kinds == frozenset({"lead", "assignee"})
        # lead 是 all pages → 并集为 all
        assert ctx.allowed_sheet_keys == "all"

    async def test_no_dimension_splice_assignee_cannot_borrow_lead_action(self, session):
        """assignee-only 用户请求只有 lead 完整条目覆盖的动作（attach_associate）→ 拒绝（不拼接）。"""
        proj = await mk_project(session)
        user = await mk_user(session)
        staff = await mk_staff(session, user_id=user.id)
        wi = await mk_wp_index(session, proj.id, wp_code="D2-1", audit_cycle="D")
        await mk_row_task(
            session, proj.id, wi.id, sheet_key="D2A", sheet_name="甲",
            assignee_staff_id=staff.id,
        )
        await mk_project_user(session, proj.id, user.id, scope_cycles="D")
        await session.flush()
        resp = CapturingResponder()
        req = _BA.wp(
            entrypoint="attachment.associate", action="attach_associate", method="POST",
            wp_index_id=wi.id, project_id=proj.id,
        )
        with pytest.raises(ExternalNotFound) as ei:
            await resolve_wp_binding_and_access(session, user, req, responder=resp)
        assert ei.value.status_code == 404
        assert resp.last_reason() == DenialReason.action_denied.value

    async def test_assignee_content_mutation_allowed_on_mapped_sheet(self, session):
        """assignee 可在被委派 sheet 上做内容写（checklist_save）；未映射 sheet 拒绝。"""
        proj = await mk_project(session)
        user = await mk_user(session)
        staff = await mk_staff(session, user_id=user.id)
        wi = await mk_wp_index(session, proj.id, wp_code="D2-1", audit_cycle="D")
        await mk_working_paper(session, proj.id, wi.id)
        await mk_row_task(
            session, proj.id, wi.id, sheet_key="D2A", sheet_name="甲",
            assignee_staff_id=staff.id,
        )
        await mk_project_user(session, proj.id, user.id, scope_cycles="D")
        await session.flush()
        req = _BA.wp(
            entrypoint="workpaper.checklist_save", action="save_checklist", method="PUT",
            wp_index_id=wi.id, project_id=proj.id, requested_sheet_key="D2A",
        )
        ctx = await resolve_wp_binding_and_access(
            session, user, req, responder=CapturingResponder()
        )
        assert ctx.access_kinds == frozenset({"assignee"})
        assert ctx.resolved_sheet_key == "D2A"


# ===========================================================================
# Property 9：Reviewer 白名单
# Validates: Requirements 7.5
# ===========================================================================
@pytest.mark.skipif(not IS_PG, reason="need PostgreSQL")
@pytest.mark.asyncio
class TestProperty9ReviewerWhitelist:
    async def test_reviewer_can_read(self, session):
        proj, user, wi, wp = await _reviewer_scenario(session)
        req = _BA.wp(
            entrypoint="workpaper.render_config", action="read_render", method="GET",
            wp_id=wp.id, project_id=proj.id,
        )
        ctx = await resolve_wp_binding_and_access(
            session, user, req, responder=CapturingResponder()
        )
        assert "reviewer" in ctx.access_kinds

    async def test_reviewer_transition_reviewed_allowed(self, session):
        proj, user, wi, wp = await _reviewer_scenario(session)
        req = _BA.wp(
            entrypoint="review.transition", action="review_transition", method="POST",
            wp_id=wp.id, project_id=proj.id, source_state="submitted",
            target_state="reviewed",
        )
        ctx = await resolve_wp_binding_and_access(
            session, user, req, responder=CapturingResponder()
        )
        assert ctx.access_kinds == frozenset({"reviewer"})

    async def test_reviewer_changes_requested_requires_reason(self, session):
        proj, user, wi, wp = await _reviewer_scenario(session)
        base = dict(
            entrypoint="review.transition", action="review_transition", method="POST",
            wp_id=wp.id, project_id=proj.id, source_state="submitted",
            target_state="changes_requested",
        )
        # 无 reason → 拒绝
        resp = CapturingResponder()
        with pytest.raises(ExternalNotFound):
            await resolve_wp_binding_and_access(session, user, _BA.wp(**base), responder=resp)
        assert resp.last_reason() == DenialReason.action_denied.value
        # 有 reason → 允许
        ctx = await resolve_wp_binding_and_access(
            session, user, _BA.wp(review_reason="需补充凭证", **base),
            responder=CapturingResponder(),
        )
        assert ctx.access_kinds == frozenset({"reviewer"})

    @pytest.mark.parametrize(
        "entrypoint,action,method,src,tgt",
        [
            ("workpaper.checklist_save", "save_checklist", "PUT", "none", "none"),
            ("workpaper.parsed_data_write", "save_parsed_data", "PUT", "none", "none"),
            ("attachment.associate", "attach_associate", "POST", "none", "none"),
            ("version.restore", "version_restore", "POST", "none", "none"),
            ("editor.file_write", "editor_write", "POST", "none", "none"),
            ("workpaper.status_transition", "status_transition", "POST", "submitted", "reviewed"),
        ],
    )
    async def test_reviewer_generic_mutations_denied(
        self, session, entrypoint, action, method, src, tgt
    ):
        proj, user, wi, wp = await _reviewer_scenario(session)
        resp = CapturingResponder()
        req = _BA.wp(
            entrypoint=entrypoint, action=action, method=method,
            wp_id=wp.id, project_id=proj.id, source_state=src, target_state=tgt,
        )
        with pytest.raises(ExternalNotFound) as ei:
            await resolve_wp_binding_and_access(session, user, req, responder=resp)
        assert ei.value.status_code == 404
        assert resp.last_reason() == DenialReason.action_denied.value


# ===========================================================================
# Property 10：绑定/claim 冲突 fail-closed
# Validates: Requirements 8.1, 8.2, 8.3, 8.4, 10.1, 10.4, 10.5, 9.x
# ===========================================================================
@pytest.mark.skipif(not IS_PG, reason="need PostgreSQL")
@pytest.mark.asyncio
class TestProperty10BindingClaimConflict:
    async def test_client_wp_index_mismatch(self, session):
        proj, user, wi, wp = await _lead_scenario(session)
        resp = CapturingResponder()
        req = _BA.wp(
            entrypoint="workpaper.render_config", action="read_render", method="GET",
            wp_id=wp.id, project_id=proj.id, client_wp_index_id=uuid4(),
        )
        with pytest.raises(ExternalNotFound):
            await resolve_wp_binding_and_access(session, user, req, responder=resp)
        assert resp.last_reason() == DenialReason.binding_conflict.value

    async def test_historical_version_denied(self, session):
        proj, user, wi, wp = await _lead_scenario(session)
        resp = CapturingResponder()
        req = _BA.wp(
            entrypoint="workpaper.render_config", action="read_render", method="GET",
            wp_id=wp.id, project_id=proj.id,
            requested_version=str(wp.file_version + 5),
        )
        with pytest.raises(ExternalNotFound):
            await resolve_wp_binding_and_access(session, user, req, responder=resp)
        assert resp.last_reason() == DenialReason.historical_version.value

    async def test_unmapped_sheet_denied(self, session):
        proj, user, wi, wp = await _lead_scenario(session)
        # 该 wp_index 无任何 ProcedureRowTask → sheet catalog 空 → 任意 sheet 未映射
        resp = CapturingResponder()
        req = _BA.wp(
            entrypoint="workpaper.render_config", action="read_render", method="GET",
            wp_id=wp.id, project_id=proj.id, requested_sheet_key="ZZ9",
        )
        with pytest.raises(ExternalNotFound):
            await resolve_wp_binding_and_access(session, user, req, responder=resp)
        assert resp.last_reason() == DenialReason.sheet_unmapped.value

    async def test_token_claim_mismatch(self, session):
        proj, user, wi, wp = await _lead_scenario(session)
        resp = CapturingResponder()
        req = _BA.wp(
            entrypoint="editor.config", action="editor_config", method="GET",
            wp_id=wp.id, project_id=proj.id,
            token_claims={"wp_id": str(uuid4()), "action": "editor_config"},
        )
        with pytest.raises(ExternalNotFound):
            await resolve_wp_binding_and_access(session, user, req, responder=resp)
        assert resp.last_reason() == DenialReason.token_invalid.value

    async def test_cross_project_via_wrong_declared_project(self, session):
        """声明 project 与资源真实 project 不一致 → cross_project（Req 9.2）。"""
        proj, user, wi, wp = await _lead_scenario(session)
        other = await mk_project(session)
        await session.flush()
        resp = CapturingResponder()
        req = _BA.wp(
            entrypoint="workpaper.render_config", action="read_render", method="GET",
            wp_id=wp.id, project_id=other.id,
        )
        with pytest.raises(ExternalNotFound):
            await resolve_wp_binding_and_access(session, user, req, responder=resp)
        assert resp.last_reason() == DenialReason.cross_project.value

    async def test_nonexistent_resource_not_found(self, session):
        proj, user, wi, wp = await _lead_scenario(session)
        resp = CapturingResponder()
        req = _BA.wp(
            entrypoint="workpaper.render_config", action="read_render", method="GET",
            wp_id=uuid4(), project_id=proj.id,
        )
        with pytest.raises(ExternalNotFound):
            await resolve_wp_binding_and_access(session, user, req, responder=resp)
        # wp_id 反查不到真实 project → 声明 project 兜底 → resolver 零候选 → binding_conflict
        assert resp.last_reason() == DenialReason.binding_conflict.value


# ===========================================================================
# Property 11：资源无关 429 在解析前；全部 deny 原因 → 相同 404 wire body
# Validates: Requirements 9.1–9.7, 14.18, 14.19
# ===========================================================================
@pytest.mark.skipif(not IS_PG, reason="need PostgreSQL")
@pytest.mark.asyncio
class TestProperty11RateLimitAndUniformNotFound:
    async def test_rate_limit_before_resource_resolution(self, session):
        """限流命中时资源根本不解析（用不存在 wp_id 仍返回 429 而非 404）。"""
        user = await mk_user(session)
        limiter = _DenyRateLimiter(retry_after=13)
        resp = CapturingResponder()
        req = _BA.wp(
            entrypoint="workpaper.render_config", action="read_render", method="GET",
            wp_id=uuid4(), project_id=uuid4(),
        )
        with pytest.raises(RateLimited) as ei:
            await resolve_wp_binding_and_access(
                session, user, req, rate_limiter=limiter, responder=resp
            )
        assert ei.value.status_code == 429
        assert ei.value.headers.get("Retry-After") == "13"
        # 限流仅依据 principal/project/family（资源无关）
        assert limiter.calls and limiter.calls[0][0] == user.id
        assert resp.last_reason() == DenialReason.rate_limited.value

    async def test_all_deny_reasons_identical_wire_body(self, session):
        """not_delegated / binding_conflict / sheet_unmapped / action_denied / historical_version /
        token_invalid / cross_project 的对外响应必须字节级相同（404 + 固定 detail）。"""
        proj, user, wi, wp = await _lead_scenario(session)
        other_proj = await mk_project(session)
        # 一个 scope 外用户 → not_delegated
        outsider = await mk_user(session)
        await mk_project_user(session, proj.id, outsider.id, scope_cycles="")
        await session.flush()

        cases = [
            # not_delegated（可见集空）
            (outsider, _BA.wp(
                entrypoint="workpaper.render_config", action="read_render", method="GET",
                wp_id=wp.id, project_id=proj.id)),
            # binding_conflict（不存在 wp）
            (user, _BA.wp(
                entrypoint="workpaper.render_config", action="read_render", method="GET",
                wp_id=uuid4(), project_id=proj.id)),
            # sheet_unmapped
            (user, _BA.wp(
                entrypoint="workpaper.render_config", action="read_render", method="GET",
                wp_id=wp.id, project_id=proj.id, requested_sheet_key="NOPE1")),
            # action_denied（lead 但无此登记动作）
            (user, _BA.wp(
                entrypoint="workpaper.render_config", action="totally_unknown_action",
                method="GET", wp_id=wp.id, project_id=proj.id)),
            # historical_version
            (user, _BA.wp(
                entrypoint="workpaper.render_config", action="read_render", method="GET",
                wp_id=wp.id, project_id=proj.id, requested_version="999")),
            # token_invalid
            (user, _BA.wp(
                entrypoint="editor.config", action="editor_config", method="GET",
                wp_id=wp.id, project_id=proj.id,
                token_claims={"action": ""})),
            # cross_project
            (user, _BA.wp(
                entrypoint="workpaper.render_config", action="read_render", method="GET",
                wp_id=wp.id, project_id=other_proj.id)),
        ]
        bodies = set()
        for actor, req in cases:
            with pytest.raises(ExternalNotFound) as ei:
                await resolve_wp_binding_and_access(
                    session, actor, req, responder=CapturingResponder()
                )
            assert ei.value.status_code == 404
            bodies.add(ei.value.detail)
        # 全部对外 detail 完全相同
        assert bodies == {EXTERNAL_NOT_FOUND_DETAIL}


# ===========================================================================
# Property 12：审计 outbox 失败不改变 404/429
# Validates: Requirements 9.8, 9.9, 9.10, 9.11
# ===========================================================================
@pytest.mark.skipif(not IS_PG, reason="need PostgreSQL")
@pytest.mark.asyncio
class TestProperty12AuditFailureContractStable:
    async def test_deny_404_stable_when_outbox_fails(self, session):
        proj, user, wi, wp = await _lead_scenario(session)
        failing = CapturingResponder(fail=True)
        req = _BA.wp(
            entrypoint="workpaper.render_config", action="read_render", method="GET",
            wp_id=uuid4(), project_id=proj.id,
        )
        with pytest.raises(ExternalNotFound) as ei:
            await resolve_wp_binding_and_access(session, user, req, responder=failing)
        assert ei.value.status_code == 404
        assert ei.value.detail == EXTERNAL_NOT_FOUND_DETAIL
        # 写入失败 → 未捕获任何记录，但响应不变
        assert failing.captured == []

    async def test_rate_limit_429_stable_when_outbox_fails(self, session):
        user = await mk_user(session)
        failing = CapturingResponder(fail=True)
        limiter = _DenyRateLimiter(retry_after=5)
        req = _BA.wp(
            entrypoint="workpaper.render_config", action="read_render", method="GET",
            wp_id=uuid4(), project_id=uuid4(),
        )
        with pytest.raises(RateLimited) as ei:
            await resolve_wp_binding_and_access(
                session, user, req, rate_limiter=limiter, responder=failing
            )
        assert ei.value.status_code == 429
        assert ei.value.headers.get("Retry-After") == "5"


# ===========================================================================
# PBT Property 11：任意 deny 场景对外恒 404 + 固定 detail（生成式）
# ===========================================================================
@pytest.mark.skipif(not IS_PG, reason="need PostgreSQL")
class TestProperty11PBTUniformNotFound:
    @given(
        kind=st.sampled_from(
            ["not_delegated", "binding_conflict", "sheet_unmapped", "action_denied"]
        ),
        nonce=st.integers(min_value=0, max_value=2_000_000_000),  # Task14: correctness>=100 有效样例（宽域防早停）
    )
    @settings(deadline=None)  # Task 14: profile-driven max_examples (smoke=5 / correctness>=100)
    def test_deny_always_404_fixed_body(self, kind, nonce):
        async def scenario(s):
            proj, user, wi, wp = await _lead_scenario(s)
            if kind == "not_delegated":
                actor = await mk_user(s)
                await mk_project_user(s, proj.id, actor.id, scope_cycles="")
                await s.flush()
                req = _BA.wp(
                    entrypoint="workpaper.render_config", action="read_render",
                    method="GET", wp_id=wp.id, project_id=proj.id)
            elif kind == "binding_conflict":
                actor = user
                req = _BA.wp(
                    entrypoint="workpaper.render_config", action="read_render",
                    method="GET", wp_id=uuid4(), project_id=proj.id)
            elif kind == "sheet_unmapped":
                actor = user
                req = _BA.wp(
                    entrypoint="workpaper.render_config", action="read_render",
                    method="GET", wp_id=wp.id, project_id=proj.id,
                    requested_sheet_key="XX404")
            else:  # action_denied
                actor = user
                req = _BA.wp(
                    entrypoint="workpaper.render_config", action="unknown_x",
                    method="GET", wp_id=wp.id, project_id=proj.id)

            try:
                await resolve_wp_binding_and_access(
                    s, actor, req, responder=CapturingResponder()
                )
                assert False, "expected ExternalNotFound"
            except ExternalNotFound as exc:
                assert exc.status_code == 404
                assert exc.detail == EXTERNAL_NOT_FOUND_DETAIL

        run_isolated(scenario)
