"""Unit tests for A9-1 内控缺陷沟通函 render strategy.

Tests: normal flow, B22B absent, empty responses, invalid JSON remark handling.
"""

from __future__ import annotations

import json
from collections import namedtuple
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.routers.wp_render_strategies._a91_deficiency_letter import render


# ─── Mock helpers ─────────────────────────────────────────────────────────────

ChecklistRow = namedtuple("ChecklistRow", ["item_id", "conclusion", "remark"])
ProjectRow = namedtuple("ProjectRow", ["client_name", "audit_year"])
B22BRow = namedtuple("B22BRow", ["wp_id"])


def _make_ctx(
    wp_id="wp-001",
    project_id="proj-001",
    checklist_rows=None,
    project_row=None,
    b22b_wp_id=None,
    b22b_checklist_rows=None,
    b22c_wp_id=None,
    b22c_checklist_rows=None,
):
    """Build a minimal mock RenderContext.

    Query sequence (Wave3 repoint: B22C preferred, B22B fallback):
      1. A9-1 checklist_responses (a91-%)
      2. B22C wp_index JOIN lookup       ← 新增（优先 B22C 单一真源）
      3. B22C checklist_responses         (仅当 b22c_wp_id 存在)
      4. B22B wp_index JOIN lookup        (向后兼容回退)
      5. B22B checklist_responses         (仅当 b22b_wp_id 存在)
      6. project context
    """
    ctx = MagicMock()
    ctx.wp_id = wp_id
    ctx.project_id = project_id

    db = AsyncMock()

    a91_result = MagicMock()
    a91_result.fetchall.return_value = checklist_rows or []

    b22c_wp_result = MagicMock()
    b22c_wp_result.fetchone.return_value = B22BRow(b22c_wp_id) if b22c_wp_id else None
    b22c_cr_result = MagicMock()
    b22c_cr_result.fetchall.return_value = b22c_checklist_rows or []

    b22b_wp_result = MagicMock()
    b22b_wp_result.fetchone.return_value = (
        B22BRow(b22b_wp_id) if b22b_wp_id else None
    )
    b22b_cr_result = MagicMock()
    b22b_cr_result.fetchall.return_value = b22b_checklist_rows or []

    proj_result = MagicMock()
    proj_result.fetchone.return_value = project_row

    results = [a91_result, b22c_wp_result]
    if b22c_wp_id:
        results.append(b22c_cr_result)
    results.append(b22b_wp_result)
    if b22b_wp_id:
        results.append(b22b_cr_result)
    results.append(proj_result)

    db.execute = AsyncMock(side_effect=results)

    ctx.db = db
    return ctx


# ─── Tests: Normal Flow ──────────────────────────────────────────────────────


