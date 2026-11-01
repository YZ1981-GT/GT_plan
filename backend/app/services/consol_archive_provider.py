"""合并归档 provider：只收集 succeeded operation + ready artifact 的清单（批 6 / ADR-CRW-006）。

被 `archive_inventory` 按 provider 模式调用，返回合并项目应归入归档包的文件清单。
缺件时写明原因并 fail-closed（清单项标 `missing`，归档编排器据此拦截）。

不新增事实表；只读 `consol_operation`、`report_generation_run`、`consol_artifact`
和薄底稿壳 `working_paper`（`wp_code='A3-CONSOL'`）。
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.consol_operation_models import ConsolOperation
from app.models.report_generation_models import ConsolArtifact, ReportGenerationRun
from app.services.consol_workpaper_shell import WP_CODE, get_consol_workpaper_shell


async def collect_consol_archive_items(
    db: AsyncSession,
    project_id: UUID,
    year: int,
) -> list[dict[str, Any]]:
    """返回合并模块应归入归档包的清单项。

    每项包含 ``{kind, label, status, path?, hash?, size?, reason?}``。
    ``status`` = ready / missing / not_applicable。
    """
    items: list[dict[str, Any]] = []

    # 1. succeeded operation
    operation = (await db.execute(
        sa.select(ConsolOperation).where(
            ConsolOperation.project_id == project_id,
            ConsolOperation.year == year,
            ConsolOperation.status == "succeeded",
        ).order_by(ConsolOperation.finished_at.desc()).limit(1)
    )).scalar_one_or_none()

    if operation is None:
        items.append({
            "kind": "consol_operation",
            "label": "合并运行",
            "status": "missing",
            "reason": "没有已成功的合并运行",
        })
        return items

    items.append({
        "kind": "consol_operation",
        "label": "合并运行",
        "status": "ready",
        "operation_id": str(operation.id),
        "operation_revision": operation.revision,
    })

    # 2. report run
    run_id = (operation.result_refs or {}).get("report_run_id")
    run = None
    if run_id:
        from uuid import UUID as _UUID

        try:
            run = await db.get(ReportGenerationRun, _UUID(str(run_id)))
        except (ValueError, TypeError):
            pass
    if run is None or run.status != "succeeded":
        items.append({
            "kind": "report_run",
            "label": "正式报表运行",
            "status": "missing",
            "reason": "合并运行未引用已成功的报表运行" if not run_id else "报表运行状态异常",
        })
    else:
        items.append({
            "kind": "report_run",
            "label": "正式报表运行",
            "status": "ready",
            "report_run_id": str(run.id),
            "row_digest": run.row_digest,
            "row_count": run.row_count,
        })

    # 3. artifacts (report_excel + consol_workpaper)
    for kind in ("report_excel", "consol_workpaper"):
        label = "正式报表 Excel" if kind == "report_excel" else "合并工作底稿包"
        artifact = (await db.execute(
            sa.select(ConsolArtifact).where(
                ConsolArtifact.project_id == project_id,
                ConsolArtifact.year == year,
                ConsolArtifact.kind == kind,
                ConsolArtifact.status == "ready",
            ).order_by(ConsolArtifact.ready_at.desc()).limit(1)
        )).scalar_one_or_none()
        if artifact is None:
            items.append({
                "kind": kind,
                "label": label,
                "status": "missing",
                "reason": f"没有已生成的{label}",
            })
        else:
            items.append({
                "kind": kind,
                "label": label,
                "status": "ready",
                "artifact_id": str(artifact.id),
                "file_name": artifact.file_name,
                "storage_path": artifact.storage_path,
                "sha256": artifact.sha256,
                "size_bytes": artifact.size_bytes,
            })

    # 4. 薄底稿壳
    shell = await get_consol_workpaper_shell(db, project_id)
    if shell is None:
        items.append({
            "kind": "workpaper_shell",
            "label": "合并底稿壳",
            "status": "not_applicable",
            "reason": "未创建 A3-CONSOL 底稿壳",
        })
    else:
        items.append({
            "kind": "workpaper_shell",
            "label": "合并底稿壳",
            "status": "ready",
            "working_paper_id": shell["working_paper_id"],
            "wp_code": WP_CODE,
            "review_status": shell.get("review_status"),
        })

    return items


def archive_items_complete(items: list[dict[str, Any]]) -> bool:
    """所有非 not_applicable 项必须是 ready；任一 missing 即 fail-closed。"""
    return all(
        item["status"] in ("ready", "not_applicable")
        for item in items
    )


__all__ = [
    "archive_items_complete",
    "collect_consol_archive_items",
]
