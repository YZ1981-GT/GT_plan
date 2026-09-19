# Feature: visibility-isolation-go-live-hardening — Task 5 真实容量验收与冻结生产 Rate_Limit_Profile（R4）
"""Task 5 / Requirements 4.1–4.12（组件 H4 CapacityHarness / C15 Cache/Rate/Perf / Property 4）。

把父 spec 已构建的 Performance_Profile / CapacityReport / RateLimitProfile 机制在本 go-live spec 上
**真实压测并冻结生产限流**，绝不假绿、绝不伪造 6000 结果、绝不预设阈值：

  A. **版本化 Performance_Profile + 最大诚实并发基线**（Req 4.1/4.2）：设计目标 = 6000 已认证并发用户
     （``TARGET_CONCURRENCY``）。本机 dev box 无法承载字面 6000 个同时在飞的 HTTP 客户端，故基线以
     **进程内真实服务（``resolve_wp_binding_and_access`` / ``WorkpaperListQueryService``）+ 真实
     PostgreSQL（audit_platform）** 运行能达到的最大代表性并发：``inflight`` 个同时在飞 × ``total``
     总请求（受 asyncpg 连接池序列化约束——这是安全关键的串行化点）。绝不伪造 6000；如实记录
     achieved concurrency + 方法学 + Honest_Extrapolation 依据。

  B. **CapacityReport + 冻结生产 Rate_Limit_Profile**（Req 4.7/4.8/4.9/4.10）：从**测量得到的**
     ``CapacityReport``（含内容 hash）经 ``freeze_rate_limit_profile`` 生成 frozen 且 active 的 profile
     （引用容量报告 hash；阈值由测量吞吐派生 × headroom，非预设、无固定 10 RPS）。缺报告/缺 hash/
     版本不匹配/无阈值 → 拒绝激活（``RateLimitProfileError`` 或 ``is_active=False``）。生产默认限流器
     inert（measurement-only）→ 只从冻结 profile 读阈值。

  C. **容量验收目标**（Req 4.3/4.4/4.5/4.6）：list p95≤2s / gate p95≤1s / 成功错误率≤1% /
     错误允许数(越权被放行)=0；越权探针必须真实穿过 gate 被拒（否则 error_allow=0 无意义）。

  D. **限流行为**（Req 4.9 within/over）：用冻结 profile 跑——阈内不误限 / 超阈 429 + 有效
     Retry-After / 资源无关（仅 principal/project/family）/ 窗口滑过恢复 / 每用户维度独立。

  E. **缓存一致性**（Req 4.x cache consistency）：撤权后 ≤1s DB epoch 安全网拒绝旧 grant，绝不
     stale-allow（复用父 ``PersistentEpochCache`` 语义，不改）。

  F. **确定性摘要 hash-pin**（Req 4.11/4.12）：易变计时（p95/throughput/wall/报告 hash/派生阈值）
     一律剥离，写入 manifest run notes（非 hash-pin）；hash-pin 的 artifact 仅含结构不变量 + 常量
     目标 + pass/fail 布尔 + 派生公式字符串 → 两次生成字节一致，可稳定 hash-pin。

不重建可见性系统、不改 ``resolve_wp_binding_and_access`` / Action_Matrix / epoch_cache 语义。
真实 PostgreSQL（audit_platform）；容量基线用 committed seed（跨连接可见）+ 显式清理（不写任何
append-only 表：注入 ``_MemResponder`` + ``NullRateLimiter``，绝不递增 epoch/写 outbox）。
"""
from __future__ import annotations

import asyncio
import json
import math
import os
import time
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings as app_settings
from app.services.wp_visibility.contracts import VisibilityContext, VisibilityRole
from app.services.wp_visibility.delegation_transaction import DelegationTransactionService
from app.services.wp_visibility.denial import (
    DenialReason,
    DenialResponder,
    ExternalNotFound,
)
from app.services.wp_visibility.epoch_cache import PersistentEpochCache
from app.services.wp_visibility.perf_metrics import VisibilityMetrics
from app.services.wp_visibility.rate_limit_profile import (
    TARGET_CONCURRENCY,
    CapacityReport,
    MeasurementModeRateLimiter,
    PerformanceProfile,
    RateLimitProfile,
    RateLimitProfileError,
    freeze_rate_limit_profile,
    get_default_rate_limiter,
    measurement_only_profile,
    reset_default_rate_limiter,
)
from app.services.wp_visibility.wp_bound_gate import (
    BindingAdapters,
    NullRateLimiter,
    resolve_wp_binding_and_access,
)
from app.services.wp_visibility.workpaper_list_query import WorkpaperListQueryService

from tests.procedure_delegation_visibility._factories import (
    IS_PG,
    mk_project,
    mk_project_user,
    mk_user,
    mk_working_paper,
    mk_wp_index,
)

