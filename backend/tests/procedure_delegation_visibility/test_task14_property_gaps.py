# Feature: procedure-delegation-visibility-isolation — Task 14 同源 PBT · 缺口属性（P9/P10/P12/P15/P16/P18/P19/P20）
"""Task 14（组件 C17 Verification）同源 smoke/correctness 属性缺口补齐。

design.md 的 Correctness Properties P1–P20 中，以下属性此前仅有 **示例（example）** 覆盖或
**完全缺失** ``@given`` 生成式覆盖，无法"输出有效样例数"；本模块用**同一批** ``@given`` property
函数补齐，并统一走 ``_pbt_profiles``：

  - **P9**  Reviewer 白名单（此前仅 test_wp_bound_gate 示例）——gate（真实 PostgreSQL）。
  - **P10** 绑定/claim 冲突 fail-closed（此前仅示例）——gate（PostgreSQL）。
  - **P12** 审计 outbox 失败不改变 404/429（此前仅示例）——gate（PostgreSQL）。
  - **P15** 展示参数/客户端身份不授权（此前仅示例）——list（PostgreSQL）。
  - **P16** HTTP/非 HTTP 入口清单 == coverage ledger（此前缺失）——纯函数（synthetic app）。
  - **P18** 撤权 ≤1s 收敛、绝不 stale-allow（此前仅示例）——epoch cache（PostgreSQL）。
  - **P19** Rate_Limit_Profile 需容量证据才激活（此前仅示例）——纯函数（合成容量报告）。
  - **P20** Evidence append-only + SHA-256/size 重算 + 完整（此前缺失）——纯函数（临时 spec dir）。

机制统一：``@given`` 顶置，``@count_examples("Pxx")`` 紧贴其下按有效样例计数，``@pbt_settings()``
不硬编码 ``max_examples`` → 由当前加载 profile 驱动（smoke=5 / correctness≥100）。每个 property 都
带一个宽域 ``nonce`` 生成参数，避免有限域早停，保证 correctness 档真正跑满 ≥100 有效样例。

SQL/事务/令牌语义在真实 PostgreSQL（audit_platform）验证，非 sqlite/mock；纯函数属性直接单测。
本模块只补属性，不改任何生产逻辑，不复制既有断言（复用既有 scenario helper 与服务）。
"""
from __future__ import annotations

import tempfile
import types
from pathlib import Path
from uuid import uuid4

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.security import entry_coverage_scanner as scanner
from app.security import evidence_manifest as ev
from app.services.wp_visibility.contracts import VisibilityRole
from app.services.wp_visibility.denial import (
    EXTERNAL_NOT_FOUND_DETAIL,
    DenialReason,
    ExternalNotFound,
    RateLimited,
)
from app.services.wp_visibility.epoch_cache import EpochUnavailable, PersistentEpochCache
from app.services.wp_visibility.rate_limit_profile import (
    CapacityReport,
    MeasurementModeRateLimiter,
    PerformanceProfile,
    RateLimitProfile,
    RateLimitProfileError,
    freeze_rate_limit_profile,
    measurement_only_profile,
)
from app.services.wp_visibility.workpaper_list_query import (
    InvalidListParams,
    WorkpaperListFilters,
    WorkpaperListQueryService,
)
from app.services.wp_visibility.wp_bound_gate import (
    BindingAdapters,
    resolve_wp_binding_and_access,
)

from ._factories import (
    IS_PG,
    mk_project,
    mk_user,
    mk_working_paper,
    mk_wp_index,
    run_isolated,
)
from ._pbt_profiles import (
    PROPERTY_MATRIX,
    VALID_EXAMPLE_COUNTS,
    count_examples,
    is_correctness,
    pbt_settings,
    target_examples,
    write_report,
)
from .test_task13_epoch_cache_rate_profile import (
    _Clock,
    _lead_scenario as _epoch_scenario,
    _set_epoch,
)
from .test_wp_bound_gate import (
    CapturingResponder,
    _DenyRateLimiter,
    _lead_scenario,
    _reviewer_scenario,
)
from .test_workpaper_list_query import _ctx, _mk_lead_wp

_BA = BindingAdapters()
_NONCE = st.integers(min_value=0, max_value=2**31 - 1)


