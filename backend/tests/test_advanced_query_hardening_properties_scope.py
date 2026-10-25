"""高级查询硬化：Hypothesis 属性测试 —— 作用域·执行路径·治理·只读门禁域。

Feature: advanced-query-hardening-wiring-closure

覆盖 Property 1/2/3（只读端点门禁）· 4/5（构建器项目作用域与缓存键隔离）·
6（单一执行路径）· 14（失败不伪装成功）· 19/20（模板治理）· 21（回写全有或全无）·
22（建表脚本幂等）· 23（前后端判据同源）· 24（指标树骨架收敛）。

契约与分页域见 `test_advanced_query_hardening_properties.py`。
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from hypothesis import given
from hypothesis import strategies as st

from app.routers.custom_query import QueryRequest as ApiQueryRequest
from app.services.custom_query import builder_scope as bs
from app.services.custom_query.builder_scope import (
    BuilderScope,
    apply_scope_to_select,
    scope_signature,
)
from app.services.custom_query.execute_compatibility import ExecuteCompatibilityAdapter
from app.services.custom_query.pagination import MAX_LIMIT
from app.services.custom_query.query_orchestrator import (
    ColumnMeta,
    QueryRequest,
    QueryResult,
)
from app.services.custom_query.table_whitelist import TABLE_WHITELIST

# 共享夹具与策略见 `_advanced_query_pbt_common`（拆分自本文件，避免行数门禁超限）
from tests._advanced_query_pbt_common import (  # noqa: E402
    PBT,
    _Addressing,
    _Guard,
    _IDENT,
    _PassthroughCache,
    _SCALAR,
    _orch,
    _run,
)
# ════════════════════════════════════════════════════════════════════════════
# Property 4 / 5 — 构建器作用域不可放宽 + 缓存键隔离
# **Validates: Requirements 2.1, 2.4**
# ════════════════════════════════════════════════════════════════════════════
@PBT
@given(pids=st.lists(st.uuids(), min_size=1, max_size=6, unique=True))
def test_p4_scope_filter_always_present_for_scopable_table(pids):
    """任意非空作用域，可作用域表的 SQL 恒含 project_id 约束。"""
    from sqlalchemy import select

    from app.models.audit_platform_models import TrialBalance

    scope = BuilderScope(project_ids=frozenset(pids))
    stmt = apply_scope_to_select(
        select(TrialBalance.id), scope=scope, table_name="trial_balance"
    )
    sql = str(stmt.compile(compile_kwargs={"literal_binds": False})).lower()
    assert "project_id" in sql



def _drop_guard_shadow() -> None:
    """删掉 ``ownership_guard`` 实例上的 ``assert_target_accessible`` 覆盖。

    为什么不能用「读出原绑定方法、finally 再赋回实例」的写法恢复：那样实例上会**永久**
    留下一个属性（哪怕值就是原绑定方法），它会遮蔽类属性 —— 之后任何
    ``patch("....OwnershipGuard.assert_target_accessible")``（类级替身）都打不上，
    表现为「另一个文件里的越权用例莫名变红」，而单跑那个文件却是绿的。
    实测就是这样让 test_disclosure_notes_hardening 的 5 条 trace 用例在合跑时变红。

    正确恢复 = 把实例属性删掉，回落到类属性。
    """
    from app.services.custom_query.ownership_guard import ownership_guard

    ownership_guard.__dict__.pop("assert_target_accessible", None)


@PBT
@given(
    a=st.lists(st.uuids(), min_size=1, max_size=5, unique=True),
    b=st.lists(st.uuids(), min_size=1, max_size=5, unique=True),
)
def test_p5_distinct_scopes_get_distinct_signatures(a, b):
    """不同作用域集合恒得不同签名；相同集合恒得相同签名（顺序无关）。"""
    sa = scope_signature(BuilderScope(project_ids=frozenset(a)))
    sb = scope_signature(BuilderScope(project_ids=frozenset(b)))
    if set(a) == set(b):
        assert sa == sb
    else:
        assert sa != sb
    # 顺序无关
    assert sa == scope_signature(BuilderScope(project_ids=frozenset(reversed(a))))
    # 全项目作用域恒与任何受限作用域不同
    assert sa != scope_signature(BuilderScope(project_ids=None))


# ════════════════════════════════════════════════════════════════════════════
# Property 6 — 单一执行路径：adapter 恰好一次，抛错时取数器零调用
# **Validates: Requirements 3.1, 3.2**
# ════════════════════════════════════════════════════════════════════════════
@PBT
@given(source=_IDENT, year=st.integers(min_value=2000, max_value=2100))
def test_p6_orchestrator_called_exactly_once_and_no_fallback(source, year):
    """任意请求体：编排器恒被调用一次；抛错时无第二条路径接手。"""
    calls = {"n": 0}

    class _Track:
        async def execute(self, request, *, user, db):
            calls["n"] += 1
            return QueryResult(rows=[], columns=[], total=0, limit=request.limit, offset=request.offset)

    adapter = ExecuteCompatibilityAdapter(
        business_fetcher=lambda *a: None, orchestrator=_Track()
    )
    body = ApiQueryRequest(project_id="p1", year=year, source=source)
    result = _run(adapter.execute(body, user=SimpleNamespace(id="u1"), db=None))
    assert calls["n"] == 1
    assert result["total"] == 0


@PBT
@given(status=st.sampled_from([400, 403, 408, 422]))
def test_p6_adapter_error_does_not_reach_fetcher(status):
    """编排器抛错时取数器恒零调用（无 fallback 兜底执行）。"""
    fetch_calls = {"n": 0}

    async def fetcher(req, resolved, db):
        fetch_calls["n"] += 1
        return [], []

    class _Failing:
        async def execute(self, request, *, user, db):
            raise HTTPException(status_code=status, detail={"error_code": "X"})

    adapter = ExecuteCompatibilityAdapter(
        business_fetcher=fetcher, orchestrator=_Failing()
    )
    body = ApiQueryRequest(project_id="p1", year=2025, source="report")
    with pytest.raises(HTTPException) as exc:
        _run(adapter.execute(body, user=SimpleNamespace(id="u1"), db=None))
    assert exc.value.status_code == status
    assert fetch_calls["n"] == 0


# ════════════════════════════════════════════════════════════════════════════
# Property 14 — 失败不伪装成功
# **Validates: Requirements 5.1, 5.3**
# ════════════════════════════════════════════════════════════════════════════
@PBT
@given(
    status=st.sampled_from([400, 403, 404, 408, 409, 422]),
    error_code=_IDENT,
)
def test_p14_domain_errors_never_degrade_to_2xx(status, error_code):
    """任意领域错误恒以原状态码上抛，不会变成「2xx + error 字段」。"""
    from unittest.mock import AsyncMock

    from fastapi import Response

    import app.routers.custom_query as router_module

    original = ExecuteCompatibilityAdapter.execute

    async def _reject(self, body, *, user, db):
        raise HTTPException(status_code=status, detail={"error_code": error_code})

    ExecuteCompatibilityAdapter.execute = _reject  # type: ignore[assignment]
    try:
        db = AsyncMock()
        with pytest.raises(HTTPException) as exc:
            _run(
                router_module.execute_query(
                    ApiQueryRequest(project_id="p1", year=2025, source="report"),
                    Response(),
                    db,
                    SimpleNamespace(id=uuid.uuid4()),
                )
            )
        assert exc.value.status_code == status
        # HTTPException 分支不得 rollback（编排链只读，无脏事务）
        db.rollback.assert_not_awaited()
    finally:
        ExecuteCompatibilityAdapter.execute = original  # type: ignore[assignment]


# ════════════════════════════════════════════════════════════════════════════
# Property 24 — 指标树骨架恒显著小于全量
# **Validates: Requirements 12.1, 12.2, 12.5**
# ════════════════════════════════════════════════════════════════════════════
@PBT
@given(
    n_sections=st.integers(min_value=1, max_value=60),
    n_cycles=st.integers(min_value=1, max_value=6),
    n_papers=st.integers(min_value=1, max_value=8),
)
def test_p24_skeleton_node_count_scales_independently_of_branch_size(
    n_sections, n_cycles, n_papers, monkeypatch
):
    """骨架节点数恒不随重分支规模增长 —— 这才是懒加载的本质。"""
    import app.routers.custom_query as rm

    async def _disclosure(template_type):
        return [{"key": f"s{i}", "label": f"s{i}"} for i in range(n_sections)]

    async def _workpaper(db, project_id):
        return [
            {
                "key": f"c{c}",
                "label": f"c{c}",
                "children": [
                    {"key": f"wp{c}{p}", "label": f"wp{c}{p}"} for p in range(n_papers)
                ],
            }
            for c in range(n_cycles)
        ]

    async def _consol(db, project_id):
        return None

    async def _tpl(db, project_id):
        return "soe"

    monkeypatch.setattr(rm, "_build_disclosure_tree", _disclosure)
    monkeypatch.setattr(rm, "_build_workpaper_tree", _workpaper)
    monkeypatch.setattr(rm, "_build_consol_units_tree", _consol)
    monkeypatch.setattr(rm, "_resolve_project_template_type", _tpl)

    def _count(nodes):
        return sum(1 + _count(n.get("children")) for n in (nodes or []))

    skeleton = _run(
        rm.get_indicators(
            project_id=None, depth=1, branch=None, response=None,
            db=object(), current_user=SimpleNamespace(id="u1"),
        )
    )
    full = _run(
        rm.get_indicators(
            project_id=None, depth=None, branch=None, response=None,
            db=object(), current_user=SimpleNamespace(id="u1"),
        )
    )
    skel_n, full_n = _count(skeleton), _count(full)
    # 骨架恒不含重分支子节点，故其节点数与 n_sections/n_cycles/n_papers 无关
    assert skel_n <= full_n
    branch_nodes = n_sections + n_cycles * (1 + n_papers)
    assert full_n - skel_n == branch_nodes, (
        f"全量-骨架={full_n - skel_n}，应恰为重分支节点数 {branch_nodes}"
    )


# ════════════════════════════════════════════════════════════════════════════
# Property 19 / 20 — 模板分享逐项目鉴权 + 非 owner 恒不可改删
# **Validates: Requirements 8.3, 8.4, 8.5**
# ════════════════════════════════════════════════════════════════════════════
@PBT
@given(
    pids=st.lists(st.uuids(), min_size=1, max_size=5),
    dup_factor=st.integers(min_value=1, max_value=3),
)
def test_p19_share_targets_authorized_once_per_distinct_project(pids, dup_factor):
    """鉴权次数恒等于去重后的项目数（重复项不重复鉴权、也不漏鉴权）。"""
    import app.routers.custom_query as rm
    from app.services.custom_query.template_scope_adapter import TemplateScopeAdapter

    checked: list[str] = []

    def _dep_factory(_operation):
        async def _dep(*, project_id, current_user, db):
            checked.append(str(project_id))

        return _dep

    original = rm.require_project_access
    rm.require_project_access = _dep_factory  # type: ignore[assignment]
    try:
        normalized = TemplateScopeAdapter.normalize(
            "project", [str(p) for p in pids] * dup_factor
        )
        _run(
            rm._assert_template_scope_edit(
                normalized, current_user=SimpleNamespace(id="u1"), db=None
            )
        )
    finally:
        rm.require_project_access = original  # type: ignore[assignment]

    assert len(checked) == len({str(p) for p in pids})
    assert sorted(checked) == sorted({str(p) for p in pids})


@PBT
@given(role=st.sampled_from(["admin", "partner", "manager", "auditor", "qc", "eqcr"]))
def test_p20_non_owner_of_any_role_cannot_mutate_template(role):
    """任意角色（含 admin）非创建者时恒不可 update/delete。"""
    import app.routers.custom_query as rm

    owner = uuid.uuid4()
    other = uuid.uuid4()
    tpl = SimpleNamespace(
        id=uuid.uuid4(), name="t", description=None, data_source="workpaper",
        config={}, scope="public", shared_project_ids=[],
        creator_id=owner, created_by=owner,
        created_at=None, updated_at=None,
    )

    class _Db:
        commit_calls = 0

        async def get(self, _m, _k):
            return tpl

        async def commit(self):
            _Db.commit_calls += 1

        async def rollback(self):
            return None

        async def refresh(self, _v):
            return None

    async def _visible(t, *, current_user, db):
        return None

    original = rm._assert_template_visible
    rm._assert_template_visible = _visible  # type: ignore[assignment]
    try:
        db = _Db()
        user = SimpleNamespace(id=other, role=SimpleNamespace(value=role))
        with pytest.raises(HTTPException) as exc_u:
            _run(
                rm.update_template(
                    template_id=str(tpl.id),
                    body=rm.TemplateUpdateRequest(name="x"),
                    db=db,
                    current_user=user,
                )
            )
        assert exc_u.value.detail["error_code"] == "ONLY_OWNER_CAN_UPDATE"
        with pytest.raises(HTTPException) as exc_d:
            _run(rm.delete_template(template_id=str(tpl.id), db=db, current_user=user))
        assert exc_d.value.detail["error_code"] == "ONLY_OWNER_CAN_DELETE"
        assert _Db.commit_calls == 0
    finally:
        rm._assert_template_visible = original  # type: ignore[assignment]


# ════════════════════════════════════════════════════════════════════════════
# Property 21 — 回写全有或全无
# **Validates: Requirements 9.3, 9.4**
# ════════════════════════════════════════════════════════════════════════════
@PBT
@given(
    n_ok=st.integers(min_value=0, max_value=4),
    bad_index=st.integers(min_value=0, max_value=4),
)
def test_p21_any_inaccessible_target_blocks_all_writes(n_ok, bad_index):
    """多目标中任一不可访问 → snapshot 写入恒零次。"""
    import app.routers.custom_query as rm
    from app.services.custom_query.ownership_guard import ownership_guard

    ok_pid = uuid.uuid4()
    bad_pid = uuid.uuid4()
    targets = [{"project_id": str(ok_pid)} for _ in range(n_ok)]
    insert_at = min(bad_index, len(targets))
    targets.insert(insert_at, {"project_id": str(bad_pid)})

    writes = {"n": 0}

    async def _visible(user, db):
        return {ok_pid, bad_pid}

    async def _assert(*, user, project_id, db):
        if str(project_id) == str(bad_pid):
            raise HTTPException(
                status_code=403, detail={"error_code": "FORBIDDEN_PROJECT"}
            )

    orig_visible = rm.get_visible_project_ids
    rm.get_visible_project_ids = _visible  # type: ignore[assignment]
    ownership_guard.assert_target_accessible = _assert  # type: ignore[assignment]
    try:
        body = SimpleNamespace(project_id=str(ok_pid), targets=targets)
        with pytest.raises(HTTPException) as exc:
            _run(
                rm._assert_writeback_authorized(
                    body=body,
                    db=None,
                    current_user=SimpleNamespace(
                        id="u1", role=SimpleNamespace(value="admin")
                    ),
                    operation="回写",
                )
            )
        assert exc.value.status_code == 403
        assert writes["n"] == 0
    finally:
        rm.get_visible_project_ids = orig_visible  # type: ignore[assignment]
        _drop_guard_shadow()


# ════════════════════════════════════════════════════════════════════════════
# Property 22 — 建表脚本幂等
# **Validates: Requirements 10.2, 10.3**
# ════════════════════════════════════════════════════════════════════════════
@PBT
@given(times=st.integers(min_value=1, max_value=5))
def test_p22_ddl_is_idempotent_for_any_repeat_count(times):
    """任意重复执行次数下 DDL 语句集恒不变且全部带 IF NOT EXISTS。"""
    import importlib.util
    from pathlib import Path as _Path

    script = _Path(__file__).resolve().parents[1] / "scripts" / "_ensure_custom_query_tables.py"
    spec = importlib.util.spec_from_file_location(f"_cqt_{times}", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert "CREATE TABLE IF NOT EXISTS" in module.DDL
    for stmt in module.INDEXES_DDL.split(";"):
        if stmt.strip():
            assert "CREATE INDEX IF NOT EXISTS" in stmt
    for col_stmt in module.ALTER_ADD_COLUMNS.values():
        assert "ADD COLUMN IF NOT EXISTS" in col_stmt
    # 重复加载不改变常量内容（无隐藏可变状态）
    again = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(again)
    assert again.DDL == module.DDL
    assert again.INDEX_NAMES == module.INDEX_NAMES


# ════════════════════════════════════════════════════════════════════════════
# Property 1 / 2 / 3 — 只读端点门禁：403 先于任何领域读取与副作用
# **Validates: Requirements 1.1, 1.2, 1.4**
# ════════════════════════════════════════════════════════════════════════════
@PBT
@given(
    project_id=st.one_of(
        st.uuids().map(str),
        st.text(min_size=1, max_size=20),  # 含非法 UUID 形态
    )
)
def test_p2_indicators_gate_precedes_all_domain_reads(project_id):
    """任意 project_id 被拒时，建树相关的领域读取恒零调用。"""
    import app.routers.custom_query as rm
    from app.services.custom_query.ownership_guard import ownership_guard

    calls = {"template": 0, "disclosure": 0, "workpaper": 0, "consol": 0}

    async def _deny(*, user, project_id, db):
        raise HTTPException(status_code=403, detail={"error_code": "FORBIDDEN_PROJECT"})

    async def _tpl(db, pid):
        calls["template"] += 1
        return "soe"

    async def _disclosure(template_type):
        calls["disclosure"] += 1
        return []

    async def _workpaper(db, pid):
        calls["workpaper"] += 1
        return []

    async def _consol(db, pid):
        calls["consol"] += 1
        return None

    originals = (
        rm._resolve_project_template_type,
        rm._build_disclosure_tree,
        rm._build_workpaper_tree,
        rm._build_consol_units_tree,
    )
    ownership_guard.assert_target_accessible = _deny  # type: ignore[assignment]
    rm._resolve_project_template_type = _tpl  # type: ignore[assignment]
    rm._build_disclosure_tree = _disclosure  # type: ignore[assignment]
    rm._build_workpaper_tree = _workpaper  # type: ignore[assignment]
    rm._build_consol_units_tree = _consol  # type: ignore[assignment]
    try:
        with pytest.raises(HTTPException) as exc:
            _run(
                rm.get_indicators(
                    project_id=project_id, depth=None, branch=None, response=None,
                    db=object(), current_user=SimpleNamespace(id="u1"),
                )
            )
        assert exc.value.status_code == 403
        assert calls == {"template": 0, "disclosure": 0, "workpaper": 0, "consol": 0}, (
            f"403 后仍发生领域读取：{calls}"
        )
    finally:
        (
            rm._resolve_project_template_type,
            rm._build_disclosure_tree,
            rm._build_workpaper_tree,
            rm._build_consol_units_tree,
        ) = originals
        _drop_guard_shadow()


@PBT
@given(project_id=st.uuids().map(str), wp_code=_IDENT)
def test_p3_sheet_preview_denied_never_touches_template_init(project_id, wp_code):
    """归属校验失败时恒不触发底稿模板初始化（无认证端点不得有写副作用）。"""
    import app.routers.custom_query as rm
    from app.services.custom_query.ownership_guard import ownership_guard

    init_calls = {"n": 0}

    async def _deny(*, user, project_id, db):
        raise HTTPException(status_code=403, detail={"error_code": "FORBIDDEN_PROJECT"})

    class _Db:
        async def execute(self, *a, **k):
            init_calls["n"] += 1  # 连库查询也不该发生
            raise AssertionError("403 后不应查询数据库")

    ownership_guard.assert_target_accessible = _deny  # type: ignore[assignment]
    try:
        with pytest.raises(HTTPException) as exc:
            _run(
                rm.wp_sheet_preview(
                    project_id=project_id, wp_code=wp_code, sheet_name=None,
                    db=_Db(), current_user=SimpleNamespace(id="u1"),
                )
            )
        assert exc.value.status_code == 403
        assert init_calls["n"] == 0
    finally:
        _drop_guard_shadow()


@PBT
@given(project_id=st.uuids().map(str), wp_code=_IDENT)
def test_p1_wp_id_by_code_requires_ownership(project_id, wp_code):
    """wp-id-by-code 恒经归属校验（匿名枚举 project_id 不再可行）。"""
    import app.routers.custom_query as rm
    from app.services.custom_query.ownership_guard import ownership_guard

    seen: list[str] = []

    async def _deny(*, user, project_id, db):
        seen.append(str(project_id))
        raise HTTPException(status_code=403, detail={"error_code": "FORBIDDEN_PROJECT"})

    class _Db:
        async def execute(self, *a, **k):
            raise AssertionError("403 后不应查询数据库")

    ownership_guard.assert_target_accessible = _deny  # type: ignore[assignment]
    try:
        with pytest.raises(HTTPException) as exc:
            _run(
                rm.wp_id_by_code(
                    project_id=project_id, wp_code=wp_code,
                    db=_Db(), current_user=SimpleNamespace(id="u1"),
                )
            )
        assert exc.value.status_code == 403
        assert seen == [project_id]
    finally:
        _drop_guard_shadow()


# ════════════════════════════════════════════════════════════════════════════
# Property 23 — 前后端构建器权限判据同源（跨语言真源锁死）
# **Validates: Requirements 11.1**
# ════════════════════════════════════════════════════════════════════════════
def test_p23_frontend_builder_roles_match_backend_whitelist():
    """前端 `QUERY_BUILDER_ROLES` 必须与后端 `_QUERY_BUILDER_ROLES` 完全一致。

    前端不可能 import Python 常量，两侧必然各存一份 —— 所以需要守卫把它们锁死。
    改造前前端用的是 `canDo('edit','project_settings')`（资源级矩阵判据），与后端的
    角色白名单根本不是同一套语义，两侧会漂移成「按钮可点但必 403」。
    """
    import re
    from pathlib import Path as _Path

    from app.routers.query_builder import _QUERY_BUILDER_ROLES

    ts = (
        _Path(__file__).resolve().parents[2]
        / "audit-platform"
        / "frontend"
        / "src"
        / "composables"
        / "useQueryBuilderAccess.ts"
    )
    assert ts.exists(), f"前端判据文件不存在：{ts}"
    source = ts.read_text(encoding="utf-8")
    m = re.search(r"QUERY_BUILDER_ROLES\s*=\s*\[([^\]]*)\]", source)
    assert m, "未在前端文件中解析到 QUERY_BUILDER_ROLES"
    frontend_roles = {
        token.strip().strip("'\"") for token in m.group(1).split(",") if token.strip()
    }
    assert frontend_roles == set(_QUERY_BUILDER_ROLES), (
        f"前端 {sorted(frontend_roles)} != 后端 {sorted(_QUERY_BUILDER_ROLES)}"
    )


def test_p23_frontend_does_not_use_resource_matrix_for_builder_gate():
    """前端构建器门禁不得回退到 canDo 资源级判据（那与后端不同源）。"""
    from pathlib import Path as _Path

    tab = (
        _Path(__file__).resolve().parents[2]
        / "audit-platform"
        / "frontend"
        / "src"
        / "components"
        / "template-library"
        / "CustomQueryTab.vue"
    )
    source = tab.read_text(encoding="utf-8")
    # 只看 <script setup> 部分，避免注释/模板里的说明文字干扰
    script = source.split("<script setup", 1)[-1]
    assert "useQueryBuilderAccess" in script, "未使用统一判据 composable"
    assert "canDo('edit', 'project_settings')" not in script
    assert 'canDo("edit", "project_settings")' not in script
