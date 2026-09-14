# -*- coding: utf-8 -*-
"""Task 10 纯逻辑守卫：ORM↔V151 DDL 双向锁死 + 允许状态边 + identity 不变式。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 1 Task 10
Requirements: 2.1, 2.4, 2.5, 2.9, 4.3, 5.4, 5.5, 5.10, 8.5, 10.5, 10.9, 10.10, 10.11, 13.5, 14.10
Properties: P4 / P5 / P18 / P36 / P43 / P59 / P63 / P64 / P68

═══ 判据形态：结构与行为，不是「字符串存在」═══

本文件三类判据，全部可被变异打红：

1. **ORM ↔ DDL 双向比对** —— 从 `V151__*.sql` 真实文本解析每张表的列名/nullable，
   与 ORM `Table.columns` 逐列比对。ORM 多一列/少一列/nullable 不符即红。
   这比「ORM 里有 28 个类」强：后者改错列名照样绿。
2. **状态机闭包与不变式** —— 遍历全部登记状态与边，断言封闭性、terminal 出边为空、
   无未登记状态、无自环；再对每条被禁形态（duplicate 链/环/stranded/跨 scope）
   逐条断言抛出**具体异常类型**。
3. **identity 代数性质** —— hypothesis 在全输入空间上验证：application key 与
   callback status / request sequence / room 指针**无关**，与 base/representation/
   bundle/authority **相关**；delivery key 随 status 变化；fold 是 GREATEST。

真实 PostgreSQL 上的并发/约束判据在
`backend/tests/workpaper_sync/test_task10_repository_pg.py`。两者不重叠：
这里证明「纯逻辑对」，那里证明「多 worker 下库里结果对」。
"""
from __future__ import annotations

import ast
import hashlib
import re
import uuid
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.models.workpaper_sync_models import (
    WORKPAPER_SYNC_TABLES,
    WorkpaperContentApplication,
    WorkpaperSyncOperation,
)
from app.services.workpaper_sync import models as dm
from app.services.workpaper_sync.models import (
    ActorType,
    ApplicationState,
    AuthorityModel,
    BundleIntegrityError,
    BundleSlot,
    BundleSlotSpec,
    CloseIntentState,
    DeliveryOwnershipError,
    DeliveryState,
    DuplicateLinkError,
    IdentityError,
    OperationScope,
    OperationShape,
    OperationState,
    RecoveryCaseState,
    RequestState,
    RoomState,
    StateTransitionError,
    SupersedeError,
    assert_delivery_ownership,
    assert_direct_primary,
    assert_supersede,
    assert_transition,
    classify_operation_shape,
    compute_application_key,
    compute_delivery_key,
    compute_frozen_request_fingerprint,
    fold_effective_sequence,
    is_digest,
    is_opaque_resource_id,
    validate_bundle_slots,
)

_REPO = Path(__file__).resolve().parents[3]
_MIGRATION = (
    _REPO
    / "backend"
    / "migrations"
    / "V151__workpaper_sync_content_application_bundle_scope.sql"
)
_REPOSITORY_SRC = (
    _REPO / "backend" / "app" / "services" / "workpaper_sync" / "repository.py"
)

_HYP = settings(max_examples=5, deadline=None)


