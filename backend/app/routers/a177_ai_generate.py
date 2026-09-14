"""A17-7 独立性声明书 — AI 辅助生成 + Docx 双向同步端点

复用 A17-1 模式：项目上下文 + 编制提示 → LLM → 前端填充。
Docx 同步：结构化 ↔ Word 双向回写。
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

router = APIRouter(tags=["a17-7-ai"])


# ─── AI Generate ─────────────────────────────────────────────────────────────


class A177AiGenerateRequest(BaseModel):
    chapter: int
    chapter_title: str
    guidance: str = ""
    variant: str = "team"
    existing_content: str = ""


class A177AiGenerateResponse(BaseModel):
    content: str


_SYSTEM_PROMPT = """你是一位资深注册会计师（CPA），正在协助编制审计底稿 A17-7《审计项目团队成员独立性声明书》。
你需要根据编制提示、项目上下文信息，以及《中国注册会计师职业道德守则》和《质量管理准则》的要求，
生成专业、简洁、可直接使用的独立性声明书内容。

输出要求：
- 语言：中文
- 风格：正式、合规，符合审计底稿格式
- 如需引用具体信息但无法获取，使用 [待填] 占位
- 直接输出正文内容，不要输出标题"""


@router.post("/api/workpapers/{wp_id}/a177/ai-generate")
async def a177_ai_generate(
    wp_id: str,
    body: A177AiGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> A177AiGenerateResponse:
    """A17-7 章节 AI 生成"""
    if not getattr(settings, "WP_AI_SERVICE_ENABLED", True):
        raise HTTPException(503, "AI 服务未启用")

    project_context = await _load_project_context(wp_id, db)

    user_prompt = _build_user_prompt(
        chapter=body.chapter,
        chapter_title=body.chapter_title,
        guidance=body.guidance,
        variant=body.variant,
        project_context=project_context,
    )

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    result = await chat_completion(messages=messages, temperature=0.3, max_tokens=1500)

    if isinstance(result, str) and result.startswith("["):
        return A177AiGenerateResponse(content="")

    return A177AiGenerateResponse(content=result)


def _build_user_prompt(chapter: int, chapter_title: str, guidance: str, variant: str, project_context: dict) -> str:
    parts = [f"## 章节：{chapter_title}\n"]
    if guidance:
        parts.append(f"## 编制提示\n{guidance}\n")
    parts.append(f"## 变体\n{'全员独立性声明' if variant == 'team' else '专委会委员独立性声明'}\n")

    ctx_lines = []
    if project_context.get("client_name"):
        ctx_lines.append(f"客户名称：{project_context['client_name']}")
    if project_context.get("audit_year"):
        ctx_lines.append(f"审计年度：{project_context['audit_year']}年")
    if ctx_lines:
        parts.append("## 项目信息\n" + "\n".join(ctx_lines) + "\n")

    parts.append("请根据编制提示和项目信息生成该章节的专业初稿内容。")
    return "\n".join(parts)


async def _load_project_context(wp_id: str, db: AsyncSession) -> dict:
    import sqlalchemy as sa

    ctx: dict = {"client_name": "", "audit_year": "", "project_id": ""}
    try:
        result = await db.execute(
            sa.text("SELECT p.id, p.client_name, p.audit_year FROM working_paper wp JOIN projects p ON wp.project_id = p.id WHERE wp.id = :wp_id"),
            {"wp_id": wp_id},
        )
        row = result.fetchone()
        if row:
            ctx["project_id"] = str(row.id)
            ctx["client_name"] = row.client_name or ""
            ctx["audit_year"] = str(row.audit_year) if row.audit_year else ""
    except Exception as e:
        logger.warning("A17-7 AI: project context 加载失败: %s", e)
    return ctx


# ─── Docx 双向同步 ──────────────────────────────────────────────────────────


@router.post("/api/workpapers/{wp_id}/a177/generate-docx")
async def a177_generate_docx(
    wp_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """结构化→Word：从 checklist_responses 生成 docx"""
    from app.services.a177_docx_sync import generate_docx
    import sqlalchemy as sa

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
        logger.error("A17-7 generate_docx 失败: %s", e, exc_info=True)
        raise HTTPException(500, f"生成 Word 失败: {str(e)[:200]}")


@router.post("/api/workpapers/{wp_id}/a177/sync-from-docx")
async def a177_sync_from_docx(
    wp_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Word→结构化：从 docx 解析回写 checklist_responses"""
    from app.services.a177_docx_sync import sync_docx_to_responses
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
        return {"ok": True, "synced_items": count}
    except Exception as e:
        logger.error("A17-7 sync_from_docx 失败: %s", e, exc_info=True)
        raise HTTPException(500, f"同步失败: {str(e)[:200]}")
