"""附件影响范围查询 service (P0-3).

提供：
- 查询附件被引用的影响范围
- 判断是否需要用户确认才能删除/替换
- 读写附件证据属性元数据 (metadata JSON 方案, ADR-029)
"""
from __future__ import annotations

from typing import Any, Optional

from backend.app.schemas.attachment_evidence import (
    AttachmentEvidenceMetadata,
    AttachmentImpactItem,
    AttachmentImpactResult,
)


def get_evidence_metadata(
    ocr_fields_cache: Optional[dict],
) -> AttachmentEvidenceMetadata:
    """从 ocr_fields_cache JSON 中提取证据属性元数据。"""
    if not ocr_fields_cache:
        return AttachmentEvidenceMetadata()
    evidence_data = ocr_fields_cache.get("evidence", {})
    if not evidence_data:
        return AttachmentEvidenceMetadata()
    return AttachmentEvidenceMetadata.model_validate(evidence_data)


def set_evidence_metadata(
    ocr_fields_cache: Optional[dict],
    metadata: AttachmentEvidenceMetadata,
) -> dict:
    """将证据属性写入 ocr_fields_cache.evidence 子键。"""
    result = dict(ocr_fields_cache) if ocr_fields_cache else {}
    result["evidence"] = metadata.model_dump(mode="json")
    return result


def get_attachment_impact(
    project_id: str,
    attachment_id: str,
    *,
    references: Optional[list[dict[str, Any]]] = None,
    is_key_evidence: bool = False,
    file_name: Optional[str] = None,
) -> AttachmentImpactResult:
    """返回附件被引用的影响范围。

    Args:
        project_id: 项目 ID
        attachment_id: 附件 ID
        references: 已知引用列表 (由调用方从 DB 查询后传入)
        is_key_evidence: 是否关键证据
        file_name: 文件名

    Returns:
        AttachmentImpactResult 包含引用详情和是否需要确认
    """
    items: list[AttachmentImpactItem] = []

    if references:
        for ref in references:
            items.append(
                AttachmentImpactItem(
                    module=ref.get("module", "unknown"),
                    module_id=ref.get("module_id", ""),
                    module_label=ref.get("module_label", "未知引用"),
                    route=ref.get("route"),
                )
            )

    references_count = len(items)
    # 关键证据被引用时必须确认
    requires_confirmation = is_key_evidence and references_count > 0

    return AttachmentImpactResult(
        project_id=project_id,
        attachment_id=attachment_id,
        file_name=file_name,
        is_key_evidence=is_key_evidence,
        references_count=references_count,
        referenced_by=items,
        requires_confirmation=requires_confirmation,
    )


def query_attachment_references(
    project_id: str,
    attachment_id: str,
) -> list[dict[str, Any]]:
    """查询附件在各模块中的引用。

    P0 实现：扫描 AttachmentWorkingPaper 关联表。
    后续可扩展扫描 review_issues、report_paragraphs、note_cells 等。

    NOTE: 此函数需要 DB session，当前返回空列表作为同步接口。
    实际使用时由 router 层传入查询结果。
    """
    # P0: 返回空列表，真实查询由 router 层完成后传入 get_attachment_impact
    return []