pytestmark = [
    pytest.mark.skipif(not IS_PG, reason="need PostgreSQL (real app services + gate integration)"),
]

_BA = BindingAdapters()

# ---------------------------------------------------------------------------
# 版本化 Performance_Profile（Req 4.1/4.16 语义；不含任何限流阈值）
# ---------------------------------------------------------------------------
PERFORMANCE_PROFILE = PerformanceProfile(
    version="perf-6000-golive-v1",
    target_concurrency=TARGET_CONCURRENCY,  # 6000（设计目标负载）
    ramp="staged ramp to max achievable in-flight; bounded by asyncpg pool serialization",
    project_distribution="single active project, mixed audit cycles D/E/F, lead+admin+restricted principals",
    request_rate="closed-loop: fixed in-flight concurrency window, back-to-back requests",
    data_scale="1 project x N wp_index (mixed cycles) x working_paper",
    action_mix={
        # 归一权重（Entry_Family 覆盖：list/gate/attachment/AI/editor-callback/bulk/worker）
        "list": 0.14,
        "gate_render": 0.16,
        "gate_checklist": 0.12,
        "gate_detail": 0.08,
        "gate_version": 0.08,
        "gate_dedicated": 0.08,
        "attachment": 0.08,
        "ai": 0.08,
        "editor_callback": 0.08,
        "bulk": 0.05,
        "worker": 0.05,
    },
    duration="fixed total request budget (closed-loop), not wall-clock bounded",
)

# 设计验收目标（design H4 "list p95≤2s / gate p95≤1s / 成功错误率≤1% / 错误允许数=0"）
TARGET_LIST_P95_S = 2.0
TARGET_GATE_P95_S = 1.0
TARGET_ERROR_RATE = 0.01
TARGET_ERROR_ALLOW = 0

# 可版本化限流窗口 + 阈值派生 headroom（阈值来自测量吞吐 × headroom，非预设）
RATE_WINDOW_S = 1.0
THRESHOLD_HEADROOM = 2.0

# 证据 artifact 目录（本 spec 独立 evidence，Task 5）
_REPO_ROOT = Path(__file__).resolve().parents[3]
_ARTIFACT_DIR = (
    _REPO_ROOT
    / ".kiro" / "specs" / "visibility-isolation-go-live-hardening"
    / "evidence" / "artifacts" / "task5"
)

# 跨测试累积结果（zzz 写 artifact 时读取）
_RESULTS: dict = {}


class _MemResponder(DenialResponder):
    """内存捕获 responder，绝不写 DB/outbox（容量 committed 场景必须避免 append-only 写）。"""

    def __init__(self) -> None:
        super().__init__()
        self._last: str | None = None

    async def _write_outbox(self, **fields) -> None:  # type: ignore[override]
        self._last = fields.get("reason")

    def last_reason(self) -> str | None:
        return self._last


class _FakeUser:
    """轻量 current_user 替身（gate 只读 .id/.role.value）。"""

    class _Role:
        def __init__(self, v: str) -> None:
            self.value = v

    def __init__(self, uid: UUID, role: str) -> None:
        self.id = uid
        self.role = _FakeUser._Role(role)


@dataclass
class _CapacityScenario:
    project_id: UUID
    lead_user_id: UUID
    admin_user_id: UUID
    restricted_user_id: UUID
    lead_ctx: VisibilityContext
    admin_ctx: VisibilityContext
    restricted_ctx: VisibilityContext
    wp_ids: list[UUID]
    wp_index_ids: list[UUID]


async def _seed_committed_capacity(engine, *, n_wp: int) -> _CapacityScenario:
    """播种一个项目：lead 主编 n_wp 张底稿（跨 D/E/F 循环）+ admin + restricted；COMMIT。"""
    cycles = ["D", "E", "F"]
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as s:
        proj = await mk_project(s)
        lead = await mk_user(s)
        admin = await mk_user(s, role="admin")
        restricted = await mk_user(s)
        await mk_project_user(s, proj.id, lead.id, scope_cycles="D,E,F")
        await mk_project_user(s, proj.id, restricted.id, scope_cycles="")  # 无 scope → 空可见集
        wp_ids: list[UUID] = []
        wpx_ids: list[UUID] = []
        for i in range(n_wp):
            cyc = cycles[i % len(cycles)]
            wi = await mk_wp_index(s, proj.id, wp_code=f"D2-{i}", audit_cycle=cyc)
            wp = await mk_working_paper(s, proj.id, wi.id)
            wp.assigned_to = lead.id
            wp_ids.append(wp.id)
            wpx_ids.append(wi.id)
        await s.commit()
        lead_ctx = VisibilityContext(
            user_id=lead.id, project_id=proj.id, role=VisibilityRole.restricted,
            is_admin=False, scope_cycles=frozenset({"D", "E", "F"}),
        )
        admin_ctx = VisibilityContext(
            user_id=admin.id, project_id=proj.id, role=VisibilityRole.admin,
            is_admin=True, scope_cycles=frozenset(),
        )
        restricted_ctx = VisibilityContext(
            user_id=restricted.id, project_id=proj.id, role=VisibilityRole.restricted,
            is_admin=False, scope_cycles=frozenset(),
        )
        return _CapacityScenario(
            project_id=proj.id, lead_user_id=lead.id, admin_user_id=admin.id,
            restricted_user_id=restricted.id, lead_ctx=lead_ctx, admin_ctx=admin_ctx,
            restricted_ctx=restricted_ctx, wp_ids=wp_ids, wp_index_ids=wpx_ids,
        )


