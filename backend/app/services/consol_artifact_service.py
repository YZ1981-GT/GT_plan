"""绑定 published report run 的不可变合并 Excel artifact。

流程：reserve（短事务）→ 收集同 operation 数据 → 线程中生成 xlsx → 同目录原子替换 → finalize ready。
同一 `(report_run, kind, node)` 只生成一次；ready 后禁止覆盖。下载只校验既有文件，不调用生成器。
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.consol_operation_models import ConsolOperation
from app.models.report_generation_models import ARTIFACT_KINDS, ConsolArtifact, ReportGenerationRun
from app.services.consol_report_run_service import (
    ReportRunError,
    operation_input_digest,
    resolve_published_run,
)
from app.services.consol_version_vector import digest_payload

_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_ROOT_DIR = "consolidation/artifacts"


class ArtifactError(RuntimeError):
    def __init__(self, code: str, message: str, *, status_code: int = 409):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def artifact_root() -> Path:
    from app.core.config import settings

    root = Path(settings.STORAGE_ROOT)
    if not root.is_absolute():
        root = Path(__file__).resolve().parents[2] / root
    return (root / _ROOT_DIR).resolve()


def _safe_relative(value: str) -> PurePosixPath:
    path = PurePosixPath(str(value or ""))
    if not value or path.is_absolute() or ".." in path.parts or "." in path.parts:
        raise ArtifactError("ARTIFACT_PATH_INVALID", "artifact 存储路径不合法")
    return path


def resolve_artifact_path(relative: str, *, root: Path | None = None) -> Path:
    base = (root or artifact_root()).resolve()
    rel = _safe_relative(relative)
    target = (base / Path(*rel.parts)).resolve()
    if target != base and not target.is_relative_to(base):
        raise ArtifactError("ARTIFACT_PATH_OUTSIDE_ROOT", "artifact 路径超出存储根")
    return target


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _write_key_values(ws: Any, rows: list[tuple[str, Any]]) -> None:
    ws.append(["字段", "值"])
    for key, value in rows:
        ws.append([key, value if isinstance(value, (str, int, float)) or value is None else _json(value)])
    ws.column_dimensions["A"].width = 28
    ws.column_dimensions["B"].width = 100


def _report_sheet_name(report_type: str) -> str:
    return {
        "balance_sheet": "资产负债表",
        "income_statement": "利润表",
        "cash_flow_statement": "现金流量表",
        "equity_statement": "所有者权益变动表",
        "cash_flow_supplement": "现金流量补充资料",
        "impairment_provision": "资产减值准备",
    }.get(report_type, report_type)[:31]


def _append_report_sheets(wb: Any, rows_by_type: dict[str, list[dict[str, Any]]]) -> None:
    headers = [
        "行次", "行编码", "项目", "本期金额", "上期金额", "公式", "留空原因",
        "来源输入摘要", "来源信封",
    ]
    for report_type in sorted(rows_by_type):
        ws = wb.create_sheet(_report_sheet_name(report_type))
        ws.append(headers)
        for row in rows_by_type[report_type]:
            provenance = row.get("provenance") or {}
            ws.append([
                row.get("row_number"), row.get("row_code"), row.get("row_name"),
                row.get("current_period_amount"), row.get("prior_period_amount"),
                row.get("formula_used"), row.get("blank_reason"),
                provenance.get("input_digest"), _json(provenance),
            ])
        for col, width in zip("ABCDEFGHI", (8, 16, 38, 18, 18, 48, 38, 68, 90)):
            ws.column_dimensions[col].width = width


def build_report_excel_bytes(run: ReportGenerationRun) -> bytes:
    """仅从 immutable run.rows_json 生成正式报表 Excel，不读当前业务表。"""
    import openpyxl

    wb = openpyxl.Workbook()
    manifest = wb.active
    manifest.title = "运行清单"
    _write_key_values(manifest, [
        ("project_id", str(run.project_id)),
        ("year", run.year),
        ("operation_id", str(run.operation_id) if run.operation_id else None),
        ("operation_revision", run.operation_revision),
        ("report_run_id", str(run.id)),
        ("input_digest", run.input_digest),
        ("row_digest", run.row_digest),
        ("applicable_standard", run.applicable_standard),
        ("report_types", run.report_types or []),
    ])
    _append_report_sheets(wb, copy.deepcopy(run.rows_json or {}))
    output = BytesIO()
    wb.save(output)
    return output.getvalue()


def _flatten_tree(node: dict[str, Any], parent_key: str | None = None) -> list[list[Any]]:
    rows = [[
        node.get("node_key"), parent_key, node.get("company_code"), node.get("company_name"),
        node.get("display_name"), node.get("role"), node.get("kind"), node.get("project_id"),
    ]]
    for child in node.get("children") or []:
        rows.extend(_flatten_tree(child, node.get("node_key")))
    return rows


def build_consol_workpaper_bytes(payload: dict[str, Any]) -> bytes:
    """把同 operation 的范围、编制表、approved 分录、试算、对账、正式报表、附注摘要写成 xlsx。"""
    import openpyxl

    wb = openpyxl.Workbook()
    manifest = wb.active
    manifest.title = "Manifest"
    _write_key_values(manifest, sorted((payload.get("manifest") or {}).items()))

    tree_ws = wb.create_sheet("企业树与范围")
    tree_ws.append(["节点键", "上级节点", "企业代码", "企业名称", "显示名称", "角色", "类型", "项目ID"])
    for row in _flatten_tree(payload.get("tree") or {}):
        tree_ws.append(row)

    worksheet_ws = wb.create_sheet("编制表")
    worksheet_ws.append(["工作表", "版本", "内容摘要", "分片", "规范JSON"])
    for item in payload.get("worksheets") or []:
        content = _json(item.get("data") or {})
        parts = [content[i:i + 30000] for i in range(0, len(content), 30000)] or [""]
        for index, part in enumerate(parts, 1):
            worksheet_ws.append([
                item.get("sheet_key"), item.get("version"), item.get("digest"),
                f"{index}/{len(parts)}", part,
            ])

    entry_ws = wb.create_sheet("已审批抵销分录")
    entry_ws.append(["分录ID", "分录号", "类型", "归属节点", "科目码", "科目名", "借方", "贷方"])
    for entry in payload.get("entries") or []:
        lines = entry.get("lines") or [{}]
        for line in lines:
            entry_ws.append([
                entry.get("id"), entry.get("entry_no"), entry.get("entry_type"), entry.get("node_key"),
                line.get("account_code"), line.get("account_name"), line.get("debit"), line.get("credit"),
            ])

    trial_ws = wb.create_sheet("合并试算")
    trial_ws.append(["科目码", "科目名", "个别数汇总", "合并调整", "合并抵销", "合并数", "来源分录"])
    for row in payload.get("trial") or []:
        trial_ws.append([
            row.get("account_code"), row.get("account_name"), row.get("individual_sum"),
            row.get("consol_adjustment"), row.get("consol_elimination"), row.get("consol_amount"),
            _json(row.get("source_entry_ids") or []),
        ])

    reconcile_ws = wb.create_sheet("对账")
    _write_key_values(reconcile_ws, sorted((payload.get("reconciliation") or {}).items()))
    _append_report_sheets(wb, payload.get("reports") or {})

    note_ws = wb.create_sheet("合并附注摘要")
    note_ws.append(["章节", "节点", "状态", "是否过期", "锁定格数", "内容摘要", "更新时间"])
    for row in payload.get("notes") or []:
        note_ws.append([
            row.get("section_id"), row.get("node_key"), row.get("cell_state"), row.get("is_stale"),
            row.get("locked_cell_count"), row.get("data_digest"), row.get("updated_at"),
        ])

    for ws in wb.worksheets:
        ws.freeze_panes = "A2"
    output = BytesIO()
    wb.save(output)
    return output.getvalue()


async def _current_input_digest(db: AsyncSession, run: ReportGenerationRun, tree: Any) -> str:
    from app.schemas.consol_context import ConsolContext
    from app.services.consol_version_vector import build_version_vector

    raw_context = (run.provenance or {}).get("context")
    if not isinstance(raw_context, dict):
        raise ArtifactError("REPORT_RUN_CONTEXT_MISSING", "正式报表运行缺少计算上下文")
    context = ConsolContext.model_validate(raw_context)
    vector = await build_version_vector(db, context=context, tree=tree)
    return operation_input_digest(vector.model_dump(mode="json"))


async def collect_workpaper_payload(
    db: AsyncSession,
    run: ReportGenerationRun,
    operation: ConsolOperation,
) -> dict[str, Any]:
    """收集同一 published operation 的底稿包数据；前后两次版本向量校验防生成中输入变化。"""
    from app.models.consol_note_data_models import ConsolNoteData
    from app.models.consol_worksheet_data_models import ConsolWorksheetData
    from app.models.consolidation_models import ConsolTrial, ConsolWorksheet
    from app.services.consol_calc_basis import attribute_entries, index_tree, load_tree_entries, records_from_entries
    from app.services.consol_reconciliation_service import reconcile_worksheet_vs_trial
    from app.services.consol_tree_service import build_tree, to_dict as tree_to_dict

    tree = await build_tree(db, run.project_id)
    if tree is None:
        raise ArtifactError("CONSOL_TREE_MISSING", "无法构建合并企业树")
    if await _current_input_digest(db, run, tree) != run.input_digest:
        raise ArtifactError("ARTIFACT_INPUT_CHANGED", "合并输入已变化，请先重新发布报表再生成底稿")

    worksheet_records = (await db.execute(sa.select(ConsolWorksheetData).where(
        ConsolWorksheetData.project_id == run.project_id,
        ConsolWorksheetData.year == run.year,
    ).order_by(ConsolWorksheetData.sheet_key))).scalars().all()
    worksheets = [{
        "sheet_key": row.sheet_key,
        "version": int(row.version or 0),
        "digest": digest_payload(row.data or {}),
        "data": copy.deepcopy(row.data or {}),
    } for row in worksheet_records]

    derived = (await db.execute(sa.select(ConsolWorksheet).where(
        ConsolWorksheet.project_id == run.project_id,
        ConsolWorksheet.year == run.year,
        ConsolWorksheet.is_deleted == sa.false(),
    ).order_by(ConsolWorksheet.node_company_code, ConsolWorksheet.account_code))).scalars().all()
    derived_rows = [{
        "node_key": row.node_company_code,
        "account_code": row.account_code,
        "children_amount_sum": str(row.children_amount_sum or 0),
        "consol_adjustment": str((row.adjustment_debit or 0) - (row.adjustment_credit or 0)),
        "consol_elimination": str((row.elimination_debit or 0) - (row.elimination_credit or 0)),
        "consolidated_amount": str(row.consolidated_amount or 0),
    } for row in derived]
    worksheets.append({
        "sheet_key": "__derived_node_account__",
        "version": operation.revision,
        "digest": digest_payload(derived_rows),
        "data": {"rows": derived_rows},
    })

    raw_entries = await load_tree_entries(db, tree, run.year, approved_only=True)
    records, invalid = records_from_entries(raw_entries)
    attributed, orphans = attribute_entries(records, index_tree(tree), invalid)
    entries = [{
        "id": str(record.id),
        "entry_no": record.entry_no,
        "entry_type": record.entry_type,
        "node_key": node_key,
        "lines": [{
            "account_code": line.account_code,
            "account_name": line.account_name,
            "debit": str(line.debit),
            "credit": str(line.credit),
        } for line in record.lines],
    } for record, node_key in attributed]

    trial_records = (await db.execute(sa.select(ConsolTrial).where(
        ConsolTrial.project_id == run.project_id,
        ConsolTrial.year == run.year,
        ConsolTrial.is_deleted == sa.false(),
    ).order_by(ConsolTrial.standard_account_code))).scalars().all()
    trial = [{
        "account_code": row.standard_account_code,
        "account_name": row.account_name,
        "individual_sum": str(row.individual_sum or 0),
        "consol_adjustment": str(row.consol_adjustment or 0),
        "consol_elimination": str(row.consol_elimination or 0),
        "consol_amount": str(row.consol_amount or 0),
        "source_entry_ids": list((row.consolidation_breakdown or {}).get("source_entry_ids") or []),
    } for row in trial_records]

    reconciliation = await reconcile_worksheet_vs_trial(db, run.project_id, run.year)
    reconciliation_payload = {
        "is_reconciled": bool(reconciliation.is_reconciled),
        "diff_count": len(reconciliation.diffs),
        "max_abs_diff": str(reconciliation.max_abs_diff),
        "diffs": [copy.deepcopy(item) for item in reconciliation.diffs[:200]],
    }

    note_records = (await db.execute(sa.select(ConsolNoteData).where(
        ConsolNoteData.project_id == run.project_id,
        ConsolNoteData.year == run.year,
    ).order_by(ConsolNoteData.section_id, ConsolNoteData.node_key))).scalars().all()
    notes = [{
        "section_id": row.section_id,
        "node_key": row.node_key,
        "cell_state": row.cell_state,
        "is_stale": bool(row.is_stale),
        "locked_cell_count": len(row.locked_cells or []),
        "data_digest": digest_payload(row.data or {}),
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    } for row in note_records]

    payload: dict[str, Any] = {
        "tree": tree_to_dict(tree),
        "worksheets": worksheets,
        "entries": entries,
        "trial": trial,
        "reconciliation": reconciliation_payload,
        "reports": copy.deepcopy(run.rows_json or {}),
        "notes": notes,
    }
    section_digests = {key: digest_payload(value) for key, value in payload.items()}
    manifest = {
        "schema_version": 1,
        "project_id": str(run.project_id),
        "year": run.year,
        "operation_id": str(operation.id),
        "operation_revision": run.operation_revision,
        "report_run_id": str(run.id),
        "input_digest": run.input_digest,
        "report_row_digest": run.row_digest,
        "section_digests": section_digests,
        "orphan_approved_entry_count": len(orphans),
    }
    manifest["root_digest"] = digest_payload(manifest)
    payload["manifest"] = manifest

    if await _current_input_digest(db, run, tree) != run.input_digest:
        raise ArtifactError("ARTIFACT_INPUT_CHANGED", "底稿收集期间合并输入发生变化，未生成文件")
    return payload


async def reserve_artifact(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    *,
    report_run_id: UUID,
    kind: str,
    node_key: str | None,
    created_by: UUID | None,
) -> tuple[ConsolArtifact, bool]:
    """预留唯一 artifact；ready 直接返回，failed 可重试，generating 由调用方报告正在生成。"""
    if kind not in ARTIFACT_KINDS:
        raise ArtifactError("ARTIFACT_KIND_INVALID", f"不支持的 artifact 类型：{kind}", status_code=422)
    run = await resolve_published_run(db, project_id, year, report_run_id=report_run_id)
    if run is None:
        raise ArtifactError("REPORT_RUN_NOT_PUBLISHED", "指定报表运行不是当前项目已发布结果")
    resolved_node = node_key or run.node_key
    if not resolved_node or resolved_node != run.node_key:
        raise ArtifactError("NON_ROOT_ARTIFACT_UNSUPPORTED", "正式 artifact 只支持报表运行的根节点")
    existing = (await db.execute(sa.select(ConsolArtifact).where(
        ConsolArtifact.report_run_id == run.id,
        ConsolArtifact.kind == kind,
        ConsolArtifact.node_key == resolved_node,
    ).with_for_update())).scalar_one_or_none()
    if existing is not None:
        if existing.status in {"ready", "generating"}:
            return existing, False
        existing.status = "generating"
        existing.error = None
        existing.storage_path = None
        existing.size_bytes = None
        existing.sha256 = None
        existing.ready_at = None
        existing.updated_at = datetime.now(timezone.utc)
        await db.flush()
        return existing, True

    label = "合并正式报表" if kind == "report_excel" else "合并工作底稿"
    artifact = ConsolArtifact(
        id=uuid.uuid4(),
        project_id=project_id,
        year=year,
        operation_id=run.operation_id,
        operation_revision=run.operation_revision,
        report_run_id=run.id,
        node_key=resolved_node,
        kind=kind,
        status="generating",
        file_name=f"{label}_{year}_{str(run.id)[:8]}.xlsx",
        content_type=_XLSX,
        created_by=created_by,
        manifest_json={},
    )
    db.add(artifact)
    await db.flush()
    return artifact, True


def _atomic_write(relative: str, content: bytes, *, root: Path | None = None) -> tuple[int, str]:
    target = resolve_artifact_path(relative, root=root)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temp.open("xb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, target)
    finally:
        if temp.exists():
            temp.unlink()
    return len(content), hashlib.sha256(content).hexdigest()


async def generate_reserved_artifact(
    db: AsyncSession,
    artifact_id: UUID,
    *,
    root: Path | None = None,
) -> ConsolArtifact:
    """生成一个已提交的 generating artifact；只 flush ready 状态，由路由统一 commit。"""
    artifact = (await db.execute(sa.select(ConsolArtifact).where(
        ConsolArtifact.id == artifact_id,
    ).with_for_update())).scalar_one_or_none()
    if artifact is None:
        raise ArtifactError("ARTIFACT_NOT_FOUND", "artifact 不存在", status_code=404)
    if artifact.status == "ready":
        return artifact
    if artifact.status != "generating":
        raise ArtifactError("ARTIFACT_NOT_RESERVED", "artifact 未处于可生成状态")
    run = await resolve_published_run(
        db,
        artifact.project_id,
        artifact.year,
        report_run_id=artifact.report_run_id,
    )
    if run is None:
        raise ArtifactError("REPORT_RUN_NOT_PUBLISHED", "报表运行已不再是正式发布结果")
    from app.services.consol_report_run_service import report_row_digest

    if report_row_digest(copy.deepcopy(run.rows_json or {})) != run.row_digest:
        raise ArtifactError("REPORT_RUN_DIGEST_MISMATCH", "正式报表运行行摘要校验失败")
    operation = await db.get(ConsolOperation, run.operation_id) if run.operation_id else None
    if operation is None:
        raise ArtifactError("OPERATION_NOT_FOUND", "artifact 对应的合并 operation 不存在")

    if artifact.kind == "report_excel":
        manifest = {
            "schema_version": 1,
            "project_id": str(run.project_id),
            "year": run.year,
            "operation_id": str(run.operation_id),
            "operation_revision": run.operation_revision,
            "report_run_id": str(run.id),
            "input_digest": run.input_digest,
            "report_row_digest": run.row_digest,
        }
        manifest["root_digest"] = digest_payload(manifest)
        content = await asyncio.to_thread(build_report_excel_bytes, run)
    else:
        payload = await collect_workpaper_payload(db, run, operation)
        manifest = copy.deepcopy(payload["manifest"])
        content = await asyncio.to_thread(build_consol_workpaper_bytes, payload)

    relative = PurePosixPath(
        str(artifact.project_id), str(artifact.year), str(run.id), f"{artifact.kind}_{artifact.id}.xlsx",
    ).as_posix()
    size, sha = await asyncio.to_thread(_atomic_write, relative, content, root=root)
    manifest["file_sha256"] = sha
    manifest["size_bytes"] = size
    artifact.storage_path = relative
    artifact.size_bytes = size
    artifact.sha256 = sha
    artifact.manifest_json = manifest
    artifact.status = "ready"
    artifact.error = None
    artifact.ready_at = datetime.now(timezone.utc)
    artifact.updated_at = artifact.ready_at
    await db.flush()
    return artifact


async def mark_artifact_failed(db: AsyncSession, artifact_id: UUID, error: BaseException) -> None:
    artifact = await db.get(ConsolArtifact, artifact_id)
    if artifact is None or artifact.status == "ready":
        return
    artifact.status = "failed"
    artifact.error = f"{type(error).__name__}: {error}"[:4000]
    artifact.updated_at = datetime.now(timezone.utc)
    await db.flush()


async def get_artifact(
    db: AsyncSession, project_id: UUID, year: int, artifact_id: UUID,
) -> ConsolArtifact | None:
    return (await db.execute(sa.select(ConsolArtifact).where(
        ConsolArtifact.id == artifact_id,
        ConsolArtifact.project_id == project_id,
        ConsolArtifact.year == year,
    ))).scalar_one_or_none()


def verify_artifact_file(artifact: ConsolArtifact, *, root: Path | None = None) -> Path:
    """验证 ready artifact 的根内路径、文件类型、size 与 SHA-256；任何不符都失败关闭。"""
    if artifact.status != "ready" or not artifact.storage_path or artifact.size_bytes is None or not artifact.sha256:
        raise ArtifactError("ARTIFACT_NOT_READY", "artifact 尚未生成完成")
    path = resolve_artifact_path(artifact.storage_path, root=root)
    if not path.is_file():
        raise ArtifactError("ARTIFACT_FILE_MISSING", "artifact 文件不存在")
    if path.stat().st_size != int(artifact.size_bytes):
        raise ArtifactError("ARTIFACT_SIZE_MISMATCH", "artifact 文件大小校验失败")
    if file_sha256(path) != artifact.sha256:
        raise ArtifactError("ARTIFACT_HASH_MISMATCH", "artifact 文件哈希校验失败")
    return path


def artifact_payload(artifact: ConsolArtifact) -> dict[str, Any]:
    return {
        "id": str(artifact.id),
        "project_id": str(artifact.project_id),
        "year": artifact.year,
        "operation_id": str(artifact.operation_id) if artifact.operation_id else None,
        "operation_revision": artifact.operation_revision,
        "report_run_id": str(artifact.report_run_id),
        "node_key": artifact.node_key,
        "kind": artifact.kind,
        "status": artifact.status,
        "file_name": artifact.file_name,
        "content_type": artifact.content_type,
        "size_bytes": artifact.size_bytes,
        "sha256": artifact.sha256,
        "manifest": copy.deepcopy(artifact.manifest_json or {}),
        "error": artifact.error,
        "created_at": artifact.created_at.isoformat() if artifact.created_at else None,
        "ready_at": artifact.ready_at.isoformat() if artifact.ready_at else None,
    }


__all__ = [
    "ArtifactError",
    "artifact_payload",
    "artifact_root",
    "build_consol_workpaper_bytes",
    "build_report_excel_bytes",
    "collect_workpaper_payload",
    "file_sha256",
    "generate_reserved_artifact",
    "get_artifact",
    "mark_artifact_failed",
    "reserve_artifact",
    "resolve_artifact_path",
    "verify_artifact_file",
]
