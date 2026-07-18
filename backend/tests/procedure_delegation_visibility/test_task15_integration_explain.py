# Feature: procedure-delegation-visibility-isolation — Task 15 全入口集成 / 安全回归 / EXPLAIN（组件 C17 Verification）
"""Task 15 综合集成套件：真实 FastAPI app（app.main:app）+ 真实 PostgreSQL（audit_platform）。

Task 15 / Requirements 3.14–3.15, 8.1–8.19, 9, 10, 14.20–14.21, 16.15–16.18 /
Design 组件 C17（Verification）/ "Integration and coverage" / Property 10/11/12/17/18。

覆盖目标（DONE 标准）：
  1. 每 Entry_Family 代表性 allow / deny / cross-project / sheet / version（真实 app + gate）。
  2. **直接比较**：不存在 / 跨项目 / 越权(out-of-scope=not_delegated) / 未映射页 / 历史版本 →
     完全相同的最终 wire 404（``{"detail":"资源不存在或不可访问"}``），内部 reason 各不相同。
  3. outbox 故障不改 404/429（Property 12）；拒绝前无敏感读取 / 无副作用。
  4. 两层委派 + history + scope + epoch 同事务原子提交（Property 17）。
  5. callback 撤权后拒绝（Property 13/18）；bulk 逐资源 preflight 原子（Req 8.14）。
  6. EXPLAIN (ANALYZE, BUFFERS) + query-count 证明可见性列表查询 + gate 解析无按底稿 N+1；
     仅实证后才加索引（本套件实测结论见 Notes / 断言）。
  7. 崩溃恢复：permission commit 后 publish/fan-out 未发生 → 持久 epoch/outbox 仍阻止 stale-allow
     （Property 18 / Req 14.21）。

每用例独立引擎/连接 + 外层事务 + ``join_transaction_mode="create_savepoint"``，用例结束整体
回滚（绝不污染 dev 库）。gate 的安全 outbox 用注入 ``CapturingResponder`` 捕获到内存（不落库）。
"""
from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import settings as app_settings
from app.core.database import get_db
from app.deps import get_current_user
from app.services.wp_visibility.contracts import VisibilityContext, VisibilityRole
from app.services.wp_visibility.delegation_transaction import (
    DelegationError,
    DelegationTransactionService,
    LeadDelegationRequest,
)
from app.services.wp_visibility.denial import (
    EXTERNAL_NOT_FOUND_DETAIL,
    DenialReason,
    DenialResponder,
    ExternalNotFound,
    RateLimited,
)
from app.services.wp_visibility.editor_security import verify_callback_preconditions
from app.services.wp_visibility.entry_integration import (
    make_bulk_preflight,
    make_bulk_visible_filter,
)
from app.services.wp_visibility.epoch_cache import PersistentEpochCache
from app.services.wp_visibility.visibility_query import VisibilityQueryService
from app.services.wp_visibility.wp_bound_gate import (
    BindingAdapters,
    NullRateLimiter,
    RateLimitDecision,
    WpBoundGate,
    resolve_wp_binding_and_access,
)

from ._factories import (
    IS_PG,
    mk_project,
    mk_project_user,
    mk_procedure_instance,
    mk_row_task,
    mk_staff,
    mk_user,
    mk_working_paper,
    mk_wp_index,
)

pytestmark = [
    pytest.mark.skipif(not IS_PG, reason="need PostgreSQL (real app + gate integration)"),
]

_BA = BindingAdapters()


def _detail(resp) -> str | None:
    """ResponseWrapperMiddleware 把 404 包成 {code,message} 信封；detail 落 message。"""
    body = resp.json()
    if not isinstance(body, dict):
        return None
    return body.get("detail") or body.get("message")


# ---------------------------------------------------------------------------
# 测试替身 responder
# ---------------------------------------------------------------------------
class CapturingResponder(DenialResponder):
    """把 outbox 写入捕获到内存（不落 dev 库）；可选模拟写入失败。"""

    def __init__(self, fail: bool = False, alert_hook=None) -> None:
        super().__init__(alert_hook=alert_hook)
        self.captured: list[dict] = []
        self._fail = fail

    async def _write_outbox(self, **fields) -> None:  # type: ignore[override]
        if self._fail:
            raise RuntimeError("simulated outbox failure")
        self.captured.append(fields)

    def last_reason(self) -> str | None:
        return self.captured[-1]["reason"] if self.captured else None