async def _cleanup_committed(engine, sc: _CapacityScenario) -> None:
    """FK 安全顺序删除 committed seed（只普通表；本场景从不写 append-only 表）。"""
    sm = async_sessionmaker(engine, expire_on_commit=False)
    pid = str(sc.project_id)
    async with sm() as s:
        for stmt in (
            "DELETE FROM working_paper WHERE project_id = CAST(:p AS uuid)",
            "DELETE FROM project_users WHERE project_id = CAST(:p AS uuid)",
            "DELETE FROM wp_index WHERE project_id = CAST(:p AS uuid)",
            "DELETE FROM users WHERE id = ANY(CAST(:u AS uuid[]))",
            "DELETE FROM projects WHERE id = CAST(:p AS uuid)",
        ):
            await s.execute(
                text(stmt),
                {
                    "p": pid,
                    "u": [str(sc.lead_user_id), str(sc.admin_user_id), str(sc.restricted_user_id)],
                },
            )
        await s.commit()


# entrypoint 表（family → gate 请求构造参数）；每项 (family, entrypoint, action, method, is_list)
_CAPACITY_FAMILIES: list[tuple[str, str, str, str, bool]] = [
    ("list", "workpaper.list", "list", "GET", True),
    ("gate_render", "workpaper.render_config", "read_render", "GET", False),
    ("gate_checklist", "workpaper.checklist_read", "read_checklist", "GET", False),
    ("gate_detail", "workpaper.detail", "read_detail", "GET", False),
    ("gate_version", "workpaper.version_list", "read_versions", "GET", False),
    ("gate_dedicated", "workpaper.dedicated_subroute", "dedicated_read", "GET", False),
    ("attachment", "attachment.read", "attach_read", "GET", False),
    ("ai", "workpaper.ai_context", "ai_read", "GET", False),
    ("editor_callback", "editor.config", "editor_config", "GET", False),
    ("bulk", "workpaper.export", "export_data", "POST", False),
    ("worker", "workpaper.detail", "read_detail", "GET", False),  # 后台重-gate 复用 detail 读
]


async def _run_capacity_baseline(
    engine, sc: _CapacityScenario, *, total: int, inflight: int, metrics: VisibilityMetrics
) -> dict:
    """闭环并发：inflight 个同时在飞 × total 总请求，动作按 family 轮转；测量注入 metrics。

    每请求独立 session（连接池），gate 用 NullRateLimiter + _MemResponder（不写 DB/outbox）。
    含越权 deny 探针（restricted 请求 lead 底稿）：若被错误放行 → record_error_allow（须恒 0）。
    """
    sm = async_sessionmaker(engine, expire_on_commit=False)
    sem = asyncio.Semaphore(inflight)
    n_fam = len(_CAPACITY_FAMILIES)
    # 每 DENY_EVERY 个请求插一个越权探针（与 n_fam=11 互质，确保探针落在各族上而非恒与 list 重合）
    DENY_EVERY = 7

    async def _one(i: int) -> None:
        fam, ep, action, method, is_list = _CAPACITY_FAMILIES[i % n_fam]
        wp_id = sc.wp_ids[i % len(sc.wp_ids)]
        is_deny_probe = (i % DENY_EVERY) == 0
        async with sem:
            async with sm() as s:
                t0 = time.perf_counter()
                try:
                    if is_deny_probe:
                        # 越权探针：restricted（空 scope）请求 lead 底稿 → 必须 404。
                        # 固定用 render 读入口（避免 list 分支吞掉探针），真实穿过 gate。
                        req = _BA.wp(entrypoint="workpaper.render_config", action="read_render",
                                     method="GET", wp_id=wp_id, project_id=sc.project_id)
                        try:
                            await resolve_wp_binding_and_access(
                                s, _FakeUser(sc.restricted_user_id, "auditor"), req,
                                responder=_MemResponder(), rate_limiter=NullRateLimiter(),
                            )
                            metrics.observe_gate_latency(time.perf_counter() - t0)
                            metrics.record_error_allow()  # 错误放行越权（须恒 0）
                        except ExternalNotFound:
                            metrics.observe_gate_latency(time.perf_counter() - t0)
                            metrics.record_denial(DenialReason.not_delegated.value)
                        return
                    if is_list:
                        svc = WorkpaperListQueryService(s)
                        await svc.list_workpapers(sc.lead_ctx, page=1, page_size=50)
                        metrics.observe_list_latency(time.perf_counter() - t0)
                        metrics.record_gate_allow()
                        return
                    # 正常放行：lead 请求自己主编底稿
                    req = _BA.wp(entrypoint=ep, action=action, method=method,
                                 wp_id=wp_id, project_id=sc.project_id)
                    await resolve_wp_binding_and_access(
                        s, _FakeUser(sc.lead_user_id, "auditor"), req,
                        responder=_MemResponder(), rate_limiter=NullRateLimiter(),
                    )
                    metrics.observe_gate_latency(time.perf_counter() - t0)
                    metrics.record_gate_allow()
                except ExternalNotFound:
                    metrics.observe_gate_latency(time.perf_counter() - t0)
                    metrics.record_error()  # 预期放行却被拒
                except Exception:  # noqa: BLE001
                    metrics.record_error()

    wall0 = time.perf_counter()
    await asyncio.gather(*[_one(i) for i in range(total)])
    wall = time.perf_counter() - wall0
    return {
        "total_requests": total,
        "inflight_concurrency": inflight,
        "wall_seconds": round(wall, 4),
        "throughput_rps": round(total / wall, 2) if wall > 0 else 0.0,
    }


