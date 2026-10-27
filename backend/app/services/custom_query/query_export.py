"""服务端完整导出的流程（advanced-query-linkage-closure R8，ADR-AQL-14，design §3.5）。

改造前「导出全部」只有构建器一处：复用分页语句（DSL ``limit ≤ 1000``）、表头直接写列键、文件名 ASCII；业务视图（弹窗、页面版）
只能把浏览器里已有的本页行导出成 xlsx。``export_service`` 的流式能力只被引用了一个常量。本模块把两处导出收成一条流程：

1. 解析与校验与 execute 相同（业务视图：``ExecuteCompatibilityAdapter.to_orchestrator_request`` → 目标解析 →
   ``business_fetchers.prepare_export``；构建器：作用域与 ``_build_select(for_export=True)`` 在路由里），全部 400 / 422
   发生在取导出名额之前；带分组 / 透视 → 400 ``EXPORT_GROUPING_UNSUPPORTED``（分组结果请用「导出当前页」）；
2. 取导出名额（``export_gate``：本人 1 个、全进程 4 个，超出 429 ``EXPORT_BUSY``）；
3. 行数预检：SQL 源先 COUNT，超过 ``EXPORT_ROW_HARD_LIMIT``（1,000,000）→ 400 ``EXPORT_ROW_HARD_LIMIT``，不取数、不产生
   文件（R8.2，不改为截断）；内存源取全部行（≤ 5,000，同 execute）；
4. ``export_service.stream_xlsx``：中文表头取请求的 ``headers``，附「查询说明」sheet（行数按实际写入的行），以 ``= + - @``
   开头的文本按文本写；首块在端点内预取——取数与写临时文件都在这一步、请求会话仍在时完成，错误还能以 JSON 返回；其余块只读
   临时文件；
5. 响应结束（发完、出错或客户端断开）时 ``GatedStreamingResponse`` 显式释放导出名额、关闭 ``stream_xlsx``（删临时文件）；
   首块之前任何失败先释放名额再抛；
6. 每次导出记一条审计 ``custom_query.export``（``audit_helper.record_export``，失败只记 WARNING，R8.4）；中文文件名按
   RFC 5987（R8.3）。

调用方须先完成项目归属校验：业务视图路由在函数体内直接调用 ``ownership_guard.assert_target_accessible``（端点鉴权基线按
函数体识别项目级判定，第 4 轮评审 #5），构建器由准入门禁与作用域保证。
"""

from __future__ import annotations

import dataclasses
import logging
import re
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from contextlib import aclosing
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError
from starlette.responses import StreamingResponse

from app.models.core import Project
from app.services.custom_query import audit_helper, business_fetchers, paged_fetch
from app.services.custom_query import export_service as export_module
from app.services.custom_query.builder_dsl import build_count
from app.services.custom_query.execute_compatibility import ExecuteCompatibilityAdapter
from app.services.custom_query.execution_guard import EXPORT_TIMEOUT_MS, cancellable_query
from app.services.custom_query.export_gate import ExportSlot, acquire_export_slot
from app.services.custom_query.ownership_guard import ownership_guard
from app.services.custom_query.pagination import collect_available_columns, resolve_sort, sort_rows
from app.services.custom_query.query_orchestrator import ColumnMeta, FetchPage, query_orchestrator

logger = logging.getLogger(__name__)

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
#: 「查询说明」里的导出时间按北京时间写（后端时间是 UTC；中国不实行夏令时，固定 +8 即准确）
BEIJING = timezone(timedelta(hours=8), name="北京时间")
_OP_LABELS = {
    "eq": "等于", "neq": "不等于", "gt": "大于", "gte": "大于等于", "lt": "小于", "lte": "小于等于",
    "like": "包含", "not_like": "不包含", "in": "属于", "not_in": "不属于", "between": "介于",
    "is_null": "为空", "is_not_null": "不为空",
}
_NO_VALUE_OPS = frozenset({"is_null", "is_not_null"})
_UNSAFE_FILE_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f\x7f]+')
_MAX_FILE_STEM = 120


async def _aclose(iterator: Any) -> None:
    closer = getattr(iterator, "aclose", None)
    if closer is not None:
        await closer()


async def _chain(first: bytes, rest: AsyncIterator[bytes]) -> AsyncIterator[bytes]:
    yield first
    async for chunk in rest:
        yield chunk


