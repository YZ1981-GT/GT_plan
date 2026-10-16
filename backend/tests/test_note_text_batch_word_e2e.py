"""R-27：四版本 Word 附注模板端到端守卫 —— 解析 → 分类 → 匹配 → 子标题并入 → 预览。

用户上传的附注文档源自这四份 Word 模板，它们是最贴近真实输入的样本。
覆盖率棘轮按 2026-10-14 实测冻结（只许升不许降；提升后请同步上调）。
"""

from __future__ import annotations

import json
import time
import uuid
import zipfile
from functools import lru_cache

import pytest

from app.services.note_document_parser import (
    MAX_DOCX_DECOMPRESS_BYTES,
    MAX_DOCX_ZIP_ENTRIES,
    MAX_SECTION_HTML_BYTES,
    MAX_SECTIONS,
    MAX_UPLOAD_BYTES,
    parse_docx,
)
from app.services.note_text_batch_flow import MAX_BATCH_SOURCE_BYTES
from app.services.note_section_catalog import (
    DATA_DIR,
    WORD_TEMPLATE_DIR,
    filter_template_sections,
    section_title_for_scope,
)
from app.services.note_section_kind import chapter_title_for_code, classify_note_section, is_account_chapter_title
from app.services.note_section_tree_locator import build_source_tree
from app.services.note_text_batch_service import SourceContext, build_preview, locate_sources

VARIANTS = [("soe", "standalone"), ("soe", "consolidated"), ("listed", "standalone"), ("listed", "consolidated")]
#: 叙述目标被命中数下限。第 23 组起按章节树逐级定位（不跨章按标题找）：首版 53/72/82/95 里有一部分是跨章碰上的
#: （系统模板 JSON 把节挂在与 Word 不同的章下，碰巧同名），按树后为 51/69/64/67。
#: 2026-10-16 种子按四版 Word 对齐（spec disclosure-note-template-word-realignment）后 61/76/99/99：
#: 国企叙述目标全部命中；上市未命中的 2 个是章正文叶子「七、1 在其他主体中的权益」「十二、1 股份支付」（Word 这两章无章首正文）
MIN_HIT = {("soe", "standalone"): 61, ("soe", "consolidated"): 76,
           ("listed", "standalone"): 99, ("listed", "consolidated"): 99}
#: 命中且有拟写入正文的下限。差额 = Word 里只有标题、没有正文的节（命中但正文为空，须判不可用）：
#: 国企「销售退回」「子公司与母公司会计期间不一致的…」「子公司向母公司转移资金的能力受到严格限制的情况」
#: 「按照有关财务会计制度应披露的其他内容」；上市「关联方承诺」「重要资产转让及出售」「年金计划主要内容及重大变化」
MIN_FILLED = {("soe", "standalone"): 60, ("soe", "consolidated"): 72,
              ("listed", "standalone"): 96, ("listed", "consolidated"): 96}
#: 解析耗时上限（实测 2.0~3.6s；NFR-6 目标 50 页 ≤5s，这四份均远超 50 页，留余量防机器抖动）
MAX_PARSE_SECONDS = 15.0
UPLOAD = SourceContext(kind="upload")
#: 四版 Word 按树定位不上的标题 = Word 与系统模板 JSON 章节树不一致处（第 23 组「树形理顺」实测 17/14/39/37 条）。
#: 种子按 Word 对齐后只剩两类，断言逐字相等 —— 多出来是回归，少了说明已对齐、须同步删掉（不留失效条目）：
#: ①章首正文无同名正文节：章标题与第一个节之间的段落全是填写提示（【披露要求…】【提示…】（注：…）
#:   （具体的报表项目应按以下要求进行注释…）），系统模板不为提示建正文节；上市「重要会计政策及会计估计」
#:   的章首另有一句模板正文「本公司根据自身生产经营特点…」，种子暂无承载位置（见 spec tasks.md Task 6 待办）
#: ②上市合并「公司财务报表主要项目注释」：种子章名「母公司财务报表主要项目注释」由需求 3.2 守卫锁定，待用户拍板
_CHAPTER_HEAD_HINTS_SOE = frozenset({"关联方关系及其交易（章首正文）", "资产负债表日后事项（章首正文）"})
_CHAPTER_HEAD_HINTS_LISTED = frozenset({
    "关联方及关联交易（章首正文）", "资产负债表日后事项（章首正文）", "重要会计政策及会计估计（章首正文）"})
