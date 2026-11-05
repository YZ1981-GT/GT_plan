"""导入记录详情（只读）：某次导入作业确认的列映射，按文件 → sheet → 列列出（spec citar-cell-source-hover R9）。

账务查询来源卡片里「文件 · sheet ·「表头」」点开跳到这里，按 ``mapping_locate_key`` 定位到那一列。
原文件导入完成后即清理（上传产物 consumed），这里只有导入时确认的映射，不读原文件。
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dataset_models import ArtifactStatus, DatasetStatus, ImportArtifact, ImportJob, LedgerDataset
from app.services.cell_source.ledger import field_label
from app.services.ledger_import.sheet_mapping import mapping_locate_key, strip_store_prefix
from app.services.user_display_names import resolve_user_display_names

TABLE_TYPE_LABELS = {
    "balance": "科目余额表", "aux_balance": "辅助余额表", "ledger": "序时账", "aux_ledger": "辅助明细账",
    "account_chart": "科目表",
}
#: 入库行数 → 中文：v2 流水线写 ``balance_rows`` 等（真库实测）；旧引擎写 ``tb_balance`` 等（模型注释的写法），两种都认
RECORD_LABELS = {
    "balance_rows": "科目余额表", "aux_balance_rows": "辅助余额表", "ledger_rows": "序时账", "aux_ledger_rows": "辅助明细账",
    "tb_balance": "科目余额表", "tb_aux_balance": "辅助余额表", "tb_ledger": "序时账", "tb_aux_ledger": "辅助明细账",
}
JOB_STATUS_LABELS = {
    "pending": "待处理", "queued": "排队中", "running": "导入中", "validating": "校验中", "writing": "写入中",
    "activating": "生效中", "completed": "已完成", "failed": "失败", "canceled": "已取消", "timed_out": "超时",
    "interrupted": "已中断",
}
DATASET_STATUS_LABELS = {
    "staged": "已写入未生效", "active": "当前生效", "superseded": "已被新导入替代", "failed": "导入失败", "rolled_back": "已回滚",
}


def column_letter(index: Any) -> str:
    """0 起的列序号 → Excel 列字母（A、B…AA）；不是整数返回空串。"""
    if not isinstance(index, int) or index < 0:
        return ""
    n, out = index + 1, ""
    while n:
        n, r = divmod(n - 1, 26)
        out = chr(65 + r) + out
    return out


def _sheets(confirmed: list[dict]) -> list[dict]:
    out = []
    for m in confirmed:
        table_type = m.get("table_type") or ""
        columns = []
        for e in sorted(m.get("mapping_entries") or [], key=lambda e: (e.get("column_index") is None, e.get("column_index") or 0)):
            field = e.get("standard_field")
            if not field:
                continue
            idx = e.get("column_index")
            columns.append({
                "column_index": idx, "column_letter": column_letter(idx),
                "header": e.get("original_header") or e.get("canonical_header") or "",
                "field": field, "field_label": field_label(field, table_type),
                "locate": mapping_locate_key(m.get("file_name"), m.get("sheet_name"), idx),
            })
        out.append({
            "file": strip_store_prefix(m.get("file_name") or ""), "sheet": m.get("sheet_name") or "",
            "table_type": table_type, "table_label": TABLE_TYPE_LABELS.get(table_type, table_type or "未识别"),
            "confirmed_by_user": bool(m.get("confirmed_by_user")), "columns": columns,
        })
    return out


def _records(summary: dict | None) -> list[dict]:
    """各表入库行数（0 行不列；同一张表两种键都有时只取一次）。"""
    out: dict[str, int] = {}
    for k, label in RECORD_LABELS.items():
        n = (summary or {}).get(k) if isinstance(summary, dict) else None
        if isinstance(n, int) and n > 0 and label not in out:
            out[label] = n
    return [{"label": label, "count": n} for label, n in out.items()]


def _file_retained(artifact: ImportArtifact | None) -> bool:
    """上传目录是否还在（导入完成后即清理；对象存储不判断，按不在处理）。"""
    if artifact is None or artifact.status == ArtifactStatus.consumed:
        return False
    from app.services.import_artifact_service import ImportArtifactService

    path = ImportArtifactService.local_path_from_uri(artifact.storage_uri or "")
    try:
        return bool(path and path.exists())
    except OSError:
        return False


async def job_mapping_view(db: AsyncSession, project_id: UUID, job_id: UUID) -> dict | None:
    """作业不属于本项目返回 None（路由回 404）。"""
    job = await db.get(ImportJob, job_id)
    if job is None or job.project_id != project_id:
        return None
    dataset = (await db.execute(
        sa.select(LedgerDataset).where(LedgerDataset.job_id == job_id).order_by(LedgerDataset.created_at.desc()).limit(1)
    )).scalars().first()
    artifact = await db.get(ImportArtifact, job.artifact_id) if job.artifact_id else None
    names = await resolve_user_display_names(db, [job.created_by]) if job.created_by else {}
    cm = job.custom_mapping if isinstance(job.custom_mapping, dict) else {}
    confirmed = cm.get("confirmed_mappings") or []
    status = job.status.value if hasattr(job.status, "value") else str(job.status)
    ds_status = (dataset.status.value if hasattr(dataset.status, "value") else str(dataset.status)) if dataset else None
    return {
        "job": {
            "id": str(job.id), "year": job.year, "status": status, "status_label": JOB_STATUS_LABELS.get(status, status),
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "created_by_name": names.get(str(job.created_by)) if job.created_by else None,
        },
        "dataset": None if dataset is None else {
            "id": str(dataset.id), "status": ds_status, "status_label": DATASET_STATUS_LABELS.get(ds_status, ds_status),
            "is_current": dataset.status == DatasetStatus.active,
            "records": _records(dataset.record_summary),
        },
        "file_retained": _file_retained(artifact),
        "has_mapping_record": bool(confirmed),
        "sheets": _sheets(confirmed),
    }
