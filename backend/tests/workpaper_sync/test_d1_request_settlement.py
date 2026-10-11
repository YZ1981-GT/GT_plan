"""D1：application 落终态 ⇒ 绑在它上面的 request 同事务终结（离线守卫）。

修前 `REQUEST_EDGES[correlated]` 登记了 `terminal / superseded / authorization_stale` 三条
出边，但全仓**零生产写入方**。三个消费方都以「request 已终结」为前提：

* participant 主动离开的 in-flight 门（`RoomService._outstanding_request_ids_of`）；
* close barrier 的 predecessor 计数（`reconcile_close_intents` 的 `predecessors_open`）；
* editor destroy 闸（`command_service.classify_editor_destroy` 的 `is_terminal`）。

于是保存成功后 request 永远停在 `correlated`，initiator 离开恒 409
`participant_leave_refused_in_flight`（真库实测：重药安徽 3 次 applied 全如此）。

本文件锁结构与映射；行为（真库、真 apply、折叠 duplicate、supersede、离开前拒后放）在
`test_task26_d1_request_settlement_pg.py::TestD1RequestSettlementOnTerminalApplication`
（采集体 `task26_d1_settlement_world.py`，由 `test_task26_oo_to_html_pg.py` 的同一次真库采集产出）。
"""

from __future__ import annotations

import ast
import asyncio
import inspect
import textwrap
import uuid
from types import SimpleNamespace

import pytest

from app.services.workpaper_sync import models as M
from app.services.workpaper_sync import request_settlement as RS
from app.services.workpaper_sync.oo_to_html import OoToHtmlCoordinator
from app.services.workpaper_sync.repository import WorkpaperSyncRepository

_SETTLE = "settle_requests_of_terminal_application"


def _fn(obj: object) -> ast.FunctionDef | ast.AsyncFunctionDef:
    tree = ast.parse(textwrap.dedent(inspect.getsource(obj)))
    node = tree.body[0]
    assert isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    return node


def _calls(node: ast.AST, name: str) -> list[ast.Call]:
    """`name(...)` 或 `x.name(...)` 两种调用形态都算。"""
    return [
        n
        for n in ast.walk(node)
        if isinstance(n, ast.Call)
        and (
            (isinstance(n.func, ast.Attribute) and n.func.attr == name)
            or (isinstance(n.func, ast.Name) and n.func.id == name)
        )
    ]


def _guarded_by_is_terminal(fn: ast.AST, call: ast.Call, machine: str) -> bool:
    """`call` 是否位于 `if is_terminal("<machine>", …)` 的 body 内。"""
    for node in ast.walk(fn):
        if not isinstance(node, ast.If):
            continue
        tests = [node.test]
        if isinstance(node.test, ast.BoolOp):
            tests = list(node.test.values)
        guarded = any(
            isinstance(t, ast.Call)
            and isinstance(t.func, ast.Name)
            and t.func.id == "is_terminal"
            and t.args
            and isinstance(t.args[0], ast.Constant)
            and t.args[0].value == machine
            for t in tests
        )
        if guarded and any(call is n for stmt in node.body for n in ast.walk(stmt)):
            return True
    return False


# ─────────────────────────────────────────────────────────────────────────
# 一、映射：单源、恰覆盖 application 终态、每条都是登记过的合法边
# ─────────────────────────────────────────────────────────────────────────


class TestTheMappingIsTheSingleSource:
    def test_keys_are_exactly_the_terminal_application_states(self) -> None:
        """新增 application 终态而映射没跟上 ⇒ 结算 fail visible，而不是静默漏一条 request。"""
        assert set(M.REQUEST_STATE_FOR_TERMINAL_APPLICATION) == set(
            M.TERMINAL_STATES["application"]
        )

    @pytest.mark.parametrize(
        "app_state", sorted(M.REQUEST_STATE_FOR_TERMINAL_APPLICATION, key=lambda s: s.value),
        ids=lambda s: s.value,
    )
    def test_each_target_is_a_registered_exit_of_correlated(
        self, app_state: M.ApplicationState
    ) -> None:
        target = M.REQUEST_STATE_FOR_TERMINAL_APPLICATION[app_state]
        assert target in M.REQUEST_EDGES[M.RequestState.correlated], target
        assert M.is_terminal("request", target), target
        M.assert_transition("request", M.RequestState.correlated, target)

    def test_content_landing_states_map_to_terminal(self) -> None:
        mp = M.REQUEST_STATE_FOR_TERMINAL_APPLICATION
        assert mp[M.ApplicationState.applied] is M.RequestState.terminal
        assert mp[M.ApplicationState.refresh_required] is M.RequestState.terminal
        assert mp[M.ApplicationState.superseded] is M.RequestState.superseded
        assert mp[M.ApplicationState.authorization_stale] is M.RequestState.authorization_stale

    @pytest.mark.parametrize(
        "app_state", [M.ApplicationState.conflict, M.ApplicationState.error],
        ids=lambda s: s.value,
    )
    def test_resolvable_states_are_not_settled(self, app_state: M.ApplicationState) -> None:
        """conflict / error 之后裁决或重试仍可能应用内容 ⇒ request 必须保持 open。"""
        assert not M.is_terminal("application", app_state)
        assert app_state not in M.REQUEST_STATE_FOR_TERMINAL_APPLICATION

    def test_correlated_is_still_an_open_state_for_leave(self) -> None:
        """出口补上了，入口语义不变：内容未应用时 in-flight 门照旧拒。"""
        from app.services.workpaper_sync import rooms as RM

        assert M.RequestState.correlated.value in RM._OPEN_REQUEST_STATES


