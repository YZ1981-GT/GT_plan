# Feature: procedure-delegation-visibility-isolation — Task 13 epoch cache / measurement-mode 限流 / 观测
"""Task 13（组件 C15 Cache/Rate/Perf）：persistent epoch 缓存、measurement-mode 限流与性能观测。

属性编号以 **prompt / design 权威编号** 为准：

  - **Property 18**（Revocation converges within one second without stale allow）：
    缓存 key 含 user+project+持久 epoch；撤权→epoch 递增后旧条目永不被 allow；≤1s DB 核对（安全网）+
    Redis 即时淘汰（快路径）双路径收敛；Redis/dispatcher 失败时同步查 DB epoch 或以 authoritative
    现取（fail-closed），绝不 stale-allow。
    **Validates: Requirements 14.13, 14.14, 14.15, 14.21**（并经 gate 体现 14.19 资源无关拒绝）。

  - **Property 19**（Rate profiles require measured capacity evidence）：
    Rate_Limit_Profile 必须由 6000 并发容量报告 + hash 生成并冻结；无证据 inert（measurement-only，
    绝不预设阈值 / 绝无固定 10 RPS）；阈内不误限、超阈返回带有效 Retry-After 的资源无关 429。
    **Validates: Requirements 14.1–14.12, 14.16, 14.17, 14.18**。

  - 观测机制（Req 14.2/14.3/14.4/14.5/9.9）：gate/list 延迟 p95、query count、cache hit/miss/stale-deny、
    拒绝 reason、错误允许数（error_allow，验收恒 0）。

SQL 语义（persistent epoch 读取自 ``wp_visibility_policy_epoch``）在真实 PostgreSQL（audit_platform）
验证，非 sqlite/mock；每用例事务隔离回滚。Rate_Limit_Profile 为纯内存契约，直接单测。
"""
from __future__ import annotations

from uuid import uuid4

import pytest
import sqlalchemy as sa

from app.models.wp_visibility_models import WpVisibilityPolicyEpoch
from app.services.wp_visibility.denial import DenialReason, ExternalNotFound, RateLimited
from app.services.wp_visibility.epoch_cache import (
    EpochUnavailable,
    PersistentEpochCache,
    invalidation_channel,
)
from app.services.wp_visibility.perf_metrics import (
    VisibilityMetrics,
    measure,
    percentile,
)
from app.services.wp_visibility.rate_limit_profile import (
    TARGET_CONCURRENCY,
    CapacityReport,
    MeasurementModeRateLimiter,
    PerformanceProfile,
    RateLimitProfileError,
    freeze_rate_limit_profile,
    measurement_only_profile,
)
from app.services.wp_visibility.wp_bound_gate import BindingAdapters, resolve_wp_binding_and_access

from ._factories import (
    IS_PG,
    mk_project,
    mk_project_user,
    mk_user,
    mk_working_paper,
    mk_wp_index,
)
from .test_wp_bound_gate import CapturingResponder

_BA = BindingAdapters()


class _Clock:
    """可控单调假时钟：精确验证 ≤1s epoch 核对窗口。"""

    def __init__(self, start: float = 1000.0) -> None:
        self.t = start

    def __call__(self) -> float:
        return self.t

    def advance(self, dt: float) -> None:
        self.t += dt


async def _lead_scenario(s, *, scope="D", cycle="D", epoch=1):
    """lead 底稿 + 已插入 policy epoch 行（持久 epoch 真源）。"""
    proj = await mk_project(s)
    user = await mk_user(s)
    wi = await mk_wp_index(s, proj.id, wp_code="D2-1", audit_cycle=cycle)
    wp = await mk_working_paper(s, proj.id, wi.id)
    wp.assigned_to = user.id
    await mk_project_user(s, proj.id, user.id, scope_cycles=scope)
    s.add(WpVisibilityPolicyEpoch(project_id=proj.id, epoch=epoch))
    await s.flush()
    return proj, user, wi, wp


