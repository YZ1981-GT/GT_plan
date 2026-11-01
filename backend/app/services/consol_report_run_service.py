"""合并报表正式运行、不可变行快照与 published 解析。

`financial_report` 保持全平台兼容的当前槽位；每次正式合并 operation 的根报表同时写
`report_generation_run.rows_json + row_digest`，页面与导出按 run 读取该不可变快照。
只有终态 succeeded 的 ConsolOperation 且 result_refs 精确引用该 run 时，run 才是 published。
"""
from __future__ import annotations

import copy
import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Iterable
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.consol_operation_models import ConsolOperation
from app.models.report_generation_models import ReportGenerationRun
from app.models.report_models import FinancialReport, FinancialReportType
from app.schemas.consol_context import ConsolContext
from app.services.consol_version_vector import digest_payload
from app.services.report_freshness import CALC_VERSION, normalize_formula

logger = logging.getLogger(__name__)

_SOURCE_INPUT_KEYS = (
    "tree_fingerprint",
    "tb_digest",
    "elimination_digest",
    "formula_digest",
    "note_mapping_digest",
    "template_digest",
)


def operation_input_digest(version_vector: dict[str, Any]) -> str:
    """与 operation 最终发布守卫相同的业务输入摘要；忽略推送自身记录的 tree revision 字段。"""
    return digest_payload({key: version_vector.get(key) for key in _SOURCE_INPUT_KEYS})


class ReportRunError(RuntimeError):
    """报表运行边界、状态或行快照不合法。"""

    def __init__(self, code: str, message: str, *, status_code: int = 409):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


@dataclass(frozen=True)
class ReportRunResult:
    run_id: UUID
    project_id: UUID
    year: int
    operation_id: UUID
    operation_revision: int
    node_key: str
    applicable_standard: str
    input_digest: str
    row_digest: str
    rows: dict[str, list[dict[str, Any]]]
    row_count: int
    changed_rows: int


def _enum_text(value: Any) -> str:
    return str(getattr(value, "value", value) or "")


def _amount_text(value: Any) -> str | None:
    if value is None or value == "":
        return None
    return str(value if isinstance(value, Decimal) else Decimal(str(value)))


def _definition_hash(formula: str | None) -> str:
    normalized = normalize_formula(formula)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _prefix_inputs(account_amounts: dict[str, Decimal], source_accounts: Iterable[str]) -> list[dict[str, str]]:
    """把公式直接引用的科目前缀/区间展开为实际取值；确定性排序，供来源信封与 input_digest。"""
    inputs: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for source in sorted({str(item) for item in source_accounts if str(item)}):
        if "~" in source:
            start, end = source.split("~", 1)
            matches = ((code, amount) for code, amount in account_amounts.items() if start <= code <= end)
            kind = "SUM_TB"
        else:
            matches = ((code, amount) for code, amount in account_amounts.items() if code.startswith(source))
            kind = "TB"
        for code, amount in sorted(matches):
            key = (kind, code)
            if key in seen:
                continue
            seen.add(key)
            inputs.append({"kind": kind, "key": code, "value": str(amount)})
    return inputs


