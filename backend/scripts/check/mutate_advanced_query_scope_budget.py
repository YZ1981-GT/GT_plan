"""变异检验：advanced-query-hardening-wiring-closure 的作用域/预算/列分层/超时守卫。

用法::

    python backend/scripts/check/mutate_advanced_query_scope_budget.py            # 真跑变异
    python backend/scripts/check/mutate_advanced_query_scope_budget.py --check-anchors  # 只验锚点

判别四态（只看退出码会把后三态误判成 RED）：
  RED          变红且正是预期那条测试        ← 唯一合格
  GREEN        没变红                       ← 守卫有缺陷
  ANCHOR-MISS  锚点未命中或命中 >1 处        ← 脚本有缺陷
  WRONG-TEST   变红了但不是预期项            ← 锚点错行或污染残留
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
GUARD = "backend/tests/test_advanced_query_scope_budget_tiers.py"


@dataclass(frozen=True)
class Mutation:
    mid: str
    path: str
    old: str
    new: str
    expect_test: str
    why: str


MUTATIONS: tuple[Mutation, ...] = (
    # ── R6.1 JOIN 业务键 ──
    Mutation(
        "M01",
        "backend/app/services/custom_query/table_whitelist.py",
        '    "adjustments": {\n        # 已移除 `wp_index`',
        '    "adjustments": {\n        "wp_index": {"on": [("project_id", "project_id")]},\n        # 已移除 `wp_index`',
        "test_removed_cartesian_joins_are_absent",
        "把笛卡尔积 JOIN 加回登记表",
    ),
    Mutation(
        "M02",
        "backend/app/services/custom_query/table_whitelist.py",
        "    if not join_business_keys(on_pairs):",
        "    if False:",
        "test_scope_only_on_pairs_rejected",
        "JOIN 业务键校验空操作",
    ),
    Mutation(
        "M03",
        "backend/app/services/custom_query/table_whitelist.py",
        '    {"project_id", "year", "company_code", "is_deleted"}',
        '    {"company_code", "is_deleted"}',
        "test_non_business_keys_set_covers_scope_columns",
        "把 project_id 从非业务键集合移除",
    ),
    # ── R6.2/6.3 复杂度预算 ──
    Mutation(
        "M04",
        "backend/app/services/custom_query/table_whitelist.py",
        "MAX_JOINS_PER_QUERY = 3",
        "MAX_JOINS_PER_QUERY = 999",
        "test_budget_limits_are_within_sane_range",
        "JOIN 条数上限放到无意义大",
    ),
    Mutation(
        "M05",
        "backend/app/services/custom_query/table_whitelist.py",
        "        if actual > limit:",
        "        if False:",
        "test_over_budget_rejected",
        "复杂度预算校验空操作",
    ),
    # ── R7 列分层 ──
    Mutation(
        "M06",
        "backend/app/services/custom_query/table_whitelist.py",
        '    {"id", "project_id", "is_deleted", "created_at", "updated_at"}\n)',
        '    {"is_deleted", "created_at", "updated_at"}\n)',
        "test_technical_columns_are_recognized",
        "把 id/project_id 从技术列名单移除",
    ),
    Mutation(
        "M07",
        "backend/app/services/custom_query/table_whitelist.py",
        '    "staff_members": frozenset({"email", "phone", "user_id"}),',
        '    "staff_members": frozenset(),',
        "test_staff_pii_registered_and_excluded_from_default",
        "清空 PII 登记",
    ),
    Mutation(
        "M08",
        "backend/app/services/custom_query/table_whitelist.py",
        "        f for f in all_fields if f not in TECHNICAL_FIELD_NAMES and f not in pii_set",
        "        f for f in all_fields",
        "test_default_fields_exclude_technical_and_pii",
        "默认列集不再剔除技术列与 PII",
    ),
    Mutation(
        "M09",
        "backend/app/services/custom_query/table_whitelist.py",
        "    if _role_may_see_pii(role):\n        return\n    meta = TABLE_WHITELIST.get(table_name) or {}",
        "    if True:\n        return\n    meta = TABLE_WHITELIST.get(table_name) or {}",
        "test_unprivileged_roles_cannot_see_pii",
        "PII 准入校验空操作",
    ),
    Mutation(
        "M10",
        "backend/app/services/custom_query/table_whitelist.py",
        "    denied = sorted(\n        {f for f in (str(x).split(\".\")[-1] for x in requested_fields) if f in pii}\n    )",
        "    denied = sorted({f for f in requested_fields if f in pii})",
        "test_pii_check_handles_two_segment_field_syntax",
        "PII 校验不再处理 table.field 双段语法",
    ),
    # ── R2 构建器作用域 ──
    Mutation(
        "M11",
        "backend/app/services/custom_query/builder_scope.py",
        "    return stmt.where(column.in_(list(scope.project_ids or ())))",
        "    return stmt",
        "test_scoped_user_gets_project_filter_in_sql",
        "作用域过滤不注入（回到改造前行为）",
    ),
    Mutation(
        "M12",
        "backend/app/services/custom_query/builder_scope.py",
        "    if scope.is_all_projects:\n        return stmt\n    column = _scope_column(table_name)",
        "    if True:\n        return stmt\n    column = _scope_column(table_name)",
        "test_scope_is_applied_by_build_select",
        "所有查询都当作全项目、跳过过滤",
    ),
    Mutation(
        "M13",
        "backend/app/services/custom_query/builder_scope.py",
        '    joined = ",".join(sorted(str(pid) for pid in (scope.project_ids or ())))\n    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:32]',
        '    return "fixed"',
        "test_scope_signature_isolates_different_scopes",
        "作用域签名恒定（缓存跨作用域串）",
    ),
    Mutation(
        "M14",
        "backend/app/services/custom_query/builder_scope.py",
        '        warnings.append(\n            "当前账号未被分派任何项目，查询范围为空；请联系项目经理分派后重试"\n        )',
        "        pass",
        "test_empty_accessible_set_yields_warning_not_silent_empty",
        "空作用域静默返回空结果、无提示",
    ),
    Mutation(
        "M15",
        "backend/app/services/custom_query/builder_scope.py",
        "        await ownership_guard.assert_target_accessible(\n            user=user, project_id=requested_project_id, db=db\n        )",
        "        pass",
        "test_explicit_inaccessible_project_rejected",
        "显式指定项目时跳过归属校验",
    ),
    Mutation(
        "M16",
        "backend/app/services/custom_query/builder_scope.py",
        'GLOBAL_CONFIG_TABLES: frozenset[str] = frozenset({"report_config"})',
        'GLOBAL_CONFIG_TABLES: frozenset[str] = frozenset({"report_config", "trial_balance"})',
        "test_global_config_tables_really_lack_project_column",
        "把有 project_id 的表误登记为全局配置表（会绕过作用域）",
    ),
    # ── R6.4 超时 ──
    Mutation(
        "M17",
        "backend/app/services/custom_query/execution_guard.py",
        'text(f"SET LOCAL statement_timeout = {int(timeout_ms)}")',
        'text(f"SET statement_timeout = {int(timeout_ms)}")',
        "test_uses_set_local_not_session_wide_set",
        "改用会话级 SET（污染连接池中被复用的连接）",
    ),
    Mutation(
        "M18",
        "backend/app/services/custom_query/execution_guard.py",
        "        await db.execute(\n            text(f\"SET LOCAL statement_timeout = {int(timeout_ms)}\")\n        )",
        "        pass",
        "test_statement_timeout_is_actually_issued",
        "根本不设超时（回到改造前 statement_timeout=0）",
    ),
    Mutation(
        "M19",
        "backend/app/services/custom_query/execution_guard.py",
        "            if is_query_canceled(exc):",
        "            if False:",
        "test_timeout_maps_to_408_not_empty_result",
        "超时不再映射为 408",
    ),
    Mutation(
        "M20",
        "backend/app/services/custom_query/execution_guard.py",
        "        except asyncio.CancelledError:\n            try:\n                await db.rollback()",
        "        except asyncio.CancelledError:\n            try:\n                pass",
        "test_client_disconnect_rolls_back_and_propagates",
        "客户端断开不回滚（连接留着跑）",
    ),
    # ── 接线判据 ──
    Mutation(
        "M21",
        "backend/app/services/custom_query/builder_dsl.py",
        '        default_fields = table_meta.get("default_fields") or table_meta["fields"]',
        '        default_fields = table_meta["fields"]',
        "test_default_select_excludes_technical_columns",
        "构建器默认列改回全字段（首列又是 UUID）",
    ),
    Mutation(
        "M22",
        "backend/app/services/custom_query/builder_dsl.py",
        "    if scope is not None:\n        stmt = apply_scope_to_select(stmt, scope=scope, table_name=dsl.table)",
        "    if False:\n        stmt = apply_scope_to_select(stmt, scope=scope, table_name=dsl.table)",
        "test_scope_is_applied_by_build_select",
        "router 不再调用作用域注入（服务层沦为死代码）",
    ),
    Mutation(
        "M23",
        "backend/app/services/custom_query/builder_dsl.py",
        "    enforce_complexity_budget(\n        joins=len(dsl.joins),",
        "    _skip_budget = (\n        len(dsl.joins),",
        "test_complexity_budget_is_enforced_by_build_select",
        "router 不再调用复杂度预算",
    ),
    Mutation(
        "M24",
        "backend/app/services/custom_query/builder_dsl.py",
        "    if requested:\n        enforce_pii_field_access(dsl.table, requested, role)",
        "    if False:\n        enforce_pii_field_access(dsl.table, requested, role)",
        "test_pii_access_is_enforced_by_build_select",
        "router 不再调用 PII 准入",
    ),
    Mutation(
        "M25",
        "backend/app/services/custom_query/builder_dsl.py",
        "    if not order_cols and not dsl.group_by and not dsl.aggregates:\n        tie_col = getattr(model, \"id\", None)",
        "    if False:\n        tie_col = getattr(model, \"id\", None)",
        "test_offset_without_order_by_gets_tie_breaker",
        "构建器 offset 分页不再补稳定排序键",
    ),
    Mutation(
        "M26",
        "backend/app/routers/query_builder.py",
        '                "fields": visible_fields_for_role(name, role),',
        '                "fields": meta["fields"],',
        "test_schema_endpoint_filters_pii_by_role",
        "schema 不再按角色隐去 PII",
    ),
)


def _read(path: str) -> str:
    return (REPO / path).read_text(encoding="utf-8")


def _write(path: str, text: str) -> None:
    (REPO / path).write_text(text, encoding="utf-8")


def check_anchors() -> int:
    """只读校验每个锚点在目标文件中恰好命中一次。"""
    bad = 0
    for m in MUTATIONS:
        try:
            src = _read(m.path)
        except OSError as exc:
            print(f"{m.mid}  ANCHOR-MISS  无法读取 {m.path}: {exc}")
            bad += 1
            continue
        hits = src.count(m.old)
        if hits != 1:
            print(f"{m.mid}  ANCHOR-MISS  命中 {hits} 次（需恰好 1）: {m.why}")
            bad += 1
        else:
            print(f"{m.mid}  OK           {m.why}")
    print(f"\n锚点校验：{len(MUTATIONS) - bad}/{len(MUTATIONS)} OK，{bad} MISS")
    return 1 if bad else 0


def _run_guard(expect_test: str) -> tuple[bool, bool]:
    """跑守卫；返回 (整体是否失败, 预期测试是否失败)。"""
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", GUARD, "-q", "--tb=no", "-p", "no:cacheprovider"],
        cwd=REPO,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    overall_failed = proc.returncode != 0
    expected_failed = any(
        line.startswith("FAILED") and expect_test in line for line in out.splitlines()
    )
    # 收集期错误（如导入期不变式抛 RuntimeError）也算「打红」，但要单独识别
    if not expected_failed and ("error" in out.lower() and "RuntimeError" in out):
        expected_failed = True
    return overall_failed, expected_failed


def run_mutations() -> int:
    # 先确认基线全绿，否则无法区分「变异打红」与「本来就红」
    base_failed, _ = _run_guard("__none__")
    if base_failed:
        print("基线未全绿，变异检验无意义，请先修复守卫")
        return 1

    verdicts: dict[str, str] = {}
    for m in MUTATIONS:
        original = _read(m.path)
        if original.count(m.old) != 1:
            verdicts[m.mid] = "ANCHOR-MISS"
            print(f"{m.mid}  ANCHOR-MISS  {m.why}")
            continue
        try:
            _write(m.path, original.replace(m.old, m.new, 1))
            overall_failed, expected_failed = _run_guard(m.expect_test)
            if not overall_failed:
                verdict = "GREEN"
            elif expected_failed:
                verdict = "RED"
            else:
                verdict = "WRONG-TEST"
        finally:
            _write(m.path, original)  # 无论如何恢复
        verdicts[m.mid] = verdict
        print(f"{m.mid}  {verdict:<12} {m.why}")

    counts = {v: sum(1 for x in verdicts.values() if x == v) for v in set(verdicts.values())}
    print("\n判定汇总：" + "  ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    ok = counts.get("RED", 0) == len(MUTATIONS)
    print("全部 RED" if ok else "存在非 RED 项，需修守卫或修脚本")
    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-anchors", action="store_true", help="只校验锚点，不改文件")
    parser.add_argument("--group", choices=("all", "scope", "lazy", "pbt"), default="all")
    args = parser.parse_args()
    if args.check_anchors:
        rc = check_anchors()
        print("\n── 指标树组锚点 ──")
        for m in LAZY_MUTATIONS:
            hits = _read(m.path).count(m.old)
            print(f"{m.mid}  {'OK' if hits == 1 else f'ANCHOR-MISS({hits})'}  {m.why}")
            if hits != 1:
                rc = 1
        return rc
    if args.group == "scope":
        return run_mutations()
    if args.group == "lazy":
        return run_lazy_mutations()
    if args.group == "pbt":
        return run_pbt_mutations()
    return run_mutations() or run_lazy_mutations() or run_pbt_mutations()


# ─────────────────────────────────────────────────────────────────────────────
# 第二批：指标树懒加载（R12）
# 单独成组以便按需只跑这一批；判定逻辑与上面完全一致。
# ─────────────────────────────────────────────────────────────────────────────
LAZY_GUARD = "backend/tests/test_advanced_query_indicators_lazy.py"

LAZY_MUTATIONS: tuple[Mutation, ...] = (
    Mutation(
        "L01",
        "backend/app/routers/custom_query.py",
        "    skeleton = isinstance(depth, int) and depth <= 1",
        "    skeleton = False",
        "test_depth1_skeleton_is_significantly_smaller",
        "depth=1 不再产生骨架（回到全量）",
    ),
    Mutation(
        "L02",
        "backend/app/routers/custom_query.py",
        '        "children": [] if skeleton else await _build_workpaper_tree(db, project_id),',
        '        "children": await _build_workpaper_tree(db, project_id),',
        "test_lazy_branches_marked_and_emptied",
        "底稿树在骨架中仍内联（首屏体积不降）",
    ),
    Mutation(
        "L03",
        "backend/app/routers/custom_query.py",
        "    disclosure_children = [] if skeleton else await _build_disclosure_tree(template_type)",
        "    disclosure_children = await _build_disclosure_tree(template_type)",
        "test_lazy_branches_marked_and_emptied",
        "附注树在骨架中仍内联",
    ),
    Mutation(
        "L04",
        "backend/app/routers/custom_query.py",
        "    branch_key = branch if isinstance(branch, str) and branch else None",
        "    branch_key = branch",
        "test_query_object_defaults_treated_as_absent",
        "改回真值判断（直调时 Query 实例被当成分支名）",
    ),
    Mutation(
        "L05",
        "backend/app/routers/custom_query.py",
        '    if branch == "workpaper":\n        return await _build_workpaper_tree(db, project_id)',
        '    if branch == "workpaper":\n        return []',
        "test_branch_returns_only_that_subtree",
        "分支加载返回空（展开后看不到内容）",
    ),
    Mutation(
        "L06",
        "backend/app/routers/custom_query.py",
        '    raise HTTPException(\n        status_code=400,\n        detail={\n            "error_code": "UNKNOWN_INDICATOR_BRANCH",',
        '    return []\n    raise HTTPException(\n        status_code=400,\n        detail={\n            "error_code": "UNKNOWN_INDICATOR_BRANCH",',
        "test_unknown_branch_returns_400_not_empty",
        "未知分支静默返回空数组而非 400",
    ),
    Mutation(
        "L07",
        "backend/app/routers/custom_query.py",
        "_INDICATORS_SCHEMA_VERSION = 10",
        "_INDICATORS_SCHEMA_VERSION = 9",
        "test_schema_version_bumped_for_lazy_fields",
        "schema 版本未升（前端旧缓存不失效）",
    ),
    Mutation(
        "L08",
        "backend/app/routers/custom_query.py",
        '        "children": disclosure_children,\n        "lazy": skeleton,',
        '        "children": disclosure_children,',
        "test_lazy_branches_marked_and_emptied",
        "节点不再标 lazy（前端无从判断是否需要按需加载）",
    ),
)


def _run_named_guard(guard: str, expect_test: str) -> tuple[bool, bool]:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", guard, "-q", "--tb=no", "-p", "no:cacheprovider"],
        cwd=REPO,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    expected_failed = any(
        line.startswith("FAILED") and expect_test in line for line in out.splitlines()
    )
    return proc.returncode != 0, expected_failed


def run_lazy_mutations() -> int:
    base_failed, _ = _run_named_guard(LAZY_GUARD, "__none__")
    if base_failed:
        print("指标树守卫基线未全绿，变异无意义")
        return 1
    verdicts: dict[str, str] = {}
    for m in LAZY_MUTATIONS:
        original = _read(m.path)
        if original.count(m.old) != 1:
            verdicts[m.mid] = "ANCHOR-MISS"
            print(f"{m.mid}  ANCHOR-MISS  {m.why}")
            continue
        try:
            _write(m.path, original.replace(m.old, m.new, 1))
            overall, expected = _run_named_guard(LAZY_GUARD, m.expect_test)
            verdict = "GREEN" if not overall else ("RED" if expected else "WRONG-TEST")
        finally:
            _write(m.path, original)
        verdicts[m.mid] = verdict
        print(f"{m.mid}  {verdict:<12} {m.why}")
    counts = {v: sum(1 for x in verdicts.values() if x == v) for v in set(verdicts.values())}
    print("\n指标树判定汇总：" + "  ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    return 0 if counts.get("RED", 0) == len(LAZY_MUTATIONS) else 1


# （入口已移至文件真正末尾，见文件底部）


# ─────────────────────────────────────────────────────────────────────────────
# 第三批：Property（PBT）与拒绝审计 / DDL 交叉锁死
# ─────────────────────────────────────────────────────────────────────────────
# PBT 已按域拆两个文件（原单文件 917 行触发 pre-commit 行数门禁）：
#   PBT_GUARD       = 契约与分页域（P7/P8/P9~P13/P15~P18）
#   PBT_SCOPE_GUARD = 作用域·执行路径·治理·只读门禁域（P1~P6/P14/P19~P24）
# 变异的 expect_test 落在哪个域，就要用对应文件当判据 —— 用错文件会得到
# WRONG-TEST 或 GREEN（那正是「守卫层级/范围错」的假绿形态）。
PBT_GUARD = "backend/tests/test_advanced_query_hardening_properties.py"
PBT_SCOPE_GUARD = "backend/tests/test_advanced_query_hardening_properties_scope.py"
CROSS_GUARD = "backend/tests/test_advanced_query_ddl_cross_lock.py"

PBT_MUTATIONS: tuple[tuple[Mutation, str], ...] = (
    (
        Mutation(
            "P01",
            "backend/app/services/custom_query/query_orchestrator.py",
            '                source=c.get("source"),',
            "",
            "test_p8_query_result_payload_roundtrip_is_lossless",
            "from_payload 漏还原 source（缓存命中与否响应形态分叉）",
        ),
        PBT_GUARD,
    ),
    (
        Mutation(
            "P02",
            "backend/app/services/custom_query/query_orchestrator.py",
            # 带 warnings 前缀以区分 cache_def 中同名的 limit/offset 两行
            '            "warnings": self.warnings,\n            "limit": self.limit,\n            "offset": self.offset,',
            '            "warnings": self.warnings,',
            "test_p8_query_result_payload_roundtrip_is_lossless",
            "to_payload 漏 limit/offset",
        ),
        PBT_GUARD,
    ),
    (
        Mutation(
            "P03",
            "backend/app/services/custom_query/pagination.py",
            "    keys.extend(_tie_breaker_keys(available, used))",
            "    pass",
            "test_p10_tie_breaker_is_appended_never_replaces_user_sort",
            "不再追加 tie-breaker（翻页顺序不确定）",
        ),
        PBT_GUARD,
    ),
    (
        Mutation(
            "P04",
            "backend/app/services/custom_query/pagination.py",
            "    ordered = sort_rows(rows, sort)\n    total = len(ordered)",
            "    ordered = sort_rows(rows, sort)\n    total = min(len(ordered), limit)",
            "test_p12_all_pages_union_equals_full_set_without_overlap",
            "total 退化为「本页行数」（前端无从判断有无下一页）",
        ),
        PBT_GUARD,
    ),
    (
        Mutation(
            "P05",
            "backend/app/services/custom_query/pagination.py",
            "    page = ordered[offset : offset + limit] if offset < total else []",
            "    page = ordered[:limit]",
            "test_p12_all_pages_union_equals_full_set_without_overlap",
            "忽略 offset（每页都返回第 1 页）",
        ),
        PBT_GUARD,
    ),
    (
        Mutation(
            "P06",
            "backend/app/services/custom_query/query_orchestrator.py",
            "        paged = apply_pagination(\n            rows, sort=sort_keys, limit=req.limit, offset=req.offset\n        )",
            "        paged = apply_pagination(\n            rows, sort=[], limit=req.limit, offset=req.offset\n        )",
            "test_p11_orchestrator_actually_applies_user_sort",
            "编排器丢弃排序键",
        ),
        PBT_GUARD,
    ),
    (
        Mutation(
            "P07",
            "backend/app/routers/custom_query.py",
            "    limit: int = Field(default=500, ge=PAGE_MIN_LIMIT, le=PAGE_MAX_LIMIT)",
            "    limit: int = 500",
            "test_p13_out_of_range_limit_rejected_at_both_entries",
            "pydantic 层去掉 limit 边界",
        ),
        PBT_GUARD,
    ),
    (
        Mutation(
            "P08",
            "backend/app/services/custom_query/table_whitelist.py",
            "    pii_cols = [f for f in all_fields if f in pii_set]",
            "    pii_cols = []",
            "test_p17_tiers_partition_fields_without_loss_or_overlap",
            "PII 列不再单独成层（会混进默认列）",
        ),
        PBT_GUARD,
    ),
    (
        Mutation(
            "P09",
            "audit-platform/frontend/src/composables/useQueryBuilderAccess.ts",
            "export const QUERY_BUILDER_ROLES = ['admin', 'manager', 'partner'] as const",
            "export const QUERY_BUILDER_ROLES = ['admin', 'manager'] as const",
            "test_p23_frontend_builder_roles_match_backend_whitelist",
            "前端角色白名单与后端漂移",
        ),
        PBT_SCOPE_GUARD,
    ),
    (
        Mutation(
            "P10",
            "backend/app/routers/custom_query.py",
            "    if project_id:\n        from app.services.custom_query.ownership_guard import ownership_guard\n\n        await ownership_guard.assert_target_accessible(",
            "    if False:\n        from app.services.custom_query.ownership_guard import ownership_guard\n\n        await ownership_guard.assert_target_accessible(",
            "test_p2_indicators_gate_precedes_all_domain_reads",
            "indicators 不再做归属校验（回到未认证可读）",
        ),
        PBT_SCOPE_GUARD,
    ),
    # ── 拒绝审计 / DDL 交叉锁死 ──
    (
        Mutation(
            "P11",
            "backend/app/services/custom_query/audit_helper.py",
            '    "COMPLEXITY_BUDGET_EXCEEDED": ACTION_QUERY_BUDGET_DENIED,',
            '    "COMPLEXITY_BUDGET_EXCEEDED": ACTION_QUERY_TIMEOUT,',
            "test_each_rejection_kind_has_distinct_action",
            "两类拒绝共用同一动作名（审计不可区分）",
        ),
        CROSS_GUARD,
    ),
    (
        Mutation(
            "P12",
            "backend/app/routers/custom_query.py",
            "        await record_query_rejected(\n            user_id=current_user.id,",
            "        await _noop_record(\n            user_id=current_user.id,",
            "test_custom_query_execute_records_timeout_rejection",
            "router 不再记拒绝审计（服务层沦为死代码）",
        ),
        CROSS_GUARD,
    ),
    (
        Mutation(
            "P13",
            "backend/scripts/_ensure_custom_query_tables.py",
            '    "shared_project_ids",\n    "tags",',
            '    "tags",',
            "test_declared_columns_equal_orm_columns",
            "脚本列集与 ORM 漂移",
        ),
        CROSS_GUARD,
    ),
    (
        Mutation(
            "P14",
            "backend/scripts/_ensure_custom_query_tables.py",
            '    "idx_cqt_shared_projects",\n)',
            ")",
            "test_index_names_equal_orm_idx_cqt_indexes",
            "脚本索引集与 ORM 漂移",
        ),
        CROSS_GUARD,
    ),
)


def run_pbt_mutations() -> int:
    verdicts: dict[str, str] = {}
    for m, guard in PBT_MUTATIONS:
        base_failed, _ = _run_named_guard(guard, "__none__")
        if base_failed:
            print(f"{m.mid}  SKIP(基线红)  {m.why}")
            verdicts[m.mid] = "BASE-RED"
            continue
        original = _read(m.path)
        if original.count(m.old) != 1:
            verdicts[m.mid] = "ANCHOR-MISS"
            print(f"{m.mid}  ANCHOR-MISS  {m.why}")
            continue
        try:
            _write(m.path, original.replace(m.old, m.new, 1))
            overall, expected = _run_named_guard(guard, m.expect_test)
            verdict = "GREEN" if not overall else ("RED" if expected else "WRONG-TEST")
        finally:
            _write(m.path, original)
        verdicts[m.mid] = verdict
        print(f"{m.mid}  {verdict:<12} {m.why}")
    counts = {v: sum(1 for x in verdicts.values() if x == v) for v in set(verdicts.values())}
    print("\nPBT 判定汇总：" + "  ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    return 0 if counts.get("RED", 0) == len(PBT_MUTATIONS) else 1


# ─────────────────────────────────────────────────────────────────────────────
# 入口必须置于文件**真正末尾**：本脚本按批次增量追加，各批的 MUTATIONS 常量与
# run_*_mutations 函数都定义在 main() 之后。入口一旦写在中间，模块执行到
# sys.exit(main()) 时后续定义尚未求值 → NameError（本脚本已因此踩过两次）。
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    sys.exit(main())