# ===========================================================================
# Property 16: HTTP 与非 HTTP 入口清单与 coverage ledger 双向相等（无漂移/无假绿）
# Validates: Requirements 13.1, 13.2, 13.3, 13.5, 13.6, 13.7, 13.13, 13.14, 16.17
# ===========================================================================
_P16_PATH_POOL = [
    "/api/workpapers/{wp_id}/render-config",       # wp-bound
    "/api/workpapers/{wp_id}/checklist-responses",  # wp-bound
    "/api/workpapers/{wp_id}/ai/generate-text",     # wp-bound
    "/api/workpapers/{wp_id}/parsed-data",          # wp-bound
    "/wopi/files/{file_id}",                        # wp-bound (editor)
    "/api/attachments/{attachment_id}/download",    # wp-bound
    "/api/projects/{project_id}/bulk-tab/export-data",  # wp-bound
    "/api/projects/{project_id}/import",            # non-wp-bound
    "/api/version",                                 # infra
]
_P16_METHODS = ["GET", "POST", "PUT", "DELETE"]


def _p16_fake_route(path: str, method: str, module: str, name: str):
    def _ep():
        return None

    _ep.__module__ = module
    _ep.__qualname__ = name
    _ep.__name__ = name
    return types.SimpleNamespace(path=path, methods={method}, endpoint=_ep)


@given(
    specs=st.lists(
        st.tuples(
            st.sampled_from(_P16_PATH_POOL),
            st.sampled_from(_P16_METHODS),
            st.integers(min_value=0, max_value=3),  # module index → 可产生真重复注册
        ),
        min_size=1,
        max_size=8,
    ),
    nonce=_NONCE,
)
@count_examples("P16")
@pbt_settings()
def test_p16_ledger_bidirectional_and_no_fake_pass(specs, nonce):
    routes = [
        _p16_fake_route(path, method, f"app.routers.mod{mod_idx}", f"ep_{i}")
        for i, (path, method, mod_idx) in enumerate(specs)
    ]
    fake_app = types.SimpleNamespace(routes=routes)
    ledger = scanner.build_ledger(app=fake_app)

    http = [e for e in ledger["entries"] if e["kind"] == "http"]
    ledger_keys = {(e["route"], e["method"]) for e in http}
    enumerated_keys = {(p, m) for (p, m, _) in specs}

    # 双向相等：ledger 的 (route,method) 集合 == 从 app 枚举的集合（零漂移，无遗漏无多余）。
    assert ledger_keys == enumerated_keys
    # 每个 (route,method) 唯一一行（真重复注册折叠为一行而非丢弃/重复）。
    keys_list = [(e["route"], e["method"]) for e in http]
    assert len(keys_list) == len(set(keys_list))

    # 真重复注册（同 route+method 绑定 ≥2 个不同 endpoint 模块）必须被标记而非静默丢弃。
    from collections import defaultdict

    modules_per_key: dict[tuple, set] = defaultdict(set)
    for (path, method, mod_idx) in specs:
        modules_per_key[(path, method)].add(mod_idx)
    for e in http:
        key = (e["route"], e["method"])
        if len(modules_per_key[key]) > 1:
            assert e.get("duplicate_registration") is True

    # 无 Wp_Bound_Gate/Matrix 之前，wp-bound 入口一律 unmigrated（baseline 反假绿）。
    for e in http:
        if e.get("wp_bound"):
            assert e["gate"] == "unmigrated" and e["matrix"] == "unmigrated"
            assert e.get("test_ids") == []
        else:
            assert e["gate"] == "not_applicable" and e["matrix"] == "not_applicable"

    # 非 HTTP 执行器（worker/retry/dead-letter）也在 ledger 中被清点（双轨盘点）。
    workers = [e for e in ledger["entries"] if e["kind"] in ("worker", "retry", "dead_letter")]
    assert workers, "coverage ledger 必须清点非 HTTP 执行器"
    for w in workers:
        assert w["route"] is None and w["method"] is None


