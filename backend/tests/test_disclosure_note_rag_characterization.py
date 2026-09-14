"""Characterization（零回归安全网）— disclosure-note-knowledge-ai-enrichment Wave 0 Task 2.

锁定"接入知识库 RAG 之前"的现有行为基线，作为后续 Property 6（关闭开关零回归）的对照。

覆盖对象：
- `DisclosureEngine._generate_text_with_llm`：**dead-import 已在 Task 5 修复**。
  历史 bug：函数体内 `from app.services.llm_client import llm_client` 引用了不存在的
  `llm_client` 符号（该模块只导出模块级 async 函数 `chat_completion`），ImportError 被
  外层 try/except 吞掉 → 恒返回 None，通用 LLM 层沦为死代码。Task 5 修复为使用模块级
  `chat_completion`（返回 str），并按"占位串（[LLM.../⚠️...）即降级、非占位且非空才当正文"
  （复用 `note_knowledge_enricher._is_llm_error`）判定。故本文件的 Part A 已同步更新为
  **修复后契约**：LLM 可用返有效文本时返回该文本；LLM 不可用（占位串）或抛异常时返回 None
  （fail-open）。此为对 bug 的有意修复，非放宽断言——其余零回归断言（never-raises /
  prompt_key 无分支差异 / 三级决策链）保留。
- `DisclosureEngine.generate_notes`：三级填充优先级链的**决策逻辑**（上年 DB
  `_prior_notes_cache` 优先 → `_generate_text_with_llm` 结果 → 模板默认文字）。
  Part B 通过直接 stub `eng._generate_text_with_llm` 隔离验证 generate_notes 的分支
  取用逻辑（DB 命中则 LLM 不被调用；DB 缺失则用 LLM 结果；LLM 为 None 则用模板）。

`DISCLOSURE_NOTE_RAG_ENABLED` 默认 False，故"当前代码"即"关闭开关"状态：本文件全部在
开关关闭下跑通（绿），构成 Property 6（关闭开关零回归）基线——RAG 关闭时
`_generate_text_with_llm` 不实例化/不调用 enricher（走通用 chat_completion 路径），
generate_notes 三级决策链行为不变。

Spec:   .kiro/specs/disclosure-note-knowledge-ai-enrichment/
Reqs:   6.1, 6.2, 6.3  Property: 6
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.models.report_models import DisclosureNote
from app.services.disclosure_engine import DisclosureEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


def _minimal_template(text_sections: list[str] | None = None) -> dict:
    return {
        "note_section": "五、1 存货",
        "section_title": "存货",
        "account_name": "存货",
        "content_type": "table",
        "sort_order": 1,
        "text_sections": text_sections or [],
        "text_template": None,
        "tables": [],
        "llm_prompt_key": None,
    }


def _stub_generate_notes_io(eng: DisclosureEngine) -> None:
    """把 generate_notes 内部的 DB / 模板 IO stub 掉，只保留三级填充决策逻辑。"""
    eng._build_table_data = AsyncMock(return_value=None)  # type: ignore[assignment]
    # 所有 db.execute 统一返回：upsert existing 查询 → 无既有记录（走 new note 分支，
    # 会调 db.add(note)）；version_line_service 的 max(version_no) 查询也复用此 mock。
    res_mock = MagicMock()
    res_mock.scalar_one_or_none = MagicMock(return_value=None)
    res_mock.scalar = MagicMock(return_value=None)
    eng.db.execute = AsyncMock(return_value=res_mock)


def _added_note(eng: DisclosureEngine) -> DisclosureNote:
    """从 db.add 的全部调用中取出被添加的 DisclosureNote。

    generate_notes 末尾会经 version_line_service.write_stamp 再 db.add 一个
    VersionLineStamp，故 db.add.call_args（最后一次）不是 note；必须按类型过滤。
    """
    for call in eng.db.add.call_args_list:
        obj = call.args[0]
        if isinstance(obj, DisclosureNote):
            return obj
    raise AssertionError("generate_notes 未 db.add 任何 DisclosureNote")


# ===========================================================================
# Part A: _generate_text_with_llm —— dead-import 修复后契约
# （RAG 默认关闭，走通用 chat_completion 路径；占位串→None，有效文本→返回文本）
# ===========================================================================

# chat_completion 服务不可用时的占位串（llm_client._sync_completion 的降级返回）
_LLM_UNAVAILABLE = "[LLM 服务暂不可用，请检查 vLLM 是否启动]"


@pytest.mark.asyncio
async def test_generate_text_returns_none_when_llm_unavailable():
    """修复后契约：LLM 不可用（chat_completion 返占位串）→ _generate_text_with_llm 返回 None。

    dead-import 修复后走真实 chat_completion；服务不可用返回 [LLM ...] 占位串，
    经 _is_llm_error 判定为降级 → 返回 None，降级到模板默认文字。
    """
    eng = _make_engine()
    with patch(
        "app.services.disclosure_engine.chat_completion",
        new=AsyncMock(return_value=_LLM_UNAVAILABLE),
    ):
        out = await eng._generate_text_with_llm(uuid4(), 2025, "五、1", "存货", "存货")
    assert out is None


@pytest.mark.asyncio
async def test_generate_text_returns_content_when_llm_ok():
    """修复后契约：LLM 可用返有效正文 → _generate_text_with_llm 返回该正文（dead-import 已修）。"""
    eng = _make_engine()
    valid = "本公司存货主要由原材料及库存商品构成，按成本与可变现净值孰低计量。"
    with patch(
        "app.services.disclosure_engine.chat_completion",
        new=AsyncMock(return_value=valid),
    ):
        out = await eng._generate_text_with_llm(uuid4(), 2025, "五、1", "存货", "存货")
    assert out == valid


@pytest.mark.asyncio
async def test_generate_text_returns_none_even_with_tb_cache_when_unavailable():
    """试算表缓存命中仅补充上下文；LLM 不可用仍返 None（tb_cache 不改变降级结果）。"""
    eng = _make_engine()
    eng._tb_cache["存货"] = {"audited": 12345.67, "opening": 8000.0, "unadjusted": 0}
    with patch(
        "app.services.disclosure_engine.chat_completion",
        new=AsyncMock(return_value=_LLM_UNAVAILABLE),
    ):
        out = await eng._generate_text_with_llm(uuid4(), 2025, "五、1", "存货", "存货")
    assert out is None


@pytest.mark.asyncio
async def test_generate_text_never_raises():
    """零回归：chat_completion 抛异常时 _generate_text_with_llm 不向上抛（内部 try/except 兜底→None）。"""
    eng = _make_engine()
    with patch(
        "app.services.disclosure_engine.chat_completion",
        new=AsyncMock(side_effect=RuntimeError("boom")),
    ):
        out = await eng._generate_text_with_llm(
            uuid4(), 2025, "五、99", "不存在科目", "不存在科目", "some_prompt_key",
        )
    assert out is None


@pytest.mark.asyncio
async def test_generate_text_none_regardless_of_prompt_key():
    """零回归：带/不带 prompt_key 行为一致（LLM 不可用均 None）——锁定无分支差异。"""
    eng = _make_engine()
    with patch(
        "app.services.disclosure_engine.chat_completion",
        new=AsyncMock(return_value=_LLM_UNAVAILABLE),
    ):
        without = await eng._generate_text_with_llm(uuid4(), 2025, "五、1", "存货", "存货")
        with_key = await eng._generate_text_with_llm(
            uuid4(), 2025, "五、1", "存货", "存货", "custom_prompt",
        )
    assert without is None
    assert with_key is None


def test_llm_client_module_exports_chat_completion_not_llm_client():
    """模块 API 守卫：llm_client 模块导出 chat_completion 函数，无 llm_client 对象。

    这是 Task 5 dead-import 修复的前提（须用 chat_completion 而非不存在的 llm_client）。
    若将来有人重新引入 `llm_client` 单例，此断言提示"LLM 层 API 已变，需重估接入方式"。
    """
    import app.services.llm_client as llm_mod

    assert not hasattr(llm_mod, "llm_client"), (
        "llm_client 模块出现了 llm_client 符号——需重新评估 _generate_text_with_llm 的接入方式"
    )
    assert hasattr(llm_mod, "chat_completion")


# ===========================================================================
# Part B: generate_notes —— 三级填充优先级链决策逻辑（stub LLM 层隔离验证）
# ===========================================================================


@pytest.mark.asyncio
async def test_generate_notes_prior_year_db_wins_llm_not_called():
    """优先级 1：上年 DB 附注（>20 字）命中 → 用之，且 _generate_text_with_llm 不被调用。"""
    eng = _make_engine()
    eng._load_templates = AsyncMock(return_value=[_minimal_template()])  # type: ignore[assignment]

    async def _fake_preload(_pid, _yr):
        eng._prior_notes_cache = {
            "五、1 存货": "本年度存货主要由原材料和库存商品构成，期末余额较上年略有增长。",
        }

    eng._preload_data_for_notes = _fake_preload  # type: ignore[assignment]
    _stub_generate_notes_io(eng)
    eng._generate_text_with_llm = AsyncMock(  # type: ignore[assignment]
        return_value="不应被使用的 LLM 文本内容内容内容内容内容",
    )

    await eng.generate_notes(uuid4(), 2025, "soe")

    # 核心：DB 优先，LLM 未被调用
    eng._generate_text_with_llm.assert_not_awaited()
    note = _added_note(eng)
    assert note.text_content is not None
    assert "库存商品" in note.text_content


@pytest.mark.asyncio
async def test_generate_notes_falls_to_llm_when_prior_missing():
    """优先级 2：上年缺失 → 调 _generate_text_with_llm，其 (>20 字) 结果作为正文。"""
    eng = _make_engine()
    eng._load_templates = AsyncMock(return_value=[_minimal_template()])  # type: ignore[assignment]

    async def _fake_preload(_pid, _yr):
        eng._prior_notes_cache = {}  # 上年缺失

    eng._preload_data_for_notes = _fake_preload  # type: ignore[assignment]
    _stub_generate_notes_io(eng)
    llm_text = "由 LLM 生成的存货附注正文，长度超过二十个字符用于通过阈值。"
    eng._generate_text_with_llm = AsyncMock(return_value=llm_text)  # type: ignore[assignment]

    await eng.generate_notes(uuid4(), 2025, "soe")

    eng._generate_text_with_llm.assert_awaited_once()
    note = _added_note(eng)
    assert note.text_content == llm_text


@pytest.mark.asyncio
async def test_generate_notes_short_prior_does_not_win():
    """基线阈值：上年文字 ≤20 字不算命中 → 降级到 LLM（锁定 len>20 判定）。"""
    eng = _make_engine()
    eng._load_templates = AsyncMock(return_value=[_minimal_template()])  # type: ignore[assignment]

    async def _fake_preload(_pid, _yr):
        eng._prior_notes_cache = {"五、1 存货": "太短"}  # ≤20 字

    eng._preload_data_for_notes = _fake_preload  # type: ignore[assignment]
    _stub_generate_notes_io(eng)
    llm_text = "上年过短时应由 LLM 生成正文，长度超过二十个字符。"
    eng._generate_text_with_llm = AsyncMock(return_value=llm_text)  # type: ignore[assignment]

    await eng.generate_notes(uuid4(), 2025, "soe")

    eng._generate_text_with_llm.assert_awaited_once()
    note = _added_note(eng)
    assert note.text_content == llm_text


@pytest.mark.asyncio
async def test_generate_notes_falls_to_template_when_llm_none():
    """优先级 3：上年缺失 + LLM 返 None → 用模板 substantive 正文。

    注：LLM 返 None 正是当前生产真实状态（Part A 已锁定 _generate_text_with_llm 恒 None），
    此处用 stub 显式复现该值以隔离验证 generate_notes 的"降级到模板"分支。
    """
    eng = _make_engine()
    eng._load_templates = AsyncMock(  # type: ignore[assignment]
        return_value=[_minimal_template(
            text_sections=["本公司存货采用成本与可变现净值孰低法进行后续计量。"],
        )],
    )

    async def _fake_preload(_pid, _yr):
        eng._prior_notes_cache = {}

    eng._preload_data_for_notes = _fake_preload  # type: ignore[assignment]
    _stub_generate_notes_io(eng)
    eng._generate_text_with_llm = AsyncMock(return_value=None)  # type: ignore[assignment]

    await eng.generate_notes(uuid4(), 2025, "soe")

    eng._generate_text_with_llm.assert_awaited_once()
    note = _added_note(eng)
    assert note.text_content == "本公司存货采用成本与可变现净值孰低法进行后续计量。"


@pytest.mark.asyncio
async def test_generate_notes_real_llm_tier_yields_template_end_to_end():
    """端到端零回归：不 stub `_generate_text_with_llm`，走真实通用路径（RAG 默认关闭）。

    上年缺失 → 真实 _generate_text_with_llm 调 chat_completion（mock 为不可用占位串）
    → _is_llm_error 判降级返 None → 最终落模板 substantive。
    锁定"LLM 不可用时三级链退化为 DB→模板"，且 RAG 关闭不触达 enricher。
    """
    eng = _make_engine()
    eng._load_templates = AsyncMock(  # type: ignore[assignment]
        return_value=[_minimal_template(
            text_sections=["本公司存货采用成本与可变现净值孰低法进行后续计量。"],
        )],
    )

    async def _fake_preload(_pid, _yr):
        eng._prior_notes_cache = {}

    eng._preload_data_for_notes = _fake_preload  # type: ignore[assignment]
    _stub_generate_notes_io(eng)
    # 不 stub _generate_text_with_llm：走真实代码；mock chat_completion 为服务不可用占位串
    with patch(
        "app.services.disclosure_engine.chat_completion",
        new=AsyncMock(return_value=_LLM_UNAVAILABLE),
    ):
        await eng.generate_notes(uuid4(), 2025, "soe")

    note = _added_note(eng)
    assert note.text_content == "本公司存货采用成本与可变现净值孰低法进行后续计量。"


# ===========================================================================
# Part C: 零回归基线锚点 —— RAG 默认关闭
# ===========================================================================


def test_rag_disabled_by_default_defines_baseline():
    """DISCLOSURE_NOTE_RAG_ENABLED 默认 False：本文件的"当前行为"即"关闭开关"基线（P6）。"""
    from app.core.config import settings

    assert settings.DISCLOSURE_NOTE_RAG_ENABLED is False
