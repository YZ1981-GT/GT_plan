"""S-3 高级查询构建器 — 可视化条件 → SQLAlchemy core 安全构造 → 执行/预览/导出

POST /api/query/preview      预览生成的 SQL（不执行）
POST /api/query/execute      执行查询，返回结构化结果
POST /api/query/export-excel 导出全部（服务端流式、不分页；> 1,000,000 行 400，不截断）
GET  /api/query/schema       返回白名单表/字段元信息（前端用于构造可视化选择器）
GET  /api/query/access       当前用户能否使用构建器、作用域内项目数与置灰原因（前端入口与后端判定同源）

设计要点：
- 仅允许查询白名单的只读 audit/财务表（trial_balance / working_paper / wp_index /
  adjustments / unadjusted_misstatements / report_line_mapping / report_config /
  account_chart / tb_balance / tb_ledger / materiality）
- 完全使用 SQLAlchemy core `select()` 按列引用构造，**不做字符串拼接**，
  绑定参数走 SQLAlchemy bindparam，杜绝 SQL 注入
- 字段名/表名/操作符/排序方向通过白名单核对后才写入 query
- 准入：系统角色 admin / partner / manager，或任一未删除项目的项目经理 / 合伙人（edit 级）
  （``services/custom_query/builder_access``，ADR-AQL-08）；能查哪些项目由构建器作用域决定
- 不暴露 user / role / token / auth 表

注册到 router_registry.system 域 §117。

Validates: requirements §三 · S-3 高级查询构建器
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
# 白名单单一真源在 services/custom_query/table_whitelist；DSL→SQL 构建在
# services/custom_query/builder_dsl（见下方 re-export 段）。router 只保留 HTTP 层。
from app.services.custom_query.builder_access import (
    FORBIDDEN_REASON,
    SYSTEM_BUILDER_ROLES,
    builder_admission,
    resolve_builder_access,
)
from app.services.custom_query.acnr_target_values import acnr_sheet, plan_builder_targets, with_acnr_results
from app.services.custom_query import count_token as count_tokens
from app.services.custom_query.builder_scope import (
    BuilderScope,
    resolve_builder_scope,
    scope_signature,
)
from app.services.custom_query.execution_guard import (
    QUERY_TIMEOUT_MS,
    cancellable_query,
)
from app.services.custom_query.table_whitelist import (
    AGGREGATE_WHITELIST,
    JOIN_WHITELIST,
    OPERATOR_WHITELIST,
    PII_ALLOWED_ROLES,
    TABLE_WHITELIST,
    visible_fields_for_role,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/query", tags=["query-builder"])


# ─────────────────────────────────────────────────────────────────────────────
# 准入：系统角色 admin / manager / partner，或任一未删除项目的项目经理 / 合伙人（edit 级）
# ─────────────────────────────────────────────────────────────────────────────
def _get_role_value(user: User) -> str:
    role = getattr(user, "role", "")
    return role.value if hasattr(role, "value") else str(role)


# 凭系统角色即可使用构建器的角色（R11.2）：真源在 builder_access，此处引用同一对象。
# 系统角色不在其中的用户，凭项目成员行（项目经理 / 合伙人、edit 级）也可使用（AQ-21）。
_QUERY_BUILDER_ROLES = SYSTEM_BUILDER_ROLES


def _forbidden() -> HTTPException:
    return HTTPException(status_code=403, detail={"error_code": "ROLE_FORBIDDEN", "message": FORBIDDEN_REASON})


def _require_admin_or_manager(user: User) -> None:
    """系统角色门禁纯函数（不含项目经理分支，保留供内部 / 测试直接调用）。

    error_code 对齐 design.md Error Handling 表：构建器角色不足 → ``ROLE_FORBIDDEN`` 403。
    """
    if _get_role_value(user) not in _QUERY_BUILDER_ROLES:
        raise _forbidden()


async def require_query_builder_access(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    """FastAPI 依赖：白名单构建器统一准入门禁（R3.6 / R11.2 / R11.3）。

    作为 Whitelist_Query_Builder 全部端点的单点准入依赖注入，判定只在 ``builder_access.builder_admission``
    （与 ``GET /api/query/access`` 同一实现）。未认证请求由 ``get_current_user`` 先行拦截（R11.4）；已认证但没有准入
    → 403 ``ROLE_FORBIDDEN``（中文原因含合伙人与项目经理，AQ-29）。
    """
    if not (await builder_admission(current_user, db)).allowed:
        raise _forbidden()
    return current_user


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic 模型 — DSL 严格校验
# ─────────────────────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────
# DSL 契约与 DSL → SQL 构建已抽到服务层 `services/custom_query/builder_dsl.py`
# （pre-commit 行数门禁指引「优先拆分或抽伴生模块」；DSL→SQL 本就属服务层职责）。
# 此处 re-export，保持 `from app.routers.query_builder import QueryDSL,
# _build_select` 等既有导入与测试不变。
# ─────────────────────────────────────────────────────────────────────────────
from app.services.custom_query.builder_dsl import (  # noqa: E402
    ExportDSL,
    FilterCond,
    OrderBy,
    QueryDSL,
    _build_filter,
    _build_select,
    build_count,
    _coerce_value,
    _excel_cell_value,
    _resolve_column,
    _resolve_field_ref,
    _resolve_table,
    _serialize_cell,
    _stmt_to_sql,
)

# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/schema")
async def get_schema(
    current_user: User = Depends(require_query_builder_access),
):
    """返回白名单表/字段元信息（前端用于构造可视化选择器）。

    S-3 v2：joins 字段列出当前表可关联的目标表 + 关联条件
    """
    role = _get_role_value(current_user)
    return {
        "tables": [
            {
                "name": name,
                "label": meta["label"],
                # 按角色隐去无权 PII 列（R7.4）；分三层下发使前端默认只展示业务列
                # （R7.2），列名真源仍是本白名单、前端不复制第二份（R7.5）。
                "fields": visible_fields_for_role(name, role),
                "default_fields": meta.get("default_fields") or [],
                "technical_fields": meta.get("technical_fields") or [],
                # 角色判据复用 PII_ALLOWED_ROLES 单一真源，不在此内联第二份角色表
                "pii_fields": (
                    meta.get("pii_fields") or [] if role in PII_ALLOWED_ROLES else []
                ),
                "joins": [
                    {
                        "target_table": target,
                        "target_label": TABLE_WHITELIST[target]["label"],
                        "on": [
                            {"left_field": l, "right_field": r}
                            for l, r in spec["on"]
                        ],
                        # many_to_one / one_to_many：一对多的关联会放大结果行数（R3.4）
                        "cardinality": spec["cardinality"],
                    }
                    for target, spec in JOIN_WHITELIST.get(name, {}).items()
                    if target in TABLE_WHITELIST
                ],
            }
            for name, meta in TABLE_WHITELIST.items()
        ],
        "operators": sorted(OPERATOR_WHITELIST),
        "aggregates": sorted(AGGREGATE_WHITELIST),
    }


@router.get("/access")
async def get_access(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """当前用户能否使用构建器（前端入口据此置灰并显示原因，与后端门禁同一判定，R3.6）。

    返回 ``allowed`` / ``basis`` / ``reason`` / ``all_projects`` / ``accessible_project_count``：admin / partner 不限项目
    （计数为 null）；其余身份的计数按构建器作用域计（与执行时同一函数），为 0 时 ``reason`` 写明原因。
    """
    return (await resolve_builder_access(current_user, db)).to_dict()


async def _builder_scope(
    body: QueryDSL, *, user: User, db: AsyncSession, requested_project_id: Any, year: int | None
) -> BuilderScope:
    """解析作用域；人员表角色门（``TABLE_ROLE_FORBIDDEN``）等可区分拒绝记审计后原样上抛（R5.5）。"""
    try:
        return await resolve_builder_scope(
            user=user,
            dsl_tables=[body.table, *(j.get("table", "") for j in body.joins)],
            requested_project_id=requested_project_id,
            year=year,
            db=db,
        )
    except HTTPException as http_exc:
        await _audit_query_rejection(http_exc, user=user, table=body.table)
        raise


@router.post("/preview")
async def preview_query(
    body: QueryDSL,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_query_builder_access),
):
    """仅生成 SQL（不执行），用于前端"SQL 预览"。

    预览也必须带上作用域约束 —— 否则用户看到的 SQL 与实际执行的 SQL 不一致，
    「预览无 WHERE project_id」正是本次改造前实测到的现象。
    """
    warnings: list[str] = []
    scope = await _builder_scope(
        body, user=current_user, db=db, requested_project_id=body.project_id, year=body.year
    )
    acnr = await plan_builder_targets(body, db=db)  # 只解析不取值（acnr design §2.2）
    stmt, column_names = _build_select(
        body, scope=scope, role=_get_role_value(current_user), warnings=warnings
    )
    payload = {
        "sql": _stmt_to_sql(stmt),
        "columns": column_names,
        "table": body.table,
        "scope": scope.describe(),
        "warnings": warnings,
    }
    return payload if acnr is None else {**payload, "acnr_resolved": await acnr.preview(db)}


async def _audit_query_rejection(
    exc: HTTPException, *, user: User, table: str
) -> None:
    """把构建器侧的拒绝事件记成可区分审计（R5.5）。

    只对已登记的 error_code 记录（超时 / 预算超限 / PII 越权）；其余 4xx 属参数
    校验类噪声，不入审计。审计失败由 ``record_query_rejected`` 内部吞掉，
    不会掩盖 ``exc`` 本身。
    """
    from app.services.custom_query.audit_helper import record_query_rejected

    detail = exc.detail if isinstance(exc.detail, dict) else {}
    await record_query_rejected(
        user_id=user.id,
        error_code=detail.get("error_code"),
        source=f"builder:{table}",
        details={"status_code": exc.status_code, "table": table},
    )


def _derive_formula_refs(table: str, rows: list[dict]) -> list[str | None]:
    """为查询结果每行派生可用的公式引用语法（无法定位返回 None；R3.7，ADR-AQL-18）。

    只给试算表行：``TB('{standard_account_code}','审定数')``，与 ``address_registry.formula_ref_to_uri`` 的 ref 语法
    一致，前端可直接校验或复制进公式编辑器。

    科目余额表（tb_balance）行不再生成（AQ-27）：原先给的 ``TB('{客户科目码}','期末')`` 有两处错——TB 域按**标准**科目码
    取数（客户科目码不属于 TB 域），「期末」也不是试算表列名（地址库认 审定数 / 未审数 / 期末余额 等）——地址库校验判无效。
    旧的写法闭包测试只用「能解析成 URI」判它，``#cell`` 段原样透传，恒成立，是假绿。其余表无稳定单值定位语义。
    """
    if table != "trial_balance":
        return [None] * len(rows)
    refs: list[str | None] = []
    for row in rows:
        code = row.get("standard_account_code")
        refs.append(f"TB('{code}','审定数')" if code else None)
    return refs


@router.post("/execute")
async def execute_query(
    body: QueryDSL,
    response: Response,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_query_builder_access),
):
    """执行查询，返回结构化结果（``total`` 为全量行数，分组时为组数）。"""
    warnings: list[str] = []
    # ─── 项目作用域（R2）：解析先于 SQL 构建与缓存读取 ────────────────────
    scope = await _builder_scope(
        body, user=current_user, db=db, requested_project_id=body.project_id, year=body.year
    )
    # acnr_targets：作用域判定（项目归属）之后、SQL 与缓存之前解析；拒绝即 422 / 503，不执行查询
    acnr = await plan_builder_targets(body, db=db)
    try:
        stmt, column_names = _build_select(
            body, scope=scope, role=_get_role_value(current_user), warnings=warnings
        )
    except HTTPException as http_exc:
        # 预算超限 / PII 越权发生在 SQL 构建期，也要留痕
        await _audit_query_rejection(http_exc, user=current_user, table=body.table)
        raise

    # ─── Redis 短 TTL 缓存（dashboard 卡片高频查询）────────────────────
    # 缓存发生在白名单安全校验之后（_build_select 已完成白名单验证）
    from app.services.query_cache import compute_cache_key, get_cached_result, set_cached_result

    # 缓存键纳入作用域签名（R2.4）：改造前写死 "__query_builder__"，两个可访问
    # 项目集合不同的用户对同一 DSL 会命中同一条缓存 = 跨作用域泄漏。
    cache_key = compute_cache_key(
        user_id=str(current_user.id),
        project_id=f"__query_builder__:{scope_signature(scope)}",
        query_params=body.model_dump(exclude={"count_token"}),
    )
    cached = await get_cached_result(cache_key)
    if cached is not None:
        response.headers["X-Cache"] = "HIT"
        return with_acnr_results(cached, await acnr.results(db) if acnr else None)

    try:
        async with cancellable_query(db, QUERY_TIMEOUT_MS):
            # total 对同一语句计数（R2.6）；后续页可带服务端签名凭证跳过重复 COUNT。
            # 不分组的聚合恒为一行（与 offset 无关），无需另跑计数。
            ungrouped_aggregate = bool(body.aggregates) and not body.group_by
            count_reused = False
            next_count_token: str | None = None
            if ungrouped_aggregate:
                total = 1
            else:
                count_stmt = build_count(stmt)
                count_subject = count_tokens.subject_of(current_user)
                count_digest = count_tokens.statement_digest(count_stmt, db.get_bind(), subject=count_subject)
                reused_total = count_tokens.reuse(body.count_token, digest=count_digest, subject=count_subject)
                count_reused = reused_total is not None
                total = int(reused_total) if count_reused else (await db.execute(count_stmt)).scalar_one()
                next_count_token = count_tokens.issue(digest=count_digest, total=int(total), subject=count_subject)
            result = await db.execute(stmt)
            rows = result.fetchall()
    except HTTPException as http_exc:
        # 408 QUERY_TIMEOUT 等原样上抛，同时记一条可区分审计（R5.5）
        await _audit_query_rejection(http_exc, user=current_user, table=body.table)
        raise
    except SQLAlchemyError as exc:
        try:
            await db.rollback()
        except Exception:
            pass
        logger.exception("query_builder execute failed")
        raise HTTPException(
            status_code=400,
            detail={"error_code": "QUERY_EXECUTION_FAILED",
                    "message": f"查询执行失败：{exc}"},
        )

    rows_serialized: list[dict] = []
    for r in rows:
        obj: dict[str, Any] = {}
        for idx, col_name in enumerate(column_names):
            v = r[idx] if idx < len(r) else None
            obj[col_name] = _serialize_cell(v)
        rows_serialized.append(obj)

    query_result = {
        "rows": rows_serialized,
        "columns": column_names,
        "total": int(total),
        "count_token": next_count_token,
        "count_reused": count_reused,
        "table": body.table,
        "sql": _stmt_to_sql(stmt),
        # 明示本次生效的项目范围（R2.2）：admin/partner 不限项目时也要让用户知道
        # 自己正在跨项目查询，而不是默认以为只看了当前项目。
        "scope": scope.describe(),
        "warnings": warnings,
        # P2-6: 自由查询结果反哺结构化引用——每行（若可定位）给出对应公式 ref，
        # 审计师可一键复制到公式编辑器，打通"探查→引用"链路。
        "formula_refs": _derive_formula_refs(body.table, rows_serialized),
    }

    # 回写 Redis 缓存（短 TTL）；单元格取值每次现读，不进缓存
    await set_cached_result(cache_key, query_result)

    return with_acnr_results(query_result, await acnr.results(db) if acnr else None)


_EXPORT_FETCH_SIZE = 2000  # 每批从 DB 拉取的行数（服务端游标），避免全量加载


@router.post("/export-excel")
async def export_excel(
    body: ExportDSL,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_query_builder_access),
):
    """导出全部（advanced-query-linkage-closure R8，ADR-AQL-14）：与 execute 同一作用域与语句（不分页），经
    ``export_service.stream_xlsx`` 流式写出。

    改造前复用分页语句（``limit ≤ 1000``）、表头写列键、文件名 ASCII，结果最多 1,000 行（AQ-20）。现在：与业务视图导出共用
    导出闸（本人 1 个、全进程 4 个，超出 429）；先 COUNT，超过 1,000,000 行 400、不产生文件（不再截断）；表头取请求的
    ``headers``，附「查询说明」sheet；每次导出记审计（流程在 ``services/custom_query/query_export``）。
    """
    from app.services.custom_query.query_export import export_builder_query

    warnings: list[str] = []
    scope = await _builder_scope(
        body, user=current_user, db=db, requested_project_id=body.project_id, year=body.year
    )
    acnr = await plan_builder_targets(body, db=db)
    try:
        stmt, column_names = _build_select(
            body, scope=scope, role=_get_role_value(current_user), warnings=warnings, for_export=True
        )
    except HTTPException as http_exc:
        # 预算超限 / PII 越权发生在 SQL 构建期，也要留痕（同 execute）
        await _audit_query_rejection(http_exc, user=current_user, table=body.table)
        raise
    return await export_builder_query(
        body, stmt=stmt, column_names=column_names, scope=scope, warnings=warnings,
        table_label=TABLE_WHITELIST[body.table]["label"], user=current_user, db=db, batch=_EXPORT_FETCH_SIZE,
        extra_sheet=acnr_sheet(await acnr.results(db) if acnr else None),
    )


# ─────────────────────────────────────────────────────────────────────────────
# 序列化工具
