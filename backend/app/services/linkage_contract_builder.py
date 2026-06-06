"""LinkageContract 构建器 — 按需生成联动契约实例。MVP: TB → WP 单向。"""
from __future__ import annotations
from app.schemas.linkage_contract import (
    LinkageContract, SourceType, TargetType, LinkageStatus, LinkageConfidence,
)


def build_tb_to_wp_contract(
    project_id: str,
    tb_row_id: str,
    tb_field: str,
    wp_id: str,
    wp_cell: str,
    amount: str | None = None,
) -> LinkageContract:
    """构建试算表 → 底稿的 LinkageContract。"""
    return LinkageContract(
        source_type=SourceType.trial_balance,
        source_id=tb_row_id,
        source_cell=tb_field,
        target_type=TargetType.workpaper,
        target_id=wp_id,
        target_cell=wp_cell,
        amount=amount,
        basis="TB audited_amount → WP cell",
        status=LinkageStatus.current,
        confidence=LinkageConfidence.system,
        route=f"/projects/{project_id}/workpapers/{wp_id}",
    )
