"""附件删除/替换前影响范围查询 service (MVP stub)."""
from __future__ import annotations


def get_attachment_impact(project_id: str, attachment_id: str) -> dict:
    """返回附件被引用的影响范围。

    MVP 阶段返回 stub 数据（references_count=0），
    P0 阶段接入真实 EvidenceRef 查询。
    """
    return {
        "project_id": project_id,
        "attachment_id": attachment_id,
        "references_count": 0,
        "referenced_by": [],
    }
