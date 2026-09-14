"""附注知识库 RAG 增强编排层 (NoteKnowledgeEnricher).

把知识库 RAG 检索接入附注 AI 正文生成——加法式、可开关、fail-open 的薄编排层：
    检索 (semantic_search, scope='knowledge_doc') → 拼参照上下文 → chat_completion 起草叙述 → 附 Citation

核心铁律：
- **不新建检索实现**：复用 `KnowledgeIndexService.semantic_search`（pgvector+BM25+ilike 三级降级+权限过滤+enrich）。
- **Fail-Open**：检索/LLM 任一环失败或空命中 → 返回 GroundedDraft(text=None) / [] ，绝不向上抛异常，
  由 caller (DisclosureEngine) 退回现有三级填充。
- **Narrative_Only 反幻觉**（Req9）：AI 仅起草文字叙述，不编造未提供的金额/比例/日期/主体；
  披露数值以附注表格 / resolver 取数 / 底稿审定数为准。
- **权限不越权**：doc_filter 后置过滤 + `semantic_search` 的 `user` 权限过滤；来源限项目文档 + Global_KB
  全局共享文档（`_vector_search` 已同时检索 `[project_id, GLOBAL_KB_PROJECT_ID]`），不跨读其他客户项目私有文档。

Design: .kiro/specs/disclosure-note-knowledge-ai-enrichment/design.md
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable
from uuid import UUID

from app.core.config import settings
from app.services.llm_client import chat_completion

logger = logging.getLogger(__name__)

# 单条检索片段截断上限（Citation.snippet = 截断后的片段摘要，避免单片过长）
_SNIPPET_CHAR_CAP = 1200


# 反幻觉 system prompt（Req9.2）—— Narrative_Only：约束只依据所供资料/数据，
# 不虚构未提供的金额/比例/日期/主体名称；数值以表格/resolver/底稿为准。中文输出（Req1.7）。
_GROUNDED_SYSTEM_PROMPT_ZH = (
    "你是资深审计师，用中文起草财务报表附注正文。"
    "严格要求："
    "①只依据下方提供的参照资料与数据表述，优先沿用参照资料的口径、术语与结构；"
    "②绝不虚构未提供的金额、比例、日期、主体名称——凡未在参照资料或数据中出现的数字一律不得编造；"
    "③披露的具体数值以附注表格为准，你只起草文字叙述、不产出权威数字；"
    "④输出必须为规范的中文附注披露文字，不要输出解释性旁白或markdown标题。"
)


@dataclass
class Citation:
    """生成草稿所依据的知识库来源标识，随草稿返回供审计师核对。"""

    snippet: str  # 截断后的片段摘要
    score: float
    source_id: str
    document_name: str | None = None
    folder_path: str | None = None
    is_stale: bool = False  # 知识库索引过期标记（Req1.5 透传供新鲜度判断）


@dataclass
class GroundedDraft:
    """由 RAG 上下文驱动生成的附注正文草稿（含引用来源列表）。"""

    text: str | None = None  # None = 未生成（fail-open / reference-only）
    citations: list[Citation] = field(default_factory=list)  # 命中来源；空 = 无 RAG 依据
    degraded: bool = False  # True = 检索/LLM 降级（无依据的通用生成 或 无生成）


class NoteKnowledgeEnricher:
    """附注 RAG 增强薄编排层。所有对外方法 fail-open，不向上抛异常。"""

    def __init__(self, db, *, knowledge_service: Any | None = None):
        self._db = db
        self._top_k = int(getattr(settings, "DISCLOSURE_NOTE_RAG_TOP_K", 5) or 5)
        self._char_budget = int(getattr(settings, "DISCLOSURE_NOTE_RAG_CHAR_BUDGET", 3000) or 3000)
        # 允许注入（测试用），否则惰性构造，避免无谓依赖
        self._knowledge = knowledge_service

    def _get_knowledge_service(self):
        """惰性构造 KnowledgeIndexService（复用现有检索实现，不新建）。"""
        if self._knowledge is None:
            from app.services.knowledge_index_service import KnowledgeIndexService

            self._knowledge = KnowledgeIndexService(self._db)
        return self._knowledge

    # ------------------------------------------------------------------
    # 查询构造 (Req7.1 / Property 7)
    # ------------------------------------------------------------------
    def build_query(
        self,
        section_title: str,
        account_name: str,
        account_code: str | None = None,
    ) -> str:
        """Note_Context_Query：仅由 section_title + account_name + 派生关键词组成。

        **不包含整段模板正文**（Property 7）——caller 只传标题与科目，不传 text_template/text_sections。
        """
        parts: list[str] = []
        if account_name:
            parts.append(str(account_name).strip())
        if section_title:
            parts.append(str(section_title).strip())
        if account_code:
            parts.append(str(account_code).strip())
        parts.append("附注")  # 派生关键词，提升知识库附注文档召回
        return " ".join(p for p in parts if p)

    # ------------------------------------------------------------------
    # 检索 (Req1.1/1.4/1.6/4.1/4.4 / Property 2/5/9/10)
    # ------------------------------------------------------------------
    @staticmethod
    def _normalize_doc_filter(doc_filter: list[UUID] | list[str] | None) -> set[str] | None:
        """把 doc_filter 归一为 str 集合；None/空 → None（不过滤）。"""
        if not doc_filter:
            return None
        return {str(d).strip() for d in doc_filter if d is not None and str(d).strip()} or None

    async def retrieve(
        self,
        project_id,
        query: str,
        *,
        user: Any | None = None,
        account_code: str | None = None,
        audit_area: str | None = None,
        doc_filter: list[UUID] | list[str] | None = None,
        top_k: int | None = None,
    ) -> list[Citation]:
        """复用 semantic_search(scope='knowledge_doc'，含 project + Global_KB) 检索。

        - **Fail-Open**：异常/空命中 → 返回 []（Req1.3/6.1）。
        - **doc_filter 后置过滤**（semantic_search 本身无 document/folder 参数）：
          在 enricher 层按 `source_id ∈ doc_filter` 或 folder_path 匹配过滤（Req4.1/Property 9）。
        - **权限透传**：`user` 交给 semantic_search 的权限过滤（Req4.4/Property 10），不越权跨客户项目。
        - 片段正文读结果 dict 的 `content` 键（已核实：非 content_text）；透传 is_stale/document_name/folder_path。
        """
        k = int(top_k or self._top_k)
        try:
            svc = self._get_knowledge_service()
            raw = await svc.semantic_search(
                project_id,
                query,
                top_k=k,
                scope="knowledge_doc",
                user=user,
                account_code=account_code,
                audit_area=audit_area,
            )
        except Exception as e:  # fail-open
            logger.warning("附注 RAG 检索失败，fail-open 返回空：%s", e)
            return []

        if not raw:
            return []

        filter_set = self._normalize_doc_filter(doc_filter)
        citations: list[Citation] = []
        for r in raw:
            if not isinstance(r, dict):
                continue
            source_id = str(r.get("source_id") or "").strip()
            folder_path = r.get("folder_path")
            # doc_filter 后置过滤：source_id 命中，或 folder_path 命中
            if filter_set is not None:
                fp = str(folder_path).strip() if folder_path else ""
                if source_id not in filter_set and (not fp or fp not in filter_set):
                    continue
            content = str(r.get("content") or "")  # ← content 键（已核实，非 content_text）
            snippet = content[:_SNIPPET_CHAR_CAP]
            try:
                score = float(r.get("score") or 0.0)
            except (TypeError, ValueError):
                score = 0.0
            citations.append(
                Citation(
                    snippet=snippet,
                    score=score,
                    source_id=source_id,
                    document_name=r.get("document_name"),
                    folder_path=folder_path,
                    is_stale=bool(r.get("is_stale", False)),
                )
            )
        return citations

    # ------------------------------------------------------------------
    # 拼参照上下文 (Req7.3 / Property 1/8)
    # ------------------------------------------------------------------
    def build_grounded_user_prompt(
        self,
        base_context: str,
        citations: list[Citation],
        char_budget: int | None = None,
    ) -> str:
        """把命中片段（标注 document_name）拼为参照上下文，超预算截断（Req7.3）。

        **整个 grounded user prompt 输出（含 base_context / header / 参照片段块）受 `char_budget`
        约束，`len(输出) ≤ char_budget`**（design Property 8：「build_grounded_user_prompt 输出被截断到
        ≤ char_budget，不溢出」）。预算充裕时命中片段与 document_name 标注完整注入（Property 1）。
        """
        base = str(base_context or "")
        budget = int(char_budget if char_budget is not None else self._char_budget)

        # 无命中：退回 base 本身，仍受总预算约束（Property 8：输出恒 ≤ budget）
        if not citations:
            return base if len(base) <= budget else base[:budget]

        parts: list[str] = []
        for c in citations:
            label = c.document_name or "知识库文档"
            entry = f"【参照资料：{label}】\n{str(c.snippet or '')}"
            if entry:
                parts.append(entry)

        if not parts:
            return base if len(base) <= budget else base[:budget]

        ref_block = "\n\n".join(parts)
        header = "=== 参照资料（请优先沿用其口径与结构，勿虚构未提供的数字）==="
        if base.strip():
            result = f"{base}\n\n{header}\n{ref_block}"
        else:
            result = f"{header}\n{ref_block}"

        # 总输出超预算 → 整体硬截断到 ≤ char_budget（含 header/base，不溢出，Property 8）
        if len(result) > budget:
            result = result[:budget]
        return result

    def _build_base_context(self, section_title: str, account_name: str) -> str:
        """构造起草叙述的基础 user 上下文（不含数值权威源，仅提示要起草的章节）。"""
        parts = []
        if section_title:
            parts.append(f"附注章节：{str(section_title).strip()}")
        if account_name:
            parts.append(f"相关科目：{str(account_name).strip()}")
        parts.append("请依据下方参照资料起草本章节的中文附注披露文字。")
        return "\n".join(parts)

    # ------------------------------------------------------------------
    # 正文生成 (Req1/4.5/9 / Property 2/13/14/16)
    # ------------------------------------------------------------------
    async def generate_note_text(
        self,
        project_id,
        year,
        note_section,
        section_title: str,
        account_name: str,
        *,
        account_code: str | None = None,
        audit_area: str | None = None,
        user: Any | None = None,
        doc_filter: list[UUID] | list[str] | None = None,
        reference_only: bool = False,
    ) -> GroundedDraft:
        """检索 → 生成 Grounded_Draft。

        - `reference_only=True`：只返回检索片段供人工引用，**不调用 llm_client.chat_completion**
          （text=None, degraded=True, Req4.5/Property 13）。
        - 无命中 → fail-open：text=None, degraded=True（caller 退回通用路径）。
        - 生成用 Narrative_Only system prompt（Req9/Property 14）；中文（Req1.7/Property 16）。
        - 任一环异常 → GroundedDraft(text=None, degraded=True)，不抛（Property 2）。
        """
        try:
            query = self.build_query(section_title, account_name, account_code)
            citations = await self.retrieve(
                project_id,
                query,
                user=user,
                account_code=account_code,
                audit_area=audit_area,
                doc_filter=doc_filter,
            )
        except Exception as e:  # 检索层已 fail-open，此处双保险
            logger.warning("附注 RAG generate_note_text 检索异常，fail-open：%s", e)
            return GroundedDraft(text=None, citations=[], degraded=True)

        # 参照文档模式：不生成，只回检索片段（Property 13）
        if reference_only:
            return GroundedDraft(text=None, citations=citations, degraded=True)

        # 无 RAG 依据 → fail-open，让 caller 退回现有通用 LLM 路径
        if not citations:
            return GroundedDraft(text=None, citations=[], degraded=True)

        try:
            base_context = self._build_base_context(section_title, account_name)
            user_prompt = self.build_grounded_user_prompt(base_context, citations, self._char_budget)
            # context 传 LLM 前值转字符串
            messages = [
                {"role": "system", "content": str(_GROUNDED_SYSTEM_PROMPT_ZH)},
                {"role": "user", "content": str(user_prompt)},
            ]
            text = await chat_completion(messages, temperature=0.3, max_tokens=1500)
        except Exception as e:  # LLM 失败 fail-open
            logger.warning("附注 RAG 生成调用失败，fail-open：%s", e)
            return GroundedDraft(text=None, citations=citations, degraded=True)

        text_str = str(text or "").strip()
        # chat_completion 失败时返回占位串（"[...]" / "⚠️..."），视为降级
        if not text_str or text_str.startswith("[") or text_str.startswith("⚠️"):
            return GroundedDraft(text=None, citations=citations, degraded=True)

        return GroundedDraft(text=text_str, citations=citations, degraded=False)

    # ------------------------------------------------------------------
    # 上年附注知识库回退 (Req2 / Property 4)
    # ------------------------------------------------------------------
    async def retrieve_prior_year_note(
        self,
        project_id,
        note_section,
        section_title: str,
        account_name: str,
        *,
        user: Any | None = None,
    ) -> GroundedDraft | None:
        """上年附注知识库回退：从知识库检索上年审计报告/附注文档片段。

        无命中 → None（caller 继续到 LLM / 模板，Req2.4）。命中 → 以首个片段作为上年来源文字候选，
        citations 标注来源为知识库文档（Property 4）。
        """
        try:
            query = self.build_query(section_title, account_name, None)
            query = f"{query} 上年 上期 附注 审计报告"
            citations = await self.retrieve(project_id, query, user=user)
        except Exception as e:  # fail-open
            logger.warning("附注 RAG 上年回退检索异常，fail-open：%s", e)
            return None

        if not citations:
            return None

        return GroundedDraft(text=citations[0].snippet, citations=citations, degraded=False)

    # ------------------------------------------------------------------
    # 一键批量预填充 (Req10 / Property 12/15)
    # ------------------------------------------------------------------
    @staticmethod
    def _has_substantive_text(section: dict) -> bool:
        """判断章节是否已有实质正文（非空且非草稿标记）。"""
        text = section.get("text_content")
        if section.get("is_draft"):
            return False
        return bool(text and str(text).strip())

    def _should_skip(self, section: dict) -> bool:
        """跳过已有实质正文 / 锁定 / manual_override 的章节（Req10.4/Property 15）。

        锁定标记兼容 `locked` 与 `is_locked` 两种键名（章节 DTO 由上游端点构造，
        不同来源命名不一，二者任一为真即视为锁定）。
        """
        if section.get("locked") or section.get("is_locked"):
            return True
        if section.get("manual_override"):
            return True
        if self._has_substantive_text(section):
            return True
        return False

    async def batch_prefill(
        self,
        project_id,
        year,
        sections: list[dict],
        *,
        user: Any | None = None,
        doc_filter: list[UUID] | list[str] | None = None,
        on_progress: Callable[[int, int, Any], Awaitable[None] | None] | None = None,
    ) -> list[dict]:
        """对空/草稿章节逐个 generate_note_text；单章 try/except 隔离降级（Property 12）。

        返回逐章节 {note_section, status(generated|degraded|skipped), text, citations}。
        跳过已有实质正文/锁定/manual_override 章节（Property 15）。不落库（采纳仍走治理流）。
        """
        results: list[dict] = []
        total = len(sections or [])
        for idx, sec in enumerate(sections or []):
            note_section = sec.get("note_section")

            if self._should_skip(sec):
                results.append(
                    {"note_section": note_section, "status": "skipped", "text": None, "citations": []}
                )
                await self._emit_progress(on_progress, idx + 1, total, note_section)
                continue

            try:
                draft = await self.generate_note_text(
                    project_id,
                    year,
                    note_section,
                    str(sec.get("section_title") or ""),
                    str(sec.get("account_name") or ""),
                    account_code=sec.get("account_code"),
                    audit_area=sec.get("audit_area"),
                    user=user,
                    doc_filter=sec.get("doc_filter") or doc_filter,
                )
                status = "generated" if draft.text else "degraded"
                results.append(
                    {
                        "note_section": note_section,
                        "status": status,
                        "text": draft.text,
                        "citations": draft.citations,
                    }
                )
            except Exception as e:  # 单章隔离降级（Property 12）
                logger.warning("附注批量预填充章节 %s 降级：%s", note_section, e)
                results.append(
                    {"note_section": note_section, "status": "degraded", "text": None, "citations": []}
                )

            await self._emit_progress(on_progress, idx + 1, total, note_section)

        return results

    @staticmethod
    async def _emit_progress(on_progress, done: int, total: int, note_section) -> None:
        """进度回调，支持同步/异步；回调异常不影响批量主流程。"""
        if on_progress is None:
            return
        try:
            res = on_progress(done, total, note_section)
            if hasattr(res, "__await__"):
                await res
        except Exception:  # 进度回调失败不影响生成
            logger.debug("附注批量预填充进度回调异常（忽略）")