class GatedStreamingResponse(StreamingResponse):
    """导出响应：先给预取的首块，再续读临时文件；响应结束时**显式**释放导出名额、关闭 ``stream_xlsx``（删临时文件）。

    不能只靠生成器的 finally：Starlette 的 ``StreamingResponse`` 遇客户端断开只取消发送、不关闭 ``body_iterator``；断开若发生在
    开始发送之前，包装生成器从未启动，``aclose()`` 只把它标为已关闭、finally 根本不执行——名额会一直被占、临时文件留在磁盘。
    """

    def __init__(self, first: bytes, rest: AsyncIterator[bytes], slot: ExportSlot, **kwargs: Any) -> None:
        self._slot = slot
        self._rest = rest
        super().__init__(_chain(first, rest), **kwargs)

    async def release(self) -> None:
        """释放导出名额、关闭字节流与 ``stream_xlsx``（幂等：重复调用不多放行名额，已关闭的生成器再关是空操作）。"""
        self._slot.release()
        await _aclose(self.body_iterator)
        await _aclose(self._rest)

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            await self.release()


class _InfoRows:
    """「查询说明」按实际写入的行数生成（COUNT 预检与取数之间若有并发写入，以文件里的数据行为准），并记下行数供审计。"""

    def __init__(self, build: Callable[[int], list[tuple[str, Any]]]) -> None:
        self._build = build
        self.written: int | None = None

    def __call__(self, written: int) -> list[tuple[str, Any]]:
        self.written = int(written)
        return self._build(self.written)


def clean_file_name(raw: str | None, default: str) -> str:
    """下载文件名：去掉路径与非法字符，补 ``.xlsx``；空则用 ``default``。"""
    stem = (raw or "").strip()
    if stem.lower().endswith(".xlsx"):
        stem = stem[:-5]
    stem = _UNSAFE_FILE_CHARS.sub("_", stem).strip(" ._")
    if not stem:
        stem = _UNSAFE_FILE_CHARS.sub("_", default).strip(" ._") or "高级查询"
    return f"{stem[:_MAX_FILE_STEM]}.xlsx"


def _value_text(op: str, value: Any) -> str:
    if op in _NO_VALUE_OPS:
        return ""
    if op == "between" and isinstance(value, (list, tuple)) and len(value) == 2:
        return f"{value[0]} 至 {value[1]}"
    if isinstance(value, (list, tuple, set)):
        return "、".join(str(v) for v in value)
    return "" if value is None else str(value)


def describe_conditions(
    conditions: Sequence[Mapping[str, Any]], logic: str, headers: Mapping[str, str],
    filters: Mapping[str, Any] | None = None,
) -> str:
    """「查询说明」的条件一栏：旧筛选键「列 = 值」与结构化条件「列 算子 值」，按 and / or 连接；字段名用界面所见中文。"""
    parts = [f"{headers.get(k) or k} = {v}" for k, v in (filters or {}).items()
             if v is not None and not (isinstance(v, str) and not v.strip())]
    joiner = " 或 " if logic == "or" else " 且 "
    terms = []
    for cond in conditions:
        field, op = str(cond.get("field") or ""), str(cond.get("op") or "")
        text = f"{headers.get(field) or field} {_OP_LABELS.get(op, op)}"
        value = _value_text(op, cond.get("value"))
        terms.append(f"{text} {value}" if value else text)
    if terms:
        parts.append(joiner.join(terms) if len(terms) == 1 or not parts else f"（{joiner.join(terms)}）")
    return "；".join(parts) or "（无）"


def export_info_rows(
    *, project: str, year: Any, source: str, conditions: str, row_count: int, user: Any, warnings: Sequence[str],
) -> list[tuple[str, Any]]:
    """「查询说明」sheet 的内容（R8.1）：项目、年度、数据源、条件、行数、导出时间、导出人；有提示时另加一行。"""
    rows: list[tuple[str, Any]] = [
        ("项目", project),
        ("年度", year if year is not None else "（未限定）"),
        ("数据源", source),
        ("条件", conditions),
        ("行数", int(row_count)),
        ("导出时间", datetime.now(BEIJING).strftime("%Y-%m-%d %H:%M:%S（北京时间）")),
        ("导出人", str(getattr(user, "username", None) or getattr(user, "id", ""))),
    ]
    notes = [str(w) for w in warnings if w]
    if notes:
        rows.append(("提示", "；".join(dict.fromkeys(notes))))
    return rows


async def _project_label(db: Any, project_id: Any) -> str:
    try:
        pid = project_id if isinstance(project_id, uuid.UUID) else uuid.UUID(str(project_id))
    except (TypeError, ValueError):
        return str(project_id)
    project = await db.get(Project, pid)
    return f"{project.name}（{pid}）" if project is not None else str(pid)


def _titled(columns: Sequence[ColumnMeta], headers: Mapping[str, str]) -> list[ColumnMeta]:
    """表头 = 请求传入的界面列名（标签真源在前端 queryColumnLabels），没有的用列键；列的其余元数据原样保留。"""
    return [dataclasses.replace(c, title=str(headers.get(c.key) or c.title or c.key)[:255]) for c in columns]


