"""a17_summary — A17-1 重大事项概要 API 路由

GET  /api/a17/chapter-definitions → 返回 16 章定义
GET  /api/a17/applicable-versions?project_id= → 返回适用的 A17-5 版本
POST /api/a17/chapters/{chapter_id}/pull → 拉取指定章节数据
GET  /api/a17/export-word → 导出 Word（或 501 如引擎未就绪）
GET  /api/a17/check-completeness → 完整性检查
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.a17_summary_service import get_chapter_definitions, pull_chapter_data
from app.services.a17_kam_push_service import push_kam_to_report
from app.services.a17_llm_service import a17_llm_service
from app.services.a17_word_exporter import A17WordExporter
from app.services.a17_5_version_selector import get_applicable_versions

router = APIRouter(prefix="/api/a17", tags=["a17-summary"])


@router.get("/chapter-definitions")
async def list_chapter_definitions(
    current_user: User = Depends(get_current_user),
):
    """返回 A17-1 全部章节定义（16 章）"""
    return get_chapter_definitions()


@router.get("/applicable-versions")
async def list_applicable_versions(
    project_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """返回项目适用的 A17-5 核对表版本列表。

    根据 business_category / scenario 判定各版本适用性。
    """
    return await get_applicable_versions(db, project_id)


class PullRequest(BaseModel):
    project_id: UUID
    wp_id: UUID | None = None


@router.post("/chapters/{chapter_id}/pull")
async def pull_chapter(
    chapter_id: str,
    body: PullRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """拉取指定章节的上游数据"""
    return await pull_chapter_data(db, body.project_id, chapter_id)


# ---------------------------------------------------------------------------
# KAM → 审计报告单向 push
# ---------------------------------------------------------------------------


class KamPushRequest(BaseModel):
    project_id: UUID
    wp_id: UUID


class KamPushResponse(BaseModel):
    success: bool
    pushed_count: int
    message: str


@router.post("/kam/push-to-report", response_model=KamPushResponse)
async def push_kam_to_report_endpoint(
    body: KamPushRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """将 A17-2-1 KAM 数据推送至审计报告 KAM 段落（单向覆写）"""
    result = await push_kam_to_report(db, body.project_id, body.wp_id)
    if result["success"]:
        await db.commit()
    return result



# ---------------------------------------------------------------------------
# Word 导出 + 完整性检查
# ---------------------------------------------------------------------------

_exporter = A17WordExporter()


class CompletenessResponse(BaseModel):
    complete: bool
    missing_chapters: list[str] = []
    red_placeholder_chapters: list[str] = []
    blue_guidance_chapters: list[str] = []
    wp_code: str = "A17-1"


@router.get("/check-completeness", response_model=CompletenessResponse)
async def check_completeness(
    project_id: UUID = Query(...),
    wp_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """检查 A17-1 所有必填章节是否完整可导出"""
    return await _exporter.check_completeness(db, project_id, wp_id)


@router.get("/export-word")
async def export_word_endpoint(
    project_id: UUID = Query(...),
    wp_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    """导出 A17-1 为 Word 文档

    如果 docx_template_filler 或模板不可用，返回 501。
    如果完整性检查未通过，返回 400 + 完整性报告。
    """
    # 先做完整性检查（warn but still export）
    report = await _exporter.check_completeness(db, project_id, wp_id)

    try:
        file_bytes = await _exporter.export_word(db, project_id, wp_id)
    except RuntimeError as e:
        raise HTTPException(status_code=501, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导出失败: {e}")

    filename = "A17-1 重大事项概要汇总.docx"
    return Response(
        content=file_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{filename}",
        },
    )


# ---------------------------------------------------------------------------
# AI 辅助生成（A17-plus）
# ---------------------------------------------------------------------------


class ChapterAiGenerateRequest(BaseModel):
    project_id: UUID
    user_hint: str = ""


class KamAiGenerateRequest(BaseModel):
    project_id: UUID
    kam_title: str
    user_hint: str = ""
    wp_refs: str = ""


class AiGenerateResponse(BaseModel):
    draft: str | None = None
    model: str | None = None
    confidence: float | None = None
    error: str | None = None


@router.post("/chapters/{chapter_id}/ai-generate", response_model=AiGenerateResponse)
async def ai_generate_chapter(
    chapter_id: str,
    body: ChapterAiGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """为指定章节生成 AI 建议稿（A17-plus）"""
    result = await a17_llm_service.generate_chapter_draft(
        db,
        body.project_id,
        chapter_id,
        user_hint=body.user_hint,
    )
    return result


@router.post("/kam/{item_id}/ai-generate", response_model=AiGenerateResponse)
async def ai_generate_kam(
    item_id: str,
    body: KamAiGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """为 KAM 条目生成三要素描述建议稿（A17-plus）"""
    result = await a17_llm_service.generate_kam_description(
        db,
        body.project_id,
        body.kam_title,
        user_hint=body.user_hint,
        wp_refs=body.wp_refs,
    )
    return result
