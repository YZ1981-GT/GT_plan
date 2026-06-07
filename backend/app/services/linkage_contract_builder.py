"""LinkageContract 构建器 — 按需生成联动契约实例。

P0-5 增强版：
- TB → WP（试算表金额 → 底稿审定表）
- WP → Note（底稿审定表 → 附注单元格）
- TB → Note（试算表 → 附注，经底稿中转）
"""
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
    """P0-5.1: 构建试算表 → 底稿的 LinkageContract。"""
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


def build_wp_to_note_contract(
    project_id: str,
    wp_id: str,
    wp_cell: str,
    note_section_id: str,
    note_cell: str | None = None,
    amount: str | None = None,
) -> LinkageContract:
    """P0-5.2: 构建底稿审定表 → 附注单元格的 LinkageContract。"""
    route = f"/projects/{project_id}/disclosure-notes?section={note_section_id}"
    if note_cell:
        route += f"&cell={note_cell}"

    return LinkageContract(
        source_type=SourceType.workpaper,
        source_id=wp_id,
        source_cell=wp_cell,
        target_type=TargetType.note,
        target_id=note_section_id,
        target_cell=note_cell,
        amount=amount,
        basis="WP 审定数 → 附注单元格",
        status=LinkageStatus.current,
        confidence=LinkageConfidence.system,
        route=route,
    )


def build_note_cell_contract(
    project_id: str,
    note_section_id: str,
    note_cell: str,
    source_type: SourceType = SourceType.workpaper,
    source_id: str = "",
    source_cell: str | None = None,
    amount: str | None = None,
) -> LinkageContract:
    """P0-5.3: 构建附注单元格的 LinkageContract（来源可为底稿或试算表）。"""
    route = f"/projects/{project_id}/disclosure-notes?section={note_section_id}&cell={note_cell}"

    return LinkageContract(
        source_type=source_type,
        source_id=source_id,
        source_cell=source_cell,
        target_type=TargetType.note,
        target_id=note_section_id,
        target_cell=note_cell,
        amount=amount,
        basis=f"{source_type.value} → 附注 {note_section_id}:{note_cell}",
        status=LinkageStatus.current,
        confidence=LinkageConfidence.system,
        route=route,
    )


def build_full_chain_contracts(
    project_id: str,
    tb_row_id: str,
    tb_field: str,
    wp_id: str,
    wp_cell: str,
    note_section_id: str,
    note_cell: str | None = None,
    amount: str | None = None,
) -> list[LinkageContract]:
    """P0-5.4: 构建完整链路 TB → WP → Note 的 LinkageContract 列表。

    返回 2 个 contract：
    1. TB → WP（试算表金额到底稿审定表）
    2. WP → Note（底稿审定表到附注单元格）
    """
    contracts = [
        build_tb_to_wp_contract(
            project_id=project_id,
            tb_row_id=tb_row_id,
            tb_field=tb_field,
            wp_id=wp_id,
            wp_cell=wp_cell,
            amount=amount,
        ),
        build_wp_to_note_contract(
            project_id=project_id,
            wp_id=wp_id,
            wp_cell=wp_cell,
            note_section_id=note_section_id,
            note_cell=note_cell,
            amount=amount,
        ),
    ]
    return contracts