async def respond_xlsx(
    slot: ExportSlot, rows: Any, columns: list[ColumnMeta], *, info_rows: _InfoRows, file_name: str,
    sheet_title: str | None = None, extra_sheets: Sequence[tuple[str, list[list[Any]]]] = (),
) -> GatedStreamingResponse:
    """生成文件并预取首块（取数与写临时文件都在这一步完成）；失败先释放名额再抛，成功后名额随响应结束释放。"""
    agen = export_module.export_service.stream_xlsx(
        rows, columns, info_rows=info_rows, sheet_title=sheet_title, extra_sheets=extra_sheets)
    try:
        try:
            first = await agen.__anext__()
        except StopAsyncIteration:
            first = b""
        finally:
            await _aclose(rows)
    except BaseException:
        slot.release()
        await agen.aclose()
        raise
    return GatedStreamingResponse(
        first, agen, slot, media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": export_module.export_service.build_content_disposition(file_name)},
    )


async def _audited(response: GatedStreamingResponse, audit: Callable[[], Awaitable[Any]]) -> GatedStreamingResponse:
    """记导出审计（``record_export`` 内部吞异常，失败只记 WARNING）；被取消等异常时先释放响应（名额、临时文件）再抛。"""
    try:
        await audit()
    except BaseException:
        await response.release()
        raise
    return response


def _grouping_unsupported() -> HTTPException:
    return HTTPException(status_code=400, detail={
        "error_code": "EXPORT_GROUPING_UNSUPPORTED",
        "message": "分组 / 透视结果不支持导出全部，请使用「导出当前页」",
    })


def _check_row_limit(row_count: int) -> None:
    """行数预检（R8.2）：超过导出硬上限 → 400，不启动导出（常量在调用时读取，与 export_service 同一个）。"""
    export_module.export_service.resolve_export_mode(
        row_count=row_count, materialized=False, row_hard_limit=export_module.EXPORT_ROW_HARD_LIMIT,
    )


async def _memory_rows(req: Any, fetched: Any, *, user: Any, db: Any) -> tuple[list[dict], list[ColumnMeta], list[str]]:
    """内存源的全部行，处理同 execute 的内存路径（可访问项目过滤 → 排序：用户 sort / 源默认 / 取数顺序）。"""
    if isinstance(fetched, FetchPage):
        rows, columns, warnings = list(fetched.rows), list(fetched.columns), list(fetched.warnings)
    else:
        rows, columns = fetched
        rows, columns, warnings = list(rows), list(columns), []
    if rows and any("project_id" in r for r in rows):
        rows = await ownership_guard.filter_accessible_rows(rows, user=user, db=db)
    keys = resolve_sort(req.source, req.sort, collect_available_columns(rows, [c.key for c in columns]))
    return sort_rows(rows, keys), columns, warnings


async def _business_export(body: Any, *, user: Any, db: Any) -> GatedStreamingResponse:
    req = ExecuteCompatibilityAdapter.to_orchestrator_request(body)
    if req.group_by or req.pivot is not None:
        raise _grouping_unsupported()
    resolved = await query_orchestrator.resolve_targets(req, db)
    plan = await business_fetchers.prepare_export(req, db)
    headers = dict(getattr(body, "headers", None) or {})
    slot = acquire_export_slot(user.id)
    try:
        if plan is not None:
            total = await paged_fetch.count_plan(plan)
            _check_row_limit(total)
            rows: Any = paged_fetch.stream_rows(plan)
            columns, warnings, label = plan.columns, plan.warnings, plan.spec.label
        else:
            rows, columns, warnings = await _memory_rows(
                req, await business_fetchers.business_fetcher(req, resolved, db), user=user, db=db)
            total, label = len(rows), req.source
            _check_row_limit(total)
        source_text = f"{label}（{req.source}）" if label != req.source else req.source
        project_text = await _project_label(db, req.project_id)
        conditions_text = describe_conditions(req.conditions, req.condition_logic, headers, req.filters)
        info = _InfoRows(lambda written: export_info_rows(
            project=project_text, year=req.year, source=source_text, conditions=conditions_text,
            row_count=written, user=user, warnings=warnings,
        ))
        file_name = clean_file_name(getattr(body, "file_name", None), f"高级查询_{label}_{req.year}")
        response = await respond_xlsx(slot, rows, _titled(columns, headers), info_rows=info, file_name=file_name)
    except BaseException:
        slot.release()
        raise
    return await _audited(response, lambda: audit_helper.record_export(
        user_id=user.id, project_id=req.project_id, details={
            "entry": "business", "source": req.source, "year": req.year,
            "row_count": info.written if info.written is not None else total,
            "columns": [c.key for c in columns], "conditions": len(req.conditions),
        }))