async def _set_epoch(s, project_id, epoch: int) -> None:
    await s.execute(
        sa.update(WpVisibilityPolicyEpoch)
        .where(WpVisibilityPolicyEpoch.project_id == project_id)
        .values(epoch=epoch)
    )
    await s.flush()


# ===========================================================================
# Property 18 · 缓存机制单元（epoch key、≤1s 收敛、Redis 淘汰、fail-closed）
# ===========================================================================
@pytest.mark.skipif(not IS_PG, reason="need PostgreSQL (persistent policy epoch)")
@pytest.mark.asyncio
class TestProperty18EpochCache:
    async def test_cache_key_includes_epoch_and_hits(self, session):
        """相同 (user,project,wp_index,epoch) → 命中缓存，loader 只调用一次。"""
        proj, user, wi, wp = await _lead_scenario(session)
        clock = _Clock()
        metrics = VisibilityMetrics()
        cache = PersistentEpochCache(epoch_ttl_seconds=1.0, clock=clock, metrics=metrics)
        calls = {"n": 0}

        async def loader():
            calls["n"] += 1
            return ["grant-A"]

        v1 = await cache.get_or_load(
            session, user_id=user.id, project_id=proj.id, wp_index_id=wi.id, loader=loader
        )
        v2 = await cache.get_or_load(
            session, user_id=user.id, project_id=proj.id, wp_index_id=wi.id, loader=loader
        )
        assert v1 == v2 == ["grant-A"]
        assert calls["n"] == 1  # 第二次命中缓存
        assert metrics.cache_hit == 1 and metrics.cache_miss == 1

    async def test_epoch_bump_within_ttl_then_converges_after_ttl(self, session):
        """撤权→epoch 递增：≤1s 窗口内仍旧值（收敛上界），>ttl 后强制 authoritative 重取（不 stale）。"""
        proj, user, wi, wp = await _lead_scenario(session, epoch=1)
        clock = _Clock()
        cache = PersistentEpochCache(epoch_ttl_seconds=1.0, clock=clock)
        state = {"grants": ["lead"]}

        async def loader():
            return list(state["grants"])

        # 初次：epoch=1 缓存 lead grant
        assert await cache.get_or_load(
            session, user_id=user.id, project_id=proj.id, wp_index_id=wi.id, loader=loader
        ) == ["lead"]

        # 撤权：DB epoch 1→2，权威结果变空
        await _set_epoch(session, proj.id, 2)
        state["grants"] = []

        # 窗口内（未过 ttl）：epoch 新鲜度仍为 1 → 命中旧条目（≤1s 收敛上界，允许）
        clock.advance(0.4)
        assert await cache.get_or_load(
            session, user_id=user.id, project_id=proj.id, wp_index_id=wi.id, loader=loader
        ) == ["lead"]

        # 超过 ttl：重读 DB epoch=2 → 旧 epoch=1 条目永不匹配 → authoritative 重取空（收敛，不 stale-allow）
        clock.advance(1.0)
        assert await cache.get_or_load(
            session, user_id=user.id, project_id=proj.id, wp_index_id=wi.id, loader=loader
        ) == []
        assert cache.cached_epoch_for(proj.id) == 2

    async def test_redis_invalidate_converges_immediately(self, session):
        """Redis 失效通知（快路径）→ 立即淘汰，无需等 ttl 即收敛。"""
        proj, user, wi, wp = await _lead_scenario(session, epoch=1)
        clock = _Clock()
        cache = PersistentEpochCache(epoch_ttl_seconds=1.0, clock=clock)
        state = {"grants": ["lead"]}

        async def loader():
            return list(state["grants"])

        await cache.get_or_load(
            session, user_id=user.id, project_id=proj.id, wp_index_id=wi.id, loader=loader
        )
        await _set_epoch(session, proj.id, 2)
        state["grants"] = []

        # 收到 Redis 失效 → 立即淘汰（不推进时钟）
        cache.invalidate(proj.id)
        assert await cache.get_or_load(
            session, user_id=user.id, project_id=proj.id, wp_index_id=wi.id, loader=loader
        ) == []
        assert cache.cached_epoch_for(proj.id) == 2

    async def test_epoch_unavailable_fails_closed_no_stale(self, session):
        """DB epoch 不可得（Redis+dispatcher 全挂的最坏情形）→ 不用缓存，authoritative 现取（非 stale）。"""
        proj, user, wi, wp = await _lead_scenario(session, epoch=1)
        metrics = VisibilityMetrics()
        cache = PersistentEpochCache(metrics=metrics)
        state = {"grants": ["lead"]}

        async def loader():
            return list(state["grants"])

        # 预热缓存（epoch=1）
        await cache.get_or_load(
            session, user_id=user.id, project_id=proj.id, wp_index_id=wi.id, loader=loader
        )

        # 强制 epoch 读取失败
        async def _boom(_db, _pid):
            raise EpochUnavailable(str(_pid))

        cache.current_epoch = _boom  # type: ignore[assignment]
        state["grants"] = []  # 撤权已发生
        # fail-closed：不返回旧缓存条目，直接权威现取空 → 绝不 stale-allow
        assert await cache.get_or_load(
            session, user_id=user.id, project_id=proj.id, wp_index_id=wi.id, loader=loader
        ) == []
        assert metrics.cache_stale_deny >= 1


