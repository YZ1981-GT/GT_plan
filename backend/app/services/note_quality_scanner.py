"""附注章节质量扫描 — 风险分级与整套 quality_summary。

spec: disclosure-note-doc-upload-and-batch-fill Phase 2 Task 14

风险只影响默认分组（推荐/需复核/不可用），不从全套模板删除章节。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "QualityFlag",
    "scan_section_quality",
    "compute_quality_summary",
]

# 占位文本匹配（中英文常见占位）
_PLACEHOLDER_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"请在此输入",
        r"请输入",
        r"占位",
        r"placeholder",
        r"\[待填写\]",
        r"\[TODO\]",
    )
)

# 来源实体信息残留（公司名、法定代表人、地址等）
_ENTITY_RISK_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p)
    for p in (
        r"法定代表人[：:]",
        r"注册地址[：:]",
        r"办公地址[：:]",
        r"统一社会信用代码[：:]",
    )
)

# 日期匹配
_DATE_PATTERN = re.compile(r"\d{4}年\d{1,2}月\d{1,2}日")

# 金额匹配（中文或千分位数字 + 元/万元/亿元）
_AMOUNT_PATTERN = re.compile(r"[\d,，]+(?:\.\d+)?(?:元|万元|亿元)")


class QualityFlag:
    EMPTY = "empty"
    PLACEHOLDER = "placeholder"
    DRAFT = "draft"
    STALE = "stale"
    SOURCE_ENTITY = "source_entity"
    DATE = "date"
    AMOUNT = "amount"
    ENTITY_SPECIFIC = "entity_specific"
    ACCOUNT_EXPLANATION = "account_explanation"


# 企业特有章节关键词（公司基本情况、治理、税收优惠、或有事项等）
_ENTITY_SPECIFIC_KEYWORDS = frozenset({
    "公司基本情况",
    "企业基本情况",
    "税收优惠",
    "或有事项",
    "持续经营",
    "关联方关系",
})


@dataclass
class SectionQuality:
    flags: list[str] = field(default_factory=list)
    is_high_risk: bool = False


def _strip_html(html: str) -> str:
    """粗略去标签取纯文本，用于关键词扫描。"""
    return re.sub(r"<[^>]+>", "", html or "").strip()


def scan_section_quality(
    *,
    text_content: str | None,
    status: str | None = None,
    is_stale: bool = False,
    section_kind: str | None = None,
    section_title: str | None = None,
    source_entity_name: str | None = None,
) -> SectionQuality:
    """扫描单个章节质量，返回标志列表。"""
    flags: list[str] = []
    plain = _strip_html(text_content or "")

    if not plain:
        flags.append(QualityFlag.EMPTY)
        return SectionQuality(flags=flags)

    # 占位文本
    for pat in _PLACEHOLDER_PATTERNS:
        if pat.search(plain):
            flags.append(QualityFlag.PLACEHOLDER)
            break

    # 状态
    if (status or "").lower() == "draft":
        flags.append(QualityFlag.DRAFT)
    if is_stale:
        flags.append(QualityFlag.STALE)

    # 来源实体信息残留
    if source_entity_name and source_entity_name in plain:
        flags.append(QualityFlag.SOURCE_ENTITY)
    for pat in _ENTITY_RISK_PATTERNS:
        if pat.search(plain):
            if QualityFlag.SOURCE_ENTITY not in flags:
                flags.append(QualityFlag.SOURCE_ENTITY)
            break

    # 日期/金额
    if _DATE_PATTERN.search(plain):
        flags.append(QualityFlag.DATE)
    if _AMOUNT_PATTERN.search(plain):
        flags.append(QualityFlag.AMOUNT)

    # 企业特有
    title = (section_title or "").strip()
    if any(kw in title for kw in _ENTITY_SPECIFIC_KEYWORDS):
        flags.append(QualityFlag.ENTITY_SPECIFIC)

    # 报表科目解释
    if section_kind == "account_explanation":
        flags.append(QualityFlag.ACCOUNT_EXPLANATION)

    high_risk = bool(
        set(flags)
        & {
            QualityFlag.SOURCE_ENTITY,
            QualityFlag.ENTITY_SPECIFIC,
            QualityFlag.ACCOUNT_EXPLANATION,
        }
    )
    return SectionQuality(flags=flags, is_high_risk=high_risk)


def compute_quality_summary(
    qualities: list[SectionQuality],
) -> dict[str, int]:
    """汇总整套章节质量统计。"""
    summary = {
        "total": len(qualities),
        "with_content": 0,
        "empty": 0,
        "placeholder": 0,
        "draft": 0,
        "stale": 0,
        "entity_specific": 0,
        "account_explanation": 0,
        "high_risk": 0,
    }
    for q in qualities:
        if QualityFlag.EMPTY in q.flags:
            summary["empty"] += 1
        else:
            summary["with_content"] += 1
        for key in ("placeholder", "draft", "stale", "entity_specific", "account_explanation"):
            if key in q.flags:
                summary[key] += 1
        if q.is_high_risk:
            summary["high_risk"] += 1
    return summary