def build_row_provenance(
    row: dict[str, Any],
    *,
    report_type: str,
    run_id: UUID,
    computed_at: datetime,
    computed_by: UUID | None,
    operation_input_digest: str,
    account_amounts: dict[str, Decimal],
    row_values: dict[tuple[str, str], str | None],
) -> dict[str, Any]:
    """合并报表域最小来源信封；直接 TB 与同行 ROW 引用记录实际值，其余由后续 S5 扩展。"""
    from app.services.consol_report_values import analyze_formula

    formula = row.get("formula_used")
    inputs = _prefix_inputs(account_amounts, row.get("source_accounts") or [])
    shape = analyze_formula(formula) if str(formula or "").strip() else None
    if shape is not None:
        refs = set(shape.row_refs)
        for start, end in shape.row_ranges:
            refs.update(
                code for (kind, code) in row_values
                if kind == report_type and start <= code <= end
            )
        for ref in sorted(refs):
            key = (report_type, ref)
            if key in row_values:
                value = row_values[key]
                source_key = f"{report_type}/{ref}"
            else:
                matches = sorted(
                    ((kind, value) for (kind, code), value in row_values.items() if code == ref),
                    key=lambda item: item[0],
                )
                value = matches[0][1] if len(matches) == 1 else None
                source_key = f"{matches[0][0]}/{ref}" if len(matches) == 1 else ref
            inputs.append({"kind": "ROW", "key": source_key, "value": "" if value is None else value})
    full_digest = digest_payload(inputs)
    return {
        "definition_version": None,
        "definition_hash": _definition_hash(formula),
        "definition_layer": "effective",
        "run_id": str(run_id),
        "computed_at": computed_at.isoformat(),
        "computed_by": str(computed_by) if computed_by else None,
        "calc_version": CALC_VERSION,
        "inputs": inputs[:200],
        "inputs_truncated": len(inputs) > 200,
        "input_digest": full_digest,
        "input_capture_status": "direct_tb_and_row_refs",
        "operation_input_digest": operation_input_digest,
    }


def canonical_report_rows(
    results: dict[str, list[dict[str, Any]]],
    *,
    run_id: UUID,
    computed_at: datetime,
    computed_by: UUID | None,
    operation_input_digest: str,
    account_amounts: dict[str, Decimal],
) -> dict[str, list[dict[str, Any]]]:
    """规范化整次报表行，固定字段和顺序；结果可直接入 JSONB 并计算 row_digest。"""
    values = {
        (report_type, str(row.get("row_code") or "")): _amount_text(row.get("current_period_amount"))
        for report_type, rows in results.items()
        for row in rows
    }
    normalized: dict[str, list[dict[str, Any]]] = {}
    for report_type in sorted(results):
        out: list[dict[str, Any]] = []
        ordered = sorted(
            results[report_type],
            key=lambda row: (int(row.get("row_number") or 0), str(row.get("row_code") or "")),
        )
        for row in ordered:
            item = {
                "report_type": report_type,
                "row_number": int(row.get("row_number") or 0),
                "row_code": str(row.get("row_code") or ""),
                "row_name": str(row.get("row_name") or ""),
                "indent_level": int(row.get("indent_level") or 0),
                "is_total_row": bool(row.get("is_total_row")),
                "current_period_amount": _amount_text(row.get("current_period_amount")),
                "prior_period_amount": _amount_text(row.get("prior_period_amount")),
                "formula_used": row.get("formula_used") or None,
                "source_accounts": list(row.get("source_accounts") or []),
                "blank_reason": row.get("blank_reason") or None,
                "prior_blank_reason": row.get("prior_blank_reason") or None,
                "has_formula": bool(row.get("has_formula")),
            }
            item["provenance"] = build_row_provenance(
                item,
                report_type=report_type,
                run_id=run_id,
                computed_at=computed_at,
                computed_by=computed_by,
                operation_input_digest=operation_input_digest,
                account_amounts=account_amounts,
                row_values=values,
            )
            out.append(item)
        normalized[report_type] = out
    return normalized


def report_row_digest(rows: dict[str, list[dict[str, Any]]]) -> str:
    return digest_payload(rows)