def test_invalidation_channel_is_per_project():
    pid = uuid4()
    assert invalidation_channel(pid) == f"wp_visibility:invalidate:{pid}"


# ===========================================================================
# Property 18 · 经 gate 端到端（撤权 ≤1s 收敛，资源无关 404）
# ===========================================================================
@pytest.mark.skipif(not IS_PG, reason="need PostgreSQL")
@pytest.mark.asyncio
class TestProperty18ThroughGate:
    async def test_gate_with_epoch_cache_allows_then_denies_after_revoke(self, session):
        proj, user, wi, wp = await _lead_scenario(session, epoch=1)
        clock = _Clock()
        cache = PersistentEpochCache(epoch_ttl_seconds=1.0, clock=clock)
        req = _BA.wp(
            entrypoint="workpaper.render_config", action="read_render", method="GET",
            wp_id=wp.id, project_id=proj.id,
        )
        # 允许（经缓存）
        ctx = await resolve_wp_binding_and_access(
            session, user, req, responder=CapturingResponder(), epoch_cache=cache
        )
        assert ctx.access_kinds == frozenset({"lead"})

        # 撤权 + epoch 递增（模拟 DelegationTransaction 提交）
        wp.assigned_to = None
        await session.flush()
        await _set_epoch(session, proj.id, 2)

        # 立即再请求（窗口内命中旧缓存 → 仍 allow，属 ≤1s 收敛上界）
        ctx2 = await resolve_wp_binding_and_access(
            session, user, req, responder=CapturingResponder(), epoch_cache=cache
        )
        assert ctx2.access_kinds == frozenset({"lead"})

        # ≤1s 后：epoch 核对发现递增 → 重取空 grants → 统一 404（not_delegated），绝不 stale-allow
        clock.advance(1.01)
        resp = CapturingResponder()
        with pytest.raises(ExternalNotFound) as ei:
            await resolve_wp_binding_and_access(
                session, user, req, responder=resp, epoch_cache=cache
            )
        assert ei.value.status_code == 404
        assert resp.last_reason() == DenialReason.not_delegated.value

    async def test_gate_epoch_cache_immediate_invalidate_denies(self, session):
        proj, user, wi, wp = await _lead_scenario(session, epoch=1)
        cache = PersistentEpochCache()
        req = _BA.wp(
            entrypoint="workpaper.render_config", action="read_render", method="GET",
            wp_id=wp.id, project_id=proj.id,
        )
        await resolve_wp_binding_and_access(
            session, user, req, responder=CapturingResponder(), epoch_cache=cache
        )
        wp.assigned_to = None
        await session.flush()
        await _set_epoch(session, proj.id, 2)
        cache.invalidate(proj.id)  # Redis 快路径
        with pytest.raises(ExternalNotFound):
            await resolve_wp_binding_and_access(
                session, user, req, responder=CapturingResponder(), epoch_cache=cache
            )


