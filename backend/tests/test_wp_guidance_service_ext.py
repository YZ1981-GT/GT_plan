"""GuidanceService 扩展测试 — 复杂度分类 + 推荐问题 + 完整响应结构

验证 Task 3.1/3.2 的核心逻辑：
1. classify_complexity 返回正确等级
2. get_recommended_questions 返回非空列表
3. GuidanceService.get_guidance 返回正确结构
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest


def _validated_runtime_entry(
    *,
    code: str = "A3-8",
    status: str = "exact",
    context_kind: str = "sheet",
    blockers: tuple[str, ...] = (),
):
    from app.services.guidance_inventory import GuidanceSourceFact

    facts = (
        GuidanceSourceFact(
            kind="static_guidance",
            ref=f"/guidance/{code}.json",
            digest="a" * 64,
            origin="ok",
        ),
        GuidanceSourceFact(
            kind="source_ref_validation",
            ref=f"/guidance/{code}.json#source_refs",
            digest="b" * 64,
            origin="valid",
        ),
    )
    entry = SimpleNamespace(
        entry_id=f"entry-{code}",
        entry_digest="c" * 64,
        parent_wp_code="A3",
        sheet_code=code,
        sheet_name=code,
        context_kind=context_kind,
        required=status != "inherited",
        exact_status=status,
        missing_sections=(),
        exact_blockers=blockers,
        stale_reasons=(),
        source_facts=facts,
    )
    entry.version_facts = lambda: {
        "entry_id": entry.entry_id,
        "entry_digest": entry.entry_digest,
        "exact_status": entry.exact_status,
    }
    return entry


# ---------------------------------------------------------------------------
# 1. classify_complexity 测试
# ---------------------------------------------------------------------------


class TestClassifyComplexity:
    """复杂度分类单元测试"""

    def _get_service(self):
        from app.services.wp_guidance_service import GuidanceService
        return GuidanceService()

    def test_high_complexity_exact_match(self):
        """精确匹配高复杂度底稿"""
        svc = self._get_service()
        assert svc.classify_complexity("A17") == "high"
        assert svc.classify_complexity("B60") == "high"
        assert svc.classify_complexity("B50") == "high"
        assert svc.classify_complexity("B51") == "high"

    def test_high_complexity_determination_pattern(self):
        """通配符 *-1 匹配审定表"""
        svc = self._get_service()
        assert svc.classify_complexity("D2-1") == "high"
        assert svc.classify_complexity("E1-1") == "high"
        assert svc.classify_complexity("F1-1") == "high"
        assert svc.classify_complexity("N2-1") == "high"

    def test_high_complexity_program_pattern(self):
        """通配符 *A 匹配程序表"""
        svc = self._get_service()
        assert svc.classify_complexity("D0A") == "high"
        assert svc.classify_complexity("E1A") == "high"
        assert svc.classify_complexity("F0A") == "high"

    def test_medium_complexity(self):
        """中复杂度底稿匹配"""
        svc = self._get_service()
        assert svc.classify_complexity("A1-15") == "medium"
        assert svc.classify_complexity("A1-16") == "medium"
        assert svc.classify_complexity("A1-13") == "medium"
        assert svc.classify_complexity("A1-14") == "medium"
        assert svc.classify_complexity("A5") == "medium"

    def test_medium_complexity_s_pattern(self):
        """S* 通配符匹配专项底稿"""
        svc = self._get_service()
        assert svc.classify_complexity("S1") == "medium"
        assert svc.classify_complexity("S32") == "medium"

    def test_low_complexity_default(self):
        """默认为低复杂度"""
        svc = self._get_service()
        assert svc.classify_complexity("A2") == "low"
        assert svc.classify_complexity("A3") == "low"
        assert svc.classify_complexity("X99") == "low"

    def test_deterministic(self):
        """相同输入多次调用结果一致"""
        svc = self._get_service()
        results = [svc.classify_complexity("D2-1") for _ in range(5)]
        assert all(r == "high" for r in results)

    def test_return_valid_literal(self):
        """返回值永远是 high/medium/low 之一"""
        svc = self._get_service()
        codes = ["A17", "B60", "D2-1", "E1A", "A1-15", "S1", "A2", "X99", ""]
        valid = {"high", "medium", "low"}
        for code in codes:
            assert svc.classify_complexity(code) in valid


# ---------------------------------------------------------------------------
# 2. get_recommended_questions 测试
# ---------------------------------------------------------------------------


class TestRecommendedQuestions:
    """推荐问题映射测试"""

    def _get_service(self):
        from app.services.wp_guidance_service import GuidanceService
        return GuidanceService()

    def test_program_table_questions(self):
        """程序表(以A结尾)返回程序表问题"""
        svc = self._get_service()
        questions = svc.get_recommended_questions("D0A")
        assert len(questions) > 0
        # 程序表问题应包含"步骤"相关
        assert any("步骤" in q for q in questions)

    def test_determination_table_questions(self):
        """审定表(以-1结尾)返回审定表问题"""
        svc = self._get_service()
        questions = svc.get_recommended_questions("D2-1")
        assert len(questions) > 0
        # 审定表问题应包含"金额"或"取数"相关
        assert any("金额" in q or "取数" in q for q in questions)

    def test_default_questions(self):
        """通用底稿返回默认问题"""
        svc = self._get_service()
        questions = svc.get_recommended_questions("A2")
        assert len(questions) > 0

    def test_known_codes_non_empty(self):
        """已知底稿编码返回非空问题列表"""
        svc = self._get_service()
        for code in ["D0A", "E1A", "D2-1", "F1-1", "A3", "B60"]:
            questions = svc.get_recommended_questions(code)
            assert isinstance(questions, list)
            assert len(questions) > 0, f"{code} 应有推荐问题"


# ---------------------------------------------------------------------------
# 3. GuidanceService.get_guidance 完整结构测试
# ---------------------------------------------------------------------------


class TestGetGuidance:
    """GuidanceService.get_guidance 响应结构验证"""

    @pytest.mark.asyncio
    async def test_response_structure(self):
        """验证响应包含所有必需字段"""
        from app.services.wp_guidance_service import GuidanceService

        svc = GuidanceService()
        response = await svc.get_guidance(
            wp_code="A17",
            wp_name="重大事项概要",
            template_path=None,
        )

        # 必须字段
        assert "wp_code" in response
        assert "wp_name" in response
        assert "source" in response
        assert "complexity" in response
        assert "guidance" in response
        assert "recommended_questions" in response

        # guidance 子结构
        assert "sections" in response["guidance"]
        assert "raw_text" in response["guidance"]

    @pytest.mark.asyncio
    async def test_source_is_valid_enum(self):
        """source 字段值合法"""
        from app.services.wp_guidance_service import GuidanceService

        svc = GuidanceService()
        response = await svc.get_guidance(wp_code="A17", template_path=None)

        valid_sources = {
            "template_sheet", "template_header", "docx_instructions",
            "static_json", "typed_fallback", "fallback"
        }
        assert response["source"] in valid_sources

    @pytest.mark.asyncio
    async def test_never_empty_raw_text(self):
        """raw_text 永不为空字符串"""
        from app.services.wp_guidance_service import GuidanceService

        svc = GuidanceService()
        # 即使完全未知的 wp_code，fallback 也应提供内容
        response = await svc.get_guidance(wp_code="ZZZZZ_UNKNOWN", template_path=None)
        assert response["guidance"]["raw_text"] != ""

    @pytest.mark.asyncio
    async def test_complexity_matches_code(self):
        """响应中的 complexity 与 classify_complexity 一致"""
        from app.services.wp_guidance_service import GuidanceService

        svc = GuidanceService()
        response = await svc.get_guidance(wp_code="D2-1", template_path=None)
        assert response["complexity"] == "high"

        response2 = await svc.get_guidance(wp_code="A2", template_path=None)
        assert response2["complexity"] == "low"

    @pytest.mark.asyncio
    async def test_static_json_source(self):
        """有静态 JSON 文件的底稿返回 static_json 来源"""
        from app.services.wp_guidance_service import GuidanceService

        svc = GuidanceService()
        response = await svc.get_guidance(wp_code="A17", template_path=None)
        assert response["source"] == "static_json"
        assert len(response["guidance"]["sections"]) > 0


# ---------------------------------------------------------------------------
# 4. child/parent resolution 与版本元数据
# ---------------------------------------------------------------------------


class TestGuidanceResolution:
    @staticmethod
    def _result(source="static_json", *, complete=True):
        from app.services.guidance_extractor import GuidanceResult, GuidanceSection
        from app.services.guidance_inventory import CANONICAL_SECTION_KEYS

        keys = CANONICAL_SECTION_KEYS if complete else ("steps",)
        sections = [
            GuidanceSection(
                heading=key,
                content=f"{key} content",
                order=index,
                key=key,
                source_refs=[{"kind": "xlsx", "path": "backend/wp_templates/A/example.xlsx"}]
                if source not in {"typed_fallback", "fallback"} else [],
            )
            for index, key in enumerate(keys)
        ]
        return GuidanceResult(
            wp_code="A3-8",
            source=source,
            sections=sections,
            raw_text="\n".join(section.content for section in sections),
        )

    @pytest.mark.asyncio
    async def test_child_exact_short_circuits_parent_full_chain(self):
        from unittest.mock import AsyncMock
        from app.services.wp_guidance_service import GuidanceService

        service = GuidanceService()
        child = self._result()
        service._extractor.extract_exact_static = AsyncMock(return_value=child)
        service._extractor.extract_full = AsyncMock()

        response = await service.resolve_guidance(
            parent_wp_code="A3",
            requested_sheet_code="A3-8",
            wp_name="商誉减值测试",
            runtime_entry=_validated_runtime_entry(),
        )

        assert response["requested_sheet_code"] == "A3-8"
        assert response["resolved_wp_code"] == "A3-8"
        assert response["inherited_from_parent"] is False
        assert response["resolution_status"] == "exact"
        assert response["resolution_reason"] == "child_exact_static"
        service._extractor.extract_full.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_child_miss_enters_parent_typed_chain_without_child_template(self):
        from unittest.mock import AsyncMock
        from pathlib import Path
        from app.services.wp_guidance_service import GuidanceService

        service = GuidanceService()
        parent = self._result("typed_fallback", complete=False)
        service._extractor.extract_exact_static = AsyncMock(return_value=None)
        service._extractor.extract_full = AsyncMock(return_value=parent)
        template = Path("backend/wp_templates/A/parent.xlsx")

        response = await service.resolve_guidance(
            parent_wp_code="A3",
            requested_sheet_code="A3-99",
            parent_template_path=template,
        )

        service._extractor.extract_exact_static.assert_awaited_once_with(
            "A3-99", validated_entry=None
        )
        service._extractor.extract_full.assert_awaited_once_with("A3", template)
        assert response["resolved_wp_code"] == "A3"
        assert response["inherited_from_parent"] is True
        assert response["resolution_status"] == "parent_inherited"
        assert response["source"] == "typed_fallback"
        assert response["resolution_reason"].startswith("child_missing:")

    @pytest.mark.asyncio
    async def test_version_and_digest_are_stable_for_same_source_facts(self):
        from unittest.mock import AsyncMock
        from app.services.wp_guidance_service import GuidanceService

        service = GuidanceService()
        parent = self._result(complete=True)
        service._extractor.extract_full = AsyncMock(return_value=parent)

        first = await service.get_guidance("A3", "商誉")
        second = await service.get_guidance("A3", "商誉")

        assert first["guidance_version"] == second["guidance_version"]
        assert first["source_digest"] == second["source_digest"]
        assert first["guidance_version"].startswith("guidance-v2-")
        assert first["generated_at"]
        assert first["missing_sections"] == []
        assert first["resolution_status"] == "invalid"
        assert first["exact_blockers"] == ["source_ref_context_missing"]


class TestRuntimeInventoryVersioning:
    @staticmethod
    def _entry(*, component_type: str = "d-form-table", stale: bool = False):
        from app.services.guidance_inventory import (
            GuidanceInventoryEntry,
            build_runtime_guidance_inventory,
        )

        static = GuidanceInventoryEntry(
            wp_code="A3-8",
            path="/guidance/A3-8.json",
            parse_status="ok",
            source_digest="a" * 64,
            exact_status="exact",
            missing_sections=(),
            reason="ok",
            source_ref_status="valid",
            source_ref_facts_digest="d" * 64,
        )
        render = {
            "sheet_code": "A3-8",
            "sheet_name": "商誉减值测试 A3-8",
            "sheet_code_reason": "explicit_code",
            "whole_workbook": False,
            "componentType": component_type,
        }
        first = build_runtime_guidance_inventory(
            parent_wp_code="A3",
            render_sheets=[render],
            static_entries=[static],
            include_whole_workbook_context=False,
        )
        if not stale:
            return first.entries[0], first.facts_digest
        changed = build_runtime_guidance_inventory(
            parent_wp_code="A3",
            render_sheets=[{**render, "componentType": "onlyoffice"}],
            static_entries=[static],
            prior_entry_digests={first.entries[0].entry_id: first.entries[0].entry_digest},
            include_whole_workbook_context=False,
        )
        return changed.entries[0], changed.facts_digest

    @staticmethod
    def _complete_result():
        from app.services.guidance_extractor import GuidanceResult, GuidanceSection
        from app.services.guidance_inventory import CANONICAL_SECTION_KEYS

        sections = [
            GuidanceSection(
                heading=key,
                content=f"{key} content",
                order=index,
                key=key,
                source_refs=[{"kind": "xlsx", "path": "backend/wp_templates/A/example.xlsx"}],
            )
            for index, key in enumerate(CANONICAL_SECTION_KEYS)
        ]
        return GuidanceResult(
            wp_code="A3-8",
            source="static_json",
            sections=sections,
            raw_text="\n".join(section.content for section in sections),
        )

    @pytest.mark.asyncio
    async def test_runtime_source_fact_changes_response_version(self):
        from unittest.mock import AsyncMock
        from app.services.wp_guidance_service import GuidanceService

        service = GuidanceService()
        service._extractor.extract_exact_static = AsyncMock(return_value=self._complete_result())
        first_entry, first_inventory_digest = self._entry(component_type="d-form-table")
        second_entry, second_inventory_digest = self._entry(component_type="onlyoffice")

        first = await service.resolve_guidance(
            parent_wp_code="A3",
            requested_sheet_code="A3-8",
            runtime_entry=first_entry,
            inventory_facts_digest=first_inventory_digest,
            inventory_run_id="run-a",
        )
        second = await service.resolve_guidance(
            parent_wp_code="A3",
            requested_sheet_code="A3-8",
            runtime_entry=second_entry,
            inventory_facts_digest=second_inventory_digest,
            inventory_run_id="run-b",
        )

        assert first["guidance_version"] != second["guidance_version"]
        assert first["source_digest"] != second["source_digest"]
        assert first["inventory_entry_id"] == second["inventory_entry_id"]
        assert first["inventory_entry_digest"] != second["inventory_entry_digest"]
        assert first["inventory_run_id"] == "run-a"
        assert second["inventory_run_id"] == "run-b"

    @pytest.mark.asyncio
    async def test_runtime_unmapped_blocker_prevents_complete_result_from_becoming_exact(self):
        from unittest.mock import AsyncMock
        from app.services.guidance_inventory import (
            GuidanceInventoryEntry,
            build_runtime_guidance_inventory,
        )
        from app.services.wp_guidance_service import GuidanceService

        static = GuidanceInventoryEntry(
            wp_code="A3-8",
            path="/guidance/A3-8.json",
            parse_status="ok",
            source_digest="c" * 64,
            exact_status="missing",
            missing_sections=(),
            reason="incomplete:unmapped_sections",
            exact_blockers=("unmapped_sections",),
            source_ref_status="valid",
            source_ref_facts_digest="e" * 64,
        )
        inventory = build_runtime_guidance_inventory(
            parent_wp_code="A3-8",
            render_sheets=[{
                "sheet_code": "A3-8",
                "sheet_name": "商誉减值测试 A3-8",
                "sheet_code_reason": "explicit_code",
                "whole_workbook": False,
                "componentType": "d-form-table",
            }],
            static_entries=[static],
            include_whole_workbook_context=False,
        )
        service = GuidanceService()
        service._extractor.extract_full = AsyncMock(return_value=self._complete_result())

        response = await service.resolve_guidance(
            parent_wp_code="A3-8",
            requested_sheet_code="A3-8",
            runtime_entry=inventory.entries[0],
            inventory_facts_digest=inventory.facts_digest,
            inventory_run_id="run-unmapped",
        )

        assert response["resolution_status"] == "missing"
        assert response["runtime_guidance_status"] == "missing"
        assert response["missing_sections"] == []
        assert response["exact_blockers"] == ["unmapped_sections"]

    @pytest.mark.asyncio
    async def test_stale_runtime_entry_overrides_parent_inherited_success_wording(self):
        from unittest.mock import AsyncMock
        from app.services.wp_guidance_service import GuidanceService

        service = GuidanceService()
        service._extractor.extract_exact_static = AsyncMock(return_value=None)
        service._extractor.extract_full = AsyncMock(return_value=self._complete_result())
        stale_entry, inventory_digest = self._entry(stale=True)

        response = await service.resolve_guidance(
            parent_wp_code="A3",
            requested_sheet_code="A3-8",
            runtime_entry=stale_entry,
            inventory_facts_digest=inventory_digest,
            inventory_run_id="run-stale",
        )

        assert response["inherited_from_parent"] is True
        assert response["resolution_status"] == "stale"
        assert response["runtime_guidance_status"] == "stale"
        assert response["stale_reasons"] == ["source_facts_changed"]
        assert response["guidance_required"] is True

    @pytest.mark.asyncio
    async def test_whole_workbook_uses_parent_chain_with_explicit_context(self):
        from unittest.mock import AsyncMock
        from app.services.wp_guidance_service import GuidanceService

        service = GuidanceService()
        service._extractor.extract_full = AsyncMock(return_value=self._complete_result())

        response = await service.resolve_guidance(
            parent_wp_code="A3",
            requested_sheet_code=None,
            whole_workbook=True,
            runtime_entry=_validated_runtime_entry(
                code="A3",
                status="inherited",
                context_kind="whole_workbook",
            ),
        )

        assert response["requested_sheet_code"] is None
        assert response["resolved_wp_code"] == "A3"
        assert response["inherited_from_parent"] is True
        assert response["resolution_status"] == "parent_inherited"
        assert response["resolution_reason"] == "whole_workbook_parent_context"
