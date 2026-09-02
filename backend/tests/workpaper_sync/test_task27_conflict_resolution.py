# -*- coding: utf-8 -*-
"""Task 27 离线守卫：纯判据、封闭映射与结构形态。
spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 2 Task 27
Requirements: 6.18, 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8, 8.9, 8.10, 8.11, 8.12, 10.10
Properties: **P35 / P36 / P37 / P38 / P43 / P65 / P67**

═══ 分工 ═══

本文件只放**不需要数据库**的判据：

* 纯函数（retry 准入闸、rollback source 准入、frozen contract 锁、decision→HTTP 映射）；
* 封闭枚举的**全集覆盖**（`FenceDecision` / `FenceReason` 少一个成员就是 fail-open 入口）；
* 结构形态（authorization-first 的调用顺序、零 Command Service、fence 判据不在本模块抄第二份、
  唯一 commit 边界）。

跨表跨事务的行为判据（冲突落行、折叠后发布、fence 五种判定的真实副作用、rollback
新版本/零写入/跨 wp 404）全部在 `_pg.py` —— 那些东西离线断言不了。

═══ 为什么结构判据要用 AST ═══

Task 26 的教训：子串判据在本域必假红也必假绿。本模块的 docstring 逐处解释「为什么
不在这里抄一份 fence 判据」时逐字写着 `evaluate_resolve_fence`；反过来，把
`self._requests.authorize_operation_scope(...)` 改名残留也能骗过子串。所有形态判据
一律走 `ast.ImportFrom` 名字与 `ast.Call` 目标。
"""
from __future__ import annotations

import ast
import inspect
import textwrap
import uuid
from pathlib import Path
from typing import Any

import pytest

from app.services.workpaper_sync import conflict_resolution as CR
from app.services.workpaper_sync import conflicts as CF
from app.services.workpaper_sync import merge as M
from app.services.workpaper_sync import oo_to_html as OH
from app.services.workpaper_sync.models import (
    ArtifactKind,
    ArtifactState,
    SyncDomainError,
)

_BACKEND = Path(__file__).resolve().parents[2]
_CR_PY = _BACKEND / "app" / "services" / "workpaper_sync" / "conflict_resolution.py"


def _tree(obj: Any) -> ast.AST:
    return ast.parse(textwrap.dedent(inspect.getsource(obj)))


def _imported(module: Any) -> dict[str, str]:
    """`{绑定名: 来源模块}` —— 结构化的 import 事实。"""
    out: dict[str, str] = {}
    for node in ast.walk(ast.parse(inspect.getsource(module))):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                out[alias.asname or alias.name] = node.module or ""
    return out


def _called(obj: Any) -> set[str]:
    """函数/方法体里被调用的名字（`Name` 与 `Attribute` 两种形态都算）。"""
    names: set[str] = set()
    for node in ast.walk(_tree(obj)):
        if isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Name):
                names.add(fn.id)
            elif isinstance(fn, ast.Attribute):
                names.add(fn.attr)
    return names


def _call_order(obj: Any, targets: tuple[str, ...]) -> list[str]:
    """按源码行序返回 `targets` 中实际出现的调用序列（顺序即判据）。"""
    seen: list[tuple[int, str]] = []
    for node in ast.walk(_tree(obj)):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", None)
        if name in targets:
            seen.append((node.lineno, name))
    return [name for _line, name in sorted(seen)]


# ═══════════════════════════════════════════════════════════════════════════
# 一、封闭映射：少一个成员就是 fail-open 入口
# ═══════════════════════════════════════════════════════════════════════════


class TestDecisionMappingIsClosed:
    """`FenceDecision`/`FenceReason` 的映射必须覆盖枚举全集。

    🔴 为什么这是**判据**而不是整洁癖：router 层拿这两张表把判定翻译成 HTTP。
    漏一个成员时最自然的写法是 `mapping.get(x, 200)` —— 于是新增的**拒绝**判定被静默
    翻译成 200 成功。这正是「fail-open 掩盖接线错误」的形态。
    """

    def test_every_decision_has_a_status(self) -> None:
        assert set(CR.RESOLVE_DECISION_STATUS) == set(CF.FenceDecision), (
            "decision→status 映射与枚举不等值："
            f"缺 {sorted(d.value for d in set(CF.FenceDecision) - set(CR.RESOLVE_DECISION_STATUS))}"
        )

    def test_every_reason_has_a_reject_code(self) -> None:
        assert set(CR.RESOLVE_REJECT_HTTP_CODE) == set(CF.FenceReason), (
            "reason→拒绝码映射与枚举不等值："
            f"缺 {sorted(r.value for r in set(CF.FenceReason) - set(CR.RESOLVE_REJECT_HTTP_CODE))}"
        )

    def test_reject_codes_are_pairwise_distinct(self) -> None:
        """逐条不同 —— 合并文案会让「哪条乐观锁失配」不可分辨（AC 8.5 要求逐项）。"""
        codes = list(CR.RESOLVE_REJECT_HTTP_CODE.values())
        assert len(codes) == len(set(codes)), f"拒绝码重复: {sorted(codes)}"

    def test_only_proceed_and_fold_are_success(self) -> None:
        """AC 8.5：只有 proceed/fold 可以继续产出 merged projection。"""
        success = {
            decision
            for decision, status in CR.RESOLVE_DECISION_STATUS.items()
            if status < 400
        }
        assert success == {CF.FenceDecision.proceed, CF.FenceDecision.fold}
        for decision in success:
            assert CF.FenceEvaluation(
                decision=decision,
                reason=CF.FenceReason.ok,
                canonical_application_id=uuid.uuid4(),
                normalized_effective_request_sequence=1,
            ).may_apply, "success 映射与 `FenceEvaluation.may_apply` 不一致"

    def test_unmapped_decision_raises_instead_of_defaulting(self) -> None:
        """`http_status_for` 必须抛而不是给默认值（默认值 = 新判定静默变成功）。"""
        for decision in CF.FenceDecision:
            assert CR.http_status_for(decision) == CR.RESOLVE_DECISION_STATUS[decision]
        with pytest.raises(CR.ConflictResolutionError):
            CR.http_status_for("nonexistent_decision")  # type: ignore[arg-type]