class TestA91RenderNormal:
    """Normal flow with saved data and B22B present."""

    @pytest.mark.asyncio
    async def test_returns_independence_data(self):
        """Saved independence fields are returned correctly."""
        rows = [
            ChecklistRow("a91-independence-team_independent", "Y", None),
            ChecklistRow("a91-independence-no_relationships", "N", "存在关联方关系"),
            ChecklistRow("a91-independence-safeguards_taken", "Y", None),
            ChecklistRow("a91-independence-non_audit_services", "Y", "提供税务咨询"),
        ]
        proj = ProjectRow("测试公司", 2025)
        ctx = _make_ctx(checklist_rows=rows, project_row=proj)

        result = await render(ctx)

        assert result is not None
        ind = result["section_data"]["independence"]
        assert ind["team_independent"] == "Y"
        assert ind["no_relationships"] == "N"
        assert ind["no_relationships_detail"] == "存在关联方关系"
        assert ind["safeguards_taken"] == "Y"
        assert ind["non_audit_services"] == "Y"
        assert ind["non_audit_services_detail"] == "提供税务咨询"

    @pytest.mark.asyncio
    async def test_returns_committee_data(self):
        """Committee applicability saved correctly."""
        rows = [
            ChecklistRow("a91-committee-applicability", "Y", "审计委员会监督无效的情况说明"),
        ]
        proj = ProjectRow("测试公司", 2025)
        ctx = _make_ctx(checklist_rows=rows, project_row=proj)

        result = await render(ctx)

        assert result["section_data"]["committee"]["applicability"] == "Y"
        assert result["section_data"]["committee"]["description"] == "审计委员会监督无效的情况说明"

    @pytest.mark.asyncio
    async def test_returns_signature_and_response(self):
        """Signature and response fields returned correctly."""
        rows = [
            ChecklistRow("a91-signature-date", "2026-06-26", None),
            ChecklistRow("a91-response-opinion", None, "同意所述内部控制缺陷"),
            ChecklistRow("a91-response-conclusion", None, "将积极整改"),
            ChecklistRow("a91-response-representative", "张总", None),
            ChecklistRow("a91-response-date", "2026-07-01", None),
        ]
        proj = ProjectRow("测试公司", 2025)
        ctx = _make_ctx(checklist_rows=rows, project_row=proj)

        result = await render(ctx)

        assert result["section_data"]["signature"]["date"] == "2026-06-26"
        assert result["section_data"]["response"]["opinion"] == "同意所述内部控制缺陷"
        assert result["section_data"]["response"]["conclusion"] == "将积极整改"
        assert result["section_data"]["response"]["representative"] == "张总"
        assert result["section_data"]["response"]["response_date"] == "2026-07-01"

    @pytest.mark.asyncio
    async def test_b22b_deficiencies_loaded(self):
        """B22B deficiencies are grouped by severity in response."""
        b22b_rows = [
            ChecklistRow(
                "b22b-deficiency-001", None,
                json.dumps({"id": "DEF-001", "description": "重大缺陷描述", "impact": "影响重大", "severity": "major", "index_ref": "B22B-001"}),
            ),
            ChecklistRow(
                "b22b-deficiency-002", None,
                json.dumps({"id": "DEF-002", "description": "重要缺陷描述", "impact": "影响较大", "severity": "significant", "index_ref": "B22B-002"}),
            ),
            ChecklistRow(
                "b22b-deficiency-003", None,
                json.dumps({"id": "DEF-003", "description": "一般缺陷描述", "impact": "影响轻微", "severity": "general", "index_ref": "B22B-003"}),
            ),
        ]
        proj = ProjectRow("测试公司", 2025)
        ctx = _make_ctx(
            checklist_rows=[],
            project_row=proj,
            b22b_wp_id="b22b-wp-001",
            b22b_checklist_rows=b22b_rows,
        )

        result = await render(ctx)

        assert len(result["deficiency_list"]["major"]) == 1
        assert len(result["deficiency_list"]["significant"]) == 1
        assert len(result["deficiency_list"]["general"]) == 1
        assert result["deficiency_list"]["major"][0]["id"] == "DEF-001"
        assert result["deficiency_list"]["major"][0]["source"] == "b22b"
        assert result["b22b_warning"] is None

    @pytest.mark.asyncio
    async def test_b22b_new_structured_format_loaded(self):
        """新版 B22B 分字段结构（B22B-def-{n}-*）能被正确重建为缺陷清单。"""
        b22b_rows = [
            ChecklistRow("B22B-def-count", None, "3"),
            # 缺陷1：重大缺陷
            ChecklistRow(
                "B22B-def-1-source", None,
                json.dumps({"tab": 1, "subPanel": None, "index": 1, "controlPoint": "高层基调缺失",
                            "deficiencyType": "设计无效", "elementName": "控制环境"}),
            ),
            ChecklistRow("B22B-def-1-severity", "重大缺陷", None),
            ChecklistRow("B22B-def-1-corrective", "Y", "建立行为准则"),
            # 缺陷2：重要缺陷
            ChecklistRow(
                "B22B-def-2-source", None,
                json.dumps({"tab": 2, "subPanel": None, "index": 1, "controlPoint": "风险评估不充分",
                            "deficiencyType": "未实施", "elementName": "风险评估过程"}),
            ),
            ChecklistRow("B22B-def-2-severity", "重要缺陷", None),
            # 缺陷3：已消除（应跳过）
            ChecklistRow(
                "B22B-def-3-source", None,
                json.dumps({"tab": 5, "subPanel": None, "index": 1, "controlPoint": "监督缺陷",
                            "deficiencyType": "设计无效", "elementName": "监督"}),
            ),
            ChecklistRow("B22B-def-3-severity", "一般缺陷", None),
            ChecklistRow("B22B-def-3-eliminated", "Y", None),
        ]
        proj = ProjectRow("测试公司", 2025)
        ctx = _make_ctx(
            checklist_rows=[],
            project_row=proj,
            b22b_wp_id="b22b-wp-001",
            b22b_checklist_rows=b22b_rows,
        )

        result = await render(ctx)

        # 重大1 + 重要1；已消除的一般缺陷被跳过
        assert len(result["deficiency_list"]["major"]) == 1
        assert len(result["deficiency_list"]["significant"]) == 1
        assert len(result["deficiency_list"]["general"]) == 0
        major = result["deficiency_list"]["major"][0]
        assert major["description"] == "高层基调缺失"
        assert major["recommendation"] == "建立行为准则"
        assert major["source"] == "b22b"
        assert result["b22b_warning"] is None

    @pytest.mark.asyncio
    async def test_b22b_deficiencies_new_format(self):
        """B22B 真实持久化格式（B22B-def-{n}-* 分字段）被正确重建并分组."""
        b22b_rows = [
            ChecklistRow("B22B-def-count", None, "3"),
            # 缺陷1：重大缺陷
            ChecklistRow(
                "B22B-def-1-source", None,
                json.dumps({"tab": 1, "subPanel": None, "index": 1, "controlPoint": "高层基调缺失",
                            "deficiencyType": "设计无效", "elementName": "控制环境"}),
            ),
            ChecklistRow("B22B-def-1-severity", "重大缺陷", None),
            ChecklistRow("B22B-def-1-corrective", "Y", "建议建立行为准则"),
            # 缺陷2：一般缺陷
            ChecklistRow(
                "B22B-def-2-source", None,
                json.dumps({"tab": 5, "subPanel": None, "index": 2, "controlPoint": "内审覆盖不足",
                            "deficiencyType": "未实施", "elementName": "监督"}),
            ),
            ChecklistRow("B22B-def-2-severity", "一般缺陷", None),
            # 缺陷3：已消除（应跳过）
            ChecklistRow(
                "B22B-def-3-source", None,
                json.dumps({"tab": 2, "subPanel": None, "index": 3, "controlPoint": "已整改项",
                            "deficiencyType": "设计无效", "elementName": "风险评估过程"}),
            ),
            ChecklistRow("B22B-def-3-severity", "重要缺陷", None),
            ChecklistRow("B22B-def-3-eliminated", "Y", None),
        ]
        proj = ProjectRow("测试公司", 2025)
        ctx = _make_ctx(
            checklist_rows=[],
            project_row=proj,
            b22b_wp_id="b22b-wp-001",
            b22b_checklist_rows=b22b_rows,
        )

        result = await render(ctx)

        assert len(result["deficiency_list"]["major"]) == 1
        assert result["deficiency_list"]["major"][0]["description"] == "高层基调缺失"
        assert result["deficiency_list"]["major"][0]["recommendation"] == "建议建立行为准则"
        assert result["deficiency_list"]["major"][0]["source"] == "b22b"
        assert len(result["deficiency_list"]["general"]) == 1
        assert result["deficiency_list"]["general"][0]["description"] == "内审覆盖不足"
        # 已消除的重要缺陷不应出现
        assert len(result["deficiency_list"]["significant"]) == 0
        assert result["b22b_warning"] is None

    @pytest.mark.asyncio
    async def test_manual_and_b22b_deficiencies_merged(self):
        """Manual deficiencies from A9-1 merged with B22B deficiencies."""
        manual_items = [{"id": "M-001", "description": "手动缺陷", "impact": "轻微", "recommendation": "建议", "indexRef": None}]
        a91_rows = [
            ChecklistRow("a91-deficiency-major", "1", json.dumps(manual_items)),
        ]
        b22b_rows = [
            ChecklistRow(
                "b22b-deficiency-001", None,
                json.dumps({"id": "DEF-001", "description": "B22B缺陷", "impact": "重大", "severity": "major", "index_ref": "B22B-001"}),
            ),
        ]
        proj = ProjectRow("测试公司", 2025)
        ctx = _make_ctx(
            checklist_rows=a91_rows,
            project_row=proj,
            b22b_wp_id="b22b-wp-001",
            b22b_checklist_rows=b22b_rows,
        )

        result = await render(ctx)

        # B22B first, then manual
        assert len(result["deficiency_list"]["major"]) == 2
        assert result["deficiency_list"]["major"][0]["source"] == "b22b"
        assert result["deficiency_list"]["major"][1]["source"] == "manual"


