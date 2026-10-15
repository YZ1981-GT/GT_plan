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
from app.services.note_section_catalog import DATA_DIR, WORD_TEMPLATE_DIR, filter_template_sections
from app.services.note_section_kind import chapter_title_for_code, classify_note_section, is_account_chapter_title
from app.services.note_text_batch_service import build_preview, fold_unmatched_descendants, match_sections

VARIANTS = [("soe", "standalone"), ("soe", "consolidated"), ("listed", "standalone"), ("listed", "consolidated")]
#: 叙述目标被命中数下限（实测 53/55、72/74、82/86、95/99）
MIN_HIT = {("soe", "standalone"): 53, ("soe", "consolidated"): 72,
           ("listed", "standalone"): 82, ("listed", "consolidated"): 95}
#: 解析耗时上限（实测 2.0~3.6s；NFR-6 目标 50 页 ≤5s，这四份均远超 50 页，留余量防机器抖动）
MAX_PARSE_SECONDS = 15.0


@lru_cache(maxsize=4)
def _parsed(tt: str, rs: str):
    started = time.perf_counter()
    result = parse_docx((WORD_TEMPLATE_DIR / f"{tt}_{rs}.docx").read_bytes())
    return result, time.perf_counter() - started


def _narrative_targets(tt: str, rs: str) -> list[dict]:
    secs = json.loads((DATA_DIR / f"note_template_{tt}.json").read_text(encoding="utf-8"))["sections"]
    out = []
    for s in filter_template_sections(secs, rs):
        if s.get("level") != 2:
            continue
        if classify_note_section(s["section_number"], tt, rs, section_title=s["section_title"]) != "narrative":
            continue
        out.append({"id": uuid.uuid4(), "note_section": s["section_number"], "section_title": s["section_title"],
                    "chapter_title": chapter_title_for_code(s["section_number"], tt),
                    "section_kind": "narrative", "text_content": "", "content_hash": ""})
    return out


def _top_chapter(sources) -> dict[str, str]:
    out, stack = {}, []
    for s in sources:
        while stack and stack[-1].level >= s.level:
            stack.pop()
        out[s.source_id] = stack[0].title if stack else s.title
        stack.append(s)
    return out


@pytest.mark.parametrize("tt,rs", VARIANTS)
def test_word_template_round_trip(tt: str, rs: str):
    parsed, elapsed = _parsed(tt, rs)
    assert elapsed < MAX_PARSE_SECONDS, f"{tt}_{rs} 解析 {elapsed:.1f}s 超限"
    sources = parsed.sections
    targets = _narrative_targets(tt, rs)
    folded, matches = fold_unmatched_descendants(sources, match_sections(sources, targets))

    chapter = _top_chapter(sources)
    title_of = {s.source_id: s.title for s in sources}
    misplaced = [f"{title_of[m.source_id]}（{chapter[m.source_id]}）" for m in matches
                 if m.target_note_id and is_account_chapter_title(chapter[m.source_id])]
    assert not misplaced, f"报表科目注释章节误入叙述目标：{misplaced[:10]}"

    assert all(m.confidence != "confirmed" for m in matches), "外部来源不得自动定案（AC-3.3）"
    hit = {m.target_note_id for m in matches if m.target_note_id}
    assert len(hit) >= MIN_HIT[(tt, rs)], f"{tt}_{rs} 命中 {len(hit)}/{len(targets)}，低于棘轮 {MIN_HIT[(tt, rs)]}"

    preview = build_preview(folded, targets, matches)
    assert preview["summary"]["recommended"] == 0, "候选不得进入推荐（默认勾选）组"
    filled = [i for i in preview["items"] if i["target_note_id"]]
    with_body = [i for i in filled if i["proposed_html"]]
    assert len(with_body) >= MIN_HIT[(tt, rs)] - 2
    # Word 中部分章标题下没有直属正文（内容全在子节）：命中但空正文 ⇒ 必须判不可用并说明原因
    for item in filled:
        if not item["proposed_html"]:
            assert (item["category"], item["unavailable_reason"]) == ("unavailable", "来源正文为空")
    assert preview["summary"]["folded"] > 0 and preview["summary"]["out_of_scope"] > 0


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

    2026-10-14 实测：章节 315~412（硬上限 500）；单章最大 27,168 B（512 KiB）；整份正文 33~58 万字节（5 MiB）；
    文件 50~88 万字节、解压 680~1170 万字节、zip 条目 24~27。§11.2「解析返回章节数」业务阈值 300 是按项目章节数
    （max 200）定的，Word 标题粒度更细，四份都超过它——业务阈值代码不强制，硬上限余量最小的是国企合并 412/500。
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