async def write_consol_formula_audit(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    rows: dict[str, list[dict[str, Any]]],
    user_id: UUID | None,
) -> None:
    """沿用原合并报表公式哈希链留痕；每行保存点失败只告警，不破坏正式报表事务。"""
    from app.services.audit_log_helper import append_audit_log

    actor = user_id or UUID("00000000-0000-0000-0000-000000000000")
    for report_type, items in rows.items():
        for row in items:
            formula = str(row.get("formula_used") or "")
            if not formula:
                continue
            try:
                async with db.begin_nested():
                    await append_audit_log(db, {
                        "user_id": actor,
                        "project_id": project_id,
                        "action": "formula.changed",
                        "resource_type": "report_config",
                        "resource_id": row.get("row_code") or "",
                        "details": {
                            "event_type": "formula_changed",
                            "module": "consol",
                            "row_code": row.get("row_code") or "",
                            "action": "execute",
                            "old_formula": "",
                            "new_formula": formula,
                            "result_value": row.get("current_period_amount") or "",
                            "trace": (row.get("provenance") or {}).get("inputs") or [f"report_type={report_type}"],
                            "year": str(year),
                            "run_id": (row.get("provenance") or {}).get("run_id"),
                        },
                    })
            except Exception as exc:  # noqa: BLE001
                logger.warning("合并公式审计写入失败（best_effort）：%s", exc)


def _snapshot_of(run: ReportGenerationRun) -> ReportRunResult:
    if not run.operation_id or not run.operation_revision or not run.node_key:
        raise ReportRunError("REPORT_RUN_INCOMPLETE", "报表运行缺少 operation 或根节点身份")
    if run.status != "succeeded" or not run.input_digest or not run.row_digest:
        raise ReportRunError("REPORT_RUN_NOT_SUCCEEDED", "报表运行尚未成功")
    return ReportRunResult(
        run_id=run.id,
        project_id=run.project_id,
        year=run.year,
        operation_id=run.operation_id,
        operation_revision=run.operation_revision,
        node_key=run.node_key,
        applicable_standard=run.applicable_standard or "",
        input_digest=run.input_digest,
        row_digest=run.row_digest,
        rows=copy.deepcopy(run.rows_json or {}),
        row_count=int(run.row_count or 0),
        changed_rows=int(run.changed_rows or 0),
    )


