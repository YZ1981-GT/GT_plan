"""AI 辅助底稿编制服务

Phase 9 Task 9.8: 分析性复核 + 函证对象提取 + 审定表核对
R3 Sprint 4 Task 21: AI 内容统一结构化
V3 Req 6 Task 6.2: wrap_ai_output_with_log 强制溯源
"""

from __future__ import annotations

import hashlib
import logging
import uuid as _uuid
from datetime import datetime
from datetime import timezone as _tz
from decimal import Decimal
from typing import Optional
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


def wrap_ai_content(
    value: str | dict,
    source_model: str,
    confidence: float,
    confirmed_by: UUID | None = None,
    confirmed_at: datetime | None = None,
) -> dict:
    """将 AI 输出包装为统一结构化格式。

    R3 Sprint 4 Task 21: 所有 AI 输出必须包装为此结构，
    以便门禁规则 AIContentMustBeConfirmedRule 检查确认状态。

    Args:
        value: AI 生成的原始内容（文本或结构化数据）
        source_model: 生成该内容的模型标识（如 'qwen3.5-27b'）
        confidence: 模型置信度 [0.0, 1.0]
        confirmed_by: 确认人 UUID（未确认时为 None）
        confirmed_at: 确认时间（未确认时为 None）

    Returns:
        统一结构化 dict
    """
    return {
        "type": "ai_generated",
        "source_model": source_model,
        "confidence": confidence,
        "confirmed_by": str(confirmed_by) if confirmed_by else None,
        "confirmed_at": confirmed_at.isoformat() if confirmed_at else None,
        "value": value,
    }


def wrap_ai_output(
    content: str,
    *,
    confidence: float = 0.0,
    source_model: str | None = None,
    target_cell: str | None = None,
    target_field: str | None = None,
    source_prompt_version: str | None = None,
) -> dict:
    """将 AI 输出包装为统一结构化格式（R3 Sprint 4 Task 21 完整版）。

    与 wrap_ai_content 的区别：本函数面向前端确认流程，
    包含 id/generated_at/confirm_action/revised_content 等字段，
    供 AIContentMustBeConfirmedRule 门禁规则检查。

    Args:
        content: AI 生成的文本内容
        confidence: 模型置信度 [0.0, 1.0]
        source_model: 模型标识，默认从 settings 读取
        target_cell: 目标单元格引用（如 "E5"）
        target_field: 目标字段名（如 "conclusion"）
        source_prompt_version: 提示词版本号

    Returns:
        统一结构化 dict，含确认状态字段
    """
    if source_model is None:
        try:
            from app.core.config import settings
            source_model = getattr(settings, "DEFAULT_CHAT_MODEL", "Qwen3.5-27B")
        except Exception:
            source_model = "Qwen3.5-27B"

    return {
        "id": str(_uuid.uuid4()),
        "type": "ai_generated",
        "source_model": source_model,
        "source_prompt_version": source_prompt_version,
        "generated_at": datetime.now(_tz.utc).isoformat(),
        "confidence": confidence,
        "content": content,
        "target_cell": target_cell,
        "target_field": target_field,
        "confirmed_by": None,
        "confirmed_at": None,
        "confirm_action": None,
        "revised_content": None,
    }


