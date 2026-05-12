"""SLO summaries for ledger import jobs."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.dataset_models import ImportEventOutbox, ImportJob, JobStatus, OutboxStatus


TERMINAL_STATUSES = {
    JobStatus.completed,
    JobStatus.failed,
    JobStatus.canceled,
    JobStatus.timed_out,
}


class ImportSLOService:
    @staticmethod
    def _thresholds() -> dict:
        return {
            "failure_rate_warn": float(settings.LEDGER_IMPORT_SLO_FAILURE_RATE_WARN_THRESHOLD),
            "timeout_rate_critical": float(settings.LEDGER_IMPORT_SLO_TIMEOUT_RATE_CRITICAL_THRESHOLD),
            "p95_duration_warn_seconds": int(settings.LEDGER_IMPORT_SLO_P95_DURATION_SECONDS_WARN_THRESHOLD),
            "queue_delay_p95_warn_seconds": int(settings.LEDGER_IMPORT_SLO_QUEUE_DELAY_P95_SECONDS_WARN_THRESHOLD),
            "outbox_backlog_warn_count": int(settings.LEDGER_IMPORT_SLO_OUTBOX_BACKLOG_WARN_THRESHOLD),
            "active_jobs_warn_count": int(settings.LEDGER_IMPORT_SLO_ACTIVE_JOBS_WARN_THRESHOLD),
        }

    @staticmethod
    def _percentile(values: list[float], percentile: float) -> float | None:
        if not values:
            return None
        ordered = sorted(values)
        index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * percentile)))
        return round(ordered[index], 3)

    @classmethod
    async def get_summary(
        cls,
        db: AsyncSession,
        *,
        hours: int = 24,
        project_id=None,
        year: int | None = None,
    ) -> dict:
        since = datetime.now(timezone.utc) - timedelta(hours=max(1, hours))
        filters = [ImportJob.created_at >= since]
        if project_id is not None:
            filters.append(ImportJob.project_id == project_id)
        if year is not None:
            filters.append(ImportJob.year == year)

        result = await db.execute(sa.select(ImportJob).where(*filters))
        jobs = list(result.scalars().all())
        total = len(jobs)
        by_status = {status.value: 0 for status in JobStatus}
        durations: list[float] = []
        queue_delays: list[float] = []
        end_to_end_durations: list[float] = []
        recent_failures: list[dict] = []
        retry_total = 0
        active_count = 0

        for job in jobs:
            by_status[job.status.value] = by_status.get(job.status.value, 0) + 1
            retry_total += int(job.retry_count or 0)
            if job.status not in TERMINAL_STATUSES:
                active_count += 1
            if job.created_at and job.started_at:
                queue_delays.append((job.started_at - job.created_at).total_seconds())
            if job.started_at and job.completed_at:
                durations.append((job.completed_at - job.started_at).total_seconds())
            if job.created_at and job.completed_at:
                end_to_end_durations.append((job.completed_at - job.created_at).total_seconds())
            if job.status in (JobStatus.failed, JobStatus.timed_out) and len(recent_failures) < 10:
                recent_failures.append({
                    "job_id": str(job.id),
                    "project_id": str(job.project_id),
                    "year": job.year,
                    "status": job.status.value,
                    "error_message": job.error_message,
                    "completed_at": job.completed_at.isoformat() if job.completed_at else None,
                })

        completed = by_status.get(JobStatus.completed.value, 0)
        failed = by_status.get(JobStatus.failed.value, 0)
        timed_out = by_status.get(JobStatus.timed_out.value, 0)
        canceled = by_status.get(JobStatus.canceled.value, 0)
        terminal = completed + failed + timed_out + canceled
        outbox_filters = []
        if project_id is not None:
            outbox_filters.append(ImportEventOutbox.project_id == project_id)
        if year is not None:
            outbox_filters.append(ImportEventOutbox.year == year)
        outbox_stmt = sa.select(ImportEventOutbox.status, sa.func.count()).group_by(ImportEventOutbox.status)
        if outbox_filters:
            outbox_stmt = outbox_stmt.where(*outbox_filters)
        outbox_rows = (await db.execute(outbox_stmt)).all()
        outbox_by_status = {
            status.value if hasattr(status, "value") else str(status): int(count)
            for status, count in outbox_rows
        }
        outbox_backlog_count = (
            outbox_by_status.get(OutboxStatus.pending.value, 0)
            + outbox_by_status.get(OutboxStatus.failed.value, 0)
        )
        throughput_per_hour = round(terminal / max(1, hours), 3)
        thresholds = cls._thresholds()

        return {
            "window_hours": max(1, hours),
            "total_jobs": total,
            "terminal_jobs": terminal,
            "active_jobs": active_count,
            "by_status": by_status,
            "success_rate": round(completed / terminal, 4) if terminal else None,
            "failure_rate": round((failed + timed_out) / terminal, 4) if terminal else None,
            "timeout_rate": round(timed_out / terminal, 4) if terminal else None,
            "retry_total": retry_total,
            "duration_seconds": {
                "avg": round(sum(durations) / len(durations), 3) if durations else None,
                "p95": cls._percentile(durations, 0.95),
                "p99": cls._percentile(durations, 0.99),
            },
            "enterprise_kpis": {
                "queue_delay_seconds": {
                    "avg": round(sum(queue_delays) / len(queue_delays), 3) if queue_delays else None,
                    "p95": cls._percentile(queue_delays, 0.95),
                },
                "end_to_end_seconds": {
                    "avg": round(sum(end_to_end_durations) / len(end_to_end_durations), 3) if end_to_end_durations else None,
                    "p95": cls._percentile(end_to_end_durations, 0.95),
                },
                "throughput_jobs_per_hour": throughput_per_hour,
                "outbox_backlog_count": outbox_backlog_count,
            },
            "alert_thresholds": thresholds,
            "recent_failures": recent_failures,
        }

    @classmethod
    async def get_runner_health(cls, db: AsyncSession) -> dict:
        """Report whether queued import jobs have an execution path."""
        now = datetime.now(timezone.utc)
        thresholds = cls._thresholds()
        queue_warn_seconds = thresholds["queue_delay_p95_warn_seconds"]
        stale_cutoff = now - timedelta(minutes=20)
        running_statuses = (
            JobStatus.running,
            JobStatus.validating,
            JobStatus.writing,
            JobStatus.activating,
        )

        queued_result = await db.execute(
            sa.select(sa.func.count(), sa.func.min(ImportJob.created_at)).where(
                ImportJob.status == JobStatus.queued,
            )
        )
        queued_count, oldest_queued_at = queued_result.one()
        active_count = int((await db.execute(
            sa.select(sa.func.count()).where(ImportJob.status.in_(running_statuses))
        )).scalar_one() or 0)
        stale_running_count = int((await db.execute(
            sa.select(sa.func.count()).where(
                ImportJob.status.in_(running_statuses),
                sa.or_(
                    sa.and_(
                        ImportJob.heartbeat_at.is_(None),
                        ImportJob.started_at.isnot(None),
                        ImportJob.started_at < stale_cutoff,
                    ),
                    ImportJob.heartbeat_at < stale_cutoff,
                ),
            )
        )).scalar_one() or 0)

        oldest_queued_age_seconds = None
        if oldest_queued_at is not None:
            oldest_queued_age_seconds = max(0, round((now - oldest_queued_at).total_seconds(), 3))

        alerts: list[dict] = []
        status = "healthy"
        in_process_enabled = bool(settings.LEDGER_IMPORT_IN_PROCESS_RUNNER_ENABLED)
        if not in_process_enabled and int(queued_count or 0) > 0:
            status = "degraded"
            alerts.append({
                "level": "warning",
                "code": "IMPORT_RUNNER_EXTERNAL_REQUIRED",
                "message": "进程内导入 runner 已关闭，queued 作业需要独立 import_worker 消费",
            })
        if oldest_queued_age_seconds is not None and oldest_queued_age_seconds > queue_warn_seconds:
            status = "degraded"
            alerts.append({
                "level": "warning",
                "code": "IMPORT_QUEUED_TOO_LONG",
                "message": f"最老导入作业排队超过 {queue_warn_seconds} 秒",
            })
        if stale_running_count > 0:
            status = "degraded"
            alerts.append({
                "level": "warning",
                "code": "IMPORT_RUNNING_HEARTBEAT_STALE",
                "message": "存在心跳疑似失联的导入作业",
            })

        return {
            "status": status,
            "runner_mode": "in_process" if in_process_enabled else "external_worker_required",
            "in_process_runner_enabled": in_process_enabled,
            "worker_poll_interval_seconds": int(settings.LEDGER_IMPORT_WORKER_POLL_INTERVAL_SECONDS),
            "worker_batch_size": int(settings.LEDGER_IMPORT_WORKER_BATCH_SIZE),
            "queued_count": int(queued_count or 0),
            "oldest_queued_at": oldest_queued_at.isoformat() if oldest_queued_at else None,
            "oldest_queued_age_seconds": oldest_queued_age_seconds,
            "active_count": active_count,
            "stale_running_count": stale_running_count,
            "queue_age_warn_seconds": queue_warn_seconds,
            "alerts": alerts,
        }

    @staticmethod
    def build_alerts(summary: dict) -> list[dict]:
        alerts: list[dict] = []
        thresholds = ImportSLOService._thresholds()
        failure_rate = summary.get("failure_rate")
        timeout_rate = summary.get("timeout_rate")
        p95 = (summary.get("duration_seconds") or {}).get("p95")
        queue_p95 = ((summary.get("enterprise_kpis") or {}).get("queue_delay_seconds") or {}).get("p95")
        outbox_backlog = (summary.get("enterprise_kpis") or {}).get("outbox_backlog_count")
        failure_rate_warn = thresholds["failure_rate_warn"]
        timeout_rate_critical = thresholds["timeout_rate_critical"]
        p95_duration_warn_seconds = thresholds["p95_duration_warn_seconds"]
        queue_delay_warn_seconds = thresholds["queue_delay_p95_warn_seconds"]
        outbox_backlog_warn_count = thresholds["outbox_backlog_warn_count"]
        active_jobs_warn_count = thresholds["active_jobs_warn_count"]
        if failure_rate is not None and failure_rate > failure_rate_warn:
            alerts.append({
                "level": "warning",
                "code": "IMPORT_FAILURE_RATE_HIGH",
                "message": f"导入失败率超过 {round(failure_rate_warn * 100, 2)}%",
            })
        if timeout_rate is not None and timeout_rate > timeout_rate_critical:
            alerts.append({
                "level": "critical",
                "code": "IMPORT_TIMEOUT_RATE_HIGH",
                "message": f"导入超时率超过 {round(timeout_rate_critical * 100, 2)}%",
            })
        if p95 is not None and p95 > p95_duration_warn_seconds:
            alerts.append({
                "level": "warning",
                "code": "IMPORT_P95_SLOW",
                "message": f"导入 P95 耗时超过 {p95_duration_warn_seconds} 秒",
            })
        if queue_p95 is not None and queue_p95 > queue_delay_warn_seconds:
            alerts.append({
                "level": "warning",
                "code": "IMPORT_QUEUE_DELAY_HIGH",
                "message": f"导入排队 P95 超过 {queue_delay_warn_seconds} 秒",
            })
        if outbox_backlog is not None and outbox_backlog > outbox_backlog_warn_count:
            alerts.append({
                "level": "warning",
                "code": "IMPORT_OUTBOX_BACKLOG_HIGH",
                "message": f"导入事件 outbox 积压超过 {outbox_backlog_warn_count}",
            })
        if summary.get("active_jobs", 0) > active_jobs_warn_count:
            alerts.append({
                "level": "warning",
                "code": "IMPORT_QUEUE_DEPTH_HIGH",
                "message": f"导入活跃队列超过 {active_jobs_warn_count} 个作业",
            })
        return alerts