async def materialize_consol_report_run(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    *,
    operation_id: UUID,
    operation_revision: int,
    trigger: str,
    triggered_by: UUID | None,
    context: ConsolContext,
    tree: Any,
    basis: Any,
    applicable_standard: str | None = None,
    input_version_vector: dict[str, Any] | None = None,
) -> ReportRunResult:
    """计算根节点报表并在同一事务内写运行快照、当前槽位和来源信封；只 flush 不 commit。

    任一步抛错时调用方回滚本报表步骤，旧 `financial_report` 和旧 published run 均保持不变。
    同 operation revision 重试命中 succeeded run 时直接返回，不重复计算。
    """
    from app.services.consol_calc_basis import MEASURE_CONSOLIDATED, node_measures, validate_calc_basis
    from app.services.consol_report_service import ConsolReportService
    from app.services.consol_report_values import CONSOL_STANDARDS, resolve_consol_standard

    if operation_revision < 1:
        raise ReportRunError("INVALID_OPERATION_REVISION", "operation revision 必须大于 0", status_code=422)
    operation = await db.get(ConsolOperation, operation_id)
    if operation is None:
        raise ReportRunError("OPERATION_NOT_FOUND", "合并 operation 不存在", status_code=404)
    if operation.status != "running" or int(operation.revision) != operation_revision:
        raise ReportRunError("OPERATION_REVISION_LOST", "合并 operation 已不是本次运行 revision")
    if int(operation.year) != year:
        raise ReportRunError("OPERATION_YEAR_MISMATCH", "报表年度与 operation 年度不一致")

    validate_calc_basis(basis, project_id, year, tree=tree)
    root_node_key = str(basis.tree.node_key)
    existing = (await db.execute(
        sa.select(ReportGenerationRun).where(
            ReportGenerationRun.operation_id == operation_id,
            ReportGenerationRun.operation_revision == operation_revision,
            ReportGenerationRun.project_id == project_id,
            ReportGenerationRun.node_key == root_node_key,
        ).with_for_update()
    )).scalar_one_or_none()
    if existing is not None and existing.status == "succeeded":
        return _snapshot_of(existing)

    standard = applicable_standard if applicable_standard in CONSOL_STANDARDS else (
        await resolve_consol_standard(db, project_id)
    )
    vector_payload = dict(input_version_vector or operation.version_vector or {})
    missing_inputs = [key for key in _SOURCE_INPUT_KEYS if not vector_payload.get(key)]
    if missing_inputs:
        raise ReportRunError(
            "INPUT_DIGEST_MISSING",
            f"operation 缺少输入摘要字段：{', '.join(missing_inputs)}",
        )
    input_digest = operation_input_digest(vector_payload)
    now = datetime.now(timezone.utc)
    run = existing or ReportGenerationRun(
        project_id=project_id,
        year=year,
        operation_id=operation_id,
        operation_revision=operation_revision,
        node_key=root_node_key,
        trigger=trigger,
        triggered_by=triggered_by,
        calc_version=CALC_VERSION,
    )
    if existing is None:
        db.add(run)
    run.status = "building"
    run.applicable_standard = standard
    run.input_digest = input_digest
    run.error = None
    run.started_at = now
    run.finished_at = None
    await db.flush()

    before_rows = (await db.execute(sa.select(FinancialReport).where(
        FinancialReport.project_id == project_id,
        FinancialReport.year == year,
        FinancialReport.is_deleted == sa.false(),
    ))).scalars().all()
    before = {
        (_enum_text(row.report_type), row.row_code): (
            _amount_text(row.current_period_amount), _amount_text(row.prior_period_amount),
            row.formula_used, row.blank_reason,
        )
        for row in before_rows
    }

    results = await ConsolReportService(db).generate_consol_reports(
        project_id,
        year,
        standard,
        context=context,
        tree=tree,
        basis=basis,
    )
    row_count = sum(len(items) for items in results.values())
    if row_count == 0:
        raise ReportRunError("REPORT_ROWS_EMPTY", "合并报表没有生成任何行，不能形成正式运行")

    root_amounts = node_measures(basis)[basis.tree.node_key][MEASURE_CONSOLIDATED]
    canonical = canonical_report_rows(
        results,
        run_id=run.id,
        computed_at=now,
        computed_by=triggered_by,
        operation_input_digest=input_digest,
        account_amounts=root_amounts,
    )
    row_digest = report_row_digest(canonical)
    current = {
        (report_type, str(item.get("row_code") or "")): (
            item.get("current_period_amount"), item.get("prior_period_amount"),
            item.get("formula_used"), item.get("blank_reason"),
        )
        for report_type, items in canonical.items()
        for item in items
    }
    changed = sum(1 for key, value in current.items() if before.get(key) != value)
    changed += sum(1 for key in before if key not in current)

    persisted = (await db.execute(sa.select(FinancialReport).where(
        FinancialReport.project_id == project_id,
        FinancialReport.year == year,
        FinancialReport.is_deleted == sa.false(),
    ))).scalars().all()
    by_key = {(_enum_text(row.report_type), row.row_code): row for row in persisted}
    for report_type, items in canonical.items():
        for item in items:
            record = by_key.get((report_type, item["row_code"]))
            if record is None:
                raise ReportRunError(
                    "REPORT_ROW_PERSISTENCE_MISMATCH",
                    f"报表行 {report_type}/{item['row_code']} 未写入当前槽位",
                )
            record.run_id = run.id
            record.provenance = copy.deepcopy(item["provenance"])
            record.calc_version = CALC_VERSION
            record.calc_error = None

    run.status = "succeeded"
    run.finished_at = now
    run.updated_at = now
    run.changed_rows = changed
    run.recomputed_rows = row_count
    run.failed_rows = 0
    run.row_count = row_count
    run.report_types = sorted(canonical)
    run.row_digest = row_digest
    run.rows_json = copy.deepcopy(canonical)
    run.provenance = {
        "domain": "consolidation",
        "operation_id": str(operation_id),
        "operation_revision": operation_revision,
        "operation_type": operation.operation_type,
        "request_hash": operation.request_hash,
        "context": context.model_dump(mode="json"),
        "version_vector": copy.deepcopy(vector_payload),
        "input_capture_status": "row_level_direct_tb_and_row_refs",
    }
    await write_consol_formula_audit(db, project_id, year, canonical, triggered_by)
    await db.flush()
    return _snapshot_of(run)


