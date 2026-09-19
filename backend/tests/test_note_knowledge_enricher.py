"""NoteKnowledgeEnricher 单测 + PBT（disclosure-note-knowledge-ai-enrichment Task 4）

覆盖正确性属性：
- P1  命中即注入（prompt 含片段 + document_name）
- P2  retrieve fail-open（异常 / 空 → []）
- P5  citations 与命中一致（无凭空构造）
- P7  build_query 不含整段模板
- P8  build_grounded_user_prompt 截断到 ≤ char_budget
- P9  doc_filter 范围（结果 source_id 全 ∈ doc_filter）
- P10 权限过滤（传 user 时 semantic_search 收到 user）
- P12 batch 单章异常隔离
- P13 reference_only 不调 chat_completion
- P14 system prompt 含反幻觉约束
- P15 batch 跳过已有 / 锁定 / manual_override
- P16 中文 system prompt

hypothesis 覆盖 P1 / P8 / P9（fast profile，显式 max_examples=5）。
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.note_knowledge_enricher import (
    _GROUNDED_SYSTEM_PROMPT_ZH,
    Citation,
    GroundedDraft,
    NoteKnowledgeEnricher,
)

_ENRICHER_MOD = "app.services.note_knowledge_enricher"


# ── 测试替身 ──────────────────────────────────────────────────────────────
class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class FakeDb:
    """仅用于 doc_filter 文件夹展开的 execute。"""

    def __init__(self, folder_docs=None):
        self._folder_docs = folder_docs or []
        self.executed = False

    async def execute(self, stmt):
        self.executed = True
        return FakeResult(self._folder_docs)


class FakeKnowledgeService:
    def __init__(self, results=None, raise_exc=None):
        self._results = results if results is not None else []
        self._raise = raise_exc
        self.calls: list[dict] = []

    async def semantic_search(
        self,
        project_id,
        query,
        top_k,
        *,
        scope="all",
        user=None,
        wp_code=None,
        account_code=None,
        audit_area=None,
    ):
        self.calls.append(
            {
                "project_id": project_id,
                "query": query,
                "top_k": top_k,
                "scope": scope,
                "user": user,
                "account_code": account_code,
                "audit_area": audit_area,
            }
        )
        if self._raise is not None:
            raise self._raise
        return list(self._results)


def _make_enricher(results=None, raise_exc=None, folder_docs=None):
    ks = FakeKnowledgeService(results=results, raise_exc=raise_exc)
    db = FakeDb(folder_docs=folder_docs)
    enricher = NoteKnowledgeEnricher(db, knowledge_service=ks)
    return enricher, ks, db


def _result(source_id, content="片段内容", doc_name="模板文档", is_stale=False, score=0.9):
    return {
        "source_type": "knowledge_doc",
        "source_id": source_id,
        "content": content,
        "score": score,
        "is_stale": is_stale,
        "document_name": doc_name,
        "folder_path": "附注模板",
    }


# ── P7: build_query 不含整段模板 ─────────────────────────────────────────
def test_build_query_excludes_full_template():
    enricher, _, _ = _make_enricher()
    template_blob = "这是一大段模板正文，包含大量默认披露文字不应进入查询" * 5
    q = enricher.build_query("五、23 应收账款", "应收账款", "1122")
    assert "应收账款" in q
    assert "1122" in q
    assert template_blob not in q
    # 查询串短小，不含整段模板
    assert len(q) < 100


# ── P14 / P16: 反幻觉约束 + 中文 system prompt ────────────────────────────
def test_system_prompt_has_narrative_and_chinese_constraints():
    # P14 反幻觉：不虚构金额/比例/日期/主体
    assert "不得编造" in _GROUNDED_SYSTEM_PROMPT_ZH or "不编造" in _GROUNDED_SYSTEM_PROMPT_ZH
    assert "金额" in _GROUNDED_SYSTEM_PROMPT_ZH
    assert "以附注表格" in _GROUNDED_SYSTEM_PROMPT_ZH
    # P16 中文输出要求
    assert "中文" in _GROUNDED_SYSTEM_PROMPT_ZH


# ── P14（第二子句 / Req9.4）: AI 生成路径不写入任何附注表格数值单元格 ──────────
def test_grounded_draft_is_narrative_only_no_table_numeric_cells():
    """P14/Req9.4：AI 生成产物结构上只承载文字叙述 + 引用来源，不含任何附注表格数值单元格。

    GroundedDraft 是 AI 生成路径的唯一产物（generate_note_text / batch_prefill 返回）。
    其字段仅 {text, citations, degraded}——不存在 table / cells / values / amounts 等
    数值单元格载体，故 AI 生成路径结构上不可能写入附注表格数值单元格（Narrative_Only）。
    此断言守卫"不新增 AI 自动写表格数值路径"（Req9.4）：若将来有人给 GroundedDraft 加
    表格数值字段，此测试会失败并提示需重估数值安全边界。
    """
    import dataclasses

    field_names = {f.name for f in dataclasses.fields(GroundedDraft)}
    assert field_names == {"text", "citations", "degraded"}, (
        f"GroundedDraft 字段应仅为文字叙述载体，实际={field_names}——"
        f"AI 生成路径不得承载附注表格数值单元格（Req9.4）"
    )
    # 数值单元格相关字段名一律不得出现
    forbidden = {"table", "tables", "table_data", "cells", "cell", "values", "amounts", "amount", "numeric"}
    assert not (field_names & forbidden), "GroundedDraft 出现了数值单元格字段，违反 Req9.4"

    # 实例层面：生成产物只暴露 text（文字）+ citations（来源），无数值单元格属性
    draft = GroundedDraft(text="纯文字叙述", citations=[], degraded=False)
    assert isinstance(draft.text, str)
    for attr in forbidden:
        assert not hasattr(draft, attr)


# ── P2: retrieve fail-open ────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_retrieve_fail_open_on_exception():
    enricher, _, _ = _make_enricher(raise_exc=RuntimeError("boom"))
    out = await enricher.retrieve("pid", "query")
    assert out == []


@pytest.mark.asyncio
async def test_retrieve_fail_open_on_empty():
    enricher, _, _ = _make_enricher(results=[])
    out = await enricher.retrieve("pid", "query")
    assert out == []


# ── P10: 权限过滤透传 user ─────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_retrieve_passes_user_and_scope():
    enricher, ks, _ = _make_enricher(results=[_result("d1")])
    user = object()
    await enricher.retrieve("pid", "q", user=user, account_code="1122", audit_area="应收")
    assert len(ks.calls) == 1
    call = ks.calls[0]
    assert call["user"] is user
    assert call["scope"] == "knowledge_doc"
    assert call["account_code"] == "1122"
    assert call["audit_area"] == "应收"


# ── P5: citations 与命中一致 ──────────────────────────────────────────────
@pytest.mark.asyncio
async def test_citations_match_hits():
    results = [
        _result("d1", content="A 片段", doc_name="上年附注", is_stale=True, score=0.88),
        _result("d2", content="B 片段", doc_name="模板", score=0.77),
    ]
    enricher, _, _ = _make_enricher(results=results)
    cites = await enricher.retrieve("pid", "q")
    assert len(cites) == 2
    assert {c.source_id for c in cites} == {"d1", "d2"}
    c1 = next(c for c in cites if c.source_id == "d1")
    assert c1.document_name == "上年附注"
    assert c1.is_stale is True
    assert c1.snippet == "A 片段"
    assert c1.score == 0.88


# ── P9: doc_filter 范围过滤 ───────────────────────────────────────────────
@pytest.mark.asyncio
async def test_retrieve_doc_filter_scope():
    from uuid import uuid4

    keep, drop = str(uuid4()), str(uuid4())
    results = [_result(keep), _result(drop)]
    enricher, _, _ = _make_enricher(results=results)
    from uuid import UUID

    cites = await enricher.retrieve("pid", "q", doc_filter=[UUID(keep)])
    assert {c.source_id for c in cites} == {keep}


# ── P1: 命中即注入 prompt ─────────────────────────────────────────────────
def test_build_grounded_prompt_injects_hits():
    cites = [Citation(document_name="上年附注", folder_path="模板", snippet="独特片段XYZ", score=0.9, source_id="d1")]
    out = NoteKnowledgeEnricher(FakeDb(), knowledge_service=FakeKnowledgeService()).build_grounded_user_prompt(
        "任务上下文", cites, char_budget=3000
    )
    assert "独特片段XYZ" in out
    assert "上年附注" in out


def test_build_grounded_prompt_no_citations_falls_back():
    out = NoteKnowledgeEnricher(FakeDb(), knowledge_service=FakeKnowledgeService()).build_grounded_user_prompt(
        "纯任务上下文", [], char_budget=3000
    )
    assert "纯任务上下文" in out
    assert "参照资料" not in out


# ── P8: 字符预算截断 ──────────────────────────────────────────────────────
def test_build_grounded_prompt_truncates_to_budget():
    cites = [Citation(document_name="doc", folder_path="f", snippet="长" * 400, score=0.9, source_id="d1")]
    enricher = NoteKnowledgeEnricher(FakeDb(), knowledge_service=FakeKnowledgeService())
    out = enricher.build_grounded_user_prompt("上下文" * 200, cites, char_budget=120)
    assert len(out) <= 120


# ── P13: reference_only 不调 chat_completion ──────────────────────────────
@pytest.mark.asyncio
async def test_reference_only_does_not_call_llm(monkeypatch):
    cc = AsyncMock(return_value="不该被调用")
    monkeypatch.setattr(f"{_ENRICHER_MOD}.chat_completion", cc)
    enricher, _, _ = _make_enricher(results=[_result("d1", content="原文片段")])
    draft = await enricher.generate_note_text(
        "pid", 2025, "note1", "五、应收账款", "应收账款", reference_only=True
    )
    assert cc.call_count == 0
    assert draft.text is None
    assert len(draft.citations) == 1
    assert draft.citations[0].snippet == "原文片段"
    assert draft.degraded is True


# ── generate_note_text: 正常生成 / fail-open ──────────────────────────────
@pytest.mark.asyncio
async def test_generate_note_text_success(monkeypatch):
    cc = AsyncMock(return_value="这是生成的中文附注正文。")
    monkeypatch.setattr(f"{_ENRICHER_MOD}.chat_completion", cc)
    enricher, _, _ = _make_enricher(results=[_result("d1")])
    draft = await enricher.generate_note_text("pid", 2025, "n1", "五、应收账款", "应收账款")
    assert draft.text == "这是生成的中文附注正文。"
    assert draft.degraded is False  # 有命中
    assert cc.call_count == 1
    # system prompt 为反幻觉中文约束（chat_completion 的 messages 为首个位置参数）
    sent_messages = cc.call_args.args[0]
    assert sent_messages[0]["content"] == _GROUNDED_SYSTEM_PROMPT_ZH


@pytest.mark.asyncio
async def test_generate_note_text_llm_error_degrades(monkeypatch):
    cc = AsyncMock(return_value="[LLM 服务暂不可用，请检查 vLLM 是否启动]")
    monkeypatch.setattr(f"{_ENRICHER_MOD}.chat_completion", cc)
    enricher, _, _ = _make_enricher(results=[_result("d1")])
    draft = await enricher.generate_note_text("pid", 2025, "n1", "五、应收账款", "应收账款")
    assert draft.text is None
    assert draft.degraded is True


@pytest.mark.asyncio
async def test_generate_note_text_no_hits_degraded(monkeypatch):
    """P2：检索空命中 → generate_note_text 返回 text=None/citations=[]（不生成），
    由 DisclosureEngine caller 退回带 TB 上下文的通用 LLM 路径（design Property 2）。"""
    cc = AsyncMock(return_value="不该被调用")
    monkeypatch.setattr(f"{_ENRICHER_MOD}.chat_completion", cc)
    enricher, _, _ = _make_enricher(results=[])
    draft = await enricher.generate_note_text("pid", 2025, "n1", "五、应收账款", "应收账款")
    assert draft.text is None  # 无 RAG 依据 → 不由 enricher 生成（Property 2）
    assert draft.degraded is True
    assert draft.citations == []
    assert cc.call_count == 0  # 不做无上下文的裸生成，交回 caller 通用路径


@pytest.mark.asyncio
async def test_generate_note_text_retrieve_exception_fail_open(monkeypatch):
    """P2：semantic_search 抛异常 → retrieve fail-open 返回 [] → generate_note_text
    返回 text=None/citations=[]，绝不向上抛异常（design Property 2）。"""
    cc = AsyncMock(return_value="不该被调用")
    monkeypatch.setattr(f"{_ENRICHER_MOD}.chat_completion", cc)
    enricher, _, _ = _make_enricher(raise_exc=RuntimeError("kb down"))
    draft = await enricher.generate_note_text("pid", 2025, "n1", "五、应收账款", "应收账款")
    assert draft.text is None
    assert draft.degraded is True
    assert draft.citations == []
    assert cc.call_count == 0


# ── retrieve_prior_year_note ──────────────────────────────────────────────
@pytest.mark.asyncio
async def test_prior_year_note_hit(monkeypatch):
    enricher, _, _ = _make_enricher(results=[_result("d1", content="上年应收账款为...", doc_name="上年审计报告")])
    draft = await enricher.retrieve_prior_year_note("pid", "n1", "五、应收账款", "应收账款")
    assert draft is not None
    assert draft.text == "上年应收账款为..."
    assert draft.citations[0].document_name == "上年审计报告"


@pytest.mark.asyncio
async def test_prior_year_note_miss_returns_none():
    enricher, _, _ = _make_enricher(results=[])
    draft = await enricher.retrieve_prior_year_note("pid", "n1", "五、应收账款", "应收账款")
    assert draft is None


# ── P15: batch 跳过已有 / 锁定 / manual_override ──────────────────────────
@pytest.mark.asyncio
async def test_batch_skips_existing_locked_override(monkeypatch):
    cc = AsyncMock(return_value="新生成")
    monkeypatch.setattr(f"{_ENRICHER_MOD}.chat_completion", cc)
    enricher, _, _ = _make_enricher(results=[_result("d1")])
    sections = [
        {"note_section": "has_text", "text_content": "已有实质正文", "section_title": "T", "account_name": "A"},
        {"note_section": "locked", "is_locked": True, "section_title": "T", "account_name": "A"},
        {"note_section": "manual", "manual_override": True, "section_title": "T", "account_name": "A"},
        {"note_section": "empty", "text_content": "", "section_title": "五、应收", "account_name": "应收账款"},
    ]
    results = await enricher.batch_prefill("pid", 2025, sections)
    by = {r["note_section"]: r for r in results}
    assert by["has_text"]["status"] == "skipped"
    assert by["locked"]["status"] == "skipped"
    assert by["manual"]["status"] == "skipped"
    assert by["empty"]["status"] == "generated"
    # 只对 empty 章节调用了一次 LLM
    assert cc.call_count == 1


# ── P12: batch 单章异常隔离 ───────────────────────────────────────────────
@pytest.mark.asyncio
async def test_batch_isolates_single_section_failure():
    enricher, _, _ = _make_enricher()

    async def fake_gen(project_id, year, note_section, section_title, account_name, **kw):
        if note_section == "boom":
            raise RuntimeError("section blew up")
        return GroundedDraft(text="ok", citations=[], degraded=True)

    enricher.generate_note_text = fake_gen
    sections = [
        {"note_section": "a", "section_title": "T", "account_name": "A"},
        {"note_section": "boom", "section_title": "T", "account_name": "A"},
        {"note_section": "c", "section_title": "T", "account_name": "A"},
    ]
    progress = []
    # on_progress 契约为 (done, total, note_section) 三参（design 型别 Callable[[int,int,Any],...]）
    results = await enricher.batch_prefill(
        "pid", 2025, sections, on_progress=lambda i, t, s: progress.append((i, t))
    )
    by = {r["note_section"]: r for r in results}
    assert by["a"]["status"] == "generated"
    assert by["c"]["status"] == "generated"
    assert by["boom"]["status"] == "degraded"  # 单章降级隔离
    assert progress[-1] == (3, 3)


# ══════════════════════ Hypothesis PBT（P1 / P8 / P9）══════════════════════

@settings(max_examples=5, deadline=None)
@given(
    snippet=st.text(min_size=1, max_size=40).filter(lambda s: s.strip()),
    doc_name=st.text(min_size=1, max_size=20).filter(lambda s: s.strip()),
)
def test_pbt_p1_hit_injected_into_prompt(snippet, doc_name):
    """P1：命中片段文本 + document_name 必进 prompt（足够预算）。"""
    enricher = NoteKnowledgeEnricher(FakeDb(), knowledge_service=FakeKnowledgeService())
    cites = [Citation(document_name=doc_name, folder_path="f", snippet=snippet, score=0.9, source_id="d1")]
    out = enricher.build_grounded_user_prompt("ctx", cites, char_budget=5000)
    assert snippet in out
    assert doc_name in out


@settings(max_examples=5, deadline=None)
@given(
    n=st.integers(min_value=0, max_value=4),
    budget=st.integers(min_value=10, max_value=500),
    base=st.text(min_size=0, max_size=300),
)
def test_pbt_p8_budget_truncation(n, budget, base):
    """P8：输出长度必 ≤ char_budget。"""
    enricher = NoteKnowledgeEnricher(FakeDb(), knowledge_service=FakeKnowledgeService())
    cites = [
        Citation(document_name=f"doc{i}", folder_path="f", snippet="内容" * 50, score=0.5, source_id=f"d{i}")
        for i in range(n)
    ]
    out = enricher.build_grounded_user_prompt(base, cites, char_budget=budget)
    assert len(out) <= budget


@settings(max_examples=5, deadline=None)
@given(
    ids=st.lists(st.integers(min_value=0, max_value=20), min_size=1, max_size=8, unique=True),
    filter_pick=st.lists(st.integers(min_value=0, max_value=20), min_size=0, max_size=8, unique=True),
)
def test_pbt_p9_doc_filter_scope(ids, filter_pick):
    """P9：doc_filter 非空时，结果 source_id 全 ∈ doc_filter。"""
    import asyncio
    from uuid import UUID

    def _u(i):
        return UUID(int=i)

    results = [_result(str(_u(i))) for i in ids]
    enricher, _, _ = _make_enricher(results=results)
    doc_filter = [_u(i) for i in filter_pick]

    async def _run():
        return await enricher.retrieve("pid", "q", doc_filter=doc_filter or None)

    cites = asyncio.run(_run())
    if doc_filter:
        allowed = {str(x) for x in doc_filter}
        assert all(c.source_id in allowed for c in cites)
    else:
        # 空 doc_filter → 不过滤，全部返回
        assert len(cites) == len(ids)
