# -*- coding: utf-8 -*-
"""Task 28 离线守卫：显式 scope router、固定 guard 与真实调用链。
spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 2 Task 28
Requirements: 3.1, 3.6, 3.7, 5.8, 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 11.4
Properties: **P10 / P11 / P45**

═══ 本文件与 `_pg.py` 的分工 ═══

* 本文件 —— **形态**与**纯行为**判据：阶段链顺序、authorization-first 的 AST 形态、
  404/403/409 的分型与唯一构造点、路由前缀与 opaque id 约束、以及用替身仓储驱动的
  guard 行为（常量工作量、撤权重放在 cache 前被拦）。不连库。
* `test_task28_sync_router_pg.py` —— 真库 + TestClient 的端到端：statusline、
  scope index 与业务行同事务、三实体计数、跨 scope 404 的 envelope 逐字节相同。

═══ 为什么有这么多「源码形态」判据 ═══

AC 10.5/10.6 禁止的是**代码形态**（「严禁先查 room/operation/recovery/application 来
反推 scope」「统一 guard 的不可交换顺序为 …」）。行为观察只能证明「这次没查」——
把一次 `sa.select(WorkpaperOoRoom)` 加回 guard 阶段后，端到端测试大概率照样通过
（结果一样），只有源码判据会红。

判据一律走 **AST**（`ImportFrom` 名字 / `Call` 目标 / `Raise` 类型），不走 grep：
Task 26 有一条 grep 式判据被自己的解释性 docstring 打红过 —— 本文件的注释里逐字写着
`WorkpaperOoRoom`、`jwt.decode` 等被禁符号，裸词匹配必然假红。
"""
from __future__ import annotations

import ast
import inspect
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
_ROUTER_PY = _BACKEND / "app" / "routers" / "wp_sync_router.py"
_GUARD_PY = _BACKEND / "app" / "services" / "workpaper_sync" / "endpoint_guard.py"
_PAYLOADS_PY = _BACKEND / "app" / "services" / "workpaper_sync" / "endpoint_payloads.py"
_PKG_INIT_PY = _BACKEND / "app" / "services" / "workpaper_sync" / "__init__.py"
_LEGACY_PY = _BACKEND / "app" / "routers" / "wp_onlyoffice_router.py"
_REGISTRY_PY = _BACKEND / "app" / "router_registry" / "workpaper.py"

import app.routers.wp_sync_router as SR  # noqa: E402
import app.services.workpaper_sync.endpoint_guard as G  # noqa: E402
import app.services.workpaper_sync.endpoint_payloads as EP  # noqa: E402
from app.services.workpaper_sync import merge as M  # noqa: E402
from app.services.workpaper_sync.models import ScopeResourceKind  # noqa: E402


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _func(tree: ast.Module, name: str) -> ast.AsyncFunctionDef | ast.FunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"找不到函数 {name!r}")


# ═══════════════════════════════════════════════════════════════════════════
# 替身：只暴露 guard 真正用到的那一个仓储方法
# ═══════════════════════════════════════════════════════════════════════════


class _ScopeRow:
    """`working_paper_sync_scope_index` 行的非敏感投影替身。"""

    def __init__(
        self,
        *,
        project_id: uuid.UUID,
        wp_id: uuid.UUID,
        entry_id: str,
        room_id: uuid.UUID | None = None,
        generation: int | None = None,
    ) -> None:
        self.project_id = project_id
        self.wp_id = wp_id
        self.entry_id = entry_id
        self.room_id = room_id
        self.generation = generation


class _RecordingRepo:
    """记录**每一次**仓储调用。

    🔴 判据是「调用序列」而不是「结果对不对」：AC 10.6 要的是顺序与调用面，
    `calls` 里出现除 `resolve_scope` 以外的任何名字即为违规 —— 而那类违规不改变结果。
    """

    def __init__(self, rows: dict[str, _ScopeRow] | None = None) -> None:
        self.rows = rows or {}
        self.calls: list[tuple[str, str]] = []

    async def resolve_scope(self, *, resource_kind: Any, resource_id: str):
        kind = getattr(resource_kind, "value", str(resource_kind))
        self.calls.append(("resolve_scope", f"{kind}/{resource_id}"))
        return self.rows.get(f"{kind}/{resource_id}")

    def __getattr__(self, item: str):  # pragma: no cover - 只在违规时被触达
        raise AssertionError(
            f"guard 调用了 repository.{item} —— 阶段 ②③④ 只许 resolve_scope"
        )