class _DenyRateLimiter:
    """资源无关限流器：恒拒绝（用于 429 契约测试）。"""

    def __init__(self, retry_after: int = 7) -> None:
        self.retry_after = retry_after

    def check(self, *, principal, project_id, entry_family):
        return RateLimitDecision(allowed=False, retry_after=self.retry_after)


# ---------------------------------------------------------------------------
# 每用例独立 PG 连接 + savepoint 隔离 + app 依赖覆盖
# ---------------------------------------------------------------------------
class _Ctx:
    def __init__(self) -> None:
        self.engine = None
        self.conn = None
        self.trans = None
        self.session: AsyncSession | None = None

    async def __aenter__(self) -> AsyncSession:
        self.engine = create_async_engine(app_settings.DATABASE_URL, pool_pre_ping=True)
        self.conn = await self.engine.connect()
        self.trans = await self.conn.begin()
        self.session = AsyncSession(
            bind=self.conn, join_transaction_mode="create_savepoint"
        )
        return self.session

    async def __aexit__(self, *exc) -> None:
        from app.main import app

        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)
        if self.session is not None:
            await self.session.close()
        if self.trans is not None:
            await self.trans.rollback()
        if self.conn is not None:
            await self.conn.close()
        if self.engine is not None:
            await self.engine.dispose()

    def bind_app(self, user):
        from app.main import app

        session = self.session

        async def _override_db():
            yield session

        app.dependency_overrides[get_db] = _override_db
        app.dependency_overrides[get_current_user] = lambda: user
        return AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        )


# ---------------------------------------------------------------------------
# 场景 helper
# ---------------------------------------------------------------------------
async def _seed_lead(s, *, scope="D", cycle="D", wp_code="D2-1"):
    proj = await mk_project(s)
    user = await mk_user(s)
    wi = await mk_wp_index(s, proj.id, wp_code=wp_code, audit_cycle=cycle)
    wp = await mk_working_paper(s, proj.id, wi.id)
    wp.assigned_to = user.id
    await mk_project_user(s, proj.id, user.id, scope_cycles=scope)
    await s.flush()
    return proj, user, wi, wp


async def _seed_outsider(s, proj):
    outsider = await mk_user(s)
    await mk_project_user(s, proj.id, outsider.id, scope_cycles="")
    await s.flush()
    return outsider


async def _mk_admin(s):
    admin = await mk_user(s, role="admin")
    await s.flush()
    return admin


