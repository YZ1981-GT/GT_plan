"""附注纯文字正文按 markdown 渲染：前后端同一口径（spec disclosure-note-doc-upload-and-batch-fill 第 22 组）。

判据真源是共享夹具 ``backend/data/note_text_markdown_cases.json``：前端
``src/utils/__tests__/noteTextMarkdown.spec.ts`` 逐条跑同一份文件，两端结论必须完全一致。
编辑器加载（前端）与 Word 导出 / 批量写入（后端）若口径不同，未保存过的纯文字章节在编辑器与 Word 里分段、
编号不一样（第 22 组首版前端用 marked、后端用 markdown-it：书写的「1. 」接在文字后，前端拆成两段、后端同段换行）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.note_html_sanitizer import (
    is_html_note_text,
    note_text_to_html,
    render_note_markdown,
    sanitize_note_html,
)

_CASES_PATH = Path(__file__).resolve().parents[1] / "data" / "note_text_markdown_cases.json"
_FIXTURE = json.loads(_CASES_PATH.read_text(encoding="utf-8"))
_DETECT = _FIXTURE["detect_cases"]
_RENDER = _FIXTURE["render_cases"]


def test_fixture_is_not_vacuous() -> None:
    """两类判定都要有、渲染要覆盖表格 / 段内换行 / 分段，否则「两端一致」可能是一起恒返回同一值。"""
    assert {c["is_html"] for c in _DETECT} == {True, False}
    expected = [c["expected"] for c in _RENDER]
    assert len(set(expected)) == len(expected)
    assert any("<table>" in e for e in expected)
    assert any("<br />" in e for e in expected)
    assert any(e.count("<p>") >= 2 for e in expected)


@pytest.mark.parametrize("case", _DETECT, ids=[c["note"] for c in _DETECT])
def test_html_detection_matches_shared_fixture(case: dict) -> None:
    assert is_html_note_text(case["text"]) is case["is_html"]


@pytest.mark.parametrize("case", _RENDER, ids=[c["note"] for c in _RENDER])
def test_render_matches_shared_fixture(case: dict) -> None:
    assert render_note_markdown(case["text"]) == case["expected"]


@pytest.mark.parametrize("case", _RENDER, ids=[c["note"] for c in _RENDER])
def test_note_text_to_html_is_the_sanitized_render(case: dict) -> None:
    """Word 导出 / 批量写入走的 note_text_to_html 必须就是「对拍过的渲染 + 消毒」，不能另起一套。"""
    assert note_text_to_html(case["text"]) == sanitize_note_html(case["expected"])


def test_written_numbering_and_indent_never_become_markup() -> None:
    """书写的编号、项目符号、缩进是正文：任何用例都不得渲染出列表或代码块。"""
    for case in _RENDER:
        for tag in ("<ol", "<ul", "<li", "<pre", "<code"):
            assert tag not in case["expected"], (case["note"], tag)