# ═══════════════════════════════════════════════════════════════════════════
# 二、retry 准入闸（AC 8.9 / Property 38）
# ═══════════════════════════════════════════════════════════════════════════


class TestRetryEligibilityGate:
    """`operation_id=NULL` 的 recovery case 一律不得进普通 retry。"""

    def test_none_is_refused_with_its_own_code(self) -> None:
        with pytest.raises(CR.RecoveryCaseRetryForbiddenError) as exc:
            CR.assert_retry_operation_eligible(None)
        assert exc.value.error_code == "recovery_case_requires_claim_before_retry"

    def test_a_real_id_passes_through_unchanged(self) -> None:
        """反向：合法 id 必须原样返回，否则闸门是恒红死路。"""
        oid = uuid.uuid4()
        assert CR.assert_retry_operation_eligible(oid) is oid

    def test_the_gate_returns_the_id_so_the_call_cannot_be_dropped(self) -> None:
        """返回值语义本身是判据：`-> None` 时删掉调用行不会有任何类型错误。

        这条断言的是**签名形态**：返回类型必须是 UUID 而不是 None，且 `retry` 真的把
        返回值往下传（不是「查了却不用」）。
        """
        sig = inspect.signature(CR.assert_retry_operation_eligible)
        assert sig.return_annotation in (uuid.UUID, "uuid.UUID"), sig.return_annotation
        src = textwrap.dedent(inspect.getsource(CR.ConflictResolutionService.retry))
        fn = ast.parse(src).body[0]
        assigned = [
            node
            for node in ast.walk(fn)
            if isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name)
            and node.value.func.id == "assert_retry_operation_eligible"
        ]
        assert len(assigned) == 1, (
            "`assert_retry_operation_eligible` 的返回值没有被绑定 ⇒ 它退化成「查了却不用」，"
            "删掉调用行不会有任何类型错误"
        )
        bound = assigned[0].targets[0]
        assert isinstance(bound, ast.Name)
        passed = [
            kw.value.id
            for node in ast.walk(fn)
            if isinstance(node, ast.Call)
            for kw in node.keywords
            if kw.arg == "operation_id" and isinstance(kw.value, ast.Name)
        ]
        assert bound.id in passed, (
            f"下游 `operation_id=` 传的不是闸门的返回值 {bound.id!r}，而是 {passed} —— "
            "那样闸门就成了摆设"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 三、rollback source 准入（AC 8.7 / Property 65 / 67）
# ═══════════════════════════════════════════════════════════════════════════


class TestRollbackSourceAdmission:
    """incoming（durable 或 quarantined）与 candidate 都不可作 rollback 源。"""

    def test_published_canonical_passes(self) -> None:
        assert (
            CR.assert_rollback_source_publishable(
                artifact_kind=ArtifactKind.canonical,
                artifact_state=ArtifactState.published,
            )
            is None
        )

    @pytest.mark.parametrize(
        ("kind", "state", "expected"),
        [
            (
                ArtifactKind.incoming,
                ArtifactState.durable,
                CR.RollbackSourceNotPublishedError,
            ),
            (
                ArtifactKind.incoming,
                ArtifactState.quarantined,
                CR.RollbackSourceQuarantinedError,
            ),
            (
                ArtifactKind.canonical,
                ArtifactState.quarantined,
                CR.RollbackSourceQuarantinedError,
            ),
            (
                ArtifactKind.upgrade_candidate,
                ArtifactState.candidate,
                CR.RollbackSourceNotPublishedError,
            ),
            (
                ArtifactKind.canonical,
                ArtifactState.staged,
                CR.RollbackSourceNotPublishedError,
            ),
            (
                ArtifactKind.projection,
                ArtifactState.published,
                CR.RollbackSourceNotPublishedError,
            ),
        ],
        ids=[
            "durable_incoming",
            "quarantined_incoming",
            "quarantined_canonical",
            "upgrade_candidate",
            "staged_canonical",
            "projection_artifact",
        ],
    )
    def test_every_forbidden_shape_is_refused(
        self, kind: ArtifactKind, state: ArtifactState, expected: type[Exception]
    ) -> None:
        with pytest.raises(expected):
            CR.assert_rollback_source_publishable(
                artifact_kind=kind, artifact_state=state
            )

    def test_quarantine_and_not_published_are_two_types(self) -> None:
        """安全隔离与「状态不对」必须分型：共用类型时前者的补救提示会被后者覆盖。"""
        assert not issubclass(
            CR.RollbackSourceQuarantinedError, CR.RollbackSourceNotPublishedError
        )
        assert not issubclass(
            CR.RollbackSourceNotPublishedError, CR.RollbackSourceQuarantinedError
        )
        assert (
            CR.RollbackSourceQuarantinedError.error_code
            != CR.RollbackSourceNotPublishedError.error_code
        )

    def test_admission_reuses_the_task13_predicate(self) -> None:
        """判据必须复用 `assert_substrate_usable`，不得在本域抄一张 kind/state 组合表。

        两套表必然漂移，而这条路径上「incoming 冒充历史版本」是最贵的错。
        """
        assert "assert_substrate_usable" in _called(
            CR.assert_rollback_source_publishable
        ), "rollback 准入没有复用 Task 13 的 substrate 判据 —— 出现了第二份组合表"


# ═══════════════════════════════════════════════════════════════════════════
# 四、frozen contract 锁（AC 6.2 / 7.10 的预览与折叠侧）
# ═══════════════════════════════════════════════════════════════════════════


class TestFrozenContractLock:
    class _Contract:
        def __init__(self, digest: str) -> None:
            self.canonical_sha256 = digest

    def test_matching_digest_passes(self) -> None:
        digest = "a" * 64
        assert (
            CR.assert_frozen_contract_matches_bundle(
                contract=self._Contract(digest), slot_digest=digest, where="unit"
            )
            is None
        )

    def test_drifted_digest_is_refused(self) -> None:
        with pytest.raises(CR.FrozenContractDriftError) as exc:
            CR.assert_frozen_contract_matches_bundle(
                contract=self._Contract("a" * 64), slot_digest="b" * 64, where="unit"
            )
        assert exc.value.error_code == "frozen_contract_digest_drift"

    def test_whitespace_is_not_a_difference(self) -> None:
        """DB `char(64)` 会带尾随空格 —— 不 strip 会让**正确**的 contract 被拒。"""
        digest = "c" * 64
        assert (
            CR.assert_frozen_contract_matches_bundle(
                contract=self._Contract(digest + " "),
                slot_digest=" " + digest,
                where="unit",
            )
            is None
        )


# ═══════════════════════════════════════════════════════════════════════════
# 五、fence 判据不在本模块抄第二份（AC 8.5 的单一真源）
# ═══════════════════════════════════════════════════════════════════════════


class TestFenceJudgementHasASingleSource:
    """resolve 的**顺序**判据只能有一份实现，在 Task 14 的 `conflicts.py` 里。"""

    def test_the_module_calls_evaluate_resolve_fence(self) -> None:
        imported = _imported(CR)
        assert imported.get("evaluate_resolve_fence") == (
            "app.services.workpaper_sync.conflicts"
        ), f"fence 判据不是从冲突域 import 的：{imported.get('evaluate_resolve_fence')!r}"
        assert "evaluate_resolve_fence" in _called(
            CR.ConflictResolutionService.resolve
        ), "`resolve` 没有调用 fence 判据 ⇒ 八项乐观锁形同不存在"

    def test_the_module_does_not_reimplement_the_ordering(self) -> None:
        """本模块不得出现第二份「先 identity 再 sequence」的比较逻辑。

        判据形态：不得直接读 `room.latest_durable_application_id` 去和 canonical
        application 比 —— 那正是抄一份顺序的入口。本模块只允许把它**装进**
        `RoomDurableFence` 交给判据函数。
        """
        src = _CR_PY.read_text(encoding="utf-8")
        tree = ast.parse(src)
        offenders: list[str] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Compare):
                continue
            names = {
                inner.attr
                for inner in ast.walk(node)
                if isinstance(inner, ast.Attribute)
            }
            if "latest_durable_application_id" in names:
                offenders.append(f"line {node.lineno}")
        assert offenders == [], (
            f"本模块自己比较了 room latest durable（行 {offenders}）—— "
            "AC 8.5 的顺序判据只能有一份实现（`conflicts.evaluate_resolve_fence`）"
        )

    def test_fold_and_supersede_are_separate_exception_types(self) -> None:
        """fold 不是 stale：两者的补救动作不同，必须分型（AC 5.5 的 no-self-supersede）。"""
        assert not issubclass(CR.ResolveSupersededError, CR.ResolveRebaseRequiredError)
        assert not issubclass(CR.ResolveRebaseRequiredError, CR.ResolveSupersededError)
        codes = {
            CR.ResolveFenceRejectedError.error_code,
            CR.ResolveSupersededError.error_code,
            CR.ResolveRebaseRequiredError.error_code,
            CR.ResolveWithoutConflictError.error_code,
        }
        assert len(codes) == 4, f"resolve 的四类拒绝共用了 error_code: {sorted(codes)}"

    def test_fold_is_not_mapped_to_a_rejection(self) -> None:
        """`fold` 必须落在成功侧 —— 映射到 409 就等于「同 app 抬 sequence 判自己 stale」。"""
        assert CR.RESOLVE_DECISION_STATUS[CF.FenceDecision.fold] < 400
        assert CR.RESOLVE_DECISION_STATUS[CF.FenceDecision.superseded] == 409

    def test_every_rejecting_decision_raises_before_the_coordinator_runs(self) -> None:
        """三条拒绝分支都必须在调用 coordinator **之前** —— 否则副作用已经发生。"""
        order = _call_order(
            CR.ConflictResolutionService.resolve,
            (
                "evaluate_resolve_fence",
                "ResolveFenceRejectedError",
                "ResolveSupersededError",
                "apply_durable_incoming",
            ),
        )
        assert order[0] == "evaluate_resolve_fence", order
        first_apply = order.index("apply_durable_incoming")
        for name in ("ResolveFenceRejectedError", "ResolveSupersededError"):
            assert order.index(name) < first_apply, (
                f"{name} 排在 `apply_durable_incoming` 之后 ⇒ 拒绝时副作用已经发生；"
                f"实得顺序 {order}"
            )


