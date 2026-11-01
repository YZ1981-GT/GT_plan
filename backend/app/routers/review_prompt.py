"""底稿级复核提示词 HTTP 端点

POST /api/workpapers/{wp_id}/review        — 单底稿 AI 复核
POST /api/projects/{pid}/ai-batch-review  — 批量复核
GET  /api/projects/{pid}/review-export     — 导出 Excel 复核报告
GET  /api/review-prompts/coverage          — 提示词覆盖率统计

Requirements: 3.1, 3.2, 3.3, 3.4, 4.1, 7.1, 7.2, 7.3, 7.4, 10.3
"""
from __future__ import annotations

import io
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session, get_db
from app.deps import assert_project_permission, authorize_wp_read, get_current_user, require_role
from app.models.core import User
from app.services.ai_review_verdict import resolve_ai_review_verdict
from app.services.batch_review_service import BatchReviewService
from app.services.llm_response_parser import LlmResponseParser, ReviewFinding
from app.services.review_prompt_service import ReviewPromptService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["review-prompt"])

# ---------------------------------------------------------------------------
# LLM 调用指标追踪
# ---------------------------------------------------------------------------

_review_metrics: dict[str, list] = {
    "calls": [],  # List of {timestamp, duration_ms, success, parse_success, token_count_approx}
}
_METRICS_MAX_HISTORY = 1000  # Keep last 1000 calls

# ---------------------------------------------------------------------------
# Pydantic 模型
# ---------------------------------------------------------------------------


class ReviewRequest(BaseModel):
    """单底稿复核请求体"""
    sheet_name: Optional[str] = Field(None, description="底稿 sheet 名称，用于 sheet-level 匹配")


class ReviewFindingResponse(BaseModel):
    """单条复核发现响应"""
    id: str
    description: str
    risk_level: str
    pass_status: bool
    category: str
    sheet_location: Optional[str] = None
    suggestion: Optional[str] = None


class SheetInfo(BaseModel):
    """底稿信息"""
    wp_id: str
    wp_code: str
    sheet_name: Optional[str] = None
    prompt_source: str  # "sheet" | "subject" | "base"


class ReviewResponse(BaseModel):
    """单底稿复核响应"""
    findings: list[ReviewFindingResponse]
    deterministic_checks: list[dict] = Field(default_factory=list)
    # 兼容旧前端；仅表示 AI 输出可解析且未触发旧风险阈值，不代表人工复核通过。
    overall_pass: bool
    review_status: str = "manual_review_required"
    risk_summary: dict[str, int]  # {"high": n, "medium": n, "low": n}
    sheet_info: SheetInfo


class CoverageReportResponse(BaseModel):
    """提示词覆盖率响应"""
    total_subjects: int
    subjects_with_sheet_prompts: int
    sheet_breakdown: dict[str, list[str]]
    missing_gaps: list[str]


class FindingStatusUpdate(BaseModel):
    """更新 Finding 状态请求"""
    status: str  # "pending" | "resolved" | "ignored" | "not_applicable"


class BatchReviewRequest(BaseModel):
    """批量复核请求体"""
    wp_code_prefix: str = Field(..., description="底稿编码前缀，如 D2")
    year: int = Field(..., description="审计年度")
    progress_session_id: Optional[str] = Field(
        None,
        description="前端生成的进度追踪 session_id，用于 batch-review-progress 轮询",
    )


class BatchFindingResponse(BaseModel):
    """批量复核中的单条发现"""
    id: str
    description: str
    risk_level: str
    pass_status: bool
    category: str
    sheet_location: Optional[str] = None
    suggestion: Optional[str] = None


class BatchResultResponse(BaseModel):
    """单底稿复核结果"""
    wp_id: str
    sheet_name: str
    wp_code: str
    pass_status: str
    findings: list[BatchFindingResponse]
    risk_summary: dict[str, int]
    reviewed_at: str
    model_used: str
    prompt_source: str
    error_message: Optional[str] = None


class BatchStatisticsResponse(BaseModel):
    """批量复核统计"""
    total_sheets: int
    passed_count: int
    failed_count: int
    error_count: int
    total_findings: int
    findings_by_risk: dict[str, int]


