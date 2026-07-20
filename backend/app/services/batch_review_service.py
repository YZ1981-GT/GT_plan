"""批量复核编排服务

对一个科目的所有底稿逐份调用 LLM 复核，容错续行，汇总结果。

Requirements: 4.1, 4.2, 4.3, 4.4, 5.1, 5.2, 5.3, 5.4
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx
from sqlalchemy import text

from app.core.config import settings
from app.core.database import async_session
from app.services.llm_client import chat_completion
from app.services.llm_response_parser import LlmResponseParser, ReviewFinding
from app.services.review_prompt_service import ReviewPromptService

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 数据类
# ---------------------------------------------------------------------------


@dataclass
class ReviewResult:
    """单底稿复核结果"""

    wp_id: str
    sheet_name: str
    wp_code: str
    pass_status: str  # "pass" | "fail" | "review_error" | "manual_review_required"
    findings: list[ReviewFinding]
    risk_summary: dict[str, int]
    reviewed_at: str  # ISO datetime
    model_used: str
    prompt_source: str
    error_message: str | None = None


@dataclass
class BatchStatistics:
    """批量复核统计"""

    total_sheets: int
    passed_count: int
    failed_count: int
    error_count: int
    total_findings: int
    findings_by_risk: dict[str, int]


@dataclass
class ExecutionMetadata:
    """执行元数据"""

    start_time: str
    end_time: str
    duration_seconds: float
    model_used: str


@dataclass
class BatchReviewReport:
    """批量复核报告"""

    session_id: str
    wp_code_prefix: str
    project_id: str
    results: list[ReviewResult]
    statistics: BatchStatistics
    execution: ExecutionMetadata


# ---------------------------------------------------------------------------
# 服务类
# ---------------------------------------------------------------------------


class BatchReviewService:
    """批量复核编排服务

    Requirements: 4.1, 4.2, 4.3, 4.4
    """

    def __init__(self):
        self._prompt_service = ReviewPromptService()

    async def execute_batch(
        self,
        project_id: str,
        wp_code_prefix: str,
        year: int,
        progress_callback: "Callable[[int, int, str], None] | None" = None,
    ) -> BatchReviewReport:
        """执行批量复核

        1. 查 wp_index + working_paper 获取该前缀下所有底稿
        2. 对每张底稿获取 render-config 内容
        3. 逐份调用 LLM 复核（顺序执行，避免 LLM 并发压力）
        4. 解析结果
        5. 持久化结果
        6. 汇总统计返回

        Requirements: 4.1, 4.2, 4.3, 4.4, 5.1, 5.2, 5.3, 5.4
        """
        session_id = str(uuid.uuid4())
        start_time = datetime.now(timezone.utc)
        model_used = settings.DEFAULT_CHAT_MODEL

        # 1. 查询该前缀下所有底稿
        sheets = await self._get_sheets_for_prefix(project_id, wp_code_prefix)

        if not sheets:
            # 无底稿返回空报告
            end_time = datetime.now(timezone.utc)
            return BatchReviewReport(
                session_id=session_id,
                wp_code_prefix=wp_code_prefix,
                project_id=project_id,
                results=[],
                statistics=BatchStatistics(
                    total_sheets=0,
                    passed_count=0,
                    failed_count=0,
                    error_count=0,
                    total_findings=0,
                    findings_by_risk={"high": 0, "medium": 0, "low": 0},
                ),
                execution=ExecutionMetadata(
                    start_time=start_time.isoformat(),
                    end_time=end_time.isoformat(),
                    duration_seconds=0.0,
                    model_used=model_used,
                ),
            )

        # 2. 逐份复核（顺序执行，避免 LLM 并发压力）
        results: list[ReviewResult] = []
        for idx, sheet in enumerate(sheets):
            if progress_callback:
                try:
                    progress_callback(idx, len(sheets), sheet.get("sheet_name", ""))
                except Exception:
                    pass
            result = await self._review_single_sheet(
                sheet, session_id, model_used
            )
            results.append(result)

        # 3. 汇总统计
        end_time = datetime.now(timezone.utc)
        duration = (end_time - start_time).total_seconds()
        statistics = self._compute_statistics(results)

        # 4. 持久化结果 (Requirements: 5.1, 5.2, 5.3, 5.4)
        await self.persist_review_results(
            project_id=project_id,
            session_id=session_id,
            wp_code_prefix=wp_code_prefix,
            results=results,
            statistics=statistics,
        )

        return BatchReviewReport(
            session_id=session_id,
            wp_code_prefix=wp_code_prefix,
            project_id=project_id,
            results=results,
            statistics=statistics,
            execution=ExecutionMetadata(
                start_time=start_time.isoformat(),
                end_time=end_time.isoformat(),
                duration_seconds=duration,
                model_used=model_used,
            ),
        )

    # ------------------------------------------------------------------
    # 持久化方法 (Requirements: 5.1, 5.2, 5.3, 5.4)
    # ------------------------------------------------------------------

    async def persist_review_results(
        self,
        project_id: str,
        session_id: str,
        wp_code_prefix: str,
        results: list[ReviewResult],
        statistics: BatchStatistics,
    ) -> None:
        """持久化复核结果到数据库

        Append-only：不覆盖旧记录 (Requirement 5.3)

        1. 每条 ReviewFinding → ai_content 表 (content_type='review_finding')
        2. 复核会话索引 → checklist_responses 表

        Requirements: 5.1, 5.2, 5.3, 5.4
        """
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")

        try:
            async with async_session() as db:
                # 1. 持久化每条 ReviewFinding 到 ai_content 表
                for result in results:
                    if result.pass_status == "review_error":
                        # 错误的底稿不写 findings，但仍可写会话索引
                        continue

                    for finding in result.findings:
                        data_sources = {
                            "sheet_name": result.sheet_name,
                            "risk_level": finding.risk_level,
                            "pass_status": str(finding.pass_status),
                            "category": finding.category,
                            "session_id": session_id,
                            "wp_code": result.wp_code,
                        }
                        await db.execute(
                            text(
                                "INSERT INTO ai_content "
                                "(id, project_id, workpaper_id, content_type, "
                                "content_text, data_sources, created_at) "
                                "VALUES (:id, :project_id, :workpaper_id, "
                                "'review_finding', :content_text, :data_sources, :now)"
                            ),
                            {
                                "id": str(uuid.uuid4()),
                                "project_id": project_id,
                                "workpaper_id": result.wp_id,
                                "content_text": finding.description,
                                "data_sources": json.dumps(
                                    data_sources, ensure_ascii=False
                                ),
                                "now": datetime.now(timezone.utc),
                            },
                        )

                # 2. 写复核会话索引到 checklist_responses 表
                #    item_id pattern: {wp_code}-review-session-{timestamp}
                #    需要一个 wp_id 关联，使用第一个结果的 wp_id
                if results:
                    # 获取 project 关联的首个 wp_id 用于 checklist_responses
                    first_wp_id = results[0].wp_id
                    item_id = f"{wp_code_prefix}-review-session-{timestamp}"
                    session_stats = {
                        "session_id": session_id,
                        "wp_code_prefix": wp_code_prefix,
                        "total_sheets": statistics.total_sheets,
                        "passed_count": statistics.passed_count,
                        "failed_count": statistics.failed_count,
                        "error_count": statistics.error_count,
                        "total_findings": statistics.total_findings,
                        "findings_by_risk": statistics.findings_by_risk,
                        "timestamp": timestamp,
                    }
                    await db.execute(
                        text(
                            "INSERT INTO checklist_responses "
                            "(id, project_id, wp_id, item_id, remark, "
                            "created_at, updated_at) "
                            "VALUES (:id, :project_id, :wp_id, :item_id, "
                            ":remark, :now, :now)"
                        ),
                        {
                            "id": str(uuid.uuid4()),
                            "project_id": project_id,
                            "wp_id": first_wp_id,
                            "item_id": item_id,
                            "remark": json.dumps(
                                session_stats, ensure_ascii=False
                            ),
                            "now": datetime.now(timezone.utc),
                        },
                    )

                await db.commit()
                logger.info(
                    "Persisted review results: session_id=%s, findings=%d, item_id=%s",
                    session_id,
                    sum(len(r.findings) for r in results if r.pass_status != "review_error"),
                    f"{wp_code_prefix}-review-session-{timestamp}",
                )

        except Exception as e:
            logger.error(
                "Failed to persist review results for session %s: %s",
                session_id, e,
            )
            # 持久化失败不阻断报告返回，仅记日志

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    async def _get_sheets_for_prefix(
        self, project_id: str, wp_code_prefix: str
    ) -> list[dict]:
        """查 wp_index + working_paper 获取前缀下所有底稿

        Returns:
            list of {wp_id, wp_code, sheet_name}
        """
        async with async_session() as db:
            result = await db.execute(
                text(
                    "SELECT wp.id AS wp_id, wi.wp_code, wi.wp_name AS sheet_name "
                    "FROM working_paper wp "
                    "JOIN wp_index wi ON wp.wp_index_id = wi.id "
                    "WHERE wp.project_id = :project_id "
                    "AND wi.wp_code LIKE :prefix "
                    "AND wp.is_deleted = false "
                    "ORDER BY wi.wp_code"
                ),
                {
                    "project_id": project_id,
                    "prefix": f"{wp_code_prefix}%",
                },
            )
            rows = result.fetchall()
            return [
                {
                    "wp_id": str(row[0]),
                    "wp_code": row[1],
                    "sheet_name": row[2] or "",
                }
                for row in rows
            ]

    async def _review_single_sheet(
        self, sheet: dict, session_id: str, model_used: str
    ) -> ReviewResult:
        """对单张底稿执行复核

        单底稿失败标记 review_error 继续下一张（容错续行）
        Requirements: 4.4
        """
        wp_id = sheet["wp_id"]
        wp_code = sheet["wp_code"]
        sheet_name = sheet["sheet_name"]

        try:
            # 1. 加载提示词
            prompt_result = self._prompt_service.load_prompt(wp_code, sheet_name)

            # 2. 获取底稿内容
            workpaper_content = await self._get_workpaper_content(wp_id, sheet_name)

            # 3. 调用 LLM
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

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
            raw_response = await chat_completion(
                messages=messages,
                temperature=0.1,  # was 0.3 — 复核任务不需要创造性
                max_tokens=3000,
            )

            if not isinstance(raw_response, str):
                raw_response = ""

            # 4. 检查 LLM 是否返回了错误/降级标记
            if raw_response.startswith("[") and ("不可用" in raw_response or "失败" in raw_response or "超时" in raw_response or "熔断" in raw_response):
                return ReviewResult(
                    wp_id=wp_id,
                    sheet_name=sheet_name,
                    wp_code=wp_code,
                    pass_status="review_error",
                    findings=[],
                    risk_summary={"high": 0, "medium": 0, "low": 0},
                    reviewed_at=datetime.now(timezone.utc).isoformat(),
                    model_used=model_used,
                    prompt_source=prompt_result.source_level,
                    error_message=raw_response,
                )

            # 5. 解析
            parse_result = LlmResponseParser.parse(raw_response)
            pass_status = LlmResponseParser.determine_pass_status(parse_result.findings)

            # 如果解析失败且降级为 unknown，标记 manual_review_required
            if not parse_result.parse_success:
                pass_status = "manual_review_required"

            # 计算风险汇总
            risk_summary = {"high": 0, "medium": 0, "low": 0}
            for f in parse_result.findings:
                if not f.pass_status and f.risk_level in risk_summary:
                    risk_summary[f.risk_level] += 1

            return ReviewResult(
                wp_id=wp_id,
                sheet_name=sheet_name,
                wp_code=wp_code,
                pass_status=pass_status,
                findings=parse_result.findings,
                risk_summary=risk_summary,
                reviewed_at=datetime.now(timezone.utc).isoformat(),
                model_used=model_used,
                prompt_source=prompt_result.source_level,
                error_message=None,
            )

        except Exception as e:
            # 容错续行：单底稿失败标记 review_error (Req 4.4)
            logger.warning(
                "Batch review failed for sheet %s (%s): %s",
                sheet_name, wp_code, e,
            )
            return ReviewResult(
                wp_id=wp_id,
                sheet_name=sheet_name,
                wp_code=wp_code,
                pass_status="review_error",
                findings=[],
                risk_summary={"high": 0, "medium": 0, "low": 0},
                reviewed_at=datetime.now(timezone.utc).isoformat(),
                model_used=model_used,
                prompt_source="unknown",
                error_message=str(e),
            )

    async def _get_workpaper_content(self, wp_id: str, sheet_name: str | None) -> str:
        """获取底稿内容（从 render-config 提取 html_data 文本）"""
        try:
            url = f"http://localhost:{settings.PORT or 9980}/api/workpapers/{wp_id}/render-config"
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(url)
                if resp.status_code != 200:
                    return "(底稿内容获取失败)"

                data = resp.json()
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
                if not target_sheet:
                    target_sheet = sheets[0]

                html_data = target_sheet.get("html_data", {}) or {}
                return self._extract_text_from_html_data(html_data)

        except Exception as e:
            logger.warning("Failed to get workpaper content for %s: %s", wp_id, e)
            return "(底稿内容获取异常)"

    @staticmethod
    def _extract_text_from_html_data(html_data: dict) -> str:
        """从 html_data 提取关键文本内容"""
        import json

        parts: list[str] = []

        for key in ("responses_snapshot", "allResponses", "checklist_responses"):
            val = html_data.get(key)
            if val and isinstance(val, (dict, list)):
                text_repr = json.dumps(val, ensure_ascii=False, indent=None)
                if len(text_repr) > 5000:
                    text_repr = text_repr[:5000] + "...(已截断)"
                parts.append(f"[{key}]\n{text_repr}")

        tb_values = html_data.get("tb_values")
        if tb_values and isinstance(tb_values, dict):
            tb_text = json.dumps(tb_values, ensure_ascii=False, indent=None)
            if len(tb_text) > 2000:
                tb_text = tb_text[:2000] + "...(已截断)"
            parts.append(f"[试算表数据]\n{tb_text}")

        if not parts:
            fallback = json.dumps(html_data, ensure_ascii=False, indent=None)
            if len(fallback) > 6000:
                fallback = fallback[:6000] + "...(已截断)"
            parts.append(f"[底稿数据]\n{fallback}")

        return "\n\n".join(parts)

    @staticmethod
    def _compute_statistics(results: list[ReviewResult]) -> BatchStatistics:
        """汇总批量复核统计

        Requirements: 4.3
        """
        total_sheets = len(results)
        passed_count = sum(1 for r in results if r.pass_status == "pass")
        failed_count = sum(1 for r in results if r.pass_status == "fail")
        error_count = sum(
            1 for r in results
            if r.pass_status in ("review_error", "manual_review_required")
        )
        total_findings = sum(len(r.findings) for r in results)

        findings_by_risk: dict[str, int] = {"high": 0, "medium": 0, "low": 0}
        for r in results:
            for f in r.findings:
                if not f.pass_status and f.risk_level in findings_by_risk:
                    findings_by_risk[f.risk_level] += 1

        return BatchStatistics(
            total_sheets=total_sheets,
            passed_count=passed_count,
            failed_count=failed_count,
            error_count=error_count,
            total_findings=total_findings,
            findings_by_risk=findings_by_risk,
        )