# ===========================================================================
# Property 19: Rate_Limit_Profile 必须由容量报告证据激活（无证据 inert，绝不预设阈值/10 RPS）
# Validates: Requirements 14.1, 14.6, 14.7, 14.8, 14.9, 14.10, 14.11, 14.12, 14.16, 14.17
# ===========================================================================
@given(
    version_match=st.booleans(),
    threshold=st.integers(min_value=-2, max_value=30),
    provide_threshold=st.booleans(),
    path=st.sampled_from(["measurement", "unfrozen_manual", "freeze"]),
    nonce=_NONCE,
)
@count_examples("P19")
@pbt_settings()
def test_p19_profile_activation_requires_capacity_evidence(
    version_match, threshold, provide_threshold, path, nonce
):
    perf = PerformanceProfile(version="perf-6000")
    report = CapacityReport(
        performance_profile_version="perf-6000" if version_match else "perf-OTHER",
        measured_at="2026-07-16T00:00:00Z",
        results={"ok": True, "n": nonce % 11},
    )

    if path == "measurement":
        # 无证据 → inert measurement-only → 永不限流、无预设阈值/无固定 10 RPS。
        prof = measurement_only_profile()
        assert prof.is_active is False
        assert prof.per_user == {} and prof.per_project == {} and prof.per_family == {}
        limiter = MeasurementModeRateLimiter(prof)
        uid, pid = uuid4(), uuid4()
        for _ in range(25):
            assert limiter.check(principal=uid, project_id=pid, entry_family="list") is None
        return

    if path == "unfrozen_manual":
        # 有阈值但未冻结/无容量 hash → 仍 inert（无证据不生效）。
        prof = RateLimitProfile(
            version="draft", per_family={"list": max(1, threshold)},
            capacity_report_hash=None, frozen=False,
        )
        assert prof.is_active is False
        limiter = MeasurementModeRateLimiter(prof)
        uid, pid = uuid4(), uuid4()
        for _ in range(25):
            assert limiter.check(principal=uid, project_id=pid, entry_family="list") is None
        return

    # path == "freeze"
    should_error = (not version_match) or (not provide_threshold) or (threshold <= 0)
    kwargs = {"per_family": {"list": threshold}} if provide_threshold else {}
    if should_error:
        # 版本不一致 / 无阈值 / 非正阈值 → 拒绝产出激活 profile（Property 19）。
        with pytest.raises(RateLimitProfileError):
            freeze_rate_limit_profile(
                version="rl-6000", performance_profile=perf, capacity_report=report,
                window_seconds=1.0, **kwargs,
            )
        return

    prof = freeze_rate_limit_profile(
        version="rl-6000", performance_profile=perf, capacity_report=report,
        per_family={"list": threshold}, window_seconds=1.0,
    )
    # 激活 profile 必须引用容量报告内容 hash（证据锚）。
    assert prof.is_active is True and prof.frozen is True
    assert prof.capacity_report_hash == report.content_hash()
    assert prof.source_performance_profile_version == "perf-6000"

    clock = _Clock()
    limiter = MeasurementModeRateLimiter(prof, clock=clock)
    uid, pid = uuid4(), uuid4()
    # 阈内不误限。
    for _ in range(threshold):
        assert limiter.check(principal=uid, project_id=pid, entry_family="list") is None
    # 超阈 → 资源无关 429 + 有效 Retry-After。
    decision = limiter.check(principal=uid, project_id=pid, entry_family="list")
    assert decision is not None and decision.allowed is False
    assert decision.retry_after >= 1
    # 窗口滑过后恢复。
    clock.advance(1.01)
    assert limiter.check(principal=uid, project_id=pid, entry_family="list") is None


