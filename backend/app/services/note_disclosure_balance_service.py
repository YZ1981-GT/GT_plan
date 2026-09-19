"""附注披露平衡规则校验服务

对关键科目附注与报表金额进行自动核对，差异进入附注质量清单。

试点科目：应收账款、固定资产、关联方余额。

规则格式参考 backend/data/note_disclosure_balance_rules.json:
  - left: 附注侧聚合表达式 sum(note.section.table.*.col)
  - right: 报表侧取值表达式 report.BS.item.amount_role
  - tolerance: 容差（绝对值）
  - severity: blocking | warning

Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5
"""

from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from app.services.note_quality_checklist_service import QualityChecklistItem


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

_RULES_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "note_disclosure_balance_rules.json"

_LEFT_PATTERN = re.compile(
    r"^sum\(note\.(?P<section>[^.]+)\.(?P<table>[^.]+)\.\*\.(?P<col>[^)]+)\)$"
)

_RIGHT_PATTERN = re.compile(
    r"^report\.(?P<statement>[^.]+)\.(?P<item>[^.]+)\.(?P<amount_role>[^.]+)$"
)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


class BalanceRule:
    """单条披露平衡规则"""

    def __init__(self, raw: dict[str, Any]) -> None:
        self.rule_id: str = raw["rule_id"]
        self.section_id: str = raw["section_id"]
        self.description: str = raw.get("description", "")
        self.left: str = raw["left"]
        self.right: str = raw["right"]
        self.tolerance: Decimal = Decimal(str(raw.get("tolerance", "0.01")))
        self.severity: str = raw.get("severity", "warning")


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class NoteDisclosureBalanceService:
    """附注披露平衡校验服务

    核心方法 check_balance_rules 接收规则列表、附注数据和报表数据，
    返回差异条目列表（QualityChecklistItem）。
    """

    def __init__(self, rules_path: Path | None = None) -> None:
        self._rules_path = rules_path or _RULES_FILE

    # ------------------------------------------------------------------
    # 公开方法
    # ------------------------------------------------------------------

    def load_rules(self) -> list[BalanceRule]:
        """从 JSON 加载规则列表"""
        if not self._rules_path.exists():
            return []
        with open(self._rules_path, encoding="utf-8") as f:
            data = json.load(f)
        return [BalanceRule(r) for r in data.get("rules", [])]

    def check_balance_rules(
        self,
        rules: list[BalanceRule],
        note_data: dict[str, Any],
        report_data: dict[str, Any],
    ) -> list[QualityChecklistItem]:
        """执行平衡规则校验

        Args:
            rules: 规则列表
            note_data: 附注数据，结构为 {section_id: {table_id: [{col: value}, ...]}}
            report_data: 报表数据，结构为 {statement: {item: {amount_role: value}}}

        Returns:
            差异质量清单条目列表
        """
        items: list[QualityChecklistItem] = []
        for rule in rules:
            result = self._evaluate_rule(rule, note_data, report_data)
            if result is not None:
                items.append(result)
        return items

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _evaluate_rule(
        self,
        rule: BalanceRule,
        note_data: dict[str, Any],
        report_data: dict[str, Any],
    ) -> QualityChecklistItem | None:
        """评估单条规则，返回差异条目或 None"""
        left_value = self._resolve_left(rule.left, note_data)
        right_value = self._resolve_right(rule.right, report_data)

        if left_value is None or right_value is None:
            # 数据缺失，生成 completeness 类型问题
            missing_side = "附注" if left_value is None else "报表"
            return QualityChecklistItem(
                level="warning",
                category="completeness",
                section_id=rule.section_id,
                message=f"{rule.description}：{missing_side}数据缺失",
                route=f"/projects/{{pid}}/disclosure-notes?section={rule.section_id}",
                evidence={
                    "rule_id": rule.rule_id,
                    "left": str(left_value),
                    "right": str(right_value),
                    "missing": missing_side,
                },
            )

        diff = abs(left_value - right_value)
        if diff > rule.tolerance:
            return QualityChecklistItem(
                level=rule.severity,
                category="tieout",
                section_id=rule.section_id,
                message=f"{rule.description}：差异 {diff:.2f}",
                route=f"/projects/{{pid}}/disclosure-notes?section={rule.section_id}",
                evidence={
                    "rule_id": rule.rule_id,
                    "left": str(left_value),
                    "right": str(right_value),
                    "diff": str(diff),
                    "tolerance": str(rule.tolerance),
                },
            )
        return None

    def _resolve_left(self, expr: str, note_data: dict[str, Any]) -> Decimal | None:
        """解析附注侧聚合表达式

        格式: sum(note.section.table.*.col)
        从 note_data[section][table] 列表中对每行的 col 求和。
        """
        match = _LEFT_PATTERN.match(expr)
        if not match:
            return None

        section = match.group("section")
        table = match.group("table")
        col = match.group("col")

        section_data = note_data.get(section)
        if not section_data or not isinstance(section_data, dict):
            return None

        table_rows = section_data.get(table)
        if not table_rows or not isinstance(table_rows, list):
            return None

        total = Decimal("0")
        for row in table_rows:
            if not isinstance(row, dict):
                continue
            val = row.get(col)
            if val is None:
                continue
            try:
                total += Decimal(str(val))
            except (InvalidOperation, ValueError):
                continue

        return total

    def _resolve_right(self, expr: str, report_data: dict[str, Any]) -> Decimal | None:
        """解析报表侧取值表达式

        格式: report.statement.item.amount_role
        从 report_data[statement][item][amount_role] 取值。
        """
        match = _RIGHT_PATTERN.match(expr)
        if not match:
            return None

        statement = match.group("statement")
        item = match.group("item")
        amount_role = match.group("amount_role")

        stmt_data = report_data.get(statement)
        if not stmt_data or not isinstance(stmt_data, dict):
            return None

        item_data = stmt_data.get(item)
        if not item_data or not isinstance(item_data, dict):
            return None

        val = item_data.get(amount_role)
        if val is None:
            return None

        try:
            return Decimal(str(val))
        except (InvalidOperation, ValueError):
            return None