# ===========================================================================
# Property 19 · Rate_Limit_Profile 需容量证据 + measurement-mode
# ===========================================================================
class TestProperty19RateLimitProfile:
    def test_measurement_only_profile_is_inert_no_thresholds(self):
        p = measurement_only_profile()
        assert p.is_active is False
        # 绝无预设业务阈值 / 固定 10 RPS
        assert p.per_user == {} and p.per_project == {} and p.per_family == {}
        assert p.capacity_report_hash is None
        assert p.frozen is False

    def test_measurement_limiter_never_limits_when_inert(self):
        limiter = MeasurementModeRateLimiter(measurement_only_profile())
        uid, pid = uuid4(), uuid4()
        # 高频调用也永不限流（inert = measurement-only）
        for _ in range(500):
            assert limiter.check(principal=uid, project_id=pid, entry_family="list") is None
        snap = limiter.observation_snapshot()
        # 仍记录观测（供 Task 17 反推阈值）
        assert any(v == 500 for v in snap.values())

    def test_freeze_requires_matching_performance_version(self):
        perf = PerformanceProfile(version="perf-1", target_concurrency=TARGET_CONCURRENCY)
        bad_report = CapacityReport(
            performance_profile_version="perf-DIFFERENT", measured_at="2026-07-16T00:00:00Z"
        )
        with pytest.raises(RateLimitProfileError):
            freeze_rate_limit_profile(
                version="rl-1", performance_profile=perf, capacity_report=bad_report,
                per_family={"list": 50},
            )

    def test_freeze_requires_positive_thresholds(self):
        perf = PerformanceProfile(version="perf-1")
        report = CapacityReport(
            performance_profile_version="perf-1", measured_at="2026-07-16T00:00:00Z"
        )
        with pytest.raises(RateLimitProfileError):
            freeze_rate_limit_profile(
                version="rl-1", performance_profile=perf, capacity_report=report,
                per_family={"list": 0},
            )

    def test_freeze_requires_some_threshold(self):
        perf = PerformanceProfile(version="perf-1")
        report = CapacityReport(
            performance_profile_version="perf-1", measured_at="2026-07-16T00:00:00Z"
        )
        with pytest.raises(RateLimitProfileError):
            freeze_rate_limit_profile(
                version="rl-1", performance_profile=perf, capacity_report=report,
            )

    def test_frozen_profile_activates_and_references_capacity_hash(self):
        perf = PerformanceProfile(
            version="perf-6000", target_concurrency=TARGET_CONCURRENCY,
            ramp="0->6000/300s", request_rate="measured", duration="600s",
        )
        report = CapacityReport(
            performance_profile_version="perf-6000",
            measured_at="2026-07-16T00:00:00Z",
            results={"list_p95_seconds": 1.3, "gate_p95_seconds": 0.4, "error_rate": 0.002},
        )
        prof = freeze_rate_limit_profile(
            version="rl-6000", performance_profile=perf, capacity_report=report,
            per_user={"list": 20}, per_project={"list": 200}, per_family={"list": 2000},
            window_seconds=1.0,
        )
        assert prof.is_active is True
        assert prof.frozen is True
        assert prof.capacity_report_hash == report.content_hash()
        assert prof.source_performance_profile_version == "perf-6000"

    def test_activated_limiter_within_threshold_then_429_with_retry_after(self):
        perf = PerformanceProfile(version="perf-6000")
        report = CapacityReport(
            performance_profile_version="perf-6000", measured_at="2026-07-16T00:00:00Z",
            results={"ok": True},
        )
        prof = freeze_rate_limit_profile(
            version="rl-6000", performance_profile=perf, capacity_report=report,
            per_user={"list": 3}, window_seconds=1.0,
        )
        clock = _Clock()
        limiter = MeasurementModeRateLimiter(prof, clock=clock, metrics=VisibilityMetrics())
        uid, pid = uuid4(), uuid4()
        # 阈内（3 次）不限流
        for _ in range(3):
            assert limiter.check(principal=uid, project_id=pid, entry_family="list") is None
        # 第 4 次超阈 → 限流 + 有效 Retry-After
        d = limiter.check(principal=uid, project_id=pid, entry_family="list")
        assert d is not None and d.allowed is False
        assert d.retry_after >= 1
        # 窗口滑过后恢复
        clock.advance(1.01)
        assert limiter.check(principal=uid, project_id=pid, entry_family="list") is None

    def test_unfrozen_thresholds_stay_inert(self):
        """有阈值但未冻结/无容量 hash → 仍 inert（无证据不生效，Property 19）。"""
        from app.services.wp_visibility.rate_limit_profile import RateLimitProfile

        p = RateLimitProfile(
            version="draft", per_family={"list": 1}, capacity_report_hash=None, frozen=False
        )
        assert p.is_active is False
        limiter = MeasurementModeRateLimiter(p)
        uid, pid = uuid4(), uuid4()
        for _ in range(50):
            assert limiter.check(principal=uid, project_id=pid, entry_family="list") is None


