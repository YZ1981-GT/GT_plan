"""a17_summary — A17-1 重大事项概要 API 路由

GET  /api/a17/chapter-definitions → 返回 16 章定义
GET  /api/a17/applicable-versions?project_id= → 返回适用的 A17-5 版本
POST /api/a17/chapters/{chapter_id}/pull → 拉取指定章节数据
GET  /api/a17/export-word → 导出 Word（或 501 如引擎未就绪）
GET  /api/a17/check-completeness → 完整性检查
"""

from uuid import UUID

from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.a17_summary_service import get_chapter_definitions, pull_chapter_data
from app.services.a17_consistency_checker import check_consistency, ConsistencyResult
from app.services.a17_kam_push_service import push_kam_to_report
from app.services.a17_llm_service import a17_llm_service
from app.services.a17_word_exporter import A17WordExporter
from app.services.a17_5_version_selector import get_applicable_versions
from app.services.review_checklist_service import get_review_sign_hints_by_preset

router = APIRouter(prefix="/api/a17", tags=["a17-summary"])


# ---------------------------------------------------------------------------
# A17 子文档定义（A17-2 ~ A17-7）
# ---------------------------------------------------------------------------

_SUB_DOC_DEFINITIONS: list[dict[str, str]] = [
    {"wp_code": "A17-2", "label": "KAM"},
    {"wp_code": "A17-3", "label": "业务咨询"},
    {"wp_code": "A17-4", "label": "分歧记录"},
    {"wp_code": "A17-5", "label": "完成核对表"},
    {"wp_code": "A17-6", "label": "总结会"},
    {"wp_code": "A17-7", "label": "独立性声明"},
]


@router.get("/chapter-definitions")
async def list_chapter_definitions(
    current_user: User = Depends(get_current_user),
):
    """返回 A17-1 全部章节定义（16 章）"""
    return get_chapter_definitions()


class SubDocItem(BaseModel):
    wp_code: str
    label: str
    exists: bool
    wp_id: str | None = None


@router.get("/sub-documents", response_model=list[SubDocItem])
async def list_sub_documents(
    project_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """查询项目 wp_index 中 A17-2 ~ A17-7 的存在状态。

    返回 SubDocItem[]，标识各子文档是否已创建。
    """
    from sqlalchemy import text as sa_text

    # 查询项目中所有 A17-x 的 wp_index 记录
    result = await db.execute(
        sa_text(
            """
            SELECT wp_code, wp_id
            FROM wp_index
            WHERE project_id = :pid
              AND wp_code IN ('A17-2', 'A17-3', 'A17-4', 'A17-5', 'A17-6', 'A17-7')
            """
        ),
        {"pid": str(project_id)},
    )
    existing_map: dict[str, str] = {}
    for row in result.fetchall():
        existing_map[row.wp_code] = str(row.wp_id)

    items: list[SubDocItem] = []
    for defn in _SUB_DOC_DEFINITIONS:
        wp_code = defn["wp_code"]
        wp_id = existing_map.get(wp_code)
        items.append(SubDocItem(
            wp_code=wp_code,
            label=defn["label"],
            exists=wp_id is not None,
            wp_id=wp_id,
        ))
    return items


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


@router.get("/review-sign-hints")
async def list_review_sign_hints(
    project_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """A17-5 核对项 preset A22/A23/A24/A25 → 读 A21~A25 子码 -sign 状态。"""
    return await get_review_sign_hints_by_preset(db, project_id)


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
# 跨章节一致性校验
# ---------------------------------------------------------------------------


class ConsistencyCheckRequest(BaseModel):
    project_id: UUID
    wp_id: UUID


class ConsistencyResultItem(BaseModel):
    rule_id: str
    severity: str
    affected_chapters: list[str]
    description: str


class ConsistencyCheckResponse(BaseModel):
    results: list[ConsistencyResultItem]
    checked_at: str


@router.post("/consistency-check", response_model=ConsistencyCheckResponse)
async def consistency_check(
    body: ConsistencyCheckRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """跨章节一致性校验：检查 A17-1 各章节结论之间的逻辑一致性"""
    from datetime import datetime, timezone
    from sqlalchemy import text as sa_text

    # 查询 16 章内容
    result = await db.execute(
        sa_text(
            """
            SELECT item_id, remark
            FROM checklist_responses
            WHERE wp_id = :wp_id
              AND item_id LIKE 'A17-1-ch%%'
            """
        ),
        {"wp_id": str(body.wp_id)},
    )
    rows = result.fetchall()
    chapters: dict[str, str | None] = {}
    for row in rows:
        chapters[row.item_id] = row.remark

    # 查询 project.business_category
    from app.models.core import Project as ProjectModel

    proj_result = await db.execute(
        sa_text(
            "SELECT business_category FROM project WHERE id = :pid"
        ),
        {"pid": str(body.project_id)},
    )
    proj_row = proj_result.fetchone()
    business_category = proj_row.business_category if proj_row else None

    # 执行校验
    check_results = check_consistency(chapters, business_category)

    return ConsistencyCheckResponse(
        results=[
            ConsistencyResultItem(**r.to_dict()) for r in check_results
        ],
        checked_at=datetime.now(timezone.utc).isoformat(),
    )


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
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
        },
    )


# ---------------------------------------------------------------------------
# AI 辅助生成（A17-plus）
# ---------------------------------------------------------------------------


class ChapterAiGenerateRequest(BaseModel):
    project_id: UUID
    user_hint: str = ""
    mode: str = "generate"  # "generate" | "polish"


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
    """为指定章节生成 AI 建议稿（A17-plus）

    mode="generate": 从头生成（不含当前章节内容）
    mode="polish": 润色改进（prompt 包含当前章节内容）
    始终包含跨章上下文。
    """
    from sqlalchemy import text as sa_text

    # 查询所有章节内容用于跨章上下文
    # 先找 wp_id：通过 wp_index 查 A17-1 对应的 wp_id
    wp_result = await db.execute(
        sa_text(
            """
            SELECT wp.id FROM working_paper wp
            JOIN wp_index wi ON wi.wp_id = wp.id
            WHERE wi.project_id = :pid AND wi.wp_code = 'A17-1'
            LIMIT 1
            """
        ),
        {"pid": str(body.project_id)},
    )
    wp_row = wp_result.fetchone()

    all_chapters: dict[str, str] = {}
    current_content = ""
    if wp_row:
        ch_result = await db.execute(
            sa_text(
                """
                SELECT item_id, remark
                FROM checklist_responses
                WHERE wp_id = :wp_id AND item_id LIKE 'A17-1-ch%%'
                """
            ),
            {"wp_id": str(wp_row[0])},
        )
        for row in ch_result.fetchall():
            content = row.remark or ""
            all_chapters[row.item_id] = content
            if row.item_id == chapter_id:
                current_content = content

    result = await a17_llm_service.generate_chapter_draft(
        db,
        body.project_id,
        chapter_id,
        user_hint=body.user_hint,
        mode=body.mode,
        current_content=current_content,
        all_chapters=all_chapters,
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
