"""QC 规则定义 CRUD + 版本管理服务

Refinement Round 3 — 需求 1：QC 规则定义表管理。

PATCH 更新时自动 version+1，保留历史（通过 version 字段追踪）。
GET 支持按 scope / severity / enabled 过滤。
DELETE 走 SoftDeleteMixin 软删除。
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.qc_rule_models import QcRuleDefinition

logger = logging.getLogger(__name__)


class QcRuleDefinitionService:
    """QC 规则定义 CRUD 服务"""

    async def list_rules(
        self,
        db: AsyncSession,
        *,
        scope: Optional[str] = None,
        severity: Optional[str] = None,
        enabled: Optional[bool] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict:
        """列出规则定义，支持过滤与分页。"""
        stmt = select(QcRuleDefinition).where(
            QcRuleDefinition.is_deleted == False  # noqa: E712
        )

        if scope:
            stmt = stmt.where(QcRuleDefinition.scope == scope)
        if severity:
            stmt = stmt.where(QcRuleDefinition.severity == severity)
        if enabled is not None:
            stmt = stmt.where(QcRuleDefinition.enabled == enabled)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await db.execute(count_stmt)).scalar() or 0

        stmt = stmt.order_by(QcRuleDefinition.rule_code.asc())
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)

        result = await db.execute(stmt)
        rules = result.scalars().all()

        return {
            "items": [self._to_dict(r) for r in rules],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    async def get_rule(self, db: AsyncSession, rule_id: uuid.UUID) -> dict:
        """获取单条规则详情。"""
        rule = await self._get_or_404(db, rule_id)
        return self._to_dict(rule)

    async def create_rule(
        self,
        db: AsyncSession,
        *,
        data: dict,
        created_by: uuid.UUID,
    ) -> dict:
        """创建新规则，version 初始为 1。"""
        # 检查 rule_code 唯一性
        existing = await db.execute(
            select(QcRuleDefinition).where(
                QcRuleDefinition.rule_code == data["rule_code"],
                QcRuleDefinition.is_deleted == False,  # noqa: E712
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=409,
                detail={
                    "error_code": "RULE_CODE_DUPLICATE",
                    "message": f"规则编号 '{data['rule_code']}' 已存在",
                },
            )

        rule = QcRuleDefinition(
            id=uuid.uuid4(),
            rule_code=data["rule_code"],
            severity=data["severity"],
            scope=data["scope"],
            category=data.get("category"),
            title=data["title"],
            description=data["description"],
            standard_ref=data.get("standard_ref"),
            expression_type=data["expression_type"],
            expression=data["expression"],
            parameters_schema=data.get("parameters_schema"),
            enabled=data.get("enabled", True),
            version=1,
            created_by=created_by,
        )
        db.add(rule)
        await db.flush()

        logger.info(
            "[QC_RULE] created rule_code=%s id=%s by=%s",
            rule.rule_code,
            rule.id,
            created_by,
        )
        return self._to_dict(rule)

    async def update_rule(
        self,
        db: AsyncSession,
        rule_id: uuid.UUID,
        *,
        data: dict,
    ) -> dict:
        """更新规则，每次 PATCH 自动 version+1。"""
        rule = await self._get_or_404(db, rule_id)

        # 如果修改了 rule_code，检查唯一性
        new_code = data.get("rule_code")
        if new_code and new_code != rule.rule_code:
            existing = await db.execute(
                select(QcRuleDefinition).where(
                    QcRuleDefinition.rule_code == new_code,
                    QcRuleDefinition.is_deleted == False,  # noqa: E712
                    QcRuleDefinition.id != rule_id,
                )
            )
            if existing.scalar_one_or_none():
                raise HTTPException(
                    status_code=409,
                    detail={
                        "error_code": "RULE_CODE_DUPLICATE",
                        "message": f"规则编号 '{new_code}' 已存在",
                    },
                )

        # 可更新字段
        updatable_fields = [
            "rule_code",
            "severity",
            "scope",
            "category",
            "title",
            "description",
            "standard_ref",
            "expression_type",
            "expression",
            "parameters_schema",
            "enabled",
        ]

        changed = False
        for field in updatable_fields:
            if field in data:
                old_val = getattr(rule, field)
                new_val = data[field]
                if old_val != new_val:
                    setattr(rule, field, new_val)
                    changed = True

        if changed:
            rule.version += 1
            rule.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
            await db.flush()
            logger.info(
                "[QC_RULE] updated rule_code=%s id=%s new_version=%d",
                rule.rule_code,
                rule.id,
                rule.version,
            )

        return self._to_dict(rule)

    async def delete_rule(self, db: AsyncSession, rule_id: uuid.UUID) -> dict:
        """软删除规则。"""
        rule = await self._get_or_404(db, rule_id)
        rule.soft_delete()
        await db.flush()

        logger.info("[QC_RULE] soft-deleted rule_code=%s id=%s", rule.rule_code, rule.id)
        return {"id": str(rule.id), "deleted": True}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get_or_404(
        self, db: AsyncSession, rule_id: uuid.UUID
    ) -> QcRuleDefinition:
        """按 ID 获取规则，不存在或已删除则 404。"""
        stmt = select(QcRuleDefinition).where(
            QcRuleDefinition.id == rule_id,
            QcRuleDefinition.is_deleted == False,  # noqa: E712
        )
        result = await db.execute(stmt)
        rule = result.scalar_one_or_none()
        if rule is None:
            raise HTTPException(status_code=404, detail="QC_RULE_NOT_FOUND")
        return rule

    def _to_dict(self, rule: QcRuleDefinition) -> dict:
        """将 ORM 对象转为字典。"""
        return {
            "id": str(rule.id),
            "rule_code": rule.rule_code,
            "severity": rule.severity,
            "scope": rule.scope,
            "category": rule.category,
            "title": rule.title,
            "description": rule.description,
            "standard_ref": rule.standard_ref,
            "expression_type": rule.expression_type,
            "expression": rule.expression,
            "parameters_schema": rule.parameters_schema,
            "enabled": rule.enabled,
            "version": rule.version,
            "created_by": str(rule.created_by) if rule.created_by else None,
            "created_at": rule.created_at.isoformat() if rule.created_at else None,
            "updated_at": rule.updated_at.isoformat() if rule.updated_at else None,
        }


qc_rule_definition_service = QcRuleDefinitionService()
