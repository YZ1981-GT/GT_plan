"""R-27：四版本 Word 附注模板端到端守卫 —— 解析 → 分类 → 匹配 → 子标题并入 → 预览。

用户上传的附注文档源自这四份 Word 模板，它们是最贴近真实输入的样本。
覆盖率棘轮按 2026-10-14 实测冻结（只许升不许降；提升后请同步上调）。
"""

from __future__ import annotations

import json
import time
import uuid
from functools import lru_cache

import pytest

from app.services.note_document_parser import parse_docx
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
