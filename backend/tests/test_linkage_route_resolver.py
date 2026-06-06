"""LinkageContract builder 路由构建测试。"""
import pytest
from app.services.linkage_contract_builder import build_tb_to_wp_contract
from app.schemas.linkage_contract import SourceType, TargetType, LinkageStatus


def test_build_tb_to_wp_contract_basic():
    """构建 TB→WP contract 包含正确的字段和路由。"""
    contract = build_tb_to_wp_contract(
        project_id="proj-001",
        tb_row_id="tb-row-100",
        tb_field="audited_amount",
        wp_id="wp-uuid-abc",
        wp_cell="E5",
        amount="99999.00",
    )
    assert contract.source_type == SourceType.trial_balance
    assert contract.source_id == "tb-row-100"
    assert contract.source_cell == "audited_amount"
    assert contract.target_type == TargetType.workpaper
    assert contract.target_id == "wp-uuid-abc"
    assert contract.target_cell == "E5"
    assert contract.amount == "99999.00"
    assert contract.route == "/projects/proj-001/workpapers/wp-uuid-abc"
    assert contract.status == LinkageStatus.current


def test_build_tb_to_wp_contract_without_amount():
    """不传金额时 amount 为 None。"""
    contract = build_tb_to_wp_contract(
        project_id="proj-002",
        tb_row_id="tb-row-200",
        tb_field="opening_balance",
        wp_id="wp-uuid-def",
        wp_cell="F10",
    )
    assert contract.amount is None
    assert contract.basis == "TB audited_amount → WP cell"


def test_build_tb_to_wp_contract_route_format():
    """route 格式包含 project_id 和 wp_id。"""
    contract = build_tb_to_wp_contract(
        project_id="p-123",
        tb_row_id="row-1",
        tb_field="field",
        wp_id="wp-456",
        wp_cell="A1",
    )
    assert "/projects/p-123/workpapers/wp-456" == contract.route
