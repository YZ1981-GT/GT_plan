"""附件永久删除服务层。

永久删除附件不能直接删除 ``attachments`` 根行：治理版本通过
``fk_av_parent_scope`` 反向引用附件，且当前版本还有循环 FK。这里把附件聚合
根、别名和版本的删除顺序集中在服务层，并用 SAVEPOINT 把外部治理引用失败
隔离成可诊断的业务阻断，避免回收站端点把 PostgreSQL 约束错误冒泡成 500。
"""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attachment_models import Attachment
from app.models.evidence_governance_models import AttachmentVersion
from app.services.attachment_storage_resolver import StoredAttachmentRef


@dataclass(frozen=True)
class PurgedAttachment:
    """数据库删除成功后交给提交后文件清理的引用。"""

    attachment_id: UUID
    file_refs: tuple[StoredAttachmentRef, ...]


class AttachmentPurgeBlocked(RuntimeError):
    """附件仍有治理层外部引用，不能物理删除。"""

    default_message = "附件仍被治理记录引用，无法永久删除；请先解除关联或清理相关作业"

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.default_message)


async def _table_exists(db: AsyncSession, table_name: str) -> bool:
    """在当前会话连接上检查可选治理表，兼容最小 SQLite 测试 schema。"""

    connection = await db.connection()
    return await connection.run_sync(
        lambda sync_connection: sa.inspect(sync_connection).has_table(table_name)
    )


async def _delete_legacy_aliases(db: AsyncSession, attachment_id: UUID) -> None:
    """删除随聚合根失效的旧 ID 别名，不删除任何外部业务证据。"""

    if not await _table_exists(db, "legacy_attachment_alias"):
        return
    await db.execute(
        sa.text(
            "DELETE FROM legacy_attachment_alias "
            "WHERE attachment_id = :attachment_id OR old_attachment_id = :attachment_id"
        ),
        {"attachment_id": str(attachment_id)},
    )


async def permanently_delete_attachment(
    db: AsyncSession, attachment: Attachment,
) -> PurgedAttachment:
    """按附件聚合顺序永久删除一条已通过业务守卫的附件。

    调用方必须先执行 ``attachment_destructive_guard.assert_destructible``。
    本函数不提交事务；调用方在所有业务行成功后统一提交。知识晋升、AI run
    资源、OCR 结果、EvidenceRef 等外部治理记录仍保留时，版本删除会触发
    ``IntegrityError``，由这里转成可重试的业务阻断，并回滚本次 SAVEPOINT。
    """

    file_ref = StoredAttachmentRef(
        attachment.project_id,
        attachment.storage_type,
        attachment.file_path,
    )
    file_refs: list[StoredAttachmentRef] = [file_ref]
    attachment_id = attachment.id
    try:
        async with db.begin_nested():
            # 与恢复路径共用根行锁，并重新读取软删状态。路由查询和真正删除
            # 之间若发生恢复，必须在这里 fail closed，不能物理删除已恢复附件。
            locked = (
                await db.execute(
                    sa.select(Attachment)
                    .where(Attachment.id == attachment_id)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
            ).scalar_one_or_none()
            if locked is None:
                raise AttachmentPurgeBlocked("附件已不存在，请刷新回收站")
            if not locked.is_deleted:
                raise AttachmentPurgeBlocked("附件已恢复，请刷新回收站")
            attachment = locked

            # 先取版本文件引用，再断开循环 FK。版本字节可能与根行使用不同
            # storage_key，提交后清理必须覆盖两者。
            versions = list(
                (
                    await db.execute(
                        sa.select(AttachmentVersion)
                        .where(AttachmentVersion.attachment_id == attachment_id)
                        .order_by(AttachmentVersion.version_no.desc())
                    )
                )
                .scalars()
                .all()
            )
            file_refs.extend(
                StoredAttachmentRef(
                    attachment.project_id,
                    version.storage_type,
                    version.storage_key,
                )
                for version in versions
            )

            # 先断开循环 FK，再删版本。版本按倒序删除，避免
            # previous_version_id 指向较旧版本时撞自引用约束。
            attachment.current_version_id = None
            await db.flush()

            await _delete_legacy_aliases(db, attachment_id)

            for version in versions:
                await db.delete(version)
            if versions:
                await db.flush()

            await db.delete(attachment)
            await db.flush()
    except IntegrityError as exc:
        raise AttachmentPurgeBlocked() from exc

    return PurgedAttachment(attachment_id=attachment_id, file_refs=tuple(file_refs))


async def batch_purge_attachments(
    db: AsyncSession, user, rows, ids: list[UUID],
) -> tuple[dict[str, object], list[StoredAttachmentRef]]:
    """批量附件删除的服务层编排；不提交，返回待清理文件引用。"""

    from app.services.attachment_destructive_guard import (
        SKIP_REASONS,
        partition_purgeable,
        skipped_summary,
    )

    purgeable, skipped = await partition_purgeable(db, user, rows)
    succeeded: list[str] = []
    failed: list[dict[str, str]] = []
    file_refs: list[StoredAttachmentRef] = []
    for reason, skipped_rows in skipped.items():
        failed.extend(
            {"id": str(row.id), "error": SKIP_REASONS[reason]}
            for row in skipped_rows
        )
    for row in purgeable:
        try:
            purged = await permanently_delete_attachment(db, row)
        except AttachmentPurgeBlocked as exc:
            skipped.setdefault("referenced", []).append(row)
            failed.append({"id": str(row.id), "error": str(exc)})
        else:
            succeeded.append(str(row.id))
            file_refs.extend(purged.file_refs)
    found_row_ids = {row.id for row in rows}
    failed.extend(
        {"id": str(row_id), "error": "记录不存在"}
        for row_id in ids
        if row_id not in found_row_ids
    )
    return {
        "succeeded": succeeded,
        "failed": failed,
        "success_count": len(succeeded),
        "fail_count": len(failed),
        "total": len(ids),
        "skipped": skipped_summary(skipped),
    }, file_refs


async def purge_deleted_attachments(
    db: AsyncSession, user,
) -> tuple[int, dict[str, int], list[StoredAttachmentRef]]:
    """清空附件的服务层编排；不提交，调用方负责 commit 和文件清理。"""

    from app.services.attachment_destructive_guard import partition_purgeable, skipped_summary

    rows = (
        await db.execute(
            sa.select(Attachment).where(Attachment.is_deleted.is_(True))
        )
    ).scalars().all()
    purgeable, skipped = await partition_purgeable(db, user, rows)
    file_refs: list[StoredAttachmentRef] = []
    deleted_count = 0
    for row in purgeable:
        try:
            purged = await permanently_delete_attachment(db, row)
        except AttachmentPurgeBlocked:
            skipped.setdefault("referenced", []).append(row)
        else:
            deleted_count += 1
            file_refs.extend(purged.file_refs)
    return deleted_count, skipped_summary(skipped), file_refs
