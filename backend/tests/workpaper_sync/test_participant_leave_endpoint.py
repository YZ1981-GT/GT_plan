"""participant 主动离开：端点形态 + 「它不是 close-intent」的结构判据（不连库）。

spec: oo-single-pass-materialize-and-room-leave · Requirement 4.1, 4.2, 4.4, 4.5
Properties: **P7**（只改该 participant）/ **P8**（dirty 拒绝）/ **P9**（幂等）

═══ 本文件与 `test_participant_leave_pg.py` 的分工 ═══

* 本文件 —— **形态**判据：路由挂在显式 scope 前缀下、guard 是第一个 await、两个 ref 都
  声明、error_code 的状态码分型、以及「leave 的代码里根本没有那些 close barrier 动作」
  这一类只能靠 AST 证明的事。
* `_pg.py` —— 真库行为：`active/closing → left` 真的落库、room 行逐列未变、其他
  participant 未变、重复 leave 零写入、dirty/in-flight 真的被拒。

═══ 为什么形态判据不可省 ═══

AC 4.1 禁止的是**动作**（不建 request / 不推 barrier / 不旋转 generation）。行为观察只能
证明「这一次没做」：给 `leave_participant` 加一句 `room.close_barrier_epoch += 1`，PG 判据
里若没有恰好比到那一列就照样绿。AST 判据看的是「这段代码有没有对 room 赋值」——
它对「加了但这次没走到」同样红。

判据一律走 AST 而不是裸词：本文件与生产代码的注释里逐字写着 `close_barrier` /
`close_capture` / `generation` 等被禁符号，字符串匹配必然假红（附录 D.3 / G.5 的教训）。
"""
from __future__ import annotations

import ast
import inspect
import textwrap
import uuid
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
_ROUTER_PY = _BACKEND / "app" / "routers" / "wp_sync_router.py"
_ROOMS_PY = _BACKEND / "app" / "services" / "workpaper_sync" / "rooms.py"

import app.routers.wp_sync_router as SR  # noqa: E402
from app.services.workpaper_sync import rooms as RM  # noqa: E402
from app.services.workpaper_sync.models import (  # noqa: E402
    PARTICIPANT_EDGES,
    ParticipantState,
    RequestState,
    ScopeResourceKind,
)
from app.services.workpaper_sync.repository import WorkpaperSyncRepository  # noqa: E402
from app.services.wp_visibility.denial import EXTERNAL_NOT_FOUND_DETAIL  # noqa: E402

#: 本任务加的那一条路由。
LEAVE_SUFFIX = "/rooms/{room_id}/participants/{participant_id}/leave"
LEAVE_HANDLER = "leave_room"
LEAVE_ACTION = "leave_room"


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _func(tree: ast.Module, name: str) -> ast.AsyncFunctionDef | ast.FunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"找不到函数 {name!r}")


def _func_of(obj: object) -> ast.AsyncFunctionDef | ast.FunctionDef:
    """从**运行时对象**取 AST（而不是按名字在文件里找）。

    好处很具体：方法被搬到别的模块 / 改名之后，本判据跟着对象走而不是悄悄找不到。
    """
    src = textwrap.dedent(inspect.getsource(obj))
    tree = ast.parse(src)
    node = tree.body[0]
    assert isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)), type(node)
    return node


def _dotted(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        head = _dotted(node.value)
        return None if head is None else f"{head}.{node.attr}"
    return None


def _first_await(fn: ast.AST) -> str | None:
    for node in ast.walk(fn):
        if isinstance(node, ast.Await) and isinstance(node.value, ast.Call):
            return _dotted(node.value.func)
    return None


def attribute_targets_of(fn: ast.AST) -> set[str]:
    """函数体内**被赋值**的属性目标（`a.b = …` / `a.b += …`），形如 ``"room.state"``。

    只收 `Attribute` 目标：局部变量赋值（`remaining = …`）与本判据无关。
    """
    out: set[str] = set()
    for node in ast.walk(fn):
        targets: list[ast.expr] = []
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
        elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
            targets = [node.target]
        for target in targets:
            if isinstance(target, ast.Attribute):
                dotted = _dotted(target)
                if dotted is not None:
                    out.add(dotted)
    return out


def called_names_of(fn: ast.AST) -> set[str]:
    """函数体内被调用的（点号）名字 —— 含 await 与非 await。"""
    out: set[str] = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Call):
            dotted = _dotted(node.func)
            if dotted is not None:
                out.add(dotted)
    return out