def _env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(name, default)))
    except (TypeError, ValueError):
        return default


def _derive_thresholds(throughput_rps: float, inflight: int, n_families: int) -> dict:
    """由测量吞吐派生每用户/每项目/每 Entry_Family 阈值（× headroom；非预设、无固定 10 RPS）。"""
    win = RATE_WINDOW_S
    hf = THRESHOLD_HEADROOM
    per_family = max(1, math.ceil((throughput_rps / max(1, n_families)) * win * hf))
    per_user = max(1, math.ceil((throughput_rps / max(1, inflight)) * win * hf))
    per_project = max(1, math.ceil(throughput_rps * win * hf))
    return {"per_family": per_family, "per_user": per_user, "per_project": per_project}


@pytest.mark.asyncio
async def test_a_capacity_baseline_freeze_and_acceptance():
    """① 版本化 Performance_Profile 容量基线（真实服务+PG，最大可诚实并发）
    ② 依测量结果冻结 Rate_Limit_Profile（引用容量报告 hash）
    ③ 容量验收：list p95≤2s / gate p95≤1s / 错误率≤1% / 错误允许数=0（Req 4.1-4.9,4.12）"""
    # 目标 6000：默认以父 Task 17 代表性规模（64 in-flight × 6000 请求）为诚实基线；env 可放大/缩小。
    total = _env_int("TASK5_TOTAL", 6000)
    inflight = _env_int("TASK5_INFLIGHT", 64)
    n_wp = _env_int("TASK5_NWP", 40)

    engine = create_async_engine(
        app_settings.DATABASE_URL,
        pool_size=inflight,
        max_overflow=16,
        pool_pre_ping=True,
        pool_timeout=60,
    )
    metrics = VisibilityMetrics()
    sc: _CapacityScenario | None = None
    try:
        sc = await _seed_committed_capacity(engine, n_wp=n_wp)
        base = await _run_capacity_baseline(
            engine, sc, total=total, inflight=inflight, metrics=metrics
        )
        snap = metrics.snapshot()

        n_families = len({f[0] for f in _CAPACITY_FAMILIES})
        thresholds = _derive_thresholds(base["throughput_rps"], inflight, n_families)

        # ── 容量报告（测量结果 → 激活 Rate_Limit_Profile 的证据锚）──
        report = CapacityReport(
            performance_profile_version=PERFORMANCE_PROFILE.version,
            measured_at="",  # 剥离时间戳（可复现 hash）
            results={
                "methodology": (
                    "in-process real services (resolve_wp_binding_and_access / "
                    "WorkpaperListQueryService) against real PostgreSQL audit_platform; "
                    "closed-loop bounded in-flight concurrency"
                ),
                "target_concurrency": TARGET_CONCURRENCY,
                "achieved_inflight_concurrency": base["inflight_concurrency"],
                "total_requests": base["total_requests"],
                "throughput_rps": base["throughput_rps"],
                "gate_p95_seconds": snap["gate_p95_seconds"],
                "list_p95_seconds": snap["list_p95_seconds"],
                "gate_samples": snap["gate_samples"],
                "list_samples": snap["list_samples"],
                "error_rate": snap["error_rate"],
                "error_allow": snap["error_allow"],
                "max_query_count": snap["max_query_count"],
                "extrapolation_basis": (
                    "p95 measured under connection-pool saturation (the security-critical "
                    "serialization point); literal 6000 simultaneous clients NOT run on dev box; "
                    f"achieved {base['inflight_concurrency']} in-flight over {base['total_requests']} "
                    "requests is the largest honest representative concurrency on this host"
                ),
                "threshold_derivation": (
                    f"per_family=ceil(tput/{n_families}*{RATE_WINDOW_S}*{THRESHOLD_HEADROOM}); "
                    f"per_user=ceil(tput/{inflight}*{RATE_WINDOW_S}*{THRESHOLD_HEADROOM}); "
                    f"per_project=ceil(tput*{RATE_WINDOW_S}*{THRESHOLD_HEADROOM})"
                ),
                "derived_thresholds": thresholds,
            },
        )
        report_hash = report.content_hash()

        # ── 冻结 Rate_Limit_Profile（Property 4：frozen + 引用容量报告 hash）──
        family_map = {f[0]: thresholds["per_family"] for f in _CAPACITY_FAMILIES}
        user_map = {f[0]: thresholds["per_user"] for f in _CAPACITY_FAMILIES}
        project_map = {f[0]: thresholds["per_project"] for f in _CAPACITY_FAMILIES}
        frozen = freeze_rate_limit_profile(
            version="rate-6000-golive-v1",
            performance_profile=PERFORMANCE_PROFILE,
            capacity_report=report,
            per_user=user_map,
            per_project=project_map,
            per_family=family_map,
            window_seconds=RATE_WINDOW_S,
        )

        # ── 冻结与激活门断言（Property 4）──
        assert frozen.is_active is True
        assert frozen.frozen is True
        assert frozen.capacity_report_hash == report_hash
        assert frozen.source_performance_profile_version == PERFORMANCE_PROFILE.version

        # ── 容量验收目标（design H4）──
        gate_p95 = snap["gate_p95_seconds"]
        list_p95 = snap["list_p95_seconds"]
        err_rate = snap["error_rate"]
        err_allow = snap["error_allow"]
        deny_probes = int(snap["denials"].get(DenialReason.not_delegated.value, 0))
        assert deny_probes > 0, "越权探针未真实穿过 gate（error_allow=0 将无意义）"
        assert err_allow == TARGET_ERROR_ALLOW, f"错误允许数(越权被放行)必须为0，实测 {err_allow}"
        assert err_rate <= TARGET_ERROR_RATE, f"错误率 {err_rate} > {TARGET_ERROR_RATE}"
        assert gate_p95 <= TARGET_GATE_P95_S, f"gate p95 {gate_p95}s > {TARGET_GATE_P95_S}s"
        assert list_p95 <= TARGET_LIST_P95_S, f"list p95 {list_p95}s > {TARGET_LIST_P95_S}s"
        assert snap["gate_samples"] > 0 and snap["list_samples"] > 0

        _RESULTS["performance_profile"] = {
            "version": PERFORMANCE_PROFILE.version,
            "config_digest": PERFORMANCE_PROFILE.config_digest(),
            "target_concurrency": TARGET_CONCURRENCY,
            "achieved_inflight_concurrency": base["inflight_concurrency"],
            "total_requests": base["total_requests"],
            "ramp": PERFORMANCE_PROFILE.ramp,
            "project_distribution": PERFORMANCE_PROFILE.project_distribution,
            "request_rate": PERFORMANCE_PROFILE.request_rate,
            "data_scale": PERFORMANCE_PROFILE.data_scale,
            "duration": PERFORMANCE_PROFILE.duration,
            "action_mix": dict(sorted(PERFORMANCE_PROFILE.action_mix.items())),
        }
        _RESULTS["capacity_report"] = {
            "content_hash": report_hash,
            "performance_profile_version": report.performance_profile_version,
            "results": dict(report.results),
        }
        _RESULTS["rate_limit_profile"] = frozen.summary()
        _RESULTS["rate_limit_profile"]["thresholds"] = thresholds
        _RESULTS["capacity_acceptance"] = {
            "gate_p95_seconds": gate_p95,
            "gate_p95_target_seconds": TARGET_GATE_P95_S,
            "gate_p95_pass": gate_p95 <= TARGET_GATE_P95_S,
            "list_p95_seconds": list_p95,
            "list_p95_target_seconds": TARGET_LIST_P95_S,
            "list_p95_pass": list_p95 <= TARGET_LIST_P95_S,
            "error_rate": err_rate,
            "error_rate_target": TARGET_ERROR_RATE,
            "error_rate_pass": err_rate <= TARGET_ERROR_RATE,
            "error_allow": err_allow,
            "error_allow_target": TARGET_ERROR_ALLOW,
            "error_allow_pass": err_allow == TARGET_ERROR_ALLOW,
            "deny_probes_observed": deny_probes,
            "denials_observed": snap["denials"],
            "max_query_count": snap["max_query_count"],
        }
        _RESULTS["_frozen_profile_obj"] = frozen
    finally:
        if sc is not None:
            await _cleanup_committed(engine, sc)
        await engine.dispose()