# ─── Tests: B22B Absent ──────────────────────────────────────────────────────


class TestA91RenderB22BAbsent:
    """B22B workpaper not found scenarios."""

    @pytest.mark.asyncio
    async def test_b22b_absent_returns_warning(self):
        """When B22B not found, returns empty deficiency list + warning."""
        proj = ProjectRow("测试公司", 2025)
        ctx = _make_ctx(checklist_rows=[], project_row=proj, b22b_wp_id=None)

        result = await render(ctx)

        assert result["b22b_warning"] == "未找到B22B内控缺陷评价表"
        assert result["deficiency_list"]["major"] == []
        assert result["deficiency_list"]["significant"] == []
        assert result["deficiency_list"]["general"] == []

    @pytest.mark.asyncio
    async def test_b22b_absent_still_returns_manual_deficiencies(self):
        """Manual deficiencies still returned when B22B is absent."""
        manual_items = [{"id": "M-001", "description": "手动缺陷", "impact": "影响", "recommendation": "建议"}]
        rows = [
            ChecklistRow("a91-deficiency-general", "1", json.dumps(manual_items)),
        ]
        proj = ProjectRow("测试公司", 2025)
        ctx = _make_ctx(checklist_rows=rows, project_row=proj, b22b_wp_id=None)

        result = await render(ctx)

        assert result["b22b_warning"] == "未找到B22B内控缺陷评价表"
        assert len(result["deficiency_list"]["general"]) == 1
        assert result["deficiency_list"]["general"][0]["source"] == "manual"


