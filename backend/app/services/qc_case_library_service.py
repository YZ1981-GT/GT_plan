"""QC 案例库服务 — Round 3 需求 8

CRUD + 脱敏发布：
- list_cases: 列表（支持 category/severity 筛选）
- get_case: 获取单条
- create_case: 手动创建
- publish_from_inspection: 从抽查子项自动脱敏并创建案例
- preview_desensitized: 预览脱敏后内容（质控合伙人确认前）
- confirm_publish: 确认发布

脱敏规则：
- 客户名替换为 [客户A] / [客户B] 等占位符
- 金额 ±5% 随机扰动（保留数量级）
"""

from __future__ import annotations

import logging
import random
import re
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Project
from app.models.qc_case_library_models import QcCaseLibrary
from app.models.qc_inspection_models import QcInspectionItem
from app.models.workpaper_models import WorkingPaper

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 脱敏工具函数（模块级，便于单元测试）
# ---------------------------------------------------------------------------

# 客户名占位符序列
_CLIENT_PLACEHOLDERS = [
    "[客户A]", "[客户B]", "[客户C]", "[客户D]", "[客户E]",
    "[客户F]", "[客户G]", "[客户H]", "[客户I]", "[客户J]",
]


def desensitize_client_name(text: str, client_name: str, placeholder: str = "[客户A]") -> str:
    """将文本中的客户名替换为占位符。

    Args:
        text: 原始文本
        client_name: 需要替换的客户名
        placeholder: 替换后的占位符（默认 [客户A]）

    Returns:
        替换后的文本
    """
    if not text or not client_name:
        return text
    # 使用 re.escape 防止客户名中的特殊字符干扰正则
    pattern = re.compile(re.escape(client_name), re.IGNORECASE)
    return pattern.sub(placeholder, text)


def desensitize_amount(amount: float | int) -> float:
    """对金额进行 ±5% 随机扰动，保留数量级。

    Args:
        amount: 原始金额

    Returns:
        扰动后的金额（保留 2 位小数）
    """
    if amount == 0:
        return 0.0
    # ±5% 扰动
    factor = 1.0 + random.uniform(-0.05, 0.05)
    result = float(amount) * factor
    # 保留 2 位小数
    return round(result, 2)


def _desensitize_parsed_data(parsed_data: dict | None, client_name: str) -> dict | None:
    """递归脱敏 parsed_data 中的客户名和金额。

    对字符串值替换客户名，对数值做 ±5% 扰动。
    """
    if parsed_data is None:
        return None

    def _walk(obj, client_name: str, placeholder: str):
        if isinstance(obj, dict):
            result = {}
            for k, v in obj.items():
                result[k] = _walk(v, client_name, placeholder)
            return result
        elif isinstance(obj, list):
            return [_walk(item, client_name, placeholder) for item in obj]
        elif isinstance(obj, str):
            return desensitize_client_name(obj, client_name, placeholder)
        elif isinstance(obj, (int, float)) and not isinstance(obj, bool):
            # 只对看起来像金额的数值做扰动（绝对值 > 1）
            if abs(obj) > 1:
                return desensitize_amount(obj)
            return obj
        else:
            return obj

    return _walk(parsed_data, client_name, _CLIENT_PLACEHOLDERS[0])


# ---------------------------------------------------------------------------
# 服务类
# ---------------------------------------------------------------------------


