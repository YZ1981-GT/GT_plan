"""附注章节类型判定：narrative / account_explanation / container。

spec: disclosure-note-doc-upload-and-batch-fill Task 9（第二轮复盘 R-16 修订）

🔴 权威 = 四版本 Word 附注模板（``data/audit_report_templates/disclosure_notes/{soe,listed}_{standalone,consolidated}.docx``）。
2026-10-14 逐节比对后裁定（见 tasks.md「Word 权威比对」）：

- ``disclosure_notes.account_name`` 不可用：真库 1009 行全部非空（含「公司基本情况」「会计期间」）；
- JSON 种子章归属不可用：上市「三、所得税费用」等 8 节被放进会计政策章，Word 在项目附注章；
- variant matrix 不可用：把会计政策章「借款费用」「债务重组」、其他重要事项章「终止经营」登记为科目，
  且「现金流量表项目注释」登记成截断码 ``三、现金流量表项目注``。

判定顺序：
1. 章号（经 ``normalize_section_code``）属「项目注释 / 项目附注」章 ⇒ account_explanation；
2. 标题在 Word 索引中**只属一类**（纠正 JSON 放错章的节）：只属科目注释章 ⇒ account_explanation；
   只属叙述章 ⇒ 不再套第 3 条；同名跨类（如「存货」）不据此判定；
3. 国企历史编号 ``五、<数字>`` ⇒ account_explanation；
4. ``has_children and not has_body`` ⇒ container —— 叙述类标题**同样适用**（design §4.1「仅承载子节的顶层
   “重要会计政策” → container」；第 17 组真实写入验收：「二 财务报表编制基础」空章行曾因标题属叙述章判成 narrative，
   与同名子节「二、1」成了两个目标）；命中第 1~3 条的科目注释节永不为 container（先返回）；
5. 其余 ⇒ narrative。

「正文载荷」= 可见文字（``has_visible_text``）或表格（:func:`has_table_payload`）。

Word 索引由 ``scripts/gen/gen_note_section_kind_index.py`` 生成到 :data:`KIND_INDEX_PATH`
（请求期不解析 docx）；守卫 ``test_note_section_kind`` 校验其与 Word 同步。
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from functools import lru_cache
from typing import Any, Literal

from app.services.note_section_catalog import (
    DATA_DIR,
    WORD_TEMPLATE_DIR,
    VARIANT_KEYS,
    build_variant_key,
    normalize_section_code,
    normalize_template_type,
    template_json_path,
)

logger = logging.getLogger(__name__)

SectionKind = Literal["narrative", "account_explanation", "container"]

__all__ = [
    "KIND_INDEX_PATH",
    "SectionKind",
    "WORD_TITLE_ALIASES",
    "build_kind_index_from_word",
    "canonical_title",
    "chapter_title_for_code",
    "classify_note_section",
    "has_table_payload",
    "is_account_chapter_title",
    "normalize_title",
]

KIND_INDEX_PATH = DATA_DIR / "note_section_kind_index.json"

#: Word 中「节」的标题层级：国企节 = H2∪H3（H3 142/153 与种子二级节吻合），上市节 = H2（H3 为节内小标题）
SECTION_HEADING_LEVELS: dict[str, frozenset[int]] = {
    "soe": frozenset({2, 3}),
    "listed": frozenset({2}),
}

_ACCOUNT_CHAPTER = re.compile(r"项目注释|项目附注")
_SOE_LEGACY_ACCOUNT = re.compile(r"^五、\d+$")
_WS = re.compile(r"\s+")
_ANNOTATION = re.compile(r"【[^】]*】")
_ENUM_HEAD = re.compile(
    r"^(?:[（(][一二三四五六七八九十\d]+[）)]|[一二三四五六七八九十]+[、.．]|\d+[、.．])"
)
_PAREN_TAIL = re.compile(r"[（(][^（）()]*[）)]$")


def normalize_title(title: str | None) -> str:
    """比对用标题：去【…】批注、空白、前导序号、尾部（…）批注与末尾冒号。"""
    text = _ENUM_HEAD.sub("", _WS.sub("", _ANNOTATION.sub("", title or "")))
    previous = None
    while previous != text:
        previous, text = text, _PAREN_TAIL.sub("", text)
    return text.rstrip("：:")


# ── Word → 索引（仅生成脚本 / 守卫调用；docx 延迟导入，运行期分类不依赖它）──────────


def _heading_level(style_name: str) -> int | None:
    for prefix in ("Heading ", "标题 "):
        if style_name.startswith(prefix):
            tail = style_name[len(prefix):].strip()
            if tail.isdigit():
                return int(tail)
    return None


def _word_titles_by_kind(variant_key: str) -> dict[str, set[str]]:
    import docx
    from docx.text.paragraph import Paragraph

    levels = SECTION_HEADING_LEVELS[variant_key.split("_", 1)[0]]
    document = docx.Document(str(WORD_TEMPLATE_DIR / f"{variant_key}.docx"))
    out: dict[str, set[str]] = {"account_explanation": set(), "narrative": set()}
    chapter_kind: str | None = None
    for element in document.element.body.iterchildren():
        if element.tag.rsplit("}", 1)[-1] != "p":
            continue
        paragraph = Paragraph(element, document)
        text = (paragraph.text or "").strip()
        level = _heading_level(paragraph.style.name if paragraph.style is not None else "")
        if not text or level is None:
            continue
        if level == 1:
            chapter_kind = "account_explanation" if _ACCOUNT_CHAPTER.search(text) else "narrative"
            out[chapter_kind].add(normalize_title(text))  # 「X、1 章名」章正文叶子按章名命中
        elif chapter_kind and level in levels:
            out[chapter_kind].add(normalize_title(text))
    return out


def build_kind_index_from_word() -> dict[str, Any]:
    """从四版本 Word 生成索引；输出确定（无时间戳，列表排序），docx 摘要入 ``_source``。"""
    variants: dict[str, dict[str, list[str]]] = {}
    digests: dict[str, str] = {}
    for vk in VARIANT_KEYS:
        path = WORD_TEMPLATE_DIR / f"{vk}.docx"
        digests[vk] = hashlib.sha256(path.read_bytes()).hexdigest()
        by_kind = _word_titles_by_kind(vk)
        variants[vk] = {kind: sorted(t for t in titles if t) for kind, titles in sorted(by_kind.items())}
    return {
        "_source": {
            "generator": "backend/scripts/gen/gen_note_section_kind_index.py",
            "authority": "data/audit_report_templates/disclosure_notes/{variant}.docx",
            "rule": "一级章标题含「项目注释/项目附注」⇒ account_explanation，其余章 ⇒ narrative；"
                    "国企节=Heading 2∪3，上市节=Heading 2",
            "docx_sha256": digests,
        },
        "variants": variants,
    }


# ── 运行期分类 ────────────────────────────────────────────────────────────────


@lru_cache(maxsize=1)
def _kind_index() -> dict[str, tuple[frozenset[str], frozenset[str]]]:
    try:
        raw = json.loads(KIND_INDEX_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as err:
        logger.warning("章节类型索引不可用（%s）：%s；仅按章号判定", KIND_INDEX_PATH, err)
        return {}
    return {
        vk: (frozenset(v.get("account_explanation", [])), frozenset(v.get("narrative", [])))
        for vk, v in (raw.get("variants") or {}).items()
    }


@lru_cache(maxsize=2)
def _account_chapter_prefixes(template_type: str) -> frozenset[str]:
    data = json.loads(template_json_path(template_type).read_text(encoding="utf-8"))
    return frozenset(
        f"{s['section_number'].strip()}、"
        for s in data.get("sections", [])
        if s.get("level") == 1 and _ACCOUNT_CHAPTER.search(s.get("section_title") or "")
    )


def _title_kind(title: str | None, template_type: str, report_scope: str | None) -> SectionKind | None:
    key = normalize_title(title)
    if not key:
        return None
    index = _kind_index()
    variants = [build_variant_key(template_type, report_scope)] if report_scope else [
        f"{template_type}_standalone", f"{template_type}_consolidated",
    ]
    in_account = any(key in index.get(vk, (frozenset(), frozenset()))[0] for vk in variants)
    in_narrative = any(key in index.get(vk, (frozenset(), frozenset()))[1] for vk in variants)
    if in_account != in_narrative:
        return "account_explanation" if in_account else "narrative"
    return None  # 不在 Word 中或同名跨类：不据标题判定


def classify_note_section(
    note_section: str | None,
    template_type: str | None,
    report_scope: str | None = None,
    *,
    section_title: str | None = None,
    has_children: bool = False,
    has_body: bool = True,
) -> SectionKind:
    """判定章节类型（顺序见模块说明）。"""
    tt = normalize_template_type(template_type)
    code = (note_section or "").strip()
    canonical = normalize_section_code(code, template_type=tt)
    if any(canonical.startswith(p) for p in _account_chapter_prefixes(tt)):
        return "account_explanation"
    by_title = _title_kind(section_title, tt, report_scope)
    if by_title == "account_explanation":
        return by_title
    if by_title is None and tt == "soe" and _SOE_LEGACY_ACCOUNT.match(code):
        return "account_explanation"
    if has_children and not has_body:
        return "container"
    return "narrative"


def has_table_payload(table_data: Any) -> bool:
    """``table_data`` 是否承载表格：非空 JSON 对象（与 Word 导出「非 dict 或空 dict 不出表」同口径）。

    🔴 不能用「非 None / IS NOT NULL」：``table_data`` 是未设 ``none_as_null`` 的 JSONB，ORM 写 ``None`` 存成
    JSON ``null``（不是 SQL NULL）。真库纯文字章节 475 行全是 JSON null、0 行 SQL NULL（2026-10-15）。
    SQL 侧同口径表达式见 ``note_text_batch_service._table_payload_expr``，两者由守卫逐值对拍。
    """
    return isinstance(table_data, dict) and bool(table_data)


# ── 匹配辅助：章归属与 Word↔系统标题别名 ───────────────────────────────────────

#: Word 模板标题 → 系统（JSON 种子）标题。证据：2026-10-14 四版本 Word 比对（tasks.md「Word 权威比对」）。
#: 用户上传的附注文档源自 Word 模板，章名与系统不同；仅用于产生 candidate，不自动定案。
_WORD_TITLE_ALIASES_RAW: dict[str, str] = {
    "公司（企业）基本情况": "公司基本情况",
    "会计政策、会计估计变更及差错更正": "重要会计政策、会计估计的变更以及前期差错的更正",
    "企业合并及合并财务报表": "合并范围的变化",
    "关联方关系及其交易": "关联方及关联交易",
}
WORD_TITLE_ALIASES: dict[str, str] = {
    normalize_title(k): normalize_title(v) for k, v in _WORD_TITLE_ALIASES_RAW.items()
}


def canonical_title(title: str | None) -> str:
    """匹配用标题键：``normalize_title`` 后再折叠 Word↔系统别名。"""
    key = normalize_title(title)
    return WORD_TITLE_ALIASES.get(key, key)


def is_account_chapter_title(title: str | None) -> bool:
    """一级章标题是否为报表科目注释章（「项目注释 / 项目附注」，Word 口径）。"""
    return bool(_ACCOUNT_CHAPTER.search(title or ""))


@lru_cache(maxsize=2)
def _chapter_titles(template_type: str) -> dict[str, str]:
    data = json.loads(template_json_path(template_type).read_text(encoding="utf-8"))
    return {
        s["section_number"].strip(): s.get("section_title") or ""
        for s in data.get("sections", [])
        if s.get("level") == 1 and s.get("section_number")
    }


def chapter_title_for_code(note_section: str | None, template_type: str | None) -> str | None:
    """章节号所属一级章标题（取自模板 JSON；国企 ``五、N`` 先归一为 ``八、N``）。"""
    tt = normalize_template_type(template_type)
    canonical = normalize_section_code((note_section or "").strip(), template_type=tt)
    head = canonical.split("、", 1)[0] if "、" in canonical else canonical
    return _chapter_titles(tt).get(head)