async def export_business_query(body: Any, *, user: Any, db: Any) -> GatedStreamingResponse:
    """业务视图「导出全部」（``POST /api/custom-query/export``）。领域 4xx 原样上抛；其余异常回滚并转 500 带追踪号。"""
    try:
        return await _business_export(body, user=user, db=db)
    except HTTPException:
        raise
    except Exception:
        correlation_id = uuid.uuid4().hex
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001 — 回滚失败不掩盖原始错误
            pass
        logger.exception("custom_query export 失败 [correlation_id=%s source=%s project=%s]",
                         correlation_id, getattr(body, "source", None), getattr(body, "project_id", None))
        raise HTTPException(status_code=500, headers={"X-Correlation-ID": correlation_id}, detail={
            "error_code": "INTERNAL_ERROR",
            "message": "导出失败，请稍后重试；如持续失败请提供追踪号联系管理员",
            "correlation_id": correlation_id,
        })


async def _builder_project_text(db: Any, scope: Any) -> str:
    if scope.requested_project_id is not None:
        return await _project_label(db, scope.requested_project_id)
    if scope.is_all_projects:
        return "全部未删除项目（未限定项目）"
    return f"可访问的 {len(scope.project_ids or ())} 个项目"


async def export_builder_query(
    body: Any, *, stmt: Any, column_names: Sequence[str], scope: Any, warnings: Sequence[str], table_label: str,
    user: Any, db: Any, batch: int = paged_fetch.STREAM_BATCH, extra_sheet: tuple[str, list[list[Any]]] | None = None,
) -> GatedStreamingResponse:
    """构建器「导出全部」（``POST /api/query/export-excel``）：``stmt`` 由 ``_build_select(for_export=True)`` 构造。

    列按位置取值（键 ``c{序号}``），DSL 里重复选同一字段也不会丢列；表头取请求的 ``headers``（键为列名），sheet 名为表名。
    ``extra_sheet``：带 acnr_targets 时追加的「单元格取值」工作表（acnr-foundation-defect-closure T15）。
    """
    headers = dict(getattr(body, "headers", None) or {})
    names = list(column_names)
    columns = [ColumnMeta(key=f"c{i}", title=str(headers.get(name) or name)[:255]) for i, name in enumerate(names)]
    joins = [str(j.get("table", "")) for j in body.joins if j.get("table")]

    async def rows() -> AsyncIterator[list[dict]]:
        async with aclosing(paged_fetch.stream_statement(db, stmt, batch=batch)) as parts:
            async for part in parts:
                yield [{f"c{i}": (row[i] if i < len(row) else None) for i in range(len(names))} for row in part]

    slot = acquire_export_slot(user.id)
    try:
        try:
            async with cancellable_query(db, EXPORT_TIMEOUT_MS):
                ungrouped_aggregate = bool(body.aggregates) and not body.group_by
                total = 1 if ungrouped_aggregate else int((await db.execute(build_count(stmt))).scalar_one())
            _check_row_limit(total)
            source = f"高级构建器：{table_label}（{body.table}）" + (f"，关联 {'、'.join(joins)}" if joins else "")
            project_text = await _builder_project_text(db, scope)
            conditions_text = describe_conditions([f.model_dump() for f in body.filters], body.filter_logic, headers)
            info = _InfoRows(lambda written: export_info_rows(
                project=project_text, year=body.year, source=source, conditions=conditions_text,
                row_count=written, user=user, warnings=[*warnings],
            ))
            file_name = clean_file_name(getattr(body, "file_name", None), f"高级构建器_{table_label}")
            response = await respond_xlsx(slot, rows(), columns, info_rows=info, file_name=file_name,
                                          sheet_title=table_label, extra_sheets=(extra_sheet,) if extra_sheet else ())
        except SQLAlchemyError as exc:
            try:
                await db.rollback()
            except Exception:  # noqa: BLE001
                pass
            raise HTTPException(status_code=400, detail={
                "error_code": "QUERY_EXECUTION_FAILED", "message": f"查询执行失败：{exc}"}) from exc
    except BaseException:
        slot.release()
        raise
    return await _audited(response, lambda: audit_helper.record_export(
        user_id=user.id, project_id=scope.requested_project_id, details={
            "entry": "builder", "table": body.table, "year": body.year,
            "row_count": info.written if info.written is not None else total,
            "columns": names, "joins": joins, "all_projects": scope.is_all_projects,
        }))
