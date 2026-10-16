"""生成附注不调用大模型（用户 2026-10-16：「LLM 只支持用户手动单击时调用」）。

spec: disclosure-note-template-word-realignment Task 21 / 24（design §6）

生成正文只走「上年附注 → 模板正文」。生成链不得构造知识库增强层、不得调 ``chat_completion``；原知识库 RAG 开关
``DISCLOSURE_NOTE_RAG_ENABLED`` 只控制生成链里的那一级，随之删除（留着会让人以为打开就能让生成走知识库）。
手动入口（AI 填充 / 续写 / 改写等）不受影响，由各自端点测试守护。
"""

from __future__ import annotations

import ast
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import settings
from tests.test_disclosure_note_generation_text_order import (
    _added_note,
    _make_engine,
    _minimal_template,
    _stub_generate_notes_io,
)

ENGINE_SRC = Path(__file__).resolve().parents[1] / "app" / "services" / "disclosure_engine.py"


@pytest.mark.asyncio
async def test_generate_notes_never_calls_llm_or_knowledge_layer():
    eng = _make_engine()
    _stub_generate_notes_io(eng)
    eng._load_templates = AsyncMock(return_value=[_minimal_template(["本公司存货按成本与可变现净值孰低计量。"])])

    async def _no_prior(_pid, _yr):
        eng._prior_notes_cache = {}

    eng._preload_data_for_notes = _no_prior
    llm = AsyncMock(return_value="大模型写的一段正文，长度超过二十个字符以免被当作无效。")
    enricher_cls = MagicMock()
    # 源模块与引擎模块两处都换：延迟 import 与模块级 import 都逃不过（引擎里重新加回 import 也会被截住）
    with patch("app.services.llm_client.chat_completion", llm), \
            patch("app.services.disclosure_engine.chat_completion", llm, create=True), \
            patch("app.services.note_knowledge_enricher.NoteKnowledgeEnricher", enricher_cls), \
            patch("app.services.disclosure_engine.NoteKnowledgeEnricher", enricher_cls, create=True):
        await eng.generate_notes(uuid.uuid4(), 2025, "soe")

    assert llm.await_count == 0, "生成附注调用了大模型"
    enricher_cls.assert_not_called()
    assert _added_note(eng).text_content == "本公司存货按成本与可变现净值孰低计量。"  # 模板正文


def test_engine_has_no_llm_reference():
    """AST：生成引擎源码里不再引用大模型客户端与知识库增强层（注释 / docstring 不算）。"""
    tree = ast.parse(ENGINE_SRC.read_text(encoding="utf-8"))
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    names |= {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    imported = {a.asname or a.name for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))
                for a in n.names}
    banned = {"chat_completion", "NoteKnowledgeEnricher", "_generate_text_with_llm", "generate_note_text",
              "retrieve_prior_year_note", "DISCLOSURE_NOTE_RAG_ENABLED"}
    assert not ((names | imported) & banned), sorted((names | imported) & banned)


def test_generation_rag_switch_removed():
    """生成链的知识库开关已删：配置里再出现它（且无消费方）就是误导运维的死开关。"""
    assert not hasattr(settings, "DISCLOSURE_NOTE_RAG_ENABLED")
    # 手动 AI 填充仍用的两个参数保留
    assert settings.DISCLOSURE_NOTE_RAG_TOP_K > 0 and settings.DISCLOSURE_NOTE_RAG_CHAR_BUDGET > 0
