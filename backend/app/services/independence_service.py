"""独立性声明服务 — Refinement Round 1 需求 10

提供独立性声明的 CRUD + 提交签字 + 问题模板读取。

核心逻辑：
- 项目核心四角色（signing_partner / manager / qc / eqcr）均需单独提交声明
- 提交时创建 SignatureRecord + 审计日志
- 问题模板从 backend/data/independence_questions.json 读取
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.independence_models import IndependenceDeclaration
from app.models.extension_models import SignatureRecord

logger = logging.getLogger(__name__)

# 问题模板缓存（进程级单例）
_questions_cache: list[dict[str, Any]] | None = None

# 问题模板文件路径
_QUESTIONS_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "independence_questions.json"


class IndependenceService:
    """独立性声明服务"""

    # ------------------------------------------------------------------
    # 问题模板
    # ------------------------------------------------------------------

    @staticmethod
    def get_questions() -> list[dict[str, Any]]:
        """读取独立性问题模板（带进程级缓存）。"""
        global _questions_cache
        if _questions_cache is not None:
            return _questions_cache
        try:
            with open(_QUESTIONS_FILE, "r", encoding="utf-8") as f:
                _questions_cache = json.load(f)
        except FileNotFoundError:
            logger.error(f"[IndependenceService] 问题模板文件不存在: {_QUESTIONS_FILE}")
            _questions_cache = []
        return _questions_cache

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    @staticmethod
    async def list_declarations(
        db: AsyncSession,
        project_id: uuid.UUID,
        year: int | None = None,
    ) -> list[IndependenceDeclaration]:
        """列出项目的独立性声明（可按年份筛选）。"""
        stmt = select(IndependenceDeclaration).where(
            IndependenceDeclaration.project_id == project_id,
        )
        if year is not None:
            stmt = stmt.where(IndependenceDeclaration.declaration_year == year)
        stmt = stmt.order_by(IndependenceDeclaration.created_at.desc())
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def create_declaration(
        db: AsyncSession,
        project_id: uuid.UUID,
        declarant_id: uuid.UUID,
        year: int,
    ) -> IndependenceDeclaration:
        """创建一份 draft 状态的独立性声明。"""
        decl = IndependenceDeclaration(
            id=uuid.uuid4(),
            project_id=project_id,
            declarant_id=declarant_id,
            declaration_year=year,
            status="draft",
        )
        db.add(decl)
        await db.flush()
        return decl

    @staticmethod
    async def update_declaration(
        db: AsyncSession,
        declaration_id: uuid.UUID,
        answers: dict[str, Any] | None = None,
        attachments: list[dict[str, Any]] | None = None,
    ) -> IndependenceDeclaration | None:
        """更新 draft 状态的声明（answers / attachments）。"""
        stmt = select(IndependenceDeclaration).where(
            IndependenceDeclaration.id == declaration_id,
        )
        result = await db.execute(stmt)
        decl = result.scalar_one_or_none()
        if decl is None:
            return None
        if decl.status != "draft":
            raise ValueError("只能更新 draft 状态的声明")
        if answers is not None:
            decl.answers = answers
        if attachments is not None:
            decl.attachments = attachments
        await db.flush()
        return decl

    @staticmethod
    async def submit_declaration(
        db: AsyncSession,
        declaration_id: uuid.UUID,
        signer_id: uuid.UUID,
    ) -> IndependenceDeclaration:
        """提交声明：draft → submitted + 创建 SignatureRecord + 审计日志。"""
        stmt = select(IndependenceDeclaration).where(
            IndependenceDeclaration.id == declaration_id,
        )
        result = await db.execute(stmt)
        decl = result.scalar_one_or_none()
        if decl is None:
            raise ValueError("声明不存在")
        if decl.status != "draft":
            raise ValueError(f"当前状态 '{decl.status}' 不允许提交，仅 draft 可提交")

        now = datetime.now(timezone.utc)

        # 检查是否存在潜在利益冲突答案
        has_conflict = _check_conflict_answers(decl.answers)

        # 创建 SignatureRecord 留痕
        sig_record = SignatureRecord(
            id=uuid.uuid4(),
            object_type="independence_declaration",
            object_id=decl.id,
            signer_id=signer_id,
            signature_level="declaration",
            signature_timestamp=now,
        )
        db.add(sig_record)
        await db.flush()

        # 更新声明状态
        decl.signed_at = now
        decl.signature_record_id = sig_record.id
        if has_conflict:
            decl.status = "pending_conflict_review"
        else:
            decl.status = "submitted"

        await db.flush()

        # 审计日志（异步队列，不阻断主流程）
        try:
            from app.services.audit_logger_enhanced import audit_logger

            await audit_logger.log_action(
                user_id=signer_id,
                action="independence_declaration.submitted",
                object_type="independence_declaration",
                object_id=decl.id,
                project_id=decl.project_id,
                details={
                    "declaration_year": decl.declaration_year,
                    "has_conflict": has_conflict,
                    "status": decl.status,
                    "signature_record_id": str(sig_record.id),
                },
            )
        except Exception as e:
            logger.warning(f"[IndependenceService] 审计日志写入失败: {e}")

        return decl

    # ------------------------------------------------------------------
    # 辅助
    # ------------------------------------------------------------------

    @staticmethod
    def declaration_to_dict(decl: IndependenceDeclaration) -> dict[str, Any]:
        """将声明对象转为 API 响应字典。"""
        return {
            "id": str(decl.id),
            "project_id": str(decl.project_id),
            "declarant_id": str(decl.declarant_id),
            "declaration_year": decl.declaration_year,
            "answers": decl.answers,
            "attachments": decl.attachments,
            "signed_at": decl.signed_at.isoformat() if decl.signed_at else None,
            "signature_record_id": str(decl.signature_record_id) if decl.signature_record_id else None,
            "reviewed_by_qc_id": str(decl.reviewed_by_qc_id) if decl.reviewed_by_qc_id else None,
            "reviewed_at": decl.reviewed_at.isoformat() if decl.reviewed_at else None,
            "status": decl.status,
            "created_at": decl.created_at.isoformat() if decl.created_at else None,
            "updated_at": decl.updated_at.isoformat() if decl.updated_at else None,
        }


def _check_conflict_answers(answers: dict[str, Any] | None) -> bool:
    """检查答案中是否存在潜在利益冲突（任一 yes_no 问题回答 yes）。"""
    if not answers:
        return False
    for key, value in answers.items():
        if isinstance(value, dict):
            answer_val = value.get("answer")
        else:
            answer_val = value
        if answer_val is True or (isinstance(answer_val, str) and answer_val.lower() == "yes"):
            return True
    return False
