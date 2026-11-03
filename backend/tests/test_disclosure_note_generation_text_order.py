"""生成附注时正文的取用顺序：上年附注 → 模板正文（2026-10-16 起两级，不调大模型 / 知识库）。

沿革：disclosure-note-knowledge-ai-enrichment Wave 0 曾锁定三级链（上年 DB → 通用大模型 → 模板）并接入知识库
RAG 回退（原 ``test_disclosure_note_rag_characterization`` / ``test_disclosure_note_rag_integration``）。用户
2026-10-16 拍板「LLM 只支持用户手动单击时调用」（spec disclosure-note-template-word-realignment Task 21），生成链
删掉了大模型级与知识库回退（``_generate_text_with_llm`` / ``_get_enricher`` 已删，配置开关
``DISCLOSURE_NOTE_RAG_ENABLED`` 一并删除）。本文件锁两级链的取用逻辑与单章失败隔离；「全程零大模型调用」由
``test_note_generation_no_llm`` 守护（复用本文件的 helper）。手动 AI 入口不受影响，由各自端点测试守护。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.models.report_models import DisclosureNote
from app.services.disclosure_engine import DisclosureEngine

TEMPLATE_TEXT = "本公司存货采用成本与可变现净值孰低法进行后续计量。"


def _make_engine() -> DisclosureEngine:
    """构造带 mock db 的 DisclosureEngine（对齐 test_disclosure_engine_v2._make_engine）。"""
    db = MagicMock()
    db.execute = AsyncMock()
    db.flush = AsyncMock()
    db.rollback = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()
    eng = DisclosureEngine(db)
    eng._wp_cache = {}
    eng._tb_cache = {}
    eng._wp_account_cache = {}
    eng._wp_fine_cache = {}
    eng._prior_notes_cache = {}
    return eng


def _minimal_template(text_sections: list[str] | None = None, *, note_section: str = "五、1 存货",
                      title: str = "存货") -> dict:
    return {
        "note_section": note_section,
        "section_title": title,
        "account_name": title,
        "content_type": "table",
        "sort_order": 1,
        "text_sections": text_sections or [],
        "text_template": None,
        "tables": [],
        "llm_prompt_key": None,
    }


def _stub_generate_notes_io(eng: DisclosureEngine) -> None:
    """把 generate_notes 内部的 DB / 构表 IO stub 掉，只保留正文取用逻辑。"""
    eng._build_table_data = AsyncMock(return_value=None)  # type: ignore[assignment]
    # 所有 db.execute 统一返回「无既有记录」（走新建分支 db.add(note)）；version_line 的 max 查询也复用
    res_mock = MagicMock()
    res_mock.scalar_one_or_none = MagicMock(return_value=None)
    res_mock.scalar = MagicMock(return_value=None)
    res_mock.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
    eng.db.execute = AsyncMock(return_value=res_mock)


def _with_prior(eng: DisclosureEngine, prior: dict) -> None:
    async def _fake_preload(_pid, _yr):
        eng._prior_notes_cache = dict(prior)

    eng._preload_data_for_notes = _fake_preload  # type: ignore[assignment]


def _added_notes(eng: DisclosureEngine) -> list[DisclosureNote]:
    """db.add 的全部 DisclosureNote（末尾还会 add 一个 VersionLineStamp，按类型过滤）。"""
    return [c.args[0] for c in eng.db.add.call_args_list if isinstance(c.args[0], DisclosureNote)]


def _added_note(eng: DisclosureEngine) -> DisclosureNote:
    notes = _added_notes(eng)
    if not notes:
        raise AssertionError("generate_notes 未 db.add 任何 DisclosureNote")
    return notes[0]


@pytest.mark.asyncio
async def test_prior_year_note_wins_over_template():
    """第 1 级：上年附注（>20 字）命中 ⇒ 用上年正文，不用模板正文。"""
    eng = _make_engine()
    eng._load_templates = AsyncMock(return_value=[_minimal_template([TEMPLATE_TEXT])])  # type: ignore[assignment]
    _with_prior(eng, {"五、1 存货": "本年度存货主要由原材料和库存商品构成，期末余额较上年略有增长。"})
    _stub_generate_notes_io(eng)

    await eng.generate_notes(uuid4(), 2025, "soe")

    text = _added_note(eng).text_content
    assert "库存商品" in text and TEMPLATE_TEXT not in text


@pytest.mark.asyncio
async def test_prior_dict_entry_text_is_used():
    """上年缓存条目是 {"text","table"} dict（Wave1 Task2.3）时取其 text。"""
    eng = _make_engine()
    eng._load_templates = AsyncMock(return_value=[_minimal_template([TEMPLATE_TEXT])])  # type: ignore[assignment]
    _with_prior(eng, {"五、1 存货": {"text": "上年附注写的存货正文，长度超过二十个字符用于通过阈值。", "table": None}})
    _stub_generate_notes_io(eng)

    await eng.generate_notes(uuid4(), 2025, "soe")

    assert _added_note(eng).text_content == "上年附注写的存货正文，长度超过二十个字符用于通过阈值。"


@pytest.mark.asyncio
@pytest.mark.parametrize("prior", [{}, {"五、1 存货": "太短"}], ids=["no_prior", "prior_not_over_20_chars"])
async def test_falls_to_template_text_when_prior_missing_or_short(prior):
    """第 2 级：上年缺失 / 不足 20 字 ⇒ 模板实质正文（中间不再有大模型级）。"""
    eng = _make_engine()
    eng._load_templates = AsyncMock(return_value=[_minimal_template([TEMPLATE_TEXT])])  # type: ignore[assignment]
    _with_prior(eng, prior)
    _stub_generate_notes_io(eng)

    await eng.generate_notes(uuid4(), 2025, "soe")

    assert _added_note(eng).text_content == TEMPLATE_TEXT


@pytest.mark.asyncio
async def test_no_prior_and_no_template_text_leaves_text_empty():
    """两级都没有 ⇒ 正文留空（不编造、不调大模型补）。"""
    eng = _make_engine()
    eng._load_templates = AsyncMock(return_value=[_minimal_template([])])  # type: ignore[assignment]
    _with_prior(eng, {})
    _stub_generate_notes_io(eng)

    await eng.generate_notes(uuid4(), 2025, "soe")

    assert not _added_note(eng).text_content


@pytest.mark.asyncio
async def test_single_section_table_failure_is_isolated():
    """单章构表抛错 ⇒ 仅该章表格为空，正文照常、其余章节照常生成，整体不失败（原 RAG Property 12 的生成侧部分）。"""
    eng = _make_engine()
    templates = [
        _minimal_template([TEMPLATE_TEXT], note_section="五、1 存货", title="存货"),
        _minimal_template(["B 章节模板正文，长度足够。"], note_section="五、2 应收账款", title="应收账款"),
    ]
    eng._load_templates = AsyncMock(return_value=templates)  # type: ignore[assignment]
    _with_prior(eng, {})
    _stub_generate_notes_io(eng)

    async def _build(project_id, year, tmpl, **_kw):
        if tmpl["note_section"] == "五、1 存货":
            raise RuntimeError("boom（单章构表异常）")
        return {"tables": []}

    eng._build_section_table_data = _build  # type: ignore[assignment]

    await eng.generate_notes(uuid4(), 2025, "soe")

    by_section = {n.note_section: n for n in _added_notes(eng)}
    assert set(by_section) == {"五、1 存货", "五、2 应收账款"}
    assert by_section["五、1 存货"].text_content == TEMPLATE_TEXT
    assert by_section["五、2 应收账款"].text_content == "B 章节模板正文，长度足够。"


def test_llm_client_module_exports_chat_completion_not_llm_client():
    """手动 AI 入口（NoteKnowledgeEnricher 等）依赖模块级 ``chat_completion``；``llm_client`` 单例不存在。

    历史 bug：生成链曾 ``from app.services.llm_client import llm_client``（不存在）被 try/except 吞掉。
    若将来重新引入 ``llm_client`` 单例，此断言提示「大模型层 API 已变，需重估各手动入口的接入方式」。
    """
    import app.services.llm_client as llm_mod

    assert not hasattr(llm_mod, "llm_client")
    assert hasattr(llm_mod, "chat_completion")


@pytest.mark.asyncio
async def test_title_hint_is_written_to_guidance_without_mutating_title_or_body(monkeypatch):
    """标题后的编制提示只走 guidance_text，不混入标题、账户名或正文。"""
    import app.services.disclosure_engine as engine_module

    eng = _make_engine()
    template = _minimal_template([], note_section="八、70", title="投资收益")
    template["title_hint"] = "下表中不适用的项目，删除"
    eng._load_templates = AsyncMock(return_value=[template])  # type: ignore[assignment]
    _with_prior(eng, {})
    _stub_generate_notes_io(eng)
    monkeypatch.setattr(
        engine_module,
        "classify_template_content",
        lambda *_args, **_kwargs: (None, "请核对本期金额", {}),
    )

    await eng.generate_notes(uuid4(), 2025, "soe")

    note = _added_note(eng)
    assert note.guidance_text == "标题提示：下表中不适用的项目，删除\n\n请核对本期金额"
    assert note.section_title == note.account_name == "投资收益"
    assert note.text_content is None