# ═══════════════════════════════════════════════════════════════════════════
# 0. 前提：`left` 在状态机里本来就合法，且是**终态**
# ═══════════════════════════════════════════════════════════════════════════


class TestTheStateMachinePremise:
    """幂等分支为什么必须**显式**，答案在 `PARTICIPANT_EDGES` 里而不是在风格偏好里。"""

    def test_active_and_closing_may_both_reach_left(self) -> None:
        assert ParticipantState.left in PARTICIPANT_EDGES[ParticipantState.active]
        assert ParticipantState.left in PARTICIPANT_EDGES[ParticipantState.closing]

    def test_left_is_terminal_so_assert_transition_can_not_carry_idempotency(self) -> None:
        """`PARTICIPANT_EDGES[left]` 是空集 ⇒ 靠捕获 `assert_transition` 做幂等必然出错。

        这条不是复述实现，它是 design 四末段那句结论的**可执行**形态：空集意味着
        「已 left 再 leave」与「从 revoked/expired 离开」抛的是**同一个**异常，而前者
        必须返回同一结果（AC 4.2）、后者必须拒绝。所以分支只能建立在「先读当前状态」上。
        """
        assert PARTICIPANT_EDGES[ParticipantState.left] == frozenset()
        for illegal in (ParticipantState.revoked, ParticipantState.expired):
            assert ParticipantState.left not in PARTICIPANT_EDGES[illegal], (
                f"{illegal.value} → left 变成合法边了 —— 那会让「被撤销的会话」可以"
                "自己走回一个正常终态，撤销的取证意义就没了"
            )


# ═══════════════════════════════════════════════════════════════════════════
# 1. 路由形态（AC 4.5 的前半：前端打得到）
# ═══════════════════════════════════════════════════════════════════════════


def _leave_route():
    hits = [r for r in SR.router.routes if r.endpoint.__name__ == LEAVE_HANDLER]
    assert len(hits) == 1, f"leave 路由不唯一: {hits}"
    return hits[0]


class TestRouteShape:
    def test_the_route_is_a_post_under_the_explicit_entry_scope_prefix(self) -> None:
        route = _leave_route()
        assert sorted(m for m in route.methods if m not in ("HEAD", "OPTIONS")) == ["POST"]
        assert route.path == SR.USER_SYNC_PREFIX + LEAVE_SUFFIX, route.path
        # 三段显式 scope 都在路径里（AC 10.5：不得从 room/participant 反推归属）。
        for segment in ("{project_id}", "{wp_id}", "{entry_id:path}"):
            assert segment in route.path

    def test_a_real_slashed_entry_id_routes_to_it(self) -> None:
        """行为侧：真实（四段）entry_id 必须唯一命中并解出原值。

        形态判据（路径模板长得对）在默认转换器 `[^/]+` 下也成立，而那时端点在生产上
        **恒 404**（Task 28 的 B01 变异已证），所以必须落到路由匹配上。
        """
        project, wp = uuid.uuid4(), uuid.uuid4()
        room, participant = uuid.uuid4(), uuid.uuid4()
        entry = "xlsx/d4/analysis/d4-tab-customer-price"
        path = (
            f"/api/projects/{project}/workpapers/{wp}/sync/entries/{entry}"
            f"/rooms/{room}/participants/{participant}/leave"
        )
        scope = {"type": "http", "method": "POST", "path": path, "headers": []}
        hits = []
        for route in SR.router.routes:
            match, child = route.matches(scope)
            if match.name == "FULL":
                hits.append((route.endpoint.__name__, child.get("path_params", {})))
        assert len(hits) == 1, f"{path} 命中 {hits}"
        name, params = hits[0]
        assert name == LEAVE_HANDLER
        assert params["entry_id"] == entry, (
            f"贪婪匹配把后缀吞进了 entry_id: {params['entry_id']!r}"
        )
        assert str(params["room_id"]) == str(room)
        assert str(params["participant_id"]) == str(participant)

    def test_it_is_a_write_action_and_not_in_the_read_only_whitelist(self) -> None:
        assert LEAVE_ACTION in SR._WRITE_ACTIONS
        assert LEAVE_ACTION not in SR._READ_ONLY_ACTIONS
        assert LEAVE_ACTION in SR._KNOWN_ACTIONS
        # 未登记的 action 名一律 403（fail closed）—— 顺手证明词汇表真的在起作用。
        assert SR._action_authorizer(
            type("S", (), {"action": "leave_rooom"})()
        ) is False

    def test_it_declares_no_idempotency_key_header(self) -> None:
        """幂等来自**终态**而不是键：声明一个没人用来合并请求的必填 header 是误导。

        判据读生成的 contract（前端据它决定要不要强制发 header），而不是读 handler 签名
        —— 前端看到的就是那份生成物。
        """
        import json

        generated = (
            _REPO
            / "audit-platform"
            / "frontend"
            / "src"
            / "components"
            / "workpaper"
            / "sync"
            / "workpaperSyncContract.generated.ts"
        ).read_text(encoding="utf-8")
        raw = generated.split("WP_SYNC_ROUTES", 1)[1]
        raw = raw[raw.index("[") : raw.index("] as const")] + "]"
        routes = json.loads(raw)
        row = next(r for r in routes if r["endpoint"] == LEAVE_HANDLER)
        assert row["method"] == "POST"
        assert row["suffix"] == LEAVE_SUFFIX
        assert row["idempotencyKey"] == "absent", row