# ═══════════════════════════════════════════════════════════════════════════
# 六、authorization-first：顺序与「只读 scope index」
# ═══════════════════════════════════════════════════════════════════════════


class TestAuthorizationFirstShape:
    """四步读路径的顺序是判据本身（AC 5.5 末段 / 8.5 / 10.5）。"""

    @pytest.mark.parametrize(
        "method",
        ["preview", "resolve"],
        ids=["preview", "resolve"],
    )
    def test_authorization_precedes_any_business_read(self, method: str) -> None:
        """授权/归一必须早于任何业务行读取。

        `preview` 走合一入口 `read_operation`（它内部就是授权→canonicalize）；
        `resolve` 必须显式两段（授权 → fence → canonicalize 之间要插 fence 比对）。

        `retry` 不在此列且**不是豁免**：它自己不读任何业务行（授权在 coordinator 的同一个
        `apply_durable_incoming` 里），因此它的判据是
        :meth:`test_retry_gate_precedes_the_coordinator` + 「无自建执行面」两条。
        """
        fn = getattr(CR.ConflictResolutionService, method)
        order = _call_order(
            fn,
            (
                "read_operation",
                "authorize_operation_scope",
                "canonicalize_authorized",
                "_load_application",
                "lock_room",
                "load_bundle_snapshot",
                "load_conflicts",
                "apply_durable_incoming",
            ),
        )
        assert order, f"{method} 一个受管调用都没有 —— 判据失去锚点"
        auth_positions = [
            i
            for i, name in enumerate(order)
            if name in ("read_operation", "authorize_operation_scope")
        ]
        assert auth_positions and auth_positions[0] == 0, (
            f"{method} 的第一个调用不是授权：{order}"
        )
        for business in ("_load_application", "lock_room", "load_conflicts"):
            if business in order:
                assert order.index(business) > auth_positions[0], (
                    f"{method} 在授权之前读了业务行 {business}：{order}"
                )

    def test_retry_gate_precedes_the_coordinator(self) -> None:
        """retry 的 nullable-operation 闸必须排在 coordinator **之前**。

        排在后面时，claim 之前的 recovery case 会先进入 `apply_durable_incoming`，
        授权/canonicalize 已经跑过一遍 —— 那条路径会在 scope index 上留下一次查询，
        而 AC 8.9 要求「不得把 nullable operation id 传给普通 retry」。
        """
        order = _call_order(
            CR.ConflictResolutionService.retry,
            ("assert_retry_operation_eligible", "apply_durable_incoming"),
        )
        assert order == ["assert_retry_operation_eligible", "apply_durable_incoming"], (
            f"retry 的调用顺序不对：{order}"
        )

    def test_resolve_uses_the_two_phase_read_not_the_convenience_entry(self) -> None:
        """resolve 必须用两段式：合一入口没有插 fence 的位置。"""
        called = _called(CR.ConflictResolutionService.resolve)
        assert {"authorize_operation_scope", "canonicalize_authorized"} <= called
        assert "read_operation" not in called, (
            "resolve 用了合一入口 ⇒ fence 比对无处插入，只能在 canonicalize 之后补 —— "
            "而 AC 8.5 要求先验 requested 授权与 direct-primary invariant"
        )

    def test_preview_and_retry_require_canonical_application_binding(self) -> None:
        """只要求 **canonical primary** 绑定 application（不得要求 requested duplicate 绑定）。"""
        for method in ("preview", "resolve"):
            src = textwrap.dedent(
                inspect.getsource(getattr(CR.ConflictResolutionService, method))
            )
            fn = ast.parse(src).body[0]
            flags = [
                kw.value
                for node in ast.walk(fn)
                if isinstance(node, ast.Call)
                for kw in node.keywords
                if kw.arg == "require_application"
            ]
            assert flags, f"{method} 没有显式声明 require_application"
            assert all(
                isinstance(v, ast.Constant) and v.value is True for v in flags
            ), f"{method} 的 require_application 不是 True：{flags}"

    def test_rollback_authorizes_on_the_version_scope_only(self) -> None:
        """rollback 的 scope 查询只能用 `content_version` + opaque UUID。

        numeric revision 不得作 scope lookup key（AC 8.7 末句）：两个 wp 都有
        `revision 1`，用它定位必然跨 scope 碰撞。
        """
        src = textwrap.dedent(
            inspect.getsource(CR.ConflictResolutionService.rollback)
        )
        fn = ast.parse(src).body[0]
        scope_calls = [
            node
            for node in ast.walk(fn)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "resolve_scope"
        ]
        assert len(scope_calls) == 1, (
            f"rollback 应恰好查一次 scope index，实得 {len(scope_calls)} 次"
        )
        kinds = [
            inner.attr
            for kw in scope_calls[0].keywords
            if kw.arg == "resource_kind"
            for inner in ast.walk(kw.value)
            if isinstance(inner, ast.Attribute)
        ]
        assert kinds == ["content_version"], (
            f"rollback 的 scope resource kind 不是 content_version：{kinds}"
        )
        ids = [
            kw.value
            for kw in scope_calls[0].keywords
            if kw.arg == "resource_id"
        ]
        assert ids and any(
            isinstance(inner, ast.Name) and inner.id == "version_id"
            for node in ids
            for inner in ast.walk(node)
        ), "scope lookup 用的不是 route 上的 opaque `version_id`"
        # scope 查询必须早于任何历史 representation / bundle 读取。
        order = _call_order(
            CR.ConflictResolutionService.rollback,
            ("resolve_scope", "_published_representation_of", "resolve", "extract", "commit"),
        )
        assert order[0] == "resolve_scope", order
        for later in ("_published_representation_of", "extract", "commit"):
            if later in order:
                assert order.index(later) > 0

    def test_missing_scope_and_cross_scope_share_one_404_type(self) -> None:
        """越权与不存在必须无法区分（AC 8.7 末句 / 10.6 的统一 404）。"""
        src = textwrap.dedent(
            inspect.getsource(CR.ConflictResolutionService.rollback)
        )
        fn = ast.parse(src).body[0]
        raised = [
            node.exc.func.id
            for node in ast.walk(fn)
            if isinstance(node, ast.Raise)
            and isinstance(node.exc, ast.Call)
            and isinstance(node.exc.func, ast.Name)
        ]
        assert raised.count("ContentVersionNotFoundError") >= 2, (
            "scope 不可见与业务行不存在必须抛**同一**类型（各自一处 raise），"
            f"实得 {raised}"
        )
        # 且这个类型不得再派生出「跨 scope 专用」子类（那等于换个名字泄露）。
        subclasses = [
            cls
            for name in CR.__all__
            if isinstance(cls := getattr(CR, name), type)
            and cls is not CR.ContentVersionNotFoundError
            and issubclass(cls, CR.ContentVersionNotFoundError)
        ]
        assert subclasses == [], f"404 语义被细分成 {subclasses} —— 会泄露存在性"

    def test_the_two_404_doors_carry_distinguishable_internal_markers(self) -> None:
        """两道门共用类型，但必须带**可分辨的内部标记**。

        🔴 这条判据的存在理由是变异检验实测出来的：删掉 scope index 那道门之后，业务行
        那道门会接住同一个输入、抛同一个类型 ⇒ 只断言类型的守卫判 GREEN，于是
        「authorization-before-resource」这条不变量的第一道门可以被悄悄删掉。

        标记是**内部**的（不进 `error_code`、不进响应信封），所以不构成存在性泄露。
        """
        src = textwrap.dedent(
            inspect.getsource(CR.ConflictResolutionService.rollback)
        )
        fn = ast.parse(src).body[0]
        markers: list[str] = []
        for node in ast.walk(fn):
            if not (
                isinstance(node, ast.Raise)
                and isinstance(node.exc, ast.Call)
                and isinstance(node.exc.func, ast.Name)
                and node.exc.func.id == "ContentVersionNotFoundError"
            ):
                continue
            found = [
                kw.value.id
                for kw in node.exc.keywords
                if kw.arg == "refused_at" and isinstance(kw.value, ast.Name)
            ]
            assert found, f"第 {node.lineno} 行的 404 没有带 refused_at 标记"
            markers.extend(found)
        assert len(markers) == len(set(markers)), (
            f"两道门用了同一个 refused_at 标记 {markers} —— 删掉一道时另一道会接住同一"
            "输入并抛同样的标记，变异检验必判 GREEN"
        )
        assert set(markers) == {"REFUSED_AT_SCOPE_INDEX", "REFUSED_AT_BUSINESS_ROW"}, (
            markers
        )
        assert CR.REFUSED_AT_STAGES == {
            CR.REFUSED_AT_SCOPE_INDEX,
            CR.REFUSED_AT_BUSINESS_ROW,
        }
        # 标记必须走封闭词表：自由文本会让守卫只能做子串匹配。
        with pytest.raises(CR.ConflictResolutionError):
            CR.ContentVersionNotFoundError("x", refused_at="somewhere_else")

    def test_the_business_row_query_filters_by_workpaper(self) -> None:
        """业务行查询必须显式带 `wp_id ==` —— 这是第二道门的**全部**内容。

        它在 scope 门仍在时是冗余的（redundant by design），因此**行为上不可证伪**：
        任何跨 wp 的 UUID 都会先被 scope 门拦住。冗余的第二道门只能用形态判据钉住，
        否则某天 scope row 被错写/被 retire，跨 wp 定位就成立了。
        """
        src = textwrap.dedent(
            inspect.getsource(CR.ConflictResolutionService.rollback)
        )
        fn = ast.parse(src).body[0]
        version_selects = [
            node
            for node in ast.walk(fn)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "where"
            and any(
                isinstance(inner, ast.Attribute)
                and inner.attr == "WorkpaperContentVersion"
                for inner in ast.walk(node)
            )
            or (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "where"
                and any(
                    isinstance(inner, ast.Name)
                    and inner.id == "WorkpaperContentVersion"
                    for inner in ast.walk(node)
                )
            )
        ]
        assert version_selects, "找不到 content version 的查询 —— 判据失去锚点"
        columns = {
            inner.attr
            for node in version_selects
            for inner in ast.walk(node)
            if isinstance(inner, ast.Attribute)
        }
        assert "wp_id" in columns, (
            f"content version 查询没有按 wp 过滤（实得列 {sorted(columns)}）—— "
            "scope index 与业务行之间失去二次核对，scope row 一旦被错写就能跨 wp 定位"
        )
        assert "id" in columns