class ExecutionMetadataResponse(BaseModel):
    """执行元数据"""
    start_time: str
    end_time: str
    duration_seconds: float
    model_used: str


class BatchReviewReportResponse(BaseModel):
    """批量复核报告响应"""
    session_id: str
    wp_code_prefix: str
    project_id: str
    results: list[BatchResultResponse]
    statistics: BatchStatisticsResponse
    execution: ExecutionMetadataResponse


# ---------------------------------------------------------------------------
# 端点实现
# ---------------------------------------------------------------------------


@router.post("/api/workpapers/{wp_id}/review", response_model=ReviewResponse)
async def review_workpaper(
    wp_id: UUID,
    body: ReviewRequest | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """单底稿 AI 复核

    - 有 sheet_name 时：用 ReviewPromptService 匹配 sheet-level prompt
    - 无 sheet_name 时：降级到科目级（向后兼容）

    流程：
    1. ReviewPromptService.load_prompt → 获取匹配的提示词
    2. 获取底稿内容（render-config → 文本化）
    3. chat_completion → LLM 复核
    4. LlmResponseParser.parse → 结构化结果
    5. 返回 ReviewResponse

    鉴权：底稿所属项目 review 级（与批量复核同级），先于读底稿、调模型（原先无任何鉴权，
    spec project-pid-path-authz-coverage）。底稿不存在 404、非成员 403。

    Requirements: 3.1, 3.2, 3.3, 3.4
    """
    wp_project_id = await authorize_wp_read(db, current_user, wp_id)
    await assert_project_permission(db, current_user, wp_project_id, "review")
    sheet_name = body.sheet_name if body else None

    # 1. 查底稿信息（wp_code）
    wp_code = await _get_wp_code(wp_id)
    if not wp_code:
        raise HTTPException(status_code=404, detail="底稿不存在或未关联 wp_index")

    # 2. 加载复核提示词
    prompt_service = ReviewPromptService()
    prompt_result = prompt_service.load_prompt(wp_code, sheet_name)

    # 3. 获取底稿内容 + 跨底稿勾稽上下文（D2 专用富勾稽 / K/N 通用勾稽，统一分发）
    workpaper_content = await _get_workpaper_content(wp_id, sheet_name)
    from app.services.cycle_review_context import (
        append_reconciliation_to_user_prompt,
        build_review_reconciliation_context,
        build_review_reconciliation_findings,
    )
    recon_context = await build_review_reconciliation_context(str(wp_id), wp_code)
    deterministic_checks = await build_review_reconciliation_findings(str(wp_id), wp_code)
    deterministic_blocking_failures = sum(
        1 for check in deterministic_checks
        if check.get("severity") == "blocking" and check.get("passed") is False
    )
    deterministic_unknown = any(
        check.get("severity") == "blocking" and check.get("passed") is None
        for check in deterministic_checks
    )

    # 4. 构建 LLM 消息并调用
    system_prompt = (
        "你是资深审计师，请根据以下复核提示词对审计底稿内容进行智能复核。\n"
        "请以严格 JSON 格式输出复核结果，格式如下：\n"
        '{"findings": [\n'
        '  {"description": "问题描述", "risk_level": "high|medium|low", "passed": true|false, '
        '"category": "认定检查|程序执行|数据完整性|风险评估|general", '
        '"location": "Sheet名!单元格范围 或 null", "suggestion": "整改建议 或 null"}\n'
        "]}\n"
        "规则：\n"
        "- 对每项检查点输出一个 finding 对象\n"
        "- passed=true 表示该项通过，passed=false 表示未通过\n"
        "- risk_level 根据检查项所属风险等级填写\n"
        "- 如系统已给出勾稽差异，必须据此输出未通过 finding，不得忽略\n"
        "- 如无问题可输出空 findings 数组\n\n"
        "## 输出示例\n\n"
        '{"findings": [\n'
        '  {"description": "期初余额与上年审定期末一致", "risk_level": "high", "passed": true, "category": "数据完整性", "location": null, "suggestion": null},\n'
        '  {"description": "坏账准备计提比例与政策不符（实际2% vs 政策3%）", "risk_level": "high", "passed": false, "category": "认定检查", "location": "坏账准备!C15:D20", "suggestion": "调整坏账准备金额，按3%重新计提"},\n'
        '  {"description": "账龄分析各段金额合计与余额一致", "risk_level": "medium", "passed": true, "category": "数据完整性", "location": null, "suggestion": null}\n'
        "]}\n\n"
        f"## 复核提示词\n\n{prompt_result.content}"
    )
    user_prompt = f"以下是需要复核的底稿内容：\n\n{workpaper_content}"
    if recon_context:
        user_prompt = append_reconciliation_to_user_prompt(user_prompt, recon_context)

    role = getattr(getattr(current_user, "role", None), "value", getattr(current_user, "role", None))
    invocation = await _call_llm(
        system_prompt, user_prompt, str(role) if role is not None else None
    )
    # 兼容既有测试/扩展对 `_call_llm` 的字符串替身；生产实现始终返回 typed 结果。
    if isinstance(invocation, str):
        from app.services.ai_chat.native_engine import is_llm_fail_soft_placeholder
        from app.services.llm_client import LLMInvocationResult, LLMInvocationStatus

        invocation = LLMInvocationResult(
            status=(
                LLMInvocationStatus.unavailable
                if is_llm_fail_soft_placeholder(invocation)
                else LLMInvocationStatus.success
            ),
            text=None if is_llm_fail_soft_placeholder(invocation) else invocation,
            error_code=("legacy_fail_soft" if is_llm_fail_soft_placeholder(invocation) else None),
            error_message=(invocation if is_llm_fail_soft_placeholder(invocation) else None),
        )
    raw_response = invocation.text or ""

    # 5. 解析 LLM 响应；typed 调用失败不得被 parser 解释成普通 finding。
    if invocation.succeeded:
        parse_result = LlmResponseParser.parse(raw_response)
    else:
        parse_result = LlmResponseParser._degrade_to_unknown(
            invocation.error_message or "AI 复核服务不可用"
        )

    # 6. AI 只提供疑点，不产生业务“通过”。
    verdict = resolve_ai_review_verdict(
        parse_success=parse_result.parse_success and not deterministic_unknown,
        findings=parse_result.findings,
        deterministic_blocking_failures=deterministic_blocking_failures,
    )
    overall_pass = verdict.business_pass
    review_status = verdict.status.value

    risk_summary = {"high": 0, "medium": 0, "low": 0}
    for f in parse_result.findings:
        if not f.pass_status:
            if f.risk_level in risk_summary:
                risk_summary[f.risk_level] += 1

    # 6b. 持久化（与批量复核对齐，append-only）
    try:
        project_id = await _get_project_id(wp_id)
        if project_id:
            from app.services.batch_review_service import (
                BatchReviewService,
                BatchStatistics,
                ReviewResult,
            )
            session_id = str(uuid.uuid4())
            single_result = ReviewResult(
                wp_id=str(wp_id),
                sheet_name=sheet_name or wp_code,
                wp_code=wp_code,
                pass_status=review_status,
                findings=parse_result.findings,
                risk_summary=risk_summary,
                reviewed_at=datetime.now(timezone.utc).isoformat(),
                model_used=invocation.model_name or "unknown",
                prompt_source=prompt_result.source_level,
                deterministic_checks=deterministic_checks,
            )
            stats = BatchStatistics(
                total_sheets=1,
                passed_count=0,
                failed_count=1 if review_status == "ai_findings_present" else 0,
                error_count=1 if review_status == "manual_review_required" else 0,
                total_findings=len(parse_result.findings),
                findings_by_risk=risk_summary,
            )
            await BatchReviewService().persist_review_results(
                project_id=project_id,
                session_id=session_id,
                wp_code_prefix=(wp_code or "WP").split("-")[0] if wp_code else "WP",
                results=[single_result],
                statistics=stats,
            )
    except Exception as e:
        logger.warning("Single review persist failed (non-blocking): %s", e)

    # 7. 构建响应
    findings_response = [
        ReviewFindingResponse(
            id=f.id,
            description=f.description,
            risk_level=f.risk_level,
            pass_status=f.pass_status,
            category=f.category,
            sheet_location=f.sheet_location,
            suggestion=f.suggestion,
        )
        for f in parse_result.findings
    ]

    return ReviewResponse(
        findings=findings_response,
        deterministic_checks=deterministic_checks,
        overall_pass=overall_pass,
        review_status=review_status,
        risk_summary=risk_summary,
        sheet_info=SheetInfo(
            wp_id=str(wp_id),
            wp_code=wp_code,
            sheet_name=sheet_name,
            prompt_source=prompt_result.source_level,
        ),
    )


@router.get("/api/review-prompts/coverage", response_model=CoverageReportResponse)
async def get_review_prompt_coverage(current_user: User = Depends(get_current_user)):
    """获取提示词覆盖率统计（全局只读诊断，不含项目数据：须登录）

    委托 ReviewPromptService.get_coverage 返回覆盖率报告。

    Requirements: 10.3
    """
    prompt_service = ReviewPromptService()
    report = prompt_service.get_coverage()

    return CoverageReportResponse(
        total_subjects=report.total_subjects,
        subjects_with_sheet_prompts=report.subjects_with_sheet_prompts,
        sheet_breakdown=report.sheet_breakdown,
        missing_gaps=report.missing_gaps,
    )


@router.get("/api/review-prompts/metrics")
async def get_review_metrics(current_user: User = Depends(require_role(["admin"]))):
    """LLM 复核运行指标（仅管理员，不返回项目正文）。"""
    calls = _review_metrics["calls"]
    if not calls:
        return {
            "total_calls": 0,
            "avg_duration_ms": 0,
            "success_rate": 0,
            "parse_success_rate": 0,
            "last_24h_calls": 0,
        }

    from datetime import timedelta
    now = datetime.now(timezone.utc)
    last_24h = [c for c in calls if (now - datetime.fromisoformat(c["timestamp"])) < timedelta(hours=24)]

    total = len(calls)
    successes = sum(1 for c in calls if c["success"])
    parse_successes = sum(1 for c in calls if c.get("parse_success"))
    avg_duration = sum(c["duration_ms"] for c in calls) / total if total else 0

    return {
        "total_calls": total,
        "avg_duration_ms": round(avg_duration, 1),
        "success_rate": round(successes / total * 100, 1) if total else 0,
        "parse_success_rate": round(parse_successes / total * 100, 1) if total else 0,
        "last_24h_calls": len(last_24h),
        "recent_calls": calls[-10:],  # Last 10 calls for debugging
    }


async def _set_finding_status(db: AsyncSession, finding_id: str, status: str) -> int:
    """写复核发现的 ``data_sources.finding_status``（PG jsonb_set），返回命中行数。"""
    result = await db.execute(
        text(
            "UPDATE ai_content SET "
            "data_sources = jsonb_set("
            "COALESCE(data_sources::jsonb, '{}'::jsonb), "
            "'{finding_status}', CAST(:status_val AS JSONB)) "
            "WHERE id = :finding_id AND content_type = 'review_finding'"
        ),
        {"finding_id": finding_id, "status_val": f'"{status}"'},
    )
    return result.rowcount


@router.patch("/api/review-findings/{finding_id}/status")
async def update_finding_status(
    finding_id: str,
    body: FindingStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新单条复核发现的状态

    允许值: pending（待处理）, resolved（已整改）, ignored（已忽略）, not_applicable（不适用）

    鉴权：该发现所属项目 review 级（原先无任何鉴权，可改任意项目的复核记录，
    spec project-pid-path-authz-coverage）；发现不存在 404。
    """
    valid_statuses = {"pending", "resolved", "ignored", "not_applicable"}
    if body.status not in valid_statuses:
        raise HTTPException(
            status_code=422,
            detail=f"无效状态，允许值: {', '.join(valid_statuses)}",
        )

    from app.models.ai_models import AIContent, AIContentType

    try:
        finding_uuid = UUID(finding_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Finding 不存在")
    project_id = (
        await db.execute(
            select(AIContent.project_id).where(
                AIContent.id == finding_uuid,
                AIContent.content_type == AIContentType.review_finding,
            )
        )
    ).scalar_one_or_none()
    if project_id is None:
        raise HTTPException(status_code=404, detail="Finding 不存在")
    await assert_project_permission(db, current_user, project_id, "review")

    if await _set_finding_status(db, finding_id, body.status) == 0:
        raise HTTPException(status_code=404, detail="Finding 不存在")
    await db.commit()
    return {"id": finding_id, "status": body.status}


# ---------------------------------------------------------------------------
# 批量复核端点 (Task 5.2)
# ---------------------------------------------------------------------------


@router.get("/api/projects/{pid}/batch-review-progress")
async def get_batch_review_progress(
    pid: UUID,
    session_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """兼容旧轮询：从 DB-backed job snapshot 投影进度。"""
    await assert_project_permission(db, current_user, pid, "readonly")
    from app.models.ai_task_job_models import AiTaskJob
    from app.services.ai_task_job_service import get_job_snapshot

    job = (await db.execute(select(AiTaskJob).where(
        AiTaskJob.project_id == pid,
        AiTaskJob.actor_id == current_user.id,
        AiTaskJob.task_kind == "workpaper_batch_review",
        AiTaskJob.idempotency_key == session_id,
    ).order_by(AiTaskJob.created_at.desc()).limit(1))).scalar_one_or_none()
    if job is None:
        try:
            job_id = UUID(session_id)
        except ValueError:
            return {"status": "not_found", "current": 0, "total": 0, "current_sheet": ""}
        job = (await db.execute(select(AiTaskJob).where(
            AiTaskJob.id == job_id,
            AiTaskJob.project_id == pid,
        ))).scalar_one_or_none()
    if job is None:
        return {"status": "not_found", "current": 0, "total": 0, "current_sheet": ""}
    snapshot = await get_job_snapshot(db, project_id=pid, job_id=job.id)
    active = next(
        (item for item in snapshot["items"] if item["status"] in {"running", "retry_wait"}),
        None,
    )
    return {
        "status": snapshot["status"],
        "current": snapshot["progress_done"],
        "total": snapshot["progress_total"],
        "current_sheet": active["target_key"] if active else "",
        "job_id": snapshot["job_id"],
    }


@router.post("/api/projects/{pid}/ai-batch-review")
async def batch_review(
    pid: UUID,
    body: BatchReviewRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """兼容入口：创建 DB-backed 底稿复核任务并立即返回 snapshot。"""
    await assert_project_permission(db, current_user, pid, "review")
    from app.routers.ai_task_jobs import AiTaskJobCreate, create_job

    return await create_job(
        pid,
        AiTaskJobCreate(
            task_kind="workpaper_batch_review",
            year=body.year,
            idempotency_key=body.progress_session_id or str(uuid.uuid4()),
            wp_code_prefix=body.wp_code_prefix,
        ),
        db,
        current_user,
    )


# ---------------------------------------------------------------------------
# 复核导出端点 (Task 5.3)
# ---------------------------------------------------------------------------


@router.get("/api/projects/{pid}/review-export")
async def export_review_report(
    pid: UUID,
    wp_code_prefix: str = Query(..., description="底稿编码前缀，如 D2"),
    session_id: Optional[str] = Query(None, description="复核会话 ID（可选）"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """导出复核结果为 Excel — 从已持久化的数据库结果读取，不重跑 LLM（项目只读级；原先无任何鉴权）

    生成 Excel workbook，每张底稿一个 worksheet + 首页汇总。
    列：序号/检查项/风险等级/是否通过/问题描述/涉及底稿定位/整改建议/负责人/状态
    RFC5987 中文文件名编码。

    Requirements: 7.1, 7.2, 7.3, 7.4
    """
    await assert_project_permission(db, current_user, pid, "readonly")
    # 优先从数据库读取已持久化的复核结果
    report = await _load_review_report_from_db(str(pid), wp_code_prefix, session_id)

    if not report or not report.results:
        raise HTTPException(
            status_code=404,
            detail="无复核结果，请先执行批量复核",
        )

    # 生成 Excel workbook
    excel_bytes = _generate_review_excel(report)

    # RFC5987 中文文件名编码
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    filename = f"{wp_code_prefix}复核报告_{today_str}.xlsx"
    encoded_filename = quote(filename, safe="")
    content_disposition = (
        f"attachment; "
        f"filename=\"review_report.xlsx\"; "
        f"filename*=UTF-8''{encoded_filename}"
    )

    return StreamingResponse(
        io.BytesIO(excel_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": content_disposition},
    )


def _generate_review_excel(report) -> bytes:
    """生成复核报告 Excel workbook

    Requirements: 7.1, 7.2, 7.3
    """
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    wb = Workbook()

    # --- 首页汇总 (Requirements: 7.3) ---
    ws_summary = wb.active
    ws_summary.title = "汇总"

    # 汇总标题
    ws_summary.append(["复核报告汇总"])
    ws_summary["A1"].font = Font(bold=True, size=14)
    ws_summary.append([])
    ws_summary.append(["科目前缀", report.wp_code_prefix])
    ws_summary.append(["复核日期", report.execution.start_time[:10]])
    ws_summary.append(["使用模型", report.execution.model_used])
    ws_summary.append(["耗时(秒)", f"{report.execution.duration_seconds:.1f}"])
    ws_summary.append([])
    ws_summary.append(["统计项", "数量"])
    ws_summary.append(["底稿总数", report.statistics.total_sheets])
    ws_summary.append(["通过", report.statistics.passed_count])
    ws_summary.append(["未通过", report.statistics.failed_count])
    ws_summary.append(["错误", report.statistics.error_count])
    ws_summary.append(["发现总数", report.statistics.total_findings])
    ws_summary.append([])
    ws_summary.append(["风险等级", "数量"])
    ws_summary.append(["高风险", report.statistics.findings_by_risk.get("high", 0)])
    ws_summary.append(["中风险", report.statistics.findings_by_risk.get("medium", 0)])
    ws_summary.append(["低风险", report.statistics.findings_by_risk.get("low", 0)])
    ws_summary.append([])
    ws_summary.append(["底稿", "编码", "通过状态", "发现数", "高风险", "中风险", "低风险"])

    for r in report.results:
        ws_summary.append([
            r.sheet_name,
            r.wp_code,
            r.pass_status,
            len(r.findings),
            r.risk_summary.get("high", 0),
            r.risk_summary.get("medium", 0),
            r.risk_summary.get("low", 0),
        ])

    # 调整列宽
    for col in ws_summary.columns:
        max_length = 0
        for cell in col:
            if cell.value:
                max_length = max(max_length, len(str(cell.value)))
        adjusted_width = min(max_length + 4, 50)
        ws_summary.column_dimensions[col[0].column_letter].width = adjusted_width

    # --- 每张底稿一个 worksheet (Requirements: 7.1, 7.2) ---
    # 列：序号/检查项/风险等级/是否通过/问题描述/涉及底稿定位/整改建议/负责人/状态
    header_row = [
        "序号", "检查项", "风险等级", "是否通过",
        "问题描述", "涉及底稿定位", "整改建议", "负责人", "状态",
    ]

    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF")

    for result in report.results:
        # 使用 wp_code 作为 sheet 名（限制 31 字符）
        sheet_title = result.wp_code[:31] if result.wp_code else result.sheet_name[:31]
        # 避免重名
        if sheet_title in wb.sheetnames:
            sheet_title = f"{sheet_title[:28]}_{result.wp_id[:3]}"
        ws = wb.create_sheet(title=sheet_title)

        # 写表头
        ws.append(header_row)
        for cell in ws[1]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center")

        # 写发现数据
        if result.findings:
            for idx, finding in enumerate(result.findings, 1):
                risk_label = {"high": "高", "medium": "中", "low": "低"}.get(
                    finding.risk_level, finding.risk_level
                )
                pass_label = "是" if finding.pass_status else "否"
                ws.append([
                    idx,
                    finding.category,
                    risk_label,
                    pass_label,
                    finding.description,
                    finding.sheet_location or "",
                    finding.suggestion or "",
                    "",  # 负责人（需人工填写）
                    "待整改" if not finding.pass_status else "已通过",
                ])
        elif result.error_message:
            ws.append([1, "复核错误", "-", "-", result.error_message, "", "", "", "错误"])
        else:
            ws.append([1, "无发现", "-", "是", "复核通过，无发现问题", "", "", "", "已通过"])

        # 调整列宽
        col_widths = [6, 14, 10, 10, 40, 20, 30, 10, 10]
        for i, width in enumerate(col_widths, 1):
            from openpyxl.utils import get_column_letter
            ws.column_dimensions[get_column_letter(i)].width = width

    # 输出为字节
    output = io.BytesIO()
    wb.save(output)
    return output.getvalue()


# ---------------------------------------------------------------------------
# 内部辅助函数
# ---------------------------------------------------------------------------


async def _load_review_report_from_db(
    project_id: str, wp_code_prefix: str, session_id: str | None
) -> "BatchReviewReport | None":
    """从 ai_content + checklist_responses 读取已持久化的复核结果"""
    import json as _json
    from collections import defaultdict

    from app.services.batch_review_service import (
        BatchReviewReport, BatchStatistics, ExecutionMetadata, ReviewResult,
    )

    async with async_session() as db:
        # 如果没有传 session_id，先兼容旧 checklist 索引；没有旧索引时从
        # DB-backed AI task job 找同前缀最近一次任务，页面刷新后仍可导出。
        if not session_id:
            cr_result = await db.execute(
                text(
                    "SELECT remark FROM checklist_responses "
                    "WHERE project_id = :project_id "
                    "AND item_id LIKE :pattern "
                    "ORDER BY created_at DESC LIMIT 1"
                ),
                {"project_id": project_id, "pattern": f"{wp_code_prefix}-review-session-%"},
            )
            cr_row = cr_result.first()
            if cr_row:
                session_meta = _json.loads(cr_row[0]) if isinstance(cr_row[0], str) else cr_row[0]
                session_id = session_meta.get("session_id")
            if not session_id:
                from app.models.ai_task_job_models import AiTaskJob

                candidates = list((await db.execute(
                    select(AiTaskJob).where(
                        AiTaskJob.project_id == UUID(project_id),
                        AiTaskJob.task_kind == "workpaper_batch_review",
                    ).order_by(AiTaskJob.created_at.desc()).limit(20)
                )).scalars().all())
                latest = next(
                    (
                        job for job in candidates
                        if str((job.request_payload or {}).get("wp_code_prefix") or "")
                        == wp_code_prefix
                    ),
                    None,
                )
                if latest is None:
                    return None
                session_id = str(latest.id)

        # 新链以 job snapshot 为权威，包含“AI 未发现新增疑点”和失败项；不能只按
        # ai_content finding 行重建，否则合法空 findings 会被误判成“没有跑过”。
        try:
            durable_job_id = UUID(session_id)
        except (TypeError, ValueError):
            durable_job_id = None
        if durable_job_id is not None:
            from app.services.ai_task_review_report import load_review_job_report

            durable = await load_review_job_report(
                db,
                project_id=UUID(project_id),
                wp_code_prefix=wp_code_prefix,
                job_id=durable_job_id,
            )
            if durable is not None:
                return durable

        # 加载旧链该 session 所有 findings
        result = await db.execute(
            text(
                "SELECT workpaper_id, content_text, data_sources, created_at "
                "FROM ai_content "
                "WHERE project_id = :project_id "
                "AND content_type = 'review_finding' "
                "AND data_sources->>'session_id' = :session_id "
                "ORDER BY created_at"
            ),
            {"project_id": project_id, "session_id": session_id},
        )
        rows = result.fetchall()

        if not rows:
            return None

        # 按 wp_code 分组
        grouped: dict[str, list] = defaultdict(list)
        for row in rows:
            ds = _json.loads(row[2]) if isinstance(row[2], str) else row[2]
            wp_code = ds.get("wp_code", "")
            grouped[wp_code].append({
                "workpaper_id": str(row[0]),
                "description": row[1],
                "data_sources": ds,
                "created_at": str(row[3]),
            })

        # 构建 ReviewResult 列表
        results: list[ReviewResult] = []
        for wp_code, findings_data in grouped.items():
            findings = [
                ReviewFinding(
                    id=str(uuid.uuid4()),
                    description=fd["description"],
                    risk_level=fd["data_sources"].get("risk_level", "unknown"),
                    pass_status=fd["data_sources"].get("pass_status") == "True",
                    category=fd["data_sources"].get("category", "general"),
                    sheet_location=None,
                    suggestion=None,
                )
                for fd in findings_data
            ]

            risk_summary = {"high": 0, "medium": 0, "low": 0}
            for f in findings:
                if not f.pass_status and f.risk_level in risk_summary:
                    risk_summary[f.risk_level] += 1

            pass_status = LlmResponseParser.determine_pass_status(
                findings, sheet_name=findings_data[0]["data_sources"].get("sheet_name")
            )

            results.append(ReviewResult(
                wp_id=findings_data[0]["workpaper_id"],
                sheet_name=findings_data[0]["data_sources"].get("sheet_name", wp_code),
                wp_code=wp_code,
                pass_status=pass_status,
                findings=findings,
                risk_summary=risk_summary,
                reviewed_at=findings_data[0]["created_at"],
                model_used="(from DB)",
                prompt_source="(from DB)",
                error_message=None,
            ))

        # 构建统计
        total = len(results)
        passed = sum(1 for r in results if r.pass_status == "pass")
        failed = sum(1 for r in results if r.pass_status == "fail")
        error = total - passed - failed
        total_findings = sum(len(r.findings) for r in results)
        findings_by_risk: dict[str, int] = {"high": 0, "medium": 0, "low": 0}
        for r in results:
            for f in r.findings:
                if not f.pass_status and f.risk_level in findings_by_risk:
                    findings_by_risk[f.risk_level] += 1

        return BatchReviewReport(
            session_id=session_id,
            wp_code_prefix=wp_code_prefix,
            project_id=project_id,
            results=results,
            statistics=BatchStatistics(
                total_sheets=total,
                passed_count=passed,
                failed_count=failed,
                error_count=error,
                total_findings=total_findings,
                findings_by_risk=findings_by_risk,
            ),
            execution=ExecutionMetadata(
                start_time=results[0].reviewed_at if results else "",
                end_time=results[-1].reviewed_at if results else "",
                duration_seconds=0.0,
                model_used="(from DB)",
            ),
        )


async def _get_wp_code(wp_id: UUID) -> str | None:
    """从 working_paper JOIN wp_index 获取 wp_code"""
    async with async_session() as db:
        result = await db.execute(
            text(
                "SELECT wi.wp_code FROM working_paper wp "
                "JOIN wp_index wi ON wp.wp_index_id = wi.id "
                "WHERE wp.id = :wp_id AND wp.is_deleted = false"
            ),
            {"wp_id": str(wp_id)},
        )
        row = result.first()
        return row[0] if row else None


async def _get_project_id(wp_id: UUID) -> str | None:
    """从 working_paper 获取 project_id"""
    async with async_session() as db:
        result = await db.execute(
            text(
                "SELECT project_id FROM working_paper "
                "WHERE id = :wp_id AND is_deleted = false"
            ),
            {"wp_id": str(wp_id)},
        )
        row = result.first()
        return str(row[0]) if row else None


async def _get_workpaper_content(wp_id: UUID, sheet_name: str | None) -> str:
    """获取底稿内容（DB 直读 checklist_responses + parsed_data，不经 HTTP）"""
    from app.services.review_content_loader import load_workpaper_review_content

    return await load_workpaper_review_content(wp_id, sheet_name)


async def _call_llm(
    system_prompt: str, user_prompt: str, role: str | None = None
):
    """调用登记的高风险复核任务；失败不返回可解析的占位正文。"""
    import time as _time

    from app.services.ai_task_executor import invoke_ai_task
    from app.services.llm_client import LLMInvocationResult, LLMInvocationStatus

    start = _time.monotonic()
    result: LLMInvocationResult
    try:
        invocation = await invoke_ai_task(
            "review.workpaper",
            user_prompt=user_prompt,
            system_addendum=system_prompt,
            role=role,
            temperature=0.1,
        )
        result = invocation.result
        return result
    except Exception as exc:
        logger.error("LLM call failed: %s", exc)
        result = LLMInvocationResult(
            status=LLMInvocationStatus.unavailable,
            error_code="internal_error",
            error_message="AI 复核服务不可用",
        )
        return result
    finally:
        duration_ms = (_time.monotonic() - start) * 1000
        current = locals().get("result")
        _review_metrics["calls"].append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "duration_ms": round(duration_ms, 1),
            "success": bool(current and current.succeeded),
            "parse_success": None,
            "token_count_approx": len(user_prompt) // 2,
        })
        if len(_review_metrics["calls"]) > _METRICS_MAX_HISTORY:
            _review_metrics["calls"] = _review_metrics["calls"][-_METRICS_MAX_HISTORY:]