# ─── Tests: Empty Responses ──────────────────────────────────────────────────


class TestA91RenderEmpty:
    """Empty/missing data scenarios."""

    @pytest.mark.asyncio
    async def test_empty_responses_returns_defaults(self):
        """No saved data returns default structure."""
        ctx = _make_ctx(checklist_rows=[], project_row=None)

        result = await render(ctx)

        assert result is not None
        assert result["section_data"]["addressee"]["client_name"] == ""
        assert result["section_data"]["independence"]["team_independent"] is None
        assert result["section_data"]["committee"]["applicability"] is None
        assert result["section_data"]["signature"]["date"] is None
        assert result["section_data"]["response"]["opinion"] is None

    @pytest.mark.asyncio
    async def test_project_context_auto_fill(self):
        """Project context auto-fills client_name and audit_report_date."""
        proj = ProjectRow("自动填充公司", 2025)
        ctx = _make_ctx(checklist_rows=[], project_row=proj)

        result = await render(ctx)

        assert result["project_context"]["client_name"] == "自动填充公司"
        assert result["project_context"]["audit_report_date"] == "2025年12月31日"
        assert result["project_context"]["firm_name"] == "致同会计师事务所（特殊普通合伙）"

    @pytest.mark.asyncio
    async def test_addressee_auto_fill_from_project(self):
        """Addressee client_name auto-fills from project when not manually set."""
        proj = ProjectRow("项目公司名", 2025)
        ctx = _make_ctx(checklist_rows=[], project_row=proj)

        result = await render(ctx)

        assert result["section_data"]["addressee"]["client_name"] == "项目公司名"

    @pytest.mark.asyncio
    async def test_no_project_returns_empty_context(self):
        """Missing project row returns empty context."""
        ctx = _make_ctx(checklist_rows=[], project_row=None)

        result = await render(ctx)

        assert result["project_context"]["client_name"] == ""
        assert result["project_context"]["audit_report_date"] is None