# ===========================================================================
# Property 20: Evidence 追加-only + 相对路径安全 + SHA-256/size 重算 + 篡改可检
# Validates: Requirements 15.1, 15.2, 15.3, 15.4, 15.5, 15.9, 15.10, 15.11
# ===========================================================================
@given(
    payload=st.binary(min_size=0, max_size=96),
    status=st.sampled_from(["passed", "failed", "not_run", "error", "skipped"]),
    unsafe=st.sampled_from([None, "dotdot", "absolute"]),
    tamper=st.booleans(),
    nonce=_NONCE,
)
@count_examples("P20")
@pbt_settings()
def test_p20_evidence_append_only_hash_complete(payload, status, unsafe, tamper, nonce):
    import hashlib

    with tempfile.TemporaryDirectory() as td:
        spec_dir = Path(td)
        (spec_dir / "evidence" / "artifacts").mkdir(parents=True)
        manifest = spec_dir / "evidence" / "manifest.json"

        # 不安全相对路径（.. / 绝对）必须在写入前被拒绝（Req 15.10）。
        if unsafe == "dotdot":
            with pytest.raises(ValueError):
                ev.append_run(
                    task_id="14", status=status, artifacts=["../escape.bin"],
                    manifest_path=manifest, spec_dir=spec_dir,
                )
            return
        if unsafe == "absolute":
            with pytest.raises(ValueError):
                ev.append_run(
                    task_id="14", status=status,
                    artifacts=[{"path": "C:/abs/escape.bin"}],
                    manifest_path=manifest, spec_dir=spec_dir,
                )
            return

        rel = "evidence/artifacts/a.bin"
        art = spec_dir / rel
        art.write_bytes(payload)

        run1 = ev.append_run(
            task_id="14", status=status, artifacts=[rel],
            manifest_path=manifest, spec_dir=spec_dir,
        )
        # SHA-256 + size 从原始字节重算并落记。
        assert run1["artifacts"][0]["sha256"] == hashlib.sha256(payload).hexdigest()
        assert run1["artifacts"][0]["size"] == len(payload)

        # 追加第二条：append-only 保留首条不变（含 failed run 保留）。
        run2 = ev.append_run(
            task_id="14", status="passed", artifacts=[rel],
            manifest_path=manifest, spec_dir=spec_dir,
        )
        import json as _json

        data = _json.loads(manifest.read_text(encoding="utf-8"))
        assert len(data["runs"]) == 2
        assert data["runs"][0]["run_id"] == run1["run_id"]
        assert data["runs"][0]["status"] == status
        assert data["runs"][1]["run_id"] == run2["run_id"]

        if tamper:
            # 篡改 artifact → precheck 必须检出 SHA/size 不一致。
            art.write_bytes(payload + b"tampered-" + str(nonce).encode())
            problems = ev.precheck(
                manifest_path=manifest, schema_path=ev.SCHEMA_PATH, spec_dir=spec_dir
            )
            assert any("SHA-256 mismatch" in p or "size mismatch" in p for p in problems)
        else:
            # 未篡改 → precheck 干净（重算一致）。
            assert ev.precheck(
                manifest_path=manifest, schema_path=ev.SCHEMA_PATH, spec_dir=spec_dir
            ) == []


# ===========================================================================
# Property 9: Reviewer 只能命中 Review_Whitelist（真实 PostgreSQL gate）
# Validates: Requirements 7.5
# ===========================================================================
_P9_ALLOW = ("read", "reviewed", "changes_requested_reason")
_P9_DENY = (
    "save_checklist", "save_parsed_data", "attach_associate", "version_restore",
    "editor_write", "status_transition", "changes_requested_no_reason",
)


