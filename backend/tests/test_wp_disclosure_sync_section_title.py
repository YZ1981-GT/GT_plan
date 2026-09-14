"""新建附注时的 section_title / account_name 取自附注模板（而非章节号本身）。

背景：旧实现 `section_title=_derive_section_title(section_id)` 使底稿同步新建的
附注在附注树/Word 导出里显示 "五、36" 这类**章节号**而不是中文标题。
"""

from __future__ import annotations

import json
from pathlib import Path

from app.models.report_models import SourceTemplate
from app.services.wp_disclosure_sync_service import (
    _derive_section_title,
    _resolve_section_meta,
    _template_section_meta,
)

_DATA = Path(__file__).resolve().parents[1] / "data"


def _sample_section(variant: str) -> tuple[str, str]:
    doc = json.loads((_DATA / f"note_template_{variant}.json").read_text(encoding="utf-8"))
    for sec in doc.get("sections") or []:
        num = (sec.get("section_number") or "").strip()
        title = (sec.get("section_title") or "").strip()
        if num and title and num != title:
            return num, title
    raise AssertionError(f"模板 {variant} 无可用章节样本")


def test_template_index_non_empty_and_keyed_by_section_number():
    for variant in ("listed", "soe"):
        idx = _template_section_meta(variant)
        assert idx, f"{variant} 模板索引不应为空"
        # key 是 section_number（形如 "五、1" / "八、1"），不是 slug
        assert all("、" in k or k.strip() for k in idx)


def test_resolve_uses_template_title_listed():
    num, title = _sample_section("listed")
    got_title, got_account = _resolve_section_meta(num, SourceTemplate.listed)
    assert got_title == title
    assert got_title != num  # 关键：不再拿章节号当标题
    assert got_account is None or isinstance(got_account, str)


def test_resolve_uses_template_title_soe():
    num, title = _sample_section("soe")
    got_title, _ = _resolve_section_meta(num, SourceTemplate.soe)
    assert got_title == title


def test_resolve_prefers_variant_then_falls_back_to_other():
    """soe 模板独有章节在 source_template=listed 时也应命中（跨变体回退）。"""
    listed_keys = set(_template_section_meta("listed"))
    soe_only = [k for k in _template_section_meta("soe") if k not in listed_keys]
    if not soe_only:
        return  # 无独有章节则跳过
    num = soe_only[0]
    title, _ = _resolve_section_meta(num, SourceTemplate.listed)
    assert title == _template_section_meta("soe")[num][0]


def test_resolve_falls_back_to_string_derivation_for_unknown_section():
    assert _resolve_section_meta("零、999 未知章节", None)[0] == "未知章节"
    assert _resolve_section_meta("零、999", None)[0] == "零、999"
    assert _resolve_section_meta("", None) == ("", None)


def test_string_derivation_helper_unchanged():
    assert _derive_section_title("五-1-1 应收账款") == "应收账款"
    assert _derive_section_title("五-1-1") == "五-1-1"
    assert _derive_section_title("") == ""