# ─────────────────────────────────────────────────────────────────────────
# 二、结算方法自身
# ─────────────────────────────────────────────────────────────────────────


class TestTheSettlementMethod:
    @pytest.mark.parametrize("state", ["conflict", "error", "queued", "applying"])
    def test_non_terminal_application_is_refused_before_any_io(self, state: str) -> None:
        """session=None：只要碰了 IO 就会 AttributeError —— 抛的必须是状态边错误。"""
        repo = WorkpaperSyncRepository(None)  # type: ignore[arg-type]
        app = SimpleNamespace(id=uuid.uuid4(), state=state, room_id=uuid.uuid4())
        with pytest.raises(M.StateTransitionError, match="不是终态"):
            asyncio.run(RS.settle_requests_of_terminal_application(repo, app))  # type: ignore[arg-type]

    def test_room_is_locked_before_the_requests(self) -> None:
        """锁序 room → request（与撤销路径一致）；反过来与 apply 后段的 room 锁可互等。"""
        fn = _fn(RS.settle_requests_of_terminal_application)
        lock_lines = [c.lineno for c in _calls(fn, "lock_room")]
        update_lines = [c.lineno for c in _calls(fn, "with_for_update")]
        assert lock_lines, "结算前没有锁 room"
        assert update_lines, "request 没有 FOR UPDATE"
        assert min(lock_lines) < min(update_lines), (lock_lines, update_lines)

    def test_both_shell_kinds_are_collected(self) -> None:
        """primary（application_id）与 direct duplicate（duplicate_of_operation_id）都要取。

        判据走 AST 的属性访问而不是源码文本：docstring 里同样写着这些列名，文本匹配会
        被它骗过（删掉真实查询条件仍全绿）。
        """
        fn = _fn(RS.settle_requests_of_terminal_application)
        attrs = {
            (ast.unparse(n.value), n.attr) for n in ast.walk(fn) if isinstance(n, ast.Attribute)
        }
        for needle in (
            ("application", "origin_request_id"),
            ("WorkpaperSyncOperation", "application_id"),
            ("WorkpaperSyncOperation", "duplicate_of_operation_id"),
            ("WorkpaperSyncOperation", "forcesave_request_id"),
        ):
            assert needle in attrs, needle

    def test_already_settled_requests_are_skipped(self) -> None:
        fn = _fn(RS.settle_requests_of_terminal_application)
        names = {
            n.func.id
            for n in ast.walk(fn)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
        }
        assert {"is_terminal", "assert_transition"} <= names, names


# ─────────────────────────────────────────────────────────────────────────
# 三、接线：每个 application 终态写入点都结算
# ─────────────────────────────────────────────────────────────────────────


class TestEveryTerminalWriterSettles:
    def test_coordinator_single_writer_settles_on_terminal(self) -> None:
        """`_advance_application` 是协调器里 application 状态的唯一写入点。"""
        fn = _fn(OoToHtmlCoordinator._advance_application)
        calls = _calls(fn, _SETTLE)
        assert len(calls) == 1, "协调器的 application 终态写入点没有结算 request"
        assert _guarded_by_is_terminal(fn, calls[0], "application"), (
            "结算必须只在落终态时发生（conflict / error 仍可能应用内容）"
        )

    def test_coordinator_writes_application_state_only_there(self) -> None:
        """防「另起一条终态路径绕过结算」：`app.state =` 只允许出现在 `_advance_application`。"""
        src = textwrap.dedent(inspect.getsource(OoToHtmlCoordinator))
        tree = ast.parse(src)
        writers: list[str] = []
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for node in ast.walk(fn):
                if not isinstance(node, ast.Assign):
                    continue
                for tgt in node.targets:
                    if (
                        isinstance(tgt, ast.Attribute)
                        and tgt.attr == "state"
                        and isinstance(tgt.value, ast.Name)
                        and tgt.value.id == "app"
                    ):
                        writers.append(fn.name)
        assert writers == ["_advance_application"], writers

    def test_repository_supersede_settles(self) -> None:
        fn = _fn(WorkpaperSyncRepository.supersede_application)
        assert len(_calls(fn, _SETTLE)) == 1

    def test_operation_finished_at_is_written_on_terminal(self) -> None:
        fn = _fn(OoToHtmlCoordinator._advance_operation)
        assigns = [
            n
            for n in ast.walk(fn)
            if isinstance(n, ast.Assign)
            and any(isinstance(t, ast.Attribute) and t.attr == "finished_at" for t in n.targets)
        ]
        assert assigns, "operation 落终态不写 finished_at"
        guarded = False
        for node in ast.walk(fn):
            if isinstance(node, ast.If) and any(
                a is n for stmt in node.body for n in ast.walk(stmt) for a in assigns
            ):
                test_src = ast.unparse(node.test)
                guarded = 'is_terminal("operation"' in test_src or "is_terminal('operation'" in test_src
        assert guarded, "finished_at 必须只在 operation 终态时写（error 可重试）"