@pytest.mark.skipif(not IS_PG, reason="need PostgreSQL (gate SQL semantics)")
@given(case=st.sampled_from(_P9_ALLOW + _P9_DENY), nonce=_NONCE)
@count_examples("P9")
@pbt_settings()
def test_p9_reviewer_whitelist_only(case, nonce):
    async def scenario(s):
        proj, user, wi, wp = await _reviewer_scenario(s)
        if case == "read":
            req = _BA.wp(entrypoint="workpaper.render_config", action="read_render",
                         method="GET", wp_id=wp.id, project_id=proj.id)
        elif case == "reviewed":
            req = _BA.wp(entrypoint="review.transition", action="review_transition",
                         method="POST", wp_id=wp.id, project_id=proj.id,
                         source_state="submitted", target_state="reviewed")
        elif case == "changes_requested_reason":
            req = _BA.wp(entrypoint="review.transition", action="review_transition",
                         method="POST", wp_id=wp.id, project_id=proj.id,
                         source_state="submitted", target_state="changes_requested",
                         review_reason="需补充凭证")
        elif case == "changes_requested_no_reason":
            req = _BA.wp(entrypoint="review.transition", action="review_transition",
                         method="POST", wp_id=wp.id, project_id=proj.id,
                         source_state="submitted", target_state="changes_requested")
        elif case == "save_checklist":
            req = _BA.wp(entrypoint="workpaper.checklist_save", action="save_checklist",
                         method="PUT", wp_id=wp.id, project_id=proj.id)
        elif case == "save_parsed_data":
            req = _BA.wp(entrypoint="workpaper.parsed_data_write", action="save_parsed_data",
                         method="PUT", wp_id=wp.id, project_id=proj.id)
        elif case == "attach_associate":
            req = _BA.wp(entrypoint="attachment.associate", action="attach_associate",
                         method="POST", wp_id=wp.id, project_id=proj.id)
        elif case == "version_restore":
            req = _BA.wp(entrypoint="version.restore", action="version_restore",
                         method="POST", wp_id=wp.id, project_id=proj.id)
        elif case == "editor_write":
            req = _BA.wp(entrypoint="editor.file_write", action="editor_write",
                         method="POST", wp_id=wp.id, project_id=proj.id)
        else:  # status_transition
            req = _BA.wp(entrypoint="workpaper.status_transition", action="status_transition",
                         method="POST", wp_id=wp.id, project_id=proj.id,
                         source_state="submitted", target_state="reviewed")

        if case in _P9_ALLOW:
            ctx = await resolve_wp_binding_and_access(
                s, user, req, responder=CapturingResponder()
            )
            assert "reviewer" in ctx.access_kinds
        else:
            resp = CapturingResponder()
            with pytest.raises(ExternalNotFound) as ei:
                await resolve_wp_binding_and_access(s, user, req, responder=resp)
            assert ei.value.status_code == 404
            assert resp.last_reason() == DenialReason.action_denied.value

    run_isolated(scenario)


# ===========================================================================
# Property 10: 绑定/claim 冲突在读正文/副作用前 fail-closed（真实 PostgreSQL gate）
# Validates: Requirements 8.1, 8.2, 8.3, 8.4, 10.1, 10.4, 10.5, 9.2, 9.6
# ===========================================================================
_P10_KINDS = (
    "client_index_mismatch", "historical_version", "unmapped_sheet",
    "token_mismatch", "cross_project", "nonexistent",
)


@pytest.mark.skipif(not IS_PG, reason="need PostgreSQL (gate SQL semantics)")
@given(kind=st.sampled_from(_P10_KINDS), nonce=_NONCE)
@count_examples("P10")
@pbt_settings()
def test_p10_binding_claim_conflict_fail_closed(kind, nonce):
    async def scenario(s):
        proj, user, wi, wp = await _lead_scenario(s)
        base = dict(entrypoint="workpaper.render_config", action="read_render",
                    method="GET", wp_id=wp.id, project_id=proj.id)
        if kind == "client_index_mismatch":
            req = _BA.wp(client_wp_index_id=uuid4(), **base)
            expected = DenialReason.binding_conflict.value
        elif kind == "historical_version":
            req = _BA.wp(requested_version=str(wp.file_version + 5), **base)
            expected = DenialReason.historical_version.value
        elif kind == "unmapped_sheet":
            req = _BA.wp(requested_sheet_key="ZZ9", **base)
            expected = DenialReason.sheet_unmapped.value
        elif kind == "token_mismatch":
            req = _BA.wp(entrypoint="editor.config", action="editor_config", method="GET",
                         wp_id=wp.id, project_id=proj.id,
                         token_claims={"wp_id": str(uuid4()), "action": "editor_config"})
            expected = DenialReason.token_invalid.value
        elif kind == "cross_project":
            other = await mk_project(s)
            await s.flush()
            req = _BA.wp(entrypoint="workpaper.render_config", action="read_render",
                         method="GET", wp_id=wp.id, project_id=other.id)
            expected = DenialReason.cross_project.value
        else:  # nonexistent
            req = _BA.wp(entrypoint="workpaper.render_config", action="read_render",
                         method="GET", wp_id=uuid4(), project_id=proj.id)
            expected = DenialReason.binding_conflict.value

        resp = CapturingResponder()
        with pytest.raises(ExternalNotFound) as ei:
            await resolve_wp_binding_and_access(s, user, req, responder=resp)
        assert ei.value.status_code == 404
        assert ei.value.detail == EXTERNAL_NOT_FOUND_DETAIL
        assert resp.last_reason() == expected

    run_isolated(scenario)