# ═══════════════════════════════════════════════════════════════════════════
# 2. authorization-first + 404 oracle（AC 4.2）
# ═══════════════════════════════════════════════════════════════════════════


class TestAuthorizationFirst:
    def test_guard_is_the_first_await_in_the_handler(self) -> None:
        fn = _func(_tree(_ROUTER_PY), LEAVE_HANDLER)
        assert _first_await(fn) == "_guard", (
            f"第一个 await 是 {_first_await(fn)!r} —— 先读业务行再授权会让 404/403 的时序"
            "泄露对象存在性"
        )

    def test_both_the_room_and_the_participant_are_declared_refs(self) -> None:
        """两个 ref 都过 scope index 的「同 project/wp/entry」交叉比对（guard 阶段 ③）。

        只声明 room 时，「拿别处的 participant_id 配自己可见的 room」一路走到 service ——
        那时 404 oracle 只剩 service 归属判据一条腿。
        """
        fn = _func(_tree(_ROUTER_PY), LEAVE_HANDLER)
        kinds: set[str] = set()
        for node in ast.walk(fn):
            if isinstance(node, ast.Call) and _dotted(node.func) == "declared_refs":
                for sub in ast.walk(node):
                    dotted = _dotted(sub)
                    if dotted and dotted.startswith("ScopeResourceKind."):
                        kinds.add(dotted.split(".", 1)[1])
        assert kinds == {"room", "participant"}, kinds
        # 两个 kind 都真的在枚举里（抄错名字会让 `declared_refs` 拿到 AttributeError）。
        assert ScopeResourceKind.room and ScopeResourceKind.participant

    def test_the_actor_is_passed_from_the_guarded_scope_not_from_the_body(self) -> None:
        """归属判据的另一半：`actor_user_id` 只能来自 `scope.user_id`。

        从 body 取「我是谁」= 任何人都能声称自己是任何人，于是「只能离开自己的 lease」
        这条门在结构上不存在。
        """
        fn = _func(_tree(_ROUTER_PY), LEAVE_HANDLER)
        found: list[str | None] = []
        for node in ast.walk(fn):
            if isinstance(node, ast.Call) and _dotted(node.func) == "svc.rooms.leave_participant":
                for kw in node.keywords:
                    if kw.arg == "actor_user_id":
                        found.append(_dotted(kw.value))
        assert found == ["scope.user_id"], found

    def test_the_not_owned_participant_gets_the_very_same_404_envelope(self) -> None:
        """「不是你的 lease」与 guard 的 404 必须**逐字节**同响应（Property 45）。"""
        http = SR._sync_http(RM.ParticipantScopeNotVisibleError("participant 不可见: x"))
        assert http.status_code == 404
        assert http.detail == EXTERNAL_NOT_FOUND_DETAIL
        assert http.detail == SR._not_found().detail
        # 拒绝原因不得从响应里读出来（连 error_code 都不给）。
        assert "participant" not in str(http.detail)

    def test_the_two_refusals_are_409_with_distinct_error_codes(self) -> None:
        """dirty 与 in-flight **分型**：前端据 code 决定提示「先保存」还是「稍等」。"""
        dirty = SR._sync_http(RM.ParticipantDirtyLeaveError("编辑器仍有未保存的修改"))
        busy = SR._sync_http(RM.ParticipantLeaveInFlightError("还有未终结的写请求"))
        assert dirty.status_code == 409 and busy.status_code == 409
        assert set(dirty.detail) == {"error_code", "message"}
        assert dirty.detail["error_code"] == "participant_leave_refused_dirty"
        assert busy.detail["error_code"] == "participant_leave_refused_in_flight"
        assert dirty.detail["error_code"] != busy.detail["error_code"], (
            "压成一个 code 会让 UI 只能说一句笼统的话，而两者的补救动作不同"
        )
        # 409 的唯一构造点刻意不放任何既有资源 id。
        for http in (dirty, busy):
            assert "id" not in http.detail

    def test_all_three_codes_are_registered_in_the_single_mapping_table(self) -> None:
        """未登记的 error_code 会落进 422 兜底 —— 那会让 404 那条变成存在性预言机。"""
        table = SR._ERROR_CODE_STATUS
        assert table["participant_scope_not_found"] == 404
        assert table["participant_leave_refused_dirty"] == 409
        assert table["participant_leave_refused_in_flight"] == 409


