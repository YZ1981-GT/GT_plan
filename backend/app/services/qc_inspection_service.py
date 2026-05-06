"""QC 抽查服务 — Round 3 需求 4

提供质控抽查底稿的核心逻辑：
- create_inspection: 按策略生成抽查批次 + items
- record_verdict: QC 复核人录入结论
- get_inspection / list_inspections: 查询

四种抽样策略（纯函数）：
- random: 按 ratio 随机抽样
- risk_based: 抽 complexity>=high 或有退回记录的底稿
- full_cycle: 选定循环的全部底稿
- mixed: 组合前三种
"""

import logging
import math
import random
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.qc_inspection_models import (
    QcInspection,
    QcInspectionItem,
)
from app.models.workpaper_models import WorkingPaper, WpIndex

logger = logging.getLogger(__name__)

# 循环复杂度映射（复用 batch_assign_strategy 的逻辑）
_CYCLE_COMPLEXITY: dict[str, int] = {
    "D": 1,
    "F": 1,
    "K": 3,
    "N": 3,
}
_DEFAULT_COMPLEXITY = 2
# "high" 复杂度阈值：>=3 视为高复杂度
_HIGH_COMPLEXITY_THRESHOLD = 3


# ---------------------------------------------------------------------------
# 策略纯函数：输入底稿列表 + 参数，输出抽中的 wp_id 列表
# ---------------------------------------------------------------------------


def _sample_random(
    workpapers: list[dict],
    params: dict,
) -> list[uuid.UUID]:
    """随机抽样策略。

    params:
        ratio: float (0.0~1.0) — 抽样比例，如 0.1 表示 10%
    """
    ratio = params.get("ratio", 0.1)
    if ratio <= 0:
        return []
    if ratio >= 1.0:
        return [wp["id"] for wp in workpapers]

    sample_count = max(1, math.ceil(len(workpapers) * ratio))
    sample_count = min(sample_count, len(workpapers))
    sampled = random.sample(workpapers, sample_count)
    return [wp["id"] for wp in sampled]


def _sample_risk_based(
    workpapers: list[dict],
    params: dict,
) -> list[uuid.UUID]:
    """风险导向抽样策略。

    抽取 complexity >= high 或有退回记录的底稿。

    params:
        complexity_threshold: int — 复杂度阈值（默认 3）
        include_rejected: bool — 是否包含有退回记录的底稿（默认 True）
    """
    threshold = params.get("complexity_threshold", _HIGH_COMPLEXITY_THRESHOLD)
    include_rejected = params.get("include_rejected", True)

    result_ids: list[uuid.UUID] = []
    seen: set[uuid.UUID] = set()

    for wp in workpapers:
        if wp["id"] in seen:
            continue
        complexity = wp.get("complexity", _DEFAULT_COMPLEXITY)
        is_rejected = wp.get("has_rejection", False)

        if complexity >= threshold:
            result_ids.append(wp["id"])
            seen.add(wp["id"])
        elif include_rejected and is_rejected:
            result_ids.append(wp["id"])
            seen.add(wp["id"])

    return result_ids


def _sample_full_cycle(
    workpapers: list[dict],
    params: dict,
) -> list[uuid.UUID]:
    """全循环抽样策略。

    抽取选定循环的全部底稿。

    params:
        cycles: list[str] — 循环代码列表，如 ["D", "K"]
    """
    cycles = params.get("cycles", [])
    if not cycles:
        return []

    cycles_upper = {c.upper() for c in cycles}
    return [
        wp["id"]
        for wp in workpapers
        if wp.get("audit_cycle", "").upper() in cycles_upper
    ]


def _sample_mixed(
    workpapers: list[dict],
    params: dict,
) -> list[uuid.UUID]:
    """混合抽样策略。

    组合 random + risk_based + full_cycle 三种策略的结果（去重）。

    params:
        random_ratio: float — 随机抽样比例（默认 0.1）
        cycles: list[str] — 全循环抽样的循环代码
        complexity_threshold: int — 风险导向复杂度阈值
        include_rejected: bool — 是否包含退回底稿
    """
    result_ids: set[uuid.UUID] = set()

    # 1. 随机部分
    random_ratio = params.get("random_ratio", params.get("ratio", 0.1))
    random_ids = _sample_random(workpapers, {"ratio": random_ratio})
    result_ids.update(random_ids)

    # 2. 风险导向部分
    risk_ids = _sample_risk_based(workpapers, {
        "complexity_threshold": params.get("complexity_threshold", _HIGH_COMPLEXITY_THRESHOLD),
        "include_rejected": params.get("include_rejected", True),
    })
    result_ids.update(risk_ids)

    # 3. 全循环部分
    cycles = params.get("cycles", [])
    if cycles:
        cycle_ids = _sample_full_cycle(workpapers, {"cycles": cycles})
        result_ids.update(cycle_ids)

    return list(result_ids)


