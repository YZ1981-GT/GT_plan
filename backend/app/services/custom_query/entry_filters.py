"""W6 业务对象筛选键（advanced-query-linkage-closure 任务 45，ADR-AQL-20；design §3.12）。

从 ``source_registry`` 拆出：那里只登记「有哪些源、各源的口径谓词」，这里是四个业务对象键怎么变成谓词——
``account_code``（可多值）、``wp_code``、``report_row``、``note_section``。拆分理由同 ``source_types``：
加上这些 resolver 后 ``source_registry`` 已 856 行，越过 800 行门；按规约抽模块而不是放宽门限。

本模块**不导入** ``source_registry``（会成环）。两个它也要用的小件放在这里作单一来源，由它反向导入：
:data:`REPORT_TYPES`（报表类型取值）与 :func:`invalid_filter`（筛选值非法的 400），以及
:func:`project_template_type`（只投影一列的准则读取，``source_registry.ref_context`` 调它）。
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.sql.elements import ColumnElement

from app.models.audit_platform_models import TrialBalance
from app.models.core import Project
from app.models.report_models import FinancialReportType
from app.services.custom_query import entry_accounts
from app.services.custom_query.cycle_scope import section_out_of_scope
from app.services.custom_query.param_sql_builder import build_portable_filter
from app.services.custom_query.source_types import FetchContext, FilterKey

#: 报表类型（``financial_report_type`` 枚举的取值，顺序同枚举声明）
REPORT_TYPES: tuple[str, ...] = tuple(t.value for t in FinancialReportType)
#: 一个 ``account_code`` 筛选键最多收多少个科目码（与条件算子的 ``MAX_IN_VALUES`` 无关：这里是前缀 OR）
MAX_ACCOUNT_CODE_VALUES = 50

_TB = TrialBalance.__table__


def invalid_filter(key: str, message: str, allowed: list[str]) -> HTTPException:
    return HTTPException(status_code=400, detail={
        "error_code": "INVALID_FILTER_VALUE", "message": message, "filter_key": key, "allowed": allowed,
    })


async def project_template_type(ctx: FetchContext) -> str:
    """本项目适用的准则（``soe`` / ``listed``），每个请求只查一次。

    只投影 ``template_type`` 一列，不能用 ``Session.get(Project, ...)`` 加载整行：整 ORM 投影会把与高级查询无关的
    新列也带进 SQL，共享库迁移稍有滞后时，查询本身已成功却会在这里整体 500。
    """
    memo = ctx.memo.get("template_type")
    if memo is None:
        result = await ctx.db.execute(
            sa.select(Project.template_type).where(Project.id == ctx.project_id).limit(1)
        )
        memo = "listed" if result.scalar_one_or_none() == "listed" else "soe"
        ctx.memo["template_type"] = memo
    return str(memo)


def remember_entry_accounts(ctx: FetchContext, codes: Iterable[str]) -> None:
    """记下本次解析出的科目码，供 ``meta.entry_accounts`` 回显（排序、去重、最多 50 个）。"""
    seen = set(ctx.memo.get("entry_accounts") or ())
    seen.update(str(c).strip() for c in codes if str(c or "").strip())
    ctx.memo["entry_accounts"] = tuple(sorted(seen))[:entry_accounts.MAX_ENTRY_ACCOUNTS]


def _remember_warning(ctx: FetchContext, message: str) -> None:
    ctx.memo.setdefault("entry_warnings", []).append(message)


def account_values(key: str, value: Any) -> list[str]:
    """科目筛选键的取值：单个字符串或 ≤ 50 项的数组；空项与整体为空都算非法。"""
    raw = value if isinstance(value, (list, tuple)) else [value]
    codes = [str(v).strip() for v in raw if str(v or "").strip()]
    if not codes:
        raise invalid_filter(key, f"筛选键「{key}」的值不能为空", [])
    if len(codes) > MAX_ACCOUNT_CODE_VALUES:
        raise invalid_filter(
            key, f"筛选键「{key}」最多 {MAX_ACCOUNT_CODE_VALUES} 个科目，实得 {len(codes)} 个", [],
        )
    return codes


def prefix_any(column: Any, codes: Sequence[str]) -> ColumnElement:
    clauses = [build_portable_filter(column, "prefix", code, allow_internal=True) for code in codes]
    return clauses[0] if len(clauses) == 1 else sa.or_(*clauses)


def account_code_key(table: sa.Table) -> FilterKey:
    """``account_code``：单值与旧的 ``prefix`` 口径完全一致；多值按前缀 OR 连接。"""

    async def resolve(ctx: FetchContext, value: Any) -> ColumnElement:
        codes = account_values("account_code", value)
        remember_entry_accounts(ctx, codes)
        return prefix_any(table.c.account_code, codes)

    return FilterKey("account_code", "account_code", "prefix", resolver=resolve)


def wp_code_key(table: sa.Table) -> FilterKey:
    """``wp_code``：底稿编码 → 科目前缀；该底稿没有登记科目 ⇒ 400 ``WP_CODE_NO_ACCOUNTS``。"""

    async def resolve(ctx: FetchContext, value: Any) -> ColumnElement:
        code = str(value).strip()
        codes = entry_accounts.codes_for_wp_code(code)
        if not codes:
            raise HTTPException(status_code=400, detail={
                "error_code": "WP_CODE_NO_ACCOUNTS", "message": "该底稿没有登记对应科目", "wp_code": code,
            })
        remember_entry_accounts(ctx, codes)
        return prefix_any(table.c.account_code, codes)

    return FilterKey("wp_code", "account_code", "prefix", resolver=resolve)


async def report_row_resolve(ctx: FetchContext, value: Any) -> ColumnElement:
    """``report_row`` = ``<报表类型>:<行次>``（试算表）：按该行报表公式的取数科目收窄。"""
    raw = str(value).strip()
    report_type, _, row_code = raw.partition(":")
    report_type, row_code = report_type.strip(), row_code.strip()
    if not row_code or report_type not in REPORT_TYPES:
        raise invalid_filter(
            "report_row", f"筛选键「report_row」的值应为「报表类型:行次」，实得「{raw}」", list(REPORT_TYPES),
        )
    try:
        predicate, info = await entry_accounts.report_row_predicate(
            ctx.db, project_id=ctx.project_id, year=ctx.year, report_type=report_type,
            row_code=row_code, column=_TB.c.standard_account_code,
        )
    except entry_accounts.ReportRowNotGenerated:
        raise HTTPException(status_code=400, detail={
            "error_code": "REPORT_ROW_NOT_GENERATED",
            "message": "该报表行尚未生成，请先在报表页生成报表", "report_row": raw,
        }) from None
    except entry_accounts.ReportRowNoAccounts:
        raise HTTPException(status_code=400, detail={
            "error_code": "REPORT_ROW_NO_ACCOUNTS",
            "message": "该报表行没有直接取数的科目，请在报表页查看公式", "report_row": raw,
        }) from None
    remember_entry_accounts(ctx, info["codes"])
    _remember_warning(ctx, f"构成科目按报表公式 {info['formula']} 的取数科目列出（含减项）")
    return predicate


async def note_section_resolve(ctx: FetchContext, value: Any) -> ColumnElement:
    """``note_section``（试算表）：附注章节 → 底稿编码 → 科目，按标准科目码等值收窄。"""
    section = str(value).strip()
    scope = await ctx.cycle.scope(ctx.project_id) if ctx.cycle is not None else None
    if scope is not None and scope.sections is not None and section not in scope.sections:
        raise section_out_of_scope(section)
    try:
        resolved = await entry_accounts.codes_for_note_section(
            ctx.db, project_id=ctx.project_id, year=ctx.year, section=section,
            template_type=await project_template_type(ctx),
        )
    except entry_accounts.NoteSectionNotFound:
        raise HTTPException(status_code=400, detail={
            "error_code": "NOTE_SECTION_NOT_FOUND",
            "message": "本项目该年度没有这个附注章节", "note_section": section,
        }) from None
    except entry_accounts.NoteSectionNoAccounts:
        raise HTTPException(status_code=400, detail={
            "error_code": "NOTE_SECTION_NO_ACCOUNTS",
            "message": "该附注章节没有登记对应科目", "note_section": section,
        }) from None
    remember_entry_accounts(ctx, resolved.codes)
    _remember_warning(
        ctx, f"「{resolved.title}」的相关科目按底稿 {'、'.join(resolved.wp_codes)} 登记的科目列出"
    )
    return _TB.c.standard_account_code.in_(list(resolved.codes))


def entry_warnings(ctx: FetchContext) -> list[str]:
    """本次解析时记下的说明（报表公式、附注章节对应的底稿），与源级 warnings 并列。"""
    return [str(w) for w in (ctx.memo.get("entry_warnings") or ())]


def entry_accounts_of(ctx: FetchContext) -> list[str]:
    """``meta.entry_accounts``：本次解析出的科目码；没有这类筛选时为空列表。"""
    return [str(code) for code in (ctx.memo.get("entry_accounts") or ())]