def _d(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


# ═══════════════════════════════════════════════════════════════════════════
# A. ORM ↔ V151 DDL 双向比对
# ═══════════════════════════════════════════════════════════════════════════


def _ddl_table_columns() -> dict[str, dict[str, bool]]:
    """从 V151 真实文本解析 `{表名: {列名: nullable}}`。

    只解析 `CREATE TABLE` 块内的列定义行（跳过 `CONSTRAINT`/注释/复合 PK），
    再叠加 `ALTER TABLE ... ADD COLUMN`（若有）。nullable 由 `NOT NULL`/`PRIMARY KEY` 推导。
    """
    sql = _MIGRATION.read_text(encoding="utf-8").replace("\r\n", "\n")
    out: dict[str, dict[str, bool]] = {}
    for m in re.finditer(
        r"CREATE TABLE(?: IF NOT EXISTS)?\s+([a-z_0-9]+)\s*\(", sql
    ):
        name = m.group(1)
        i = m.end() - 1
        depth = 0
        while i < len(sql):
            if sql[i] == "(":
                depth += 1
            elif sql[i] == ")":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        body = sql[m.end() : i]
        # 顶层逗号切分
        parts: list[str] = []
        cur: list[str] = []
        depth = 0
        for ch in body:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            if ch == "," and depth == 0:
                parts.append("".join(cur))
                cur = []
            else:
                cur.append(ch)
        parts.append("".join(cur))

        cols: dict[str, bool] = {}
        for raw in parts:
            # 去掉行注释
            stripped = "\n".join(
                ln for ln in raw.split("\n") if not ln.strip().startswith("--")
            )
            frag = " ".join(stripped.split())
            if not frag or frag.upper().startswith("CONSTRAINT"):
                continue
            col_m = re.match(r"^([a-z_0-9]+)\s+([A-Za-z]+)", frag)
            if col_m is None:
                continue
            col = col_m.group(1)
            upper = frag.upper()
            nullable = "NOT NULL" not in upper and "PRIMARY KEY" not in upper
            cols[col] = nullable
        out[name] = cols
    # PK 由独立 CONSTRAINT 声明的表：其 PK 列在 DB 里也是 NOT NULL
    for tbl, pk_cols in (
        ("working_paper_sync_entry_state", ("wp_id", "entry_id")),
        ("working_paper_sync_scope_index", ("resource_kind", "resource_id")),
        ("working_paper_sync_operation_contributor", ("operation_id", "participant_id")),
    ):
        for c in pk_cols:
            if c in out.get(tbl, {}):
                out[tbl][c] = False
    return out


@pytest.fixture(scope="module")
def ddl_columns() -> dict[str, dict[str, bool]]:
    parsed = _ddl_table_columns()
    assert len(parsed) == 28, (
        f"V151 应有 28 张新表，解析得 {len(parsed)}（解析器失效时本文件全部判据都会失真）"
    )
    return parsed


def test_orm_covers_exactly_the_v151_tables(ddl_columns: dict[str, dict[str, bool]]) -> None:
    """ORM 登记的表集合与 V151 的 28 张表**完全相等**（多一张/少一张都红）。"""
    orm = set(WORKPAPER_SYNC_TABLES)
    ddl = set(ddl_columns)
    assert orm == ddl, (
        f"ORM 独有: {sorted(orm - ddl)}\nDDL 独有（ORM 未映射）: {sorted(ddl - orm)}"
    )


def test_orm_columns_match_ddl_bidirectionally(
    ddl_columns: dict[str, dict[str, bool]]
) -> None:
    """逐表逐列双向比对列名与 nullable —— ORM 漂移即红（Requirement 2.5 identity 完整性）。"""
    problems: list[str] = []
    for table, orm_cls in sorted(WORKPAPER_SYNC_TABLES.items()):
        orm_cols = {c.name: bool(c.nullable) for c in orm_cls.__table__.columns}
        ddl_cols = ddl_columns[table]
        only_orm = set(orm_cols) - set(ddl_cols)
        only_ddl = set(ddl_cols) - set(orm_cols)
        if only_orm:
            problems.append(f"{table}: ORM 多出列（orm_extra）{sorted(only_orm)}")
        if only_ddl:
            problems.append(f"{table}: ORM 缺列（ddl_extra）{sorted(only_ddl)}")
        for col in sorted(set(orm_cols) & set(ddl_cols)):
            if orm_cols[col] != ddl_cols[col]:
                problems.append(
                    f"{table}.{col}: nullable 不符 ORM={orm_cols[col]} DDL={ddl_cols[col]}"
                )
    assert not problems, "ORM ↔ V151 DDL 漂移:\n" + "\n".join(problems)


def test_application_key_lives_only_on_content_application(
    ddl_columns: dict[str, dict[str, bool]]
) -> None:
    """Property 64：`application_key` 只能存在于 application 表；operation 出现同名字段即失败。"""
    assert "application_key" in {
        c.name for c in WorkpaperContentApplication.__table__.columns
    }
    op_cols = {c.name for c in WorkpaperSyncOperation.__table__.columns}
    assert "application_key" not in op_cols, (
        "operation ORM 出现 application_key —— operation 不得复制 application identity 作幂等真源"
    )
    assert "incoming_sha256" not in op_cols, (
        "operation ORM 不得复制 incoming identity"
    )
    holders = [t for t, cols in ddl_columns.items() if "application_key" in cols]
    assert holders == ["working_paper_content_application"], (
        f"DDL 侧 application_key 的持有者应恰为 application 表，实得 {holders}"
    )


def test_operation_has_nullable_unique_application_and_direct_self_fk(
    ddl_columns: dict[str, dict[str, bool]]
) -> None:
    """`application_id` nullable、`duplicate_of_operation_id` nullable self FK（Task 10 硬判据）。"""
    ddl = ddl_columns["working_paper_sync_operation"]
    assert ddl["application_id"] is True, "application_id 必须 nullable（pre-correlation 合法态）"
    assert ddl["duplicate_of_operation_id"] is True, "duplicate 指针必须 nullable"
    orm = {c.name: bool(c.nullable) for c in WorkpaperSyncOperation.__table__.columns}
    assert orm["application_id"] is True and orm["duplicate_of_operation_id"] is True
    fk_targets = {
        c.name: {fk.target_fullname for fk in c.foreign_keys}
        for c in WorkpaperSyncOperation.__table__.columns
        if c.foreign_keys
    }
    assert fk_targets["duplicate_of_operation_id"] == {"working_paper_sync_operation.id"}
    assert fk_targets["application_id"] == {"working_paper_content_application.id"}


def test_repository_never_commits() -> None:
    """repository 只 flush 不 commit —— AST 判据（真实行为判据在 PG 守卫的 rollback 场景）。

    用 AST 而不是 grep：`# commit` 注释、字符串里的 "commit" 不该打红，而
    `await self._session.commit()` 必须打红。
    """
    tree = ast.parse(_REPOSITORY_SRC.read_text(encoding="utf-8"))
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in ("commit", "begin", "begin_nested"):
                offenders.append(f"line {node.lineno}: .{node.func.attr}()")
    assert not offenders, (
        "repository 出现事务边界调用（只 flush 不 commit）: " + "; ".join(offenders)
    )
    flushes = sum(
        1
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "flush"
    )
    assert flushes >= 1, "repository 必须真的 flush（否则 DB CHECK 要到调用方 commit 才触发）"


def test_repository_uses_database_locks_not_process_locks() -> None:
    """Property 59：串行化必须来自数据库锁；出现 `asyncio.Lock`/`threading.Lock` 即红。"""
    src = _REPOSITORY_SRC.read_text(encoding="utf-8")
    tree = ast.parse(src)
    bad: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in ("Lock", "Semaphore", "RLock"):
            bad.append(f"line {node.lineno}: {node.attr}")
    assert not bad, f"repository 不得依赖进程内锁: {bad}"
    assert "pg_advisory_xact_lock" in src, "per-wp 串行化必须用事务级 advisory lock"
    assert "with_for_update" in src, "room/application/scope 必须用行锁"


# ═══════════════════════════════════════════════════════════════════════════
# B. 状态机闭包
# ═══════════════════════════════════════════════════════════════════════════


def test_state_machines_are_closed_and_registered() -> None:
    """每个机器的边只指向已登记状态；terminal 出边为空；禁自环。"""
    problems: list[str] = []
    for name, edges in dm.STATE_MACHINES.items():
        states = set(edges)
        for src, outs in edges.items():
            if src in outs:
                problems.append(f"{name}: {src.value} 自环")
            unknown = outs - states
            if unknown:
                problems.append(f"{name}: {src.value} → 未登记 {sorted(u.value for u in unknown)}")
        for terminal in dm.TERMINAL_STATES[name]:
            assert not edges[terminal]
    assert not problems, "状态机不闭合:\n" + "\n".join(problems)


def test_every_enum_value_is_registered_in_its_machine() -> None:
    """DB CHECK 里的枚举全集必须在状态机里登记 —— 否则会出现「DB 允许但 repository 不认」。"""
    pairs = [
        ("operation", OperationState),
        ("application", ApplicationState),
        ("request", RequestState),
        ("room", RoomState),
        ("close_intent", CloseIntentState),
        ("recovery_case", RecoveryCaseState),
        ("delivery", DeliveryState),
    ]
    for machine, enum_cls in pairs:
        registered = set(dm.STATE_MACHINES[machine])
        assert registered == set(enum_cls), (
            f"{machine}: 状态机登记 {sorted(s.value for s in registered)} "
            f"≠ 枚举 {sorted(s.value for s in enum_cls)}"
        )


def test_duplicate_is_terminal_and_operation_terminals_are_closed() -> None:
    """Property 18：`duplicate` 必为 terminal（loser shell 不得继续流转）。"""
    assert dm.is_terminal("operation", OperationState.duplicate)
    assert OperationState.duplicate in dm.TERMINAL_STATES["operation"]


def test_illegal_transition_raises() -> None:
    with pytest.raises(StateTransitionError):
        assert_transition("operation", OperationState.applied, OperationState.merging)
    with pytest.raises(StateTransitionError):
        assert_transition("operation", OperationState.duplicate, OperationState.applied)
    with pytest.raises(StateTransitionError):
        assert_transition("recovery_case", RecoveryCaseState.download_only, RecoveryCaseState.application_created)
    with pytest.raises(StateTransitionError):
        assert_transition("close_intent", CloseIntentState.promoted, CloseIntentState.successor_selected)
    with pytest.raises(StateTransitionError):
        assert_transition("incoming_artifact", "quarantined", "durable")
    with pytest.raises(StateTransitionError):
        assert_transition("operation", "created", "not_a_state")


def test_quarantined_incoming_has_no_edge_to_durable() -> None:
    """Requirement 5.6：quarantined 与 durable 不可互转（两支永不合流）。"""
    edges = dm.INCOMING_ARTIFACT_EDGES
    assert dm.ArtifactState.durable not in edges[dm.ArtifactState.quarantined]
    assert dm.ArtifactState.quarantined not in edges[dm.ArtifactState.durable]


def test_promoted_leader_cannot_pick_successor() -> None:
    """Requirement 10.10：leader 已 promotion 后授权失效只能走 recovery，不得再选 successor。"""
    outs = dm.CLOSE_INTENT_EDGES[CloseIntentState.promoted]
    assert CloseIntentState.successor_selected not in outs
    assert CloseIntentState.leader_ready not in outs
    assert {CloseIntentState.authorization_stale, CloseIntentState.recovery_required} <= outs


# ═══════════════════════════════════════════════════════════════════════════
# C. operation 三态 / duplicate 链环 / delivery 归属
# ═══════════════════════════════════════════════════════════════════════════

_A, _B, _C = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()


def test_operation_shape_three_states() -> None:
    assert (
        classify_operation_shape(
            application_id=None, duplicate_of_operation_id=None, state=OperationState.accepted
        )
        is OperationShape.pre_correlation
    )
    assert (
        classify_operation_shape(
            application_id=_A,
            duplicate_of_operation_id=None,
            state=OperationState.application_bound,
        )
        is OperationShape.primary
    )
    assert (
        classify_operation_shape(
            application_id=None, duplicate_of_operation_id=_B, state=OperationState.duplicate
        )
        is OperationShape.duplicate
    )


def test_operation_shape_rejects_illegal_combinations() -> None:
    with pytest.raises(DuplicateLinkError):  # 双 owner
        classify_operation_shape(
            application_id=_A, duplicate_of_operation_id=_B, state=OperationState.duplicate
        )
    with pytest.raises(DuplicateLinkError):  # duplicate 指针但非 terminal
        classify_operation_shape(
            application_id=None, duplicate_of_operation_id=_B, state=OperationState.accepted
        )
    with pytest.raises(DuplicateLinkError):  # state=duplicate 却无指针（stranded）
        classify_operation_shape(
            application_id=None, duplicate_of_operation_id=None, state=OperationState.duplicate
        )


def _scope(
    op_id: uuid.UUID,
    *,
    app: uuid.UUID | None = None,
    dup: uuid.UUID | None = None,
    state: OperationState = OperationState.accepted,
    entry: str = "g7.listed",
    bundle: uuid.UUID | None = None,
    authority: str | None = None,
    wp: uuid.UUID | None = None,
) -> OperationScope:
    return OperationScope(
        operation_id=op_id,
        project_id=_A,
        wp_id=wp or _B,
        entry_id=entry,
        room_id=_C,
        definition_bundle_id=bundle or _A,
        authority_model_definition_sha256=authority or _d("authority"),
        application_id=app,
        duplicate_of_operation_id=dup,
        state=state,
    )


def test_direct_primary_accepts_legal_link() -> None:
    app = uuid.uuid4()
    primary_id = uuid.uuid4()
    assert_direct_primary(
        loser=_scope(uuid.uuid4()),
        target=_scope(primary_id, app=app, state=OperationState.application_bound),
        application_id=app,
    )


def test_direct_primary_rejects_self_chain_stranded_cross_scope() -> None:
    app = uuid.uuid4()
    me = uuid.uuid4()
    # self
    with pytest.raises(DuplicateLinkError):
        assert_direct_primary(
            loser=_scope(me), target=_scope(me, app=app), application_id=app
        )
    # 链/环：目标本身是 duplicate
    with pytest.raises(DuplicateLinkError):
        assert_direct_primary(
            loser=_scope(me),
            target=_scope(uuid.uuid4(), dup=uuid.uuid4(), state=OperationState.duplicate),
            application_id=app,
        )
    # 🔴 只触发「duplicate 指针非空」这一项（application 与 state 都合法）：
    # 不这样单独覆盖时，把该项短路的变异会被同一条 if 里的 state 项遮蔽（实测 GREEN）
    with pytest.raises(DuplicateLinkError):
        assert_direct_primary(
            loser=_scope(me),
            target=_scope(
                uuid.uuid4(), app=app, dup=uuid.uuid4(), state=OperationState.accepted
            ),
            application_id=app,
        )
    # 只触发「state=duplicate」这一项（指针为空、application 合法）
    with pytest.raises(DuplicateLinkError):
        assert_direct_primary(
            loser=_scope(me),
            target=_scope(uuid.uuid4(), app=app, state=OperationState.duplicate),
            application_id=app,
        )
    # stranded：目标未绑定 application（由 application 不等值这条统一拒绝）
    with pytest.raises(DuplicateLinkError):
        assert_direct_primary(
            loser=_scope(me), target=_scope(uuid.uuid4()), application_id=app
        )
    # 目标绑定的是另一个 application
    with pytest.raises(DuplicateLinkError):
        assert_direct_primary(
            loser=_scope(me),
            target=_scope(uuid.uuid4(), app=uuid.uuid4()),
            application_id=app,
        )
    # 跨 scope
    with pytest.raises(DuplicateLinkError):
        assert_direct_primary(
            loser=_scope(me, entry="other.entry"),
            target=_scope(uuid.uuid4(), app=app),
            application_id=app,
        )
    # 跨 frozen bundle
    with pytest.raises(DuplicateLinkError):
        assert_direct_primary(
            loser=_scope(me, bundle=uuid.uuid4()),
            target=_scope(uuid.uuid4(), app=app),
            application_id=app,
        )
    # 跨 authority model digest
    with pytest.raises(DuplicateLinkError):
        assert_direct_primary(
            loser=_scope(me, authority=_d("other-authority")),
            target=_scope(uuid.uuid4(), app=app),
            application_id=app,
        )


def test_no_self_supersede_and_requires_higher_sequence() -> None:
    """Property 18 / 36：同 canonical application 只 fold，不得 supersede 自己。"""
    app = uuid.uuid4()
    with pytest.raises(SupersedeError):
        assert_supersede(
            old_application_id=app,
            new_application_id=app,
            old_effective_sequence=3,
            new_effective_sequence=9,
        )
    with pytest.raises(SupersedeError):
        assert_supersede(
            old_application_id=app,
            new_application_id=uuid.uuid4(),
            old_effective_sequence=9,
            new_effective_sequence=9,
        )
    assert_supersede(
        old_application_id=app,
        new_application_id=uuid.uuid4(),
        old_effective_sequence=3,
        new_effective_sequence=4,
    )


def test_delivery_ownership_by_durable_at_only() -> None:
    """Requirement 5.4：pre-durable 可零 owner；durable 必恰一；request/application 不做 XOR。"""
    # pre-durable 零 owner 合法，且可保留已精确绑定的 request
    assert_delivery_ownership(
        state=DeliveryState.error,
        durable_at_is_set=False,
        application_id=None,
        callback_recovery_case_id=None,
        forcesave_request_id=uuid.uuid4(),
    )
    # durable + application owner + request 同时存在 → 合法（不是 XOR）
    assert_delivery_ownership(
        state=DeliveryState.acknowledged,
        durable_at_is_set=True,
        application_id=_A,
        callback_recovery_case_id=None,
        forcesave_request_id=uuid.uuid4(),
    )
    # 双 owner
    with pytest.raises(DeliveryOwnershipError):
        assert_delivery_ownership(
            state=DeliveryState.durable,
            durable_at_is_set=True,
            application_id=_A,
            callback_recovery_case_id=_B,
        )
    # durable 却零 owner
    with pytest.raises(DeliveryOwnershipError):
        assert_delivery_ownership(
            state=DeliveryState.durable,
            durable_at_is_set=True,
            application_id=None,
            callback_recovery_case_id=None,
        )
    # 把泛化 terminal 当 durable
    with pytest.raises(DeliveryOwnershipError):
        assert_delivery_ownership(
            state=DeliveryState.unmatched,
            durable_at_is_set=False,
            application_id=None,
            callback_recovery_case_id=_B,
        )


# ═══════════════════════════════════════════════════════════════════════════
# D. identity 代数性质
# ═══════════════════════════════════════════════════════════════════════════

_KEY_ARGS = dict(
    wp_id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
    room_id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
    generation=3,
    frozen_client_base_version_id=uuid.UUID("33333333-3333-3333-3333-333333333333"),
    frozen_client_base_representation_id=uuid.UUID("44444444-4444-4444-4444-444444444444"),
    incoming_sha256=_d("incoming"),
    definition_bundle_sha256=_d("bundle"),
    authority_model_definition_sha256=_d("authority"),
    adapter_build_digest=_d("adapter"),
)


def test_application_key_signature_excludes_status_and_sequence() -> None:
    """Property 64 的结构判据：key 计算入参**不含** status / request id / sequence / room 指针。"""
    import inspect

    params = set(inspect.signature(compute_application_key).parameters)
    forbidden = {
        "callback_status",
        "status",
        "request_id",
        "forcesave_request_id",
        "request_sequence",
        "origin_request_sequence",
        "effective_request_sequence",
        "room_last_applied_version_id",
        "latest_durable_application_id",
    }
    assert not (params & forbidden), (
        f"application key 不得引入 {sorted(params & forbidden)}"
    )
    assert params == set(_KEY_ARGS), (
        f"application key 入参集合漂移: {sorted(params)}"
    )


def test_application_key_is_stable_and_identity_sensitive() -> None:
    base = compute_application_key(**_KEY_ARGS)
    assert base == compute_application_key(**_KEY_ARGS), "同输入必须确定性"
    for field, changed in [
        ("frozen_client_base_version_id", uuid.uuid4()),
        ("frozen_client_base_representation_id", uuid.uuid4()),
        ("definition_bundle_sha256", _d("bundle-v2")),
        ("authority_model_definition_sha256", _d("authority-v2")),
        ("adapter_build_digest", _d("adapter-v2")),
        ("incoming_sha256", _d("incoming-v2")),
        ("generation", 4),
    ]:
        args = dict(_KEY_ARGS)
        args[field] = changed
        assert compute_application_key(**args) != base, (
            f"{field} 变化必须产生不同 application key（否则 same incoming + 不同 frozen identity 会被误折叠）"
        )


def test_application_key_rejects_empty_and_zero_digests() -> None:
    for field in (
        "incoming_sha256",
        "definition_bundle_sha256",
        "authority_model_definition_sha256",
        "adapter_build_digest",
    ):
        for bad in ("", "   ", "0" * 64, "A" * 64, "abc"):
            args = dict(_KEY_ARGS)
            args[field] = bad
            with pytest.raises(IdentityError):
                compute_application_key(**args)


def test_delivery_key_varies_by_status_and_discriminator() -> None:
    """同 frozen identity 的 status 6 / 2 / 网络重试是**不同 delivery**，但只对应一个 application。"""
    room = uuid.uuid4()
    k6 = compute_delivery_key(room_id=room, generation=1, callback_status=6, discriminator="oo-1")
    k2 = compute_delivery_key(room_id=room, generation=1, callback_status=2, discriminator="oo-1")
    k2r = compute_delivery_key(room_id=room, generation=1, callback_status=2, discriminator="oo-2")
    assert len({k6, k2, k2r}) == 3
    with pytest.raises(IdentityError):
        compute_delivery_key(room_id=room, generation=1, callback_status=2, discriminator="  ")


def test_frozen_fingerprint_covers_every_frozen_field() -> None:
    """cache hit 逐项等值：任一冻结项变化都必须改变 fingerprint（Requirement 4.1）。"""
    args = dict(
        client_confirmation_id=uuid.uuid4(),
        client_base_version_id=uuid.uuid4(),
        client_base_representation_id=uuid.uuid4(),
        client_base_projection_sha256=_d("projection"),
        definition_bundle_sha256=_d("bundle"),
        authority_model_definition_sha256=_d("authority"),
        adapter_build_digest=_d("adapter"),
        contributor_snapshot_digest=_d("contributors"),
        client_edit_epoch=2,
        write_fence_epoch=3,
        initiator_permission_epoch=4,
    )
    base = compute_frozen_request_fingerprint(**args)
    mutations = {
        "client_confirmation_id": uuid.uuid4(),
        "client_base_version_id": uuid.uuid4(),
        "client_base_representation_id": uuid.uuid4(),
        "client_base_projection_sha256": _d("projection-2"),
        "definition_bundle_sha256": _d("bundle-2"),
        "authority_model_definition_sha256": _d("authority-2"),
        "adapter_build_digest": _d("adapter-2"),
        "contributor_snapshot_digest": _d("contributors-2"),
        "client_edit_epoch": 3,
        "write_fence_epoch": 4,
        "initiator_permission_epoch": 5,
    }
    assert set(mutations) == set(args), "fingerprint 入参集合漂移"
    for field, value in mutations.items():
        variant = dict(args)
        variant[field] = value
        assert compute_frozen_request_fingerprint(**variant) != base, (
            f"{field} 变化未改变 frozen fingerprint ⇒ 不等值重放会被当 cache hit"
        )


# ── PBT ──────────────────────────────────────────────────────────────────


@_HYP
@given(
    status=st.integers(min_value=1, max_value=7),
    sequence=st.integers(min_value=1, max_value=10_000),
    room_pointer=st.uuids(),
)
def test_property_64_key_independent_of_status_sequence_room_pointer(
    status: int, sequence: int, room_pointer: uuid.UUID
) -> None:
    """Property 64：application key 与 callback status / request sequence / room 指针无关。

    **Validates: Requirements 5.5**
    """
    key = compute_application_key(**_KEY_ARGS)
    # status / sequence / room pointer 都不是 key 的输入，故任意取值下 key 恒定
    assert key == compute_application_key(**_KEY_ARGS)
    assert len(key) == 64 and is_digest(key)
    # delivery key 才随 status 变化
    d1 = compute_delivery_key(
        room_id=_KEY_ARGS["room_id"], generation=1, callback_status=status, discriminator=str(sequence)
    )
    d2 = compute_delivery_key(
        room_id=_KEY_ARGS["room_id"],
        generation=1,
        callback_status=(status % 7) + 1 if (status % 7) + 1 != status else status + 1,
        discriminator=str(sequence),
    )
    assert d1 != d2
    assert room_pointer is not None


@_HYP
@given(
    existing=st.integers(min_value=1, max_value=10_000),
    incoming=st.integers(min_value=1, max_value=10_000),
)
def test_property_18_fold_is_greatest_and_monotonic(existing: int, incoming: int) -> None:
    """Property 18：`effective_request_sequence` fold 就是 GREATEST，单调不回退。

    **Validates: Requirements 5.5**
    """
    folded = fold_effective_sequence(existing, incoming)
    assert folded == max(existing, incoming)
    assert folded >= existing and folded >= incoming
    # 幂等：再 fold 同一值不变
    assert fold_effective_sequence(folded, incoming) == folded
    # 交换律
    assert fold_effective_sequence(incoming, existing) == folded


@_HYP
@given(revision=st.integers(min_value=0, max_value=10**9))
def test_property_59_numeric_revision_is_never_a_scope_key(revision: int) -> None:
    """Requirement 10.6 / 8.7：numeric revision 永不可作 scope/resource/route key。

    **Validates: Requirements 10.11**
    """
    assert not is_opaque_resource_id(str(revision))
    assert is_opaque_resource_id(str(uuid.uuid4()))


# ═══════════════════════════════════════════════════════════════════════════
# E. bundle typed slots
# ═══════════════════════════════════════════════════════════════════════════


def _def_slot(slot: BundleSlot, digest: str | None = None) -> BundleSlotSpec:
    return BundleSlotSpec(
        slot, "definition", f"definition:{uuid.uuid4()}", digest or _d(f"{slot.value}-def")
    )


def _marker_slot(slot: BundleSlot, version: str = "v1") -> BundleSlotSpec:
    t = f"{slot.value}:none:{version}"
    return BundleSlotSpec(slot, t, f"marker:{t}", _d(t))


def test_projection_contract_requires_three_approved_definition_children() -> None:
    slots = {s: _def_slot(s) for s in BundleSlot}
    validate_bundle_slots(
        authority_model=AuthorityModel.projection_contract,
        authority_model_definition_sha256=_d("authority"),
        slots=slots,
    )
    for replaced in BundleSlot:
        bad = dict(slots)
        bad[replaced] = _marker_slot(replaced)
        with pytest.raises(BundleIntegrityError):
            validate_bundle_slots(
                authority_model=AuthorityModel.projection_contract,
                authority_model_definition_sha256=_d("authority"),
                slots=bad,
            )


def test_custom_authority_may_use_typed_null_markers() -> None:
    slots = {
        BundleSlot.template: _def_slot(BundleSlot.template),
        BundleSlot.instrumentation: _marker_slot(BundleSlot.instrumentation),
        BundleSlot.contract: _marker_slot(BundleSlot.contract),
    }
    validate_bundle_slots(
        authority_model=AuthorityModel.custom_authoritative_ooxml,
        authority_model_definition_sha256=_d("authority-custom"),
        slots=slots,
    )


def test_slot_omission_null_empty_zero_and_illegal_marker_all_rejected() -> None:
    good = {s: _def_slot(s) for s in BundleSlot}
    # slot omission
    for missing in BundleSlot:
        partial = {s: v for s, v in good.items() if s is not missing}
        with pytest.raises(BundleIntegrityError):
            validate_bundle_slots(
                authority_model=AuthorityModel.projection_contract,
                authority_model_definition_sha256=_d("authority"),
                slots=partial,
            )
    # 空 type / 空 ref / 全零 digest / 大写 hex
    for bad_spec in (
        BundleSlotSpec(BundleSlot.template, "", f"definition:{uuid.uuid4()}", _d("x")),
        BundleSlotSpec(BundleSlot.template, "definition", "", _d("x")),
        BundleSlotSpec(BundleSlot.template, "definition", f"definition:{uuid.uuid4()}", "0" * 64),
        BundleSlotSpec(BundleSlot.template, "definition", f"definition:{uuid.uuid4()}", "A" * 64),
        BundleSlotSpec(BundleSlot.template, "definition", "definition:not-a-uuid", _d("x")),
        # 非版本化 marker
        BundleSlotSpec(BundleSlot.template, "template:none", "marker:template:none", _d("x")),
        # 用了别的 slot 的 marker
        BundleSlotSpec(
            BundleSlot.template, "contract:none:v1", "marker:contract:none:v1", _d("x")
        ),
        # type 与 ref 不一致
        BundleSlotSpec(
            BundleSlot.template, "template:none:v1", "marker:template:none:v2", _d("x")
        ),
    ):
        bad = dict(good)
        bad[BundleSlot.template] = bad_spec
        with pytest.raises(BundleIntegrityError):
            validate_bundle_slots(
                authority_model=AuthorityModel.custom_authoritative_ooxml,
                authority_model_definition_sha256=_d("authority"),
                slots=bad,
            )
    # authority model digest 全零
    with pytest.raises(BundleIntegrityError):
        validate_bundle_slots(
            authority_model=AuthorityModel.projection_contract,
            authority_model_definition_sha256="0" * 64,
            slots=good,
        )


def test_digest_single_source_of_truth() -> None:
    """`is_digest` 与 V151 的 `wpsync_is_digest()` 同判据：全零/大写/短串/空白全拒。"""
    assert is_digest(_d("ok"))
    for bad in ("", " ", "0" * 64, _d("ok").upper(), _d("ok")[:63], _d("ok") + "a", None, 123):
        assert not is_digest(bad), f"{bad!r} 不应被当作合法 digest"


def test_actor_types_cover_reconciler() -> None:
    """close reconciler 是独立 actor：不得用 system/route identity 冒充用户（Requirement 4.10）。"""
    assert {a.value for a in ActorType} == {"user", "system", "callback", "reconciler"}
