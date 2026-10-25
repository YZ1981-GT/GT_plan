"""S-3 高级查询构建器 — 可视化条件 → SQLAlchemy core 安全构造 → 执行/预览/导出

POST /api/query/preview      预览生成的 SQL（不执行）
POST /api/query/execute      执行查询，返回结构化结果
POST /api/query/export-excel 执行查询并导出 Excel
GET  /api/query/schema       返回白名单表/字段元信息（前端用于构造可视化选择器）

设计要点：
- 仅允许查询白名单的只读 audit/财务表（trial_balance / working_paper / wp_index /
  adjustments / unadjusted_misstatements / report_line_mapping / report_config /
  account_chart / tb_balance / tb_ledger / materiality）
- 完全使用 SQLAlchemy core `select()` 按列引用构造，**不做字符串拼接**，
  绑定参数走 SQLAlchemy bindparam，杜绝 SQL 注入
- 字段名/表名/操作符/排序方向通过白名单核对后才写入 query
- 仅 admin / manager 可访问
- 不暴露 user / role / token / auth 表

注册到 router_registry.system 域 §117。

Validates: requirements §三 · S-3 高级查询构建器
"""

from __future__ import annotations

import io
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
# 白名单单一真源在 services/custom_query/table_whitelist；DSL→SQL 构建在
# services/custom_query/builder_dsl（见下方 re-export 段）。router 只保留 HTTP 层。
from app.services.custom_query.builder_scope import (
    resolve_builder_scope,
    scope_signature,
)
from app.services.custom_query.execution_guard import (
    EXPORT_TIMEOUT_MS,
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
# RBAC：仅 admin / manager / partner（partner ⊃ manager 权限超集）可访问
# ─────────────────────────────────────────────────────────────────────────────
def _get_role_value(user: User) -> str:
    role = getattr(user, "role", "")
    return role.value if hasattr(role, "value") else str(role)


# 白名单构建器可访问角色（R11.2）：admin / manager；partner 为 manager 权限超集，
# 平台既有约定纳入（signing partner 亦可用构建器）。auditor / qc / readonly 等
# 其余已认证角色一律 403 ROLE_FORBIDDEN（R11.3）。
_QUERY_BUILDER_ROLES = ("admin", "manager", "partner")


def _require_admin_or_manager(user: User) -> None:
    """角色门禁纯函数（保留供内部/测试直接调用）。

    error_code 对齐 design.md Error Handling 表：构建器角色不足 → ``ROLE_FORBIDDEN`` 403。
    """
    role = _get_role_value(user)
    if role not in _QUERY_BUILDER_ROLES:
        raise HTTPException(
            status_code=403,
            detail={"error_code": "ROLE_FORBIDDEN",
                    "message": "高级查询构建器仅 admin / manager 可访问"},
        )


def require_query_builder_access(
    current_user: User = Depends(get_current_user),
) -> User:
    """FastAPI 依赖：白名单构建器统一角色门禁（R11.2 / R11.3）。

    作为 Whitelist_Query_Builder 全部端点的单点准入依赖注入。未认证请求由
    ``get_current_user`` 先行拦截（R11.4）；已认证但角色不足 → 403 ``ROLE_FORBIDDEN``。
    """
    _require_admin_or_manager(current_user)
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
    FilterCond,
    OrderBy,
    QueryDSL,
    _build_filter,
    _build_select,
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
    scope = await resolve_builder_scope(
        user=current_user,
        dsl_tables=[body.table, *(j.get("table", "") for j in body.joins)],
        db=db,
    )
    stmt, column_names = _build_select(
        body, scope=scope, role=_get_role_value(current_user), warnings=warnings
    )
    return {
        "sql": _stmt_to_sql(stmt),
        "columns": column_names,
        "table": body.table,
        "scope": scope.describe(),
        "warnings": warnings,
    }


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
    """为查询结果每行派生可用的公式引用语法（无法定位返回 None）。

    打通高级查询（自由 SQL 探查）与结构化公式引用层：
    - trial_balance → ``TB('{standard_account_code}','审定数')``
    - tb_balance    → ``TB('{standard_account_code}','期末')``

    与 ``address_registry.formula_ref_to_uri`` 的 ref 语法保持一致，
    前端可直接把 ref 丢给 useAddressRegistry.resolve/validate 或复制进公式编辑器。
    其余表（working_paper/report_config 等）暂无稳定单值定位语义，返回 None。

    Req 21.3（grammar_v1 契约）：此处产出的 ``TB('{code}','审定数')`` /
    ``TB('{code}','期末')`` 均为 grammar_v1-valid 的 TB 域 ref —— TB 是非 wp 域，
    经 ``acnr.resolver.full_resolve`` 的 V1 delegation（``_delegate_v1`` →
    ``address_registry.formula_ref_to_uri`` → ``tb://{code}#{col}``）解析为
    ``found=True``（非 null），不会产出畸形 ref。两种列名（审定数/期末）都仅作为 URI
    的 ``#cell`` 段透传，解析恒成立。契约由 task 34.2 的公式构造 grammar_v1 断言测试统一覆盖。
    """
    refs: list[str | None] = []
    if table == "trial_balance":
        for row in rows:
            code = row.get("standard_account_code")
            refs.append(f"TB('{code}','审定数')" if code else None)
    elif table == "tb_balance":
        for row in rows:
            code = row.get("standard_account_code") or row.get("account_code")
            refs.append(f"TB('{code}','期末')" if code else None)
    else:
        refs = [None] * len(rows)
    return refs


@router.post("/execute")
async def execute_query(
    body: QueryDSL,
    response: Response,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_query_builder_access),
):
    """执行查询，返回结构化结果。"""
    warnings: list[str] = []
    # ─── 项目作用域（R2）：解析先于 SQL 构建与缓存读取 ────────────────────
    scope = await resolve_builder_scope(
        user=current_user,
        dsl_tables=[body.table, *(j.get("table", "") for j in body.joins)],
        db=db,
    )
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
        query_params=body.model_dump(),
    )
    cached = await get_cached_result(cache_key)
    if cached is not None:
        response.headers["X-Cache"] = "HIT"
        return cached

    try:
        async with cancellable_query(db, QUERY_TIMEOUT_MS):
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
        "total": len(rows_serialized),
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

    # 回写 Redis 缓存（短 TTL）
    await set_cached_result(cache_key, query_result)

    return query_result


