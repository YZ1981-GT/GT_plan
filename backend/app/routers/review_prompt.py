"""底稿级复核提示词 HTTP 端点

POST /api/workpapers/{wp_id}/review        — 单底稿 AI 复核
POST /api/projects/{pid}/batch-review      — 批量复核
GET  /api/projects/{pid}/review-export     — 导出 Excel 复核报告
GET  /api/review-prompts/coverage          — 提示词覆盖率统计

Requirements: 3.1, 3.2, 3.3, 3.4, 4.1, 7.1, 7.2, 7.3, 7.4, 10.3
"""
from __future__ import annotations

import asyncio
import io
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import quote
from uuid import UUID

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.core.config import settings
from app.core.database import async_session
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
# 并发控制 & 进度追踪
# ---------------------------------------------------------------------------

# 每项目批量复核锁（防止并发重复执行）
_batch_locks: dict[str, asyncio.Lock] = {}

# 批量复核进度追踪 (per session_id)
_batch_progress: dict[str, dict] = {}

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
    overall_pass: bool
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
async def review_workpaper(wp_id: UUID, body: ReviewRequest | None = None):
    """单底稿 AI 复核

    - 有 sheet_name 时：用 ReviewPromptService 匹配 sheet-level prompt
    - 无 sheet_name 时：降级到科目级（向后兼容）

    流程：
    1. ReviewPromptService.load_prompt → 获取匹配的提示词
    2. 获取底稿内容（render-config → 文本化）
    3. chat_completion → LLM 复核
    4. LlmResponseParser.parse → 结构化结果
    5. 返回 ReviewResponse

    Requirements: 3.1, 3.2, 3.3, 3.4
    """
    sheet_name = body.sheet_name if body else None

    # 1. 查底稿信息（wp_code）
    wp_code = await _get_wp_code(wp_id)
    if not wp_code:
        raise HTTPException(status_code=404, detail="底稿不存在或未关联 wp_index")

    # 2. 加载复核提示词
    prompt_service = ReviewPromptService()
    prompt_result = prompt_service.load_prompt(wp_code, sheet_name)

    # 3. 获取底稿内容
    workpaper_content = await _get_workpaper_content(wp_id, sheet_name)

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

    raw_response = await _call_llm(system_prompt, user_prompt)

    # 5. 解析 LLM 响应
    parse_result = LlmResponseParser.parse(raw_response)

    # 6. 计算总体通过状态和风险汇总
    overall_pass_str = LlmResponseParser.determine_pass_status(parse_result.findings)
    overall_pass = overall_pass_str == "pass"

    risk_summary = {"high": 0, "medium": 0, "low": 0}
    for f in parse_result.findings:
        if not f.pass_status:
            if f.risk_level in risk_summary:
                risk_summary[f.risk_level] += 1

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
        overall_pass=overall_pass,
        risk_summary=risk_summary,
        sheet_info=SheetInfo(
            wp_id=str(wp_id),
            wp_code=wp_code,
            sheet_name=sheet_name,
            prompt_source=prompt_result.source_level,
        ),
    )