# ═══════════════════════════════════════════════════════════════════════════
# 3. 「它不是 close-intent」的结构判据（AC 4.1 / P7）
# ═══════════════════════════════════════════════════════════════════════════

#: leave 路径上**一个都不许出现**的动作。名字取自 close-intent 真的在做的那些事。
_FORBIDDEN_CALLS = frozenset(
    {
        "create_forcesave_request_with_shell",
        "freeze_and_persist_request",
        "create_close_intent",
        "reconcile_close_intents",
        "append_close_intent_event",
        "append_operation_event",
        "append_application_event",
        "register_scope",
        "supersede_room",
        "_mark_refresh_required_locked",
        "_cancel_outstanding_requests_locked",
        "revoke_participant",
    }
)

#: leave 路径上**一个都不许被赋值**的 room 列。
_FORBIDDEN_ROOM_COLUMNS = frozenset(
    {
        "state",
        "generation",
        "write_fence_epoch",
        "close_barrier_epoch",
        "close_leader_intent_id",
        "close_leader_eligibility_epoch",
        "refresh_required_at",
        "refresh_reason",
        "expires_at",
        "updated_at",
        "superseded_at",
        "doc_key",
    }
)


def room_column_writes(fn: ast.AST) -> set[str]:
    """函数体内对**任何名字叫 room 的对象**的属性赋值。

    名字口径刻意宽（`room.*` / `self.room.*` 都收）—— 漏收一种写法比多收一种坏得多。
    检查器自身的反证见 `test_the_room_write_detector_itself_works`。
    """
    out: set[str] = set()
    for dotted in attribute_targets_of(fn):
        parts = dotted.split(".")
        if len(parts) >= 2 and parts[-2] == "room":
            out.add(parts[-1])
    return out


class TestLeaveDoesNoneOfTheCloseBarrierWork:
    """P7 的结构侧：**代码里根本没有**那些动作，而不是「这次没走到」。"""

    @pytest.mark.parametrize(
        "target",
        [RM.RoomService.leave_participant, WorkpaperSyncRepository.mark_participant_left],
        ids=["service", "repository"],
    )
    def test_no_request_no_barrier_no_generation_rotation(self, target: object) -> None:
        called = {name.split(".")[-1] for name in called_names_of(_func_of(target))}
        forbidden = sorted(called & _FORBIDDEN_CALLS)
        assert not forbidden, (
            f"{getattr(target, '__qualname__', target)} 调了 {forbidden} —— "
            "那是 close barrier 仲裁在做的事；对未改动文档做它会把 room 锁死"
            "（真栈 room 03bbcad8 停在 close_barrier 后再也进不去）"
        )

    @pytest.mark.parametrize(
        "target",
        [RM.RoomService.leave_participant, WorkpaperSyncRepository.mark_participant_left],
        ids=["service", "repository"],
    )
    def test_not_one_room_column_is_assigned(self, target: object) -> None:
        wrote = room_column_writes(_func_of(target))
        assert not wrote, (
            f"{getattr(target, '__qualname__', target)} 给 room 写了 {sorted(wrote)} —— "
            "P7 的反证正是「让 leave 顺手改 room.state ⇒ 红」"
        )
        # 分母不塌：被禁列表真的覆盖了那些列名（`_FORBIDDEN_ROOM_COLUMNS` 若写空，
        # 上面的断言在任何实现下都绿）。
        assert len(_FORBIDDEN_ROOM_COLUMNS) >= 12

    def test_the_room_write_detector_itself_works(self) -> None:
        """喂一份**人为**改了 room 的源码，检查器必须报出来（反空转）。"""
        bad = ast.parse(
            textwrap.dedent(
                """
                async def leave(self, room_id):
                    room = await self._repo.lock_room(room_id)
                    room.state = "close_barrier"
                    room.close_barrier_epoch += 1
                """
            )
        ).body[0]
        assert room_column_writes(bad) == {"state", "close_barrier_epoch"}
        good = ast.parse("async def leave(self):\n    participant.state = 'left'\n").body[0]
        assert room_column_writes(good) == set(), "对照组必须先过"

    def test_the_forbidden_call_detector_itself_works(self) -> None:
        bad = ast.parse(
            "async def leave(self):\n    await self._repo.create_close_intent()\n"
        ).body[0]
        called = {n.split(".")[-1] for n in called_names_of(bad)}
        assert called & _FORBIDDEN_CALLS == {"create_close_intent"}

    def test_the_only_participant_columns_written_are_the_leave_facts(self) -> None:
        """写入面**恰好**是 `state` / `left_at` / `updated_at` 三列。

        多写一列（例如顺手 `revoked_at = now()`）会让「主动离开」与「被撤销」在数据上
        混同，而撤销的取证意义正来自 `revoked_at` 只由撤销写。
        """
        wrote = {
            dotted.split(".")[-1]
            for dotted in attribute_targets_of(
                _func_of(WorkpaperSyncRepository.mark_participant_left)
            )
            if dotted.split(".")[0] == "participant"
        }
        assert wrote == {"state", "left_at", "updated_at"}, sorted(wrote)