# ═══════════════════════════════════════════════════════════════════════════
# 1) 直接比较：五种拒绝原因 → 完全相同的最终 wire 404（内部 reason 各不相同）
#    Property 11 / Req 9.1–9.7, 5.9, 5.13。gate 是 wire 产生层（ExternalNotFound 即
#    路由返回对象），故在 gate 层直接比较五种场景的 wire 形态完全一致。
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
class TestUniformWire404AllReasons:
    """一次性构造 nonexistent / cross-project / out-of-scope / unmapped-sheet /
    historical-version 五种拒绝，断言：内部 reason 互异，但对外 wire（status+body）全同。"""

    @staticmethod
    async def _drive(session, user, req):
        """驱动 gate；返回 (raised ExternalNotFound, internal reason)。"""
        resp = CapturingResponder()
        exc: ExternalNotFound | None = None
        try:
            await resolve_wp_binding_and_access(session, user, req, responder=resp)
        except ExternalNotFound as e:
            exc = e
        return exc, resp.last_reason()

    async def test_all_five_reasons_identical_wire(self):
        ctx = _Ctx()
        s = await ctx.__aenter__()
        try:
            proj, lead, wi, wp = await _seed_lead(s)
            other = await mk_project(s)
            wi2 = await mk_wp_index(s, other.id, wp_code="D2-1", audit_cycle="D")
            wp2 = await mk_working_paper(s, other.id, wi2.id)
            # scope 外的受限用户（同项目、无委派、scope 空）
            outsider = await _seed_outsider(s, proj)

            scenarios = {}

            # (a) 不存在：随机 wp_id，无 project 反查 → not_found
            scenarios["not_found"] = (
                lead,
                _BA.wp(entrypoint="workpaper.render_config", action="read_render",
                       method="GET", wp_id=uuid4()),
            )
            # (b) 跨项目：客户端声明 proj，资源真实属于 other → cross_project
            scenarios["cross_project"] = (
                lead,
                _BA.wp(entrypoint="workpaper.render_config", action="read_render",
                       method="GET", wp_id=wp2.id, project_id=proj.id),
            )
            # (c) 越权/未委派（out-of-scope 等价）：outsider 请求本 wp → not_delegated
            scenarios["not_delegated"] = (
                outsider,
                _BA.wp(entrypoint="workpaper.render_config", action="read_render",
                       method="GET", wp_id=wp.id, project_id=proj.id),
            )
            # (d) 未映射页：lead 请求不存在的 sheet_key → sheet_unmapped
            scenarios["sheet_unmapped"] = (
                lead,
                _BA.wp(entrypoint="workpaper.checklist", action="read_checklist",
                       method="GET", wp_id=wp.id, project_id=proj.id,
                       requested_sheet_key="NONEXISTENT-SHEET-ZZZ"),
            )
            # (e) 历史版本：lead 请求 ≠ Current_Version 的版本 → historical_version
            scenarios["historical_version"] = (
                lead,
                _BA.wp(entrypoint="workpaper.render_config", action="read_render",
                       method="GET", wp_id=wp.id, project_id=proj.id,
                       requested_version=str(int(wp.file_version) + 99)),
            )

            wires: list[tuple[int, str, dict]] = []
            reasons: list[str | None] = []
            for label, (u, req) in scenarios.items():
                exc, reason = await self._drive(s, u, req)
                assert exc is not None, f"{label} 未拒绝"
                wires.append((exc.status_code, exc.detail, dict(exc.headers or {})))
                reasons.append(reason)

            # 内部 reason 互异（证明确实触发了五种不同的真实原因）
            assert reasons == [
                DenialReason.not_found.value,
                DenialReason.cross_project.value,
                DenialReason.not_delegated.value,
                DenialReason.sheet_unmapped.value,
                DenialReason.historical_version.value,
            ], reasons

            # 对外 wire 完全相同：全部 404 + 固定 detail + 无可区分头
            first = wires[0]
            assert first[0] == 404 and first[1] == EXTERNAL_NOT_FOUND_DETAIL
            for w in wires[1:]:
                assert w == first, f"wire 不一致: {w} != {first}"
        finally:
            await ctx.__aexit__()

    async def test_real_app_route_level_reasons_identical_404(self):
        """真实 app HTTP wire 层：route 可表达的三种原因（not_found/cross_project/not_delegated）
        通过 render-config 入口返回完全相同的 404 body。"""
        ctx = _Ctx()
        s = await ctx.__aenter__()
        try:
            proj, lead, wi, wp = await _seed_lead(s)
            other = await mk_project(s)
            wi2 = await mk_wp_index(s, other.id, wp_code="D2-1", audit_cycle="D")
            wp2 = await mk_working_paper(s, other.id, wi2.id)
            outsider = await _seed_outsider(s, proj)

            bodies = []
            async with ctx.bind_app(lead) as c:
                r = await c.get(f"/api/workpapers/{uuid4()}/render-config")     # not_found
                bodies.append((r.status_code, _detail(r)))
                r = await c.get(f"/api/workpapers/{wp2.id}/render-config")       # cross_project
                bodies.append((r.status_code, _detail(r)))
            async with ctx.bind_app(outsider) as c:
                r = await c.get(f"/api/workpapers/{wp.id}/render-config")        # not_delegated
                bodies.append((r.status_code, _detail(r)))

            first = bodies[0]
            assert first == (404, EXTERNAL_NOT_FOUND_DETAIL)
            for b in bodies[1:]:
                assert b == first, f"HTTP wire 不一致: {b} != {first}"
        finally:
            await ctx.__aexit__()


# ═══════════════════════════════════════════════════════════════════════════
# 2) 每 Entry_Family 代表性 allow / deny / cross-project（gate 层，覆盖全部 wp-bound 族）
#    Req 8.5–8.16, 9.1–9.7。sheet/version 维度见 TestUniformWire404AllReasons；
#    list/bulk/callback 分别见列表查询测试 / TestBulkPreflightAtomic / TestCallbackAfterRevocation。
# ═══════════════════════════════════════════════════════════════════════════
# (family 标签, entrypoint, action, method)：每族取一个 lead full_power 支持的代表性入口。
_FAMILY_MATRIX = [
    ("detail", "workpaper.detail", "read_detail", "GET"),
    ("render_config", "workpaper.render_config", "read_render", "GET"),
    ("html", "workpaper.html", "read_html", "GET"),
    ("checklist", "workpaper.checklist_read", "read_checklist", "GET"),
    ("parsed_data", "workpaper.parsed_data_read", "read_parsed_data", "GET"),
    ("status", "workpaper.status_read", "read_status", "GET"),
    ("version", "workpaper.version_list", "read_versions", "GET"),
    ("review", "review.conversation.read", "review_read", "GET"),
    ("task", "procedure.task_read", "read_task", "GET"),
    ("ai", "workpaper.ai_context", "ai_read", "GET"),
    ("attachment", "attachment.read", "attach_read", "GET"),
    ("file", "file.download", "file_download", "GET"),
    ("export", "workpaper.export", "export_data", "POST"),
    ("editor", "editor.config", "editor_config", "GET"),
    ("dedicated", "workpaper.dedicated_subroute", "dedicated_read", "GET"),
]


