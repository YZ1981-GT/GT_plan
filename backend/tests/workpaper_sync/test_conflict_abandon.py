"""冲突集「显式作废」的离线守卫（纯判据 + 结构形态）。

spec `frozen-contract-read-path-and-legacy-operation-settlement` 任务 8
Requirements: R3.3 / R3.4
Property: **Property 3**（状态变了但内容没落地不可能出现）

═══ 分工 ═══

本文件只放**不需要数据库**的判据：

* 纯函数（原因归一、操作者校验、状态准入）；
* 封闭枚举取值（终态必须来自既有 `OperationState`，不得新造字面量）；
* 结构形态（状态推进只经 `append_operation_event`；不物理删除；不碰 `superseded_at`）；
* 迁移与 ORM 的三层一致（V276 三列 ↔ ORM `Mapped[]` ↔ service 写入）。

跨表跨事务的行为判据（三列真落库、幂等重放零写入、不删行、`superseded_at` 未被清零、
operation 真的离开 `conflict`）全部在 `test_conflict_abandon_pg.py` —— 那些离线断言不了。
端点级的三角色鉴权在 `test_conflict_abandon_endpoint.py`。

🔴 纪律（memory 铁律 ㉖）：结构判据一律用 **AST**，不用文本 `in` 匹配 ——
注释与 docstring 正反两向都会骗过文本扫描器。本模块的 docstring 逐处解释「为什么不裸
SQL 改 state」时逐字写着 `UPDATE`，用子串判据会把自己判成违规。
"""

from __future__ import annotations

import ast
import uuid
from pathlib import Path

import pytest

from app.services.workpaper_sync import conflict_abandon as CA
from app.services.workpaper_sync import models as M

BACKEND = Path(__file__).resolve().parents[2]
SVC = BACKEND / "app" / "services" / "workpaper_sync"
ABANDON_PY = SVC / "conflict_abandon.py"
REPO_PY = SVC / "repository.py"
MIGRATION_V = BACKEND / "migrations" / "V276__sync_conflict_abandon_columns.sql"
MIGRATION_R = BACKEND / "migrations" / "R276__rollback_sync_conflict_abandon_columns.sql"


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _methods(path: Path) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    """顶层函数与类的直接方法，键用 `Class.method` / `func`。"""
    out: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}
    for node in _tree(path).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out[node.name] = node
        elif isinstance(node, ast.ClassDef):
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    out[f"{node.name}.{sub.name}"] = sub
    return out


def _called_names(fn: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Name):
                names.add(f.id)
            elif isinstance(f, ast.Attribute):
                names.add(f.attr)
    return names


def _sql_literals(fn: ast.AST) -> list[str]:
    """函数体里出现的 `sa.text("…")` 字面量（AST，注释与 docstring 天然排除）。"""
    out: list[str] = []
    for node in ast.walk(fn):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "text"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            out.append(node.args[0].value)
    return out


# ═══════════════════════════════════════════════════════════════════════════
# 一、终态必须来自既有枚举（不得新造字面量）
# ═══════════════════════════════════════════════════════════════════════════