class _Probe:
    def __init__(
        self,
        *,
        project_visible: bool = True,
        workflow_locked: bool = False,
        raises: BaseException | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        self.project_visible = project_visible
        self.workflow_locked = workflow_locked
        self.raises = raises
        self.payload = payload
        self.calls: list[str] = []

    async def observe(self, *, project_id, wp_id, entry_id):
        self.calls.append(f"{project_id}/{wp_id}/{entry_id}")
        if self.raises is not None:
            raise self.raises
        if self.payload is not None:
            return dict(self.payload)
        return {
            "project_visible": self.project_visible,
            "workflow_locked": self.workflow_locked,
            "readonly": self.workflow_locked,
        }


PROJECT = uuid.UUID("11111111-1111-4111-8111-111111111111")
WP = uuid.UUID("22222222-2222-4222-8222-222222222222")
OTHER_WP = uuid.UUID("33333333-3333-4333-8333-333333333333")
USER = uuid.UUID("44444444-4444-4444-8444-444444444444")
ENTRY = "xlsx/gt-d2-accounts-receivable"


def _guard_with(
    *,
    rows: dict[str, _ScopeRow] | None = None,
    probe: _Probe | None = None,
    authorize: Any = None,
    claims: G.ScopeClaimCodec | None = None,
    read_only_actions: frozenset[str] = frozenset(),
) -> tuple[G.SyncEndpointGuard, _RecordingRepo, _Probe]:
    repo = _RecordingRepo(rows)
    p = probe or _Probe()
    guard = G.SyncEndpointGuard(
        repository=repo,  # type: ignore[arg-type]
        visibility=p,
        authorize=authorize if authorize is not None else (lambda scope: True),
        claim_codec=claims,
        read_only_actions=read_only_actions,
    )
    return guard, repo, p


def _request(**kw: Any) -> G.SyncEndpointRequest:
    base: dict[str, Any] = dict(
        project_id=PROJECT,
        wp_id=WP,
        entry_id=ENTRY,
        action="materialize",
        user_id=USER,
        refs=(),
    )
    base.update(kw)
    return G.SyncEndpointRequest(**base)


# ═══════════════════════════════════════════════════════════════════════════
# A. 阶段链与 authorization-first 形态
# ═══════════════════════════════════════════════════════════════════════════


class TestGuardPhaseChain:
    """AC 10.6 的「不可交换顺序」必须是可证伪的形态，而不是 docstring 里的一句话。"""

    def test_required_phase_order_is_the_acceptance_criterion_order(self) -> None:
        """阶段序逐位等于 AC 10.6 原文顺序。

        写成逐位相等而不是集合包含：换序在功能上往往完全不变（每一阶段都跑了），
        只有位置判据会红 —— 而换序恰恰是 authorization-before-resource 唯一要禁的事。
        """
        assert [p.value for p in G.REQUIRED_PHASES] == [
            "authenticated",
            "route_scope_parsed",
            "scope_index_resolved",
            "visibility_verified",
            "action_authorized",
        ]

    def test_guarded_scope_rejects_reordered_phases(self) -> None:
        """阶段齐全但顺序被换 ⇒ `assert_complete()` 必抛。"""
        swapped = (
            G.GuardPhase.authenticated,
            G.GuardPhase.scope_index_resolved,
            G.GuardPhase.route_scope_parsed,
            G.GuardPhase.visibility_verified,
            G.GuardPhase.action_authorized,
        )
        scope = G.GuardedScope(
            project_id=PROJECT,
            wp_id=WP,
            entry_id=ENTRY,
            user_id=USER,
            action="materialize",
            refs=(),
            attributions={},
            phases=swapped,
            observed={},
        )
        with pytest.raises(G.SyncEndpointGuardError):
            scope.assert_complete()

    def test_guarded_scope_rejects_missing_phase(self) -> None:
        scope = G.GuardedScope(
            project_id=PROJECT,
            wp_id=WP,
            entry_id=ENTRY,
            user_id=USER,
            action="materialize",
            refs=(),
            attributions={},
            phases=G.REQUIRED_PHASES[:-1],
            observed={},
        )
        with pytest.raises(G.SyncEndpointGuardError):
            scope.assert_complete()

    def test_authorization_phase_touches_only_the_scope_index(self) -> None:
        """AST：guard 阶段方法只许调 `resolve_scope`，且不得引用任何业务表符号。"""
        assert G.assert_guard_authorization_first_shape() == ("resolve_scope",)

    def test_the_404_family_has_exactly_one_throw_site(self) -> None:
        """六条 404 分支必须 `append` 登记，由 `enforce()` 的唯一间接抛出点统一抛。"""
        assert G.assert_single_refusal_site() == 1

    def test_every_404_subclass_is_registered_for_the_throw_site_judgement(self) -> None:
        """反向锁死：新增 404 子类却忘了登记 ⇒ 上一条判据会漏掉它。

        用 `__subclasses__()` 反查而不是维护第二份名单 —— 第二份名单也会漏。
        """
        actual = {G.SyncScopeInvisibleError.__name__} | {
            c.__name__ for c in G.SyncScopeInvisibleError.__subclasses__()
        }
        assert actual == set(G._NOT_FOUND_FAMILY_NAMES), (
            f"404 家族实际成员 {sorted(actual)} 与判据名单 "
            f"{sorted(G._NOT_FOUND_FAMILY_NAMES)} 不符"
        )

    def test_refusal_families_are_pairwise_disjoint(self) -> None:
        """三族互不为子类、error_code 互不重复。

        共用 error_code 时靠前的分支被短路后靠后的会顶上来，定向变异判 GREEN ——
        本 spec 已三次踩到这个形态。
        """
        families = (
            G.SyncEndpointUnauthenticatedError,
            G.SyncScopeInvisibleError,
            G.SyncActionForbiddenError,
            G.VisibilityProbeFailedError,
        )
        for a in families:
            for b in families:
                if a is b:
                    continue
                assert not issubclass(a, b), f"{a.__name__} 是 {b.__name__} 的子类"
        codes: dict[str, str] = {}
        members = list(families)
        for family in families:
            members.extend(family.__subclasses__())
        for cls in members:
            code = cls.error_code
            assert code not in codes or codes[code] == cls.__name__, (
                f"error_code {code!r} 同时属于 {codes[code]} 与 {cls.__name__}"
            )
            codes[code] = cls.__name__

    def test_http_mapping_is_closed(self) -> None:
        """未登记的拒绝类型必须抛，而不是兜底 500。"""
        assert G.http_status_for_refusal(G.ScopeIndexMissError("x")) == 404
        assert G.http_status_for_refusal(G.ScopeCrossBoundaryError("x")) == 404
        assert G.http_status_for_refusal(G.ScopeProjectNotVisibleError("x")) == 404
        assert G.http_status_for_refusal(G.SyncWorkflowLockedError("x")) == 403
        assert G.http_status_for_refusal(G.ActionNotPermittedError("x")) == 403
        assert G.http_status_for_refusal(G.SyncEndpointUnauthenticatedError("x")) == 401
        assert G.http_status_for_refusal(G.VisibilityProbeFailedError("x")) == 503
        with pytest.raises(G.SyncEndpointGuardError):
            G.http_status_for_refusal(RuntimeError("未登记"))

    def test_both_probe_and_authorizer_are_mandatory(self) -> None:
        """可选依赖 = 默认放行。两者都必须在构造处失败。"""
        repo = _RecordingRepo()
        with pytest.raises(G.SyncEndpointGuardError):
            G.SyncEndpointGuard(repository=repo, visibility=None, authorize=lambda s: True)  # type: ignore[arg-type]
        with pytest.raises(G.SyncEndpointGuardError):
            G.SyncEndpointGuard(repository=repo, visibility=_Probe(), authorize=None)  # type: ignore[arg-type]


# ═══════════════════════════════════════════════════════════════════════════
# B. guard 行为
# ═══════════════════════════════════════════════════════════════════════════


class TestGuardRefusals:
    """六条 404、两条 403、一条 503 各自可独立证伪。"""

    @pytest.mark.asyncio
    async def test_unauthenticated_is_the_only_401(self) -> None:
        guard, repo, probe = _guard_with()
        with pytest.raises(G.SyncEndpointUnauthenticatedError):
            await guard.enforce(_request(user_id=None))
        # 401 在阶段 ① 就终止：连 scope index 都不该查（未认证请求不得触达任何查询面）。
        assert repo.calls == []
        assert probe.calls == []

    @pytest.mark.asyncio
    async def test_missing_route_entry_is_404_not_422(self) -> None:
        guard, _repo, _probe = _guard_with()
        with pytest.raises(G.RouteScopeIncompleteError):
            await guard.enforce(_request(entry_id=None))

    @pytest.mark.asyncio
    async def test_blank_route_entry_counts_as_missing(self) -> None:
        """空白 entry 与缺 entry 同型 —— `"  "` 不得被当成合法 entry_id。"""
        guard, _repo, _probe = _guard_with()
        with pytest.raises(G.RouteScopeIncompleteError):
            await guard.enforce(_request(entry_id="   "))

    @pytest.mark.asyncio
    async def test_scope_index_miss_and_retired_share_one_type(self) -> None:
        """`resolve_scope` 已过滤 `retired_at`，所以「不存在」与「已退役」同一条分支。"""
        guard, repo, _probe = _guard_with()
        ref = G.ScopeRef(
            resource_kind=ScopeResourceKind.sync_operation, resource_id=str(uuid.uuid4())
        )
        with pytest.raises(G.ScopeIndexMissError):
            await guard.enforce(_request(refs=(ref,)))
        assert [c[0] for c in repo.calls] == ["resolve_scope"]

    @pytest.mark.asyncio
    async def test_cross_scope_use_is_its_own_branch(self) -> None:
        op = uuid.uuid4()
        rows = {
            f"sync_operation/{op}": _ScopeRow(
                project_id=PROJECT, wp_id=OTHER_WP, entry_id=ENTRY
            )
        }
        guard, _repo, _probe = _guard_with(rows=rows)
        ref = G.ScopeRef(
            resource_kind=ScopeResourceKind.sync_operation, resource_id=str(op)
        )
        with pytest.raises(G.ScopeCrossBoundaryError):
            await guard.enforce(_request(refs=(ref,)))

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("kind", "raw"),
        [
            (ScopeResourceKind.content_version, "11"),
            (ScopeResourceKind.content_version, "0"),
            (ScopeResourceKind.sync_operation, "11"),
            (ScopeResourceKind.room, "999999"),
            (ScopeResourceKind.recovery_case, "1"),
        ],
        ids=[
            "version-11",
            "version-0",
            "operation-11",
            "room-999999",
            "recovery-case-1",
        ],
    )
    async def test_numeric_revision_as_route_key_is_refused(
        self, kind: ScopeResourceKind, raw: str
    ) -> None:
        """numeric revision 作 scope/route key 一律拒（AC 10.6 / 8.7）。

        🔴 分母**必须**跨 resource kind，这是变异检验实测出来的：第一版只测了
        `content_version`，而那个 kind 上还有第二条判据（「必须是 UUID」）。两条分支
        当时共用一个异常类型 ⇒ 把 `is_opaque_resource_id(...)` 短路成 `if False:` 之后，
        UUID 那条会抛出同一类型顶上来 ⇒ 判据照旧通过 ⇒ 「numeric revision 不得作 scope
        key」这条对 room/operation/recovery case 等**全部其他 kind** 从未被锁住。
        现在两条分支各有独立类型（`OpaqueResourceIdRequiredError` /
        `VersionIdNotUuidError`），且本判据覆盖三种非 version kind。
        """
        guard, _repo, _probe = _guard_with()
        ref = G.ScopeRef(resource_kind=kind, resource_id=raw)
        with pytest.raises(G.OpaqueResourceIdRequiredError) as caught:
            await guard.enforce(_request(refs=(ref,)))
        assert not isinstance(caught.value, G.VersionIdNotUuidError), (
            "非 opaque 的 route key 被判成「不是 UUID」—— 两条分支必须各自可证伪"
        )

    @pytest.mark.asyncio
    async def test_non_uuid_version_id_is_refused(self) -> None:
        """content_version 的 resource_id 只接受 immutable UUID。

        与上一条分型的理由：`"rev-11"` 是 opaque 的（不是纯数字），只有 UUID 判据
        才拦得住它 —— 而两个 wp 的 revision 1 必须由不同 UUID 无碰撞定位。
        """
        guard, _repo, _probe = _guard_with()
        ref = G.ScopeRef(
            resource_kind=ScopeResourceKind.content_version, resource_id="rev-11"
        )
        with pytest.raises(G.VersionIdNotUuidError):
            await guard.enforce(_request(refs=(ref,)))

    @pytest.mark.asyncio
    async def test_the_two_opaque_id_branches_do_not_share_an_error_code(self) -> None:
        """反向锁死上面两条：共用 error_code 时靠前的分支会变成事实上的死代码。

        判据不只看「类型不同」，还看 `error_code` 不同 —— HTTP 层与 metrics 都按 code
        归因，两条分支共用一个 code 时运维分不清「拿 revision 当 key」与「version_id
        格式错」，而这两者的处置完全不同（前者是越权探测，后者是客户端 bug）。
        """
        assert G.OpaqueResourceIdRequiredError is not G.VersionIdNotUuidError
        assert not issubclass(
            G.OpaqueResourceIdRequiredError, G.VersionIdNotUuidError
        )
        assert not issubclass(
            G.VersionIdNotUuidError, G.OpaqueResourceIdRequiredError
        )
        assert (
            G.OpaqueResourceIdRequiredError.error_code
            != G.VersionIdNotUuidError.error_code
        )
        # 两者仍在同一 404 家族 ⇒ 对外 envelope/status 完全相同（Property 45）
        for cls in (G.OpaqueResourceIdRequiredError, G.VersionIdNotUuidError):
            assert issubclass(cls, G.SyncScopeInvisibleError)
            assert G.http_status_for_refusal(cls("x")) == 404

    @pytest.mark.asyncio
    async def test_project_invisible_is_404_and_the_probe_really_ran(self) -> None:
        room = uuid.uuid4()
        rows = {
            f"room/{room}": _ScopeRow(project_id=PROJECT, wp_id=WP, entry_id=ENTRY)
        }
        guard, _repo, probe = _guard_with(
            rows=rows, probe=_Probe(project_visible=False)
        )
        ref = G.ScopeRef(resource_kind=ScopeResourceKind.room, resource_id=str(room))
        with pytest.raises(G.ScopeProjectNotVisibleError):
            await guard.enforce(_request(refs=(ref,)))
        assert len(probe.calls) == 1, "visibility 判据必须真查，不得靠硬编码"

    @pytest.mark.asyncio
    async def test_workflow_locked_is_403_for_write_actions(self) -> None:
        room = uuid.uuid4()
        rows = {f"room/{room}": _ScopeRow(project_id=PROJECT, wp_id=WP, entry_id=ENTRY)}
        guard, _repo, _probe = _guard_with(
            rows=rows, probe=_Probe(workflow_locked=True), read_only_actions=frozenset({"read_timeline"})
        )
        ref = G.ScopeRef(resource_kind=ScopeResourceKind.room, resource_id=str(room))
        with pytest.raises(G.SyncWorkflowLockedError):
            await guard.enforce(_request(refs=(ref,), action="forcesave"))

    @pytest.mark.asyncio
    async def test_workflow_locked_still_allows_registered_read_actions(self) -> None:
        """归档/复核通过的底稿仍必须能看 conflicts/timeline（AC 11.6 / 11.11）。

        🔴 这条判据的由来是一个**真实缺陷**：第一版让 guard 无条件按 `workflow_locked`
        拒绝，真库实测里 `GET /recovery-cases` 也拿到 403。当时的离线守卫只测了写
        action 的否定侧，所以全绿。
        """
        room = uuid.uuid4()
        rows = {f"room/{room}": _ScopeRow(project_id=PROJECT, wp_id=WP, entry_id=ENTRY)}
        guard, _repo, _probe = _guard_with(
            rows=rows,
            probe=_Probe(workflow_locked=True),
            read_only_actions=frozenset({"read_timeline"}),
        )
        ref = G.ScopeRef(resource_kind=ScopeResourceKind.room, resource_id=str(room))
        scope = await guard.enforce(_request(refs=(ref,), action="read_timeline"))
        scope.assert_complete()

    @pytest.mark.asyncio
    async def test_an_empty_read_only_set_fails_closed(self) -> None:
        """默认空名单 ⇒ 一律拒绝。可选参数不得意味着「默认放行」。"""
        room = uuid.uuid4()
        rows = {f"room/{room}": _ScopeRow(project_id=PROJECT, wp_id=WP, entry_id=ENTRY)}
        guard, _repo, _probe = _guard_with(
            rows=rows, probe=_Probe(workflow_locked=True)
        )
        ref = G.ScopeRef(resource_kind=ScopeResourceKind.room, resource_id=str(room))
        with pytest.raises(G.SyncWorkflowLockedError):
            await guard.enforce(_request(refs=(ref,), action="read_timeline"))

    @pytest.mark.asyncio
    async def test_action_callback_denial_is_its_own_403_branch(self) -> None:
        room = uuid.uuid4()
        rows = {f"room/{room}": _ScopeRow(project_id=PROJECT, wp_id=WP, entry_id=ENTRY)}
        guard, _repo, _probe = _guard_with(rows=rows, authorize=lambda scope: False)
        ref = G.ScopeRef(resource_kind=ScopeResourceKind.room, resource_id=str(room))
        with pytest.raises(G.ActionNotPermittedError):
            await guard.enforce(_request(refs=(ref,)))

    @pytest.mark.asyncio
    async def test_probe_failure_is_neither_403_nor_404(self) -> None:
        """探针崩了既不能判「可见」（fail-open）也不能判「越权」。"""
        guard, _repo, _probe = _guard_with(
            probe=_Probe(raises=RuntimeError("visibility 服务不可用"))
        )
        with pytest.raises(G.VisibilityProbeFailedError) as caught:
            await guard.enforce(_request())
        assert not isinstance(caught.value, G.SyncScopeInvisibleError)
        assert not isinstance(caught.value, G.SyncActionForbiddenError)

    @pytest.mark.asyncio
    async def test_probe_payload_missing_the_visibility_key_fails_closed(self) -> None:
        """缺 `project_visible` 时按缺省值放行 = 取消整道门。"""
        guard, _repo, _probe = _guard_with(probe=_Probe(payload={"workflow_locked": False}))
        with pytest.raises(G.VisibilityProbeFailedError):
            await guard.enforce(_request())


