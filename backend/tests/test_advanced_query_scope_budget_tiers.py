"""高级查询：项目作用域 / JOIN 业务键 / 复杂度预算 / 列分层 / 超时 守卫。

Feature: advanced-query-hardening-wiring-closure
覆盖 Requirements 2.x（构建器项目作用域）· 6.x（JOIN 安全与复杂度预算）·
7.x（技术列与 PII 收敛）· 4.3（构建器稳定排序）。

判据一律落在**行为与结构**上，不用「符号是否存在」：
- 作用域：断言生成的 SQL 真的带 project_id 约束、且用户 DSL 无法放宽；
- JOIN：断言登记表内不存在纯作用域列的 JOIN（结构判据），且运行期拒绝；
- 预算：断言超限即 400 且不执行；
- 列分层：断言默认列集与技术列/PII 列交集为空、schema 按角色隐去 PII；
- 超时：断言真的发出了 SET LOCAL statement_timeout。
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.services.custom_query import builder_scope as bs
from app.services.custom_query.builder_scope import (
    BuilderScope,
    GLOBAL_CONFIG_TABLES,
    apply_scope_to_select,
    resolve_builder_scope,
    scope_signature,
    table_is_scopable,
)
from app.services.custom_query.table_whitelist import (
    JOIN_WHITELIST,
    MAX_AGGREGATES,
    MAX_GROUP_DIMS,
    MAX_JOINS_PER_QUERY,
    NON_BUSINESS_JOIN_KEYS,
    PII_ALLOWED_ROLES,
    TABLE_WHITELIST,
    TECHNICAL_FIELD_NAMES,
    derive_field_tiers,
    enforce_complexity_budget,
    enforce_join_business_key,
    enforce_pii_field_access,
    join_business_keys,
    visible_fields_for_role,
)

P1 = uuid.UUID("11111111-1111-1111-1111-111111111111")
P2 = uuid.UUID("22222222-2222-2222-2222-222222222222")


def _sql(stmt) -> str:
    return str(stmt.compile(compile_kwargs={"literal_binds": False}))


# ════════════════════════════════════════════════════════════════════════════
# R6.1 — JOIN 必须含业务键
# ════════════════════════════════════════════════════════════════════════════
class TestJoinBusinessKey:
    def test_whitelist_has_no_scope_only_join_registration(self):
        """结构判据：登记表内不存在仅按作用域列关联的 JOIN。"""
        offending = [
            f"{base} -> {target}"
            for base, targets in JOIN_WHITELIST.items()
            for target, spec in targets.items()
            if not join_business_keys(spec.get("on") or ())
        ]
        assert offending == [], f"笛卡尔积风险 JOIN 登记：{offending}"

    def test_removed_cartesian_joins_are_absent(self):
        """三处已知笛卡尔积登记确已移除（防被重新加回）。"""
        assert "wp_index" not in JOIN_WHITELIST.get("trial_balance", {})
        assert "wp_index" not in JOIN_WHITELIST.get("adjustments", {})
        # projects 不再作为 base 向业务表发散
        assert JOIN_WHITELIST.get("projects") is None

    def test_projects_still_usable_as_join_target(self):
        """projects 仍可作为 JOIN 目标（N:1 收敛方向，不是笛卡尔积）。"""
        assert "projects" in JOIN_WHITELIST.get("disclosure_notes", {})
        assert "projects" in JOIN_WHITELIST.get("work_hours", {})
        assert "projects" in TABLE_WHITELIST  # 单表查询仍可用

    def test_scope_only_on_pairs_rejected(self):
        with pytest.raises(HTTPException) as exc:
            enforce_join_business_key(
                "trial_balance", "wp_index", [("project_id", "project_id")]
            )
        assert exc.value.status_code == 400
        assert exc.value.detail["error_code"] == "JOIN_MISSING_BUSINESS_KEY"

    def test_all_scope_columns_combined_still_rejected(self):
        """多个作用域列叠加仍不构成业务关联。"""
        with pytest.raises(HTTPException):
            enforce_join_business_key(
                "trial_balance",
                "adjustments",
                [("project_id", "project_id"), ("year", "year")],
            )

    def test_business_key_accepted(self):
        enforce_join_business_key(
            "trial_balance",
            "account_chart",
            [("project_id", "project_id"), ("standard_account_code", "account_code")],
        )

    def test_non_business_keys_set_covers_scope_columns(self):
        assert {"project_id", "year"} <= NON_BUSINESS_JOIN_KEYS


# ════════════════════════════════════════════════════════════════════════════
# R6.2 / R6.3 — 复杂度预算
# ════════════════════════════════════════════════════════════════════════════
class TestComplexityBudget:
    @pytest.mark.parametrize(
        "kwargs,kind",
        [
            ({"joins": MAX_JOINS_PER_QUERY + 1}, "joins"),
            ({"group_dims": MAX_GROUP_DIMS + 1}, "group_dims"),
            ({"aggregates": MAX_AGGREGATES + 1}, "aggregates"),
        ],
    )
    def test_over_budget_rejected(self, kwargs, kind):
        with pytest.raises(HTTPException) as exc:
            enforce_complexity_budget(**kwargs)
        assert exc.value.status_code == 400
        assert exc.value.detail["error_code"] == "COMPLEXITY_BUDGET_EXCEEDED"
        assert exc.value.detail["kind"] == kind
        # 必须明示上限，否则用户不知道该拆到多少
        assert exc.value.detail["limit"] == kwargs[kind] - 1

    def test_at_budget_boundary_allowed(self):
        enforce_complexity_budget(
            joins=MAX_JOINS_PER_QUERY,
            group_dims=MAX_GROUP_DIMS,
            aggregates=MAX_AGGREGATES,
        )

    def test_budget_limits_are_within_sane_range(self):
        """上限本身必须在合理区间 —— 否则「预算」形同虚设。

        🔴 这条是补上一个守卫缺陷：上面的 `test_over_budget_rejected` 用
        `MAX_* + 1` 算期望值，把常量改成 999 后期望值跟着变成 1000，判据自我实现、
        变异打不红（变异检验 M04 实测 GREEN）。故此处用**字面量**上界锚住。
        """
        assert 1 <= MAX_JOINS_PER_QUERY <= 5, MAX_JOINS_PER_QUERY
        assert 1 <= MAX_GROUP_DIMS <= 10, MAX_GROUP_DIMS
        assert 1 <= MAX_AGGREGATES <= 20, MAX_AGGREGATES

    @pytest.mark.parametrize(
        "kwargs",
        [{"joins": 4}, {"group_dims": 6}, {"aggregates": 11}],
    )
    def test_literal_over_budget_values_rejected(self, kwargs):
        """用字面量而非 `MAX_* + 1` 断言超限（与常量解耦）。"""
        with pytest.raises(HTTPException) as exc:
            enforce_complexity_budget(**kwargs)
        assert exc.value.detail["error_code"] == "COMPLEXITY_BUDGET_EXCEEDED"


# ════════════════════════════════════════════════════════════════════════════
# R7 — 技术列与 PII 收敛
# ════════════════════════════════════════════════════════════════════════════
class TestFieldTiers:
    def test_every_table_has_tiers(self):
        for name, meta in TABLE_WHITELIST.items():
            assert "default_fields" in meta, f"{name} 缺 default_fields"
            assert "technical_fields" in meta, f"{name} 缺 technical_fields"
            assert "pii_fields" in meta, f"{name} 缺 pii_fields"

    def test_default_fields_exclude_technical_and_pii(self):
        """核心不变式：默认列集与技术列/PII 列交集为空。"""
        for name, meta in TABLE_WHITELIST.items():
            default = set(meta["default_fields"])
            assert not (default & set(meta["technical_fields"])), name
            assert not (default & set(meta["pii_fields"])), name

    def test_default_fields_are_non_empty(self):
        """每张表都要有业务列 —— 否则默认查询会返回空列集。"""
        for name, meta in TABLE_WHITELIST.items():
            assert meta["default_fields"], f"{name} 的业务默认列集为空"

    def test_tiers_partition_all_fields(self):
        """三层并集恰好等于全字段（不漏列、不重复）。"""
        for name, meta in TABLE_WHITELIST.items():
            union = (
                set(meta["default_fields"])
                | set(meta["technical_fields"])
                | set(meta["pii_fields"])
            )
            assert union == set(meta["fields"]), name

    def test_technical_columns_are_recognized(self):
        tiers = derive_field_tiers(
            ["id", "project_id", "account_code", "is_deleted", "created_at", "updated_at"]
        )
        assert tiers["default_fields"] == ("account_code",)
        assert set(tiers["technical_fields"]) == TECHNICAL_FIELD_NAMES

    def test_staff_pii_registered_and_excluded_from_default(self):
        meta = TABLE_WHITELIST["staff_members"]
        assert set(meta["pii_fields"]) == {"email", "phone", "user_id"}
        assert "email" not in meta["default_fields"]

    @pytest.mark.parametrize("role", sorted(PII_ALLOWED_ROLES))
    def test_privileged_roles_see_pii(self, role):
        assert "email" in visible_fields_for_role("staff_members", role)
        enforce_pii_field_access("staff_members", ["email"], role)

    @pytest.mark.parametrize("role", ["auditor", "qc", "eqcr", "readonly", "", None])
    def test_unprivileged_roles_cannot_see_pii(self, role):
        assert "email" not in visible_fields_for_role("staff_members", role)
        with pytest.raises(HTTPException) as exc:
            enforce_pii_field_access("staff_members", ["email"], role)
        assert exc.value.status_code == 403
        assert exc.value.detail["error_code"] == "PII_FIELD_FORBIDDEN"

    def test_pii_check_handles_two_segment_field_syntax(self):
        """`table.field` 双段语法不能绕过 PII 校验。"""
        with pytest.raises(HTTPException):
            enforce_pii_field_access(
                "staff_members", ["staff_members.email"], "auditor"
            )

    def test_non_pii_table_unaffected(self):
        enforce_pii_field_access("trial_balance", ["audited_amount"], "auditor")

    def test_pii_roles_do_not_cover_all_builder_roles(self):
        """PII 白名单不得覆盖全部构建器准入角色，否则该分层是空操作。

        🔴 这条锁死一个真实踩坑：初版 PII_ALLOWED_ROLES = {admin, partner, manager}
        与构建器准入角色 (admin, manager, partner) **完全重合** ⇒ 能进构建器的人
        恰好都有 PII 权限 ⇒ 整层过滤从未生效（additive 死代码）。必须至少有一个
        能用构建器却看不到 PII 的角色，分层才有意义。
        """
        from app.routers.query_builder import _QUERY_BUILDER_ROLES

        builder_roles = set(_QUERY_BUILDER_ROLES)
        assert builder_roles - PII_ALLOWED_ROLES, (
            "PII_ALLOWED_ROLES 覆盖了全部构建器角色，PII 分层将永不生效："
            f"builder={sorted(builder_roles)} pii={sorted(PII_ALLOWED_ROLES)}"
        )


# ════════════════════════════════════════════════════════════════════════════
# R2 — 构建器项目作用域
# ════════════════════════════════════════════════════════════════════════════
class _Guard:
    """OwnershipGuard 替身。"""

    def __init__(self, accessible, *, deny=()):
        self._accessible = accessible
        self._deny = {str(d) for d in deny}
        self.asserted: list[str] = []

    async def get_accessible_project_ids(self, user, db):
        return self._accessible

    async def assert_target_accessible(self, *, user, project_id, db):
        self.asserted.append(str(project_id))
        if str(project_id) in self._deny:
            raise HTTPException(
                status_code=403, detail={"error_code": "FORBIDDEN_PROJECT"}
            )


@pytest.fixture
def patch_guard(monkeypatch):
    def _apply(guard):
        monkeypatch.setattr(bs, "ownership_guard", guard)
        return guard

    return _apply


class TestBuilderScope:
    @pytest.mark.asyncio
    async def test_scoped_user_gets_project_filter_in_sql(self, patch_guard):
        """行为判据：生成的 SQL 真的带 project_id 约束。"""
        patch_guard(_Guard({P1, P2}))
        from sqlalchemy import select

        from app.models.audit_platform_models import TrialBalance

        scope = await resolve_builder_scope(
            user=SimpleNamespace(id="u1"), dsl_tables=["trial_balance"], db=None
        )
        stmt = apply_scope_to_select(
            select(TrialBalance.id), scope=scope, table_name="trial_balance"
        )
        sql = _sql(stmt).lower()
        assert "project_id in" in sql

    @pytest.mark.asyncio
    async def test_user_filter_cannot_widen_scope(self, patch_guard):
        """用户自写 project_id 过滤只与作用域取交集（AND），不能放宽。"""
        patch_guard(_Guard({P1}))
        from sqlalchemy import select

        from app.models.audit_platform_models import TrialBalance

        scope = await resolve_builder_scope(
            user=SimpleNamespace(id="u1"), dsl_tables=["trial_balance"], db=None
        )
        # 模拟用户 DSL 先加了一个「查 P2」的条件，作用域随后追加
        stmt = select(TrialBalance.id).where(TrialBalance.project_id == P2)
        stmt = apply_scope_to_select(stmt, scope=scope, table_name="trial_balance")
        sql = _sql(stmt).lower()
        assert sql.count("project_id") >= 2
        assert " and " in sql, "作用域必须以 AND 追加，不能替换用户条件"

    @pytest.mark.asyncio
    async def test_all_access_role_not_filtered_but_annotated(self, patch_guard):
        """admin/partner 不加过滤，但必须标注实际作用域（R2.2）。"""
        patch_guard(_Guard(None))
        scope = await resolve_builder_scope(
            user=SimpleNamespace(id="u1"), dsl_tables=["trial_balance"], db=None
        )
        assert scope.is_all_projects
        assert scope.describe()["all_projects"] is True
        assert any("全部项目" in w for w in scope.warnings)

    @pytest.mark.asyncio
    async def test_empty_accessible_set_yields_warning_not_silent_empty(
        self, patch_guard
    ):
        """无项目分派 → 空作用域 + 明确 warning（不静默返回空结果）。"""
        patch_guard(_Guard(set()))
        scope = await resolve_builder_scope(
            user=SimpleNamespace(id="u1"), dsl_tables=["trial_balance"], db=None
        )
        assert scope.project_ids == frozenset()
        assert any("未被分派任何项目" in w for w in scope.warnings)

    @pytest.mark.asyncio
    async def test_explicit_inaccessible_project_rejected(self, patch_guard):
        """显式指定不可访问项目 → 403（R2.5）。"""
        guard = patch_guard(_Guard({P1}, deny={P2}))
        with pytest.raises(HTTPException) as exc:
            await resolve_builder_scope(
                user=SimpleNamespace(id="u1"),
                dsl_tables=["trial_balance"],
                requested_project_id=str(P2),
                db=None,
            )
        assert exc.value.status_code == 403
        assert guard.asserted == [str(P2)], "必须经 OwnershipGuard 而非自行判定"

    @pytest.mark.asyncio
    async def test_global_config_table_skipped_with_warning(self, patch_guard):
        """全局配置表跳过过滤但要标注（R2.3）。"""
        patch_guard(_Guard({P1}))
        scope = await resolve_builder_scope(
            user=SimpleNamespace(id="u1"), dsl_tables=["report_config"], db=None
        )
        assert "report_config" in scope.unscoped_tables
        assert any("report_config" in w for w in scope.warnings)

    def test_global_config_tables_really_lack_project_column(self):
        """登记为全局配置的表确实没有 project_id 列（防误登记放过有项目维度的表）。"""
        for table_name in GLOBAL_CONFIG_TABLES:
            assert not table_is_scopable(table_name), (
                f"{table_name} 有 project_id 列，不应登记为全局配置表"
            )

    def test_scopable_tables_are_actually_filtered(self):
        """可作用域表在 apply 时必须真的加上约束。"""
        from sqlalchemy import select

        from app.models.audit_platform_models import TrialBalance

        scope = BuilderScope(project_ids=frozenset({P1}))
        stmt = apply_scope_to_select(
            select(TrialBalance.id), scope=scope, table_name="trial_balance"
        )
        assert "project_id" in _sql(stmt).lower()

    def test_scope_signature_isolates_different_scopes(self):
        """R2.4：不同作用域必须产出不同签名（否则缓存跨作用域串）。"""
        a = scope_signature(BuilderScope(project_ids=frozenset({P1})))
        b = scope_signature(BuilderScope(project_ids=frozenset({P2})))
        c = scope_signature(BuilderScope(project_ids=frozenset({P1, P2})))
        all_access = scope_signature(BuilderScope(project_ids=None))
        assert len({a, b, c, all_access}) == 4

    def test_scope_signature_is_order_independent(self):
        """同一集合的不同枚举顺序必须得到同一签名（否则缓存命中率归零）。"""
        assert scope_signature(BuilderScope(project_ids=frozenset({P1, P2}))) == (
            scope_signature(BuilderScope(project_ids=frozenset({P2, P1})))
        )


# ════════════════════════════════════════════════════════════════════════════
# R6.4 — 语句超时
# ════════════════════════════════════════════════════════════════════════════
class _RecordingSession:
    def __init__(self, *, in_tx=True):
        self.statements: list[str] = []
        self._in_tx = in_tx
        self.rolled_back = False

    def in_transaction(self):
        return self._in_tx

    async def begin(self):
        self._in_tx = True

    async def execute(self, stmt, params=None):
        self.statements.append(str(stmt))
        return None

    async def rollback(self):
        self.rolled_back = True


class TestExecutionGuard:
    @pytest.mark.asyncio
    async def test_statement_timeout_is_actually_issued(self):
        """行为判据：真的发出了 SET LOCAL statement_timeout。

        全仓改造前 grep `statement_timeout` 命中 0 处、真实库该参数为 0。
        """
        from app.services.custom_query.execution_guard import statement_timeout

        session = _RecordingSession()
        async with statement_timeout(session, 12345):
            pass
        joined = " ".join(session.statements).lower()
        assert "set local statement_timeout" in joined
        assert "12345" in joined

    @pytest.mark.asyncio
    async def test_uses_set_local_not_session_wide_set(self):
        """必须是 SET LOCAL：SET 会留在连接上污染后续复用该连接的请求。"""
        from app.services.custom_query.execution_guard import statement_timeout

        session = _RecordingSession()
        async with statement_timeout(session):
            pass
        for stmt in session.statements:
            low = stmt.lower()
            if "statement_timeout" in low:
                assert "set local" in low

    @pytest.mark.asyncio
    async def test_timeout_maps_to_408_not_empty_result(self):
        """超时必须是可识别错误码，不能退化为空结果。"""
        from sqlalchemy.exc import DBAPIError

        from app.services.custom_query.execution_guard import cancellable_query

        session = _RecordingSession()

        class _Orig(Exception):
            sqlstate = "57014"

        with pytest.raises(HTTPException) as exc:
            async with cancellable_query(session, 1000):
                raise DBAPIError("stmt", {}, _Orig("canceling statement"))
        assert exc.value.status_code == 408
        assert exc.value.detail["error_code"] == "QUERY_TIMEOUT"
        assert session.rolled_back

    @pytest.mark.asyncio
    async def test_client_disconnect_rolls_back_and_propagates(self):
        """客户端断开 → 回滚释放连接，且取消要继续向上传播。"""
        import asyncio

        from app.services.custom_query.execution_guard import cancellable_query

        session = _RecordingSession()
        with pytest.raises(asyncio.CancelledError):
            async with cancellable_query(session, 1000):
                raise asyncio.CancelledError()
        assert session.rolled_back

    @pytest.mark.asyncio
    async def test_non_timeout_error_passes_through_unchanged(self):
        """非超时异常不得被伪装成 408。"""
        from app.services.custom_query.execution_guard import cancellable_query

        session = _RecordingSession()
        with pytest.raises(ValueError):
            async with cancellable_query(session, 1000):
                raise ValueError("boom")

    def test_export_budget_is_larger_than_interactive(self):
        from app.services.custom_query.execution_guard import (
            EXPORT_TIMEOUT_MS,
            QUERY_TIMEOUT_MS,
        )

        assert EXPORT_TIMEOUT_MS > QUERY_TIMEOUT_MS > 0


# ════════════════════════════════════════════════════════════════════════════
# 接线判据 — 断言 router **真的**消费了上面这些能力
# ════════════════════════════════════════════════════════════════════════════
# 上面的用例大多是纯函数判据：即便 router 一行都不调用它们也会全绿，那正是
# 「additive 注入即死代码」的形态（本 spec 的成因就是 7 个服务模块 router 引用数
# 为 0）。以下用例把判据落到 `_build_select` 与真实端点响应上。
class TestBuilderWiring:
    def _dsl(self, **kwargs):
        from app.routers.query_builder import QueryDSL

        payload = {"table": "trial_balance"}
        payload.update(kwargs)
        return QueryDSL(**payload)

    def test_default_select_excludes_technical_columns(self):
        """R7.1 接线：不选字段时构建器返回的列集不含技术列。

        改造前 `_build_select` 的 else 分支遍历 `table_meta["fields"]`（全字段），
        而前端 `dsl.fields = []` 是默认值 ⇒ 结果首列是 UUID 主键。
        """
        from app.routers.query_builder import _build_select

        _stmt, column_names = _build_select(self._dsl())
        assert column_names, "默认列集不应为空"
        assert not (set(column_names) & TECHNICAL_FIELD_NAMES), (
            f"默认列集仍含技术列：{sorted(set(column_names) & TECHNICAL_FIELD_NAMES)}"
        )
        # 与真源的 default_fields 一致，而非另一套
        assert column_names == TABLE_WHITELIST["trial_balance"]["default_fields"]

    def test_explicit_technical_column_still_allowed(self):
        """R7.3：显式选技术列仍可用（保留排查能力）。"""
        from app.routers.query_builder import _build_select

        _stmt, column_names = _build_select(self._dsl(fields=["id", "project_id"]))
        assert column_names == ["id", "project_id"]

    def test_scope_is_applied_by_build_select(self):
        """R2.1 接线：传入 scope 时 `_build_select` 真的把约束加进 SQL。"""
        from app.routers.query_builder import _build_select

        scope = BuilderScope(project_ids=frozenset({P1}))
        stmt, _ = _build_select(self._dsl(), scope=scope)
        assert "project_id in" in _sql(stmt).lower()

    def test_complexity_budget_is_enforced_by_build_select(self):
        """R6.2 接线：超预算的 DSL 在 `_build_select` 即被拒。"""
        from app.routers.query_builder import _build_select

        with pytest.raises(HTTPException) as exc:
            _build_select(
                self._dsl(
                    group_by=[f"g{i}" for i in range(MAX_GROUP_DIMS + 1)],
                )
            )
        assert exc.value.detail["error_code"] == "COMPLEXITY_BUDGET_EXCEEDED"

    def test_pii_access_is_enforced_by_build_select(self):
        """R7.4 接线：无权角色显式请求 PII 列 → 403。"""
        from app.routers.query_builder import _build_select

        with pytest.raises(HTTPException) as exc:
            _build_select(
                type(self._dsl())(table="staff_members", fields=["email"]),
                role="auditor",
            )
        assert exc.value.status_code == 403
        assert exc.value.detail["error_code"] == "PII_FIELD_FORBIDDEN"

    def test_offset_without_order_by_gets_tie_breaker(self):
        """R4.3 接线：构建器无用户排序时补确定性键。

        改造前 `order_by` 为空即无 ORDER BY 却紧接 `.offset()` —— PG 对无序结果集
        的 offset 不保证稳定，翻页会重复/漏行。
        """
        from app.routers.query_builder import _build_select

        stmt, _ = _build_select(self._dsl(offset=10))
        assert "order by" in _sql(stmt).lower()

    @pytest.mark.asyncio
    # manager 而非 auditor：auditor 会先被构建器角色门禁挡成 403，压根到不了
    # PII 过滤这一层。manager 能用构建器但无 PII 权限，恰好是有效的判据点 ——
    # 这也反过来要求 PII_ALLOWED_ROLES 不能与构建器准入角色重合。
    @pytest.mark.parametrize("role,expect_pii", [("admin", True), ("manager", False)])
    async def test_schema_endpoint_filters_pii_by_role(self, role, expect_pii):
        """R7.2/R7.4 接线（行为判据）：schema 端点按角色下发/隐去 PII 字段。

        🔴 补守卫缺陷：仅有的 `test_router_imports_wiring_symbols` 是**符号存在**
        判据，把 `visible_fields_for_role(name, role)` 换成 `meta["fields"]` 也不会
        变红（变异检验 M26 实测 GREEN）。故此处走真实端点断言响应内容。
        """
        from fastapi import FastAPI
        from httpx import ASGITransport, AsyncClient

        from app.core.database import get_db
        from app.deps import get_current_user
        from app.routers.query_builder import router as qb_router

        app = FastAPI()
        app.include_router(qb_router)

        async def _db():
            yield None

        async def _user():
            return SimpleNamespace(
                id=uuid.uuid4(), role=SimpleNamespace(value=role)
            )

        app.dependency_overrides[get_db] = _db
        app.dependency_overrides[get_current_user] = _user

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as client:
            resp = await client.get("/api/query/schema")
        assert resp.status_code == 200, resp.text
        tables = {t["name"]: t for t in resp.json()["tables"]}
        staff_fields = set(tables["staff_members"]["fields"])
        if expect_pii:
            assert "email" in staff_fields
        else:
            assert "email" not in staff_fields, "无权角色的 schema 不应含 PII 字段"
            assert "phone" not in staff_fields
            assert tables["staff_members"]["pii_fields"] == []
        # 分层字段必须一并下发，否则前端无从区分业务列与技术列
        assert tables["trial_balance"]["default_fields"]
        assert tables["trial_balance"]["technical_fields"]

    def test_custom_query_execute_has_single_cache_path(self):
        """业务视图 execute 内不得存在第二条缓存路径（R3.1）。

        改造前 router 自己做一层 `query_cache.get_cached_result`，与编排器内部的
        `CanonicalRedisQueryCache` 并行 —— 两套键规则、两套 TTL，命中与否的语义
        取决于先命中哪一层。收敛后缓存只归编排器，router 只据 `cache_hit` 落 header。
        """
        import ast
        import inspect
        import textwrap

        import app.routers.custom_query as rm

        src = textwrap.dedent(inspect.getsource(rm.execute_query))
        tree = ast.parse(src)
        called = {
            getattr(n.func, "id", None) or getattr(n.func, "attr", None)
            for n in ast.walk(tree)
            if isinstance(n, ast.Call)
        }
        for banned in ("get_cached_result", "set_cached_result", "compute_cache_key"):
            assert banned not in called, (
                f"execute_query 内仍直接调用 {banned}()，形成第二条缓存路径"
            )
        # 反向自检：解析器要能认出真实存在的调用，否则上面的断言是空转
        assert "execute" in called, "AST 解析未认出 adapter.execute 调用，判据不可靠"

    def test_wiring_symbols_present_in_owning_modules(self):
        """接线的最低结构判据：各符号在其**归属模块**中可调用。

        注意：这是**辅助**判据，不能作为接线的唯一证据 —— 符号 import 在而调用点
        被改掉时它照样绿（见上一条测试的说明）。

        2026-08-23：DSL→SQL 构建（含白名单/预算/PII 门禁调用）已从 router 抽到
        `services/custom_query/builder_dsl`（pre-commit 行数门禁要求「优先拆分或抽
        伴生模块」），故判据按归属模块分别断言，而不是一律查 router 命名空间。
        """
        import app.routers.query_builder as qb
        import app.services.custom_query.builder_dsl as dsl

        # router 侧：HTTP 层用到的
        for name in ("resolve_builder_scope", "scope_signature", "cancellable_query",
                     "visible_fields_for_role", "_build_select", "_stmt_to_sql"):
            assert callable(getattr(qb, name, None)), f"router 未接线 {name}"
        # 服务层侧：DSL→SQL 构建内的门禁
        for name in ("apply_scope_to_select", "enforce_complexity_budget",
                     "enforce_join_business_key", "enforce_pii_field_access",
                     "enforce_query_plan"):
            assert callable(getattr(dsl, name, None)), f"builder_dsl 未接线 {name}"


# ════════════════════════════════════════════════════════════════════════════
# UI 全中文化：默认列集必须全部有中文标签（跨语言真源锁死）
# ════════════════════════════════════════════════════════════════════════════
class TestDefaultColumnsHaveChineseLabels:
    """构建器默认列集的每一列都必须在前端 queryColumnLabels 里有中文映射。

    🔴 这条来自浏览器实测发现的缺口：构建器结果表里 `account_category` /
    `rje_adjustment` / `currency_code` 三列仍显示英文，而同表其他列已中文化 ——
    单元测试全绿、类型检查也无话可说，因为「缺一条 map 项」不是错误而是**缺失**。
    此后新增白名单列若忘了配中文，本守卫会打红。

    只覆盖 `default_fields`（用户默认会看到的列）；技术列显示英文可接受。
    """

    @staticmethod
    def _frontend_label_keys() -> set[str]:
        import re
        from pathlib import Path

        ts = (
            Path(__file__).resolve().parents[2]
            / "audit-platform"
            / "frontend"
            / "src"
            / "components"
            / "query"
            / "queryColumnLabels.ts"
        )
        source = ts.read_text(encoding="utf-8")
        # 去掉行注释，避免注释里的示例键被算作已映射
        source = re.sub(r"//[^\n]*", "", source)
        return set(re.findall(r"(\w+)\s*:\s*'[^']+'", source))

    def test_every_default_field_has_chinese_label(self):
        mapped = self._frontend_label_keys()
        missing: dict[str, list[str]] = {}
        for name, meta in TABLE_WHITELIST.items():
            gaps = [f for f in meta["default_fields"] if f not in mapped]
            if gaps:
                missing[name] = gaps
        assert not missing, (
            "以下默认列缺中文映射（请补 queryColumnLabels.ts）：\n"
            + "\n".join(f"  {t}: {sorted(cols)}" for t, cols in sorted(missing.items()))
        )

    def test_label_map_is_parseable(self):
        """反向自检：解析器至少要能认出一批已知键，否则上一条会假绿。"""
        mapped = self._frontend_label_keys()
        for known in ("account_name", "audited_amount", "opening_balance"):
            assert known in mapped, f"解析器未认出已知键 {known}，判据不可靠"
