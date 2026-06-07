"""质量问题类型库服务 — P2-3 实现

基于配置 JSON 管理问题类型（ADR-032 决策）。
支持：归类、统计重复、导出培训材料候选清单。

Requirements: 6.1, 6.2
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 配置文件路径
_CONFIG_PATH = Path(__file__).parent.parent.parent / "data" / "quality_issue_types.json"


# ─── 配置加载 ─────────────────────────────────────────────────────────────────


@lru_cache(maxsize=1)
def _load_config() -> dict[str, Any]:
    """加载质量问题类型配置（带缓存）。"""
    if not _CONFIG_PATH.exists():
        logger.warning(f"[QualityIssueType] config not found: {_CONFIG_PATH}")
        return {"types": [], "categories": {}}
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def reload_config() -> dict[str, Any]:
    """强制重新加载配置（测试或热更新时用）。"""
    _load_config.cache_clear()
    return _load_config()


# ─── 服务 ─────────────────────────────────────────────────────────────────────


class QualityIssueTypeService:
    """质量问题类型库

    基于 backend/data/quality_issue_types.json 配置驱动。
    """

    # ─── P2-3.5 获取所有类型定义 ──────────────────────────────────────────

    def get_all_types(self) -> list[dict[str, Any]]:
        """返回全部问题类型列表。"""
        config = _load_config()
        return config.get("types", [])

    def get_type_by_code(self, code: str) -> dict[str, Any] | None:
        """根据 code 获取单个问题类型。"""
        for t in self.get_all_types():
            if t["code"] == code:
                return t
        return None

    def get_categories(self) -> dict[str, str]:
        """返回问题分类映射 {code: name_zh}。"""
        config = _load_config()
        return config.get("categories", {})

    def get_types_by_category(self, category: str) -> list[dict[str, Any]]:
        """按分类过滤问题类型。"""
        return [t for t in self.get_all_types() if t.get("category") == category]

    # ─── P2-3.6 复核/QC 问题支持归类 ─────────────────────────────────────

    def classify_issue(
        self,
        issue_type_code: str,
    ) -> dict[str, Any] | None:
        """验证并返回问题类型信息（用于给问题归类）。

        Returns None if code is invalid.
        """
        type_def = self.get_type_by_code(issue_type_code)
        if type_def is None:
            return None
        return {
            "code": type_def["code"],
            "name_zh": type_def["name_zh"],
            "category": type_def["category"],
            "severity_default": type_def["severity_default"],
        }

    def validate_type_code(self, code: str) -> bool:
        """验证 type_code 是否存在于配置中。"""
        return self.get_type_by_code(code) is not None

    # ─── P2-3.7 统计重复问题 ─────────────────────────────────────────────

    def count_by_type(
        self,
        issues: list[dict[str, Any]],
    ) -> dict[str, int]:
        """统计问题列表中各类型的出现次数。

        Args:
            issues: 问题列表，每个 dict 需含 issue_type_code 字段

        Returns:
            {type_code: count}
        """
        counts: dict[str, int] = {}
        for issue in issues:
            code = issue.get("issue_type_code")
            if code:
                counts[code] = counts.get(code, 0) + 1
        return counts

    def find_repeated_issues(
        self,
        issues: list[dict[str, Any]],
        threshold: int = 2,
    ) -> list[dict[str, Any]]:
        """找出重复出现的问题类型（出现次数 >= threshold）。

        Returns:
            [{code, name_zh, count, severity_default, training_hint}]
        """
        counts = self.count_by_type(issues)
        repeated = []
        for code, count in sorted(counts.items(), key=lambda x: -x[1]):
            if count >= threshold:
                type_def = self.get_type_by_code(code)
                if type_def:
                    repeated.append({
                        "code": code,
                        "name_zh": type_def["name_zh"],
                        "count": count,
                        "severity_default": type_def["severity_default"],
                        "training_hint": type_def.get("training_hint", ""),
                    })
        return repeated

    # ─── P2-3.8 导出培训材料候选清单 ────────────────────────────────────

    def export_training_candidates(
        self,
        issues: list[dict[str, Any]],
        min_occurrences: int = 2,
    ) -> list[dict[str, Any]]:
        """导出培训材料候选清单。

        基于重复问题统计，输出需要培训的主题列表。

        Returns:
            [{
                code, name_zh, category, count,
                severity_default, training_hint, examples,
                priority (based on count * severity weight)
            }]
        """
        repeated = self.find_repeated_issues(issues, threshold=min_occurrences)

        severity_weight = {"critical": 4, "high": 3, "medium": 2, "low": 1}
        candidates = []
        for item in repeated:
            type_def = self.get_type_by_code(item["code"])
            if not type_def:
                continue

            weight = severity_weight.get(item["severity_default"], 1)
            priority_score = item["count"] * weight

            candidates.append({
                "code": item["code"],
                "name_zh": item["name_zh"],
                "category": type_def.get("category", ""),
                "category_name": self.get_categories().get(type_def.get("category", ""), ""),
                "count": item["count"],
                "severity_default": item["severity_default"],
                "training_hint": item.get("training_hint", ""),
                "examples": type_def.get("examples", []),
                "priority_score": priority_score,
            })

        # 按优先级降序
        candidates.sort(key=lambda x: -x["priority_score"])
        return candidates
