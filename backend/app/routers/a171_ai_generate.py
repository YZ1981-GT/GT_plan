"""A17-1 重大事项概要汇总 — AI 章节生成端点

按 B14 模式：加载项目上下文 + 知识库文档 → 构造 prompt → 调 LLM。
支持用户指定知识库文档 IDs 作为参考。
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.llm_client import chat_completion

logger = logging.getLogger(__name__)

router = APIRouter(tags=["a17-1-ai"])


class A171AiGenerateRequest(BaseModel):
    chapter: int
    chapter_title: str
    guidance: str = ""
    existing_content: str = ""
    knowledge_doc_ids: list[str] = []


class A171AiGenerateResponse(BaseModel):
    content: str
    sources: list[str] = []


_SYSTEM_PROMPT = """你是一位资深注册会计师（CPA），正在协助编制审计底稿 A17-1《重大事项概要汇总》。
你需要根据编制提示（源自审计底稿模板的蓝色字体指导内容）、项目知识库中的参考资料，
以及中国审计准则（CAS）要求，生成专业、简洁、可直接使用的审计底稿章节内容。

输出要求：
- 语言：中文
- 风格：审计专业用语，客观陈述事实和结论
- 如需引用具体数据但无法获取，使用 [待填] 占位
- 不要输出标题（标题已由系统生成）
- 直接输出正文内容"""


@router.post("/api/workpapers/{wp_id}/a171/ai-generate")
async def a171_ai_generate(
    wp_id: str,
    body: A171AiGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> A171AiGenerateResponse:
    """A17-1 章节 AI 生成"""

    if not getattr(settings, "WP_AI_SERVICE_ENABLED", True):
        raise HTTPException(503, "AI 服务未启用")

    # 1. 加载项目上下文（项目以底稿自身所属项目为准；router 级 dedicated_wp_gate 已校验可访问该底稿）
    project_context = await _load_project_context(wp_id, db)
    project_uuid = _parse_uuid(project_context.get("project_id"))

    # 2. 加载知识库文档（用户指定 or 自动检索）；均按「当前用户 ∩ 底稿所属项目」判定可见性
    kb_texts: list[str] = []
    sources: list[str] = []
    if body.knowledge_doc_ids:
        kb_texts, sources = await _load_selected_kb_docs(
            body.knowledge_doc_ids, project_uuid, current_user, db
        )
    else:
        kb_texts, sources = await _load_auto_kb_docs(
            project_uuid, body.chapter_title, current_user, db
        )

    # 3. 构造 user prompt
    user_prompt = _build_user_prompt(
        chapter=body.chapter,
        chapter_title=body.chapter_title,
        guidance=body.guidance,
        existing_content=body.existing_content,
        project_context=project_context,
    )

    # 4. 调用 LLM
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    result = await chat_completion(
        messages=messages,
        temperature=0.3,
        max_tokens=2000,
        context_documents=kb_texts if kb_texts else None,
    )

    # 5. 检查降级标记
    if isinstance(result, str) and result.startswith("["):
        # LLM 服务降级 — 返回友好消息而非 503
        return A171AiGenerateResponse(content="", sources=[])

    return A171AiGenerateResponse(content=result, sources=sources)


def _build_user_prompt(
    chapter: int,
    chapter_title: str,
    guidance: str,
    existing_content: str,
    project_context: dict,
) -> str:
    parts = [f"## 章节：{chapter_title}\n"]

    if guidance:
        parts.append(f"## 编制提示\n{guidance}\n")

    ctx_lines = []
    if project_context.get("client_name"):
        ctx_lines.append(f"客户名称：{project_context['client_name']}")
    if project_context.get("audit_year"):
        ctx_lines.append(f"审计年度：{project_context['audit_year']}年")
    if project_context.get("audit_period"):
        ctx_lines.append(f"审计期间：{project_context['audit_period']}")
    if project_context.get("business_category"):
        ctx_lines.append(f"业务类别：{project_context['business_category']}")
    if project_context.get("report_scope"):
        scope_map = {"standalone": "单体财务报表", "consolidated": "合并及母公司财务报表"}
        ctx_lines.append(f"报告范围：{scope_map.get(project_context['report_scope'], project_context['report_scope'])}")
    if ctx_lines:
        parts.append("## 项目信息\n" + "\n".join(ctx_lines) + "\n")
        parts.append("请在生成内容中直接使用上述项目信息替换占位符，不要使用[待填]。\n")

    if existing_content:
        parts.append(f"## 已有内容（请补充完善）\n{existing_content[:2000]}\n")
        parts.append("请基于编制提示和参考资料，补充完善上述已有内容。保留合理部分，纠正不当表述。")
    else:
        parts.append("请根据编制提示和参考资料生成该章节的专业初稿内容。")

    return "\n".join(parts)


async def _load_project_context(wp_id: str, db: AsyncSession) -> dict:
    """从 working_paper → project 获取上下文"""
    import sqlalchemy as sa

    ctx: dict = {
        "project_id": "",
        "client_name": "",
        "audit_period": "",
        "audit_year": "",
        "business_category": "",
        "report_scope": "",
    }
    try:
        result = await db.execute(
            sa.text("""
                SELECT p.id, p.client_name, p.audit_year, p.business_category,
                       p.report_scope
                FROM working_paper wp
                JOIN projects p ON wp.project_id = p.id
                WHERE wp.id = :wp_id
            """),
            {"wp_id": wp_id},
        )
        row = result.fetchone()
        if row:
            ctx["project_id"] = str(row.id)
            ctx["client_name"] = row.client_name or ""
            ctx["audit_year"] = str(row.audit_year) if row.audit_year else ""
            ctx["audit_period"] = f"{row.audit_year}年度" if row.audit_year else ""
            ctx["business_category"] = row.business_category or ""
            ctx["report_scope"] = getattr(row, "report_scope", "") or ""
    except Exception as e:
        logger.warning("A17-1 AI: project context 加载失败: %s", e)
    return ctx


#: 用户点名参考文档：最多读取的 ID 数 / 进入提示词的篇数 / 每篇字数
_SELECTED_DOC_ID_CAP = 20
_SELECTED_DOC_LIMIT = 5
_DOC_CHAR_LIMIT = 4000


def _parse_uuid(value) -> UUID | None:
    try:
        return UUID(str(value)) if value else None
    except (ValueError, TypeError):
        return None


async def _load_selected_kb_docs(
    doc_ids: list[str], project_id: UUID | None, user, db: AsyncSession
) -> tuple[list[str], list[str]]:
    """加载用户在界面上点名的知识库文档（如 A17-3 上传的咨询附件）。

    🔴 旧实现查遗留表 ``ai_knowledge_base`` 的 ``title`` / ``content`` —— 该表没有这两列、
    也没有任何写入方，SQL 恒失败被吞成空 ⇒ 点名的文档从未进入 AI 生成（spec
    knowledge-base-retrieval-and-authz-closure 5.6）。现改读 ``knowledge_documents``，
    每篇过单一判定面（当前用户 ∩ 底稿所属项目）；客户端传来的 ID 不可信，
    不可见 / 已删除的静默跳过（不暴露存在性）。
    """
    if project_id is None or not doc_ids:
        return [], []
    try:
        from app.services.knowledge_index_service import KnowledgeIndexService

        docs = await KnowledgeIndexService(db).load_documents(
            doc_ids[:_SELECTED_DOC_ID_CAP], user=user, project_id=project_id
        )
    except Exception as e:  # noqa: BLE001 - 参考资料缺失不阻断生成
        logger.warning("A17-1 AI: 加载指定知识库文档失败（降级为无参考）: %s", e)
        return [], []
    texts: list[str] = []
    sources: list[str] = []
    for doc in docs:
        content = doc.get("content") or ""
        if not content:
            continue
        texts.append(content[:_DOC_CHAR_LIMIT])
        sources.append(doc.get("document_name") or doc["source_id"])
        if len(texts) >= _SELECTED_DOC_LIMIT:
            break
    return texts, sources


async def _load_auto_kb_docs(
    project_id: UUID | None, chapter_title: str, user, db: AsyncSession
) -> tuple[list[str], list[str]]:
    """按章节标题自动检索知识库（文档正文词法 + 可用时的向量；来源名取 document_name）。"""
    if project_id is None:
        return [], []
    try:
        from app.services.reference_doc_service import ReferenceDocService

        docs = await ReferenceDocService.search_knowledge_base(
            project_id,
            keywords=[chapter_title, "审计", "CAS"],
            category="audit_standards",
            max_docs=3,
            db=db,
            user=user,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("A17-1 AI: 自动检索KB失败 (降级为无参考): %s", e)
        return [], []
    texts: list[str] = []
    sources: list[str] = []
    for doc in docs:
        content = doc.get("content") or ""
        if content:
            texts.append(content[:_DOC_CHAR_LIMIT])
            sources.append(doc.get("document_name") or "知识库文档")
    return texts, sources


# ---------------------------------------------------------------------------
# A17-1 Docx 双向同步端点
# ---------------------------------------------------------------------------


@router.post("/api/workpapers/{wp_id}/a171/generate-docx")
async def a171_generate_docx(
    wp_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """结构化→Word：从 checklist_responses 生成 docx 文件，返回 onlyoffice-config 所需信息"""
    from app.services.a171_docx_sync import generate_docx
    import sqlalchemy as sa

    # 获取 project_id
    row = await db.execute(
        sa.text("SELECT project_id FROM working_paper WHERE id = :wid LIMIT 1"),
        {"wid": wp_id},
    )
    pid = row.scalar_one_or_none()
    if not pid:
        raise HTTPException(404, "底稿不存在")

    try:
        file_path = await generate_docx(UUID(wp_id), pid, db)
        return {"ok": True, "file_path": str(file_path)}
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        logger.error("A17-1 generate_docx 失败: %s", e, exc_info=True)
        raise HTTPException(500, f"生成 Word 失败: {str(e)[:200]}")


@router.post("/api/workpapers/{wp_id}/a171/sync-from-docx")
async def a171_sync_from_docx(
    wp_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Word→结构化：从项目存储的 docx 解析内容回写到 checklist_responses"""
    from app.services.a171_docx_sync import sync_docx_to_responses
    import sqlalchemy as sa

    row = await db.execute(
        sa.text("SELECT project_id FROM working_paper WHERE id = :wid LIMIT 1"),
        {"wid": wp_id},
    )
    pid = row.scalar_one_or_none()
    if not pid:
        raise HTTPException(404, "底稿不存在")

    try:
        count = await sync_docx_to_responses(UUID(wp_id), pid, db, current_user.id)
        return {"ok": True, "synced_chapters": count}
    except Exception as e:
        logger.error("A17-1 sync_from_docx 失败: %s", e, exc_info=True)
        raise HTTPException(500, f"同步失败: {str(e)[:200]}")