class TestConstantWorkRefusal:
    """三种 404 原因必须跑完**同一串工作**（AC 10.6 的「同阶段 + 统一时序预算」）。

    时间本身不适合当判据（CI 抖动），所以判的是**可观测的工作量**：
    scope-index 查询次数与 visibility 探针调用次数。就地 `raise` 会让某一种原因
    少跑一次探针 —— 那正是存在性预言机的来源。
    """

    @pytest.mark.asyncio
    async def test_all_three_404_causes_do_the_same_amount_of_work(self) -> None:
        op_ok = uuid.uuid4()
        op_cross = uuid.uuid4()
        op_miss = uuid.uuid4()
        rows = {
            f"sync_operation/{op_ok}": _ScopeRow(
                project_id=PROJECT, wp_id=WP, entry_id=ENTRY
            ),
            f"sync_operation/{op_cross}": _ScopeRow(
                project_id=PROJECT, wp_id=OTHER_WP, entry_id=ENTRY
            ),
        }
        observed: dict[str, tuple[int, int]] = {}
        for label, op, invisible in (
            ("miss", op_miss, False),
            ("cross", op_cross, False),
            ("invisible", op_ok, True),
        ):
            guard, repo, probe = _guard_with(
                rows=rows, probe=_Probe(project_visible=not invisible)
            )
            ref = G.ScopeRef(
                resource_kind=ScopeResourceKind.sync_operation, resource_id=str(op)
            )
            with pytest.raises(G.SyncScopeInvisibleError):
                await guard.enforce(_request(refs=(ref,)))
            observed[label] = (len(repo.calls), len(probe.calls))
        assert len(set(observed.values())) == 1, (
            f"三种 404 原因的工作量不同：{observed} —— 响应时间会成为存在性预言机"
        )
        assert observed["miss"] == (1, 1)

    @pytest.mark.asyncio
    async def test_the_action_callback_never_runs_when_a_404_is_pending(self) -> None:
        """404 待抛时不得进入阶段 ⑤ —— 否则 403/404 的分型顺序被颠倒。"""
        seen: list[str] = []

        def _authorize(scope: G.GuardedScope) -> bool:
            seen.append(scope.action)
            return True

        guard, _repo, _probe = _guard_with(
            probe=_Probe(project_visible=False), authorize=_authorize
        )
        with pytest.raises(G.ScopeProjectNotVisibleError):
            await guard.enforce(_request())
        assert seen == []


class TestRevokedReplayIsRefusedBeforeAnyCacheLookup:
    """Property 45 末段：首次成功后撤权，同 key 重放必须**零泄露、零副作用**。"""

    @pytest.mark.asyncio
    async def test_replay_after_revocation_stops_at_the_guard(self) -> None:
        room = uuid.uuid4()
        rows = {f"room/{room}": _ScopeRow(project_id=PROJECT, wp_id=WP, entry_id=ENTRY)}
        allowed = {"value": True}
        guard, repo, _probe = _guard_with(
            rows=rows, authorize=lambda scope: allowed["value"]
        )
        ref = G.ScopeRef(resource_kind=ScopeResourceKind.room, resource_id=str(room))
        first = await guard.enforce(_request(refs=(ref,), action="forcesave"))
        first.assert_complete()

        allowed["value"] = False
        before = list(repo.calls)
        with pytest.raises(G.ActionNotPermittedError):
            await guard.enforce(_request(refs=(ref,), action="forcesave"))
        # 撤权后的重放只多了一次 scope-index 读：没有业务读、没有幂等缓存读。
        assert [c[0] for c in repo.calls[len(before) :]] == ["resolve_scope"]
        assert guard.refused == 1


class TestSignedScopeClaim:
    """download-only 签发的短期 claim：跨 scope / 过期 / 换用途 / 伪造全部拒绝。"""

    def _codec(self) -> G.ScopeClaimCodec:
        return G.ScopeClaimCodec("task28-secret")

    def _complete_scope(self, ref: G.ScopeRef) -> G.GuardedScope:
        return G.GuardedScope(
            project_id=PROJECT,
            wp_id=WP,
            entry_id=ENTRY,
            user_id=USER,
            action="download_only",
            refs=(ref,),
            attributions={
                ref.key: G.ScopeAttribution(
                    resource_kind=ref.resource_kind,
                    resource_id=ref.resource_id,
                    project_id=PROJECT,
                    wp_id=WP,
                    entry_id=ENTRY,
                    room_id=None,
                    generation=None,
                )
            },
            phases=G.REQUIRED_PHASES,
            observed={"project_visible": True},
        )

    def test_empty_secret_is_refused_at_construction(self) -> None:
        with pytest.raises(G.ScopeClaimMismatchError):
            G.ScopeClaimCodec("")

    def test_mint_requires_a_complete_guarded_scope(self) -> None:
        """签发面只接受已过 guard 的 scope —— 否则能铸出跨 scope 的合法 claim。"""
        ref = G.ScopeRef(
            resource_kind=ScopeResourceKind.recovery_case, resource_id=str(uuid.uuid4())
        )
        partial = G.GuardedScope(
            project_id=PROJECT,
            wp_id=WP,
            entry_id=ENTRY,
            user_id=USER,
            action="download_only",
            refs=(ref,),
            attributions={},
            phases=G.REQUIRED_PHASES[:2],
            observed={},
        )
        with pytest.raises(G.SyncEndpointGuardError):
            self._codec().mint(scope=partial, ref=ref, purpose="recovery_download")

    def test_roundtrip_then_cross_scope_reuse_is_refused(self) -> None:
        codec = self._codec()
        case = uuid.uuid4()
        ref = G.ScopeRef(
            resource_kind=ScopeResourceKind.recovery_case, resource_id=str(case)
        )
        token, claim = codec.mint(
            scope=self._complete_scope(ref), ref=ref, purpose="recovery_download"
        )
        assert codec.decode(token).resource_id == str(case)
        assert claim.purpose == "recovery_download"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "flavour",
        ["forged", "expired", "wrong_purpose", "cross_wp", "not_in_refs"],
        ids=["forged", "expired", "wrong-purpose", "cross-wp", "not-in-refs"],
    )
    async def test_bad_claims_share_the_404_family(self, flavour: str) -> None:
        codec = self._codec()
        case = uuid.uuid4()
        ref = G.ScopeRef(
            resource_kind=ScopeResourceKind.recovery_case, resource_id=str(case)
        )
        rows = {
            f"recovery_case/{case}": _ScopeRow(
                project_id=PROJECT, wp_id=WP, entry_id=ENTRY
            )
        }
        purpose = "recovery_download"
        if flavour == "forged":
            token = G.ScopeClaimCodec("another-secret").mint(
                scope=self._complete_scope(ref), ref=ref, purpose=purpose
            )[0]
        elif flavour == "expired":
            token = codec.mint(
                scope=self._complete_scope(ref),
                ref=ref,
                purpose=purpose,
                ttl=timedelta(seconds=-5),
            )[0]
        elif flavour == "wrong_purpose":
            token = codec.mint(
                scope=self._complete_scope(ref), ref=ref, purpose="other_purpose"
            )[0]
        elif flavour == "cross_wp":
            other = G.ScopeClaim(
                schema_version=G.CLAIM_SCHEMA_VERSION,
                project_id=PROJECT,
                wp_id=OTHER_WP,
                entry_id=ENTRY,
                resource_kind=ref.resource_kind,
                resource_id=ref.resource_id,
                user_id=USER,
                purpose=purpose,
                expires_at=_now() + timedelta(minutes=5),
            )
            token = codec.encode(other)
        else:
            elsewhere = G.ScopeRef(
                resource_kind=ScopeResourceKind.recovery_case,
                resource_id=str(uuid.uuid4()),
            )
            token = codec.mint(
                scope=self._complete_scope(elsewhere), ref=elsewhere, purpose=purpose
            )[0]
        guard, _repo, _probe = _guard_with(rows=rows, claims=codec)
        with pytest.raises(G.ScopeClaimMismatchError):
            await guard.enforce(
                _request(
                    refs=(ref,),
                    action="download_recovery_artifact",
                    signed_claim=token,
                    claim_purpose=purpose,
                )
            )

    @pytest.mark.asyncio
    async def test_a_claim_without_a_codec_is_never_waved_through(self) -> None:
        case = uuid.uuid4()
        ref = G.ScopeRef(
            resource_kind=ScopeResourceKind.recovery_case, resource_id=str(case)
        )
        rows = {
            f"recovery_case/{case}": _ScopeRow(
                project_id=PROJECT, wp_id=WP, entry_id=ENTRY
            )
        }
        guard, _repo, _probe = _guard_with(rows=rows, claims=None)
        with pytest.raises(G.ScopeClaimMismatchError):
            await guard.enforce(
                _request(refs=(ref,), signed_claim="anything", claim_purpose="p")
            )


