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
from app.services.a17_kam_push_service import push_kam_to_report, check_kam_stale
from app.services.a17_independence_drift import (
    check_independence_drift,
    import_b3_periods_to_a177,
)
from app.services.a176_agenda_prefill import build_agenda_prefill
from app.services.a17_upstream_stale_service import check_chapter_stale, check_agenda_stale
from app.services.a17_partner_summary_service import (
    get_partner_summary,
    get_report_date_timeline,
)
from app.services.a17_signoff_self_check import (
    get_cross_alerts,
    get_signoff_self_check,
)
from app.services.a17_llm_service import a17_llm_service
from app.services.a17_word_exporter import A17WordExporter
from app.services.a17_5_version_selector import get_applicable_versions
from app.services.review_checklist_service import get_review_sign_hints_by_preset

router = APIRouter(prefix="/api/a17", tags=["a17-summary"])


# ---------------------------------------------------------------------------
# A17 子文档定义（A17-2 ~ A17-7）
# ---------------------------------------------------------------------------

_SUB_DOC_DEFINITIONS: list[dict[str, str]] = [
    {"wp_code": "A17-2-1", "label": "KAM"},
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
    """查询项目 wp_index 中 A17-2-1 ~ A17-7 的存在状态。

    返回 SubDocItem[]，标识各子文档是否已创建。
    A17-5：任一 A17-5-* 分册存在即视为可用。
    """
    from sqlalchemy import text as sa_text

    # 查询项目中所有 A17-x 的 wp_index 记录（含 A17-2-1、A17-5-*）
    result = await db.execute(
        sa_text(
            """
            -- wp_index 无 wp_id 列；wp_id 须经 working_paper.wp_index_id 反查
            SELECT wi.wp_code, wp.id AS wp_id
            FROM wp_index wi
            LEFT JOIN working_paper wp ON wp.wp_index_id = wi.id
            WHERE wi.project_id = :pid
              AND wi.wp_code LIKE 'A17-%'
              AND wi.wp_code <> 'A17-1'
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
        if wp_code == "A17-5":
            child = next(
                ((c, wid) for c, wid in existing_map.items() if c.startswith("A17-5")),
                None,
            )
            items.append(SubDocItem(
                wp_code=wp_code,
                label=defn["label"],
                exists=child is not None,
                wp_id=child[1] if child else None,
            ))
        else:
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


class KamStaleResponse(BaseModel):
    stale: bool
    message: str
    source_hash: str | None = None
    report_hash: str | None = None


@router.get("/kam/stale-check", response_model=KamStaleResponse)
async def kam_stale_check(
    project_id: UUID = Query(...),
    wp_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """检测 A17-2-1 KAM 与审计报告 KAM 段落是否同步"""
    return await check_kam_stale(db, project_id, wp_id)


class IndependenceDriftResponse(BaseModel):
    has_drift: bool
    message: str
    a177: dict
    b3: dict


@router.get("/independence-drift", response_model=IndependenceDriftResponse)
async def independence_drift_check(
    project_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """检测 A17-7 与 B3 独立性期间字段是否一致"""
    return await check_independence_drift(db, project_id)


class AgendaPrefillResponse(BaseModel):
    agenda: dict[str, str]


@router.get("/a176/agenda-prefill", response_model=AgendaPrefillResponse)
async def a176_agenda_prefill(
    project_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """为 A17-6 总结会议程提供自动预填建议"""
    agenda = await build_agenda_prefill(db, project_id)
    return AgendaPrefillResponse(agenda=agenda)


@router.get("/chapters/stale-check")
async def chapters_stale_check(
    project_id: UUID = Query(...),
    wp_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """A17-1 各章相对上游底稿是否过期"""
    return await check_chapter_stale(db, project_id, wp_id)


@router.get("/a176/agenda-stale-check")
async def agenda_stale_check(
    project_id: UUID = Query(...),
    wp_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """A17-6 议程相对上游是否过期"""
    return await check_agenda_stale(db, project_id, wp_id)


@router.get("/report-date-timeline")
async def report_date_timeline(
    project_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """总结会 / 独立性签署 / 审计报告日时间轴"""
    return await get_report_date_timeline(db, project_id)


@router.get("/partner-summary")
async def partner_summary(
    project_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """合伙人/EQCR 一页摘要"""
    return await get_partner_summary(db, project_id)


@router.get("/cross-alerts")
async def a17_cross_alerts(
    project_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """A13 超重要性 / A10-1 未沟通 联动告警"""
    return await get_cross_alerts(db, project_id)


@router.get("/signoff-self-check")
async def a17_signoff_self_check(
    project_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """归档/签发前自检（含跨底稿联动）"""
    return await get_signoff_self_check(db, project_id)


class ImportB3PeriodsRequest(BaseModel):
    project_id: UUID
    wp_id: UUID
    overwrite: bool = False


@router.post("/independence/import-b3-periods")
async def independence_import_b3_periods(
    body: ImportB3PeriodsRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """从 B3 导入独立性期间字段到 A17-7"""
    result = await import_b3_periods_to_a177(
        db,
        body.project_id,
        body.wp_id,
        current_user.id,
        overwrite=body.overwrite,
    )
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
    """跨章节一致性校验：检查 A17-1 各章节结论之间的逻辑一致性。

    同时读取 A17-7 签署状态、A17-3/A17-3-1 成对状态作为跨底稿上下文。
    兼容 a171-ch*（GtA171AuditSummary）与旧版 A17-1-ch* item_id。
    """
    from datetime import datetime, timezone
    from sqlalchemy import text as sa_text

    chapters = await _load_a171_chapters_for_consistency(db, body.wp_id)
    context = await _load_a17_cross_doc_context(db, body.project_id)

    proj_result = await db.execute(
        sa_text("SELECT business_category FROM projects WHERE id = :pid"),
        {"pid": str(body.project_id)},
    )
    proj_row = proj_result.fetchone()
    business_category = proj_row.business_category if proj_row else None

    check_results = check_consistency(chapters, business_category, context)

    return ConsistencyCheckResponse(
        results=[ConsistencyResultItem(**r.to_dict()) for r in check_results],
        checked_at=datetime.now(timezone.utc).isoformat(),
    )


async def _load_a171_chapters_for_consistency(db, wp_id) -> dict[str, str | None]:
    """从 checklist_responses 组装 A17-1-ch01..ch16 文本映射。"""
    import json as _json
    import re

    from sqlalchemy import text as sa_text

    result = await db.execute(
        sa_text(
            """
            SELECT item_id, conclusion, remark
            FROM checklist_responses
            WHERE wp_id = :wp_id
              AND (
                item_id LIKE 'a171-ch%%'
                OR item_id LIKE 'A17-1-ch%%'
              )
            """
        ),
        {"wp_id": str(wp_id)},
    )
    chapters: dict[str, str | None] = {f"A17-1-ch{i:02d}": None for i in range(1, 17)}

    def _merge(key: str, text: str | None) -> None:
        if not text or not str(text).strip():
            return
        prev = chapters.get(key) or ""
        chapters[key] = f"{prev}\n{text}".strip() if prev else str(text).strip()

    for row in result.fetchall():
        item_id: str = row.item_id

        # 旧格式: A17-1-ch01
        m_old = re.match(r"A17-1-ch(\d{2})", item_id)
        if m_old:
            _merge(f"A17-1-ch{m_old.group(1)}", row.remark or row.conclusion)
            continue

        # 新格式: a171-ch{N}-content / -yn / -table
        m = re.match(r"a171-ch(\d{1,2})-(content|yn|table)$", item_id)
        if not m:
            continue
        num = int(m.group(1))
        kind = m.group(2)
        key = f"A17-1-ch{num:02d}"
        if kind == "content":
            _merge(key, row.remark)
        elif kind == "yn":
            parts = [p for p in (row.conclusion, row.remark) if p]
            _merge(key, "\n".join(str(p) for p in parts))
        elif kind == "table":
            raw = row.remark or ""
            try:
                rows = _json.loads(raw) if raw else []
                _merge(key, _json.dumps(rows, ensure_ascii=False) if rows else "")
            except Exception:
                _merge(key, raw)

    return chapters


async def _load_a17_cross_doc_context(db, project_id) -> dict:
    """加载 A17-7 签署、A17-3/3-1 成对状态。"""
    from sqlalchemy import text as sa_text

    ctx = {
        "a177_signed": False,
        "a173_has_content": False,
        "a1731_closed": False,
    }

    # wp_id map
    idx = await db.execute(
        sa_text(
            """
            -- wp_index 无 wp_id 列；wp_id 须经 working_paper.wp_index_id 反查
            SELECT wi.wp_code, wp.id AS wp_id FROM wp_index wi
            LEFT JOIN working_paper wp ON wp.wp_index_id = wi.id
            WHERE wi.project_id = :pid
              AND wi.wp_code IN ('A17-3', 'A17-3-1', 'A17-7', 'A17-7A')
            """
        ),
        {"pid": str(project_id)},
    )
    wp_map = {row.wp_code: str(row.wp_id) for row in idx.fetchall() if row.wp_id}

    async def _has_filled(wp_id: str, like_prefix: str) -> bool:
        r = await db.execute(
            sa_text(
                """
                SELECT 1 FROM checklist_responses
                WHERE wp_id = :wid
                  AND item_id LIKE :pfx
                  AND (
                    (conclusion IS NOT NULL AND conclusion <> '')
                    OR (remark IS NOT NULL AND TRIM(remark) <> '')
                  )
                LIMIT 1
                """
            ),
            {"wid": wp_id, "pfx": f"{like_prefix}%"},
        )
        return r.fetchone() is not None

    # A17-7 signed
    for code in ("A17-7", "A17-7A"):
        wid = wp_map.get(code)
        if not wid:
            continue
        r = await db.execute(
            sa_text(
                """
                SELECT conclusion FROM checklist_responses
                WHERE wp_id = :wid AND item_id = 'A17-7-sign-status'
                LIMIT 1
                """
            ),
            {"wid": wid},
        )
        row = r.fetchone()
        if row and row.conclusion == "signed":
            ctx["a177_signed"] = True
            break
        # fallback: any a177 sign-like filled
        if await _has_filled(wid, "a177-"):
            # 有填写但未必 signed；仅当明确 signed 才 True。保持 False。
            pass

    # A17-3 has content
    wid3 = wp_map.get("A17-3")
    if wid3 and await _has_filled(wid3, "a173-"):
        ctx["a173_has_content"] = True

    # A17-3-1 closed = has execution content OR not_required flag
    wid31 = wp_map.get("A17-3-1")
    if wid31:
        r = await db.execute(
            sa_text(
                """
                SELECT conclusion FROM checklist_responses
                WHERE wp_id = :wid AND item_id = 'a1731-meta-not_required'
                LIMIT 1
                """
            ),
            {"wid": wid31},
        )
        row = r.fetchone()
        if row and str(row.conclusion).lower() in ("1", "true", "yes", "y", "是"):
            ctx["a1731_closed"] = True
        elif await _has_filled(wid31, "a1731-sec"):
            ctx["a1731_closed"] = True

    # 无咨询时视为已关闭（不成对阻断）
    if not ctx["a173_has_content"]:
        ctx["a1731_closed"] = True

    return ctx


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
            JOIN wp_index wi ON wp.wp_index_id = wi.id
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