@router.get("/api/review-prompts/coverage", response_model=CoverageReportResponse)
async def get_review_prompt_coverage():
    """获取提示词覆盖率统计

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
async def get_review_metrics():
    """LLM 复核调用监控指标"""
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


@router.patch("/api/review-findings/{finding_id}/status")
async def update_finding_status(finding_id: str, body: FindingStatusUpdate):
    """更新单条复核发现的状态

    允许值: pending（待处理）, resolved（已整改）, ignored（已忽略）, not_applicable（不适用）
    """
    valid_statuses = {"pending", "resolved", "ignored", "not_applicable"}
    if body.status not in valid_statuses:
        raise HTTPException(
            status_code=422,
            detail=f"无效状态，允许值: {', '.join(valid_statuses)}",
        )

    async with async_session() as db:
        result = await db.execute(
            text(
                "UPDATE ai_content SET "
                "data_sources = jsonb_set("
                "COALESCE(data_sources::jsonb, '{}'::jsonb), "
                "'{finding_status}', CAST(:status_val AS JSONB)) "
                "WHERE id = :finding_id AND content_type = 'review_finding'"
            ),
            {"finding_id": finding_id, "status_val": f'"{body.status}"'},
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Finding 不存在")
        await db.commit()

    return {"id": finding_id, "status": body.status}


# ---------------------------------------------------------------------------
# 批量复核端点 (Task 5.2)
# ---------------------------------------------------------------------------


@router.get("/api/projects/{pid}/batch-review-progress")
async def get_batch_review_progress(pid: UUID, session_id: str = Query(...)):
    """获取批量复核进度"""
    progress = _batch_progress.get(session_id)
    if not progress:
        return {"status": "not_found", "current": 0, "total": 0, "current_sheet": ""}
    return progress


@router.post(
    "/api/projects/{pid}/batch-review",
    response_model=BatchReviewReportResponse,
)
async def batch_review(pid: UUID, body: BatchReviewRequest):
    """批量复核端点

    接收 wp_code_prefix 和 year，委托 BatchReviewService 执行批量复核。
    逐份调用 LLM 复核，容错续行，汇总结果。

    Requirements: 4.1
    """
    # 并发锁：同一项目不允许同时执行批量复核
    lock_key = str(pid)
    if lock_key not in _batch_locks:
        _batch_locks[lock_key] = asyncio.Lock()

    if _batch_locks[lock_key].locked():
        raise HTTPException(status_code=409, detail="该项目正在复核中，请稍后再试")

    async with _batch_locks[lock_key]:
        service = BatchReviewService()
        session_id_for_progress = str(uuid.uuid4())

        def _update_progress(current: int, total: int, current_sheet: str):
            _batch_progress[session_id_for_progress] = {
                "status": "running",
                "current": current,
                "total": total,
                "current_sheet": current_sheet,
            }

        report = await service.execute_batch(
            project_id=str(pid),
            wp_code_prefix=body.wp_code_prefix,
            year=body.year,
            progress_callback=_update_progress,
        )

        # 清理进度
        _batch_progress.pop(session_id_for_progress, None)

    # 将 dataclass 结果转为 Pydantic 响应
    results_response = [
        BatchResultResponse(
            wp_id=r.wp_id,
            sheet_name=r.sheet_name,
            wp_code=r.wp_code,
            pass_status=r.pass_status,
            findings=[
                BatchFindingResponse(
                    id=f.id,
                    description=f.description,
                    risk_level=f.risk_level,
                    pass_status=f.pass_status,
                    category=f.category,
                    sheet_location=f.sheet_location,
                    suggestion=f.suggestion,
                )
                for f in r.findings
            ],
            risk_summary=r.risk_summary,
            reviewed_at=r.reviewed_at,
            model_used=r.model_used,
            prompt_source=r.prompt_source,
            error_message=r.error_message,
        )
        for r in report.results
    ]

    return BatchReviewReportResponse(
        session_id=report.session_id,
        wp_code_prefix=report.wp_code_prefix,
        project_id=report.project_id,
        results=results_response,
        statistics=BatchStatisticsResponse(
            total_sheets=report.statistics.total_sheets,
            passed_count=report.statistics.passed_count,
            failed_count=report.statistics.failed_count,
            error_count=report.statistics.error_count,
            total_findings=report.statistics.total_findings,
            findings_by_risk=report.statistics.findings_by_risk,
        ),
        execution=ExecutionMetadataResponse(
            start_time=report.execution.start_time,
            end_time=report.execution.end_time,
            duration_seconds=report.execution.duration_seconds,
            model_used=report.execution.model_used,
        ),
    )


# ---------------------------------------------------------------------------
# 复核导出端点 (Task 5.3)
# ---------------------------------------------------------------------------


@router.get("/api/projects/{pid}/review-export")
async def export_review_report(
    pid: UUID,
    wp_code_prefix: str = Query(..., description="底稿编码前缀，如 D2"),
    session_id: Optional[str] = Query(None, description="复核会话 ID（可选）"),
):
    """导出复核结果为 Excel — 从已持久化的数据库结果读取，不重跑 LLM

    生成 Excel workbook，每张底稿一个 worksheet + 首页汇总。
    列：序号/检查项/风险等级/是否通过/问题描述/涉及底稿定位/整改建议/负责人/状态
    RFC5987 中文文件名编码。

    Requirements: 7.1, 7.2, 7.3, 7.4
    """
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
        # 如果没有传 session_id，从 checklist_responses 获取最近的 session
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
            if not cr_row:
                return None
            session_meta = _json.loads(cr_row[0]) if isinstance(cr_row[0], str) else cr_row[0]
            session_id = session_meta.get("session_id")
            if not session_id:
                return None

        # 加载该 session 所有 findings
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

            pass_status = LlmResponseParser.determine_pass_status(findings)

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


async def _get_workpaper_content(wp_id: UUID, sheet_name: str | None) -> str:
    """获取底稿内容（从 render-config 提取 html_data 文本）

    TODO(P0-4): 理想情况应直接调用 _get_render_config_impl 避免自调 HTTP。
    但该函数需要 db: AsyncSession + current_user 参数，直接导入会导致循环依赖
    或需要 mock auth。当前保留 httpx 方式，待后续 render-config 提供无 auth 的
    内部调用入口后再迁移。
    """
    try:
        url = f"http://localhost:{settings.PORT or 9980}/api/workpapers/{wp_id}/render-config"
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                logger.warning(
                    "render-config fetch failed for wp %s: %d", wp_id, resp.status_code
                )
                return "(底稿内容获取失败)"

            data = resp.json()
            # ResponseWrapperMiddleware 包装: {code, message, data: {...}}
            payload = data.get("data", data)
            sheets = payload.get("sheets", [])

            if not sheets:
                return "(底稿无内容)"

            # 如果有 sheet_name，尝试匹配
            target_sheet = None
            if sheet_name:
                for s in sheets:
                    s_name = s.get("sheet_name", "") or ""
                    if sheet_name in s_name or s_name in sheet_name:
                        target_sheet = s
                        break
            # 无匹配或无 sheet_name → 取第一个
            if not target_sheet:
                target_sheet = sheets[0]

            # 提取 html_data 中的文本内容
            html_data = target_sheet.get("html_data", {}) or {}
            return _extract_text_from_html_data(html_data)

    except Exception as e:
        logger.warning("Failed to get workpaper content for %s: %s", wp_id, e)
        return "(底稿内容获取异常)"


def _extract_text_from_html_data(html_data: dict) -> str:
    """从 html_data 提取关键文本内容作为 LLM 输入"""
    parts: list[str] = []

    # 提取 responses_snapshot / allResponses（checklist 回应数据）
    for key in ("responses_snapshot", "allResponses", "checklist_responses"):
        val = html_data.get(key)
        if val and isinstance(val, (dict, list)):
            # 将 JSON 转为可读文本
            import json
            text_repr = json.dumps(val, ensure_ascii=False, indent=None)
            if len(text_repr) > 5000:
                text_repr = text_repr[:5000] + "...(已截断)"
            parts.append(f"[{key}]\n{text_repr}")

    # 提取 tb_values（试算表数据）
    tb_values = html_data.get("tb_values")
    if tb_values and isinstance(tb_values, dict):
        import json
        tb_text = json.dumps(tb_values, ensure_ascii=False, indent=None)
        if len(tb_text) > 2000:
            tb_text = tb_text[:2000] + "...(已截断)"
        parts.append(f"[试算表数据]\n{tb_text}")

    # 提取项目上下文
    project_context = html_data.get("projectContext") or html_data.get("project_context")
    if project_context and isinstance(project_context, dict):
        parts.append(
            f"[项目信息] 客户: {project_context.get('client_name', '')} "
            f"年度: {project_context.get('audit_year', '')}"
        )

    # 如果什么都没提取到，将整个 html_data 的 key 列表和简要值作为输入
    if not parts:
        import json
        fallback = json.dumps(html_data, ensure_ascii=False, indent=None)
        if len(fallback) > 6000:
            fallback = fallback[:6000] + "...(已截断)"
        parts.append(f"[底稿数据]\n{fallback}")

    return "\n\n".join(parts)


async def _call_llm(system_prompt: str, user_prompt: str) -> str:
    """调用 LLM chat_completion 获取复核结果"""
    import time as _time
    start = _time.monotonic()
    success = False
    try:
        from app.services.llm_client import chat_completion

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        result = await chat_completion(
            messages=messages,
            temperature=0.1,
            max_tokens=3000,
        )
        success = True
        return result if isinstance(result, str) else ""
    except Exception as e:
        logger.error("LLM call failed: %s", e)
        return f"[AI 复核暂时不可用: {e}]"
    finally:
        duration_ms = (_time.monotonic() - start) * 1000
        _review_metrics["calls"].append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "duration_ms": round(duration_ms, 1),
            "success": success,
            "parse_success": None,  # Will be updated after parse
            "token_count_approx": len(user_prompt) // 2,  # Rough approximation
        })
        # Trim to max history
        if len(_review_metrics["calls"]) > _METRICS_MAX_HISTORY:
            _review_metrics["calls"] = _review_metrics["calls"][-_METRICS_MAX_HISTORY:]