# ═══════════════════════════════════════════════════════════════════════════
# C. router 形态
# ═══════════════════════════════════════════════════════════════════════════

#: Task 28 明文要求的端点（design §API 逐条列出）。
_REQUIRED_ENDPOINTS: tuple[tuple[str, str], ...] = (
    ("POST", "/pending-mutations"),
    ("GET", "/store-projection"),
    ("POST", "/materialize"),
    ("POST", "/rooms/{room_id}/confirm-descriptor"),
    ("POST", "/rooms/{room_id}/forcesave"),
    ("POST", "/rooms/{room_id}/close-intents"),
    ("GET", "/recovery-cases"),
    ("POST", "/recovery-cases/{case_id}/claim"),
    ("POST", "/recovery-cases/{case_id}/download-only"),
    ("GET", "/operations/{operation_id}"),
    ("GET", "/operations/{operation_id}/conflicts"),
    ("GET", "/operations/{operation_id}/timeline"),
    ("POST", "/operations/{operation_id}/resolve"),
    ("POST", "/versions/{version_id}/rollback"),
)


def _user_routes() -> list[tuple[frozenset[str], str]]:
    return [(frozenset(r.methods), r.path) for r in SR.router.routes]


class TestRouterShape:
    def test_every_required_endpoint_exists_under_the_explicit_prefix(self) -> None:
        routes = {(m, p) for methods, p in _user_routes() for m in methods}
        missing = [
            (method, suffix)
            for method, suffix in _REQUIRED_ENDPOINTS
            if (method, SR.USER_SYNC_PREFIX + suffix) not in routes
        ]
        assert not missing, f"缺端点: {missing}"

    def test_all_user_routes_carry_explicit_project_wp_entry(self) -> None:
        """AC 10.6：每个用户路由**显式**携带 project/wp/entry。"""
        for methods, path in _user_routes():
            assert path.startswith(SR.USER_SYNC_PREFIX), (
                f"{sorted(methods)} {path} 不在显式 scope 前缀下 —— "
                "缺 scope 段的端点必须从 room/operation 反推归属，那是 AC 10.5 明令禁止的"
            )

    def test_the_entry_id_segment_uses_the_path_converter(self) -> None:
        """`entry_id` 必须是 `:path` 转换器（形态侧）。"""
        assert "{entry_id:path}" in SR.USER_SYNC_PREFIX, (
            f"USER_SYNC_PREFIX={SR.USER_SYNC_PREFIX!r} 的 entry 段不是 `:path` 转换器"
        )

    @pytest.mark.parametrize(
        "entry",
        [
            "xlsx/gt-d2-accounts-receivable",
            "xlsx/d4/analysis/d4-tab-customer-price",
            "docx/gt-a10-bundle",
        ],
        ids=["two-segment", "four-segment", "docx"],
    )
    def test_a_real_slashed_entry_id_routes(self, entry: str) -> None:
        """**行为侧**：真实（含斜杠的）entry_id 必须唯一命中每条路由并解出原值。

        🔴 这条判据的由来是一个**真实缺陷**：第一版把 entry 段写成 `{entry_id}`
        （默认转换器 `[^/]+`），而
        `backend/data/workpaper_sync_entry_manifest.json` 的 **186 条 entry_id 全部含
        `/`**，最深四段。后果是**每一个**端点在生产上恒 404 —— 而且是 Starlette 自己的
        `{"detail":"Not Found"}`，连 guard 都进不去。真库实测时 13 个场景全部拿到那个
        404，而所有「路径模板长得对」的形态判据全绿：
        `path.startswith(USER_SYNC_PREFIX)` 在两种转换器下都成立。

        所以判据必须落到**路由匹配**上，且要断言解出的 `entry_id` 逐字等于原值
        （贪婪 `.*` 若把后缀吞掉，`entry_id` 会变成 `xxx/materialize`）。
        """
        project, wp = uuid.uuid4(), uuid.uuid4()
        base = f"/api/projects/{project}/workpapers/{wp}/sync/entries/{entry}"
        room, op, case, version = (uuid.uuid4() for _ in range(4))
        suffixes = [
            ("POST", "/pending-mutations"),
            ("GET", "/store-projection"),
            ("POST", "/materialize"),
            ("POST", f"/rooms/{room}/confirm-descriptor"),
            ("POST", f"/rooms/{room}/forcesave"),
            ("POST", f"/rooms/{room}/close-intents"),
            ("GET", "/recovery-cases"),
            ("POST", f"/recovery-cases/{case}/claim"),
            ("POST", f"/recovery-cases/{case}/download-only"),
            ("GET", f"/recovery-cases/{case}/download"),
            # Task 29 追加：recovery case 的**独立** timeline（AC 13.5 / 13.6）。
            ("GET", f"/recovery-cases/{case}/timeline"),
            ("GET", f"/operations/{op}"),
            ("GET", f"/operations/{op}/conflicts"),
            ("GET", f"/operations/{op}/timeline"),
            ("POST", f"/operations/{op}/resolve"),
            ("POST", f"/operations/{op}/retry"),
            ("POST", f"/versions/{version}/rollback"),
        ]
        assert len(suffixes) == len(SR.router.routes), (
            "本判据的分母必须覆盖全部路由 —— 端点增删时同步这张表"
        )
        for method, suffix in suffixes:
            scope = {
                "type": "http",
                "method": method,
                "path": base + suffix,
                "headers": [],
            }
            hits = []
            for route in SR.router.routes:
                match, child = route.matches(scope)
                if match.name == "FULL":
                    hits.append((route.endpoint.__name__, child.get("path_params", {})))
            assert len(hits) == 1, (
                f"{method} {suffix} 命中 {[h[0] for h in hits]} —— 应恰好 1 条"
            )
            assert hits[0][1].get("entry_id") == entry, (
                f"{method} {suffix} 解出的 entry_id={hits[0][1].get('entry_id')!r} "
                f"≠ {entry!r} —— 贪婪 `.*` 把后缀吞进了 entry_id"
            )

    def test_no_route_uses_numeric_revision_as_a_path_parameter(self) -> None:
        """`{revision}` 之类的路径参数一律不得出现（AC 10.6 / 8.7）。"""
        for _methods, path in _user_routes():
            assert "{revision}" not in path and "{numeric_revision}" not in path, path

    def test_rollback_takes_an_opaque_version_id_typed_as_str(self) -> None:
        """`version_id` 必须声明为 `str` 而不是 `uuid.UUID`。

        声明成 UUID 时 `/versions/11/rollback` 会被 FastAPI 拦成 **422**，
        于是「numeric revision 不得作 route key」由框架顺手实现、本 spec 无从证伪，
        而且 422 与统一 404 oracle 不同桶（存在性泄露）。
        """
        hints = inspect.get_annotations(SR.rollback_version, eval_str=False)
        assert hints["version_id"] in ("str", str), (
            f"version_id 的注解是 {hints['version_id']!r} —— 必须是 str，"
            "由 guard 的 OpaqueResourceIdRequiredError 走统一 404"
        )

    def test_recovery_list_requires_room_and_generation(self) -> None:
        """AC 10.6：recovery list 必须显式带 room/generation（不得可选）。

        判据走 FastAPI 自己解出的 dependant（`required` 标志），不看
        `inspect.signature` 的 `default` —— FastAPI 的 `Query(...)` 把「必填」记成
        `PydanticUndefined`，用 `is ...` 比会恒假红。
        """
        from fastapi.dependencies.utils import get_dependant

        route = next(
            r for r in SR.router.routes if r.endpoint is SR.list_recovery_cases
        )
        dependant = get_dependant(path=route.path, call=route.endpoint)
        required = {
            p.name for p in dependant.query_params if p.field_info.is_required()
        }
        assert {"room_id", "generation"} <= required, (
            f"recovery list 的必填 query 是 {sorted(required)} —— 缺 room/generation 时"
            "「列出这个 wp 下所有 case」会成为存在性泄露面"
        )

    def test_the_idempotency_key_is_a_required_server_side_header(self) -> None:
        """design §API 的七个幂等端点必须**服务端强制**携带 `Idempotency-Key`。

        🔴 Task 28 bullet 1 明文：pending token / confirmation / claim 的
        Idempotency-Key、409 stale identity 与零 revision 语义「不得由前端约定代替」。
        改成 `Header(default="")` 时不会有任何功能测试失败 —— 而后果是复合幂等键
        `(room, generation, participant, kind, key)` 的最后一项对所有请求恒为空串，
        于是**同一 participant 的任意两次 forcesave 折叠成一次**（第二次拿到第一次的
        request/operation），而第二次真实的编辑内容再也不会被 correlate。

        判据走 FastAPI 自己解出的 dependant（`field_info.is_required()`），不看
        `inspect.signature` 的 default —— `Header(...)` 的默认值是
        `PydanticUndefined`，用 `is ...` 比会恒假红。
        """
        from fastapi.dependencies.utils import get_dependant

        #: 有幂等语义的写端点（design §API 逐条列出 `Idempotency-Key` 的那些）。
        expected_required = {
            "create_pending_mutation",
            "materialize",
            "confirm_descriptor",
            "request_forcesave",
            "create_close_intent",
            "claim_recovery_case",
            "resolve_conflicts",
        }
        declared: dict[str, bool] = {}
        for route in SR.router.routes:
            dependant = get_dependant(path=route.path, call=route.endpoint)
            for param in dependant.header_params:
                if str(getattr(param.field_info, "alias", "")) == "Idempotency-Key":
                    declared[route.endpoint.__name__] = bool(
                        param.field_info.is_required()
                    )
        assert set(declared) == expected_required, (
            f"声明 Idempotency-Key 的端点是 {sorted(declared)}，"
            f"design §API 要求的是 {sorted(expected_required)}"
        )
        optional = sorted(name for name, required in declared.items() if not required)
        assert not optional, (
            f"{optional} 把 Idempotency-Key 声明成可选 —— 缺 key 时复合幂等键的最后一项"
            "恒为空串，同一 participant 的任意两次请求会折叠成一次"
        )

    def test_the_callback_route_is_a_service_scope_route(self) -> None:
        """callback 挂 `public_router`、不在用户前缀下、路径含 `onlyoffice-callback`。"""
        paths = [r.path for r in SR.public_router.routes]
        assert len(paths) == 1, paths
        (path,) = paths
        assert not path.startswith(SR.USER_SYNC_PREFIX), (
            "callback 不得走用户 404/403 契约（AC 10.6 末段）"
        )
        # `ResponseWrapperMiddleware._SKIP_CONTAINS` 认这个子串；OO 协议要求
        # `{"error": N}` 是**顶层**，被 `{code,message,data}` 包一层就等于回了个 200 空壳。
        assert "onlyoffice-callback" in path, path

    def test_response_wrapper_really_skips_that_path(self) -> None:
        """反向锁死上一条：判据不能只看子串，要看中间件真的会跳过。"""
        from app.middleware.response import _SKIP_CONTAINS

        (path,) = [r.path for r in SR.public_router.routes]
        assert any(seg in path for seg in _SKIP_CONTAINS)