# ===========================================================================
# Property 19 · 资源无关 429（经 gate，14.18）
# ===========================================================================
@pytest.mark.skipif(not IS_PG, reason="need PostgreSQL")
@pytest.mark.asyncio
class TestProperty19ResourceIndependent429:
    async def test_activated_profile_429_before_resource_resolution(self, session):
        """激活 profile 超阈时，gate 在解析资源前就 429（用不存在 wp/project 仍 429，非 404）。"""
        user = await mk_user(session)
        perf = PerformanceProfile(version="perf-6000")
        report = CapacityReport(
            performance_profile_version="perf-6000", measured_at="2026-07-16T00:00:00Z",
            results={"ok": True},
        )
        prof = freeze_rate_limit_profile(
            version="rl-6000", performance_profile=perf, capacity_report=report,
            per_family={"list": 1}, window_seconds=1.0,
        )
        limiter = MeasurementModeRateLimiter(prof)
        req = _BA.wp(
            entrypoint="workpaper.list", action="list", method="GET",
            wp_id=uuid4(), project_id=uuid4(), entry_family="list",
        )
        # 首次放行 → 资源不存在 → 但因限流器未超阈，继续解析 → binding_conflict 404
        with pytest.raises(ExternalNotFound):
            await resolve_wp_binding_and_access(
                session, user, req, rate_limiter=limiter, responder=CapturingResponder()
            )
        # 第二次超阈 → 资源无关 429（资源根本不解析，证明存在性不可推断）
        with pytest.raises(RateLimited) as ei:
            await resolve_wp_binding_and_access(
                session, user, req, rate_limiter=limiter, responder=CapturingResponder()
            )
        assert ei.value.status_code == 429
        assert int(ei.value.headers["Retry-After"]) >= 1

    async def test_measurement_default_never_limits_through_gate(self, session):
        """gate 默认 measurement-mode 限流器 inert → 永不 429（与旧 NullRateLimiter 行为一致）。"""
        proj, user, wi, wp = await _lead_scenario(session)
        req = _BA.wp(
            entrypoint="workpaper.render_config", action="read_render", method="GET",
            wp_id=wp.id, project_id=proj.id,
        )
        # 不注入 rate_limiter → 用生产默认（inert measurement-mode）
        ctx = await resolve_wp_binding_and_access(
            session, user, req, responder=CapturingResponder()
        )
        assert ctx.access_kinds == frozenset({"lead"})