# ═══════════════════════════════════════════════════════════════════════════
# 4. 幂等分支是**显式**的（AC 4.2 / P9）
# ═══════════════════════════════════════════════════════════════════════════


class TestTheIdempotencyBranchIsExplicit:
    def test_the_current_state_is_compared_before_assert_transition(self) -> None:
        """先读当前状态再决定，而不是 `try: assert_transition except: pass`。

        两条断言合起来才有意义：①存在一个与 `ParticipantState.left` 比较的 `if`；
        ②它的 body 里有 `return`（短路），且这个 `if` 在源码上**早于**
        `assert_transition` 那一行。只断言①时，一个「比了但继续往下走」的实现照样绿。
        """
        fn = _func_of(WorkpaperSyncRepository.mark_participant_left)
        branch_lines: list[int] = []
        for node in ast.walk(fn):
            if not isinstance(node, ast.If):
                continue
            compared = any(
                _dotted(sub) == "ParticipantState.left" for sub in ast.walk(node.test)
            )
            returns = any(isinstance(sub, ast.Return) for sub in node.body)
            if compared and returns:
                branch_lines.append(node.lineno)
        assert branch_lines, (
            "找不到「当前状态已是 left ⇒ 直接返回」的显式分支 —— "
            "PARTICIPANT_EDGES[left] 是空集，靠捕获 assert_transition 做幂等会把"
            "「重复离开」与「从 revoked 离开」压成同一个异常"
        )
        transition_lines = [
            node.lineno
            for node in ast.walk(fn)
            if isinstance(node, ast.Call) and _dotted(node.func) == "assert_transition"
        ]
        assert transition_lines, "真正的迁移必须仍走 assert_transition（不得绕过转换表）"
        assert min(branch_lines) < min(transition_lines), (
            f"幂等分支在 {branch_lines} 行、assert_transition 在 {transition_lines} 行 —— "
            "顺序反了就等于没有幂等分支"
        )

    def test_the_replayed_flag_reaches_the_response(self) -> None:
        """幂等重放在**响应上**可见（`replayed`），不只是服务端心里知道。"""
        fn = _func(_tree(_ROUTER_PY), LEAVE_HANDLER)
        returns = [n for n in ast.walk(fn) if isinstance(n, ast.Return)]
        assert len(returns) == 1, "handler 应只有一个 return（单一响应形态）"
        body = returns[0].value
        assert isinstance(body, ast.Dict)
        keys = {k.value for k in body.keys if isinstance(k, ast.Constant)}
        assert {"replayed", "left_at", "remaining_active_editors", "room_state"} <= keys, keys
        sources = {
            k.value: _dotted(v)
            for k, v in zip(body.keys, body.values)
            if isinstance(k, ast.Constant)
            for sub in [v]
            for v in [next((s for s in ast.walk(sub) if isinstance(s, ast.Attribute)), sub)]
        }
        assert sources["replayed"] == "outcome.already_left", sources