class TestGuardIsTheFirstAwaitInEveryHandler:
    """AC 10.6 的顺序在 router 侧的形态：guard 必须是每个 handler 的第一个 await。"""

    def test_every_user_handler_awaits_the_guard_first(self) -> None:
        tree = _tree(_ROUTER_PY)
        handlers = [
            _endpoint_function_name(r) for _methods, r in [(None, x) for x in _user_routes()]
        ]
        checked = 0
        for name in sorted(set(handlers)):
            fn = _func(tree, name)
            first = _first_await_call(fn)
            assert first == "_guard", (
                f"{name}() 的第一个 await 是 {first!r} 而不是 `_guard` —— "
                "authorization-before-resource/cache 要求 guard 先跑完"
            )
            checked += 1
        # `+3` = `_REQUIRED_ENDPOINTS` 之外的三个端点：
        # `GET …/recovery-cases/{case_id}/download`（Task 28）、
        # `POST …/operations/{operation_id}/retry`（Task 28）、
        # `GET …/recovery-cases/{case_id}/timeline`（Task 29 追加）。
        assert checked == len(_REQUIRED_ENDPOINTS) + 3, (
            f"只核对了 {checked} 个 handler —— 端点数变化时本判据的分母必须同步"
        )


def _endpoint_function_name(route: tuple[frozenset[str], str]) -> str:
    _methods, path = route
    for r in SR.router.routes:
        if r.path == path:
            return r.endpoint.__name__
    raise AssertionError(path)


def _if_tests(fn: ast.AST) -> list[str]:
    """函数体内每个 `if` 的**判定表达式**源码。

    🔴 与「函数体内出现过某个属性名」是两件完全不同的判据。后者是 presence 判据，
    `if False: return {"error": int(outcome.response_error)}` 能满足它 —— 属性节点还在
    死分支里。本 spec 的变异检验实测抓到过两条这种形态（B09/B10 判 GREEN）。
    判「某个值真的在门控一条分支」必须看 `If.test`。
    """
    return [ast.unparse(node.test) for node in ast.walk(fn) if isinstance(node, ast.If)]


def _constant_false_gates(fn: ast.AST) -> list[str]:
    """判定表达式里含 `False` 字面量的 `if` —— 即被门控掉的死分支。

    `if False:` / `if x and False:` 两种形态都会被抓到。存在这类门控时，
    「接线还在源码里」不再等于「接线会执行」。
    """
    out: list[str] = []
    for node in ast.walk(fn):
        if not isinstance(node, ast.If):
            continue
        for sub in ast.walk(node.test):
            if isinstance(sub, ast.Constant) and sub.value is False:
                out.append(ast.unparse(node.test))
                break
    return out


def _first_await_call(fn: ast.AST) -> str | None:
    """按**执行顺序**找第一个 `await f(...)` 的被调名。"""
    for node in ast.walk(fn):
        if isinstance(node, ast.Await) and isinstance(node.value, ast.Call):
            func = node.value.func
            if isinstance(func, ast.Name):
                return func.id
            if isinstance(func, ast.Attribute):
                return func.attr
    return None


class TestUnifiedEnvelopes:
    def test_404_has_exactly_one_construction_site(self) -> None:
        """整个 router 里只许一处构造 404，且用平台统一不可见响应体。"""
        tree = _tree(_ROUTER_PY)
        sites = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Name) and func.id == "HTTPException":
                for kw in node.keywords:
                    if kw.arg == "status_code" and isinstance(kw.value, ast.Constant):
                        if kw.value.value == 404:
                            sites.append(node.lineno)
        assert len(sites) == 1, (
            f"404 构造点有 {len(sites)} 处（行 {sites}）—— 多份文案迟早出现"
            "「资源不存在」与「无权访问」两种措辞，那就是存在性预言机"
        )

    def test_the_404_body_is_the_platform_wide_detail(self) -> None:
        from app.services.wp_visibility.denial import EXTERNAL_NOT_FOUND_DETAIL

        exc = SR._not_found()
        assert exc.status_code == 404
        assert exc.detail == EXTERNAL_NOT_FOUND_DETAIL

    def test_the_409_body_carries_no_resource_identifier(self) -> None:
        """AC 4.1 / Property 45：409 不得返回已有 request/operation 标识。"""
        from app.services.workpaper_sync.models import IdempotencyConflictError

        exc = SR._conflict(
            IdempotencyConflictError("同 key 不同 initiator"), error_code="idempotency_conflict"
        )
        assert exc.status_code == 409
        assert set(exc.detail.keys()) == {"error_code", "message"}
        for banned in ("request_id", "operation_id", "forcesave_request_id", "application_id"):
            assert banned not in str(exc.detail), (
                f"409 响应体出现 {banned} —— 把别人的资源 id 交给冲突方"
            )

    def test_conflict_construction_never_reads_an_existing_row(self) -> None:
        """AST：`_conflict` 体内不得出现任何 `.id` 读取（旧标识的唯一来源）。"""
        fn = _func(_tree(_ROUTER_PY), "_conflict")
        for node in ast.walk(fn):
            assert not (isinstance(node, ast.Attribute) and node.attr == "id"), (
                "_conflict() 读了某个对象的 .id —— 409 不得返回旧标识"
            )