# ─── Tests: Invalid JSON remark ──────────────────────────────────────────────


class TestA91RenderInvalidJson:
    """Invalid JSON in remark field handling."""

    @pytest.mark.asyncio
    async def test_invalid_json_deficiency_remark_graceful(self):
        """Invalid JSON in deficiency remark does not crash render."""
        rows = [
            ChecklistRow("a91-deficiency-major", "1", "not valid json{{{"),
        ]
        proj = ProjectRow("测试公司", 2025)
        ctx = _make_ctx(checklist_rows=rows, project_row=proj)

        result = await render(ctx)

        # Should return empty list for that severity, no crash
        assert result["deficiency_list"]["major"] == []

    @pytest.mark.asyncio
    async def test_non_list_json_deficiency_remark(self):
        """JSON remark that is not a list is ignored gracefully."""
        rows = [
            ChecklistRow("a91-deficiency-significant", "1", json.dumps({"not": "a list"})),
        ]
        proj = ProjectRow("测试公司", 2025)
        ctx = _make_ctx(checklist_rows=rows, project_row=proj)

        result = await render(ctx)

        assert result["deficiency_list"]["significant"] == []

    @pytest.mark.asyncio
    async def test_partial_deficiency_items_parsed(self):
        """Deficiency items with missing fields still parse with defaults."""
        items = [{"id": "PARTIAL-001"}]  # Missing description, impact, recommendation
        rows = [
            ChecklistRow("a91-deficiency-general", "1", json.dumps(items)),
        ]
        proj = ProjectRow("测试公司", 2025)
        ctx = _make_ctx(checklist_rows=rows, project_row=proj)

        result = await render(ctx)

        assert len(result["deficiency_list"]["general"]) == 1
        item = result["deficiency_list"]["general"][0]
        assert item["id"] == "PARTIAL-001"
        assert item["description"] == ""
        assert item["impact"] == ""
        assert item["recommendation"] == ""


# ─── Tests: Response Structure ───────────────────────────────────────────────


class TestA91RenderStructure:
    """Response structure validation."""

    @pytest.mark.asyncio
    async def test_response_has_four_top_keys(self):
        """Response always has exactly 4 top-level keys."""
        ctx = _make_ctx(checklist_rows=[], project_row=None)

        result = await render(ctx)

        assert set(result.keys()) == {"section_data", "deficiency_list", "project_context", "b22b_warning"}

    @pytest.mark.asyncio
    async def test_section_data_has_5_sections(self):
        """section_data always has 5 section sub-keys."""
        ctx = _make_ctx(checklist_rows=[], project_row=None)

        result = await render(ctx)

        assert set(result["section_data"].keys()) == {
            "addressee", "independence", "committee", "signature", "response"
        }

    @pytest.mark.asyncio
    async def test_deficiency_list_has_3_severities(self):
        """deficiency_list always has 3 severity keys."""
        ctx = _make_ctx(checklist_rows=[], project_row=None)

        result = await render(ctx)

        assert set(result["deficiency_list"].keys()) == {"major", "significant", "general"}


# ─── Tests: B22C preferred (Wave3 repoint) ───────────────────────────────────