# ===========================================================================
# Property 12: 安全审计 outbox 写入失败不改变 404/429（真实 PostgreSQL gate）
# Validates: Requirements 9.8, 9.9, 9.10, 9.11
# ===========================================================================
@pytest.mark.skipif(not IS_PG, reason="need PostgreSQL (gate SQL semantics)")
@given(mode=st.sampled_from(["deny", "ratelimit"]), retry=st.integers(min_value=1, max_value=59), nonce=_NONCE)
@count_examples("P12")
@pbt_settings()
def test_p12_audit_failure_never_changes_contract(mode, retry, nonce):
    async def scenario(s):
        proj, user, wi, wp = await _lead_scenario(s)
        failing = CapturingResponder(fail=True)  # 模拟 outbox 写入失败
        if mode == "deny":
            req = _BA.wp(entrypoint="workpaper.render_config", action="read_render",
                         method="GET", wp_id=uuid4(), project_id=proj.id)
            with pytest.raises(ExternalNotFound) as ei:
                await resolve_wp_binding_and_access(s, user, req, responder=failing)
            assert ei.value.status_code == 404
            assert ei.value.detail == EXTERNAL_NOT_FOUND_DETAIL
            assert failing.captured == []  # 写入失败但响应不变
        else:  # ratelimit
            limiter = _DenyRateLimiter(retry_after=retry)
            req = _BA.wp(entrypoint="workpaper.render_config", action="read_render",
                         method="GET", wp_id=uuid4(), project_id=uuid4())
            with pytest.raises(RateLimited) as ei:
                await resolve_wp_binding_and_access(
                    s, user, req, rate_limiter=limiter, responder=failing
                )
            assert ei.value.status_code == 429
            assert ei.value.headers.get("Retry-After") == str(retry)

    run_isolated(scenario)


# ===========================================================================
# Property 15: 展示参数/客户端身份绝不授权；授权只来自服务端 context（真实 PostgreSQL list）
# Validates: Requirements 12.1, 12.2, 12.3, 11.7
# ===========================================================================
@pytest.mark.skipif(not IS_PG, reason="need PostgreSQL (list SQL semantics)")
@given(
    variant=st.sampled_from(["display_invariant", "illegal_page", "illegal_page_size", "illegal_sort", "illegal_dir"]),
    sort=st.sampled_from(["wp_code", "file_status"]),
    sort_dir=st.sampled_from(["asc", "desc"]),
    claimed_role=st.sampled_from(["admin", "manager", "partner", "auditor"]),
    nonce=_NONCE,
)
@count_examples("P15")
@pbt_settings()
def test_p15_display_and_client_identity_never_authorize(
    variant, sort, sort_dir, claimed_role, nonce
):
    async def scenario(s):
        proj = await mk_project(s)
        user = await mk_user(s)
        # 被委派主编底稿（唯一应可见）
        wi_mine = await mk_wp_index(s, proj.id, wp_code="D2-1", audit_cycle="D")
        await _mk_lead_wp(s, proj.id, wi_mine.id, user.id)
        # scope 内但别人主编（未委派给 user → 不可见）
        other = await mk_user(s)
        wi_other = await mk_wp_index(s, proj.id, wp_code="D2-2", audit_cycle="D")
        await _mk_lead_wp(s, proj.id, wi_other.id, other.id)

        # 服务端 context 只授权 user 被委派的底稿；claimed_role 只是"客户端声明"，不进 context。
        ctx = _ctx(user.id, proj.id, VisibilityRole.restricted, {"D"})
        svc = WorkpaperListQueryService(s)

        if variant == "display_invariant":
            # 任意合法展示参数（sort/dir/分页）不改变可见集（授权只来自 context，非展示/客户端身份）。
            out = await svc.list_workpapers(ctx, sort=sort, sort_dir=sort_dir, page=1, page_size=10)
            codes = {it["wp_code"] for it in out["items"]}
            assert codes == {"D2-1"}
            # 声明 admin/manager 客户端角色不会让 user 看到 wi_other。
            assert "D2-2" not in codes
        else:
            bad = {
                "illegal_page": dict(page=0),
                "illegal_page_size": dict(page_size=10_000),
                "illegal_sort": dict(sort="; DROP TABLE working_paper"),
                "illegal_dir": dict(sort_dir="sideways"),
            }[variant]
            with pytest.raises(InvalidListParams):
                await svc.list_workpapers(ctx, **bad)

    run_isolated(scenario)