class TestTerminalStateComesFromTheExistingEnum:
    """R3.3「operation 落终态」不许新造取值。

    🔴 新造字面量会让两处同时失配：DB 侧 `ck_wpso_state`（V151 逐值锁死）会拒绝写入，
    平台 `is_terminal("operation", …)` 也会把它判成非终态 ⇒ `finished_at` 不写、
    `settle_requests_of_terminal_application` 不触发。
    """

    def test_the_terminal_state_is_an_existing_operation_state(self) -> None:
        assert isinstance(CA.ABANDON_TERMINAL_STATE, M.OperationState)
        assert CA.ABANDON_TERMINAL_STATE in set(M.OperationState)

    def test_the_terminal_state_is_really_terminal(self) -> None:
        """出边为空 —— 否则「落终态」是假的，它还会被别的流程继续推进。"""
        assert M.is_terminal("operation", CA.ABANDON_TERMINAL_STATE) is True
        assert M.OPERATION_EDGES[CA.ABANDON_TERMINAL_STATE] == frozenset()

    def test_conflict_may_reach_the_chosen_terminal(self) -> None:
        """`conflict` 的登记出边必须包含它 —— 否则 `append_operation_event` 会抛。"""
        M.assert_transition(
            "operation", M.OperationState.conflict, CA.ABANDON_TERMINAL_STATE
        )

    def test_the_chosen_terminal_is_one_of_conflicts_terminal_successors(self) -> None:
        """`conflict` 的登记出边必须包含它 —— 否则 `append_operation_event` 会抛。

        🔴 现算（2026-11-16）：`conflict` 的终态后继有**两个** —— `superseded` 与
        `authorization_stale`。选前者的理由是可证伪的：`authorization_stale` 的语义是
        「授权在裁决途中失效」（由 `assert_final_authorization` 的 fence 触发），
        而作废是**人工作出的业务决定**，不是授权事件。用它会让 timeline 把作废误报成
        「授权过期」，运维会去查权限而不是查谁作了废。
        """
        terminal_successors = {
            s
            for s in M.OPERATION_EDGES[M.OperationState.conflict]
            if M.is_terminal("operation", s)
        }
        assert CA.ABANDON_TERMINAL_STATE in terminal_successors, (
            f"{CA.ABANDON_TERMINAL_STATE} 不是 conflict 的终态后继（实得 {terminal_successors}）"
        )

    def test_the_other_terminal_successor_means_something_else(self) -> None:
        """作废**不得**借道 `authorization_stale` —— 它有自己的错误码与触发源。

        本判据把「选择理由」变成可证伪的断言：`authorization_stale` 只由
        `ResolveAuthorizationStaleError` 产生（见 `conflict_resolution`），作废路径
        不 import 它、也不抛它（`TestTheAbandonModuleDoesNotDependOnTheResolvePath`
        钉住「不 import conflict_resolution」，本条钉住终态选值不撞车）。
        """
        others = {
            s
            for s in M.OPERATION_EDGES[M.OperationState.conflict]
            if M.is_terminal("operation", s)
        } - {CA.ABANDON_TERMINAL_STATE}
        assert M.OperationState.authorization_stale in others, (
            "现算的前提变了：`authorization_stale` 已不是 conflict 的终态后继 —— "
            "请重新核对本节两条判据的依据"
        )
        assert CA.ABANDON_TERMINAL_STATE is M.OperationState.superseded, (
            "作废的终态必须是 superseded：authorization_stale 语义是「授权失效」，"
            "用它会让 timeline 把人工作废误报成授权事件"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 二、原因与操作者（R3.3：带中文原因与操作者）
# ═══════════════════════════════════════════════════════════════════════════


class TestReasonIsMandatoryAndNonVacuous:
    def test_a_normal_reason_is_stripped_and_returned(self) -> None:
        assert CA.normalize_abandon_reason("  契约已换代，这批冲突不再需要处理  ") == (
            "契约已换代，这批冲突不再需要处理"
        )

    @pytest.mark.parametrize(
        "raw",
        [None, "", "   ", "无", "作废", "abc", 0, [], {"reason": "x"}],
        ids=["none", "empty", "spaces", "one-char", "two-char", "latin-3", "int", "list", "dict"],
    )
    def test_blank_or_too_short_reason_is_refused(self, raw: object) -> None:
        with pytest.raises(CA.AbandonReasonRequiredError) as exc:
            CA.normalize_abandon_reason(raw)
        assert exc.value.error_code == "conflict_abandon_reason_required"

    def test_the_threshold_is_not_zero(self) -> None:
        """`MIN_REASON_CHARS` 是判据的一部分，不能是 0（否则上一条的短串会被放行）。"""
        assert CA.MIN_REASON_CHARS >= 4


class TestActorIsMandatory:
    def test_a_uuid_is_returned_as_is(self) -> None:
        actor = uuid.uuid4()
        assert CA.assert_abandon_actor(actor) == actor

    def test_a_uuid_text_is_accepted(self) -> None:
        actor = uuid.uuid4()
        assert CA.assert_abandon_actor(str(actor)) == actor

    @pytest.mark.parametrize("raw", [None, "", "not-a-uuid", 0, object()], ids=lambda v: type(v).__name__)
    def test_a_missing_actor_is_refused(self, raw: object) -> None:
        with pytest.raises(CA.AbandonActorRequiredError) as exc:
            CA.assert_abandon_actor(raw)
        assert exc.value.error_code == "conflict_abandon_actor_required"


# ═══════════════════════════════════════════════════════════════════════════
# 三、状态准入：只有 conflict 可作废
# ═══════════════════════════════════════════════════════════════════════════


class TestOnlyConflictIsAbandonable:
    def test_conflict_passes(self) -> None:
        CA.assert_conflict_abandonable(M.OperationState.conflict)
        CA.assert_conflict_abandonable("conflict")

    @pytest.mark.parametrize(
        "state",
        [
            M.OperationState.applied,
            M.OperationState.superseded,
            M.OperationState.refresh_required,
            M.OperationState.rejected,
            M.OperationState.authorization_stale,
            M.OperationState.duplicate,
        ],
        ids=lambda s: s.value,
    )
    def test_every_terminal_state_is_refused(self, state: M.OperationState) -> None:
        """已结算的 operation 不得重复作废（R3.3 隐含：作废是一次性动作）。"""
        with pytest.raises(CA.ConflictNotAbandonableError) as exc:
            CA.assert_conflict_abandonable(state)
        assert "终态" in str(exc.value)
        assert exc.value.error_code == "conflict_not_abandonable"

    @pytest.mark.parametrize(
        "state",
        [M.OperationState.applying, M.OperationState.merging, M.OperationState.rematerializing],
        ids=lambda s: s.value,
    )
    def test_intermediate_states_are_refused(self, state: M.OperationState) -> None:
        """中间态作废会把正在落库的流水线拦腰切断。"""
        with pytest.raises(CA.ConflictNotAbandonableError):
            CA.assert_conflict_abandonable(state)

    def test_error_is_refused_too(self) -> None:
        """`error` 不是终态（可重试）但同样不是 conflict —— 必须拒。

        🔴 这一条独立成用例：`error` 是唯一一个「非终态但也不该作废」的取值，
        把它漏掉时上面的两个参数化都会绿。
        """
        with pytest.raises(CA.ConflictNotAbandonableError):
            CA.assert_conflict_abandonable(M.OperationState.error)

    def test_an_unknown_state_raises_instead_of_passing(self) -> None:
        """未登记的状态不得被当成「不是 conflict 就拒」以外的形态放过。"""
        with pytest.raises(ValueError):
            CA.assert_conflict_abandonable("no-such-state")


# ═══════════════════════════════════════════════════════════════════════════
# 四、结构形态：状态推进只经一个入口，不裸 SQL，不删行
# ═══════════════════════════════════════════════════════════════════════════


class TestStateIsAdvancedThroughTheSingleTransitionEntry:
    def test_abandon_uses_append_operation_event(self) -> None:
        """R3.3「禁止裸 SQL 改 state」的正面判据：只经 `append_operation_event`。

        该方法是状态推进的唯一合法写入口 —— 它内部 `assert_transition` 校验登记边、
        写 append-only event、再投影 current state。绕过它等于同时跳过边校验与 timeline。
        """
        called = _called_names(_methods(ABANDON_PY)["ConflictAbandonService.abandon"])
        assert "append_operation_event" in called, (
            "abandon() 没有调用 append_operation_event —— 状态推进必须走它"
        )

    def test_abandon_never_writes_state_with_raw_sql(self) -> None:
        """反向判据：`abandon()` 里不得出现任何裸 SQL 文本（AST 取 `sa.text` 实参）。

        这是 R3.3 末句的可证伪形式：把 `append_operation_event` 换成
        `sa.text("UPDATE working_paper_sync_operation SET state='superseded' …")`
        时上一条会红、本条也会红（两重锁，任一被绕都能被另一条抓）。
        """
        literals = _sql_literals(_methods(ABANDON_PY)["ConflictAbandonService.abandon"])
        assert literals == [], f"abandon() 里出现裸 SQL 字面量：{literals}"

    def test_abandon_never_deletes_conflict_rows(self) -> None:
        """R3.3「不物理删除冲突行」：AST 里不得有 `delete(` / `sa.delete`。"""
        tree = _tree(ABANDON_PY)
        offenders: list[str] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
            if name == "delete":
                offenders.append(f"line {node.lineno}: {name}()")
        assert offenders == [], (
            "conflict_abandon 里出现 delete 调用 —— 冲突行是 append-only 审计事实，"
            f"作废只写三列不删行：{offenders}"
        )

    def test_abandon_never_touches_superseded_at(self) -> None:
        """勘误 E.3：`superseded_at` 的唯一写入方是 `record_conflicts`（观测同步）。

        作废路径写它会被下一次重观测静默抹掉（`record_conflicts` 对**本轮命中**的行
        执行 `row.superseded_at = None`）。AST 断言：`abandon()` 里没有任何
        `superseded_at` 赋值目标。
        """
        assign_targets: set[str] = set()
        for node in ast.walk(_methods(ABANDON_PY)["ConflictAbandonService.abandon"]):
            if isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Attribute):
                        assign_targets.add(t.attr)
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Attribute):
                assign_targets.add(node.target.attr)
        assert "superseded_at" not in assign_targets, (
            "abandon() 给 superseded_at 赋值 —— 该列属观测同步，人工作废会写第二真源"
        )

    def test_abandon_writes_exactly_the_three_new_columns(self) -> None:
        """三条新列必须都被写（缺一列 = `ck_wpsc_abandon_triplet` 会拒，或轨迹残缺）。"""
        targets: set[str] = set()
        for node in ast.walk(_methods(ABANDON_PY)["ConflictAbandonService.abandon"]):
            if isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Attribute):
                        targets.add(t.attr)
        assert {"abandoned_at", "abandon_reason", "abandoned_by"} <= targets, (
            f"abandon() 没有写全三列，实得 {sorted(targets)}"
        )