async def wrap_ai_output_with_log(
    *,
    content: str,
    confidence: float = 0.0,
    source_model: str | None = None,
    target_cell: str | None = None,
    target_field: str | None = None,
    source_prompt_version: str | None = None,
    prompt_hash: str | None = None,
    prompt_text: str | None = None,
    # ── V3 Req 6 强制溯源参数（齐全时写 ai_content_log）─────────────
    db: AsyncSession | None = None,
    project_id: UUID | None = None,
    user_id: UUID | None = None,
    instance_type: str | None = None,
    instance_id: UUID | None = None,
    wp_id: UUID | None = None,
) -> dict:
    """异步包装 AI 输出（V3 Req 6 Task 6.2 强制溯源版本）。

    与同步 wrap_ai_output 的关键差异：
    1. **强制写日志**：当 db / project_id / user_id / instance_type / instance_id
       五个参数齐全时，调用 ai_content_log_service.create() 写入
       ai_content_log 表（pending 状态）+ 写入审计日志。
    2. **新增 hash 字段**：返回 dict 含 content_hash（sha256），以及
       prompt_hash（若调用方提供 prompt_text 则自动计算）。
    3. **写表后字段**：成功写表时返回 dict 中追加
       ai_content_log_id（UUID 字符串）+ confirm_action='pending'。

    向后兼容：当上述 5 参数任一缺失时，跳过 DB 写入，返回基础 dict
    （结构与同步 wrap_ai_output 一致 + content_hash + prompt_hash），
    既有调用点（wp_llm_prompts.py 4 处 + WpAIService 内部 5 处）
    无需立即改造。

    参数:
        content: AI 生成文本
        confidence: 置信度 [0.0, 1.0]
        source_model: 模型标识，None=从 settings.DEFAULT_CHAT_MODEL 读取
        target_cell: 目标单元格引用（如 "E5"）
        target_field: 目标字段名（如 "conclusion"）
        source_prompt_version: 提示词版本号
        prompt_hash: 提示词 SHA-256 哈希（若与 prompt_text 同时提供，
            优先使用 prompt_hash）
        prompt_text: 提示词原文，若提供且 prompt_hash 为 None 则自动计算
        db: 异步数据库会话（强制写日志的 5 必备参数之一）
        project_id: 项目 UUID
        user_id: 触发生成的用户 UUID
        instance_type: 'workpaper' / 'adjustment' / 'misstatement' /
            'disclosure' / 'risk_assessment' 等
        instance_id: 业务实例 UUID
        wp_id: 关联底稿 UUID（可选，仅 instance_type='workpaper' 时建议填）

    返回:
        统一结构化 dict，含：
        - id / type / source_model / source_prompt_version
        - generated_at / confidence / content
        - target_cell / target_field
        - confirmed_by / confirmed_at / confirm_action / revised_content
        - prompt_hash / content_hash（V3 Req 6 新增）
        - 写表成功时还包含：ai_content_log_id（覆盖 id）+
          confirm_action='pending'

    Validates: Requirements 6.2 (强制写 ai_content_log + 返回 id /
        generated_at / confirm_action)
    """
    # ── 1. 默认 source_model 从 settings 读取（与同步版本一致） ──
    if source_model is None:
        try:
            from app.core.config import settings
            source_model = getattr(settings, "DEFAULT_CHAT_MODEL", "Qwen3.5-27B")
        except Exception:
            source_model = "Qwen3.5-27B"

    # ── 2. 计算 content_hash（始终）+ prompt_hash（如有 prompt_text）──
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    if prompt_hash is None and prompt_text is not None:
        prompt_hash = hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()

    # ── 3. 基础 dict（无论是否写表都返回此结构）───────────────────
    generated_at_iso = datetime.now(_tz.utc).isoformat()
    base_dict: dict = {
        "id": str(_uuid.uuid4()),
        "type": "ai_generated",
        "source_model": source_model,
        "source_prompt_version": source_prompt_version,
        "generated_at": generated_at_iso,
        "confidence": confidence,
        "content": content,
        "target_cell": target_cell,
        "target_field": target_field,
        "confirmed_by": None,
        "confirmed_at": None,
        "confirm_action": None,
        "revised_content": None,
        # V3 Req 6 新增字段
        "prompt_hash": prompt_hash,
        "content_hash": content_hash,
    }

    # ── 4. 强制写日志：5 参齐全才写 ───────────────────────────────
    write_log_args = {
        "db": db,
        "project_id": project_id,
        "user_id": user_id,
        "instance_type": instance_type,
        "instance_id": instance_id,
    }
    if all(v is not None for v in write_log_args.values()):
        # 局部导入避免循环依赖（ai_content_log_service 不依赖 wp_ai_service，
        # 但此处显式 import 仅在需要时加载）
        from app.services import ai_content_log_service

        try:
            ai_log = await ai_content_log_service.create(
                db=db,
                project_id=project_id,
                user_id=user_id,
                instance_type=instance_type,
                instance_id=instance_id,
                target_cell=target_cell,
                model=source_model,
                prompt_hash=prompt_hash,
                content_hash=content_hash,
                generated_content=content,
                confidence=confidence,
                wp_id=wp_id,
            )
            # 用 DB 实际写入的 id 覆盖临时 id（保持外部引用一致性）
            base_dict["ai_content_log_id"] = str(ai_log.id)
            base_dict["confirm_action"] = "pending"
        except Exception as e:
            # 写表失败不应中断 AI 输出返回；记日志便于排查
            logger.warning(
                "wrap_ai_output_with_log: ai_content_log.create failed: %s "
                "(project_id=%s, instance_type=%s, instance_id=%s)",
                e, project_id, instance_type, instance_id,
            )

    return base_dict