# ═══════════════════════════════════════════════════════════════════════════
# 七、零 Command Service（Property 38：retry 不再 forcesave）
# ═══════════════════════════════════════════════════════════════════════════

#: Command Service 的符号集合。与 `oo_to_html._COMMAND_SERVICE_SYMBOLS` 同源即可，
#: 但这里显式列出 —— import 私有名会让「Task 26 改了名字」变成本文件的假绿。
_COMMAND_SERVICE_NAMES = (
    "CommandService",
    "OnlyOfficeCommandService",
    "command_service",
    "forcesave",
    "issue_forcesave",
)


class TestNoForcesaveSurface:
    """retry/resolve 一律不再触发 OO forcesave（Property 38 的模块形态）。"""

    def test_no_command_service_symbol_is_imported_or_called(self) -> None:
        imported = set(_imported(CR))
        called: set[str] = set()
        for node in ast.walk(ast.parse(_CR_PY.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call):
                fn = node.func
                if isinstance(fn, ast.Name):
                    called.add(fn.id)
                elif isinstance(fn, ast.Attribute):
                    called.add(fn.attr)
        hits = sorted((imported | called) & set(_COMMAND_SERVICE_NAMES))
        assert hits == [], (
            f"本模块出现 Command Service 符号 {hits} —— durable incoming 的 retry/resolve "
            "一律不得再 forcesave（AC 8.9 / Property 38）"
        )

    def test_retry_has_no_execution_body_of_its_own(self) -> None:
        """retry 不得自建执行体：任何「retry 专用捷径」都会绕过某道门。

        判据：`retry` 体内除了闸门与 coordinator 调用，不得出现 extract/merge/commit
        这类执行面。
        """
        called = _called(CR.ConflictResolutionService.retry)
        forbidden = called & {
            "merge_projections",
            "apply_resolutions",
            "commit",
            "extract",
            "materialize",
            "open_substrate",
            "publish_representation",
        }
        assert forbidden == set(), (
            f"retry 自建了执行面 {sorted(forbidden)} —— 它必须复用 Task 26 的同一个 "
            "`apply_durable_incoming`（attempt>1）"
        )
        assert "apply_durable_incoming" in called


# ═══════════════════════════════════════════════════════════════════════════
# 八、唯一 commit 边界（Property 61 的本模块侧）
# ═══════════════════════════════════════════════════════════════════════════


class TestSingleCommitBoundary:
    """业务内容只经 `ContentMutationService.commit`；本模块自己不写 version/revision。"""

    def test_rollback_commits_through_the_content_mutation_service(self) -> None:
        called = _called(CR.ConflictResolutionService.rollback)
        assert "commit" in called, "rollback 没有走唯一 commit 边界"
        imported = _imported(CR)
        assert imported.get("ContentMutationService") == (
            "app.services.workpaper_sync.content_mutation"
        )

    def test_the_module_never_touches_revision_domain_writes(self) -> None:
        """`bump_content_revision` / `create_content_version` / `set_current_content_version`
        三个 business revision 域方法一律不得在本模块出现（Task 15 的 `RevisionLockedRepository`
        对它们恒抛，但本模块根本不该走到那一步）。
        """
        from app.services.workpaper_sync.content_mutation import (
            REVISION_DOMAIN_WRITE_METHODS,
        )

        called: set[str] = set()
        for node in ast.walk(ast.parse(_CR_PY.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                called.add(node.func.attr)
        hits = sorted(called & REVISION_DOMAIN_WRITE_METHODS)
        assert hits == [], (
            f"本模块直接调用 business revision 域写方法 {hits} —— "
            "revision 只由 `ContentMutationService.commit` 唯一事务推进"
        )

    def test_the_registry_records_this_module_as_a_merge_domain_consumer(self) -> None:
        """`merge.RETIRED_DEFERRALS` 必须登记本模块，且声明经由 commit 边界落库。"""
        mine = [
            entry
            for entry in M.RETIRED_DEFERRALS
            if str(entry["expected_consumer_module"]).endswith("conflict_resolution.py")
        ]
        assert len(mine) == 1, f"本模块的退役登记应恰一条，实得 {len(mine)}"
        entry = mine[0]
        assert entry["retired_by_task"] == "27"
        assert entry["intended_status"] == "retired"
        assert entry["commits_through"] == (
            "app/services/workpaper_sync/content_mutation.py"
        )
        assert "evaluate_resolve_fence" in str(entry["capability"])


# ═══════════════════════════════════════════════════════════════════════════
# 九、Task 26 的欠账在本任务被还清（登记 ↔ 事实双向）
# ═══════════════════════════════════════════════════════════════════════════


class TestTask26DebtIsSettled:
    """接线的**事实**与两张登记表必须一致，且欠账不得同时挂在两侧。"""

    def test_the_deferred_entry_is_gone_from_the_merge_registry(self) -> None:
        deferred = {str(e["capability"]) for e in M.DEFERRED_CONSUMERS}
        assert "evaluate_resolve_fence / apply_resolutions" not in deferred, (
            "同一能力仍挂在 `DEFERRED_CONSUMERS` 上 —— 「还没还」与「已还」并存"
        )
        retired = {str(e["capability"]) for e in M.RETIRED_DEFERRALS}
        assert "evaluate_resolve_fence / apply_resolutions" in retired

    def test_the_coordinator_registry_is_retired_not_deleted(self) -> None:
        entry = OH.RETIRED_ADJUDICATION_CONSUMER
        assert entry["intended_status"] == "retired"
        assert entry["retired_by_task"] == "27"
        assert not hasattr(OH, "DEFERRED_ADJUDICATION_CONSUMER"), (
            "旧登记名仍在 ⇒ 两张表并存，核对时不知道哪张是真的"
        )

    def test_the_settle_function_is_the_wiring_point(self) -> None:
        """折叠必须走 `merge.apply_resolutions`，且判据可用合成输入逐条喂。"""
        imported = _imported(OH)
        assert imported.get("apply_resolutions") == (
            "app.services.workpaper_sync.merge"
        )
        assert "apply_resolutions" in _called(OH.settle_adjudicated_projection)

    def test_the_refresh_verdict_no_longer_reads_merge_merged(self) -> None:
        """AC 8.12 末句：refresh 判据必须落在**真正发布**的那份 projection 上。

        判据形态：Task 15 的 `_advance_room` 不得再读 `mutation.merge.merged`，
        而必须调用 `projection_requires_client_refresh` 并把 settled 传进去。
        """
        from app.services.workpaper_sync.content_mutation import ContentMutationService

        src = textwrap.dedent(
            inspect.getsource(ContentMutationService._advance_room)  # noqa: SLF001
        )
        fn = ast.parse(src).body[0]
        merged_reads = [
            node.lineno
            for node in ast.walk(fn)
            if isinstance(node, ast.Attribute) and node.attr == "merged"
        ]
        assert merged_reads == [], (
            f"`_advance_room` 仍在读 `merge.merged`（行 {merged_reads}）—— "
            "带裁决时它与落库内容不同，refresh 判据会按错值计算"
        )
        calls = [
            node
            for node in ast.walk(fn)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "projection_requires_client_refresh"
        ]
        assert len(calls) == 1, "refresh 判据没有走 merge 域的唯一纯函数"
        keywords = {kw.arg for kw in calls[0].keywords}
        assert {"settled", "incoming", "word_only_keys"} <= keywords, keywords

    def test_merge_outcome_helper_delegates_to_the_same_pure_function(self) -> None:
        """`MergeOutcome.requires_client_refresh` 必须委托到同一份实现（不许两套）。"""
        assert "projection_requires_client_refresh" in _called(
            M.MergeOutcome.requires_client_refresh
        )

    def test_business_mutation_refuses_merge_without_projection(self) -> None:
        """带 merge 却没有 projection ⇒ `_advance_room` 只能回落到 `merge.merged`。"""
        from app.services.workpaper_sync.content_mutation import (
            AuthorityModelMismatchError,
            BusinessMutation,
        )

        class _FakeMerge:
            word_only_keys: tuple[str, ...] = ()

        with pytest.raises(AuthorityModelMismatchError):
            BusinessMutation(
                authoritative_payload=b"x", merge=_FakeMerge()  # type: ignore[arg-type]
            )

    def test_resolution_choices_require_a_merge(self) -> None:
        from app.services.workpaper_sync.content_mutation import (
            AuthorityModelMismatchError,
            BusinessMutation,
        )

        with pytest.raises(AuthorityModelMismatchError):
            BusinessMutation(
                authoritative_payload=b"x",
                resolution_choices=(
                    CF.ResolutionChoice(
                        stable_field_key="k",
                        kind=CF.ResolutionKind.keep_current,
                        oo_location="A1",
                    ),
                ),
            )


# ═══════════════════════════════════════════════════════════════════════════
# 十、异常分型总表（共用 error_code = 靠前的分支永久不可达）
# ═══════════════════════════════════════════════════════════════════════════


class TestResolveApplyLandedGate:
    """裁决轨迹只能记在**真的落地了**的应用上（AC 8.4 / 8.5 / 8.6 / P43）。

    🔴 这道判据的由来（2026-08-28 真库实测抓到的生产缺陷）：Task 26 的
    `apply_durable_incoming` 在 incoming 已 durable 之后**刻意不抛异常** —— 失败落成
    终态并保留 incoming（AC 5.7/5.8：durable 之后返回非零 ack 等于静默丢件）。
    `resolve` 不看 `outcome.result` 时，`workflow_locked=True` 的裁决实测得到
    `conflict_rows_marked=1` + `http_status=200`，而 revision/version/pointer 全没动。
    """

    def test_the_admissible_set_is_exactly_the_two_landed_states(self) -> None:
        """封闭集合：新增终态时必须显式归类，不得落进「视为成功」。"""
        assert CR.RESOLVE_LANDED_RESULTS == {"applied", "refresh_required"}
        assert CR.REBASE_ADMISSIBLE_RESULTS == CR.RESOLVE_LANDED_RESULTS | {"conflict"}

    def test_the_gate_covers_every_coordinator_terminal_state(self) -> None:
        """判据必须对 `OoToHtmlResult` **全集**有定义 —— 漏一个就是一条放行路径。"""
        classified = CR.RESOLVE_LANDED_RESULTS | {
            "authorization_stale",
            "error",
            "conflict",
        }
        assert {r.value for r in OH.OoToHtmlResult} <= classified, (
            f"未归类的 apply 终态: "
            f"{sorted({r.value for r in OH.OoToHtmlResult} - classified)}"
        )

    @pytest.mark.parametrize(
        ("result", "expected"),
        [
            ("applied", None),
            ("refresh_required", None),
            ("authorization_stale", CR.ResolveAuthorizationStaleError),
            ("error", CR.ResolveApplyFailedError),
            ("conflict", CR.ResolveApplyFailedError),
        ],
        ids=["applied", "refresh_required", "authorization_stale", "error", "conflict"],
    )
    def test_each_terminal_state_lands_on_its_own_verdict(
        self, result: str, expected: type[Exception] | None
    ) -> None:
        call = dict(
            result=result,
            error_code="final_fence_workflow_locked",
            error_stage="fence_before_publish",
            where="unit",
        )
        if expected is None:
            assert CR.assert_resolve_apply_landed(**call) is None
            return
        with pytest.raises(expected):
            CR.assert_resolve_apply_landed(**call)

    def test_rebase_admits_conflict_but_still_refuses_failures(self) -> None:
        """rebase 探测的正常结果是 `conflict`；失败终态仍必须原样透出。"""
        assert (
            CR.assert_resolve_apply_landed(
                result="conflict",
                error_code=None,
                error_stage=None,
                where="unit",
                landed=CR.REBASE_ADMISSIBLE_RESULTS,
            )
            is None
        )
        with pytest.raises(CR.ResolveAuthorizationStaleError):
            CR.assert_resolve_apply_landed(
                result="authorization_stale",
                error_code="final_fence_project_not_visible",
                error_stage="fence_before_write",
                where="unit",
                landed=CR.REBASE_ADMISSIBLE_RESULTS,
            )

    def test_the_two_verdicts_are_separate_types_and_carry_the_inner_cause(
        self,
    ) -> None:
        """不可重试 vs 可重试必须分型，且**哪一条** fence 要能被 router 归因。"""
        assert not issubclass(
            CR.ResolveAuthorizationStaleError, CR.ResolveApplyFailedError
        )
        assert not issubclass(
            CR.ResolveApplyFailedError, CR.ResolveAuthorizationStaleError
        )
        with pytest.raises(CR.ResolveAuthorizationStaleError) as exc:
            CR.assert_resolve_apply_landed(
                result="authorization_stale",
                error_code="final_fence_initiator_epoch_changed",
                error_stage="fence_before_write",
                where="unit",
            )
        assert exc.value.apply_error_code == "final_fence_initiator_epoch_changed"
        assert exc.value.apply_result == "authorization_stale"

    def test_the_gate_runs_before_the_adjudication_trail_is_written(self) -> None:
        """顺序即判据：轨迹是审计事实，不能先写完再发现没落地。"""
        order = _call_order(
            CR.ConflictResolutionService.resolve,
            ("assert_resolve_apply_landed", "_record_resolution_trail"),
        )
        assert order.index("assert_resolve_apply_landed") < order.index(
            "_record_resolution_trail"
        ), f"落地自证排在轨迹写入之后：{order}"

    def test_the_rebase_branch_also_asserts_landing(self) -> None:
        """rebase 分支的 apply 同样要自证 —— 否则授权失效会被包成 409「刷新再来」。"""
        src = textwrap.dedent(inspect.getsource(CR.ConflictResolutionService.resolve))
        calls = [
            node
            for node in ast.walk(ast.parse(src))
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "assert_resolve_apply_landed"
        ]
        assert len(calls) == 2, (
            f"`assert_resolve_apply_landed` 出现 {len(calls)} 次 —— proceed/fold 与 "
            "rebase 两条路各需一次"
        )
        assert any(
            any(kw.arg == "landed" for kw in call.keywords) for call in calls
        ), "rebase 那一次没有传 `landed=REBASE_ADMISSIBLE_RESULTS` ⇒ 会把正常的 conflict 判失败"


class TestErrorCodesAreDistinct:
    def test_every_exported_error_has_a_unique_code(self) -> None:
        codes: dict[str, list[str]] = {}
        for name in CR.__all__:
            cls = getattr(CR, name)
            if isinstance(cls, type) and issubclass(cls, SyncDomainError):
                codes.setdefault(cls.error_code, []).append(name)
        shared = {code: names for code, names in codes.items() if len(names) > 1}
        assert shared == {}, (
            f"以下 error_code 被多个异常共用 ⇒ 靠前的分支永久不可达: {shared}"
        )

    def test_codes_do_not_collide_with_the_coordinator_module(self) -> None:
        """跨模块也不得撞码：router 按 code 分派补救动作。"""
        mine = {
            getattr(CR, name).error_code
            for name in CR.__all__
            if isinstance(getattr(CR, name), type)
            and issubclass(getattr(CR, name), SyncDomainError)
        }
        theirs = {
            getattr(OH, name).error_code
            for name in OH.__all__
            if isinstance(getattr(OH, name), type)
            and issubclass(getattr(OH, name), SyncDomainError)
        }
        assert mine & theirs == set(), f"跨模块撞码: {sorted(mine & theirs)}"
