"""CI-18 / CI-19 卡点测试 — D13 章节序号重构验收.

CI-18: section_id 全局唯一 + level 1-5 范围 + parent_section_id 引用有效
CI-19: rendered_number 在 scope 内唯一

这些测试对模板 JSON 数据做静态校验（不依赖 DB）。
"""

import json
from pathlib import Path

import pytest

from app.services.note_section_numbering_service import NoteSectionNumberingService

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
SOE_PATH = DATA_DIR / "note_template_soe.json"
LISTED_PATH = DATA_DIR / "note_template_listed.json"


def _load_sections(path: Path) -> list[dict]:
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    return raw.get("sections", [])


# ---------------------------------------------------------------------------
# CI-18: section_id 唯一 + level 1-5 + parent 引用有效
# ---------------------------------------------------------------------------


class TestCI18:
    """CI-18 卡点：section_id / level / parent_section_id 完整性."""

    @pytest.fixture(params=["soe", "listed"])
    def sections(self, request):
        path = SOE_PATH if request.param == "soe" else LISTED_PATH
        if not path.exists():
            pytest.skip(f"{path.name} not found")
        return _load_sections(path)

    def test_section_id_present(self, sections):
        """每个 section 必须有 section_id."""
        for s in sections:
            assert s.get("section_id"), f"Missing section_id: {s.get('section_title')}"

    def test_section_id_unique(self, sections):
        """section_id 在文件内唯一."""
        ids = [s["section_id"] for s in sections]
        assert len(ids) == len(set(ids)), f"Duplicate section_ids found"

    def test_section_id_length(self, sections):
        """section_id 不超过 100 字符（VARCHAR(100) 约束）."""
        for s in sections:
            sid = s["section_id"]
            assert len(sid) <= 100, f"section_id too long ({len(sid)}): {sid[:50]}..."

    def test_level_range(self, sections):
        """level 必须在 1-5 范围内."""
        for s in sections:
            level = s.get("level")
            assert level is not None, f"Missing level: {s['section_id']}"
            assert 1 <= level <= 5, f"Invalid level={level}: {s['section_id']}"

    def test_parent_section_id_valid(self, sections):
        """parent_section_id 如果非 None，必须指向同文件内存在的 section_id."""
        all_ids = {s["section_id"] for s in sections}
        for s in sections:
            parent = s.get("parent_section_id")
            if parent is not None:
                assert parent in all_ids, (
                    f"Invalid parent_section_id={parent} for {s['section_id']}"
                )

    def test_no_self_reference(self, sections):
        """section 不能 parent 指向自己."""
        for s in sections:
            if s.get("parent_section_id"):
                assert s["parent_section_id"] != s["section_id"]


# ---------------------------------------------------------------------------
# CI-19: rendered_number 在 scope 内唯一
# ---------------------------------------------------------------------------


class TestCI19:
    """CI-19 卡点：rendered_number 在 scope 内唯一."""

    @pytest.fixture(params=["soe", "listed"])
    def sections(self, request):
        path = SOE_PATH if request.param == "soe" else LISTED_PATH
        if not path.exists():
            pytest.skip(f"{path.name} not found")
        return _load_sections(path)

    def test_rendered_numbers_unique_scope_both(self, sections):
        """scope='both' 下 rendered_number 唯一（排除空字符串）."""
        svc = NoteSectionNumberingService()
        result = svc.render_sections(sections, scope="both")
        non_empty = [v for v in result.values() if v]
        assert len(non_empty) == len(set(non_empty)), (
            f"Duplicate rendered_numbers in scope=both"
        )

    def test_rendered_numbers_unique_scope_standalone(self, sections):
        """scope='standalone' 下 rendered_number 唯一."""
        svc = NoteSectionNumberingService()
        result = svc.render_sections(sections, scope="standalone")
        non_empty = [v for v in result.values() if v]
        assert len(non_empty) == len(set(non_empty))

    def test_rendered_numbers_unique_scope_consolidated(self, sections):
        """scope='consolidated' 下 rendered_number 唯一."""
        svc = NoteSectionNumberingService()
        result = svc.render_sections(sections, scope="consolidated")
        non_empty = [v for v in result.values() if v]
        assert len(non_empty) == len(set(non_empty))