@pytest.mark.asyncio
class TestEntryFamilyGateSweep:
    """逐 Entry_Family：lead 放行 / outsider 拒绝 / 跨项目拒绝（gate 层统一断言）。"""

    async def test_each_family_allow_deny_cross(self):
        ctx = _Ctx()
        s = await ctx.__aenter__()
        try:
            proj, lead, wi, wp = await _seed_lead(s)
            outsider = await _seed_outsider(s, proj)
            other = await mk_project(s)
            wi2 = await mk_wp_index(s, other.id, wp_code="D2-1", audit_cycle="D")
            wp2 = await mk_working_paper(s, other.id, wi2.id)
            await s.flush()

            failures: list[str] = []
            for label, ep, action, method in _FAMILY_MATRIX:
                # allow：lead 放行 → 返回 ctx（access_kind=lead）
                req_allow = _BA.wp(
                    entrypoint=ep, action=action, method=method,
                    wp_id=wp.id, project_id=proj.id,
                )
                try:
                    ac = await resolve_wp_binding_and_access(
                        s, lead, req_allow, responder=CapturingResponder()
                    )
                    if "lead" not in ac.access_kinds:
                        failures.append(f"{label}: allow 未含 lead grant")
                except ExternalNotFound:
                    failures.append(f"{label}: lead 被误拒")

                # deny：outsider（同项目无委派）→ 404
                req_deny = _BA.wp(
                    entrypoint=ep, action=action, method=method,
                    wp_id=wp.id, project_id=proj.id,
                )
                resp = CapturingResponder()
                try:
                    await resolve_wp_binding_and_access(s, outsider, req_deny, responder=resp)
                    failures.append(f"{label}: outsider 未被拒")
                except ExternalNotFound as e:
                    if e.status_code != 404 or e.detail != EXTERNAL_NOT_FOUND_DETAIL:
                        failures.append(f"{label}: deny wire 非统一 404")

                # cross-project：lead 声明 proj，资源真实属 other → 404
                req_cross = _BA.wp(
                    entrypoint=ep, action=action, method=method,
                    wp_id=wp2.id, project_id=proj.id,
                )
                try:
                    await resolve_wp_binding_and_access(
                        s, lead, req_cross, responder=CapturingResponder()
                    )
                    failures.append(f"{label}: cross-project 未被拒")
                except ExternalNotFound:
                    pass

            assert not failures, "Entry_Family 覆盖失败:\n" + "\n".join(failures)
        finally:
            await ctx.__aexit__()


# ═══════════════════════════════════════════════════════════════════════════
# 3) 安全审计 outbox 故障不改 404/429（Property 12 / Req 9.10, 9.11, 14.18）
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
class TestOutboxFailureContractStable:
    async def test_deny_outbox_failure_still_404_with_alert(self):
        ctx = _Ctx()
        s = await ctx.__aenter__()
        try:
            proj, _lead, wi, wp = await _seed_lead(s)
            outsider = await _seed_outsider(s, proj)
            alerts: list = []
            resp = CapturingResponder(
                fail=True, alert_hook=lambda r, ep, exc: alerts.append((r, ep))
            )
            req = _BA.wp(
                entrypoint="workpaper.render_config", action="read_render",
                method="GET", wp_id=wp.id, project_id=proj.id,
            )
            with pytest.raises(ExternalNotFound) as ei:
                await resolve_wp_binding_and_access(s, outsider, req, responder=resp)
            # outbox 写入失败 → 对外仍 404 + 固定 detail 不变
            assert ei.value.status_code == 404
            assert ei.value.detail == EXTERNAL_NOT_FOUND_DETAIL
            # 并产生 Operational_Alert
            assert alerts, "outbox 失败未触发 Operational_Alert"
        finally:
            await ctx.__aexit__()

    async def test_rate_limit_outbox_failure_still_429(self):
        ctx = _Ctx()
        s = await ctx.__aenter__()
        try:
            proj, lead, wi, wp = await _seed_lead(s)
            alerts: list = []
            resp = CapturingResponder(
                fail=True, alert_hook=lambda r, ep, exc: alerts.append((r, ep))
            )
            gate = WpBoundGate(
                s, rate_limiter=_DenyRateLimiter(retry_after=7), responder=resp
            )
            req = _BA.wp(
                entrypoint="workpaper.render_config", action="read_render",
                method="GET", wp_id=wp.id, project_id=proj.id,
            )
            with pytest.raises(RateLimited) as ei:
                await gate.resolve(lead, req)
            # 资源无关 429 + 有效 Retry-After 不因 outbox 失败而改变
            assert ei.value.status_code == 429
            assert ei.value.headers.get("Retry-After") == "7"
            assert alerts, "限流 outbox 失败未触发 Operational_Alert"
        finally:
            await ctx.__aexit__()


