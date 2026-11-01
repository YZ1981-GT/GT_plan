"""从耐久 AI job snapshot 重建可导出的批量复核报告。"""

from __future__ import annotations

from collections import Counter
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_task_job_models import AiTaskItem, AiTaskJob
from app.services.batch_review_service import (
    BatchReviewReport,
    BatchStatistics,
    ExecutionMetadata,
    ReviewResult,
)
from app.services.llm_response_parser import ReviewFinding


async def load_review_job_report(
    db: AsyncSession,
    *,
    project_id: UUID,
    wp_code_prefix: str,
    job_id: UUID,
) -> BatchReviewReport | None:
    job = (await db.execute(sa.select(AiTaskJob).where(
        AiTaskJob.id == job_id,
        AiTaskJob.project_id == project_id,
        AiTaskJob.task_kind == "workpaper_batch_review",
    ))).scalar_one_or_none()
    if job is None:
        return None
    items = list((await db.execute(sa.select(AiTaskItem).where(
        AiTaskItem.job_id == job.id,
    ).order_by(AiTaskItem.ordinal))).scalars().all())

    results: list[ReviewResult] = []
    for item in items:
        data = dict(item.result_summary or {})
        raw_findings = data.get("findings") or []
        findings = [ReviewFinding(
            id=str(raw.get("id") or ""),
            description=str(raw.get("description") or ""),
            risk_level=str(raw.get("risk_level") or "unknown"),
            pass_status=bool(raw.get("pass_status")),
            category=str(raw.get("category") or "general"),
            sheet_location=raw.get("sheet_location"),
            suggestion=raw.get("suggestion"),
        ) for raw in raw_findings]
        status = str(data.get("review_status") or (
            "review_error" if item.status == "failed" else "manual_review_required"
        ))
        results.append(ReviewResult(
            wp_id=str(data.get("wp_id") or item.target_id),
            sheet_name=str(data.get("sheet_name") or item.target_key or "底稿"),
            wp_code=str(data.get("wp_code") or ""),
            pass_status=status,
            findings=findings,
            risk_summary=dict(data.get("risk_summary") or {"high": 0, "medium": 0, "low": 0}),
            reviewed_at=str(data.get("reviewed_at") or item.finished_at or job.finished_at or ""),
            model_used=str(data.get("model_used") or "unknown"),
            prompt_source=str(data.get("prompt_source") or "unknown"),
            error_message=item.error_message or data.get("error_message"),
        ))

    status_counts = Counter(result.pass_status for result in results)
    findings_by_risk = {"high": 0, "medium": 0, "low": 0}
    for result in results:
        for finding in result.findings:
            if not finding.pass_status and finding.risk_level in findings_by_risk:
                findings_by_risk[finding.risk_level] += 1
    models = sorted({result.model_used for result in results if result.model_used != "unknown"})
    start = job.started_at or job.created_at
    end = job.finished_at or job.updated_at
    duration = max(0.0, (end - start).total_seconds()) if start and end else 0.0
    return BatchReviewReport(
        session_id=str(job.id),
        wp_code_prefix=wp_code_prefix,
        project_id=str(project_id),
        results=results,
        statistics=BatchStatistics(
            total_sheets=len(results),
            passed_count=0,
            failed_count=(
                status_counts["ai_findings_present"]
                + status_counts["deterministic_failure"]
                + status_counts["fail"]
            ),
            error_count=(
                status_counts["manual_review_required"]
                + status_counts["review_error"]
            ),
            total_findings=sum(len(result.findings) for result in results),
            findings_by_risk=findings_by_risk,
        ),
        execution=ExecutionMetadata(
            start_time=start.isoformat() if start else "",
            end_time=end.isoformat() if end else "",
            duration_seconds=duration,
            model_used="、".join(models) if models else "unknown",
        ),
    )
