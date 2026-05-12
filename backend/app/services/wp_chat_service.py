"""底稿 LLM 对话服务 — Phase 10 Task 5.1-5.3

对话式底稿填充、台账分析底稿生成、知识库双向关联。
"""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncGenerator
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import TbLedger, TbBalance, TrialBalance
from app.models.workpaper_models import WorkingPaper, WpIndex

logger = logging.getLogger(__name__)


class WpChatService:
    """底稿 LLM 对话服务"""

    async def chat_stream(
        self,
        db: AsyncSession,
        wp_id: UUID,
        message: str,
        context: dict[str, Any] | None = None,
    ) -> AsyncGenerator[str, None]:
        """SSE 流式对话 — 注入底稿上下文 + 四表数据 + 知识库"""
        # 0. AI 脱敏前置过滤（R4 需求 2 验收 7）
        from app.services.export_mask_service import export_mask_service
        if context and "cell_context" in context:
            context["cell_context"], _mapping = export_mask_service.mask_context(context["cell_context"])
        elif context:
            context, _mapping = export_mask_service.mask_context(context)

        # 1. 加载底稿信息
        wp_info = await self._load_wp_context(db, wp_id)
        # 2. 构建 system prompt
        system_prompt = self._build_system_prompt(wp_info, context)
        # 3. 调用 LLM
        try:
            from app.services.llm_client import get_llm_client
            client = get_llm_client()
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message},
            ]
            stream = client.chat.completions.create(
                model=client._default_model if hasattr(client, "_default_model") else "default",
                messages=messages,
                stream=True,
                max_tokens=4096,
            )
            full_response = ""
            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    text = chunk.choices[0].delta.content
                    full_response += text
                    yield f"data: {json.dumps({'type': 'content', 'text': text}, ensure_ascii=False)}\n\n"

            # 尝试提取 fill_suggestion
            suggestion = self._extract_fill_suggestion(full_response)
            if suggestion:
                yield f"data: {json.dumps({'type': 'fill_suggestion', 'suggestions': suggestion}, ensure_ascii=False)}\n\n"

            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        except Exception as e:
            logger.warning("wp_chat LLM 调用失败: %s, 使用 stub 回复", e)
            yield f"data: {json.dumps({'type': 'content', 'text': f'[LLM 暂不可用] 已收到您的问题：{message}'}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

    async def generate_ledger_analysis(
        self,
        db: AsyncSession,
        project_id: UUID,
        account_codes: list[str] | None = None,
        year: int | None = None,
    ) -> dict[str, Any]:
        """台账分析底稿生成 — LLM 分析序时账大额/异常/关联方交易"""
        from app.services.dataset_query import get_active_filter

        # 查询序时账数据
        if year:
            conditions = [await get_active_filter(db, TbLedger.__table__, project_id, year)]
        else:
            # year=None：查所有年度的 active data
            from app.models.dataset_models import LedgerDataset, DatasetStatus
            active_ds_subq = (
                sa.select(LedgerDataset.id)
                .where(
                    LedgerDataset.project_id == project_id,
                    LedgerDataset.status == DatasetStatus.active,
                )
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

        # 汇总统计
        total_debit = sum(float(r.debit_amount or 0) for r in ledger_rows)
        total_credit = sum(float(r.credit_amount or 0) for r in ledger_rows)
        large_entries = [
            r for r in ledger_rows
            if (float(r.debit_amount or 0) > 100000 or float(r.credit_amount or 0) > 100000)
        ]

        analysis_text = (
            f"## 台账分析报告\n\n"
            f"- 分析凭证数：{len(ledger_rows)}\n"
            f"- 借方合计：{total_debit:,.2f}\n"
            f"- 贷方合计：{total_credit:,.2f}\n"
            f"- 大额交易（>10万）：{len(large_entries)} 笔\n\n"
        )

        findings = []
        for entry in large_entries[:20]:
            findings.append({
                "voucher_no": entry.voucher_no,
                "date": entry.voucher_date.isoformat() if entry.voucher_date else None,
                "account_code": entry.account_code,
                "debit": float(entry.debit_amount or 0),
                "credit": float(entry.credit_amount or 0),
                "summary": entry.summary or "",
            })

        # 尝试 LLM 生成分析说明
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
        """加载底稿上下文"""
        stmt = (
            sa.select(WorkingPaper, WpIndex)
            .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
            .where(WorkingPaper.id == wp_id)
        )
        result = await db.execute(stmt)
        row = result.first()
        if not row:
            return {"wp_code": "unknown", "wp_name": "unknown"}
        wp, idx = row
        return {
            "wp_code": idx.wp_code,
            "wp_name": idx.wp_name,
            "audit_cycle": idx.audit_cycle,
            "parsed_data": wp.parsed_data or {},
            "project_id": str(wp.project_id),
        }

    def _build_system_prompt(self, wp_info: dict, context: dict | None) -> str:
        """构建 system prompt"""
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

    def _extract_fill_suggestion(self, response: str) -> list[dict] | None:
        """从 LLM 回复中提取填充建议 [FILL:B5=12345]"""
        import re
        pattern = r'\[FILL:([A-Z]+\d+)=([^\]]+)\]'
        matches = re.findall(pattern, response)
        if not matches:
            return None
        return [{"cell_ref": m[0], "value": m[1]} for m in matches]

    async def _llm_analyze_ledger(self, entries: list) -> str | None:
        """LLM 分析序时账"""
        try:
            from app.services.llm_client import get_llm_client
            client = get_llm_client()
            summary_lines = []
            for e in entries[:50]:
                line = f"{e.voucher_date} {e.voucher_no} {e.account_code} D:{e.debit_amount} C:{e.credit_amount} {e.summary or ''}"
                summary_lines.append(line)
            prompt = (
                "以下是部分序时账数据，请分析大额交易、异常交易和可能的关联方交易：\n\n"
                + "\n".join(summary_lines)
            )
            resp = client.chat.completions.create(
                model=client._default_model if hasattr(client, "_default_model") else "default",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2048,
            )
            return resp.choices[0].message.content
        except Exception as e:
            logger.warning("LLM 台账分析失败: %s", e)
            return None