# ===========================================================================
# 观测机制（延迟 p95 / query count / error_allow / reason 分布）
# ===========================================================================
class TestObservabilityMetrics:
    def test_percentile_nearest_rank(self):
        assert percentile([], 95) == 0.0
        assert percentile([1.0], 95) == 1.0
        vals = [float(i) for i in range(1, 101)]  # 1..100
        assert percentile(vals, 95) == 95.0

    def test_measure_records_latency_and_p95(self):
        m = VisibilityMetrics()
        clock = _Clock()

        def _clk() -> float:
            return clock.t

        for dt in (0.1, 0.2, 0.3, 0.4, 2.5):
            with measure(m.observe_gate_latency, clock=_clk):
                clock.advance(dt)
        assert len(m.gate_latencies) == 5
        assert m.p95_gate_latency() == 2.5

    def test_error_allow_and_reason_distribution(self):
        m = VisibilityMetrics()
        m.record_gate_allow()
        m.record_error()
        m.record_denial(DenialReason.not_delegated.value)
        m.record_denial(DenialReason.rate_limited.value)
        m.record_cache_stale_deny()
        snap = m.snapshot()
        assert snap["error_allow"] == 0  # 验收硬指标：越权放行恒 0
        assert snap["denials"]["not_delegated"] == 1
        assert snap["denials"]["rate_limited"] == 1
        assert snap["cache_stale_deny"] == 1
        assert 0.0 <= snap["error_rate"] <= 1.0

    def test_query_count_tracks_no_n1(self):
        m = VisibilityMetrics()
        for n in (2, 2, 2):
            m.observe_query_count(n)
        assert m.max_query_count() == 2  # 常数查询数（无 per-wp N+1）


# ===========================================================================
# Property 18 · outbox → Redis fan-out 分发器与订阅器（即时淘汰快路径 + 优雅降级）
# ===========================================================================
import asyncio

from app.models.wp_visibility_models import WpVisibilityInvalidationOutbox
from app.services.wp_visibility.invalidation_dispatcher import (
    InvalidationDispatcher,
    handle_invalidation_message,
    run_invalidation_subscriber,
)


def _fake_redis():
    """decode_responses 的进程内 fakeredis（无真实 Redis 依赖）。"""
    import fakeredis.aioredis

    return fakeredis.aioredis.FakeRedis(decode_responses=True)


def test_handle_invalidation_message_parses_channel_and_invalidates():
    """纯解析：合法 channel → 淘汰对应项目缓存；非法前缀/UUID → 忽略。"""
    cache = PersistentEpochCache()
    pid = uuid4()
    # 预置一条新鲜度记录，验证被淘汰
    cache._epoch_freshness[pid] = type(  # noqa: SLF001 — 测试直接构造
        "F", (), {"epoch": 3, "checked_at": 0.0}
    )()
    assert handle_invalidation_message(cache, invalidation_channel(pid)) is True
    assert cache.cached_epoch_for(pid) is None  # 已淘汰
    # 非本前缀 / 非法 UUID → False，不抛
    assert handle_invalidation_message(cache, "other:channel:x") is False
    assert handle_invalidation_message(cache, invalidation_channel("not-a-uuid")) is False


@pytest.mark.asyncio
async def test_dispatcher_degrades_when_redis_unavailable(monkeypatch):
    """Redis 全挂（get_redis→None）→ publish_pending no-op 返回 0（降级，DB 安全网兜底）。"""
    import app.core.redis as core_redis

    async def _none():
        return None

    monkeypatch.setattr(core_redis, "get_redis", _none)
    disp = InvalidationDispatcher()

    class _NoDB:
        async def execute(self, *a, **k):  # 不应被调用（Redis 先降级）
            raise AssertionError("degradation 路径不应触达 DB 查询")

    assert await disp.publish_pending(_NoDB()) == 0


@pytest.mark.asyncio
async def test_subscriber_returns_immediately_when_redis_unavailable(monkeypatch):
    """订阅器：Redis 全挂（get_redis→None）→ 立即返回（降级），不阻塞、不抛。"""
    import app.core.redis as core_redis

    async def _none():
        return None

    monkeypatch.setattr(core_redis, "get_redis", _none)
    cache = PersistentEpochCache()
    # 有真实 Redis 时也不能阻塞：get_redis 被 patch 成 None → 立即返回（≤1s 内完成）。
    await asyncio.wait_for(run_invalidation_subscriber(cache, redis=None), timeout=5.0)