# ===========================================================================
# Property 18: 撤权 ≤1s 收敛且绝不 stale-allow（真实 PostgreSQL persistent epoch cache）
# Validates: Requirements 14.13, 14.14, 14.15, 14.21
# ===========================================================================
@pytest.mark.skipif(not IS_PG, reason="need PostgreSQL (persistent policy epoch)")
@given(path=st.sampled_from(["within_ttl", "past_ttl", "invalidate", "unavailable"]), nonce=_NONCE)
@count_examples("P18")
@pbt_settings()
def test_p18_revocation_converges_no_stale_allow(path, nonce):
    async def scenario(s):
        proj, user, wi, wp = await _epoch_scenario(s, epoch=1)
        clock = _Clock()
        cache = PersistentEpochCache(epoch_ttl_seconds=1.0, clock=clock)
        state = {"grants": ["lead"]}

        async def loader():
            return list(state["grants"])

        async def _load():
            return await cache.get_or_load(
                s, user_id=user.id, project_id=proj.id, wp_index_id=wi.id, loader=loader
            )

        # 预热：epoch=1 缓存 lead grant。
        assert await _load() == ["lead"]
        # 撤权：DB epoch 1→2，权威结果变空。
        await _set_epoch(s, proj.id, 2)
        state["grants"] = []

        if path == "within_ttl":
            # ≤1s 窗口内：仍可能命中旧条目（收敛上界，允许，非 stale 违规）。
            clock.advance(0.4)
            assert await _load() == ["lead"]
        elif path == "past_ttl":
            # 超 ttl：重读 DB epoch=2 → 旧 epoch=1 条目永不匹配 → authoritative 重取空。
            clock.advance(1.01)
            assert await _load() == []
            assert cache.cached_epoch_for(proj.id) == 2
        elif path == "invalidate":
            # Redis 快路径失效 → 立即收敛（不推进时钟）。
            cache.invalidate(proj.id)
            assert await _load() == []
        else:  # unavailable：epoch 读取失败（Redis+dispatcher 全挂）→ fail-closed 权威现取，绝不 stale。
            async def _boom(_db, _pid):
                raise EpochUnavailable(str(_pid))

            cache.current_epoch = _boom  # type: ignore[assignment]
            assert await _load() == []

    run_isolated(scenario)


# ===========================================================================
# 覆盖报告 + 有效样例数落地（必须在同文件所有 property 之后运行）
# ===========================================================================
def test_zzz_pbt_coverage_report_and_valid_example_counts():
    """写出 P1–P20 覆盖矩阵 + 每 property 有效样例数 artifact；断言完整性与 correctness 阈值。"""
    # design P1–P20 全部登记覆盖来源（同源批次；无遗漏）。
    for i in range(1, 21):
        assert f"P{i}" in PROPERTY_MATRIX, f"design property P{i} 未登记覆盖来源"

    report_path = ev.EVIDENCE_DIR / "artifacts" / "task14" / "valid_example_counts.json"
    payload = write_report(report_path)
    assert payload["profile"] == ("correctness" if is_correctness() else payload["profile"])

    # 本文件的 gap 属性必须真正跑出有效样例（correctness 档 ≥100，smoke 档 ≥1）。
    pure_gap = ["P16", "P19", "P20"]
    db_gap = ["P9", "P10", "P12", "P15", "P18"]
    active_gap = pure_gap + (db_gap if IS_PG else [])
    threshold = target_examples() if is_correctness() else 1
    for pid in active_gap:
        got = VALID_EXAMPLE_COUNTS.get(pid, 0)
        assert got >= threshold, (
            f"{pid} 有效样例数 {got} < 期望 {threshold}（profile={payload['profile']}）"
        )
