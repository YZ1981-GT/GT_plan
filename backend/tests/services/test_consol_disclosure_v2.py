"""Sprint B.1 — consol_disclosure_service V2 单元测试.

覆盖 B.1.1~B.1.10：
- generate_full_consol_notes 返回 180 章节结构
- _aggregate_common_section 调 aggregation service
- 子公司清单拉取
- 抵销前后双列标记
- 章节序号 scope=consolidated 重排
- 文字段落 vars 含 subsidiary_count
- 多层 lineage 写入
- 合并范围变化 → stale
- 合并专用章节 wp_data binding
- 章节映射 CSV 加载

Validates: Requirements D8, D12, D13
"""

from __future__ import annotations

import csv
import os
import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

from app.services.consol_disclosure_service import (
    CONSOL_SUBSIDIARY_CHANGED,
    _CONSOL_SECTION_WP_BINDINGS,
    _add_elimination_columns,
    _build_consol_paragraph_vars,
    _fetch_subsidiary_list,
    _generate_consol_only_sections_v2,
    _load_section_mapping,
    _renumber_sections_consolidated,
    _render_text_paragraphs_v2,
    _write_lineage_v2,
    generate_full_consol_notes,
    handle_consol_subsidiary_changed,
    register_consol_subsidiary_changed_handler,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_subsidiaries():
    """3 家子公司 mock 数据."""
    return [
        {"project_id": uuid4(), "company_code": "SUB001", "company_name": "子公司A", "consol_level": 2},
        {"project_id": uuid4(), "company_code": "SUB002", "company_name": "子公司B", "consol_level": 2},
        {"project_id": uuid4(), "company_code": "SUB003", "company_name": "子公司C", "consol_level": 3},
    ]


@pytest.fixture
def parent_project_id():
    return uuid4()


# ---------------------------------------------------------------------------
# B.1.1 generate_full_consol_notes 主方法
# ---------------------------------------------------------------------------


class TestGenerateFullConsolNotes:
    """B.1.1 generate_full_consol_notes 测试."""

    @pytest.mark.asyncio
    async def test_returns_180_sections_structure(self, parent_project_id, mock_subsidiaries):
        """生成结果包含 173 共有 + 7 合并专用章节（mock 映射 23 行 + 7 = 30）."""
        mock_db = AsyncMock()

        with patch(
            "app.services.consol_disclosure_service._fetch_subsidiary_list",
            return_value=mock_subsidiaries,
        ), patch(
            "app.services.consol_disclosure_service._load_section_mapping",
            return_value=[
                {"section_id": f"section_{i}", "consol_section_id": f"consol_section_{i}",
                 "aggregation_method": "simple_sum", "elimination_rule": ""}
                for i in range(173)
            ],
        ), patch(
            "app.services.consol_note_aggregation_service.aggregate_section",
            return_value={"rows": [{"label": "test", "values": {}}], "method": "simple_sum",
                         "child_count": 3, "section_id": "test", "elimination_applied": False},
        ), patch(
            "app.services.consol_note_aggregation_service.get_lineage_chain",
            return_value=[parent_project_id],
        ):
            result = await generate_full_consol_notes(
                db=mock_db,
                parent_project_id=parent_project_id,
                year=2025,
                template_type="soe",
            )

        # 173 共有 + 7 合并专用 = 180
        assert len(result) == 180
        # 每个章节都有 section_id
        for section in result:
            assert "section_id" in section

    @pytest.mark.asyncio
    async def test_returns_correct_section_types(self, parent_project_id, mock_subsidiaries):
        """结果包含 common 和 consol_only 两种类型."""
        mock_db = AsyncMock()

        with patch(
            "app.services.consol_disclosure_service._fetch_subsidiary_list",
            return_value=mock_subsidiaries,
        ), patch(
            "app.services.consol_disclosure_service._load_section_mapping",
            return_value=[
                {"section_id": "section_cash", "consol_section_id": "consol_section_cash",
                 "aggregation_method": "simple_sum", "elimination_rule": ""}
            ],
        ), patch(
            "app.services.consol_note_aggregation_service.aggregate_section",
            return_value={"rows": [], "method": "simple_sum",
                         "child_count": 3, "section_id": "section_cash",
                         "elimination_applied": False},
        ), patch(
            "app.services.consol_note_aggregation_service.get_lineage_chain",
            return_value=[parent_project_id],
        ):
            result = await generate_full_consol_notes(
                db=mock_db,
                parent_project_id=parent_project_id,
                year=2025,
            )

        types = {s["section_type"] for s in result}
        assert "common" in types
        assert "consol_only" in types

    @pytest.mark.asyncio
    async def test_lineage_written_to_all_sections(self, parent_project_id, mock_subsidiaries):
        """每个章节都写入了 lineage."""
        mock_db = AsyncMock()
        grandparent_id = uuid4()

        with patch(
            "app.services.consol_disclosure_service._fetch_subsidiary_list",
            return_value=mock_subsidiaries,
        ), patch(
            "app.services.consol_disclosure_service._load_section_mapping",
            return_value=[],
        ), patch(
            "app.services.consol_note_aggregation_service.get_lineage_chain",
            return_value=[parent_project_id, grandparent_id],
        ):
            result = await generate_full_consol_notes(
                db=mock_db,
                parent_project_id=parent_project_id,
                year=2025,
            )

        # 7 合并专用章节
        assert len(result) == 7
        for section in result:
            assert "lineage" in section
            assert len(section["lineage"]) == 2
            assert str(parent_project_id) in section["lineage"]


# ---------------------------------------------------------------------------
# B.1.2 _aggregate_common_section
# ---------------------------------------------------------------------------


class TestAggregateCommonSection:
    """B.1.2 _aggregate_common_section 测试."""

    @pytest.mark.asyncio
    async def test_calls_aggregate_section(self, mock_subsidiaries):
        """调用 consol_note_aggregation_service.aggregate_section."""
        mock_db = AsyncMock()
        mapping = {
            "section_id": "section_cash",
            "consol_section_id": "consol_section_cash",
            "aggregation_method": "simple_sum",
            "elimination_rule": "",
        }

        with patch(
            "app.services.consol_note_aggregation_service.aggregate_section",
            return_value={"rows": [{"label": "现金", "values": {"col_end": "100"}}],
                         "method": "simple_sum", "child_count": 3,
                         "section_id": "section_cash", "elimination_applied": False},
        ) as mock_agg:
            from app.services.consol_disclosure_service import _aggregate_common_section

            result = await _aggregate_common_section(
                db=mock_db,
                consol_project_id=uuid4(),
                year=2025,
                mapping=mapping,
                subsidiaries=mock_subsidiaries,
            )

        assert result is not None
        assert result["section_id"] == "consol_section_cash"
        assert result["section_type"] == "common"
        mock_agg.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_empty_section_when_no_data(self, mock_subsidiaries):
        """无数据时返回空章节占位."""
        mock_db = AsyncMock()
        mapping = {
            "section_id": "section_empty",
            "consol_section_id": "consol_section_empty",
            "aggregation_method": "simple_sum",
            "elimination_rule": "",
        }

        with patch(
            "app.services.consol_note_aggregation_service.aggregate_section",
            return_value=None,
        ):
            from app.services.consol_disclosure_service import _aggregate_common_section

            result = await _aggregate_common_section(
                db=mock_db,
                consol_project_id=uuid4(),
                year=2025,
                mapping=mapping,
                subsidiaries=mock_subsidiaries,
            )

        assert result is not None
        assert result["table_data"]["rows"] == []
        assert result["table_data"]["child_count"] == 3


# ---------------------------------------------------------------------------
# B.1.3 子公司清单拉取
# ---------------------------------------------------------------------------


class TestFetchSubsidiaryList:
    """B.1.3 _fetch_subsidiary_list 测试."""

    @pytest.mark.asyncio
    async def test_returns_descendants(self):
        """从 consol_tree_service 获取后代节点."""
        from app.services.consol_tree_service import TreeNode

        mock_db = AsyncMock()
        root_id = uuid4()
        child1_id = uuid4()
        child2_id = uuid4()

        root_node = TreeNode(
            project_id=root_id,
            company_code="ROOT",
            company_name="母公司",
            parent_company_code=None,
            ultimate_company_code="ROOT",
            consol_level=1,
            children=[
                TreeNode(
                    project_id=child1_id,
                    company_code="C1",
                    company_name="子公司1",
                    parent_company_code="ROOT",
                    ultimate_company_code="ROOT",
                    consol_level=2,
                ),
                TreeNode(
                    project_id=child2_id,
                    company_code="C2",
                    company_name="子公司2",
                    parent_company_code="ROOT",
                    ultimate_company_code="ROOT",
                    consol_level=2,
                ),
            ],
        )

        with patch(
            "app.services.consol_tree_service.build_tree",
            return_value=root_node,
        ), patch(
            "app.services.consol_tree_service.get_descendants",
            return_value=root_node.children,
        ):
            result = await _fetch_subsidiary_list(mock_db, root_id)

        assert len(result) == 2
        assert result[0]["company_code"] == "C1"
        assert result[1]["company_code"] == "C2"

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_tree(self):
        """树不存在时返回空列表."""
        mock_db = AsyncMock()

        with patch(
            "app.services.consol_tree_service.build_tree",
            return_value=None,
        ):
            result = await _fetch_subsidiary_list(mock_db, uuid4())

        assert result == []


# ---------------------------------------------------------------------------
# B.1.4 抵销前后双列
# ---------------------------------------------------------------------------


class TestEliminationColumns:
    """B.1.4 _add_elimination_columns 测试."""

    def test_adds_markers_when_rule_exists(self):
        """有抵销规则时添加双列标记."""
        result = {"rows": [{"label": "test"}], "elimination_applied": True}
        updated = _add_elimination_columns(result, "internal_ar")

        assert updated["_pre_elimination"] is True
        assert updated["_post_elimination"] is True
        assert updated["elimination_rule"] == "internal_ar"

    def test_no_markers_when_no_rule(self):
        """无抵销规则时不添加标记."""
        result = {"rows": [{"label": "test"}], "elimination_applied": False}
        updated = _add_elimination_columns(result, "")

        assert "_pre_elimination" not in updated
        assert "_post_elimination" not in updated


# ---------------------------------------------------------------------------
# B.1.5 合并专用章节 wp_data binding
# ---------------------------------------------------------------------------


class TestConsolOnlySectionsWpData:
    """B.1.5 + B.1.9 合并专用章节 wp_data 绑定测试."""

    def test_goodwill_has_wp_binding(self, mock_subsidiaries):
        """商誉章节绑定 h08 底稿."""
        sections = _generate_consol_only_sections_v2(uuid4(), 2025, mock_subsidiaries)
        goodwill = next(s for s in sections if s["section_id"] == "goodwill")

        assert goodwill["binding"] is not None
        assert goodwill["binding"]["wp_code"] == "h08"
        assert goodwill["binding"]["source"] == "wp_data"

    def test_mi_has_wp_binding(self, mock_subsidiaries):
        """少数股东权益章节绑定 g 底稿."""
        sections = _generate_consol_only_sections_v2(uuid4(), 2025, mock_subsidiaries)
        mi = next(s for s in sections if s["section_id"] == "minority_interest")

        assert mi["binding"] is not None
        assert mi["binding"]["wp_code"] == "g"

    def test_forex_has_wp_binding(self, mock_subsidiaries):
        """外币折算章节绑定 m 底稿."""
        sections = _generate_consol_only_sections_v2(uuid4(), 2025, mock_subsidiaries)
        forex = next(s for s in sections if s["section_id"] == "forex_translation")

        assert forex["binding"] is not None
        assert forex["binding"]["wp_code"] == "m"

    def test_seven_consol_only_sections(self, mock_subsidiaries):
        """生成 7 个合并专用章节."""
        sections = _generate_consol_only_sections_v2(uuid4(), 2025, mock_subsidiaries)
        assert len(sections) == 7

    def test_subsidiary_count_in_summary(self, mock_subsidiaries):
        """summary 包含子公司数量."""
        sections = _generate_consol_only_sections_v2(uuid4(), 2025, mock_subsidiaries)
        scope = next(s for s in sections if s["section_id"] == "consol_scope")
        assert "3" in scope["table_data"]["summary"]


# ---------------------------------------------------------------------------
# B.1.6 多层 lineage
# ---------------------------------------------------------------------------


class TestLineageV2:
    """B.1.6 _write_lineage_v2 测试."""

    @pytest.mark.asyncio
    async def test_returns_lineage_chain(self):
        """返回从当前到最顶层的 lineage 链."""
        mock_db = AsyncMock()
        project_id = uuid4()
        grandparent_id = uuid4()

        with patch(
            "app.services.consol_note_aggregation_service.get_lineage_chain",
            return_value=[project_id, grandparent_id],
        ):
            result = await _write_lineage_v2(mock_db, project_id)

        assert len(result) == 2
        assert result[0] == str(project_id)
        assert result[1] == str(grandparent_id)

    @pytest.mark.asyncio
    async def test_single_level_lineage(self):
        """单层合并只有自身."""
        mock_db = AsyncMock()
        project_id = uuid4()

        with patch(
            "app.services.consol_note_aggregation_service.get_lineage_chain",
            return_value=[project_id],
        ):
            result = await _write_lineage_v2(mock_db, project_id)

        assert len(result) == 1


# ---------------------------------------------------------------------------
# B.1.7 文字段落合并版 vars
# ---------------------------------------------------------------------------


class TestConsolParagraphVars:
    """B.1.7 _build_consol_paragraph_vars 测试."""

    def test_contains_subsidiary_count(self, mock_subsidiaries):
        """vars 包含 subsidiary_count."""
        vars_dict = _build_consol_paragraph_vars(mock_subsidiaries, 2025)
        assert vars_dict["subsidiary_count"] == 3

    def test_contains_controlled_subsidiaries(self, mock_subsidiaries):
        """vars 包含 controlled_subsidiaries（consol_level <= 2）."""
        vars_dict = _build_consol_paragraph_vars(mock_subsidiaries, 2025)
        # mock 中 2 家 level=2, 1 家 level=3
        assert vars_dict["controlled_subsidiaries"] == 2

    def test_contains_year(self, mock_subsidiaries):
        """vars 包含 year."""
        vars_dict = _build_consol_paragraph_vars(mock_subsidiaries, 2025)
        assert vars_dict["year"] == 2025

    def test_is_consolidated_flag(self, mock_subsidiaries):
        """vars 包含 is_consolidated=True."""
        vars_dict = _build_consol_paragraph_vars(mock_subsidiaries, 2025)
        assert vars_dict["is_consolidated"] is True

    def test_render_text_paragraphs_with_template(self):
        """含 text_template 的章节被渲染."""
        sections = [
            {
                "section_id": "test",
                "text_template": "本集团共有 {{ subsidiary_count }} 家子公司",
            }
        ]
        vars_dict = {"subsidiary_count": 5}
        result = _render_text_paragraphs_v2(sections, vars_dict)
        assert result[0]["text_content"] == "本集团共有 5 家子公司"

    def test_render_text_paragraphs_without_template(self):
        """无 text_template 的章节不受影响."""
        sections = [{"section_id": "test"}]
        result = _render_text_paragraphs_v2(sections, {"subsidiary_count": 5})
        assert "text_content" not in result[0]


# ---------------------------------------------------------------------------
# B.1.8 章节序号 scope='consolidated' 重排
# ---------------------------------------------------------------------------


class TestRenumberSectionsConsolidated:
    """B.1.8 _renumber_sections_consolidated 测试."""

    def test_assigns_rendered_numbers(self):
        """章节被分配 rendered_number."""
        sections = [
            {"section_id": "s1", "level": 1, "sort_index": 1, "scope": "consolidated"},
            {"section_id": "s2", "level": 1, "sort_index": 2, "scope": "consolidated"},
            {"section_id": "s3", "level": 1, "sort_index": 3, "scope": "consolidated"},
        ]
        result = _renumber_sections_consolidated(sections)

        assert result[0]["rendered_number"] == "一、"
        assert result[1]["rendered_number"] == "二、"
        assert result[2]["rendered_number"] == "三、"

    def test_scope_consolidated_filter(self):
        """scope=consolidated 的章节参与编号."""
        sections = [
            {"section_id": "s1", "level": 1, "sort_index": 1, "scope": "consolidated"},
            {"section_id": "s2", "level": 1, "sort_index": 2, "scope": "standalone"},
            {"section_id": "s3", "level": 1, "sort_index": 3, "scope": "consolidated"},
        ]
        result = _renumber_sections_consolidated(sections)

        # s1 和 s3 参与编号，s2 被过滤
        assert result[0].get("rendered_number") == "一、"
        # s2 不参与 consolidated scope 编号
        assert result[2].get("rendered_number") == "二、"


# ---------------------------------------------------------------------------
# B.1.10 合并范围变化 → stale
# ---------------------------------------------------------------------------


class TestConsolSubsidiaryChanged:
    """B.1.10 handle_consol_subsidiary_changed 测试."""

    @pytest.mark.asyncio
    async def test_marks_stale_on_event(self):
        """收到事件后标记 stale."""
        project_id = uuid4()
        event = {"project_id": str(project_id), "year": 2025}

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "app.services.consol_note_stale_handler.mark_consol_sections_stale",
            new_callable=AsyncMock,
        ) as mock_stale, patch(
            "app.core.database.async_session",
            return_value=mock_session,
        ):
            await handle_consol_subsidiary_changed(event)

        mock_stale.assert_called_once()
        call_kwargs = mock_stale.call_args
        assert call_kwargs[1]["section_id"] is None  # 全部章节

    @pytest.mark.asyncio
    async def test_ignores_none_event(self):
        """None 事件被忽略."""
        await handle_consol_subsidiary_changed(None)
        # 不抛异常即通过

    @pytest.mark.asyncio
    async def test_ignores_incomplete_event(self):
        """缺少字段的事件被忽略."""
        await handle_consol_subsidiary_changed({"project_id": str(uuid4())})
        # 缺 year，不抛异常

    def test_register_handler(self):
        """注册事件处理器."""
        mock_bus = MagicMock()
        register_consol_subsidiary_changed_handler(mock_bus)
        mock_bus.subscribe.assert_called_once_with(
            CONSOL_SUBSIDIARY_CHANGED, handle_consol_subsidiary_changed,
        )


# ---------------------------------------------------------------------------
# 辅助函数测试
# ---------------------------------------------------------------------------


class TestLoadSectionMapping:
    """_load_section_mapping CSV 加载测试."""

    def test_loads_csv_file(self):
        """能加载 consol_note_section_mapping.csv."""
        mappings = _load_section_mapping()
        # CSV 有 23 行数据
        assert len(mappings) >= 20
        # 每行有必要字段
        for m in mappings:
            assert "section_id" in m
            assert "consol_section_id" in m
            assert "aggregation_method" in m

    def test_first_row_is_cash(self):
        """第一行是货币资金."""
        mappings = _load_section_mapping()
        assert mappings[0]["section_id"] == "section_cash"
        assert mappings[0]["aggregation_method"] == "simple_sum"

    def test_elimination_rules_parsed(self):
        """抵销规则正确解析."""
        mappings = _load_section_mapping()
        ar_mapping = next(m for m in mappings if m["section_id"] == "section_ar_summary")
        assert ar_mapping["elimination_rule"] == "internal_ar"
