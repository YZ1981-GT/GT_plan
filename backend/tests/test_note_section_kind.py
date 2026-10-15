"""章节类型判定：设计基线 + 四版本 Word 模板权威守卫（第二轮复盘 R-16）。

本文件**独立**解析 Word（不复用生产模块的解析函数），与生产分类器两套实现互相校验。
Word 口径：国企「节」= Heading 2∪3，上市「节」= Heading 2；章标题含「项目注释/项目附注」⇒ 科目注释章。
"""

from __future__ import annotations

import collections
import json
import re
from functools import lru_cache

import docx
import pytest
from docx.text.paragraph import Paragraph

from app.services.note_section_catalog import DATA_DIR, filter_template_sections
from app.services.note_section_kind import (
    KIND_INDEX_PATH,
    build_kind_index_from_word,
    classify_note_section,
)

DOCX_DIR = DATA_DIR / "audit_report_templates" / "disclosure_notes"
VARIANTS = [("soe", "standalone"), ("soe", "consolidated"), ("listed", "standalone"), ("listed", "consolidated")]
SECTION_LEVELS = {"soe": {2, 3}, "listed": {2}}
_ACCOUNT_CHAPTER = re.compile(r"项目注释|项目附注")
_WS = re.compile(r"\s+")
_ENUM_HEAD = re.compile(r"^(?:[（(][一二三四五六七八九十\d]+[）)]|[一二三四五六七八九十]+[、.．]|\d+[、.．])")
_TAIL = re.compile(r"[（(][^（）()]*[）)]$")
_ANNOT = re.compile(r"【[^】]*】")


def norm(title: str) -> str:
    t = _ENUM_HEAD.sub("", _WS.sub("", _ANNOT.sub("", title or "")))
    prev = None
    while prev != t:
        prev, t = t, _TAIL.sub("", t)
    return t.rstrip("：:")


def _heading_level(style_name: str) -> int | None:
    for prefix in ("Heading ", "标题 "):
        tail = style_name[len(prefix):].strip() if style_name.startswith(prefix) else ""
        if tail.isdigit():
            return int(tail)
    return None


@lru_cache(maxsize=4)
def word_kinds(tt: str, rs: str) -> dict[str, frozenset[str]]:
    """标题 → 其在 Word 中所属章类型集合（节与章名都登记）。"""
    document = docx.Document(str(DOCX_DIR / f"{tt}_{rs}.docx"))
    kinds: dict[str, set[str]] = collections.defaultdict(set)
    current = None
    for el in document.element.body.iterchildren():
        if el.tag.rsplit("}", 1)[-1] != "p":
            continue
        para = Paragraph(el, document)
        text = (para.text or "").strip()
        level = _heading_level(para.style.name if para.style is not None else "")
        if not text or level is None:
            continue
        if level == 1:
            current = "account_explanation" if _ACCOUNT_CHAPTER.search(text) else "narrative"
            kinds[norm(text)].add(current)
        elif current and level in SECTION_LEVELS[tt]:
            kinds[norm(text)].add(current)
    return {k: frozenset(v) for k, v in kinds.items()}


def _json_sections(tt: str, rs: str) -> list[dict]:
    raw = json.loads((DATA_DIR / f"note_template_{tt}.json").read_text(encoding="utf-8"))["sections"]
    return [s for s in filter_template_sections(raw, rs) if s.get("level") == 2]