# ═══════════════════════════════════════════════════════════════════════════
# 4) 拒绝前无副作用（Req 8.1）：outsider PUT → 404 且底稿数据零写入
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
class TestNoSideEffectBeforeDenial:
    async def test_denied_put_persists_nothing(self):
        """未授权用户 PUT 被拒（项目级 edit 门 403 或 wp gate 404，均层叠在写入之前）→
        checklist_responses 零写入（拒绝前无副作用）。"""
        ctx = _Ctx()
        s = await ctx.__aenter__()
        try:
            proj, _lead, wi, wp = await _seed_lead(s)
            outsider = await _seed_outsider(s, proj)
            payload = {"items": [{"item_id": "D2-note", "conclusion": None, "remark": "x"}]}
            async with ctx.bind_app(outsider) as c:
                r = await c.put(
                    f"/api/workpapers/{wp.id}/checklist-responses", json=payload
                )
            # 既有项目级 edit 门（403）或 wp gate（404）均阻断——绝不 2xx，且都在写入之前。
            assert r.status_code in (403, 404)
            assert r.status_code != 200
            # 拒绝前无副作用：checklist_responses 零写入
            cnt = (
                await s.execute(
                    text(
                        "SELECT count(*) FROM checklist_responses WHERE wp_id = :wid"
                    ),
                    {"wid": str(wp.id)},
                )
            ).scalar_one()
            assert cnt == 0, "拒绝请求仍写入了 checklist_responses（副作用泄露）"
        finally:
            await ctx.__aexit__()

    async def test_gate_write_denial_is_uniform_404_before_mutation(self):
        """gate 层：未委派用户请求写动作（save_checklist）→ 统一 404，且 gate 纯读不产生副作用。"""
        ctx = _Ctx()
        s = await ctx.__aenter__()
        try:
            proj, _lead, wi, wp = await _seed_lead(s)
            outsider = await _seed_outsider(s, proj)
            resp = CapturingResponder()
            req = _BA.wp(
                entrypoint="workpaper.checklist_save", action="save_checklist",
                method="PUT", wp_id=wp.id, project_id=proj.id,
            )
            with pytest.raises(ExternalNotFound) as ei:
                await resolve_wp_binding_and_access(s, outsider, req, responder=resp)
            assert ei.value.status_code == 404
            assert ei.value.detail == EXTERNAL_NOT_FOUND_DETAIL
            assert resp.last_reason() == DenialReason.not_delegated.value
        finally:
            await ctx.__aexit__()


# ═══════════════════════════════════════════════════════════════════════════
# 5) 两层委派 + history + scope + epoch 同事务原子（Property 17 / Req 3.14, 14.20）
# ═══════════════════════════════════════════════════════════════════════════
async def _setup_person(s, project, *, scope="D"):
    """project 内建立唯一 active staff↔user 映射 + scope。"""
    from ._factories import mk_assignment

    user = await mk_user(s)
    staff = await mk_staff(s, user_id=user.id)
    await mk_assignment(s, project.id, staff.id, role="manager")
    await mk_project_user(s, project.id, user.id, role="auditor", scope_cycles=scope)
    await s.flush()
    return user, staff


