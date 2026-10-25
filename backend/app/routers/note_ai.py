"""附注 LLM 辅助 API

Phase 9 Task 9.29
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user, require_project_access
from app.models.core import User

router = APIRouter(prefix="/api/disclosure-notes", tags=["note-ai"])


class PolicyGenerateRequest(BaseModel):
    section_number: str
    template_type: str = "soe"
    industry: str | None = None
    year: int = 2025


class AnalysisGenerateRequest(BaseModel):
    section_number: str
    current_data: dict | None = None
    prior_data: dict | None = None
    year: int = 2025


#: 与前端「📚 知识库」选择器的 maxSelect 一致
_MAX_KNOWLEDGE_DOCS = 5


class RewriteRequest(BaseModel):
    """改写请求"""
    text: str
    instruction: str = "请改写以下文本，使其更加专业规范"
    section_number: str = ""
    year: int = 2025
    #: 用户点选的知识文档 ID（服务端逐篇判权后读正文；不接受前端拼好的正文）
    knowledge_doc_ids: list[UUID] = Field(default_factory=list, max_length=_MAX_KNOWLEDGE_DOCS)


class ContinueWriteRequest(BaseModel):
    """续写请求"""
    text: str
    section_number: str = ""
    year: int = 2025
    #: 同 ``RewriteRequest.knowledge_doc_ids``
    knowledge_doc_ids: list[UUID] = Field(default_factory=list, max_length=_MAX_KNOWLEDGE_DOCS)


@router.post("/{project_id}/ai/generate-policy")
async def generate_policy(
    project_id: UUID,
    data: PolicyGenerateRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """会计政策自动生成（接入 vLLM + RAG 参照上年附注）"""
    from app.services.llm_client import chat_completion
    from app.services.reference_doc_service import ReferenceDocService

    # RAG: 加载上年同章节附注作为参照
    context_docs = await ReferenceDocService.load_context(
        db, project_id, data.year,
        source_type="prior_year_notes",
        section_hint=data.section_number,
    )

    prompt = f"请为{data.template_type}版附注的「{data.section_number}」章节生成标准会计政策文本。行业：{data.industry or '一般企业'}。要求简洁专业，符合中国企业会计准则。"
    try:
        text = await chat_completion(
            [
                {"role": "system", "content": "你是审计附注编写专家，请生成标准会计政策文本。如有参照文档请参考其格式和内容。"},
                {"role": "user", "content": prompt},
            ],
            max_tokens=1500,
            context_documents=context_docs if context_docs else None,
        )
    except Exception:
        text = f"根据{data.template_type}模版，{data.section_number}章节的标准会计政策文本。（LLM 服务暂不可用）"
    return {"section_number": data.section_number, "generated_text": text, "source": "llm", "reference_count": len(context_docs)}


@router.post("/{project_id}/ai/generate-analysis")
async def generate_analysis(
    project_id: UUID,
    data: AnalysisGenerateRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """变动分析自动生成（接入 vLLM + RAG 参照上年附注）"""
    from app.services.llm_client import chat_completion
    from app.services.reference_doc_service import ReferenceDocService
    from app.services.export_mask_service import export_mask_service

    context_docs = await ReferenceDocService.load_context(
        db, project_id, data.year,
        source_type="prior_year_notes",
        section_hint=data.section_number,
    )

    # AI 脱敏前置过滤（R4 需求 2 / R8-S1 Task 36）
    masked_current, _m1 = export_mask_service.mask_context(data.current_data)
    masked_prior, _m2 = export_mask_service.mask_context(data.prior_data)

    prompt = f"附注章节「{data.section_number}」，本期数据：{masked_current}，上期数据：{masked_prior}。请用一段话分析变动原因。"
    try:
        text = await chat_completion([
            {"role": "system", "content": "你是审计分析师，请分析附注数据变动原因，语言简洁专业。如有上年参照请对比分析。"},
            {"role": "user", "content": prompt},
        ], max_tokens=500, context_documents=context_docs if context_docs else None)
    except Exception:
        text = "本期余额较上期变动，主要系...（LLM 服务暂不可用）"
    return {"section_number": data.section_number, "generated_text": text, "source": "llm", "reference_count": len(context_docs)}


@router.post("/{project_id}/ai/check-completeness")
async def check_completeness(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """披露完整性检查（接入 vLLM + RAG 参照知识库准则）"""
    from app.services.llm_client import chat_completion
    from app.services.reference_doc_service import ReferenceDocService

    context_docs = await ReferenceDocService.load_context(
        db, project_id, 2025,
        source_type="knowledge_base",
        knowledge_category="accounting_standards",
        knowledge_keywords=["披露", "附注", "准则"],
    )

    try:
        text = await chat_completion([
            {"role": "system", "content": "你是审计附注审核专家。请检查附注是否遗漏必要披露事项（关联方交易、或有事项、日后事项等）。"},
            {"role": "user", "content": "请列出常见的必要披露事项清单，并标注是否可能遗漏。"},
        ], max_tokens=800, context_documents=context_docs if context_docs else None)
        return {"missing_sections": [], "suggestions": [text], "reference_count": len(context_docs)}
    except Exception:
        return {"missing_sections": [], "suggestions": ["LLM 服务暂不可用"], "reference_count": 0}


@router.post("/{project_id}/ai/check-expression")
async def check_expression(
    project_id: UUID,
    section_number: str = Query(...),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """表述规范性检查（接入 vLLM）"""
    return {"section_number": section_number, "issues": [], "message": "表述规范检查需要提供具体文本内容"}


#: 用户点选的知识文档注入 LLM 的总字数预算（按篇均分）。``chat_completion`` 对全部参照文档
#: 合计截断 8000 字：若每篇各给 4000，第 3 篇起会被截断整篇丢掉，而 ``knowledge_count`` 仍把它
#: 算作「已参考」—— 均分让用户选的每一篇都真的进上下文，剩余约 2000 字留给上年附注。
_KNOWLEDGE_BUDGET_CHARS = 6000


async def _load_selected_knowledge(
    db: AsyncSession, project_id: UUID, user: User, doc_ids: list[UUID]
) -> list[str]:
    """用户在「📚 知识库」里点选的文档 → LLM 参照文本（按 ID 逐篇过单一判定面）。

    spec knowledge-upload-robustness-and-consumer-wiring R6.2：
      * 只接受文档 ID、不接受前端拼好的正文（客户端文本不可信，可伪造成任意提示词注入）；
      * ``load_documents`` 以 project 模式逐篇判定（当前用户可读 ∩ 当前项目范围），
        不可见 / 已删除的静默跳过，不暴露存在性；读失败返回空（fail-closed）；
      * 正文为空的文档（扫描件等）不计入，``knowledge_count`` 只数真正注入的篇数。
    """
    if not doc_ids:
        return []
    from app.services.knowledge_index_service import KnowledgeIndexService

    docs = await KnowledgeIndexService(db).load_documents(doc_ids, user=user, project_id=project_id)
    usable = [d for d in docs if (d.get("content") or "").strip()]
    if not usable:
        return []
    per_doc = max(500, _KNOWLEDGE_BUDGET_CHARS // len(usable))
    return [
        f"【知识库 - {d.get('document_name') or d.get('source_id')}】\n{d['content'].strip()[:per_doc]}"
        for d in usable
    ]


@router.post("/{project_id}/ai/complete")
async def ai_complete(
    project_id: UUID,
    data: ContinueWriteRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("readonly")),
):
    """智能续写（POST body，接入 vLLM + RAG：用户点选的知识文档 + 上年附注）。

    🔴 此前本路径注册了两次：先注册的 query 参数版（``section_number`` 必填查询参数、
    年度写死 2025）遮蔽了本函数，前端按 JSON body 调用恒 422 —— 续写功能从未可用。
    已删除 query 版（spec knowledge-upload-robustness-and-consumer-wiring R6.3）。
    鉴权与同业务域 ``ai-fill`` 一致：项目 readonly 即可（不落库）。
    """
    from app.services.llm_client import chat_completion
    from app.services.reference_doc_service import ReferenceDocService
    from app.services.export_mask_service import export_mask_service

    knowledge_docs = await _load_selected_knowledge(db, project_id, user, data.knowledge_doc_ids)
    prior_docs = await ReferenceDocService.load_context(
        db, project_id, data.year,
        source_type="prior_year_notes",
        section_hint=data.section_number,
    )
    # 用户点选的资料在前：总长截断时优先保留
    context_docs = knowledge_docs + prior_docs

    # AI 脱敏前置过滤（R4 需求 2 / R8-S1 Task 36）
    masked_text, _mapping = export_mask_service.mask_text(data.text)

    try:
        text = await chat_completion([
            {"role": "system", "content": "你是审计附注编写助手。请续写以下文本，保持专业风格，语言简洁。参考上年附注的表述风格。只输出续写部分，不要重复已有内容。"},
            {"role": "user", "content": f"请续写以下内容：\n\n{masked_text}"},
        ], max_tokens=500, context_documents=context_docs if context_docs else None)
        return {
            "result": data.text + text,
            "appended": text,
            "reference_count": len(context_docs),
            "knowledge_count": len(knowledge_docs),
        }
    except Exception:
        return {
            "result": data.text,
            "appended": "",
            "error": "LLM 服务暂不可用",
            "reference_count": 0,
            "knowledge_count": 0,
        }


@router.post("/{project_id}/ai/rewrite")
async def ai_rewrite(
    project_id: UUID,
    data: RewriteRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("readonly")),
):
    """改写选中文本（接入 vLLM + RAG：用户点选的知识文档 + 上年附注）。"""
    from app.services.llm_client import chat_completion
    from app.services.reference_doc_service import ReferenceDocService
    from app.services.export_mask_service import export_mask_service

    knowledge_docs = await _load_selected_knowledge(db, project_id, user, data.knowledge_doc_ids)
    prior_docs = await ReferenceDocService.load_context(
        db, project_id, data.year,
        source_type="prior_year_notes",
        section_hint=data.section_number,
    )
    context_docs = knowledge_docs + prior_docs

    # AI 脱敏前置过滤（R4 需求 2 / R8-S1 Task 36）
    masked_text, _mapping = export_mask_service.mask_text(data.text)

    try:
        text = await chat_completion([
            {"role": "system", "content": "你是审计附注编写专家。请按照用户指令改写文本，保持专业审计语言风格，符合中国企业会计准则表述规范。只输出改写后的文本，不要解释。"},
            {"role": "user", "content": f"指令：{data.instruction}\n\n原文：\n{masked_text}"},
        ], max_tokens=1000, context_documents=context_docs if context_docs else None)
        return {
            "original": data.text,
            "rewritten": text,
            "reference_count": len(context_docs),
            "knowledge_count": len(knowledge_docs),
        }
    except Exception:
        return {
            "original": data.text,
            "rewritten": data.text,
            "error": "LLM 服务暂不可用",
            "reference_count": 0,
            "knowledge_count": 0,
        }
