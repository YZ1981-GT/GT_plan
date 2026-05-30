"""凭证 OCR + evidence_group 服务 — wp-functional-actions spec Task 7

职责：
  1. 接收凭证照片附件
  2. OCR 识别凭证内容
  3. LLM 结构化提取（凭证号/日期/金额/摘要）
  4. 填入 evidence_group 关联到抽凭条目

LLM 链路待接入 — 当前使用 stub 模式
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# ─── 凭证字段定义 ─────────────────────────────────────────

VOUCHER_FIELDS = [
    "voucher_no",       # 凭证号
    "voucher_date",     # 凭证日期
    "debit_amount",     # 借方金额
    "credit_amount",    # 贷方金额
    "summary",          # 摘要
    "account_name",     # 科目名称
    "preparer",         # 制单人
    "reviewer",         # 审核人
]


class WpEvidenceOcrService:
    """凭证 OCR + evidence_group 服务"""

    async def recognize_vouchers(
        self,
        db: AsyncSession,
        project_id: UUID,
        attachment_ids: list[UUID],
    ) -> dict[str, Any]:
        """OCR + LLM 识别凭证照片

        Returns:
            {
                "total": int,
                "recognized": int,
                "vouchers": [
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
        vouchers = []

        for att_id in attachment_ids:
            att_info = await self._get_attachment_info(db, att_id)
            if not att_info:
                vouchers.append({
                    "attachment_id": str(att_id),
                    "filename": "未知文件",
                    "status": "failed",
                    "fields": {},
                    "confidence": 0.0,
                    "error": "附件不存在",
                })
                continue

            # LLM 链路待接入 — OCR + LLM 识别
            fields = await self._ocr_and_recognize(db, att_id, att_info)
            vouchers.append({
                "attachment_id": str(att_id),
                "filename": att_info.get("filename", ""),
                "status": "recognized" if fields else "failed",
                "fields": fields,
                "confidence": 0.80 if fields else 0.0,
            })

        return {
            "total": len(attachment_ids),
            "recognized": sum(1 for v in vouchers if v["status"] == "recognized"),
            "vouchers": vouchers,
        }

    async def fill_evidence_group(
        self,
        db: AsyncSession,
        wp_id: UUID,
        entry_index: int,
        voucher_data: dict[str, Any],
    ) -> bool:
        """将识别结果填入 evidence_group

        Args:
            wp_id: 底稿 ID
            entry_index: 抽凭条目索引
            voucher_data: 确认后的凭证数据（含 attachment_id + fields）
        """
        import json

        result = await db.execute(text(
            "SELECT parsed_data FROM working_papers WHERE id = :wp_id"
        ), {"wp_id": str(wp_id)})
        row = result.fetchone()
        if not row:
            return False

        parsed_data = row[0] or {}
        if isinstance(parsed_data, str):
            parsed_data = json.loads(parsed_data)

        action_data = parsed_data.get("action_data", {})
        entries = action_data.get("entries", [])

        if 0 <= entry_index < len(entries):
            evidence_group = entries[entry_index].get("evidence_group", [])
            evidence_group.append({
                "attachment_id": voucher_data.get("attachment_id"),
                "voucher_no": voucher_data.get("fields", {}).get("voucher_no"),
                "voucher_date": voucher_data.get("fields", {}).get("voucher_date"),
                "amount": voucher_data.get("fields", {}).get("debit_amount")
                    or voucher_data.get("fields", {}).get("credit_amount"),
                "summary": voucher_data.get("fields", {}).get("summary"),
                "confidence": voucher_data.get("confidence", 0),
            })
            entries[entry_index]["evidence_group"] = evidence_group
            action_data["entries"] = entries
            parsed_data["action_data"] = action_data

            await db.execute(text(
                "UPDATE working_papers SET parsed_data = :pd::jsonb WHERE id = :wp_id"
            ), {"pd": json.dumps(parsed_data, ensure_ascii=False, default=str), "wp_id": str(wp_id)})
            await db.flush()
            return True

        return False

    async def cross_check_evidence(
        self,
        entry: dict[str, Any],
        evidence_group: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """证据链交叉核对

        比对抽凭条目与 OCR 识别的凭证数据：
          - 凭证号是否匹配
          - 金额是否一致
          - 日期是否在合理范围
        """
        issues = []
        entry_voucher_no = entry.get("voucher_no", "")
        entry_amount = float(entry.get("debit_amount", 0)) + float(entry.get("credit_amount", 0))

        for ev in evidence_group:
            ev_voucher_no = ev.get("voucher_no", "")
            ev_amount = float(ev.get("amount", 0))

            # 凭证号核对
            if ev_voucher_no and entry_voucher_no and ev_voucher_no != entry_voucher_no:
                issues.append({
                    "type": "voucher_no_mismatch",
                    "message": f"凭证号不匹配: 底稿={entry_voucher_no}, 照片={ev_voucher_no}",
                    "severity": "warning",
                })

            # 金额核对（允许 1% 误差）
            if ev_amount > 0 and entry_amount > 0:
                diff_pct = abs(ev_amount - entry_amount) / entry_amount
                if diff_pct > 0.01:
                    issues.append({
                        "type": "amount_mismatch",
                        "message": f"金额差异 {diff_pct*100:.1f}%: 底稿={entry_amount:.2f}, 照片={ev_amount:.2f}",
                        "severity": "error" if diff_pct > 0.05 else "warning",
                    })

        return {
            "matched": len(issues) == 0,
            "issues": issues,
            "evidence_count": len(evidence_group),
        }

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

    async def _ocr_and_recognize(
        self,
        db: AsyncSession,
        attachment_id: UUID,
        att_info: dict[str, Any],
    ) -> dict[str, Any]:
        """OCR + LLM 识别凭证

        LLM 链路待接入 — 当前返回 stub 数据
        实际实现应：
          1. 读取图片/PDF 附件
          2. 调用 OCR（MinerU / PaddleOCR）提取文本
          3. 构造 prompt 调用 LLM 结构化提取
          4. 解析 JSON 输出
        """
        # TODO: LLM 链路待接入
        logger.info(
            f"[凭证OCR] LLM 链路待接入，attachment_id={attachment_id}, "
            f"filename={att_info.get('filename')}"
        )

        # Stub: 返回空字段模板
        return {field: None for field in VOUCHER_FIELDS}