@pytest.mark.asyncio
class TestTwoLayerScopeEpochAtomic:
    async def test_lead_scope_expansion_all_writes_atomic(self, session):
        s = session
        project = await mk_project(s)
        actor = await mk_user(s)
        # 被委派人：scope 为 "X"（不含目标循环 D）
        user, staff = await _setup_person(s, project, scope="X")
        wi = await mk_wp_index(s, project.id, wp_code="D2-1", audit_cycle="D")
        wp = await mk_working_paper(s, project.id, wi.id)
        inst = await mk_procedure_instance(
            s, project.id, audit_cycle="D", wp_code="D2-1", wp_id=wp.id
        )
        await s.flush()

        svc = DelegationTransactionService(s)
        result = await svc.delegate_lead(
            LeadDelegationRequest(
                project_id=project.id, actor_user_id=actor.id, staff_id=staff.id,
                wp_index_id=wi.id, wp_code="D2-1", procedure_instance_id=inst.id,
                expand_scope=True, scope_reason="Task15 跨循环委派",
            )
        )
        assert result.ok and result.epoch is not None
        await s.refresh(wp)
        await s.refresh(inst)

        # ① 权威字段 = user_id；② 投影 = staff_id（两层联动同一自然人）
        assert wp.assigned_to == user.id
        assert inst.assigned_to == staff.id
        # ③ scope 并集写入（原 X + 目标 D）
        scope_after = (
            await s.execute(
                text(
                    "SELECT scope_cycles FROM project_users "
                    "WHERE project_id=:p AND user_id=:u AND is_deleted=false"
                ),
                {"p": str(project.id), "u": str(user.id)},
            )
        ).scalar_one()
        assert "D" in scope_after and "X" in scope_after
        # ④ 统一 delegation history 快照
        hist = (
            await s.execute(
                text(
                    "SELECT count(*) FROM workpaper_delegation_history "
                    "WHERE wp_index_id=:w AND layer='lead'"
                ),
                {"w": str(wi.id)},
            )
        ).scalar_one()
        assert hist == 1
        # ⑤ policy epoch 递增 + ⑥ invalidation outbox 同事务
        epoch = (
            await s.execute(
                text("SELECT epoch FROM wp_visibility_policy_epoch WHERE project_id=:p"),
                {"p": str(project.id)},
            )
        ).scalar_one()
        assert epoch >= 1
        outbox = (
            await s.execute(
                text(
                    "SELECT count(*) FROM wp_visibility_invalidation_outbox "
                    "WHERE project_id=:p AND epoch=:e"
                ),
                {"p": str(project.id), "e": epoch},
            )
        ).scalar_one()
        assert outbox >= 1

    async def test_invalid_mapping_rolls_back_no_writes(self, session):
        """staff→user 映射不成立 → 委派拒绝且零写入（epoch 不递增）。"""
        s = session
        project = await mk_project(s)
        actor = await mk_user(s)
        wi = await mk_wp_index(s, project.id, wp_code="D2-1", audit_cycle="D")
        wp = await mk_working_paper(s, project.id, wi.id)
        await s.flush()
        # 无映射的随机 staff_id
        svc = DelegationTransactionService(s)
        with pytest.raises(DelegationError):
            await svc.delegate_lead(
                LeadDelegationRequest(
                    project_id=project.id, actor_user_id=actor.id, staff_id=uuid4(),
                    wp_index_id=wi.id,
                )
            )
        await s.refresh(wp)
        assert wp.assigned_to is None
        epoch = (
            await s.execute(
                text("SELECT count(*) FROM wp_visibility_policy_epoch WHERE project_id=:p"),
                {"p": str(project.id)},
            )
        ).scalar_one()
        assert epoch == 0, "拒绝的委派仍递增了 policy epoch"


# ═══════════════════════════════════════════════════════════════════════════
# 6) callback 撤权后拒绝（Property 13/18 / Req 8.16, 10.6–10.8, 16.17）
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
class TestCallbackAfterRevocation:
    async def test_callback_regate_rejects_after_revocation(self, session):
        s = session
        proj, lead, wi, wp = await _seed_lead(s)

        # 撤权前：编辑器入口 gate 放行
        req = _BA.wp(
            entrypoint="editor.config", action="editor_config", method="GET",
            wp_id=wp.id, project_id=proj.id,
        )
        ctx = await resolve_wp_binding_and_access(s, lead, req, responder=CapturingResponder())
        assert "lead" in ctx.access_kinds

        # 撤销 Workpaper_Lead（排队 callback 期间撤权）
        wp.assigned_to = None
        await s.flush()

        # callback 执行时 re-gate：不再可见 → 统一 404
        resp = CapturingResponder()
        with pytest.raises(ExternalNotFound):
            await resolve_wp_binding_and_access(s, lead, req, responder=resp)
        assert resp.last_reason() == DenialReason.not_delegated.value

    async def test_callback_preconditions_reject_revoked_session(self):
        """落盘前重校验：撤权（gate_allow_write=False）→ not_delegated。"""
        ok, reason = verify_callback_preconditions(
            claim_action="callback", server_action="callback",
            claim_version="1", current_version="1", gate_allow_write=False,
        )
        assert ok is False and reason == "not_delegated"