KNOWN_TREE_GAPS: dict[tuple[str, str], frozenset[str]] = {
    ("soe", "standalone"): _CHAPTER_HEAD_HINTS_SOE,
    ("soe", "consolidated"): _CHAPTER_HEAD_HINTS_SOE | {
        "母公司财务报表的主要项目附注（章首正文）", "财务报表主要项目注释（章首正文）"},
    ("listed", "standalone"): _CHAPTER_HEAD_HINTS_LISTED,
    ("listed", "consolidated"): _CHAPTER_HEAD_HINTS_LISTED | {"公司财务报表主要项目注释"},
}
_GAP_KINDS = ("tree_unmatched", "tree_ambiguous", "chapter_body_unmatched")


@lru_cache(maxsize=4)
def _parsed(tt: str, rs: str):
    started = time.perf_counter()
    result = parse_docx((WORD_TEMPLATE_DIR / f"{tt}_{rs}.docx").read_bytes())
    return result, time.perf_counter() - started


def _targets(tt: str, rs: str) -> list[dict]:
    """系统模板 JSON 生成的新项目章节树（按适用口径）：一级章是容器、节是叶子（与生成链 / Task 10 回填同形）。
    标题取该口径下的标题（上市「五」单体叫「财务报表项目附注」，``disclosure_engine`` 生成时同口径）。"""
    secs = filter_template_sections(json.loads((DATA_DIR / f"note_template_{tt}.json").read_text(encoding="utf-8"))["sections"], rs)
    parents = {s.get("parent_section_id") for s in secs if s.get("parent_section_id")}
    return [{"id": uuid.uuid4(), "note_section": s["section_number"], "section_title": section_title_for_scope(s, rs),
             "section_id": s["section_id"], "parent_section_id": s.get("parent_section_id"),
             "chapter_title": chapter_title_for_code(s["section_number"], tt),
             "section_kind": classify_note_section(s["section_number"], tt, rs, section_title=section_title_for_scope(s, rs),
                                                   has_children=s["section_id"] in parents, has_body=False),
             "text_content": "", "content_hash": ""} for s in secs]


@pytest.mark.parametrize("tt,rs", VARIANTS)
def test_word_template_round_trip(tt: str, rs: str):
    parsed, elapsed = _parsed(tt, rs)
    assert elapsed < MAX_PARSE_SECONDS, f"{tt}_{rs} 解析 {elapsed:.1f}s 超限"
    sources = parsed.sections
    targets = _targets(tt, rs)
    located, matches, structural = locate_sources(sources, targets, source_context=UPLOAD)

    top = {n.sid: n for n in build_source_tree(sources)}

    def chapter_of(sid: str) -> str:
        node = top[sid.removesuffix("#body")]
        while node.parent is not None:
            node = node.parent
        return node.section.title

    misplaced = [m.source_id for m in matches if m.target_note_id and is_account_chapter_title(chapter_of(m.source_id))]
    assert not misplaced, f"报表科目注释章节误入叙述目标：{misplaced[:10]}"
    kind_of = {t["id"]: t["section_kind"] for t in targets}
    assert {kind_of[m.target_note_id] for m in matches if m.target_note_id} <= {"narrative"}, "上传只填叙述性章节"

    assert all(m.confidence != "confirmed" for m in matches), "外部来源不得自动定案（AC-3.3）"
    hit = {m.target_note_id for m in matches if m.target_note_id}
    narrative = [t for t in targets if t["section_kind"] == "narrative"]
    assert len(hit) >= MIN_HIT[(tt, rs)], f"{tt}_{rs} 命中 {len(hit)}/{len(narrative)}，低于棘轮 {MIN_HIT[(tt, rs)]}"

    title = {s.source_id: s.title for s in located}
    gaps = {title[m.source_id] for m in matches if m.match_kind in _GAP_KINDS}
    assert gaps == KNOWN_TREE_GAPS[(tt, rs)], (
        f"{tt}_{rs} 新增不一致 {sorted(gaps - KNOWN_TREE_GAPS[(tt, rs)])}；"
        f"已对齐须从清单删除 {sorted(KNOWN_TREE_GAPS[(tt, rs)] - gaps)}")

    preview = build_preview(located, targets, matches, structural_ids=structural)
    assert preview["summary"]["recommended"] == 0, "候选不得进入推荐（默认勾选）组"
    filled = [i for i in preview["items"] if i["target_note_id"]]
    assert len([i for i in filled if i["proposed_html"]]) >= MIN_FILLED[(tt, rs)]
    # Word 中部分节标题下没有直属正文（内容全在下级）：命中但空正文 ⇒ 必须判不可用并说明原因
    for item in filled:
        if not item["proposed_html"]:
            assert (item["category"], item["unavailable_reason"]) == ("unavailable", "来源正文为空")
    # 叶子以下的小标题并入、一级章只作定位锚点
    assert preview["summary"]["folded"] > 0 and preview["summary"]["anchor"] > 0


