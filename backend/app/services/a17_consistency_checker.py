"""a17_consistency_checker — 跨章节/跨底稿一致性校验引擎

加载 backend/data/a17_consistency_rules.json 中的规则，
对 A17-1 的 16 章内容执行正则匹配逻辑校验，并可结合跨底稿上下文
（A17-7 签署、A17-3/3-1 成对状态）。

支持的 condition 模式:
- source_matches AND target_matches
- source_matches AND NOT target_matches
- source_empty AND project.business_category == 'xxx'   (兼容旧规则)
- source_empty AND is_a_class_or_listed
- source_filled AND NOT context.xxx
- context.xxx AND NOT context.yyy
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).resolve().parents[2] / "data"
_RULES_PATH = _DATA_DIR / "a17_consistency_rules.json"

# 中文「上市公司」及 A 类业务分类前缀均视为上市/A 类强制场景
_LISTED_ALIASES = {"上市公司", "上市实体", "A股上市公司"}


@dataclass
class ConsistencyResult:
    rule_id: str
    severity: str
    affected_chapters: list[str]
    description: str

    def to_dict(self) -> dict:
        return asdict(self)


def _load_rules() -> list[dict]:
    """加载一致性规则 JSON，失败时返回空列表。"""
    try:
        return json.loads(_RULES_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.error("Failed to load a17_consistency_rules.json: %s", e)
        return []


def _content_matches(content: str | None, pattern: str | None) -> bool:
    """检查内容是否匹配正则 pattern。"""
    if not content or not pattern:
        return False
    return bool(re.search(pattern, content))


def _content_is_empty(content: str | None) -> bool:
    """检查章节内容是否为空（None / 空白串 / 空 HTML）。"""
    if content is None:
        return True
    stripped = re.sub(r"<[^>]*>", "", content).strip()
    return len(stripped) == 0


def is_a_class_or_listed(business_category: Optional[str]) -> bool:
    """A 类业务前缀或中文「上市公司」别名。"""
    if not business_category:
        return False
    cat = business_category.strip()
    if cat in _LISTED_ALIASES:
        return True
    if cat.upper().startswith("A"):
        return True
    return False


def check_consistency(
    chapters: dict[str, str | None],
    business_category: Optional[str] = None,
    context: Optional[dict[str, Any]] = None,
) -> list[ConsistencyResult]:
    """执行跨章节一致性校验。

    Args:
        chapters: 章节 ID → 内容 的映射 (e.g. {"A17-1-ch01": "...", ...})
        business_category: 项目业务分类（可为 None；支持 A1/A2 或「上市公司」）
        context: 跨底稿上下文，如
            {"a177_signed": bool, "a173_has_content": bool, "a1731_closed": bool}

    Returns:
        触发的规则结果列表
    """
    rules = _load_rules()
    ctx = context or {}
    results: list[ConsistencyResult] = []

    for rule in rules:
        rule_id = rule.get("rule_id", "unknown")
        condition = rule.get("condition", "")
        severity = rule.get("severity", "info")
        description = rule.get("description", "")
        source_chapter = rule.get("source_chapter")
        target_chapter = rule.get("target_chapter")
        source_pattern = rule.get("source_pattern")
        target_pattern = rule.get("target_pattern")

        source_content = chapters.get(source_chapter) if source_chapter else None
        target_content = chapters.get(target_chapter) if target_chapter else None

        triggered = _evaluate_condition(
            condition=condition,
            source_content=source_content,
            target_content=target_content,
            source_pattern=source_pattern,
            target_pattern=target_pattern,
            business_category=business_category,
            context=ctx,
        )

        if triggered:
            affected = [ch for ch in [source_chapter, target_chapter] if ch]
            # 跨底稿规则补充受影响标识
            if "a177" in rule_id:
                affected = list(dict.fromkeys([*affected, "A17-7"]))
            if "consultation" in rule_id:
                affected = list(dict.fromkeys([*affected, "A17-3", "A17-3-1"]))
            results.append(
                ConsistencyResult(
                    rule_id=rule_id,
                    severity=severity,
                    affected_chapters=affected,
                    description=description,
                )
            )

    return results


def _ctx_flag(context: dict[str, Any], key: str) -> bool:
    """读取 context 布尔标志；缺失视为 False。"""
    val = context.get(key)
    return bool(val)


def _evaluate_condition(
    condition: str,
    source_content: str | None,
    target_content: str | None,
    source_pattern: str | None,
    target_pattern: str | None,
    business_category: Optional[str],
    context: dict[str, Any],
) -> bool:
    """根据 condition 字符串评估规则是否触发。"""

    if condition == "source_matches AND target_matches":
        return _content_matches(source_content, source_pattern) and _content_matches(
            target_content, target_pattern
        )

    if condition == "source_matches AND NOT target_matches":
        return _content_matches(source_content, source_pattern) and not _content_matches(
            target_content, target_pattern
        )

    if condition == "source_empty AND is_a_class_or_listed":
        return _content_is_empty(source_content) and is_a_class_or_listed(business_category)

    if condition == "source_filled AND NOT context.a177_signed":
        return (not _content_is_empty(source_content)) and (
            not _ctx_flag(context, "a177_signed")
        )

    if condition == "context.a173_has_content AND NOT context.a1731_closed":
        return _ctx_flag(context, "a173_has_content") and (
            not _ctx_flag(context, "a1731_closed")
        )

    if condition.startswith("source_empty AND project.business_category"):
        # 兼容旧规则: source_empty AND project.business_category == '上市公司'
        if business_category is None:
            return False
        match = re.search(r"==\s*'([^']+)'", condition)
        if not match:
            return False
        expected_category = match.group(1)
        # 「上市公司」规则同时接受 A 类编码
        if expected_category in _LISTED_ALIASES:
            return _content_is_empty(source_content) and is_a_class_or_listed(
                business_category
            )
        return _content_is_empty(source_content) and business_category == expected_category

    logger.warning("Unknown condition format: %s", condition)
    return False