def _operation_references_run(operation: ConsolOperation, run: ReportGenerationRun) -> bool:
    refs = dict(operation.result_refs or {})
    wanted = str(run.id)
    if str(refs.get("report_run_id") or "") == wanted:
        return True
    run_ids = refs.get("report_run_ids") or {}
    return isinstance(run_ids, dict) and str(run_ids.get(str(run.project_id)) or "") == wanted


async def resolve_published_run(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    *,
    operation_id: UUID | None = None,
    report_run_id: UUID | None = None,
) -> ReportGenerationRun | None:
    """只返回被 succeeded operation 精确引用的 succeeded run；不回退 legacy/current 行。"""
    stmt = (
        sa.select(ReportGenerationRun, ConsolOperation)
        .join(ConsolOperation, ConsolOperation.id == ReportGenerationRun.operation_id)
        .where(
            ReportGenerationRun.project_id == project_id,
            ReportGenerationRun.year == year,
            ReportGenerationRun.status == "succeeded",
            ConsolOperation.status == "succeeded",
            ConsolOperation.revision == ReportGenerationRun.operation_revision,
        )
        .order_by(ConsolOperation.finished_at.desc(), ReportGenerationRun.finished_at.desc())
        .limit(100)
    )
    if operation_id is not None:
        stmt = stmt.where(ConsolOperation.id == operation_id)
    if report_run_id is not None:
        stmt = stmt.where(ReportGenerationRun.id == report_run_id)
    for run, operation in (await db.execute(stmt)).all():
        if _operation_references_run(operation, run):
            return run
    return None


async def published_report_payload(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    report_type: str,
    *,
    operation_id: UUID | None = None,
    report_run_id: UUID | None = None,
) -> tuple[ReportGenerationRun, list[dict[str, Any]]]:
    run = await resolve_published_run(
        db,
        project_id,
        year,
        operation_id=operation_id,
        report_run_id=report_run_id,
    )
    if run is None:
        raise ReportRunError(
            "PUBLISHED_REPORT_NOT_FOUND",
            "当前项目年度没有已发布的合并报表，请先完成“更新合并结果”",
            status_code=409,
        )
    rows = copy.deepcopy((run.rows_json or {}).get(report_type) or [])
    if not rows:
        raise ReportRunError(
            "REPORT_TYPE_NOT_IN_RUN",
            f"正式运行中没有报表类型 {report_type}",
            status_code=404,
        )
    if report_row_digest(copy.deepcopy(run.rows_json or {})) != run.row_digest:
        raise ReportRunError("REPORT_RUN_DIGEST_MISMATCH", "正式报表运行行摘要校验失败")
    return run, rows


def run_summary(run: ReportGenerationRun) -> dict[str, Any]:
    return {
        "id": str(run.id),
        "project_id": str(run.project_id),
        "year": run.year,
        "operation_id": str(run.operation_id) if run.operation_id else None,
        "operation_revision": run.operation_revision,
        "node_key": run.node_key,
        "applicable_standard": run.applicable_standard,
        "trigger": run.trigger,
        "status": run.status,
        "calc_version": run.calc_version,
        "input_digest": run.input_digest,
        "row_digest": run.row_digest,
        "row_count": run.row_count,
        "report_types": list(run.report_types or []),
        "provenance": copy.deepcopy(run.provenance or {}),
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
    }


__all__ = [
    "ReportRunError",
    "ReportRunResult",
    "build_row_provenance",
    "canonical_report_rows",
    "materialize_consol_report_run",
    "operation_input_digest",
    "published_report_payload",
    "report_row_digest",
    "resolve_published_run",
    "run_summary",
    "write_consol_formula_audit",
]