class QcCaseLibraryService:
    """QC 案例库 CRUD + 脱敏发布服务。"""

    async def list_cases(
        self,
        db: AsyncSession,
        category: str | None = None,
        severity: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        """列出案例（支持分类/严重度筛选）。

        Returns:
            {items: [...], total: int, page: int, page_size: int}
        """
        stmt = select(QcCaseLibrary).where(
            QcCaseLibrary.is_deleted == False  # noqa: E712
        )
        count_stmt = select(func.count(QcCaseLibrary.id)).where(
            QcCaseLibrary.is_deleted == False  # noqa: E712
        )

        if category:
            stmt = stmt.where(QcCaseLibrary.category == category)
            count_stmt = count_stmt.where(QcCaseLibrary.category == category)
        if severity:
            stmt = stmt.where(QcCaseLibrary.severity == severity)
            count_stmt = count_stmt.where(QcCaseLibrary.severity == severity)

        # 总数
        total_result = await db.execute(count_stmt)
        total = total_result.scalar() or 0

        # 分页
        stmt = stmt.order_by(QcCaseLibrary.published_at.desc())
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)

        result = await db.execute(stmt)
        cases = result.scalars().all()

        return {
            "items": [self._to_dict(c) for c in cases],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    async def get_case(self, db: AsyncSession, case_id: uuid.UUID) -> dict | None:
        """获取单条案例详情，同时增加阅读计数。"""
        stmt = select(QcCaseLibrary).where(
            QcCaseLibrary.id == case_id,
            QcCaseLibrary.is_deleted == False,  # noqa: E712
        )
        result = await db.execute(stmt)
        case = result.scalar_one_or_none()
        if case is None:
            return None

        # 增加阅读计数
        case.review_count = (case.review_count or 0) + 1
        await db.flush()

        return self._to_dict(case)

    async def create_case(
        self,
        db: AsyncSession,
        data: dict,
        published_by: uuid.UUID,
    ) -> dict:
        """手动创建案例。

        Args:
            data: {title, category, severity, description, lessons_learned?,
                   related_wp_refs?, related_standards?}
            published_by: 发布人 ID
        """
        case = QcCaseLibrary(
            id=uuid.uuid4(),
            title=data["title"],
            category=data["category"],
            severity=data["severity"],
            description=data["description"],
            lessons_learned=data.get("lessons_learned"),
            related_wp_refs=data.get("related_wp_refs"),
            related_standards=data.get("related_standards"),
            published_by=published_by,
            published_at=datetime.now(timezone.utc).replace(tzinfo=None),
            review_count=0,
        )
        db.add(case)
        await db.flush()
        return self._to_dict(case)

    async def preview_desensitized(
        self,
        db: AsyncSession,
        inspection_id: uuid.UUID,
        item_id: uuid.UUID,
    ) -> dict | None:
        """预览脱敏后的案例内容（发布前质控合伙人确认用）。

        Returns:
            脱敏后的预览数据，或 None（item 不存在时）
        """
        # 1. 查找 inspection item
        item_stmt = select(QcInspectionItem).where(
            QcInspectionItem.id == item_id,
            QcInspectionItem.inspection_id == inspection_id,
        )
        item_result = await db.execute(item_stmt)
        item = item_result.scalar_one_or_none()
        if item is None:
            return None

        # 2. 查找关联底稿
        wp_stmt = select(WorkingPaper).where(WorkingPaper.id == item.wp_id)
        wp_result = await db.execute(wp_stmt)
        wp = wp_result.scalar_one_or_none()
        if wp is None:
            return None

        # 3. 查找项目获取客户名
        project_stmt = select(Project).where(Project.id == wp.project_id)
        project_result = await db.execute(project_stmt)
        project = project_result.scalar_one_or_none()
        client_name = project.client_name if project else ""

        # 4. 脱敏
        desensitized_data = _desensitize_parsed_data(wp.parsed_data, client_name)
        desensitized_findings = None
        if item.findings:
            desensitized_findings = _desensitize_parsed_data(item.findings, client_name)

        return {
            "inspection_id": str(inspection_id),
            "item_id": str(item_id),
            "wp_id": str(item.wp_id),
            "client_name_original": client_name,
            "client_name_replaced": _CLIENT_PLACEHOLDERS[0],
            "desensitized_data": desensitized_data,
            "desensitized_findings": desensitized_findings,
            "qc_verdict": item.qc_verdict,
        }

    async def publish_from_inspection(
        self,
        db: AsyncSession,
        inspection_id: uuid.UUID,
        item_id: uuid.UUID,
        published_by: uuid.UUID,
        title: str | None = None,
        category: str | None = None,
        lessons_learned: str | None = None,
    ) -> dict | None:
        """从抽查子项脱敏后发布为案例。

        质控合伙人已预览确认后调用此方法完成发布。

        Args:
            inspection_id: 抽查批次 ID
            item_id: 抽查子项 ID
            published_by: 发布人 ID
            title: 案例标题（可选，默认自动生成）
            category: 案例分类（可选，默认从 findings 推断）
            lessons_learned: 经验教训（可选）

        Returns:
            创建的案例字典，或 None（item 不存在时）
        """
        # 1. 查找 inspection item
        item_stmt = select(QcInspectionItem).where(
            QcInspectionItem.id == item_id,
            QcInspectionItem.inspection_id == inspection_id,
        )
        item_result = await db.execute(item_stmt)
        item = item_result.scalar_one_or_none()
        if item is None:
            return None

        # 2. 查找关联底稿
        wp_stmt = select(WorkingPaper).where(WorkingPaper.id == item.wp_id)
        wp_result = await db.execute(wp_stmt)
        wp = wp_result.scalar_one_or_none()
        if wp is None:
            return None

        # 3. 查找项目获取客户名
        project_stmt = select(Project).where(Project.id == wp.project_id)
        project_result = await db.execute(project_stmt)
        project = project_result.scalar_one_or_none()
        client_name = project.client_name if project else ""

        # 4. 脱敏
        desensitized_data = _desensitize_parsed_data(wp.parsed_data, client_name)
        desensitized_findings = None
        if item.findings:
            desensitized_findings = _desensitize_parsed_data(item.findings, client_name)

        # 5. 构建案例
        severity = item.qc_verdict or "warning"
        if severity == "fail":
            severity = "blocking"
        elif severity == "conditional_pass":
            severity = "warning"
        elif severity == "pass":
            severity = "info"

        # 自动生成标题
        if not title:
            title = f"质控案例 — {datetime.now(timezone.utc).strftime('%Y%m%d')}"

        # 默认分类
        if not category:
            category = "质控抽查"

        # 构建脱敏后的底稿引用
        related_wp_refs = [{
            "wp_id": str(item.wp_id),
            "snippet": desensitized_data if desensitized_data else {},
            "findings": desensitized_findings,
        }]

        # 关联准则（从 findings 中提取 rule_code 对应的 standard_ref）
        related_standards = await self._get_related_standards(db, item.findings)

        case = QcCaseLibrary(
            id=uuid.uuid4(),
            title=title,
            category=category,
            severity=severity,
            description=f"来源：质控抽查 {inspection_id}，底稿 {item.wp_id}",
            lessons_learned=lessons_learned,
            related_wp_refs=related_wp_refs,
            related_standards=related_standards,
            published_by=published_by,
            published_at=datetime.now(timezone.utc).replace(tzinfo=None),
            review_count=0,
        )
        db.add(case)
        await db.flush()
        return self._to_dict(case)

    async def _get_related_standards(
        self, db: AsyncSession, findings: dict | None
    ) -> list[dict] | None:
        """从 findings 中提取 rule_code，查找对应的 standard_ref。"""
        if not findings:
            return None

        # findings 可能是 {items: [{rule_code: 'QC-01', ...}]} 或列表
        rule_codes = []
        if isinstance(findings, dict):
            items = findings.get("items", [])
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict) and "rule_code" in item:
                        rule_codes.append(item["rule_code"])
        elif isinstance(findings, list):
            for item in findings:
                if isinstance(item, dict) and "rule_code" in item:
                    rule_codes.append(item["rule_code"])

        if not rule_codes:
            return None

        from app.models.qc_rule_models import QcRuleDefinition

        stmt = select(QcRuleDefinition.standard_ref).where(
            QcRuleDefinition.rule_code.in_(rule_codes),
            QcRuleDefinition.is_deleted == False,  # noqa: E712
        )
        result = await db.execute(stmt)
        rows = result.scalars().all()

        standards = []
        for ref in rows:
            if ref and isinstance(ref, list):
                standards.extend(ref)
        return standards if standards else None

    def _to_dict(self, case: QcCaseLibrary) -> dict:
        """将 ORM 对象转为字典。"""
        return {
            "id": str(case.id),
            "title": case.title,
            "category": case.category,
            "severity": case.severity,
            "description": case.description,
            "lessons_learned": case.lessons_learned,
            "related_wp_refs": case.related_wp_refs,
            "related_standards": case.related_standards,
            "published_by": str(case.published_by),
            "published_at": case.published_at.isoformat() if case.published_at else None,
            "review_count": case.review_count,
        }


# 模块级单例
qc_case_library_service = QcCaseLibraryService()
