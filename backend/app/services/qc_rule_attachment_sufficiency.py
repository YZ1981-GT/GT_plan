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
    """返回 ``QCFindingItem`` 的关键字参数列表（不含 rule_id / severity）；查询失败 ⇒ 空（与改造前同为 fail-open）。"""
    from app.services.attachment_wp_view import evaluate_wp_evidence_requirements

    try:
        requirements = await evaluate_wp_evidence_requirements(db, wp_id)
    except Exception:
        logger.warning("QC-17 证据声明判定失败，底稿 id=%s", wp_id, exc_info=True)
        return []
    if not requirements:
        return []
    missing = [r for r in requirements if not r.get("satisfied")]
    if not missing:
        return []
    return [{
        "message": "应收集证据未齐：" + "；".join(_missing_label(r) for r in missing),
        "expected_value": [r["type"] for r in requirements],
        "actual_value": [r["type"] for r in requirements if r.get("satisfied")],
    }]