class TestDesignBaseline:
    """design §4.1 基线 + Word 比对坐实的 JSON/matrix 偏差样本。"""

    @pytest.mark.parametrize("code,title,tt,expected", [
        ("一、1", "公司基本情况", "soe", "narrative"),
        ("四、会计期间", "会计期间", "soe", "narrative"),
        ("八、1", "货币资金", "soe", "account_explanation"),
        ("五、1", "货币资金", "soe", "account_explanation"),       # 国企历史编号 五、N
        ("五、1", "货币资金", "listed", "account_explanation"),
        ("十二、长期股权投资", "长期股权投资", "soe", "account_explanation"),  # 国企母公司章
        ("四、存货", "存货", "soe", "narrative"),                  # 同名跨类：按章号判
        # JSON 把以下节放进上市会计政策章，Word 在项目附注章
        ("三、所得税费用", "所得税费用", "listed", "account_explanation"),
        ("三、现金流量表项目注释", "现金流量表项目注释", "listed", "account_explanation"),
        # matrix 把以下节登记为科目，Word 在会计政策 / 其他重要事项章
        ("三、借款费用", "借款费用", "listed", "narrative"),
        ("三、债务重组【不适用", "债务重组", "listed", "narrative"),
        ("十四、终止经营", "终止经营", "listed", "narrative"),
    ])
    def test_baseline(self, code: str, title: str, tt: str, expected: str):
        assert classify_note_section(code, tt, section_title=title) == expected

    def test_pure_parent_without_body_is_container(self):
        assert classify_note_section("四、自定义父节", "soe", has_children=True, has_body=False) == "container"
        assert classify_note_section("四、自定义父节", "soe", has_children=True, has_body=True) == "narrative"

    def test_account_section_never_becomes_container(self):
        assert classify_note_section("八、1", "soe", has_children=True, has_body=False) == "account_explanation"
        assert classify_note_section("三、所得税费用", "listed", section_title="所得税费用",
                                     has_children=True, has_body=False) == "account_explanation"

    @pytest.mark.parametrize("tt,rs,code,title", [
        ("soe", "standalone", "二", "财务报表编制基础"),
        ("soe", "consolidated", "四", "重要会计政策、会计估计"),
        ("listed", "standalone", "三", "重要会计政策及会计估计"),
    ])
    def test_narrative_titled_pure_parent_is_container(self, tt: str, rs: str, code: str, title: str):
        """design §4.1「仅承载子节的顶层“重要会计政策” → container」：标题在 Word 里属叙述章不豁免容器规则。

        新生成附注的「二 财务报表编制基础」是空章行 + 同名子节「二、1」；首版按 Word 标题先返回 narrative，
        章行进了上传可填范围 ⇒ 同名两个目标、只能人工选（第 17 组真实写入验收发现）。"""
        from app.services.note_section_kind import _title_kind

        assert _title_kind(title, tt, rs) == "narrative", "样本须是 Word 判为叙述章的标题，否则测不到该分支"
        assert classify_note_section(code, tt, rs, section_title=title,
                                     has_children=True, has_body=False) == "container"
        assert classify_note_section(code, tt, rs, section_title=title,
                                     has_children=True, has_body=True) == "narrative"
        assert classify_note_section(code, tt, rs, section_title=title) == "narrative"

    def test_narrative_title_still_skips_soe_legacy_rule(self):
        """顺序不变：Word 判为叙述章的标题不再套「国企历史编号 五、N」；标题不在 Word 时才套。"""
        from app.services.note_section_kind import _title_kind

        assert _title_kind("财务报表编制基础", "soe", "standalone") == "narrative"
        assert classify_note_section("五、99", "soe", "standalone", section_title="财务报表编制基础") == "narrative"
        assert classify_note_section("五、99", "soe", "standalone", section_title="自定义科目") == "account_explanation"


class TestTablePayload:
    """「承载表格」= 非空 JSON 对象（与 Word 导出同口径）；JSON null / 空对象 / 数组都不算。"""

    @pytest.mark.parametrize("value,expected", [
        (None, False), ({}, False), ([], False), ([{"label": "x"}], False), ("text", False), (0, False),
        ({"rows": []}, True), ({"rows": [{"label": "合计"}]}, True), ({"_tables": [{}]}, True),
    ])
    def test_has_table_payload(self, value, expected: bool):
        from app.services.note_section_kind import has_table_payload

        assert has_table_payload(value) is expected


#: 防空转下限 ≈ 实测核对数的 90%（实测 114 / 140 / 146 / 163，2026-10-14）
_MIN_CHECKED = {
    ("soe", "standalone"): 100,
    ("soe", "consolidated"): 125,
    ("listed", "standalone"): 130,
    ("listed", "consolidated"): 145,
}


class TestWordAuthority:
    @pytest.mark.parametrize("tt,rs", VARIANTS)
    def test_unambiguous_sections_match_word(self, tt: str, rs: str):
        """Word 中归属唯一的节：分类必须与其所在章类型一致（同名跨类 / Word 缺失只跳过不断言）。"""
        kinds = word_kinds(tt, rs)
        checked, wrong = 0, []
        for s in _json_sections(tt, rs):
            expected = kinds.get(norm(s["section_title"]), frozenset())
            if len(expected) != 1:
                continue
            got = classify_note_section(s["section_number"], tt, rs, section_title=s["section_title"])
            checked += 1
            if got != next(iter(expected)):
                wrong.append(f"{s['section_number']}|{s['section_title'][:16]} 判={got} Word={next(iter(expected))}")
        assert not wrong, f"{tt}_{rs} 与 Word 不一致 {len(wrong)} 处（checked={checked}）: {wrong[:20]}"
        assert checked >= _MIN_CHECKED[(tt, rs)], f"{tt}_{rs} 仅核对 {checked} 节，守卫疑似空转"

    def test_committed_index_in_sync_with_word(self):
        """Word 模板更新而索引未重生成 ⇒ 打红（重跑 scripts/gen/gen_note_section_kind_index.py）。"""
        committed = json.loads(KIND_INDEX_PATH.read_text(encoding="utf-8"))
        assert committed == build_kind_index_from_word()
