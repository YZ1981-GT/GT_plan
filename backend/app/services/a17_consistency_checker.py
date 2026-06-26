"""a17_consistency_checker — 跨章节一致性校验引擎

加载 backend/data/a17_consistency_rules.json 中的规则，
对 A17-1 的 16 章内容执行正则匹配逻辑校验，返回结构化结果。

支持的 condition 模式:
- source_matches AND target_matches
- source_matches AND NOT target_matches
- source_empty AND project.business_category == 'xxx'
"""

import json
import logging
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).resolve().parents[2] / "data"
_RULES_PATH = _DATA_DIR / "a17_consistency_rules.json"


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
    """检查章节内容是否为空（None / 空白串）。"""
    if content is None:
        return True
    # 去除 HTML 标签后判断是否为纯空白
    stripped = re.sub(r"<[^>]*>", "", content).strip()
    return len(stripped) == 0


def check_consistency(
    chapters: dict[str, str | None],
    business_category: Optional[str] = None,
) -> list[ConsistencyResult]:
    """执行跨章节一致性校验。

    Args:
        chapters: 章节 ID → 内容 的映射 (e.g. {"A17-1-ch01": "...", ...})
        business_category: 项目业务分类（可为 None）

    Returns:
        触发的规则结果列表
    """
    rules = _load_rules()
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
        )

        if triggered:
            affected = [ch for ch in [source_chapter, target_chapter] if ch]
            results.append(
                ConsistencyResult(
                    rule_id=rule_id,
                    severity=severity,
                    affected_chapters=affected,
                    description=description,
                )
            )

    return results


def _evaluate_condition(
    condition: str,
    source_content: str | None,
    target_content: str | None,
    source_pattern: str | None,
    target_pattern: str | None,
    business_category: Optional[str],
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

    if condition.startswith("source_empty AND project.business_category"):
        # 解析期望的 business_category 值
        # 格式: source_empty AND project.business_category == '上市公司'
        if business_category is None:
            # business_category 为 null → 跳过此规则
            return False
        match = re.search(r"==\s*'([^']+)'", condition)
        if not match:
            return False
        expected_category = match.group(1)
        return _content_is_empty(source_content) and business_category == expected_category

    logger.warning("Unknown condition format: %s", condition)
    return False