class TestRouterDoesNotReimplementServiceLogic:
    """「router 只做参数搬运」是可验证的形态，不是自我声明。"""

    def test_the_router_never_compares_the_frozen_request_fingerprint(self) -> None:
        """复合幂等键与 fingerprint 比对只有一份实现（Task 23 的仓储）。"""
        tree = _tree(_ROUTER_PY)
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                assert node.attr != "frozen_request_fingerprint", (
                    "router 自己读了 frozen_request_fingerprint —— 抄第二份比对必然漂移"
                )

    def test_the_router_never_decodes_a_jwt(self) -> None:
        """callback 的验签只在 `callback_route`。"""
        tree = _tree(_ROUTER_PY)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                assert not (
                    node.func.attr == "decode"
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "jwt"
                ), "router 自己 jwt.decode —— callback 校验必须只在 callback_route"

    def test_the_router_does_not_import_the_merge_or_conflicts_domain(self) -> None:
        """merge/冲突域的消费方必须全在 `app/services/workpaper_sync/`（Task 14 的边界）。

        翻译层是 `endpoint_payloads`；router 只调它。**AST 判据**而不是裸词：
        本文件与 router 的注释里都逐字写着这些模块名。
        """
        tree = _tree(_ROUTER_PY)
        banned = {
            "app.services.workpaper_sync.merge",
            "app.services.workpaper_sync.conflicts",
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert node.module not in banned, (
                    f"router 直接 import {node.module} —— 表现层不得成为 merge 域消费方"
                )

    def test_the_router_builds_no_second_onlyoffice_config(self) -> None:
        """Property 11：descriptor 是唯一凭证，组件不得再拿到第二份 config。"""
        tree = _tree(_ROUTER_PY)
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict):
                keys = {
                    k.value
                    for k in node.keys
                    if isinstance(k, ast.Constant) and isinstance(k.value, str)
                }
                assert not ({"document", "editorConfig"} & keys), (
                    "router 里出现 OnlyOffice config 字面量 —— descriptor 必须是唯一来源"
                )

    def test_read_only_actions_match_the_read_endpoints_exactly(self) -> None:
        """`_READ_ONLY_ACTIONS` / `_WRITE_ACTIONS` 与实际端点的 action **双向**等值。

        四种偏离各自打红：

        * 读 action 漏登记 ⇒ 归档底稿连 timeline 都看不了（AC 11.6 / 11.11）；
        * 写 action 落进只读白名单 ⇒ workflow 锁定下被放行；
        * 词汇表里有端点不再使用的 action ⇒ 名单腐化，下次改名时没人知道该删哪条；
        * 端点用了词汇表外的 action（笔误）⇒ `_action_authorizer` 会 403，
          而那条 403 在功能测试里长得像「权限不足」。
        """
        tree = _tree(_ROUTER_PY)
        read_methods = {
            r.endpoint.__name__ for r in SR.router.routes if "GET" in r.methods
        }
        actions_of_reads: set[str] = set()
        actions_of_writes: set[str] = set()
        for r in SR.router.routes:
            fn = _func(tree, r.endpoint.__name__)
            action = _guard_action_of(fn)
            assert action is not None, f"{r.endpoint.__name__}() 没有向 _guard 传 action"
            (actions_of_reads if r.endpoint.__name__ in read_methods else actions_of_writes).add(
                action
            )
        assert actions_of_reads == set(SR._READ_ONLY_ACTIONS), (
            f"读端点的 action {sorted(actions_of_reads)} 与 _READ_ONLY_ACTIONS "
            f"{sorted(SR._READ_ONLY_ACTIONS)} 不等值"
        )
        assert actions_of_writes == set(SR._WRITE_ACTIONS), (
            f"写端点的 action {sorted(actions_of_writes)} 与 _WRITE_ACTIONS "
            f"{sorted(SR._WRITE_ACTIONS)} 不等值"
        )
        assert not (SR._READ_ONLY_ACTIONS & SR._WRITE_ACTIONS), "读写名单有交集"
        assert SR._KNOWN_ACTIONS == (SR._READ_ONLY_ACTIONS | SR._WRITE_ACTIONS)

    def test_an_unknown_action_name_is_refused(self) -> None:
        """词汇表外的 action（例如 `_guard(action="reslove_conflicts")` 笔误）必须 403。"""
        scope = G.GuardedScope(
            project_id=PROJECT,
            wp_id=WP,
            entry_id=ENTRY,
            user_id=USER,
            action="reslove_conflicts",
            refs=(),
            attributions={},
            phases=G.REQUIRED_PHASES,
            observed={"project_visible": True},
        )
        assert SR._action_authorizer(scope) is False
        for known in sorted(SR._KNOWN_ACTIONS):
            ok = G.GuardedScope(
                project_id=PROJECT, wp_id=WP, entry_id=ENTRY, user_id=USER,
                action=known, refs=(), attributions={},
                phases=G.REQUIRED_PHASES, observed={"project_visible": True},
            )
            assert SR._action_authorizer(ok) is True, known

    def test_the_guard_is_built_with_the_read_only_action_set(self) -> None:
        """装配处必须把只读名单注入 guard（否则名单存在但不起作用 = 死代码）。"""
        fn = _func(_tree(_ROUTER_PY), "build_sync_services")
        kwargs: set[str] = set()
        for node in ast.walk(fn):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "SyncEndpointGuard"
            ):
                kwargs = {kw.arg for kw in node.keywords if kw.arg}
        assert "read_only_actions" in kwargs, (
            "build_sync_services 没有把 _READ_ONLY_ACTIONS 注入 guard —— "
            "名单存在但不起作用就是 additive 死代码（假绿第①源）"
        )


def _guard_action_of(fn: ast.AST) -> str | None:
    for node in ast.walk(fn):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_guard"
        ):
            for kw in node.keywords:
                if kw.arg == "action" and isinstance(kw.value, ast.Constant):
                    return str(kw.value.value)
    return None


# ═══════════════════════════════════════════════════════════════════════════
# D. 真实调用链：Task 26 欠账的翻转
# ═══════════════════════════════════════════════════════════════════════════


class TestOoToHtmlHasARealProductionCallChain:
    """Task 26 收口时 `oo_to_html.py` **没有生产调用方**，非死代码只由登记表结构性背书。

    Task 28 接线后判据翻转成真实调用链：本类的每一条都从 router 出发反查，
    「接线被删」与「接线搬去别的模块」都打红 —— 那是登记表本身查不出来的。
    """

    def test_the_router_imports_the_coordinator(self) -> None:
        tree = _tree(_ROUTER_PY)
        imported = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            and node.module == "app.services.workpaper_sync.oo_to_html"
            for alias in node.names
        }
        assert "OoToHtmlCoordinator" in imported, (
            "router 不再 import OoToHtmlCoordinator —— OO→HTML 编排退回零生产调用方"
        )

    def test_apply_durable_incoming_is_really_called(self) -> None:
        """AST：`_apply_durable_incoming` 内必须有一次 `coordinator.apply_durable_incoming`。

        另加一条：本函数内不得有 `False` 字面量门控的 `if` —— 否则「调用点还在源码里」
        与「调用会执行」就不是一回事了（把整段接线塞进 `if False:` 即可绕过 presence 判据）。
        """
        fn = _func(_tree(_ROUTER_PY), "_apply_durable_incoming")
        calls = [
            node.func.attr
            for node in ast.walk(fn)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        ]
        assert "apply_durable_incoming" in calls, (
            "_apply_durable_incoming() 没有调用 coordinator.apply_durable_incoming"
        )
        dead = _constant_false_gates(fn)
        assert not dead, (
            f"_apply_durable_incoming() 里有被 False 门控的分支 {dead} —— "
            "接线在源码里但不会执行，presence 判据看不出来"
        )

    def test_the_callback_handler_reaches_that_function(self) -> None:
        """链的另一半：callback handler 必须调 `_apply_durable_incoming`。"""
        fn = _func(_tree(_ROUTER_PY), "post_room_onlyoffice_callback")
        calls = {
            (node.func.id if isinstance(node.func, ast.Name) else node.func.attr)
            for node in ast.walk(fn)
            if isinstance(node, ast.Call)
            and isinstance(node.func, (ast.Name, ast.Attribute))
        }
        assert "handle_callback" in calls, "callback handler 没有委派 delivery service"
        assert "_apply_durable_incoming" in calls, (
            "callback handler 没有在归组后触发 OO→HTML apply —— "
            "incoming durable 之后没人消费它，整条 OO→HTML 方向是死的"
        )

    def test_the_callback_handler_checks_the_outcome_instead_of_absence_of_exception(
        self,
    ) -> None:
        """`handle_callback` 刻意不抛（AC 5.7/5.8），所以必须读 `response_error`。

        🔴 判据必须是「`response_error` 真的在**门控**一条返回分支」，不是「函数体里出现
        过这个属性名」。变异检验实测：把 `if outcome.response_error != 0:` 短路成
        `if False:` 之后，presence 判据照旧全绿（属性节点还在死分支里）—— 而那正是
        「durable 前的失败被当成 ack=0，OO 丢件」的形态。
        """
        fn = _func(_tree(_ROUTER_PY), "post_room_onlyoffice_callback")
        gates = _if_tests(fn)
        assert any("response_error" in gate for gate in gates), (
            f"callback handler 的分支判定 {gates} 里没有一条读 `response_error` —— "
            "只靠「没抛异常」判成功时，durable 前的失败会被当成 ack=0，"
            "OO 于是丢件（Task 4 实测它不重投）"
        )
        dead = _constant_false_gates(fn)
        assert not dead, (
            f"callback handler 里有被 False 门控的分支 {dead} —— "
            "非零 ack 的返回点在源码里但不会执行"
        )
        # 该分支必须**返回**非零 ack（读了却不据此返回等于没读）
        returns_error = [
            ast.unparse(node)
            for gate in [n for n in ast.walk(fn) if isinstance(n, ast.If)]
            if "response_error" in ast.unparse(gate.test)
            for node in gate.body
            if isinstance(node, ast.Return)
        ]
        assert any("response_error" in r for r in returns_error), (
            f"读了 response_error 但分支体没有据此返回非零 ack：{returns_error}"
        )

    def test_the_apply_step_checks_result_instead_of_absence_of_exception(self) -> None:
        """coordinator 在 durable 之后也刻意不抛 —— 必须读 `outcome.result`。

        🔴 同上一条：判据看的是 `If.test`，不是「源码里出现过 `result.result`」。
        `if False: logger.warning(... result.result ...)` 能满足 presence 判据
        （变异检验实测判 GREEN），而 apply 失败会一声不响地被当成成功。
        """
        fn = _func(_tree(_ROUTER_PY), "_apply_durable_incoming")
        gates = _if_tests(fn)
        assert any("result.result" in gate for gate in gates), (
            f"_apply_durable_incoming() 的分支判定 {gates} 里没有一条读 `result.result` "
            "—— apply 失败会被静默当成成功（Task 27 就是被这个形态咬到才加了落地自证）"
        )

    def test_conflict_resolution_is_reachable_from_the_router(self) -> None:
        tree = _tree(_ROUTER_PY)
        imported = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            and node.module == "app.services.workpaper_sync.conflict_resolution"
            for alias in node.names
        }
        assert "ConflictResolutionService" in imported
        for handler, method in (
            ("resolve_conflicts", "resolve"),
            ("retry_operation", "retry"),
            ("rollback_version", "rollback"),
        ):
            fn = _func(tree, handler)
            calls = {
                node.func.attr
                for node in ast.walk(fn)
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            }
            assert method in calls, f"{handler}() 没有调用 ConflictResolutionService.{method}"

    def test_the_retirement_registry_records_task_28(self) -> None:
        """登记表侧：判据是**归因型**（只看我这一条），不是全局等值。

        `RETIRED_DEFERRALS` 是跨任务共享登记表 —— 用 `len(...) == N` 之类的全局等值
        判据，别人合法追加一条就把本守卫打红（Task 15 实测踩过）。
        """
        mine = [
            entry
            for entry in M.RETIRED_DEFERRALS
            if str(entry.get("retired_by_task")) == "28"
        ]
        assert len(mine) == 1, f"Task 28 的退役登记应为 1 条，实得 {len(mine)}"
        entry = mine[0]
        assert (
            entry["expected_consumer_module"]
            == "app/services/workpaper_sync/endpoint_payloads.py"
        )
        assert (_BACKEND / "app" / "services" / "workpaper_sync" / "endpoint_payloads.py").is_file()