class TestTheAbandonServiceNeverCommits:
    """「只 flush 不 commit」：commit 由 router 统一做，否则三列与状态不在同一事务。"""

    def test_no_commit_call_in_the_module(self) -> None:
        offenders: list[str] = []
        for name, fn in _methods(ABANDON_PY).items():
            for node in ast.walk(fn):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "commit"
                ):
                    offenders.append(f"{name} line {node.lineno}")
        assert offenders == [], f"conflict_abandon 里出现 commit()：{offenders}"


# ═══════════════════════════════════════════════════════════════════════════
# 五、三层一致：V276 迁移 ↔ ORM ↔ 白名单/回退
# ═══════════════════════════════════════════════════════════════════════════


class TestMigrationOrmAndServiceAgree:
    """memory 铁律：DB 迁移 + ORM `Mapped[]` + service 方法，任一缺失即伪绿。"""

    def test_the_migration_adds_all_three_columns_idempotently(self) -> None:
        sql = MIGRATION_V.read_text(encoding="utf-8")
        for column in ("abandoned_at", "abandon_reason", "abandoned_by"):
            assert f"ADD COLUMN IF NOT EXISTS {column}" in sql, (
                f"V276 没有幂等地加列 {column}（CREATE/ALTER 必 IF NOT EXISTS）"
            )

    def test_the_migration_declares_the_triplet_check(self) -> None:
        sql = MIGRATION_V.read_text(encoding="utf-8")
        assert "ck_wpsc_abandon_triplet" in sql
        # 三列同生共死 + 原因非空白
        assert "(abandoned_at IS NULL) = (abandoned_by IS NULL)" in sql
        assert "length(btrim(abandon_reason)) > 0" in sql

    def test_the_rollback_drops_exactly_those_three(self) -> None:
        sql = MIGRATION_R.read_text(encoding="utf-8")
        for column in ("abandoned_at", "abandon_reason", "abandoned_by"):
            assert f"DROP COLUMN IF EXISTS {column}" in sql, f"R276 没有删列 {column}"
        # 有作废行时必须拒绝回滚，而不是静默抹掉审计事实
        assert "RAISE EXCEPTION" in sql
        assert "abandoned_at IS NOT NULL" in sql

    def test_the_orm_maps_all_three_columns(self) -> None:
        from app.models.workpaper_sync_models import WorkpaperSyncConflict

        columns = {c.name: c for c in WorkpaperSyncConflict.__table__.columns}
        for column in ("abandoned_at", "abandon_reason", "abandoned_by"):
            assert column in columns, f"ORM 缺列 {column} —— 三层不一致"
            assert columns[column].nullable is True, (
                f"{column} 必须可空（作废是显式动作，绝大多数行永远为空）"
            )

    def test_the_orm_does_not_reuse_superseded_at(self) -> None:
        """ORM 侧也必须有三列独立的列 —— 把 `abandoned_at` 写成 `superseded_at` 的别名
        （同名列 / 同 `mapped_column` 对象）会让两层同时退化成第二真源。"""
        from app.models.workpaper_sync_models import WorkpaperSyncConflict

        cols = {c.name: c for c in WorkpaperSyncConflict.__table__.columns}
        assert cols["abandoned_at"] is not cols["superseded_at"]