_EXPORT_FETCH_SIZE = 2000  # 每批从 DB 拉取的行数，避免全量加载

# 导出行数硬上限复用 export_service 既有常量（R6.7：不在 router 层另写一套阈值）
from app.services.custom_query.export_service import EXPORT_ROW_HARD_LIMIT  # noqa: E402


@router.post("/export-excel")
async def export_excel(
    body: QueryDSL,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_query_builder_access),
):
    """执行查询并以流式/分页方式生成 Excel（write_only 模式避免全量内存峰值）。"""
    scope = await resolve_builder_scope(
        user=current_user,
        dsl_tables=[body.table, *(j.get("table", "") for j in body.joins)],
        db=db,
    )
    stmt, column_names = _build_select(
        body, scope=scope, role=_get_role_value(current_user)
    )
    try:
        async with cancellable_query(db, EXPORT_TIMEOUT_MS):
            result = await db.execute(stmt)
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        try:
            await db.rollback()
        except Exception:
            pass
        raise HTTPException(
            status_code=400,
            detail={"error_code": "QUERY_EXECUTION_FAILED",
                    "message": f"查询执行失败：{exc}"},
        )

    from openpyxl import Workbook
    from openpyxl.cell import WriteOnlyCell
    from openpyxl.styles import Alignment, Font, PatternFill

    wb = Workbook(write_only=True)
    table_label = TABLE_WHITELIST[body.table]["label"]
    ws = wb.create_sheet(title=table_label[:31])

    # 表头（write_only 模式通过 WriteOnlyCell 设置样式）
    header_font = Font(bold=True)
    header_fill = PatternFill(start_color="F0EDF5", end_color="F0EDF5", fill_type="solid")
    header_alignment = Alignment(horizontal="center")
    header_cells = []
    for name in column_names:
        cell = WriteOnlyCell(ws, value=name)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_alignment
        header_cells.append(cell)
    ws.append(header_cells)

    # 分页读取数据行并逐批写入（避免全量加载到内存）
    # 行数硬上限（R6.6）：改造前 fetchmany 无上限，笛卡尔积 JOIN 下会把百万行全部
    # 拉完。达上限时**在文件内显式标注**被截断 —— 静默产出不完整文件最危险，
    # 审计师会把它当完整证据留档。
    written = 0
    truncated = False
    while True:
        batch = result.fetchmany(_EXPORT_FETCH_SIZE)
        if not batch:
            break
        for row in batch:
            if written >= EXPORT_ROW_HARD_LIMIT:
                truncated = True
                break
            ws.append([_excel_cell_value(row[i] if i < len(row) else None)
                       for i in range(len(column_names))])
            written += 1
        if truncated:
            break

    if truncated:
        ws.append([])
        ws.append([
            f"※ 结果已达导出上限 {EXPORT_ROW_HARD_LIMIT} 行并被截断，"
            "本文件不是完整结果集；请补充筛选条件后重新导出"
        ])

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    filename = f"query_{body.table}.xlsx"
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ─────────────────────────────────────────────────────────────────────────────
# 序列化工具