@pytest.mark.skipif(not IS_PG, reason="need PostgreSQL (invalidation outbox)")
@pytest.mark.asyncio
class TestInvalidationDispatcherThroughRedis:
    async def _seed_outbox(self, s, project_id, *, epoch, change_type="delegation"):
        row = WpVisibilityInvalidationOutbox(
            project_id=project_id, epoch=epoch, change_type=change_type
        )
        s.add(row)
        await s.flush()
        return row

    async def test_publish_pending_fans_out_and_invalidates_local(self, session):
        """outbox 行 → 按项目 publish 到 Redis channel + 同节点本地缓存即时淘汰。"""
        proj, user, wi, wp = await _lead_scenario(session, epoch=1)
        # 本地缓存预置一条新鲜度（模拟已缓存 grants）
        cache = PersistentEpochCache()
        cache._epoch_freshness[proj.id] = type(  # noqa: SLF001
            "F", (), {"epoch": 1, "checked_at": 0.0}
        )()
        # 撤权：epoch 递增 + 写 invalidation outbox（模拟 DelegationTransaction 提交后）
        await _set_epoch(session, proj.id, 2)
        await self._seed_outbox(session, proj.id, epoch=2)

        fake = _fake_redis()
        pubsub = fake.pubsub()
        await pubsub.subscribe(invalidation_channel(proj.id))
        # 丢弃订阅确认消息
        await pubsub.get_message(timeout=1.0)

        disp = InvalidationDispatcher(local_cache=cache)
        published = await disp.publish_pending(session, fake)
        assert published >= 1
        # 同节点本地缓存被即时淘汰（快路径）
        assert cache.cached_epoch_for(proj.id) is None

        # Redis channel 收到 epoch 消息
        msg = await pubsub.get_message(timeout=1.0)
        assert msg is not None and msg["type"] == "message"
        assert msg["data"] == "2"
        await pubsub.unsubscribe(invalidation_channel(proj.id))
        await pubsub.aclose()

    async def test_publish_pending_cursor_skips_already_published(self, session):
        """游标幂等：同一分发器二次 publish_pending 不重复发布旧行。"""
        proj, user, wi, wp = await _lead_scenario(session, epoch=1)
        await _set_epoch(session, proj.id, 2)
        await self._seed_outbox(session, proj.id, epoch=2)
        fake = _fake_redis()
        disp = InvalidationDispatcher()
        first = await disp.publish_pending(session, fake)
        assert first >= 1
        # 无新行 → 第二次不重复发布（游标已越过）
        second = await disp.publish_pending(session, fake)
        assert second == 0

    async def test_subscriber_invalidates_on_published_message(self, session):
        """端到端：订阅器收到 fan-out 消息 → 淘汰本地缓存（撤权即时收敛快路径）。"""
        proj, user, wi, wp = await _lead_scenario(session, epoch=1)
        cache = PersistentEpochCache()
        cache._epoch_freshness[proj.id] = type(  # noqa: SLF001
            "F", (), {"epoch": 1, "checked_at": 0.0}
        )()
        fake = _fake_redis()
        stop = asyncio.Event()
        task = asyncio.create_task(
            run_invalidation_subscriber(cache, redis=fake, stop_event=stop)
        )
        try:
            await asyncio.sleep(0.2)  # 等待 psubscribe 就绪
            await fake.publish(invalidation_channel(proj.id), "2")
            # 轮询等待淘汰生效（≤2s）
            for _ in range(40):
                if cache.cached_epoch_for(proj.id) is None:
                    break
                await asyncio.sleep(0.05)
            assert cache.cached_epoch_for(proj.id) is None
        finally:
            stop.set()
            try:
                await asyncio.wait_for(task, timeout=2.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                task.cancel()