# ═══════════════════════════════════════════════════════════════════════════
# 六、router 侧形态：操作者不取请求体、端点挂写 action
# ═══════════════════════════════════════════════════════════════════════════


ROUTER_PY = BACKEND / "app" / "routers" / "wp_sync_router.py"


class TestTheEndpointTakesTheActorFromServerState:
    def test_actor_comes_from_guarded_scope_not_from_payload(self) -> None:
        """R3.3「带操作者」的**安全性**判据：`actor_id` 必须来自 `scope.user_id`。

        🔴 变异 d（操作者取请求体）必须让本条红：把 `actor_id=scope.user_id` 改成
        `actor_id=payload.get("actor_id")` 后这里的实参名字就不再是 `scope`。
        """
        fn = _methods(ROUTER_PY)["abandon_conflicts"]
        actor_args = [
            kw.value
            for node in ast.walk(fn)
            if isinstance(node, ast.Call)
            for kw in node.keywords
            if kw.arg == "actor_id"
        ]
        assert actor_args, "abandon_conflicts() 没有向 service 传 actor_id"
        for arg in actor_args:
            assert isinstance(arg, ast.Attribute) and arg.attr == "user_id", (
                "actor_id 的实参不是 `<something>.user_id` —— 操作者必须取服务端当前用户，"
                "不得来自请求体（否则审计轨迹可伪造）"
            )
            assert isinstance(arg.value, ast.Name) and arg.value.id == "scope", (
                f"actor_id 的来源是 {ast.dump(arg)!r} 而不是 scope.user_id"
            )

    def test_the_endpoint_declares_the_write_action(self) -> None:
        from app.routers import wp_sync_router as SR

        assert "abandon_conflicts" in SR._WRITE_ACTIONS
        assert "abandon_conflicts" not in SR._READ_ONLY_ACTIONS

    def test_the_three_new_error_codes_are_registered(self) -> None:
        from app.routers import wp_sync_router as SR

        assert SR._ERROR_CODE_STATUS["conflict_not_abandonable"] == 409
        assert SR._ERROR_CODE_STATUS["conflict_abandon_reason_required"] == 422
        assert SR._ERROR_CODE_STATUS["conflict_abandon_actor_required"] == 422

    def test_the_endpoint_reads_reason_from_payload_only(self) -> None:
        """请求体只允许 `reason` —— 端点不得从 payload 取 actor/actor_id/abandoned_by。"""
        fn = _methods(ROUTER_PY)["abandon_conflicts"]
        payload_keys: set[str] = set()
        for node in ast.walk(fn):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "get"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "payload"
                and node.args
                and isinstance(node.args[0], ast.Constant)
            ):
                payload_keys.add(str(node.args[0].value))
        assert payload_keys <= {"reason"}, (
            f"端点从请求体读了 {sorted(payload_keys)} —— 只允许 reason"
        )


class TestTheAbandonModuleDoesNotDependOnTheResolvePath:
    """作废与裁决是两条不同写路径。"""

    def test_it_does_not_import_conflict_resolution(self) -> None:
        """反向依赖会同时造成循环 import 与「作废也要过 resolve fence」的错误约束。"""
        tree = _tree(ABANDON_PY)
        modules = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        }
        assert "app.services.workpaper_sync.conflict_resolution" not in modules
        assert "app.services.workpaper_sync.oo_to_html" not in modules
