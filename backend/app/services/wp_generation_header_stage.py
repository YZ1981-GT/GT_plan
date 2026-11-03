"""按编码生成的锁外表头准备。

表头写到 staging 的确定性兄弟文件，成功后只更新 manifest；不覆盖原 staging。这样进程在文件写后、
DB manifest commit 前崩溃时，重入可安全覆盖临时兄弟文件，不会拿旧摘要校验已经被改写的原文件。
"""
from __future__ import annotations

import shutil
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.wp_generation_models import WorkpaperGenerationItem
from app.services.wp_generation_operation_service import OperationConflict, get_operation
from app.services.wp_generation_staging import file_sha256, validated_staging_file
from app.services.wp_header_service import fill_generated_workpaper_header


async def prepare_staged_headers(
    db: AsyncSession,
    *,
    project_id: UUID,
    operation_id: UUID,
    lease_token: UUID,
) -> None:
    operation = await get_operation(db, project_id, operation_id, for_update=True)
    if operation is None or operation.lease_token != lease_token or operation.status != "materialized":
        raise OperationConflict("生成操作不再处于表头准备阶段")
    if operation.kind != "from_codes":
        return
    items = (await db.execute(
        sa.select(WorkpaperGenerationItem)
        .where(WorkpaperGenerationItem.operation_id == operation_id)
        .order_by(WorkpaperGenerationItem.ordinal)
    )).scalars().all()
    for item in items:
        if item.status == "failed" or item.header_prepared:
            continue
        if not item.staging_path or not item.file_sha256:
            raise RuntimeError(f"{item.wp_code} 缺少 staging manifest")
        source = validated_staging_file(project_id, operation_id, item.staging_path, item.file_sha256)
        if source.suffix.lower() not in {".xlsx", ".xlsm"}:
            item.header_prepared = True
            continue
        prepared = source.with_name(f"{source.stem}.header{source.suffix}")
        shutil.copy2(source, prepared)
        issue = await fill_generated_workpaper_header(
            db,
            project_id=project_id,
            wp_id=item.wp_id,
            path=prepared,
            wp_code=item.wp_code,
            wp_name=item.wp_name,
            cycle=item.audit_cycle,
            from_template=bool(item.from_template),
        )
        item.staging_path = str(prepared)
        item.file_sha256 = file_sha256(prepared)
        item.header_issue = issue
        item.header_prepared = True
    await db.flush()
