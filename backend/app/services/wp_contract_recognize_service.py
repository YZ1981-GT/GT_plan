"""合同台账 LLM 识别服务 — wp-functional-actions spec Task 6

职责：
  1. 接收合同附件 ID 列表
  2. 调用 LLM 识别合同关键字段（替换正则 _extract_contract_fields）
  3. 返回结构化识别结果供逐份确认

LLM 链路待接入 — 当前使用 stub 模式（模拟 LLM 返回）
复用 wp-tsj-llm-review 的 LLM 链路模式
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# ─── 合同字段定义 ─────────────────────────────────────────

CONTRACT_FIELDS = [
    "contract_no",       # 合同编号
    "contract_name",     # 合同名称
    "party_a",           # 甲方
    "party_b",           # 乙方
    "contract_amount",   # 合同金额
    "currency",          # 币种
    "sign_date",         # 签订日期
    "start_date",        # 开始日期
    "end_date",          # 结束日期
    "contract_type",     # 合同类型
    "payment_terms",     # 付款条件
    "key_terms",         # 关键条款摘要
]


class WpContractRecognizeService:
    """合同台账 LLM 识别服务"""

    async def recognize_contracts(
        self,
        db: AsyncSession,
        project_id: UUID,
        attachment_ids: list[UUID],
    ) -> dict[str, Any]:
        """识别多份合同，返回结构化结果

        Returns:
            {
                "total": int,
                "recognized": int,
                "contracts": [
                    {
                        "attachment_id": str,
                        "filename": str,
                        "status": "recognized" | "failed",
                        "fields": { ... },
                        "confidence": float,
                    }
                ]
            }
        """
        contracts = []

        for att_id in attachment_ids:
            # 获取附件信息
            att_info = await self._get_attachment_info(db, att_id)
            if not att_info:
                contracts.append({
                    "attachment_id": str(att_id),
                    "filename": "未知文件",
                    "status": "failed",
                    "fields": {},
                    "confidence": 0.0,
                    "error": "附件不存在",
                })
                continue

            # LLM 链路待接入 — 使用 stub 返回
            fields = await self._llm_recognize_contract(db, att_id, att_info)
            contracts.append({
                "attachment_id": str(att_id),
                "filename": att_info.get("filename", ""),
                "status": "recognized" if fields else "failed",
                "fields": fields,
                "confidence": 0.85 if fields else 0.0,
            })

        return {
            "total": len(attachment_ids),
            "recognized": sum(1 for c in contracts if c["status"] == "recognized"),
            "contracts": contracts,
        }

    async def confirm_and_fill(
        self,
        db: AsyncSession,
        wp_id: UUID,
        confirmed_contracts: list[dict[str, Any]],
    ) -> int:
        """确认后填回台账 parsed_data

        Args:
            confirmed_contracts: 用户确认后的合同数据列表
        """
        import json

        result = await db.execute(text(
            "SELECT parsed_data FROM working_papers WHERE id = :wp_id"
        ), {"wp_id": str(wp_id)})
        row = result.fetchone()
        if not row:
            return 0

        parsed_data = row[0] or {}
        if isinstance(parsed_data, str):
            parsed_data = json.loads(parsed_data)

        # 追加到 contract_ledger 区域
        existing = parsed_data.get("contract_ledger", [])
        existing.extend(confirmed_contracts)
        parsed_data["contract_ledger"] = existing

        await db.execute(text(
            "UPDATE working_papers SET parsed_data = :pd::jsonb WHERE id = :wp_id"
        ), {"pd": json.dumps(parsed_data, ensure_ascii=False, default=str), "wp_id": str(wp_id)})
        await db.flush()

        return len(confirmed_contracts)

    async def _get_attachment_info(
        self, db: AsyncSession, attachment_id: UUID
    ) -> dict[str, Any] | None:
        """获取附件基本信息"""
        result = await db.execute(text(
            "SELECT id, filename, file_path, mime_type "
            "FROM attachments WHERE id = :att_id"
        ), {"att_id": str(attachment_id)})
        row = result.fetchone()
        if not row:
            return None
        return {
            "id": str(row[0]),
            "filename": row[1],
            "file_path": row[2],
            "mime_type": row[3],
        }

    async def _llm_recognize_contract(
        self,
        db: AsyncSession,
        attachment_id: UUID,
        att_info: dict[str, Any],
    ) -> dict[str, Any]:
        """LLM 识别合同字段

        LLM 链路待接入 — 当前返回 stub 数据
        实际实现应：
          1. 读取附件内容（PDF/图片 → OCR → 文本）
          2. 构造 prompt（含字段定义 + 示例）
          3. 调用 LLM（复用 wp-tsj-llm-review 的 llm_client）
          4. 解析 JSON 结构化输出
        """
        # TODO: LLM 链路待接入
        # from app.services.llm_client import get_llm_client
        # client = get_llm_client()
        # response = await client.chat(...)

        logger.info(
            f"[合同识别] LLM 链路待接入，attachment_id={attachment_id}, "
            f"filename={att_info.get('filename')}"
        )

        # Stub: 返回空字段模板（前端显示为"待识别"）
        return {field: None for field in CONTRACT_FIELDS}