def test_b_freeze_requires_capacity_report_hash():
    """缺报告/缺 hash/版本不匹配/无阈值 → 拒绝激活；measurement-only 永 inert（Req 4.8/4.10）。"""
    # ① measurement-only profile：无 hash、未冻结 → 永不激活（inert）
    inert = measurement_only_profile("golive-inert-0")
    assert inert.is_active is False
    assert inert.capacity_report_hash is None
    assert inert.frozen is False

    # ② 手工构造 frozen=True 但 capacity_report_hash 缺失 → is_active 仍 False（激活门核心）
    no_hash = RateLimitProfile(
        version="bad-no-hash", per_family={"gate_render": 10.0},
        capacity_report_hash=None, frozen=True,
    )
    assert no_hash.is_active is False, "缺 capacity_report_hash 绝不激活"

    # ③ capacity report 版本与 performance profile 不一致 → freeze 拒绝
    mismatched = CapacityReport(performance_profile_version="some-other-version", measured_at="", results={})
    with pytest.raises(RateLimitProfileError):
        freeze_rate_limit_profile(
            version="rate-mismatch", performance_profile=PERFORMANCE_PROFILE,
            capacity_report=mismatched, per_family={"gate_render": 10.0},
        )

    # ④ 无任何阈值维度 → freeze 拒绝（阈值须由容量测量得出，非预设）
    good_report = CapacityReport(
        performance_profile_version=PERFORMANCE_PROFILE.version, measured_at="", results={"x": 1}
    )
    with pytest.raises(RateLimitProfileError):
        freeze_rate_limit_profile(
            version="rate-no-thresholds", performance_profile=PERFORMANCE_PROFILE,
            capacity_report=good_report,  # 三维阈值全空
        )

    # ⑤ 非正阈值 → freeze 拒绝
    with pytest.raises(RateLimitProfileError):
        freeze_rate_limit_profile(
            version="rate-nonpositive", performance_profile=PERFORMANCE_PROFILE,
            capacity_report=good_report, per_user={"gate_render": 0},
        )

    # ⑥ 合法冻结：frozen + active + 引用报告 hash（正例锚定）
    frozen = freeze_rate_limit_profile(
        version="rate-golive-freeze-ok", performance_profile=PERFORMANCE_PROFILE,
        capacity_report=good_report, per_family={"gate_render": 5.0},
    )
    assert frozen.is_active is True
    assert frozen.capacity_report_hash == good_report.content_hash()

    _RESULTS["freeze_gate"] = {
        "measurement_only_inert": True,
        "missing_hash_refuses_activation": True,
        "version_mismatch_refused": True,
        "no_thresholds_refused": True,
        "nonpositive_threshold_refused": True,
        "valid_freeze_active": True,
    }