class WpAIService:
    """AI 辅助底稿编制"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def analytical_review(self, project_id: UUID, account_code: str, year: int) -> dict:
        """分析性复核：变动分析 + LLM 生成分析文本"""
        from app.models.audit_platform_models import TrialBalance
        from app.services.task_center import create_task, update_task, TaskType, TaskStatus

        task_id = create_task(
            TaskType.ai_analysis,
            project_id=str(project_id),
            params={"account_code": account_code, "year": year, "action": "analytical_review"},
        )
        update_task(task_id, TaskStatus.processing)

        try:
            q = sa.select(TrialBalance).where(
                TrialBalance.project_id == project_id,
                TrialBalance.standard_account_code == account_code,
                TrialBalance.year == year,
                TrialBalance.is_deleted == False,  # noqa
            )
            tb = (await self.db.execute(q)).scalar_one_or_none()
            if not tb:
                update_task(task_id, TaskStatus.failed, error="科目未找到")
                return {"error": f"科目 {account_code} 未找到"}

            current = float(tb.audited_debit or 0) - float(tb.audited_credit or 0)
            prior = float(tb.unadjusted_debit or 0) - float(tb.unadjusted_credit or 0)
            change = current - prior
            rate = round(change / prior * 100, 2) if prior != 0 else None
            is_significant = abs(rate or 0) > 20 if rate is not None else abs(change) > 0

            # 调用 LLM 生成分析文本（RAG: 参照上年底稿分析结论）
            from app.services.llm_client import chat_completion
            from app.services.reference_doc_service import ReferenceDocService

            context_docs = await ReferenceDocService.load_context(
                self.db, project_id, year,
                source_type="prior_year_workpaper",
                wp_code=None,  # 按科目匹配
                knowledge_keywords=[account_code],
            )

            prompt = f"科目 {account_code}，本期余额 {current:,.2f}，上期余额 {prior:,.2f}，变动额 {change:,.2f}，变动率 {rate}%。请用一句话分析变动原因。"
            # AI 脱敏前置过滤（R4 需求 2 / R8-S1 Task 35）
            from app.services.export_mask_service import export_mask_service
            masked_prompt, _mapping = export_mask_service.mask_text(prompt)
            try:
                ai_text = await chat_completion([
                    {"role": "system", "content": "你是审计分析师，请简洁分析科目余额变动原因。如有上年分析参照请对比。"},
                    {"role": "user", "content": masked_prompt},
                ], context_documents=context_docs if context_docs else None)
                source_model = "qwen3.5-27b"
            except Exception:
                ai_text = f"该科目余额变动 {change:,.2f}，变动率 {rate}%。"
                source_model = "fallback"

            # R3 Sprint 4: AI 输出统一结构化
            ai_analysis_wrapped = wrap_ai_content(
                value=ai_text,
                source_model=source_model,
                confidence=0.8 if source_model != "fallback" else 0.0,
            )

            update_task(task_id, TaskStatus.success)
            return {
                "account_code": account_code,
                "current_balance": current,
                "prior_balance": prior,
                "change_amount": change,
                "change_rate": rate,
                "is_significant": is_significant,
                "ai_analysis": ai_analysis_wrapped,
                "recommended_procedures": [],
                "task_id": task_id,
            }
        except Exception as e:
            update_task(task_id, TaskStatus.failed, error=str(e))
            raise

    async def extract_confirmations(self, project_id: UUID, account_code: str, year: int) -> list[dict]:
        """函证对象提取：从辅助余额表提取"""
        from app.models.audit_platform_models import TbAuxBalance

        from app.services.dataset_query import get_active_filter

        q = (
            sa.select(TbAuxBalance)
            .where(
                await get_active_filter(self.db, TbAuxBalance.__table__, project_id, year),
                TbAuxBalance.account_code.like(f"{account_code}%"),
            )
            .order_by(TbAuxBalance.closing_balance.desc())
            .limit(50)
        )
        rows = (await self.db.execute(q)).scalars().all()
        return [
            {
                "aux_name": r.aux_name,
                "aux_code": r.aux_code,
                "closing_balance": float(r.closing_balance or 0),
                "opening_balance": float(r.opening_balance or 0),
            }
            for r in rows
        ]

    async def check_wp_report_consistency(self, project_id: UUID, year: int) -> list[dict]:
        """审定表核对：底稿审定数 vs 报表行次金额"""
        from app.models.report_models import FinancialReport
        from app.models.workpaper_models import WorkingPaper

        # 获取有 parsed_data 的底稿
        wp_q = sa.select(WorkingPaper).where(
            WorkingPaper.project_id == project_id,
            WorkingPaper.is_deleted == False,  # noqa
            WorkingPaper.parsed_data.isnot(None),
        )
        wps = (await self.db.execute(wp_q)).scalars().all()

        # 获取报表数据
        report_q = sa.select(FinancialReport).where(
            FinancialReport.project_id == project_id,
            FinancialReport.year == year,
        )
        reports = (await self.db.execute(report_q)).scalars().all()
        report_map = {r.row_code: float(r.current_period_amount or 0) for r in reports}

        results = []
        for wp in wps:
            pd = wp.parsed_data or {}
            wp_amount = pd.get("audited_amount")
            if wp_amount is not None:
                # 简化：暂时只返回底稿有 parsed_data 的记录
                results.append({
                    "wp_id": str(wp.id),
                    "wp_amount": wp_amount,
                    "status": "has_data",
                })

        return results

    # ------------------------------------------------------------------
    # E1 spec Sprint 1 Task 1.16: 4 个 LLM 辅助方法
    # 复用 mask_context 脱敏 + chat_completion + wrap_ai_output 包装
    # 锚定: requirements F6.3 / wp_template_metadata.llm_prompts
    # ------------------------------------------------------------------

    async def _load_llm_prompt(
        self, wp_code: str, scenario: str
    ) -> dict | None:
        """从 wp_template_metadata.llm_prompts 加载指定场景的 prompt 模板

        Args:
            wp_code: 底稿编码(如 'E1')
            scenario: 场景名(audit_conclusion / variance_analysis /
                      check_conclusion / cutoff_conclusion)

        Returns:
            {"system_prompt", "user_template", "output_target"} 或 None
        """
        try:
            from app.models.wp_optimization_models import WpTemplateMetadata

            stmt = sa.select(WpTemplateMetadata).where(
                WpTemplateMetadata.wp_code == wp_code
            ).limit(1)
            result = await self.db.execute(stmt)
            meta = result.scalar_one_or_none()
            if meta is None or not meta.llm_prompts:
                return None
            return meta.llm_prompts.get(scenario)
        except Exception as e:
            logger.warning("_load_llm_prompt(%s, %s) failed: %s", wp_code, scenario, e)
            return None

    async def _execute_llm_with_mask(
        self,
        system_prompt: str,
        user_prompt: str,
        scenario: str,
        target: dict | None = None,
    ) -> dict:
        """统一 LLM 执行 + 脱敏 + 包装 helper

        步骤:
        1. mask_text 脱敏(金额/客户名等)
        2. chat_completion 调 LLM
        3. wrap_ai_output 包装(便于前端 AiContentConfirmDialog 确认)
        4. 失败时降级 fallback 文本
        """
        from app.services.export_mask_service import export_mask_service
        from app.services.llm_client import chat_completion

        masked_user, _ = export_mask_service.mask_text(user_prompt)
        try:
            ai_text = await chat_completion([
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": masked_user},
            ])
            source_model = "qwen3.5-27b"
            confidence = 0.8
        except Exception as e:
            logger.warning("LLM scenario=%s failed: %s", scenario, e)
            ai_text = f"[{scenario} LLM 调用失败,请人工填写] (错误: {e})"
            source_model = "fallback"
            confidence = 0.0

        return wrap_ai_output(
            content=ai_text,
            confidence=confidence,
            source_model=source_model,
            target_cell=(target or {}).get("cell"),
            target_field=scenario,
            source_prompt_version=f"e1_v1_{scenario}",
        )

    async def generate_audit_conclusion(
        self,
        project_id: UUID,
        wp_code: str,
        year: int,
        *,
        company_name: str = "",
        audited_amount: float = 0.0,
        prior_amount: float = 0.0,
        period_change: float = 0.0,
        change_rate: float = 0.0,
        aje_total: float = 0.0,
        rje_total: float = 0.0,
        anomalies: str = "无",
    ) -> dict:
        """E1 spec F6.3 场景 1: 审计说明自动生成(R40-R46)

        基于审定表数据生成 200-300 字审计说明草稿。
        """
        prompt_cfg = await self._load_llm_prompt(wp_code, "audit_conclusion")
        if prompt_cfg is None:
            return wrap_ai_output(
                content=f"[{wp_code} 未配置 audit_conclusion prompt,请先在 wp_template_metadata.llm_prompts 添加]",
                confidence=0.0,
                source_model="fallback",
                target_field="audit_conclusion",
            )

        user_prompt = prompt_cfg["user_template"].format(
            company_name_masked=company_name or "[company_1]",
            audit_period=str(year),
            audited_amount=f"{audited_amount:,.2f}",
            period_change=f"{period_change:,.2f}",
            change_rate=change_rate,
            prior_amount=f"{prior_amount:,.2f}",
            aje_total=f"{aje_total:,.2f}",
            rje_total=f"{rje_total:,.2f}",
            anomalies=anomalies,
        )
        return await self._execute_llm_with_mask(
            system_prompt=prompt_cfg["system_prompt"],
            user_prompt=user_prompt,
            scenario="audit_conclusion",
            target=prompt_cfg.get("output_target"),
        )

    async def generate_variance_analysis(
        self,
        project_id: UUID,
        wp_code: str,
        year: int,
        *,
        company_name: str = "",
        diff_amount: float = 0.0,
        diff_direction: str = "",
        bank_name: str = "",
        materiality_level: float = 0.0,
    ) -> dict:
        """E1 spec F6.3 场景 2: 差异原因分析(银行存款余额调节差异)

        分析差异成因:在途存款 / 在途票据 / 银行错记 / 未达账项。
        """
        prompt_cfg = await self._load_llm_prompt(wp_code, "variance_analysis")
        if prompt_cfg is None:
            return wrap_ai_output(
                content=f"[{wp_code} 未配置 variance_analysis prompt]",
                confidence=0.0,
                source_model="fallback",
                target_field="variance_analysis",
            )

        user_prompt = prompt_cfg["user_template"].format(
            company_name_masked=company_name or "[company_1]",
            diff_amount=f"{diff_amount:,.2f}",
            diff_direction=diff_direction or "未指明",
            bank_name_masked=bank_name or "[bank_1]",
            materiality_level=f"{materiality_level:,.2f}",
        )
        return await self._execute_llm_with_mask(
            system_prompt=prompt_cfg["system_prompt"],
            user_prompt=user_prompt,
            scenario="variance_analysis",
            target=prompt_cfg.get("output_target"),
        )

    async def generate_check_conclusion(
        self,
        project_id: UUID,
        wp_code: str,
        year: int,
        *,
        check_type: str = "",
        check_scope: str = "",
        passed_count: int = 0,
        total_count: int = 0,
        exceptions: str = "无",
        attachment_count: int = 0,
    ) -> dict:
        """E1 spec F6.3 场景 3: 检查结论生成(B/D 类弹窗)

        基于检查清单完成情况生成结论(80-150 字)。
        """
        prompt_cfg = await self._load_llm_prompt(wp_code, "check_conclusion")
        if prompt_cfg is None:
            return wrap_ai_output(
                content=f"[{wp_code} 未配置 check_conclusion prompt]",
                confidence=0.0,
                source_model="fallback",
                target_field="check_conclusion",
            )

        user_prompt = prompt_cfg["user_template"].format(
            check_type=check_type,
            check_scope=check_scope,
            passed_count=passed_count,
            total_count=total_count,
            exceptions=exceptions,
            attachment_count=attachment_count,
        )
        return await self._execute_llm_with_mask(
            system_prompt=prompt_cfg["system_prompt"],
            user_prompt=user_prompt,
            scenario="check_conclusion",
            target=prompt_cfg.get("output_target"),
        )

    async def generate_cutoff_conclusion(
        self,
        project_id: UUID,
        wp_code: str,
        year: int,
        *,
        cutoff_date: str = "",
        days_before: int = 5,
        days_after: int = 5,
        sample_count: int = 0,
        amount_range: str = "",
        issues_count: int = 0,
    ) -> dict:
        """E1 spec F6.3 场景 4: 截止测试结论(E1-21~E1-23)

        基于跨期凭证检查情况生成结论(100-150 字)。
        """
        prompt_cfg = await self._load_llm_prompt(wp_code, "cutoff_conclusion")
        if prompt_cfg is None:
            return wrap_ai_output(
                content=f"[{wp_code} 未配置 cutoff_conclusion prompt]",
                confidence=0.0,
                source_model="fallback",
                target_field="cutoff_conclusion",
            )

        user_prompt = prompt_cfg["user_template"].format(
            cutoff_date=cutoff_date,
            days_before=days_before,
            days_after=days_after,
            sample_count=sample_count,
            amount_range=amount_range,
            issues_count=issues_count,
        )
        return await self._execute_llm_with_mask(
            system_prompt=prompt_cfg["system_prompt"],
            user_prompt=user_prompt,
            scenario="cutoff_conclusion",
            target=prompt_cfg.get("output_target"),
        )