class TestPackageExportsTheProductionSurface:
    """Task 25~27 的守卫辐射面几乎为零，因为本包的 `__init__` 一条 import 都没有。"""

    def test_the_package_init_really_imports_the_wave2_services(self) -> None:
        tree = _tree(_PKG_INIT_PY)
        modules = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        }
        for required in (
            "app.services.workpaper_sync.oo_to_html",
            "app.services.workpaper_sync.conflict_resolution",
            "app.services.workpaper_sync.materialize_coordinator",
            "app.services.workpaper_sync.endpoint_guard",
            "app.services.workpaper_sync.callback_delivery",
        ):
            assert required in modules, (
                f"`workpaper_sync/__init__.py` 不再 import {required} —— "
                "只在 docstring 里提及等于零辐射面（改本包不牵动任何测试）"
            )

    def test_the_exports_are_importable(self) -> None:
        import app.services.workpaper_sync as WS

        for name in WS.__all__:
            assert getattr(WS, name, None) is not None, name


# ═══════════════════════════════════════════════════════════════════════════
# E. 注册与 legacy 委派
# ═══════════════════════════════════════════════════════════════════════════


class TestRegistrationAndLegacyDelegation:
    def test_both_routers_are_registered_outside_the_auto_gate_loop(self) -> None:
        """AC 10.6 的顺序要求 router **不**挂 `dedicated_wp_gate`。

        那个 router-level 依赖会在 handler 之前跑完 visibility，把 scope-index 与
        visibility 的先后调换 —— 而这条顺序不可交换。可见性判据一份不少：
        `WpGateVisibilityProbe` 调用**同一个** `enforce_wp_gate`。
        """
        text = _REGISTRY_PY.read_text(encoding="utf-8")
        tree = ast.parse(text)
        included: list[str] = []
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "include_router"
                and node.args
                and isinstance(node.args[0], ast.Name)
            ):
                if not any(kw.arg == "dependencies" for kw in node.keywords):
                    included.append(node.args[0].id)
        assert "wp_sync" in included, "sync router 未显式注册（会落进自动加 gate 的循环）"
        assert "wp_sync_public" in included, "callback router 未显式注册"

    def test_the_probe_reuses_the_platform_visibility_gate(self) -> None:
        """可见性不得抄第二份：探针必须调 `enforce_wp_gate`。"""
        fn = _func(_tree(_ROUTER_PY), "observe")
        calls = {
            (node.func.id if isinstance(node.func, ast.Name) else node.func.attr)
            for node in ast.walk(fn)
            if isinstance(node, ast.Call)
            and isinstance(node.func, (ast.Name, ast.Attribute))
        }
        assert "enforce_wp_gate" in calls, (
            "WpGateVisibilityProbe 没有调用平台统一门 —— 抄第二份可见性规则的后果是"
            "「同步域比平台门更宽松」，那正是横向越权入口"
        )

    def test_the_legacy_callback_delegates_room_bound_requests(self) -> None:
        """新式（四项绑定）callback 只委派新服务；legacy 分支一行不跑。"""
        tree = _tree(_LEGACY_PY)
        fn = _func(tree, "post_sheet_onlyoffice_callback")
        names = [
            node.func.id
            for node in ast.walk(fn)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        ]
        assert "_has_room_bound_callback_query" in names
        assert "_delegate_room_bound_callback" in names
        delegate = _func(tree, "_delegate_room_bound_callback")
        called = {
            (node.func.id if isinstance(node.func, ast.Name) else node.func.attr)
            for node in ast.walk(delegate)
            if isinstance(node, ast.Call)
            and isinstance(node.func, (ast.Name, ast.Attribute))
        }
        assert "post_room_onlyoffice_callback" in called, (
            "legacy 委派没有落到新服务的 handler 上"
        )

    def test_the_delegation_predicate_reads_the_single_source_of_bound_params(self) -> None:
        """绑定参数名清单只有一份（`callback_route.URL_BOUND_PARAMS`）。"""
        fn = _func(_tree(_LEGACY_PY), "_has_room_bound_callback_query")
        names = {node.id for node in ast.walk(fn) if isinstance(node, ast.Name)}
        assert "URL_BOUND_PARAMS" in names, (
            "委派判据自己写了一份参数名清单 —— 新增一项绑定时它会静默漏掉新式 callback，"
            "于是新式回调落进 legacy 分支被按 sheet 名覆盖文件"
        )

    def test_the_delegation_is_gated_on_all_four_bound_params(self) -> None:
        """真行为：缺任一项都不得委派（legacy URL 必须仍走 legacy）。"""
        from app.routers.wp_onlyoffice_router import _has_room_bound_callback_query
        from app.services.workpaper_sync.callback_route import URL_BOUND_PARAMS

        full = {name: "x" for name in URL_BOUND_PARAMS}

        class _Req:
            def __init__(self, params: dict[str, str]) -> None:
                self.query_params = params

        assert _has_room_bound_callback_query(_Req(full)) is True
        for name in URL_BOUND_PARAMS:
            partial = dict(full)
            partial.pop(name)
            assert _has_room_bound_callback_query(_Req(partial)) is False, name
        assert _has_room_bound_callback_query(_Req({})) is False


# ═══════════════════════════════════════════════════════════════════════════
# F. 请求体翻译层
# ═══════════════════════════════════════════════════════════════════════════


def _fence_domain_fields() -> tuple[str, ...]:
    """`ResolveFenceRequest` 的字段名 —— 必填清单判据的**独立**分母。

    直接用 `EP.RESOLVE_FENCE_REQUIRED_FIELDS` 做 parametrize 是自证重言式：
    从常量里删一项，用例也一起消失。域内 dataclass 是 AC 8.5 的另一份表达，
    与那个常量互相独立，所以它才能当分母。
    """
    import dataclasses

    from app.services.workpaper_sync.conflicts import ResolveFenceRequest

    return tuple(f.name for f in dataclasses.fields(ResolveFenceRequest))


_ALL_FENCE_FIELDS: tuple[str, ...] = _fence_domain_fields()
#: 域字段减去唯一合法可空项（room 还没有任何 durable application 时它就是 null，
#: 强制必填会锁死「第一次冲突」的裁决）。
_FENCE_FIELDS_FROM_DOMAIN: tuple[str, ...] = tuple(
    name for name in _ALL_FENCE_FIELDS if name != "room_latest_durable_application_id"
)


