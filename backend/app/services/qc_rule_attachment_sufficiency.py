"""QC-17 证据充分性判定（spec attachment-archive-and-a-class-evidence 需求 6，ADR-AE-09）。

按底稿证据声明判定，与附件抽屉「应收集证据」同一实现（``attachment_wp_view.evaluate_wp_evidence_requirements``，
含函证逐笔拆分）：无声明的底稿不出结论；有未满足的类型 ⇒ 一条结论列出缺哪几类。

改造前按「底稿挂了几份整稿关联附件」计数：任何底稿没挂附件都出阻断结论，挂了一份无关附件就放行，
且行级证据链接、函证回函都不算 —— 与抽屉的判定是两套口径。

``qc_engine.AttachmentSufficiencyRule`` 只做委托（``qc_engine.py`` 是超行数门的历史大文件，新逻辑放这里）。
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)


def _missing_label(req: dict[str, Any]) -> str:
    breakdown = req.get("breakdown")
    if isinstance(breakdown, dict) and breakdown.get("missing"):
        return f"{req['label']}（{breakdown['missing']} 笔未回函且无替代程序）"
    return str(req["label"])


async def evidence_sufficiency_findings(db, wp_id: UUID) -> list[dict[str, Any]]:
    """把统一四态证据事实映射为 QC-17 阻断项。``unknown`` 不能伪装成通过。"""
    from app.services.evidence_readiness import EvidenceReadinessService

    result = await EvidenceReadinessService(db).evaluate_workpaper(wp_id)
    if result.status in {"ready", "not_declared"}:
        return []
    if result.status == "unknown":
        message = result.errors[0]["message"] if result.errors else "证据状态无法判断"
        return [{
            "message": message,
            "expected_value": "可证明的证据就绪状态",
            "actual_value": "unknown",
        }]
    requirements = [dict(row) for row in result.requirements]
    missing = [row for row in requirements if not row.get("satisfied")]
    labels = [_missing_label(row) for row in missing]
    if "key_evidence_ocr_confirmation" in result.missing_types:
        labels.append("关键证据识别结果未人工确认")
    return [{
        "message": "应收集证据未齐：" + "；".join(labels),
        "expected_value": [row["type"] for row in requirements],
        "actual_value": [row["type"] for row in requirements if row.get("satisfied")],
    }]
