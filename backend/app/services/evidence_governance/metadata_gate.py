"""MetadataCompletenessGate — 元数据完整门禁（Task 4.4, Wave 3）。

Spec: attachment-ocr-ai-evidence-governance-hardening
Requirements: R2.1
Design: §5.3 FormalOutputGate（元数据完整性前置条件）
Properties: P6 (EvidenceRef 完整性)

门禁规则（R2.1）：
  元数据不完整时禁止：
    - 新建正式 EvidenceRef
    - 确认 AI 内容
    - 进入归档

  门禁 **不阻断**：
    - 读取操作
    - 停用（deactivate）

``metadata_status`` 在 ``Attachment`` 表中取值：
  - ``complete``：全部必填证据元数据已填写
  - ``incomplete``：至少一个必填字段缺失

``metadata_missing`` 存储缺失字段列表（JSON 数组）。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.evidence_governance.frozen_contracts import (
    EvidenceErrorCode,
    EvidenceGovernanceError,
)


# 必需的元数据字段（R2.1: 来源、取得日期、提供方、是否关键证据）
_REQUIRED_METADATA_FIELDS: frozenset[str] = frozenset({
    "source_type",
    "obtained_at",
    "provider",
    "is_key_evidence",
})


@dataclass(frozen=True)
class MetadataCheckResult:
    """元数据完整性检查结果。"""

    is_complete: bool
    missing_fields: list[str] = field(default_factory=list)


class MetadataCompletenessGate:
    """元数据完整门禁 — 阻止 metadata_status='incomplete' 的附件参与正式流程。

    门禁操作：
    - ``check_attachment`` — 检查单个附件元数据完整性
    - ``assert_complete_for_ref`` — 创建 EvidenceRef 前断言完整（抛异常）
    - ``assert_complete_for_ai_confirm`` — AI 确认前断言完整
    - ``assert_complete_for_archive`` — 归档前断言完整
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def check_attachment(
        self, attachment_id: uuid.UUID
    ) -> MetadataCheckResult:
        """检查附件元数据完整性（纯查询，不阻断）。"""
        row = (
            await self._db.execute(
                sa.text(
                    "SELECT metadata_status, metadata_missing "
                    "FROM attachments WHERE id = :aid LIMIT 1"
                ),
                {"aid": str(attachment_id)},
            )
        ).mappings().first()

        if row is None:
            # 附件不存在 — 由 scope guard 或其他层拒绝；此处视为不完整
            return MetadataCheckResult(
                is_complete=False, missing_fields=list(_REQUIRED_METADATA_FIELDS)
            )

        status = row.get("metadata_status")
        if status == "complete":
            return MetadataCheckResult(is_complete=True)

        # 从 metadata_missing 列解析缺失字段
        missing_raw = row.get("metadata_missing")
        if missing_raw is None:
            missing = list(_REQUIRED_METADATA_FIELDS)
        elif isinstance(missing_raw, list):
            missing = missing_raw
        elif isinstance(missing_raw, str):
            import json
            try:
                missing = json.loads(missing_raw)
            except (json.JSONDecodeError, TypeError):
                missing = list(_REQUIRED_METADATA_FIELDS)
        else:
            missing = list(_REQUIRED_METADATA_FIELDS)

        return MetadataCheckResult(is_complete=False, missing_fields=missing)

    async def assert_complete_for_ref(
        self, attachment_id: uuid.UUID
    ) -> None:
        """创建 EvidenceRef 前断言附件元数据完整（R2.1）。

        不完整则抛 ``METADATA_INCOMPLETE``，包含缺失字段列表。
        """
        result = await self.check_attachment(attachment_id)
        if not result.is_complete:
            raise EvidenceGovernanceError(
                EvidenceErrorCode.METADATA_INCOMPLETE,
                f"attachment metadata incomplete: {', '.join(result.missing_fields)}",
            )

    async def assert_complete_for_ai_confirm(
        self, attachment_id: uuid.UUID
    ) -> None:
        """AI 内容确认前断言附件元数据完整（R2.1）。"""
        result = await self.check_attachment(attachment_id)
        if not result.is_complete:
            raise EvidenceGovernanceError(
                EvidenceErrorCode.METADATA_INCOMPLETE,
                f"cannot confirm AI content: attachment metadata incomplete "
                f"({', '.join(result.missing_fields)})",
            )

    async def assert_complete_for_archive(
        self, attachment_id: uuid.UUID
    ) -> None:
        """归档前断言附件元数据完整（R2.1）。"""
        result = await self.check_attachment(attachment_id)
        if not result.is_complete:
            raise EvidenceGovernanceError(
                EvidenceErrorCode.METADATA_INCOMPLETE,
                f"cannot archive: attachment metadata incomplete "
                f"({', '.join(result.missing_fields)})",
            )

    async def check_multiple(
        self, attachment_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, MetadataCheckResult]:
        """批量检查多个附件的元数据完整性。"""
        if not attachment_ids:
            return {}

        results: dict[uuid.UUID, MetadataCheckResult] = {}
        rows = (
            await self._db.execute(
                sa.text(
                    "SELECT id, metadata_status, metadata_missing "
                    "FROM attachments WHERE id = ANY(:ids)"
                ),
                {"ids": [str(aid) for aid in attachment_ids]},
            )
        ).mappings().all()

        found_ids = set()
        for row in rows:
            aid = uuid.UUID(str(row["id"]))
            found_ids.add(aid)
            if row["metadata_status"] == "complete":
                results[aid] = MetadataCheckResult(is_complete=True)
            else:
                missing_raw = row.get("metadata_missing")
                if isinstance(missing_raw, list):
                    missing = missing_raw
                elif isinstance(missing_raw, str):
                    import json
                    try:
                        missing = json.loads(missing_raw)
                    except (json.JSONDecodeError, TypeError):
                        missing = list(_REQUIRED_METADATA_FIELDS)
                else:
                    missing = list(_REQUIRED_METADATA_FIELDS)
                results[aid] = MetadataCheckResult(
                    is_complete=False, missing_fields=missing
                )

        # 未找到的附件标记为不完整
        for aid in attachment_ids:
            if aid not in found_ids:
                results[aid] = MetadataCheckResult(
                    is_complete=False, missing_fields=list(_REQUIRED_METADATA_FIELDS)
                )

        return results
