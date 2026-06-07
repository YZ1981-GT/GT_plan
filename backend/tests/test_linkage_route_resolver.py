"""LinkageContract builder 路由构建测试（P0 增强版）。

覆盖：
- P0-3.5: wp_code 可直接解析到 WorkpaperEditor
- P0-5.1: TB → WP contract
- P0-5.2: WP → Note contract
- P0-5.3: Note cell contract
- P0-5.4: 完整链路 TB → WP → Note
"""
import pytest
from app.services.linkage_contract_builder import (
    build_tb_to_wp_contract,
    build_wp_to_note_contract,
    build_note_cell_contract,
    build_full_chain_contracts,
)
from app.schemas.linkage_contract import (
    SourceType, TargetType, LinkageStatus, LinkageConfidence,
)


# ═══ P0-5.1: TB → WP ═══

class TestBuildTbToWpContract:
    """试算表金额 → 底稿审定表 LinkageContract。"""

    def test_basic_fields(self):
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

    def test_without_amount(self):
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

    def test_route_format(self):
        """route 格式包含 project_id 和 wp_id。"""
        contract = build_tb_to_wp_contract(
            project_id="p-123",
            tb_row_id="row-1",
            tb_field="field",
            wp_id="wp-456",
            wp_cell="A1",
        )
        assert "/projects/p-123/workpapers/wp-456" == contract.route


# ═══ P0-5.2: WP → Note ═══

class TestBuildWpToNoteContract:
    """底稿审定表 → 附注单元格 LinkageContract。"""

    def test_basic_fields(self):
        contract = build_wp_to_note_contract(
            project_id="proj-001",
            wp_id="wp-uuid-abc",
            wp_cell="审定数",
            note_section_id="note-section-3",
            note_cell="table-1.row-2.col-1",
            amount="50000.00",
        )
        assert contract.source_type == SourceType.workpaper
        assert contract.source_id == "wp-uuid-abc"
        assert contract.source_cell == "审定数"
        assert contract.target_type == TargetType.note
        assert contract.target_id == "note-section-3"
        assert contract.target_cell == "table-1.row-2.col-1"
        assert contract.amount == "50000.00"
        assert "disclosure-notes" in contract.route
        assert "section=note-section-3" in contract.route
        assert "cell=table-1.row-2.col-1" in contract.route

    def test_without_cell(self):
        """不传 note_cell 时路由不含 cell 参数。"""
        contract = build_wp_to_note_contract(
            project_id="p-1",
            wp_id="wp-1",
            wp_cell="col-D",
            note_section_id="section-5",
        )
        assert "cell=" not in contract.route
        assert contract.target_cell is None


# ═══ P0-5.3: Note Cell ═══

class TestBuildNoteCellContract:
    """附注单元格 LinkageContract。"""

    def test_from_workpaper(self):
        contract = build_note_cell_contract(
            project_id="proj-001",
            note_section_id="sec-1",
            note_cell="row-3.col-2",
            source_type=SourceType.workpaper,
            source_id="wp-uuid",
            source_cell="审定数",
            amount="12345.00",
        )
        assert contract.target_type == TargetType.note
        assert contract.target_id == "sec-1"
        assert contract.target_cell == "row-3.col-2"
        assert contract.source_type == SourceType.workpaper
        assert "section=sec-1" in contract.route
        assert "cell=row-3.col-2" in contract.route

    def test_from_trial_balance(self):
        contract = build_note_cell_contract(
            project_id="proj-002",
            note_section_id="sec-2",
            note_cell="cell-A1",
            source_type=SourceType.trial_balance,
            source_id="tb-row-x",
        )
        assert contract.source_type == SourceType.trial_balance
        assert contract.source_id == "tb-row-x"


# ═══ P0-5.4: 完整链路 ═══

class TestBuildFullChainContracts:
    """完整 TB → WP → Note 链路。"""

    def test_returns_two_contracts(self):
        """完整链路返回 2 个 contract。"""
        contracts = build_full_chain_contracts(
            project_id="proj-001",
            tb_row_id="tb-row-1",
            tb_field="audited_amount",
            wp_id="wp-001",
            wp_cell="E5",
            note_section_id="sec-1",
            note_cell="table-1.row-1.col-1",
            amount="100000.00",
        )
        assert len(contracts) == 2

    def test_first_is_tb_to_wp(self):
        """第一个 contract 是 TB → WP。"""
        contracts = build_full_chain_contracts(
            project_id="p-1",
            tb_row_id="tb-1",
            tb_field="audited_amount",
            wp_id="wp-1",
            wp_cell="D12",
            note_section_id="sec-1",
            amount="999.00",
        )
        first = contracts[0]
        assert first.source_type == SourceType.trial_balance
        assert first.target_type == TargetType.workpaper

    def test_second_is_wp_to_note(self):
        """第二个 contract 是 WP → Note。"""
        contracts = build_full_chain_contracts(
            project_id="p-1",
            tb_row_id="tb-1",
            tb_field="audited_amount",
            wp_id="wp-1",
            wp_cell="D12",
            note_section_id="sec-1",
            note_cell="cell-A",
            amount="999.00",
        )
        second = contracts[1]
        assert second.source_type == SourceType.workpaper
        assert second.target_type == TargetType.note
        assert second.target_cell == "cell-A"

    def test_chain_source_matches_target(self):
        """链路连续性：第一个 contract 的 target 是第二个的 source。"""
        contracts = build_full_chain_contracts(
            project_id="p-1",
            tb_row_id="tb-1",
            tb_field="audited_amount",
            wp_id="wp-1",
            wp_cell="E5",
            note_section_id="sec-1",
            amount="1000.00",
        )
        # 第一个 target_id (wp_id) == 第二个 source_id
        assert contracts[0].target_id == contracts[1].source_id
        # 金额一致
        assert contracts[0].amount == contracts[1].amount

    def test_wp_code_resolves_to_workpaper_editor_route(self):
        """P0-3.5: wp_code 可直接解析到 WorkpaperEditor 路由。

        验证 build_tb_to_wp_contract 生成的 route 指向
        /projects/{pid}/workpapers/{wp_id}，即 WorkpaperEditor 页面。
        """
        contract = build_tb_to_wp_contract(
            project_id="proj-uat",
            tb_row_id="tb-row-5",
            tb_field="audited_amount",
            wp_id="wp-e56062ae",
            wp_cell="E5",
            amount="140094.82",
        )
        # route 必须是 WorkpaperEditor 路径格式
        assert contract.route.startswith("/projects/proj-uat/workpapers/")
        assert "wp-e56062ae" in contract.route
