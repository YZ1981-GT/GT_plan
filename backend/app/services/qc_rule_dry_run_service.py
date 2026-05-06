"""QC 规则试运行（dry-run）服务

Refinement Round 3 — 需求 2：
- 对采样底稿跑规则沙箱，不写 DB，返回命中率
- 耗时超过 60s 走 BackgroundJob 异步化
- dry-run 结果仅用于预览，不写入 wp_qc_results
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any, Optional
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.qc_rule_models import QcRuleDefinition
from app.models.workpaper_models import WorkingPaper, WpIndex
from app.services.qc_rule_executor import (
    RuleExecutionResult,
    execute_rule,
)

logger = logging.getLogger(__name__)

# 同步执行超时阈值（秒），超过则走异步
DRY_RUN_SYNC_TIMEOUT_SECONDS = 60

# 默认采样大小
DEFAULT_SAMPLE_SIZE = 50

# 最大采样大小（防止过大请求）
MAX_SAMPLE_SIZE = 500


class DryRunResult:
    """试运行结果"""

    def __init__(
        self,
        total_checked: int,
        hits: int,
        hit_rate: float,
        sample_findings: list[dict],
    ):
        self.total_checked = total_checked
        self.hits = hits
        self.hit_rate = hit_rate
        self.sample_findings = sample_findings

    def to_dict(self) -> dict:
        return {
            "total_checked": self.total_checked,
            "hits": self.hits,
            "hit_rate": self.hit_rate,
            "sample_findings": self.sample_findings,
        }


class QcRuleDryRunService:
    """QC 规则试运行服务"""

    async def run_dry_run(
        self,
        db: AsyncSession,
        rule: QcRuleDefinition,
        scope: str,
        project_ids: Optional[list[UUID]] = None,
        sample_size: Optional[int] = None,
    ) -> DryRunResult:
        """执行规则试运行。

        Args:
            db: 数据库会话
            rule: 规则定义
            scope: 'project' | 'all'
            project_ids: 项目 ID 列表（scope='project' 时必填）
            sample_size: 采样大小

        Returns:
            DryRunResult 试运行结果
        """
        effective_sample_size = min(
            sample_size or DEFAULT_SAMPLE_SIZE,
            MAX_SAMPLE_SIZE,
        )

        # 采样底稿
        workpapers = await self._sample_workpapers(
            db, rule.scope, scope, project_ids, effective_sample_size
        )

        if not workpapers:
            return DryRunResult(
                total_checked=0,
                hits=0,
                hit_rate=0.0,
                sample_findings=[],
            )

        # 对每张底稿执行规则（沙箱，不写 DB）
        findings: list[dict] = []
        hits = 0

        for wp in workpapers:
            result = await self._execute_rule_on_workpaper(rule, wp)
            if not result.passed:
                hits += 1
                # 收集 findings（限制数量避免响应过大）
                for f in result.findings[:3]:
                    findings.append({
                        "wp_id": str(wp.id),
                        "wp_code": wp.wp_code if hasattr(wp, "wp_code") else None,
                        "message": f.get("message", ""),
                        "severity": f.get("severity", rule.severity),
                    })

        total_checked = len(workpapers)
        hit_rate = round(hits / total_checked, 4) if total_checked > 0 else 0.0

        return DryRunResult(
            total_checked=total_checked,
            hits=hits,
            hit_rate=hit_rate,
            sample_findings=findings[:50],  # 最多返回 50 条 findings
        )

    async def should_run_async(
        self,
        db: AsyncSession,
        rule: QcRuleDefinition,
        scope: str,
        project_ids: Optional[list[UUID]] = None,
        sample_size: Optional[int] = None,
    ) -> bool:
        """判断是否应该走异步执行。

        当 sample_size > 100 时建议走异步。
        """
        effective_sample_size = sample_size or DEFAULT_SAMPLE_SIZE
        return effective_sample_size > 100

    async def _sample_workpapers(
        self,
        db: AsyncSession,
        rule_scope: str,
        request_scope: str,
        project_ids: Optional[list[UUID]],
        sample_size: int,
    ) -> list[Any]:
        """采样底稿。

        根据 rule.scope 和请求 scope 查询底稿：
        - rule_scope='workpaper': 查 working_paper 表
        - request_scope='project': 限定 project_ids
        - request_scope='all': 全部项目
        """
        # 构建查询：联合 WorkingPaper 和 WpIndex 获取 wp_code
        stmt = (
            sa.select(
                WorkingPaper.id,
                WorkingPaper.project_id,
                WorkingPaper.parsed_data,
                WpIndex.wp_code,
            )
            .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
            .where(
                WorkingPaper.is_deleted == False,  # noqa: E712
            )
        )

        # 按 scope 过滤
        if request_scope == "project" and project_ids:
            stmt = stmt.where(WorkingPaper.project_id.in_(project_ids))

        # 随机采样（使用 func.random() 排序 + limit）
        stmt = stmt.order_by(sa.func.random()).limit(sample_size)

        result = await db.execute(stmt)
        rows = result.all()

        # 转为简单对象供执行器使用
        return [
            _WorkpaperSample(
                id=row.id,
                project_id=row.project_id,
                parsed_data=row.parsed_data,
                wp_code=row.wp_code,
            )
            for row in rows
        ]

    async def _execute_rule_on_workpaper(
        self,
        rule: QcRuleDefinition,
        wp: "_WorkpaperSample",
    ) -> RuleExecutionResult:
        """对单张底稿执行规则（沙箱，不写 DB）。"""
        try:
            if rule.expression_type == "jsonpath":
                return await execute_rule(
                    rule,
                    parsed_data=wp.parsed_data or {},
                )
            elif rule.expression_type == "python":
                # Python 类型规则需要 context 对象
                context = _build_qc_context(wp)
                return await execute_rule(rule, context=context)
            else:
                # sql/regex 等未实现类型
                return RuleExecutionResult(
                    rule_code=rule.rule_code,
                    passed=True,
                    error=f"expression_type='{rule.expression_type}' 不支持 dry-run",
                )
        except Exception as e:
            logger.warning(
                "[DRY_RUN] Rule %s failed on wp %s: %s",
                rule.rule_code,
                wp.id,
                e,
            )
            return RuleExecutionResult(
                rule_code=rule.rule_code,
                passed=False,
                error=str(e),
            )


class _WorkpaperSample:
    """轻量底稿采样对象（不持有 ORM session）"""

    def __init__(
        self,
        id: UUID,
        project_id: UUID,
        parsed_data: dict | None,
        wp_code: str | None,
    ):
        self.id = id
        self.project_id = project_id
        self.parsed_data = parsed_data or {}
        self.wp_code = wp_code


def _build_qc_context(wp: _WorkpaperSample) -> Any:
    """构建 Python 类型规则所需的 QCContext 对象。

    尝试导入 QCContext，如果不存在则构建简单 dict-like 对象。
    """
    try:
        from app.services.qc_engine import QCContext

        return QCContext(
            wp_id=wp.id,
            project_id=wp.project_id,
            parsed_data=wp.parsed_data,
        )
    except (ImportError, TypeError):
        # 如果 QCContext 不可用或签名不匹配，用简单对象
        class _SimpleContext:
            def __init__(self, wp_id, project_id, parsed_data):
                self.wp_id = wp_id
                self.project_id = project_id
                self.parsed_data = parsed_data

        return _SimpleContext(
            wp_id=wp.id,
            project_id=wp.project_id,
            parsed_data=wp.parsed_data,
        )


# 单例
qc_rule_dry_run_service = QcRuleDryRunService()
