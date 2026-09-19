"""F 循环 sheet-level 复核提示词加载集成测试。"""
from __future__ import annotations

from pathlib import Path

from app.services.review_prompt_service import ReviewPromptService

_F_DIR = Path(__file__).resolve().parents[1] / "data" / "tsj_review_prompts" / "F"


def test_f_dir_has_sheet_prompts():
    assert _F_DIR.is_dir(), "tsj_review_prompts/F 应已生成"
    files = list(_F_DIR.glob("F*.md"))
    assert len(files) >= 80


def test_load_f2_1_sheet_level():
    svc = ReviewPromptService()
    result = svc.load_prompt("F2", "审定表F2-1")
    assert result.source_level == "sheet"
    assert result.file_path and result.file_path.endswith("F2-1.md")
    assert "1471" in result.content or "跌价" in result.content
    assert len(result.checklist) >= 5 or "- [ ]" in result.content


def test_load_f2_14_adjustment_not_confused_with_detail():
    svc = ReviewPromptService()
    result = svc.load_prompt("F2", "调整分录F2-14")
    assert result.source_level == "sheet"
    assert "F2-14" in (result.file_path or "")
    assert "1412" in result.content or "1471" in result.content


def test_load_f2_29_cutoff():
    svc = ReviewPromptService()
    result = svc.load_prompt("F2", "截止测试F2-29")
    assert result.source_level == "sheet"
    assert "F2-29" in (result.file_path or "")


def test_f1_subject_alias_prepaid():
    """F1 科目级回退应命中预付账款，而非应付账款。"""
    svc = ReviewPromptService()
    result = svc.load_prompt("F1", None)
    assert result.source_level in ("subject", "sheet", "base")
    if result.source_level == "subject":
        assert "预付" in (result.file_path or "") or "预付" in result.content


def test_f5_subject_alias_cost():
    svc = ReviewPromptService()
    result = svc.load_prompt("F5", None)
    if result.source_level == "subject":
        assert "成本" in (result.file_path or "") or "成本" in result.content


def test_reserved_sheets_have_no_prompt_files():
    reserved = [
        "F2-15", "F2-17", "F2-27", "F2-28",
        "F2-36", "F2-37", "F2-45", "F2-46", "F2-50", "F2-51",
    ]
    for code in reserved:
        assert not (_F_DIR / f"{code}.md").exists(), f"{code} 不应有 sheet prompt"