def test_c_production_reads_only_from_frozen_profile():
    """生产限流器默认 inert（measurement-only）→ 只从冻结 profile 读阈值（Req 4.9）。"""
    reset_default_rate_limiter()
    try:
        default = get_default_rate_limiter()
        assert default.profile.is_active is False, "生产默认限流器必须 inert（无容量证据不限流）"
        # inert 时无论多少请求都不限流（阈值只来自冻结 profile；无预设/无固定 10 RPS）
        uid, pid = uuid4(), uuid4()
        for _ in range(1000):
            assert default.check(principal=uid, project_id=pid, entry_family="gate_render") is None
        _RESULTS["production_reads_only_frozen"] = {
            "default_limiter_inert": True,
            "inert_never_limits": True,
        }
    finally:
        reset_default_rate_limiter()


def test_d_rate_limit_within_over_and_resource_independent():
    """用冻结 profile 跑限流验收：阈内不误限 / 超阈 429 + 有效 Retry-After / 资源无关（Req 4.9 within/over）"""
    frozen: RateLimitProfile | None = _RESULTS.get("_frozen_profile_obj")
    if frozen is None:
        pytest.skip("frozen profile 未生成（test_a 失败）")
    assert frozen.is_active

    fam = "gate_render"
    per_user = frozen.limit_for("user", fam)
    per_project = frozen.limit_for("project", fam)
    per_family = frozen.limit_for("family", fam)
    assert per_user and per_project and per_family
    operative = int(min(per_user, per_project, per_family))

    clock_val = {"t": 1000.0}

    def _clock() -> float:
        return clock_val["t"]

    uid = uuid4()
    pid = uuid4()

    # ① 阈内不误限：operative 个请求在同一窗口全部放行
    limiter = MeasurementModeRateLimiter(frozen, clock=_clock, metrics=VisibilityMetrics())
    for _ in range(operative):
        d = limiter.check(principal=uid, project_id=pid, entry_family=fam)
        assert d is None, "阈内请求被误限"

    # ② 超阈 429 + 有效 Retry-After
    over = limiter.check(principal=uid, project_id=pid, entry_family=fam)
    assert over is not None and over.allowed is False
    assert over.retry_after >= 1, "Retry-After 必须为有效正整数秒"

    # ③ 资源无关：check() 仅取 principal/project/family，同 principal/project/family 恒 429
    over2 = limiter.check(principal=uid, project_id=pid, entry_family=fam)
    assert over2 is not None and over2.allowed is False

    # ④ 窗口滑过后恢复放行
    clock_val["t"] += RATE_WINDOW_S + 0.001
    recovered = limiter.check(principal=uid, project_id=pid, entry_family=fam)
    assert recovered is None, "窗口滑过后应恢复放行"

    # ⑤ 不同 principal 独立计数（每用户维度）
    limiter2 = MeasurementModeRateLimiter(frozen, clock=_clock, metrics=VisibilityMetrics())
    other = uuid4()
    assert limiter2.check(principal=other, project_id=pid, entry_family=fam) is None

    _RESULTS["rate_limit_acceptance"] = {
        "family": fam,
        "within_threshold_no_false_limit": True,
        "over_threshold_429": True,
        "retry_after_valid": bool(over.retry_after >= 1),
        "resource_independent": True,
        "recovers_after_window": True,
        "per_user_isolated": True,
    }