# ═══════════════════════════════════════════════════════════════════════════
# 5. 事务边界：service 只 flush，router 单 commit（本域惯例）
# ═══════════════════════════════════════════════════════════════════════════


class TestTransactionBoundary:
    @pytest.mark.parametrize(
        "target",
        [RM.RoomService.leave_participant, WorkpaperSyncRepository.mark_participant_left],
        ids=["service", "repository"],
    )
    def test_neither_the_service_nor_the_repository_commits(self, target: object) -> None:
        called = {name.split(".")[-1] for name in called_names_of(_func_of(target))}
        assert "commit" not in called, (
            f"{getattr(target, '__qualname__', target)} 自己 commit —— "
            "跨 service 编排时会把别人的半成品一起提交"
        )

    def test_the_handler_commits_exactly_once_and_rolls_back_on_refusal(self) -> None:
        fn = _func(_tree(_ROUTER_PY), LEAVE_HANDLER)
        commits = [
            n
            for n in ast.walk(fn)
            if isinstance(n, ast.Call) and _dotted(n.func) == "svc.session.commit"
        ]
        rollbacks = [
            n
            for n in ast.walk(fn)
            if isinstance(n, ast.Call) and _dotted(n.func) == "svc.session.rollback"
        ]
        assert len(commits) == 1, f"commit 出现 {len(commits)} 次"
        assert len(rollbacks) == 1, (
            "拒绝分支必须 rollback —— 不回滚会把 leave 之前那些 SELECT FOR UPDATE 的"
            "事务一直挂着，而 409 的调用方以为什么都没发生"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 6. 「未终结 request」名单单源（AC 4.4 的 in-flight 那一半）
# ═══════════════════════════════════════════════════════════════════════════


class TestTheOpenRequestStatesAreSingleSourced:
    def test_the_four_states_are_exactly_the_ones_that_can_still_get_a_callback(self) -> None:
        assert RM._OPEN_REQUEST_STATES == (
            RequestState.frozen.value,
            RequestState.pending.value,
            RequestState.accepted.value,
            RequestState.correlated.value,
        )
        # `correlated` 必须在内：incoming 已 durable 但内容尚未应用（AC 4.7）。
        assert RequestState.correlated.value in RM._OPEN_REQUEST_STATES

    def test_both_consumers_read_that_one_constant(self) -> None:
        """撤销取消它们 / 主动离开据它拒绝 —— 两处都必须引用同一个常量。

        各写一份的后果不是「不一致」，而是新增一个中间态时只有一处跟上：于是一个仍可能
        收到 callback 的 request 被当成已终结，lease 被释放，callback 回来时没有归属。
        """
        for target in (
            RM.RoomService._outstanding_request_ids_of,
            RM.RoomService._cancel_outstanding_requests_locked,
        ):
            names = {
                _dotted(n)
                for n in ast.walk(_func_of(target))
                if isinstance(n, (ast.Name, ast.Attribute))
            }
            assert "_OPEN_REQUEST_STATES" in names, (
                f"{target.__qualname__} 没有引用 _OPEN_REQUEST_STATES"
            )
            # 反面：不得在函数体内自己再列一遍状态字面量。
            inline = {
                _dotted(n)
                for n in ast.walk(_func_of(target))
                if isinstance(n, ast.Attribute) and (_dotted(n) or "").startswith("RequestState.")
            }
            # 白名单只放**目标**态：撤销要把 request 落 `superseded`，那不是「又列一遍
            # 未终结名单」。任何其他 `RequestState.*` 出现即意味着名单被抄了第二份。
            assert inline <= {"RequestState.superseded", "RequestState.superseded.value"}, (
                f"{target.__qualname__} 里又列了一遍 request 状态: {sorted(inline)}"
            )

    def test_the_active_editor_count_has_a_single_implementation(self) -> None:
        """`closing` 算不算 active 这条口径只有一份实现（RoomService）。

        `CloseIntentService` 用它判「要不要先出一个 predecessor forcesave」，leave 用它交出
        AC 4.3 的可观测面。两处各写一份 `count(*)` 时，这条口径可以在一处被改掉而另一处
        不知道 —— 而它正好决定 close barrier 会不会等一个永远不来的 predecessor。
        """
        from app.services.workpaper_sync.close_intent import CloseIntentService

        called = called_names_of(_func_of(CloseIntentService._count_active_editors))
        assert "self._rooms.count_active_editors" in called, called
        assert not any(n.endswith("select") for n in called), (
            "close_intent 又自己查了一遍 —— 口径必须只有一份实现"
        )