#: 平台 Word 模板的结构标记（导出引擎用）：浏览器实测发现上传模板文档后被原样带进拟写入正文
_TEMPLATE_MARKERS = ("##SECTION:", "##/SECTION:", "##STYLE_REF:", "{{section:", "{{table:", "{{seq:")


@pytest.mark.parametrize("tt,rs", VARIANTS)
def test_platform_template_markers_never_reach_preview(tt: str, rs: str):
    parsed, _ = _parsed(tt, rs)
    leaked = [(s.title, m) for s in parsed.sections for m in _TEMPLATE_MARKERS if m in s.html]
    assert not leaked, f"{tt}_{rs} 解析结果残留模板标记 {len(leaked)} 处，例：{leaked[:3]}"
    # 剥掉标记后不得留下空段落壳
    assert not [s.title for s in parsed.sections if "<p></p>" in s.html]


@pytest.mark.parametrize("tt,rs", VARIANTS)
def test_word_template_within_frozen_hard_caps(tt: str, rs: str):
    """NFR-5 / Task 56：四份权威模板是最贴近真实上传的样本，必须整份落在 design §11.2 硬上限内（不截断、不 413）。

    2026-10-14 实测：章节 315~412；单章最大 27,168 B（512 KiB）；整份正文 33~58 万字节（5 MiB）；
    文件 50~88 万字节、解压 680~1170 万字节、zip 条目 24~27。章节硬上限原为 500，国企合并 412 只剩 18% 余量，
    2026-10-15 拍板上调到 1000（请求体同步上调见 ``test_note_text_batch_caps.TestSectionCap``）。
    """
    path = WORD_TEMPLATE_DIR / f"{tt}_{rs}.docx"
    parsed, _ = _parsed(tt, rs)
    with zipfile.ZipFile(path) as zf:
        entries, unzip = len(zf.infolist()), sum(e.file_size for e in zf.infolist())
    sizes = [len(s.html.encode("utf-8")) for s in parsed.sections]
    assert [w for w in parsed.warnings if "截断" in w] == []
    assert [s.title for s in parsed.sections if any("截断" in w for w in s.warnings)] == []
    assert len(parsed.sections) < MAX_SECTIONS, "达到上限即被截断：尾部章节丢失（只给一条截断提示）"
    assert max(sizes) < MAX_SECTION_HTML_BYTES and sum(sizes) < MAX_BATCH_SOURCE_BYTES
    assert path.stat().st_size < MAX_UPLOAD_BYTES
    assert entries < MAX_DOCX_ZIP_ENTRIES and unzip < MAX_DOCX_DECOMPRESS_BYTES