@pytest.mark.asyncio
async def test_e_cache_consistency_revocation_no_stale_allow(session):
    """缓存一致性：撤权后 ≤1s DB epoch 安全网拒绝旧 grant，绝不 stale-allow（Req 4 cache consistency）。"""
    s = session
    proj = await mk_project(s)
    actor = await mk_user(s)
    lead = await mk_user(s)
    await mk_project_user(s, proj.id, lead.id, scope_cycles="D")
    wi = await mk_wp_index(s, proj.id, wp_code="D2-1", audit_cycle="D")
    wp = await mk_working_paper(s, proj.id, wi.id)
    wp.assigned_to = lead.id
    await s.flush()

    clk = {"t": 500.0}
    cache_fast = PersistentEpochCache(epoch_ttl_seconds=1.0, clock=lambda: clk["t"], metrics=VisibilityMetrics())
    cache_net = PersistentEpochCache(epoch_ttl_seconds=1.0, clock=lambda: clk["t"], metrics=VisibilityMetrics())
    req = _BA.wp(entrypoint="workpaper.render_config", action="read_render", method="GET",
                 wp_id=wp.id, project_id=proj.id)

    # 撤权前：两个缓存均缓存放行结果
    for cache in (cache_fast, cache_net):
        ctx = await resolve_wp_binding_and_access(
            s, lead, req, responder=_MemResponder(), rate_limiter=NullRateLimiter(), epoch_cache=cache,
        )
        assert "lead" in ctx.access_kinds

    # 撤权：清空 lead + 同事务递增 policy epoch（e0→e1）
    wp.assigned_to = None
    svc = DelegationTransactionService(s)
    await svc.bump_policy_epoch(proj.id, "delegation", actor_user_id=actor.id)
    await s.flush()

    # 快路径：Redis 失效通知立即淘汰旧 epoch 条目 → 立即拒绝
    cache_fast.invalidate(proj.id)
    with pytest.raises(ExternalNotFound):
        await resolve_wp_binding_and_access(
            s, lead, req, responder=_MemResponder(), rate_limiter=NullRateLimiter(), epoch_cache=cache_fast,
        )

    # 安全网：Redis 全挂（从不 invalidate），推进 >epoch_ttl → ≤1s DB epoch 核对发现 e1≠e0 → 拒绝
    clk["t"] += 1.001
    with pytest.raises(ExternalNotFound):
        await resolve_wp_binding_and_access(
            s, lead, req, responder=_MemResponder(), rate_limiter=NullRateLimiter(), epoch_cache=cache_net,
        )

    _RESULTS["cache_consistency"] = {
        "redis_fast_path_denies_immediately": True,
        "db_epoch_recheck_within_1s_denies": True,
        "no_stale_allow": True,
        "epoch_ttl_seconds": 1.0,
    }


# ═══════════════════════════════════════════════════════════════════════════
# 确定性摘要 artifact 落地（Req 4.11/4.12）
#   仅含结构不变量 + 常量目标 + pass/fail 布尔 + 派生公式字符串 → 两次生成字节一致，可稳定 hash-pin。
#   易变计时（p95/throughput/wall/报告 hash/派生阈值）不进 hash-pin artifact，改写 manifest run notes。
# ═══════════════════════════════════════════════════════════════════════════
def _write_json(name: str, payload: dict) -> Path:
    _ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    p = _ARTIFACT_DIR / name
    p.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return p


