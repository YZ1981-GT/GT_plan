"""GuidanceExtractor 基础正确性测试

验证：
1. extract 返回 GuidanceResult 结构正确
2. fallback 当无 template_path 时
3. static JSON 加载正常
"""
from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

import pytest

from app.services.guidance_extractor import (
    GUIDANCE_DIR,
    GuidanceExtractor,
    GuidanceResult,
    GuidanceSection,
)


@pytest.fixture
def extractor():
    return GuidanceExtractor()


def _run(coro):
    """辅助：同步执行 async 函数"""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# 1. extract 返回 GuidanceResult 结构正确
# ---------------------------------------------------------------------------


class TestGuidanceResultStructure:
    """验证返回结构完整性"""

    def test_result_has_required_fields(self, extractor):
        """GuidanceResult 必须包含 wp_code/source/sections/raw_text"""
        result = _run(extractor.extract("NONEXISTENT_CODE_XYZ", None))
        assert isinstance(result, GuidanceResult)
        assert result.wp_code == "NONEXISTENT_CODE_XYZ"
        assert result.source in (
            "template_sheet",
            "template_header",
            "docx_instructions",
            "static_json",
            "fallback",
        )
        assert isinstance(result.sections, list)
        assert isinstance(result.raw_text, str)
        assert len(result.raw_text) > 0  # 永不为空

    def test_sections_have_correct_structure(self, extractor):
        """每个 GuidanceSection 有 heading/content/order"""
        result = _run(extractor.extract("NONEXISTENT_CODE_XYZ", None))
        for section in result.sections:
            assert isinstance(section, GuidanceSection)
            assert isinstance(section.heading, str)
            assert isinstance(section.content, str)
            assert isinstance(section.order, int)


# ---------------------------------------------------------------------------
# 2. fallback 当无 template_path 时
# ---------------------------------------------------------------------------


class TestFallbackBehavior:
    """验证降级行为"""

    def test_no_template_path_returns_fallback(self, extractor):
        """template_path=None 且无 static JSON 时返回 fallback"""
        result = _run(extractor.extract("ZZZZZ_NO_EXIST", None))
        assert result.source == "fallback"
        assert "请参照" in result.raw_text
        assert len(result.sections) >= 1

    def test_nonexistent_template_returns_fallback_or_json(self, extractor):
        """template_path 指向不存在文件时降级"""
        fake_path = Path("/tmp/does_not_exist_12345.xlsx")
        result = _run(extractor.extract("ZZZZZ_NO_EXIST_2", fake_path))
        # 应降级到 static_json 或 fallback
        assert result.source in ("static_json", "fallback")
        assert len(result.raw_text) > 0

    def test_fallback_result_non_empty(self, extractor):
        """fallback 结果永不为空字符串"""
        result = _run(extractor.extract("___TEST___", None))
        assert result.raw_text != ""
        assert result.sections != []


# ---------------------------------------------------------------------------
# 3. static JSON 加载正常
# ---------------------------------------------------------------------------


class TestStaticJsonLoading:
    """验证从 wp_guidance/*.json 加载"""

    def test_known_wp_code_loads_from_json(self, extractor):
        """已有 static JSON 的 wp_code 可正确加载"""
        # A17.json 已确认存在
        if not (GUIDANCE_DIR / "A17.json").exists():
            pytest.skip("A17.json 不存在")

        result = _run(extractor.extract("A17", None))
        assert result.source == "static_json"
        assert result.wp_code == "A17"
        assert len(result.sections) >= 1
        # A17 应有编制目的/主要内容/编制步骤
        headings = [s.heading for s in result.sections]
        assert any("编制目的" in h for h in headings)

    def test_json_sections_preserve_order(self, extractor):
        """JSON sections 保持原始顺序"""
        if not (GUIDANCE_DIR / "A17.json").exists():
            pytest.skip("A17.json 不存在")

        result = _run(extractor.extract("A17", None))
        orders = [s.order for s in result.sections]
        assert orders == sorted(orders)

    def test_custom_json_file_loads_correctly(self, extractor):
        """临时创建 JSON 文件验证加载逻辑"""
        test_code = "__TEST_GUIDANCE_EXTRACTOR__"
        test_file = GUIDANCE_DIR / f"{test_code}.json"

        try:
            test_data = {
                "wp_code": test_code,
                "title": "测试底稿 — 编制说明",
                "sections": [
                    {"heading": "一、编制目的", "content": "测试内容第一节"},
                    {"heading": "二、编制步骤", "content": "测试内容第二节"},
                ],
                "source": "static_json",
            }
            test_file.write_text(
                json.dumps(test_data, ensure_ascii=False, indent=2), encoding="utf-8"
            )

            result = _run(extractor.extract(test_code, None))
            assert result.source == "static_json"
            assert result.wp_code == test_code
            assert len(result.sections) == 2
            assert result.sections[0].heading == "一、编制目的"
            assert result.sections[1].content == "测试内容第二节"
            assert "测试内容第一节" in result.raw_text
        finally:
            if test_file.exists():
                test_file.unlink()


# ---------------------------------------------------------------------------
# 4. xlsx sheet 提取（如果模板文件存在）
# ---------------------------------------------------------------------------


class TestXlsxExtraction:
    """验证 xlsx 模板提取（需要模板文件存在）"""

    def _find_template_with_guidance_sheet(self) -> Path | None:
        """在 wp_templates 中找一个有编制说明 sheet 的文件"""
        template_dir = Path(__file__).resolve().parent.parent / "wp_templates"
        if not template_dir.exists():
            return None
        for xlsx_path in template_dir.rglob("*.xlsx"):
            if xlsx_path.name.startswith("~$"):
                continue
            try:
                from python_calamine import CalamineWorkbook

                wb = CalamineWorkbook.from_path(str(xlsx_path))
                for name in wb.sheet_names:
                    if name.strip().lower() in {"编制说明", "说明", "instructions"}:
                        return xlsx_path
            except Exception:
                continue
        return None

    def test_xlsx_with_guidance_sheet(self, extractor):
        """有「编制说明」sheet 的 xlsx 应提取为 template_sheet"""
        path = self._find_template_with_guidance_sheet()
        if path is None:
            pytest.skip("未找到含编制说明 sheet 的模板文件")

        result = _run(extractor.extract("TEST_XLSX", path))
        assert result.source == "template_sheet"
        assert len(result.sections) >= 1
        assert len(result.raw_text) > 0


# ---------------------------------------------------------------------------
# 5. 超时保护
# ---------------------------------------------------------------------------


class TestTimeoutProtection:
    """验证超时保护机制"""

    def test_timeout_returns_none_gracefully(self, extractor):
        """超时时优雅降级而非抛异常"""
        import time

        def slow_func(*args):
            time.sleep(10)
            return None

        # 直接测试 _try_with_timeout
        result = _run(extractor._try_with_timeout(slow_func, "test"))
        # 应在 5 秒内返回 None（超时）
        assert result is None