# ─────────────────────────────────────────────────────────────────────────
# 四、触类旁通：其余两条 request 终结路径同样补写 finished_at
# ─────────────────────────────────────────────────────────────────────────


class _FakeSession:
    def __init__(self, rows: list[object] | None = None) -> None:
        self.rows = list(rows or [])
        self.flushes = 0

    async def execute(self, _stmt: object) -> "_FakeSession":
        return self

    def scalars(self) -> "_FakeSession":
        return self

    def all(self) -> list[object]:
        return list(self.rows)

    async def flush(self) -> None:
        self.flushes += 1


class _FakeRepo:
    def __init__(self, session: _FakeSession) -> None:
        self.session = session
        self.events: list[dict[str, object]] = []

    async def append_operation_event(self, **kwargs: object) -> None:
        self.events.append(kwargs)


class TestOtherTerminalPathsStampFinishedAt:
    def test_terminate_without_callback(self) -> None:
        """CS 终态码（no_changes / doc_not_online …）⇒ request `terminal` 且有 finished_at。"""
        from app.services.workpaper_sync.request_application import RequestApplicationService

        repo = _FakeRepo(_FakeSession())
        svc = RequestApplicationService(repo, rooms=object())  # type: ignore[arg-type]
        req = SimpleNamespace(state="frozen", finished_at=None)
        op = SimpleNamespace(
            id=uuid.uuid4(), state="created", error_code=None, error_stage=None, finished_at=None
        )
        asyncio.run(
            svc.terminate_without_callback(
                SimpleNamespace(request=req, operation=op),  # type: ignore[arg-type]
                cs_outcome="no_changes",
            )
        )
        assert req.state == "terminal"
        assert req.finished_at is not None
        assert op.finished_at is not None

    def test_cancel_outstanding_requests_on_revoke(self) -> None:
        """撤销取消 open request ⇒ `superseded` 且有 finished_at。"""
        from app.services.workpaper_sync.rooms import RoomService

        rows = [
            SimpleNamespace(id=uuid.uuid4(), state=s, finished_at=None)
            for s in ("frozen", "correlated")
        ]
        session = _FakeSession(rows)
        svc = RoomService(_FakeRepo(session))  # type: ignore[arg-type]
        room = SimpleNamespace(id=uuid.uuid4(), generation=1)
        cancelled = asyncio.run(svc._cancel_outstanding_requests_locked(room))  # type: ignore[arg-type]
        assert len(cancelled) == 2
        assert [r.state for r in rows] == ["superseded", "superseded"]
        assert all(r.finished_at is not None for r in rows)


# ─────────────────────────────────────────────────────────────────────────
# 五、历史欠账结算工具：不得另写一套规则
# ─────────────────────────────────────────────────────────────────────────


def _load_settle_tool() -> object:
    import importlib.util
    from pathlib import Path

    path = (
        Path(__file__).resolve().parents[2]
        / "scripts" / "fix" / "settle_stranded_forcesave_requests.py"
    )
    spec = importlib.util.spec_from_file_location("_settle_stranded_tool", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestStrandedRequestTool:
    def test_state_sets_are_derived_from_the_state_machine(self) -> None:
        tool = _load_settle_tool()
        open_states = set(tool._OPEN_REQUEST_STATES)  # type: ignore[attr-defined]
        assert open_states == {
            s.value for s in M.RequestState if not M.is_terminal("request", s)
        }
        assert "correlated" in open_states
        assert set(tool._TERMINAL_APPLICATION_STATES) == {  # type: ignore[attr-defined]
            s.value for s in M.TERMINAL_STATES["application"]
        }

    def test_tool_delegates_to_the_production_settlement(self) -> None:
        tool = _load_settle_tool()
        tree = ast.parse(inspect.getsource(tool.run))  # type: ignore[attr-defined]
        assert _calls(tree, _SETTLE), "工具必须调用生产结算方法，不得自写 UPDATE"
        assert not [
            n for n in ast.walk(tree)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and n.func.attr == "update"
        ], "工具里出现了直接 UPDATE"

    def test_linkage_covers_origin_primary_and_duplicate_shells(self) -> None:
        sql = str(_load_settle_tool()._STRANDED_SQL)  # type: ignore[attr-defined]
        for needle in (
            "a.origin_request_id",
            "o.application_id = a.id",
            "d.duplicate_of_operation_id = p.id",
        ):
            assert needle in sql, needle
