"""b14_ai_generate — B1-4 尽职调查报告 LLM 辅助生成端点

POST /api/projects/{project_id}/b14/chapters/{chapter_id}/ai-generate
  Body: { mode: "generate"|"polish", user_hint, current_content }
  Response: { draft, model, confidence, error }

设计：
- 通过 ReferenceDocService.load_from_knowledge_base 检索知识库文档（最多 3 篇）
- 构造尽调报告专属 system prompt（含 CPA 行业格式规范）
- 注入 project_context + 跨章节摘要 + 知识库参考
- 调用 vLLM 生成并返回
- LLM 服务不可用时返回 503 + error 消息
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.routers.wp_render_strategies._b14_due_diligence import CHAPTERS_META

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects", tags=["b14-ai-generate"])


# ─── 请求/响应模型 ──────────────────────────────────────────────────────────

class B14AiGenerateRequest(BaseModel):
    mode: str = "generate"  # "generate" | "polish"
    user_hint: str = ""
    current_content: str = ""


class B14AiGenerateResponse(BaseModel):
    draft: str | None = None
    model: str | None = None
    confidence: float | None = None
    error: str | None = None


# ─── 章节标题映射 ────────────────────────────────────────────────────────────

_CHAPTER_TITLE_MAP: dict[str, str] = {
    ch["id"]: ch["title"] for ch in CHAPTERS_META
}


# ─── System prompt 模板 ─────────────────────────────────────────────────────

_SYSTEM_PROMPT_TEMPLATE = """你是一位经验丰富的中国注册会计师，专业从事IPO审计尽职调查。你正在撰写尽职调查（预备调查）报告的「{chapter_title}」章节。

格式规范：
- 采用中国CPA行业尽调报告标准格式
- 语言正式、严谨、客观
- 涉及金额使用人民币元/万元/亿元
- 涉及比率保留两位小数
- 引用法规使用全称