class TestA91RenderB22CPreferred:
    """Wave3: B22C 为缺陷严重程度单一真源，优先于 B22B 读取。"""

    @pytest.mark.asyncio
    async def test_b22c_deficiencies_loaded_and_grouped(self):
        """B22C 缺陷按 severity 中文映射为 major/significant/general 分组。"""
        b22c_rows = [
            ChecklistRow("B22C-env-def-count", None, "1"),
            ChecklistRow("B22C-env-def-1-desc", None, "控制环境重大缺陷"),
            ChecklistRow("B22C-env-def-1-severity", "重大缺陷", None),
            ChecklistRow("B22C-risk-def-count", None, "1"),
            ChecklistRow("B22C-risk-def-1-desc", None, "风险评估重要缺陷"),
            ChecklistRow("B22C-risk-def-1-severity", "重要缺陷", None),
            ChecklistRow("B22C-monitor-def-count", None, "1"),
            ChecklistRow("B22C-monitor-def-1-desc", None, "监督一般缺陷"),
            ChecklistRow("B22C-monitor-def-1-severity", "一般缺陷", None),
        ]
        proj = ProjectRow("测试公司", 2025)
        ctx = _make_ctx(
            checklist_rows=[],
            project_row=proj,
            b22c_wp_id="b22c-wp-001",
            b22c_checklist_rows=b22c_rows,
        )

        result = await render(ctx)

        assert len(result["deficiency_list"]["major"]) == 1
        assert len(result["deficiency_list"]["significant"]) == 1
        assert len(result["deficiency_list"]["general"]) == 1
        assert result["deficiency_list"]["major"][0]["description"] == "控制环境重大缺陷"
        assert result["deficiency_list"]["major"][0]["source"] == "b22c"
        assert result["deficiency_list"]["major"][0]["index_ref"] == "控制环境"
        # B22C 有数据 → warning 为 None（源已找到）
        assert result["b22b_warning"] is None

    @pytest.mark.asyncio
    async def test_b22c_empty_severity_falls_back_to_flags(self):
        """B22C 未评定 severity 时按 flags.sig 回退（值得关注→significant，否则→general）。"""
        b22c_rows = [
            ChecklistRow("B22C-info-def-count", None, "2"),
            ChecklistRow("B22C-info-def-1-desc", None, "标记为值得关注的缺陷"),
            ChecklistRow("B22C-info-def-1-flags", None, json.dumps({"cd": True, "sig": True})),
            ChecklistRow("B22C-info-def-2-desc", None, "普通控制缺陷"),
            ChecklistRow("B22C-info-def-2-flags", None, json.dumps({"cd": True, "sig": False})),
        ]
        proj = ProjectRow("测试公司", 2025)
        ctx = _make_ctx(
            checklist_rows=[],
            project_row=proj,
            b22c_wp_id="b22c-wp-001",
            b22c_checklist_rows=b22c_rows,
        )

        result = await render(ctx)

        assert len(result["deficiency_list"]["significant"]) == 1
        assert result["deficiency_list"]["significant"][0]["description"] == "标记为值得关注的缺陷"
        assert len(result["deficiency_list"]["general"]) == 1
        assert result["deficiency_list"]["general"][0]["description"] == "普通控制缺陷"

    @pytest.mark.asyncio
    async def test_b22c_empty_desc_skipped(self):
        """B22C 空 desc 占位条目不计入缺陷函。"""
        b22c_rows = [
            ChecklistRow("B22C-env-def-count", None, "2"),
            ChecklistRow("B22C-env-def-1-desc", None, "真实缺陷"),
            ChecklistRow("B22C-env-def-1-severity", "重大缺陷", None),
            ChecklistRow("B22C-env-def-2-desc", None, "   "),  # 空白占位
            ChecklistRow("B22C-env-def-2-severity", "一般缺陷", None),
        ]
        proj = ProjectRow("测试公司", 2025)
        ctx = _make_ctx(
            checklist_rows=[],
            project_row=proj,
            b22c_wp_id="b22c-wp-001",
            b22c_checklist_rows=b22c_rows,
        )

        result = await render(ctx)

        total = sum(len(result["deficiency_list"][s]) for s in ("major", "significant", "general"))
        assert total == 1
        assert result["deficiency_list"]["major"][0]["description"] == "真实缺陷"

    @pytest.mark.asyncio
    async def test_b22c_dedup_over_b22b(self):
        """B22C 与 B22B 同 description 缺陷去重，不重复计入。"""
        b22c_rows = [
            ChecklistRow("B22C-env-def-count", None, "1"),
            ChecklistRow("B22C-env-def-1-desc", None, "重复的控制缺陷"),
            ChecklistRow("B22C-env-def-1-severity", "重大缺陷", None),
        ]
        b22b_rows = [
            ChecklistRow(
                "b22b-deficiency-001", None,
                json.dumps({"id": "DEF-DUP", "description": "重复的控制缺陷", "impact": "x", "severity": "major"}),
            ),
            ChecklistRow(
                "b22b-deficiency-002", None,
                json.dumps({"id": "DEF-UNIQUE", "description": "仅 B22B 的缺陷", "impact": "y", "severity": "significant"}),
            ),
        ]
        proj = ProjectRow("测试公司", 2025)
        ctx = _make_ctx(
            checklist_rows=[],
            project_row=proj,
            b22c_wp_id="b22c-wp-001",
            b22c_checklist_rows=b22c_rows,
            b22b_wp_id="b22b-wp-001",
            b22b_checklist_rows=b22b_rows,
        )

        result = await render(ctx)

        # major：只有 B22C 的重复缺陷（B22B 同名去重）
        assert len(result["deficiency_list"]["major"]) == 1
        assert result["deficiency_list"]["major"][0]["source"] == "b22c"
        # significant：B22B 独有缺陷仍保留
        assert len(result["deficiency_list"]["significant"]) == 1
        assert result["deficiency_list"]["significant"][0]["id"] == "DEF-UNIQUE"

    @pytest.mark.asyncio
    async def test_p5_grouping_equivalence_b22c_vs_b22b(self):
        """P5：同一批缺陷数据，经 B22C（新源）与经 B22B（旧源）的分组结果等价。"""
        # 同一组缺陷：重大/重要/一般 各 1
        b22c_rows = [
            ChecklistRow("B22C-env-def-count", None, "1"),
            ChecklistRow("B22C-env-def-1-desc", None, "缺陷A"),
            ChecklistRow("B22C-env-def-1-severity", "重大缺陷", None),
            ChecklistRow("B22C-risk-def-count", None, "1"),
            ChecklistRow("B22C-risk-def-1-desc", None, "缺陷B"),
            ChecklistRow("B22C-risk-def-1-severity", "重要缺陷", None),
            ChecklistRow("B22C-monitor-def-count", None, "1"),
            ChecklistRow("B22C-monitor-def-1-desc", None, "缺陷C"),
            ChecklistRow("B22C-monitor-def-1-severity", "一般缺陷", None),
        ]
        b22b_rows = [
            ChecklistRow("B22B-def-count", None, "3"),
            ChecklistRow("B22B-def-1-source", None, json.dumps({"tab": 1, "index": 1, "controlPoint": "缺陷A", "elementName": "控制环境"})),
            ChecklistRow("B22B-def-1-severity", "重大缺陷", None),
            ChecklistRow("B22B-def-2-source", None, json.dumps({"tab": 2, "index": 1, "controlPoint": "缺陷B", "elementName": "风险评估过程"})),
            ChecklistRow("B22B-def-2-severity", "重要缺陷", None),
            ChecklistRow("B22B-def-3-source", None, json.dumps({"tab": 5, "index": 1, "controlPoint": "缺陷C", "elementName": "监督"})),
            ChecklistRow("B22B-def-3-severity", "一般缺陷", None),
        ]
        proj = ProjectRow("测试公司", 2025)

        ctx_b22c = _make_ctx(
            checklist_rows=[], project_row=proj,
            b22c_wp_id="b22c-wp-001", b22c_checklist_rows=b22c_rows,
        )
        ctx_b22b = _make_ctx(
            checklist_rows=[], project_row=ProjectRow("测试公司", 2025),
            b22b_wp_id="b22b-wp-001", b22b_checklist_rows=b22b_rows,
        )

        res_c = await render(ctx_b22c)
        res_b = await render(ctx_b22b)

        # 分组成员数量等价（P5）
        for sev in ("major", "significant", "general"):
            assert len(res_c["deficiency_list"][sev]) == len(res_b["deficiency_list"][sev]) == 1
        # 分组成员描述等价
        assert {d["description"] for d in res_c["deficiency_list"]["major"]} == {"缺陷A"}
        assert {d["description"] for d in res_b["deficiency_list"]["major"]} == {"缺陷A"}