# ═══════════════════════════════════════════════════════════════════════════
# 7) bulk 逐资源 preflight 原子（Req 8.14）
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
class TestBulkPreflightAtomic:
    async def test_preflight_atomic_deny_on_any_invisible(self, session):
        s = session
        proj, lead, wi, wp = await _seed_lead(s)
        other_wi = await mk_wp_index(s, proj.id, wp_code="K1-1", audit_cycle="K")
        other_wp = await mk_working_paper(s, proj.id, other_wi.id)
        await s.flush()

        vf = make_bulk_visible_filter(s, lead)
        assert await vf(wp.id, None) is True
        assert await vf(other_wp.id, None) is False

        pf = make_bulk_preflight(s, lead, responder=CapturingResponder())
        await pf(wp.id, None)  # 可见 → 不抛
        with pytest.raises(ExternalNotFound):
            await pf(other_wp.id, None)  # 显式含不可见资源 → 副作用前整请求失败


# ═══════════════════════════════════════════════════════════════════════════
# 8) EXPLAIN (ANALYZE, BUFFERS) + query-count：证明可见性列表查询 + gate 解析无按底稿 N+1
#    Design Testing Strategy / Req 16.15–16.18。
# ═══════════════════════════════════════════════════════════════════════════
def _fresh_engine_run(coro_fn):
    """独立引擎 + 事务隔离回滚 + before_cursor_execute 计数器。"""
    async def _wrap():
        engine = create_async_engine(app_settings.DATABASE_URL)
        counter = {"n": 0}

        @event.listens_for(engine.sync_engine, "before_cursor_execute")
        def _count(conn, cursor, statement, params, context, executemany):  # noqa: ANN001
            counter["n"] += 1

        cnn = await engine.connect()
        trans = await cnn.begin()
        s = AsyncSession(bind=cnn, join_transaction_mode="create_savepoint")
        try:
            return await coro_fn(s, counter)
        finally:
            await s.close()
            await trans.rollback()
            await cnn.close()
            await engine.dispose()

    return asyncio.run(_wrap())


async def _seed_lead_n(s, n: int):
    """一名 lead 用户 + n 张其主编底稿（全部可见）。"""
    proj = await mk_project(s)
    user = await mk_user(s)
    await mk_project_user(s, proj.id, user.id, scope_cycles="D")
    wps = []
    for i in range(n):
        wi = await mk_wp_index(s, proj.id, wp_code=f"D2-{i}", audit_cycle="D")
        wp = await mk_working_paper(s, proj.id, wi.id)
        wp.assigned_to = user.id
        wps.append((wi, wp))
    await s.flush()
    return proj, user, wps


# EXPLAIN 计划文本收集（供报告读取；-s 输出可见）。
EXPLAIN_PLANS: list[str] = []