# 策略分派表
_STRATEGY_MAP = {
    "random": _sample_random,
    "risk_based": _sample_risk_based,
    "full_cycle": _sample_full_cycle,
    "mixed": _sample_mixed,
}


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class QcInspectionService:
    """质控抽查服务"""

    async def create_inspection(
        self,
        db: AsyncSession,
        *,
        project_id: uuid.UUID,
        strategy: str,
        params: dict | None,
        reviewer_id: uuid.UUID,
    ) -> dict:
        """创建抽查批次 + 生成抽查子项。

        1. 查询项目下所有底稿
        2. 按策略抽样
        3. 生成 QcInspection + QcInspectionItem 记录
        """
        if strategy not in _STRATEGY_MAP:
            raise HTTPException(
                status_code=422,
                detail={
                    "error_code": "INVALID_STRATEGY",
                    "message": f"不支持的抽样策略: {strategy}，可选: {list(_STRATEGY_MAP.keys())}",
                },
            )

        params = params or {}

        # 查询项目下所有底稿（join WpIndex 获取 audit_cycle）
        stmt = (
            select(
                WorkingPaper.id,
                WorkingPaper.review_status,
                WpIndex.audit_cycle,
                WpIndex.wp_code,
            )
            .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
            .where(
                WorkingPaper.project_id == project_id,
                WorkingPaper.is_deleted == False,  # noqa: E712
            )
        )
        result = await db.execute(stmt)
        rows = result.all()

        if not rows:
            raise HTTPException(
                status_code=404,
                detail={
                    "error_code": "NO_WORKPAPERS",
                    "message": "该项目下没有可抽查的底稿",
                },
            )

        # 构建底稿信息列表
        workpapers: list[dict] = []
        for row in rows:
            audit_cycle = row.audit_cycle or ""
            complexity = _CYCLE_COMPLEXITY.get(
                audit_cycle.upper(), _DEFAULT_COMPLEXITY
            )
            # 判断是否有退回记录
            review_status_str = (
                row.review_status.value
                if hasattr(row.review_status, "value")
                else str(row.review_status)
            )
            has_rejection = "rejected" in review_status_str

            workpapers.append({
                "id": row.id,
                "audit_cycle": audit_cycle,
                "complexity": complexity,
                "has_rejection": has_rejection,
                "wp_code": row.wp_code,
            })

        # 执行策略
        strategy_fn = _STRATEGY_MAP[strategy]
        sampled_ids = strategy_fn(workpapers, params)

        if not sampled_ids:
            raise HTTPException(
                status_code=422,
                detail={
                    "error_code": "EMPTY_SAMPLE",
                    "message": "按当前策略和参数未抽到任何底稿，请调整参数",
                },
            )

        # 限制每批次最多 50 张（设计文档约束）
        if len(sampled_ids) > 50:
            sampled_ids = sampled_ids[:50]

        # 创建 QcInspection
        inspection = QcInspection(
            id=uuid.uuid4(),
            project_id=project_id,
            strategy=strategy,
            params=params,
            reviewer_id=reviewer_id,
            status="created",
        )
        db.add(inspection)

        # 创建 QcInspectionItem
        items: list[QcInspectionItem] = []
        for wp_id in sampled_ids:
            item = QcInspectionItem(
                id=uuid.uuid4(),
                inspection_id=inspection.id,
                wp_id=wp_id,
                status="pending",
            )
            db.add(item)
            items.append(item)

        await db.flush()

        logger.info(
            "[QC_INSPECTION] created inspection=%s project=%s strategy=%s items=%d reviewer=%s",
            inspection.id,
            project_id,
            strategy,
            len(items),
            reviewer_id,
        )

        return self._inspection_to_dict(inspection, items)

    async def record_verdict(
        self,
        db: AsyncSession,
        *,
        inspection_id: uuid.UUID,
        item_id: uuid.UUID,
        verdict: str,
        findings: dict | None = None,
    ) -> dict:
        """QC 复核人录入结论。

        verdict: 'pass' | 'fail' | 'conditional_pass'
        findings: 可选的发现问题 JSONB
        """
        valid_verdicts = {"pass", "fail", "conditional_pass"}
        if verdict not in valid_verdicts:
            raise HTTPException(
                status_code=422,
                detail={
                    "error_code": "INVALID_VERDICT",
                    "message": f"无效的结论: {verdict}，可选: {list(valid_verdicts)}",
                },
            )

        # 查找 inspection item
        stmt = select(QcInspectionItem).where(
            QcInspectionItem.id == item_id,
            QcInspectionItem.inspection_id == inspection_id,
        )
        result = await db.execute(stmt)
        item = result.scalar_one_or_none()

        if item is None:
            raise HTTPException(
                status_code=404,
                detail="QC_INSPECTION_ITEM_NOT_FOUND",
            )

        # 更新 item
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        item.qc_verdict = verdict
        item.findings = findings
        item.status = "completed"
        item.completed_at = now

        # 检查是否所有 items 都已完成，如果是则更新 inspection 状态
        inspection_stmt = select(QcInspection).where(
            QcInspection.id == inspection_id
        )
        inspection_result = await db.execute(inspection_stmt)
        inspection = inspection_result.scalar_one_or_none()

        if inspection is None:
            raise HTTPException(
                status_code=404,
                detail="QC_INSPECTION_NOT_FOUND",
            )

        # 更新 inspection 状态为 in_progress（如果还是 created）
        if inspection.status == "created":
            inspection.status = "in_progress"
            inspection.started_at = now

        # 检查是否全部完成
        pending_count_stmt = (
            select(func.count())
            .select_from(QcInspectionItem)
            .where(
                QcInspectionItem.inspection_id == inspection_id,
                QcInspectionItem.status != "completed",
                QcInspectionItem.id != item_id,  # 排除当前刚更新的
            )
        )
        pending_count = (await db.execute(pending_count_stmt)).scalar() or 0

        if pending_count == 0:
            inspection.status = "completed"
            inspection.completed_at = now

        await db.flush()

        logger.info(
            "[QC_INSPECTION] verdict recorded inspection=%s item=%s verdict=%s",
            inspection_id,
            item_id,
            verdict,
        )

        return {
            "id": str(item.id),
            "inspection_id": str(item.inspection_id),
            "wp_id": str(item.wp_id),
            "status": item.status,
            "qc_verdict": item.qc_verdict,
            "findings": item.findings,
            "completed_at": item.completed_at.isoformat() if item.completed_at else None,
        }

    async def get_inspection(
        self,
        db: AsyncSession,
        inspection_id: uuid.UUID,
    ) -> dict:
        """获取抽查批次详情（含子项）。"""
        stmt = select(QcInspection).where(QcInspection.id == inspection_id)
        result = await db.execute(stmt)
        inspection = result.scalar_one_or_none()

        if inspection is None:
            raise HTTPException(
                status_code=404,
                detail="QC_INSPECTION_NOT_FOUND",
            )

        # 加载 items
        items_stmt = (
            select(QcInspectionItem)
            .where(QcInspectionItem.inspection_id == inspection_id)
            .order_by(QcInspectionItem.created_at.asc())
        )
        items_result = await db.execute(items_stmt)
        items = items_result.scalars().all()

        return self._inspection_to_dict(inspection, items)

    async def list_inspections(
        self,
        db: AsyncSession,
        *,
        project_id: Optional[uuid.UUID] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        """列出抽查批次，可按项目过滤。"""
        stmt = select(QcInspection).where(
            QcInspection.is_deleted == False  # noqa: E712
        )

        if project_id:
            stmt = stmt.where(QcInspection.project_id == project_id)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await db.execute(count_stmt)).scalar() or 0

        stmt = stmt.order_by(QcInspection.created_at.desc())
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)

        result = await db.execute(stmt)
        inspections = result.scalars().all()

        items_list = []
        for insp in inspections:
            items_list.append(self._inspection_summary(insp))

        return {
            "items": items_list,
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _inspection_to_dict(
        self,
        inspection: QcInspection,
        items: list[QcInspectionItem],
    ) -> dict:
        """将 inspection + items 转为字典。"""
        return {
            "id": str(inspection.id),
            "project_id": str(inspection.project_id),
            "strategy": inspection.strategy,
            "params": inspection.params,
            "reviewer_id": str(inspection.reviewer_id),
            "status": inspection.status,
            "started_at": inspection.started_at.isoformat() if inspection.started_at else None,
            "completed_at": inspection.completed_at.isoformat() if inspection.completed_at else None,
            "report_url": inspection.report_url,
            "created_at": inspection.created_at.isoformat() if inspection.created_at else None,
            "items": [self._item_to_dict(item) for item in items],
            "item_count": len(items),
        }

    def _inspection_summary(self, inspection: QcInspection) -> dict:
        """抽查批次摘要（不含 items 详情）。"""
        return {
            "id": str(inspection.id),
            "project_id": str(inspection.project_id),
            "strategy": inspection.strategy,
            "reviewer_id": str(inspection.reviewer_id),
            "status": inspection.status,
            "started_at": inspection.started_at.isoformat() if inspection.started_at else None,
            "completed_at": inspection.completed_at.isoformat() if inspection.completed_at else None,
            "created_at": inspection.created_at.isoformat() if inspection.created_at else None,
            "item_count": len(inspection.items) if inspection.items else 0,
        }

    def _item_to_dict(self, item: QcInspectionItem) -> dict:
        """将 item 转为字典。"""
        return {
            "id": str(item.id),
            "inspection_id": str(item.inspection_id),
            "wp_id": str(item.wp_id),
            "status": item.status,
            "qc_verdict": item.qc_verdict,
            "findings": item.findings,
            "completed_at": item.completed_at.isoformat() if item.completed_at else None,
        }


# 模块级单例
qc_inspection_service = QcInspectionService()