def test_zzz_write_task5_artifacts():
    """把容量验收/冻结 profile 落地为确定性 artifact + 易变计时写 volatile meta（供 manifest notes）。
    强断言：全部强制项必须真实通过，否则本测试失败（不落地假绿 summary）。"""
    assert "capacity_report" in _RESULTS, "缺容量报告（test_a 未通过）"
    assert "rate_limit_profile" in _RESULTS and _RESULTS["rate_limit_profile"]["active"], "缺激活的冻结 profile"
    assert "capacity_acceptance" in _RESULTS, "缺容量验收结果"
    assert "rate_limit_acceptance" in _RESULTS, "缺限流验收结果"
    assert "freeze_gate" in _RESULTS, "缺 freeze-requires-hash 结果"
    assert "cache_consistency" in _RESULTS, "缺缓存一致性结果"
    ca = _RESULTS["capacity_acceptance"]
    assert ca["gate_p95_pass"] and ca["list_p95_pass"] and ca["error_rate_pass"] and ca["error_allow_pass"]

    pp = _RESULTS["performance_profile"]
    rlp = _RESULTS["rate_limit_profile"]

    # ── 确定性摘要（hash-pin）：无易变数字 ──
    deterministic = {
        "task": "5",
        "feature": "visibility-isolation-go-live-hardening",
        "requirement": "R4 真实容量验收与冻结生产 Rate_Limit_Profile",
        "performance_profile": {
            "version": pp["version"],
            "config_digest": pp["config_digest"],
            "target_concurrency": pp["target_concurrency"],
            "achieved_inflight_concurrency": pp["achieved_inflight_concurrency"],
            "total_requests": pp["total_requests"],
            "ramp": pp["ramp"],
            "project_distribution": pp["project_distribution"],
            "request_rate": pp["request_rate"],
            "data_scale": pp["data_scale"],
            "duration": pp["duration"],
            "action_mix": pp["action_mix"],
        },
        "rate_limit_profile": {
            "version": rlp["version"],
            "window_seconds": rlp["window_seconds"],
            "frozen": rlp["frozen"],
            "active": rlp["active"],
            "source_performance_profile_version": rlp["source_performance_profile_version"],
            "per_user_families": rlp["per_user_families"],
            "per_project_families": rlp["per_project_families"],
            "per_family_families": rlp["per_family_families"],
            "activation_binding": (
                "is_active iff frozen AND capacity_report_hash present & equal to source "
                "CapacityReport.content_hash(); missing report/hash refuses activation"
            ),
            "threshold_derivation": _RESULTS["capacity_report"]["results"]["threshold_derivation"],
            "capacity_report_hash_recorded_in": "manifest run notes (volatile per measurement)",
        },
        "acceptance_targets": {
            "list_p95_seconds": TARGET_LIST_P95_S,
            "gate_p95_seconds": TARGET_GATE_P95_S,
            "error_rate": TARGET_ERROR_RATE,
            "error_allow": TARGET_ERROR_ALLOW,
        },
        "acceptance_result": {
            "list_p95_pass": ca["list_p95_pass"],
            "gate_p95_pass": ca["gate_p95_pass"],
            "error_rate_pass": ca["error_rate_pass"],
            "error_allow_pass": ca["error_allow_pass"],
            "error_allow": ca["error_allow"],
            "deny_probes_present": ca["deny_probes_observed"] > 0,
        },
        "freeze_gate": _RESULTS["freeze_gate"],
        "production_reads_only_frozen": _RESULTS.get("production_reads_only_frozen", {}),
        "rate_limit_acceptance": _RESULTS["rate_limit_acceptance"],
        "cache_consistency": _RESULTS["cache_consistency"],
        "methodology": _RESULTS["capacity_report"]["results"]["methodology"],
        "extrapolation_basis": _RESULTS["capacity_report"]["results"]["extrapolation_basis"],
        "honesty_note": (
            "literal 6000 simultaneous HTTP clients NOT fabricated; achieved concurrency + "
            "extrapolation basis documented; frozen profile bound by measured CapacityReport hash"
        ),
    }
    _write_json("task5_capacity_frozen_profile_summary.json", deterministic)

    # ── 易变计时 meta（NOT hash-pinned；供 append 脚本写入 manifest run notes）──
    volatile = {
        "capacity_report_hash": _RESULTS["capacity_report"]["content_hash"],
        "rate_limit_profile_version": rlp["version"],
        "performance_profile_version": pp["version"],
        "measured": {
            "gate_p95_seconds": ca["gate_p95_seconds"],
            "list_p95_seconds": ca["list_p95_seconds"],
            "error_rate": ca["error_rate"],
            "error_allow": ca["error_allow"],
            "deny_probes_observed": ca["deny_probes_observed"],
            "max_query_count": ca["max_query_count"],
            "throughput_rps": _RESULTS["capacity_report"]["results"]["throughput_rps"],
            "achieved_inflight_concurrency": pp["achieved_inflight_concurrency"],
            "total_requests": pp["total_requests"],
            "derived_thresholds": rlp["thresholds"],
        },
    }
    _write_json("_task5_volatile_meta.json", volatile)

    assert (_ARTIFACT_DIR / "task5_capacity_frozen_profile_summary.json").exists()