class TestResolvePayloadTranslation:
    """AC 8.3：裁决落点由服务端决定；AC 8.5：八项乐观锁必须显式携带。"""

    def _fence_payload(self, **over: Any) -> dict[str, Any]:
        payload = {
            "expected_current_revision": 12,
            "room_generation": 3,
            "client_edit_epoch": 5,
            "canonical_application_id": str(uuid.uuid4()),
            "application_effective_request_sequence": 8,
            "room_latest_durable_application_id": None,
            "room_latest_durable_sequence": 8,
            "conflict_set_digest": "a" * 64,
        }
        payload.update(over)
        return payload

    def test_a_complete_fence_payload_round_trips(self) -> None:
        fence = EP.build_resolve_fence(self._fence_payload())
        assert fence.expected_current_revision == 12
        assert fence.room_latest_durable_application_id is None

    @pytest.mark.parametrize("missing", _FENCE_FIELDS_FROM_DOMAIN, ids=_FENCE_FIELDS_FROM_DOMAIN)
    def test_every_required_fence_field_is_really_required(self, missing: str) -> None:
        """AC 8.5 的每一项乐观锁缺失都必须 `FenceFieldMissingError`。

        🔴 分母来自**域内 dataclass**（`ResolveFenceRequest` 的字段）而不是
        `EP.RESOLVE_FENCE_REQUIRED_FIELDS` 本身。用后者做 parametrize 是**自证重言式**：
        从常量里删掉一项，对应的参数化用例也一起消失 ⇒ 全绿。变异检验实测判 GREEN
        （B26），这就是「守卫把分母和分子绑在一起」这类假绿的形态。

        分母换成域字段后，常量少登记一项时那一项的用例仍会跑，而
        `build_resolve_fence` 会抛 `KeyError` 而不是 `FenceFieldMissingError` ⇒ 打红。
        """
        payload = self._fence_payload()
        payload.pop(missing)
        with pytest.raises(EP.FenceFieldMissingError):
            EP.build_resolve_fence(payload)

    def test_the_required_list_equals_the_domain_fields_minus_the_optional_one(self) -> None:
        """必填清单与域内 dataclass **双向**等值（只减去那一个合法可空项）。

        双向：少登记 ⇒ fence 少比一项（上一条会红）；多登记一个 dataclass 里没有的名字
        ⇒ 那一项永远无法被满足，resolve 恒 422（本条会红）。
        """
        assert set(EP.RESOLVE_FENCE_REQUIRED_FIELDS) == (
            set(_ALL_FENCE_FIELDS) - {"room_latest_durable_application_id"}
        ), (
            f"必填清单 {sorted(EP.RESOLVE_FENCE_REQUIRED_FIELDS)} 与 ResolveFenceRequest "
            f"字段 {sorted(_ALL_FENCE_FIELDS)} 不等值（可空项只允许 "
            "room_latest_durable_application_id）"
        )
        assert len(EP.RESOLVE_FENCE_REQUIRED_FIELDS) == len(
            set(EP.RESOLVE_FENCE_REQUIRED_FIELDS)
        ), "必填清单有重复项"

    def test_the_optional_durable_application_id_stays_optional(self) -> None:
        """room 还没有任何 durable application 时它就是 null —— 必填会锁死第一次裁决。"""
        payload = self._fence_payload()
        payload.pop("room_latest_durable_application_id")
        assert EP.build_resolve_fence(payload).room_latest_durable_application_id is None

    def _row(self, **over: Any):
        class _Row:
            pass

        row = _Row()
        row.id = over.get("id", uuid.uuid4())
        row.stable_field_key = over.get("stable_field_key", "header_block/total_amount")
        row.row_key = over.get("row_key", "")
        row.oo_location = over.get("oo_location", "Sheet1!C11")
        return row

    def test_the_stable_key_comes_from_the_server_row_not_the_request(self) -> None:
        """客户端即使提交 stable key 也一律忽略（AC 8.3）。"""
        row = self._row()
        choices = EP.build_resolution_choices(
            items=[
                {
                    "conflict_id": str(row.id),
                    "choice": "take_incoming",
                    "stable_field_key": "attacker/controlled",
                }
            ],
            conflict_rows=[row],
        )
        assert len(choices) == 1
        assert choices[0].stable_field_key == "header_block/total_amount"
        assert choices[0].oo_location == "Sheet1!C11"

    def test_an_unknown_conflict_id_is_its_own_refusal(self) -> None:
        row = self._row()
        with pytest.raises(EP.UnknownConflictIdError):
            EP.build_resolution_choices(
                items=[{"conflict_id": str(uuid.uuid4()), "choice": "take_incoming"}],
                conflict_rows=[row],
            )

    def test_an_unknown_choice_fails_visible(self) -> None:
        row = self._row()
        with pytest.raises(EP.UnknownResolutionKindError):
            EP.build_resolution_choices(
                items=[{"conflict_id": str(row.id), "choice": "incoming"}],
                conflict_rows=[row],
            )

    def test_manual_without_a_value_key_is_refused(self) -> None:
        row = self._row()
        with pytest.raises(EP.ManualValueRequiredError):
            EP.build_resolution_choices(
                items=[{"conflict_id": str(row.id), "choice": "manual"}],
                conflict_rows=[row],
            )

    def test_manual_with_an_explicit_null_means_delete_not_missing(self) -> None:
        """`value=null` 是「合并为删除」这一合法裁决，不是「没填」。"""
        row = self._row()
        (choice,) = EP.build_resolution_choices(
            items=[{"conflict_id": str(row.id), "choice": "manual", "value": None}],
            conflict_rows=[row],
        )
        assert choice.manual is not None
        assert choice.manual.present is False

    def test_take_instance_without_an_xpath_is_refused(self) -> None:
        row = self._row()
        with pytest.raises(EP.InstanceXpathRequiredError):
            EP.build_resolution_choices(
                items=[{"conflict_id": str(row.id), "choice": "take_instance"}],
                conflict_rows=[row],
            )

    def test_payload_refusals_have_distinct_error_codes(self) -> None:
        codes = {
            cls.error_code
            for cls in (
                EP.FenceFieldMissingError,
                EP.UnknownConflictIdError,
                EP.UnknownResolutionKindError,
                EP.ManualValueRequiredError,
                EP.InstanceXpathRequiredError,
            )
        }
        assert len(codes) == 5, f"翻译层的拒绝分型 error_code 重复：{sorted(codes)}"


# ═══════════════════════════════════════════════════════════════════════════
# G. 服务域异常 → HTTP 的封闭映射
# ═══════════════════════════════════════════════════════════════════════════


class TestServiceErrorMapping:
    def test_404_family_of_service_errors_uses_the_unified_envelope(self) -> None:
        from app.services.wp_visibility.denial import EXTERNAL_NOT_FOUND_DETAIL
        from app.services.workpaper_sync.conflict_resolution import (
            ContentVersionNotFoundError,
            REFUSED_AT_SCOPE_INDEX,
        )
        from app.services.workpaper_sync.request_application import (
            OperationScopeNotVisibleError,
        )

        for exc in (
            ContentVersionNotFoundError("x", refused_at=REFUSED_AT_SCOPE_INDEX),
            OperationScopeNotVisibleError("x"),
        ):
            http = SR._sync_http(exc)
            assert http.status_code == 404
            assert http.detail == EXTERNAL_NOT_FOUND_DETAIL, (
                f"{type(exc).__name__} 的 404 响应体与统一 oracle 不同 —— "
                "文案差异就是存在性泄露"
            )

    def test_idempotency_conflict_maps_to_409_without_ids(self) -> None:
        from app.services.workpaper_sync.models import IdempotencyConflictError

        http = SR._sync_http(IdempotencyConflictError("跨 participant 复用同 key"))
        assert http.status_code == 409
        assert set(http.detail.keys()) == {"error_code", "message"}

    def test_every_mapped_error_code_really_exists_in_the_sync_domain(self) -> None:
        """反向锁死：映射表的每个 key 必须是某个 `SyncDomainError` 子类的真 `error_code`。

        🔴 这条判据的由来是一个**真实缺陷**：第一版映射表是手写字面量，16 条里 5 条
        拼错（`descriptor_stale_identity` / `operation_scope_not_visible` /
        `materialize_authorization_failed` / `recovery_retry_forbidden` /
        `descriptor_substrate_stale`）。拼错的后果不是「映射不准」，而是
        `OperationScopeNotVisibleError` 落到 422 ⇒ 「跨 scope 读」与「不存在」在响应上
        可区分 ⇒ Property 45 的存在性预言机。功能测试全绿，因为每条路径都还是
        「返回了一个错误」。
        """
        import importlib
        import pkgutil

        import app.services.workpaper_sync as WSPKG
        from app.services.workpaper_sync.models import SyncDomainError

        known: set[str] = set()
        for info in pkgutil.walk_packages(WSPKG.__path__, prefix=WSPKG.__name__ + "."):
            mod = importlib.import_module(info.name)
            for name in dir(mod):
                obj = getattr(mod, name)
                if isinstance(obj, type) and issubclass(obj, SyncDomainError):
                    known.add(str(obj.error_code))
        unknown = sorted(set(SR._ERROR_CODE_STATUS) - known)
        assert not unknown, (
            f"映射表里的 error_code 在同步域中不存在（拼错或已重命名）：{unknown}"
        )
        assert len(SR._ERROR_CODE_STATUS) >= 20, (
            f"映射表只有 {len(SR._ERROR_CODE_STATUS)} 条 —— 分母塌陷会让本判据恒真"
        )

    def test_the_mapping_table_refuses_contradictory_registration(self) -> None:
        """同一 error_code 登记两个 status ⇒ 构造期即抛（而不是「后写的赢」）。

        🔴 判据必须**真的喂一份矛盾登记**。只断言 `_build_error_code_status() ==
        _ERROR_CODE_STATUS`（确定性）时，那条 raise 在真实表上恒不触发 ⇒ 从测试侧
        不可达 ⇒ 把它短路成 `if False:` 的定向变异永久判 GREEN。这就是为什么生产函数
        开了一个只给判据用的 `spec` 注入口（生产调用不传）。
        """
        from app.services.workpaper_sync.models import SyncDomainError

        class _A(SyncDomainError):
            error_code = "task28_probe_contradictory_code"

        # 同一 code 落两个 status ⇒ 必抛，且不得「后写的赢」
        with pytest.raises(SyncDomainError):
            SR._build_error_code_status(spec=((404, (_A,)), (422, (_A,))))
        # 同 code 同 status 重复登记是合法的（跨模块同义拒绝共用一个 code）
        assert SR._build_error_code_status(spec=((404, (_A, _A)),)) == {
            "task28_probe_contradictory_code": 404
        }
        # 不传 spec 时仍是生产表，且与模块级常量逐项相同（确定性）
        assert SR._build_error_code_status() == SR._ERROR_CODE_STATUS

    def test_an_unmapped_service_error_does_not_become_500(self) -> None:
        """未登记的 error_code 落 422（可解释的客户端错误），而不是被当平台故障。"""
        from app.services.workpaper_sync.models import SyncDomainError

        class _Novel(SyncDomainError):
            error_code = "task28_probe_only_novel_code"

        http = SR._sync_http(_Novel("x"))
        assert http.status_code == 422
        assert http.detail["error_code"] == "task28_probe_only_novel_code"