项目信息：
- 客户名称：{client_name}
- 所属行业：{industry}
- 报告期间：{audit_period}
- 事务所：{firm_name}"""


# ─── 端点 ────────────────────────────────────────────────────────────────────

@router.post(
    "/{project_id}/b14/chapters/{chapter_id}/ai-generate",
    response_model=B14AiGenerateResponse,
)
async def b14_ai_generate(
    project_id: UUID,
    chapter_id: str,
    body: B14AiGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """为 B1-4 尽调报告指定章节生成 AI 建议稿.

    mode="generate": 从头生成
    mode="polish": 基于 current_content 润色改进
    """
    # 0. 验证 chapter_id
    chapter_title = _CHAPTER_TITLE_MAP.get(chapter_id)
    if not chapter_title:
        raise HTTPException(status_code=400, detail=f"无效的章节 ID: {chapter_id}")

    # 1. 检查 AI 服务开关
    if not settings.WP_AI_SERVICE_ENABLED:
        raise HTTPException(status_code=503, detail="AI 服务未启用")

    # 2. 加载项目上下文
    project_context = await _load_project_context(db, project_id)

    # 3. 加载跨章节摘要（从 checklist_responses）
    cross_chapter_ctx = await _load_cross_chapter_summaries(db, project_id, chapter_id)

    # 4. 检索知识库参考文档（最多 3 篇）
    kb_docs = await _load_knowledge_base_docs(db, project_id, chapter_title)

    # 5. 构造 prompt
    system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(
        chapter_title=chapter_title,
        client_name=project_context.get("client_name", ""),
        industry=project_context.get("industry", ""),
        audit_period=project_context.get("audit_period", ""),
        firm_name=project_context.get("firm_name", "致同会计师事务所（特殊普通合伙）"),
    )

    user_prompt = _build_user_prompt(
        chapter_title=chapter_title,
        mode=body.mode,
        user_hint=body.user_hint,
        current_content=body.current_content,
        cross_chapter_ctx=cross_chapter_ctx,
        kb_docs=kb_docs,
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    # 6. 调用 LLM
    try:
        from app.services.llm_client import chat_completion

        draft = await chat_completion(
            messages=messages,
            temperature=0.4,
            max_tokens=2000,
        )

        # 检测 llm_client 返回的错误标记（熔断/超时/连接失败）
        if isinstance(draft, str) and draft.startswith("["):
            raise HTTPException(status_code=503, detail=draft)

        return B14AiGenerateResponse(
            draft=draft,
            model=settings.DEFAULT_CHAT_MODEL,
            confidence=0.85,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("B1-4 AI 生成失败 (chapter=%s): %s", chapter_id, e, exc_info=True)
        raise HTTPException(status_code=503, detail=f"AI 生成失败: {e}")


# ─── 辅助函数 ────────────────────────────────────────────────────────────────

async def _load_project_context(db: AsyncSession, project_id: UUID) -> dict:
    """从 projects 表加载项目上下文."""
    context = {
        "client_name": "",
        "industry": "",
        "audit_period": "",
        "firm_name": "致同会计师事务所（特殊普通合伙）",
    }
    try:
        result = await db.execute(
            sa_text(
                "SELECT client_name, audit_year, business_category "
                "FROM projects WHERE id = :pid"
            ),
            {"pid": str(project_id)},
        )
        row = result.fetchone()
        if row:
            context["client_name"] = row.client_name or ""
            if row.audit_year:
                context["audit_period"] = f"{row.audit_year}年度"
            context["industry"] = row.business_category or ""
    except Exception as e:  # noqa: BLE001
        logger.warning("B1-4 AI project context 查询失败: %s", e)
    return context


async def _load_cross_chapter_summaries(
    db: AsyncSession, project_id: UUID, target_chapter_id: str
) -> str:
    """加载 B1-4 其他章节内容作为跨章上下文."""
    try:
        # 找到 B1-4 对应的 wp_id
        wp_result = await db.execute(
            sa_text(
                """
                SELECT wp.id FROM working_paper wp
                JOIN wp_index wi ON wi.wp_id = wp.id
                WHERE wi.project_id = :pid AND wi.wp_code = 'B1-4'
                LIMIT 1
                """
            ),
            {"pid": str(project_id)},
        )
        wp_row = wp_result.fetchone()
        if not wp_row:
            return ""

        # 加载所有 b14-ch*-content 和 b14-ch*-{section} 文本
        ch_result = await db.execute(
            sa_text(
                """
                SELECT item_id, remark
                FROM checklist_responses
                WHERE wp_id = :wp_id AND item_id LIKE 'b14-ch%%'
                AND remark IS NOT NULL AND remark != ''
                """
            ),
            {"wp_id": str(wp_row[0])},
        )

        # 按章节号分组，排除当前章节
        target_num = None
        for ch in CHAPTERS_META:
            if ch["id"] == target_chapter_id:
                target_num = ch["number"]
                break

        parts: list[str] = []
        budget = 3000  # 跨章上下文字符预算
        used = 0

        for row in ch_result.fetchall():
            item_id: str = row.item_id
            remark: str = row.remark

            # 跳过当前章节的内容
            if target_num and f"b14-ch{target_num}-" in item_id:
                continue

            snippet = f"[{item_id}] {remark.strip()[:300]}"
            if used + len(snippet) > budget:
                break
            parts.append(snippet)
            used += len(snippet)

        return "\n".join(parts)
    except Exception as e:  # noqa: BLE001
        logger.debug("B1-4 跨章上下文加载失败（非阻塞）: %s", e)
        return ""


async def _load_knowledge_base_docs(
    db: AsyncSession, project_id: UUID, chapter_title: str
) -> list[str]:
    """从知识库检索与当前章节相关的参考文档（最多 3 篇）."""
    try:
        from app.services.reference_doc_service import ReferenceDocService

        docs = await ReferenceDocService.load_from_knowledge_base(
            project_id=project_id,
            category="due_diligence",
            keywords=[chapter_title, "尽职调查", "尽调"],
            max_docs=3,
            db=db,
        )
        return docs
    except Exception as e:  # noqa: BLE001
        logger.debug("B1-4 知识库检索失败（非阻塞）: %s", e)
        return []


def _build_user_prompt(
    *,
    chapter_title: str,
    mode: str,
    user_hint: str,
    current_content: str,
    cross_chapter_ctx: str,
    kb_docs: list[str],
) -> str:
    """构造用户 prompt."""
    parts: list[str] = []

    # 基础指令
    if mode == "generate":
        parts.append(f"请为「{chapter_title}」章节生成完整的尽职调查报告内容。")
    else:
        parts.append(f"请对「{chapter_title}」章节的现有内容进行润色改进。")

    # 用户提示
    if user_hint:
        parts.append(f"\n## 用户补充要求\n{user_hint}")

    # 知识库参考文档
    if kb_docs:
        parts.append("\n## 知识库参考文档")
        for doc in kb_docs:
            parts.append(doc)

    # 跨章节上下文
    if cross_chapter_ctx:
        parts.append(f"\n## 其他章节上下文（确保一致性）\n{cross_chapter_ctx}")

    # polish 模式：附带当前内容
    if mode == "polish" and current_content:
        parts.append(
            f"\n## 当前章节已有内容（请在此基础上润色改进）\n{current_content.strip()}"
            "\n\n## 润色要求\n"
            "请保留原有结构和核心判断，优化文字表述、改善逻辑连贯性、"
            "确保与其他章节结论一致、补充遗漏要点。不要从头重写。"
        )

    return "\n".join(parts)
