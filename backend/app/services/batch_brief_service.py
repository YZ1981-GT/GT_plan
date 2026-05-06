"""批量简报服务 — Round 2 需求 6

POST /api/projects/briefs/batch
- 走 ExportJobService 异步，内部循环调 ProgressBriefService.generate
- AI 模式拼完后走 unified_ai_service 做综合总结，失败回退纯拼接
- 结果存 ExportTaskService 历史，7 天内相同项目组合复用
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.models.phase13_models import ExportJob, ExportJobStatus, WordExportTask
from app.services.export_job_service import ExportJobService
from app.services.pm_service import ProgressBriefService
from app.services.unified_ai_service import UnifiedAIService

logger = logging.getLogger(__name__)

# 缓存有效期（天）
CACHE_TTL_DAYS = 7


def _compute_cache_key(project_ids: list[UUID], use_ai: bool) -> str:
    """根据项目组合 + AI 模式计算缓存键。

    Batch 1 Fix 1.10: 用 MD5 前 16 字符（适配 WordExportTask.template_type String(20)）。
    """
    sorted_ids = sorted(str(pid) for pid in project_ids)
    raw = json.dumps({"project_ids": sorted_ids, "use_ai": use_ai}, sort_keys=True)
    return hashlib.md5(raw.encode()).hexdigest()[:16]


class BatchBriefService:
    """批量简报生成服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def find_cached_result(
        self, project_ids: list[UUID], use_ai: bool
    ) -> WordExportTask | None:
        """查找 7 天内相同项目组合的缓存结果"""
        cache_key = _compute_cache_key(project_ids, use_ai)
        cutoff = datetime.now(timezone.utc) - timedelta(days=CACHE_TTL_DAYS)

        result = await self.db.execute(
            sa.select(WordExportTask).where(
                WordExportTask.doc_type == "batch_brief",
                WordExportTask.status == "generated",
                WordExportTask.created_at >= cutoff,
                # Batch 3 Fix 2: 用专用 cache_key 字段查找
                WordExportTask.cache_key == cache_key,
            ).order_by(WordExportTask.created_at.desc()).limit(1)
        )
        return result.scalar_one_or_none()

    async def create_batch_brief_job(
        self,
        project_ids: list[UUID],
        use_ai: bool,
        user_id: UUID,
    ) -> UUID:
        """创建批量简报异步任务，返回 export_job_id

        超过 6 个项目时强制走后台任务（设计文档要求）。
        """
        # 检查缓存
        cached = await self.find_cached_result(project_ids, use_ai)
        if cached:
            logger.info("命中批量简报缓存: task_id=%s", cached.id)
            # 创建一个已完成的 job 指向缓存结果
            job_svc = ExportJobService(self.db)
            # 使用第一个 project_id 作为 job 的 project_id（ExportJob 要求单个 project_id）
            job = await job_svc.create_job(
                project_id=project_ids[0],
                job_type="batch_brief",
                payload={
                    "project_ids": [str(pid) for pid in project_ids],
                    "use_ai": use_ai,
                    "cached_task_id": str(cached.id),
                },
                user_id=user_id,
                total=len(project_ids),
            )
            # 直接标记为成功
            job.status = ExportJobStatus.succeeded.value
            job.progress_done = len(project_ids)
            await self.db.flush()
            return job.id

        # 创建新的异步任务
        job_svc = ExportJobService(self.db)
        job = await job_svc.create_job(
            project_id=project_ids[0],
            job_type="batch_brief",
            payload={
                "project_ids": [str(pid) for pid in project_ids],
                "use_ai": use_ai,
            },
            user_id=user_id,
            total=len(project_ids),
        )
        return job.id

    async def execute_batch_brief(
        self,
        job_id: UUID,
        project_ids: list[UUID],
        use_ai: bool,
        user_id: UUID,
    ) -> dict[str, Any]:
        """执行批量简报生成（由后台任务调用）

        1. 逐项目调 ProgressBriefService.generate
        2. 拼接所有简报
        3. AI 模式下调 unified_ai_service 做综合总结
        4. 失败回退纯拼接
        5. 存 ExportTaskService 历史
        """
        job_svc = ExportJobService(self.db)
        brief_svc = ProgressBriefService(self.db)

        # 标记任务开始
        job = await job_svc.get_job(job_id)
        if job:
            job.status = ExportJobStatus.running.value
            await self.db.flush()

        # 逐项目生成简报
        briefs: list[dict[str, Any]] = []
        done = 0
        failed = 0

        for pid in project_ids:
            try:
                brief = await brief_svc.generate_brief(pid, polish_with_llm=False)
                briefs.append(brief)
                done += 1
            except Exception as e:
                logger.warning("项目 %s 简报生成失败: %s", pid, e)
                briefs.append({
                    "project_name": str(pid),
                    "text_summary": f"⚠️ 简报生成失败: {e}",
                    "raw_summary": f"生成失败: {e}",
                    "completion_rate": 0,
                    "error": str(e),
                })
                failed += 1

            # 更新进度
            await job_svc.update_progress(job_id, done=done, failed=failed)

        # 拼接所有简报
        combined_text = self._combine_briefs(briefs)

        # AI 综合总结
        ai_summary: str | None = None
        ai_fallback_reason: str | None = None
        if use_ai and briefs:
            ai_summary, ai_fallback_reason = await self._generate_ai_summary_with_reason(combined_text)

        # 构建最终结果
        final_text = ai_summary if ai_summary else combined_text
        result = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "project_count": len(project_ids),
            "briefs": briefs,
            "combined_text": combined_text,
            "ai_summary": ai_summary,
            "final_text": final_text,
            "use_ai": use_ai,
            "ai_used": ai_summary is not None,
            "ai_fallback_reason": ai_fallback_reason,
        }

        # 存入 ExportTaskService 历史（复用 WordExportTask 表）
        cache_key = _compute_cache_key(project_ids, use_ai)
        task = WordExportTask(
            project_id=project_ids[0],
            doc_type="batch_brief",
            status="generated",
            template_type="batch_brief",  # Batch 3 Fix 2: 恢复 template_type 原始语义
            cache_key=cache_key,  # Batch 3 Fix 2: 专用缓存键字段
            file_path=json.dumps(result, ensure_ascii=False, default=str),
            created_by=user_id,
        )
        self.db.add(task)
        await self.db.flush()

        # 更新 job payload 记录结果 task_id
        job = await job_svc.get_job(job_id)
        if job:
            payload = dict(job.payload or {})
            payload["result_task_id"] = str(task.id)
            job.payload = payload
            flag_modified(job, "payload")
            # 确保最终状态正确
            if failed == 0:
                job.status = ExportJobStatus.succeeded.value
            elif done > 0:
                job.status = ExportJobStatus.partial_failed.value
            else:
                job.status = ExportJobStatus.failed.value
            await self.db.flush()

        return result

    def _combine_briefs(self, briefs: list[dict[str, Any]]) -> str:
        """拼接多项目简报为统一文档"""
        lines = [
            "# 跨项目合并简报",
            "",
            f"**生成时间**：{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC",
            f"**项目数量**：{len(briefs)}",
            "",
            "---",
            "",
        ]

        for i, brief in enumerate(briefs, 1):
            project_name = brief.get("project_name", f"项目 {i}")
            completion_rate = brief.get("completion_rate", 0)
            lines.append(f"## {i}. {project_name}")
            lines.append("")
            lines.append(f"**完成率**：{completion_rate}%")
            lines.append("")

            # 使用 raw_summary 作为各项目内容
            raw = brief.get("raw_summary", brief.get("text_summary", ""))
            # 去掉原始简报的顶级标题（避免重复）
            raw_lines = raw.split("\n")
            filtered = [
                line for line in raw_lines
                if not line.startswith("## ") or "项目进度简报" not in line
            ]
            lines.append("\n".join(filtered))
            lines.append("")
            lines.append("---")
            lines.append("")

        # 综合风险汇总
        lines.append("## 综合风险汇总")
        lines.append("")
        rejected_projects = [
            b["project_name"] for b in briefs
            if b.get("rejected_count", 0) > 0
        ]
        if rejected_projects:
            lines.append(f"⚠️ 以下项目有退回底稿需关注：{', '.join(rejected_projects)}")
        else:
            lines.append("✅ 所有项目无退回底稿。")
        lines.append("")

        low_rate_projects = [
            f"{b['project_name']}({b.get('completion_rate', 0)}%)"
            for b in briefs
            if b.get("completion_rate", 0) < 50
        ]
        if low_rate_projects:
            lines.append(f"⚠️ 以下项目完成率低于 50%：{', '.join(low_rate_projects)}")
        lines.append("")

        return "\n".join(lines)

    async def _generate_ai_summary(self, combined_text: str) -> str | None:
        """调用 unified_ai_service 生成综合总结，失败返回 None（回退纯拼接）

        Batch 1 Fix 1.8: 截断 combined_text 到 MAX_AI_INPUT_CHARS 避免超模型 context window。
        """
        # Batch 1 Fix 1.8: 限制输入长度（Qwen3.5-27B context ~32k tokens ≈ 48k chars 中文）
        MAX_AI_INPUT_CHARS = 24000
        truncated_text = combined_text[:MAX_AI_INPUT_CHARS]
        if len(combined_text) > MAX_AI_INPUT_CHARS:
            truncated_text += "\n\n[... 内容已截断，仅展示前 24000 字符 ...]"

        try:
            ai_svc = UnifiedAIService(self.db)
            prompt = (
                "你是一位资深审计项目经理。以下是多个审计项目的进度简报汇总。"
                "请生成一份综合总结，适合在周会上向合伙人汇报。要求：\n"
                "1. 用 Markdown 格式\n"
                "2. 开头概述整体情况（几个项目、平均完成率、最大风险）\n"
                "3. 按风险等级排序各项目关键信息\n"
                "4. 结尾给出本周重点关注事项和建议\n"
                "5. 语言正式简洁，突出关键数字\n\n"
                f"各项目简报数据：\n\n{truncated_text}"
            )
            result = await ai_svc.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.4,
            )
            if result and isinstance(result, str) and not result.startswith("[LLM"):
                return result
            logger.warning("AI 综合总结返回无效结果，回退纯拼接")
            return None
        except Exception as e:
            logger.warning("AI 综合总结失败，回退纯拼接: %s", e)
            return None

    async def _generate_ai_summary_with_reason(self, combined_text: str) -> tuple[str | None, str | None]:
        """调用 AI 生成综合总结，返回 (summary, fallback_reason)。

        成功时 fallback_reason=None，失败时 summary=None 且 fallback_reason 包含原因。
        """
        MAX_AI_INPUT_CHARS = 24000
        truncated_text = combined_text[:MAX_AI_INPUT_CHARS]
        if len(combined_text) > MAX_AI_INPUT_CHARS:
            truncated_text += "\n\n[... 内容已截断，仅展示前 24000 字符 ...]"

        try:
            ai_svc = UnifiedAIService(self.db)
            prompt = (
                "你是一位资深审计项目经理。以下是多个审计项目的进度简报汇总。"
                "请生成一份综合总结，适合在周会上向合伙人汇报。要求：\n"
                "1. 用 Markdown 格式\n"
                "2. 开头概述整体情况（几个项目、平均完成率、最大风险）\n"
                "3. 按风险等级排序各项目关键信息\n"
                "4. 结尾给出本周重点关注事项和建议\n"
                "5. 语言正式简洁，突出关键数字\n\n"
                f"各项目简报数据：\n\n{truncated_text}"
            )
            result = await ai_svc.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.4,
            )
            if result and isinstance(result, str) and not result.startswith("[LLM"):
                return result, None
            reason = "AI 返回无效结果（空或 [LLM 前缀），已回退纯拼接"
            logger.warning("AI 综合总结返回无效结果，回退纯拼接")
            return None, reason
        except Exception as e:
            reason = f"AI 调用异常: {e}"
            logger.warning("AI 综合总结失败，回退纯拼接: %s", e)
            return None, reason

    async def get_job_result(self, job_id: UUID) -> dict[str, Any] | None:
        """获取批量简报任务结果"""
        job_svc = ExportJobService(self.db)
        job = await job_svc.get_job(job_id)
        if not job:
            return None

        result: dict[str, Any] = {
            "job_id": str(job.id),
            "status": job.status,
            "progress_total": job.progress_total,
            "progress_done": job.progress_done,
            "failed_count": job.failed_count,
        }

        # 如果已完成，尝试获取结果
        if job.status == ExportJobStatus.succeeded.value:
            payload = job.payload or {}
            # 检查是否命中缓存
            cached_task_id = payload.get("cached_task_id")
            result_task_id = payload.get("result_task_id") or cached_task_id

            if result_task_id:
                task_result = await self.db.execute(
                    sa.select(WordExportTask).where(
                        WordExportTask.id == UUID(result_task_id)
                    )
                )
                task = task_result.scalar_one_or_none()
                if task and task.file_path:
                    try:
                        result["data"] = json.loads(task.file_path)
                    except (json.JSONDecodeError, TypeError):
                        result["data"] = {"final_text": task.file_path}

        return result