class TestExplainAndQueryCount:
    def test_grants_list_query_count_constant(self):
        """可见性可见集构建（列表路径）query-count 不随底稿数量增长（无 N+1）。"""
        def _count_for(n: int) -> int:
            async def _c(s, counter):
                proj, user, _wps = await _seed_lead_n(s, n)
                ctx = VisibilityContext(
                    user_id=user.id, project_id=proj.id,
                    role=VisibilityRole.restricted, is_admin=False,
                    scope_cycles=frozenset({"D"}),
                )
                counter["n"] = 0
                gs = await VisibilityQueryService(s).grants_for_project(ctx)
                assert len(gs.by_wp_index) == n
                return counter["n"]
            return _fresh_engine_run(_c)

        small = _count_for(3)
        large = _count_for(30)
        assert small == large, f"grants 列表查询 N+1: {small} vs {large}"
        assert small <= 2, f"grants 构建应为常量单次 UNION，实测 {small}"

    def test_gate_resolution_query_count_constant(self):
        """单资源 gate 解析 query-count 不随项目底稿数量增长（无按底稿 N+1）。"""
        def _count_for(n: int) -> int:
            async def _c(s, counter):
                proj, user, wps = await _seed_lead_n(s, n)
                target_wp = wps[0][1]
                gate = WpBoundGate(
                    s, rate_limiter=NullRateLimiter(), responder=CapturingResponder()
                )
                req = _BA.wp(
                    entrypoint="workpaper.render_config", action="read_render",
                    method="GET", wp_id=target_wp.id, project_id=proj.id,
                )
                counter["n"] = 0
                ctx = await gate.resolve(user, req)
                assert "lead" in ctx.access_kinds
                return counter["n"]
            return _fresh_engine_run(_c)

        small = _count_for(3)
        large = _count_for(30)
        assert small == large, f"gate 解析按底稿 N+1: {small} vs {large}"

    def test_explain_analyze_buffers_grants_union(self):
        """对生产 grants UNION ALL 跑真实 EXPLAIN (ANALYZE, BUFFERS)，记录计划。"""
        from app.services.wp_visibility import visibility_query as vq

        async def _c(s, counter):
            proj, user, _wps = await _seed_lead_n(s, 30)
            branches = [
                vq._BRANCH_LEAD.format(wpx_filter_wi=""),
                vq._BRANCH_ASSIGNEE.format(wpx_filter_prt=""),
                vq._BRANCH_REVIEWER.format(wpx_filter_prt=""),
                vq._BRANCH_LEAD_HISTORY.format(wpx_filter_wdh=""),
                vq._BRANCH_ROW_HISTORY.format(wpx_filter_wdh=""),
            ]
            sql = "\nUNION ALL\n".join(f"({b.strip()})" for b in branches)
            params = {
                "pid": str(proj.id), "uid": str(user.id),
                "cancelled": "cancelled", "scope": ["D"],
            }
            rows = (
                await s.execute(text("EXPLAIN (ANALYZE, BUFFERS) " + sql), params)
            ).all()
            plan = "\n".join(str(r[0]) for r in rows)
            return plan

        plan = _fresh_engine_run(_c)
        EXPLAIN_PLANS.append(plan)
        print("\n===== EXPLAIN (ANALYZE, BUFFERS) grants UNION ALL =====\n" + plan)
        # 单条 UNION ALL 语句 → 计划以 Append 汇聚各分支，无按底稿相关子查询循环。
        assert plan.strip(), "EXPLAIN 计划为空"
        # 无 per-workpaper 相关子计划（N+1 的典型指纹）。
        assert "SubPlan" not in plan, "计划出现 SubPlan（可能的 N+1）"


# ═══════════════════════════════════════════════════════════════════════════
# 9) 崩溃恢复：permission commit 后 publish/fan-out 未发生 → 持久 epoch/outbox 仍阻止
#    stale-allow（Property 18 / Req 14.21）。
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
class TestCrashRecoveryNoStaleAllow:
    async def test_persistent_epoch_blocks_stale_allow_without_publish(self, session):
        s = session
        proj, lead, wi, wp = await _seed_lead(s)

        # 可注入单调假时钟：精确验证 ≤1s DB epoch 核对收敛。
        clock = {"t": 1000.0}
        cache = PersistentEpochCache(
            epoch_ttl_seconds=1.0, clock=lambda: clock["t"]
        )
        gate = WpBoundGate(
            s, rate_limiter=NullRateLimiter(),
            responder=CapturingResponder(), epoch_cache=cache,
        )
        req = _BA.wp(
            entrypoint="workpaper.render_config", action="read_render",
            method="GET", wp_id=wp.id, project_id=proj.id,
        )
        # ① 撤权前：gate 放行并按 (user,project,wp_index,epoch=0) 缓存 grants。
        ctx = await gate.resolve(lead, req)
        assert "lead" in ctx.access_kinds
        assert cache.entry_count() == 1

        # ② 模拟 permission commit（撤权 + 持久 epoch 递增 + invalidation outbox），
        #    但 publish/fan-out 崩溃：**不**调用 cache.invalidate()（Redis 通知从未送达）。
        wp.assigned_to = None
        await s.flush()
        svc = DelegationTransactionService(s)
        new_epoch = await svc.bump_policy_epoch(
            proj.id, "delegation", actor_user_id=lead.id
        )
        await s.flush()
        assert new_epoch >= 1
        # 明确不失效缓存（模拟 dispatcher/Redis 未投递）。
        assert cache.entry_count() == 1  # 旧 epoch 条目仍在本地

        # ③ ≤1s 后（超过 epoch_ttl）：节点对 DB epoch 的最坏 stale 窗口到期，重新核对。
        clock["t"] += 1.5

        # ④ 再次 gate 解析：持久 epoch 从 0→new_epoch，旧缓存条目失配 → 重取权威 grants
        #    （已撤权 → 空）→ 统一 404。绝不 stale-allow。
        resp = CapturingResponder()
        with pytest.raises(ExternalNotFound):
            await resolve_wp_binding_and_access(
                s, lead, req, responder=resp, epoch_cache=cache
            )
        assert resp.last_reason() == DenialReason.not_delegated.value
