"""底稿 LLM 对话服务：请求内准备上下文，流式阶段不持有 AsyncSession。"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, AsyncGenerator
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import TbLedger
from app.models.workpaper_models import WorkingPaper, WpIndex

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PreparedWpChat:
    """流开始前已完成所有 DB / 脱敏工作的不可变载荷。"""

    project_id: UUID | None
    messages: tuple[dict[str, str], ...]
    message: str


class WpChatService:
    """底稿 LLM 对话服务。"""

    async def prepare_chat(
        self,
        db: AsyncSession,
        wp_id: UUID,
        message: str,
        context: dict[str, Any] | None = None,
    ) -> PreparedWpChat:
        """在 HTTP handler 内加载/脱敏上下文；返回后可安全关闭 DB session。"""
        from app.services.export_mask_service import export_mask_service

        if context and "cell_context" in context:
            safe_context = dict(context)
            safe_context["cell_context"], _mapping = export_mask_service.mask_context(context["cell_context"])
        elif context:
            safe_context, _mapping = export_mask_service.mask_context(context)
        else:
            safe_context = None

        wp_info = await self._load_wp_context(db, wp_id)
        system_prompt = self._build_system_prompt(wp_info, safe_context)
        raw_project_id = wp_info.get("project_id")
        try:
            project_id = UUID(str(raw_project_id)) if raw_project_id else None
        except (TypeError, ValueError):
            project_id = None
        return PreparedWpChat(
            project_id=project_id,
            messages=(
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message},
            ),
            message=message,
        )

    async def stream_prepared(self, prepared: PreparedWpChat) -> AsyncGenerator[str, None]:
        """纯 LLM SSE 流：绝不读取 ORM / AsyncSession。"""
        try:
            from app.services.llm_client import chat_completion

            full_response = ""
            async for text in await chat_completion(list(prepared.messages), stream=True, max_tokens=4096):
                if text:
                    full_response += text
                    yield f"data: {json.dumps({'type': 'content', 'text': text}, ensure_ascii=False)}\n\n"
            suggestion = self._extract_fill_suggestion(full_response)
            if suggestion:
                yield f"data: {json.dumps({'type': 'fill_suggestion', 'suggestions': suggestion}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        except Exception as exc:  # noqa: BLE001 - 对话降级不影响 SSE 帧完整性
            logger.warning("wp_chat LLM 调用失败: %s, 使用 stub 回复", exc)
            yield f"data: {json.dumps({'type': 'content', 'text': f'[LLM 暂不可用] 已收到您的问题：{prepared.message}'}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

    async def chat_stream(
        self,
        db: AsyncSession,
        wp_id: UUID,
        message: str,
        context: dict[str, Any] | None = None,
    ) -> AsyncGenerator[str, None]:
        """兼容旧调用方。

        新路由必须先调 :meth:`prepare_chat` 再调 :meth:`stream_prepared`，避免生成器持有 DB。
        这个包装器只保留给已有服务级用例和历史调用点，不在 HTTP 流式端点使用。
        """
        prepared = await self.prepare_chat(db, wp_id, message, context)
        async for chunk in self.stream_prepared(prepared):
            yield chunk

    async def generate_ledger_analysis(
        self,
        db: AsyncSession,
        project_id: UUID,
        account_codes: list[str] | None = None,
        year: int | None = None,
    ) -> dict[str, Any]:
        """台账分析底稿生成 — LLM 分析序时账大额/异常/关联方交易。"""
        from app.services.dataset_query import get_active_filter

        if year:
            conditions = [await get_active_filter(db, TbLedger.__table__, project_id, year)]
        else:
            from app.models.dataset_models import LedgerDataset, DatasetStatus

            active_ds_subq = (
                sa.select(LedgerDataset.id)
                .where(LedgerDataset.project_id == project_id, LedgerDataset.status == DatasetStatus.active)
            )
            conditions = [
                TbLedger.project_id == project_id,
                TbLedger.dataset_id.in_(active_ds_subq),
                TbLedger.is_deleted == sa.false(),
            ]
        if account_codes:
            conditions.append(TbLedger.account_code.in_(account_codes))

        stmt = (
            sa.select(TbLedger)
            .where(*conditions)
            .order_by(TbLedger.voucher_date, TbLedger.voucher_no)
            .limit(5000)
        )
        result = await db.execute(stmt)
        ledger_rows = result.scalars().all()
        if not ledger_rows:
            return {"analysis": "无序时账数据", "entries_analyzed": 0, "findings": []}

        total_debit = sum(float(row.debit_amount or 0) for row in ledger_rows)
        total_credit = sum(float(row.credit_amount or 0) for row in ledger_rows)
        large_entries = [
            row for row in ledger_rows
            if float(row.debit_amount or 0) > 100000 or float(row.credit_amount or 0) > 100000
        ]
        analysis_text = (
            f"## 台账分析报告\n\n- 分析凭证数：{len(ledger_rows)}\n"
            f"- 借方合计：{total_debit:,.2f}\n- 贷方合计：{total_credit:,.2f}\n"
            f"- 大额交易（>10万）：{len(large_entries)} 笔\n\n"
        )
        findings = [{
            "voucher_no": entry.voucher_no,
            "date": entry.voucher_date.isoformat() if entry.voucher_date else None,
            "account_code": entry.account_code,
            "debit": float(entry.debit_amount or 0),
            "credit": float(entry.credit_amount or 0),
            "summary": entry.summary or "",
        } for entry in large_entries[:20]]
        llm_analysis = await self._llm_analyze_ledger(ledger_rows[:200])
        if llm_analysis:
            analysis_text += f"\n### AI 分析\n{llm_analysis}\n"
        return {
            "analysis": analysis_text,
            "entries_analyzed": len(ledger_rows),
            "large_entries": len(large_entries),
            "findings": findings,
        }

    async def _load_wp_context(self, db: AsyncSession, wp_id: UUID) -> dict[str, Any]:
        """加载底稿上下文；未找到时不泄露其他项目数据。"""
        row = (
            await db.execute(
                sa.select(WorkingPaper, WpIndex)
                .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
                .where(WorkingPaper.id == wp_id, WorkingPaper.is_deleted == sa.false())
            )
        ).first()
        if not row:
            return {"wp_code": "unknown", "wp_name": "unknown", "project_id": None}
        wp, idx = row
        return {
            "wp_code": idx.wp_code,
            "wp_name": idx.wp_name,
            "audit_cycle": idx.audit_cycle,
            "parsed_data": wp.parsed_data or {},
            "project_id": str(wp.project_id),
        }

    def _build_system_prompt(self, wp_info: dict[str, Any], context: dict[str, Any] | None) -> str:
        prompt = (
            "你是审计底稿填写助手。当前底稿信息：\n"
            f"- 编号：{wp_info.get('wp_code', 'N/A')}\n"
            f"- 名称：{wp_info.get('wp_name', 'N/A')}\n"
            f"- 审计循环：{wp_info.get('audit_cycle', 'N/A')}\n\n"
            "请根据用户问题提供专业的审计建议。如果需要填写数据，"
            "请在回复中用 [FILL:单元格引用=值] 格式标注建议填入的内容。\n"
        )
        if context and context.get("selected_cell"):
            prompt += f"\n用户当前选中单元格：{context['selected_cell']}\n"
        parsed = wp_info.get("parsed_data", {})
        if parsed:
            prompt += f"\n底稿已解析数据摘要：{json.dumps(parsed, ensure_ascii=False)[:2000]}\n"
        return prompt

    def _extract_fill_suggestion(self, response: str) -> list[dict[str, str]] | None:
        import re

        matches = re.findall(r'\[FILL:([A-Z]+\d+)=([^\]]+)\]', response)
        return [{"cell_ref": item[0], "value": item[1]} for item in matches] or None

    async def _llm_analyze_ledger(self, entries: list[Any]) -> str | None:
        try:
            from app.services.llm_client import chat_completion

            lines = [
                f"{entry.voucher_date} {entry.voucher_no} {entry.account_code} "
                f"D:{entry.debit_amount} C:{entry.credit_amount} {entry.summary or ''}"
                for entry in entries[:50]
            ]
            prompt = "以下是部分序时账数据，请分析大额交易、异常交易和可能的关联方交易：\n\n" + "\n".join(lines)
            return await chat_completion([{"role": "user", "content": prompt}], max_tokens=2048)
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM 台账分析失败: %s", exc)
            return None
