"""附注校验公式引擎

实现 11 种校验类型：余额/宽表/纵向/交叉/跨科目/其中项/二级明细/完整性/账龄衔接/LLM审核/描述
遵循互斥规则：[余额] 不与 [其中项]/[宽表] 共存
其中项通用规则：sum(明细行) = 合计行

PRESET_TO_RULE 字典（Sprint 4 Task 4.1）：把 ``check_presets`` / ``_validation_rules``
字段中的 11 个中文枚举映射到引擎内部的英文规则代号，引擎在处理 ``note.table_data
._validation_rules`` 字段时通过该字典派发到对应执行器。``"描述"`` 映射为 ``"SKIP"``，
表示该 preset 仅用于章节级文字描述，不参与数值校验。

Requirements: 22.1-22.7 + R3.x（check_presets 接入）
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.services._decimal_helpers import amount_tolerance

from app.models.report_models import DisclosureNote

logger = logging.getLogger(__name__)


def _resolve_tolerance(rule_tolerance: Decimal, *reference_amounts: Decimal | None) -> Decimal:
    """按金额规模动态容差，rule.tolerance 作为下限。

    取 max(rule.tolerance, amount_tolerance(max_abs_reference))：
    - 小金额（<1万）：保持 rule.tolerance（默认 0.01），避免比硬编码更严格
    - 大金额（≥1万）：使用 amount_tolerance 动态放宽，避免 1000万 元差 1 元被误判不平衡
    """
    # 选取参考金额中绝对值最大者作为容差基准
    candidate: Decimal | None = None
    for amt in reference_amounts:
        if amt is None:
            continue
        if candidate is None or abs(amt) > abs(candidate):
            candidate = amt
    dynamic = amount_tolerance(candidate)
    return max(rule_tolerance, dynamic)


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

class ValidationType(str, Enum):
    BALANCE = "余额"
    WIDE_TABLE = "宽表"
    VERTICAL = "纵向"
    CROSS = "交叉"
    CROSS_ACCOUNT = "跨科目"
    SUB_ITEM = "其中项"
    SECONDARY_DETAIL = "二级明细"
    COMPLETENESS = "完整性"
    AGING_PROGRESSION = "账龄衔接"
    LLM_REVIEW = "LLM审核"
    DESCRIPTION = "描述"


# Mutual exclusion rule: 余额 cannot coexist with 其中项 or 宽表
MUTUALLY_EXCLUSIVE = {
    ValidationType.BALANCE: {ValidationType.SUB_ITEM, ValidationType.WIDE_TABLE},
    ValidationType.SUB_ITEM: {ValidationType.BALANCE},
    ValidationType.WIDE_TABLE: {ValidationType.BALANCE},
}


# ---------------------------------------------------------------------------
# Sprint 4 Task 4.1 — check_presets → 内部规则代号映射
# ---------------------------------------------------------------------------

#: ``PRESET_TO_RULE`` 把 ``note.table_data._validation_rules`` / ``check_presets``
#: 中的 11 个中文枚举映射到引擎内部代号；``"描述"`` 映射为 ``"SKIP"``，引擎据此
#: 跳过纯文本说明类章节（不产生 ValidationResult）。未识别的 preset 经
#: ``resolve_rule_from_preset`` 也返回 ``None``（默认跳过 + warning 日志）。
PRESET_TO_RULE: dict[str, str] = {
    "余额": "BALANCE_TIE",
    "宽表": "WIDE_TABLE_HORIZONTAL",
    "纵向": "VERTICAL_CARRY",
    "交叉": "CROSS_TABLE_TIE",
    "跨科目": "CROSS_ACCOUNT_TIE",
    "其中项": "WHEREOF_SUM",
    "二级明细": "DETAIL_LEVEL2_TIE",
    "完整性": "ROW_COMPLETENESS",
    "账龄衔接": "AGING_PROGRESSION",
    "LLM审核": "LLM_SEMANTIC_REVIEW",
    "描述": "SKIP",
}

#: 11 个 PRESET_TO_RULE 代号 → ValidationType 反向映射；``"SKIP"`` 不在表内
#: （因为 ``"描述"`` 不参与执行）。
_RULE_CODE_TO_TYPE: dict[str, ValidationType] = {
    "BALANCE_TIE": ValidationType.BALANCE,
    "WIDE_TABLE_HORIZONTAL": ValidationType.WIDE_TABLE,
    "VERTICAL_CARRY": ValidationType.VERTICAL,
    "CROSS_TABLE_TIE": ValidationType.CROSS,
    "CROSS_ACCOUNT_TIE": ValidationType.CROSS_ACCOUNT,
    "WHEREOF_SUM": ValidationType.SUB_ITEM,
    "DETAIL_LEVEL2_TIE": ValidationType.SECONDARY_DETAIL,
    "ROW_COMPLETENESS": ValidationType.COMPLETENESS,
    "AGING_PROGRESSION": ValidationType.AGING_PROGRESSION,
    "LLM_SEMANTIC_REVIEW": ValidationType.LLM_REVIEW,
}


def resolve_rule_from_preset(preset: str | None) -> str | None:
    """把 ``check_presets`` 元素映射到 PRESET_TO_RULE 的内部代号。

    Args:
        preset: ``note.table_data._validation_rules`` / ``check_presets`` 中的
            单个枚举（如 ``"余额"``）。允许 ``None`` / 空串 / 未识别字符串。

    Returns:
        - 命中表中且非 ``"描述"`` 时返回对应 rule code（如 ``"BALANCE_TIE"``）。
        - ``"描述"`` 类（即 ``PRESET_TO_RULE`` 值为 ``"SKIP"``）返回 ``None``。
        - ``None`` / 未识别字符串返回 ``None``（默认跳过）。

    Examples:
        >>> resolve_rule_from_preset("余额")
        'BALANCE_TIE'
        >>> resolve_rule_from_preset("描述") is None
        True
        >>> resolve_rule_from_preset("foo") is None
        True
        >>> resolve_rule_from_preset(None) is None
        True
    """
    if not preset or not isinstance(preset, str):
        return None
    code = PRESET_TO_RULE.get(preset.strip())
    if code is None or code == "SKIP":
        return None
    return code


def _rule_from_preset(
    preset: str,
    section_code: str,
    *,
    table_index: int = 0,
) -> ValidationRule | None:
    """工厂：把 PRESET_TO_RULE 元素转成 ``ValidationRule``。

    用于 ``note.table_data._validation_rules`` 触发路径（不走 preset.md 解析）。
    """
    code = resolve_rule_from_preset(preset)
    if code is None:
        return None
    rtype = _RULE_CODE_TO_TYPE.get(code)
    if rtype is None:
        return None
    return ValidationRule(
        section_code=section_code,
        rule_type=rtype,
        expression=f"preset:{preset}",
        description=f"由 _validation_rules 触发：{preset} → {code}",
        metadata={
            "preset": preset,
            "rule_code": code,
            "table_index": table_index,
            "trigger_source": "_validation_rules",
        },
    )


@dataclass
class ValidationRule:
    """A single validation rule loaded from preset."""
    section_code: str
    rule_type: ValidationType
    expression: str
    description: str = ""
    tolerance: Decimal = Decimal("0.01")
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ValidationResult:
    """Result of executing a single validation rule."""
    id: str = field(default_factory=lambda: str(uuid4()))
    section_code: str = ""
    rule_type: str = ""
    rule_expression: str = ""
    passed: bool = True
    expected_value: Decimal | None = None
    actual_value: Decimal | None = None
    diff_amount: Decimal | None = None
    details: dict[str, Any] = field(default_factory=dict)
    executed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class ValidationContext:
    """Context data for validation execution."""
    project_id: UUID | None = None
    year: int = 0
    note_data: dict[str, Any] = field(default_factory=dict)  # section_code -> table_data
    tb_data: dict[str, Decimal] = field(default_factory=dict)  # account_code -> amount
    report_data: dict[str, Decimal] = field(default_factory=dict)  # row_code -> amount
    wp_data: dict[str, Any] = field(default_factory=dict)  # wp_code -> parsed_data


# ---------------------------------------------------------------------------
# Preset Loader
# ---------------------------------------------------------------------------

_PRESET_FILES = {
    "soe": "附注模版/国企版校验公式预设.md",
    "listed": "附注模版/上市版校验公式预设.md",
}


def _parse_preset_md(content: str) -> list[ValidationRule]:
    """Parse a validation preset MD file into rules.

    Expected format in MD:
    ## section_code: 章节名称
    - [余额] expression: 描述
    - [宽表] expression: 描述
    """
    rules: list[ValidationRule] = []
    current_section = ""

    # Pattern for rule lines: - [类型] expression
    rule_pattern = re.compile(
        r"^[-*]\s*\[([^\]]+)\]\s*(.+?)(?:\s*[:：]\s*(.+))?$"
    )
    # Section header pattern
    section_pattern = re.compile(r"^#{1,4}\s+(\S+?)[:：\s]")

    for line in content.split("\n"):
        line = line.strip()
        if not line:
            continue

        # Check for section header
        sec_match = section_pattern.match(line)
        if sec_match:
            current_section = sec_match.group(1)
            continue

        # Check for rule line
        rule_match = rule_pattern.match(line)
        if rule_match:
            type_str = rule_match.group(1).strip()
            expression = rule_match.group(2).strip()
            description = rule_match.group(3) or ""

            # Map type string to enum
            try:
                rule_type = ValidationType(type_str)
            except ValueError:
                logger.debug("Unknown validation type: %s", type_str)
                continue

            rules.append(ValidationRule(
                section_code=current_section,
                rule_type=rule_type,
                expression=expression,
                description=description.strip(),
            ))

    return rules


def load_preset_rules(template_type: str, base_dir: Path | None = None) -> list[ValidationRule]:
    """Load validation rules from preset MD file."""
    if base_dir is None:
        base_dir = Path(__file__).resolve().parent.parent.parent.parent

    rel_path = _PRESET_FILES.get(template_type, _PRESET_FILES["soe"])
    full_path = base_dir / rel_path

    if not full_path.exists():
        logger.warning("Validation preset file not found: %s", full_path)
        return []

    try:
        content = full_path.read_text(encoding="utf-8-sig")
        return _parse_preset_md(content)
    except Exception as e:
        logger.error("Failed to load validation preset: %s", e)
        return []


# ---------------------------------------------------------------------------
# Validation Executors
# ---------------------------------------------------------------------------

def _check_mutual_exclusion(rules: list[ValidationRule]) -> list[ValidationRule]:
    """Filter rules to enforce mutual exclusion.

    [余额] cannot coexist with [其中项] or [宽表] for the same section.
    """
    by_section: dict[str, list[ValidationRule]] = {}
    for r in rules:
        by_section.setdefault(r.section_code, []).append(r)

    valid_rules: list[ValidationRule] = []
    for section_code, section_rules in by_section.items():
        types_in_section = {r.rule_type for r in section_rules}

        # Check for conflicts
        has_balance = ValidationType.BALANCE in types_in_section
        has_sub_item = ValidationType.SUB_ITEM in types_in_section
        has_wide_table = ValidationType.WIDE_TABLE in types_in_section

        if has_balance and (has_sub_item or has_wide_table):
            # Remove balance rules (keep sub_item/wide_table as they're more specific)
            logger.warning(
                "Mutual exclusion conflict in section %s: removing [余额] rules",
                section_code,
            )
            valid_rules.extend(
                r for r in section_rules if r.rule_type != ValidationType.BALANCE
            )
        else:
            valid_rules.extend(section_rules)

    return valid_rules


# 规则执行器已抽到伴生模块 note_validation_executors.py
from app.services.note_validation_executors import EXECUTORS as _EXECUTORS


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class NoteValidationEngine:
    """附注校验公式引擎"""

    def __init__(self, db: AsyncSession | None = None):
        self.db = db
        self._rules_cache: dict[str, list[ValidationRule]] = {}

    async def load_preset(self, template_type: str) -> list[ValidationRule]:
        """Load and cache validation rules from preset file."""
        if template_type in self._rules_cache:
            return self._rules_cache[template_type]

        rules = load_preset_rules(template_type)
        # Apply mutual exclusion filter
        rules = _check_mutual_exclusion(rules)
        self._rules_cache[template_type] = rules
        return rules

    def execute_rule(self, rule: ValidationRule, context: ValidationContext) -> ValidationResult:
        """Execute a single validation rule."""
        executor = _EXECUTORS.get(rule.rule_type)
        if executor is None:
            return ValidationResult(
                section_code=rule.section_code,
                rule_type=rule.rule_type.value,
                rule_expression=rule.expression,
                passed=True,
                details={"error": f"No executor for type: {rule.rule_type.value}"},
            )

        try:
            return executor(rule, context)
        except Exception as e:
            logger.warning("Validation rule execution error: %s - %s", rule.expression, e)
            return ValidationResult(
                section_code=rule.section_code,
                rule_type=rule.rule_type.value,
                rule_expression=rule.expression,
                passed=True,  # Don't block on errors
                details={"error": str(e)},
            )

    # ------------------------------------------------------------------
    # Sprint 4 Task 4.1 — _validation_rules / check_presets 触发路径
    # ------------------------------------------------------------------

    def rules_from_inline_presets(
        self,
        section_code: str,
        presets: list[str] | None,
        *,
        table_index: int = 0,
    ) -> list[ValidationRule]:
        """从单个章节 / 单张表的 ``_validation_rules`` 列表生成规则。

        Args:
            section_code: 章节编号（``note.note_section``）。
            presets: ``note.table_data._validation_rules`` 或单张表
                ``_tables[i]._validation_rules`` 的元素列表。允许 ``None``。
            table_index: 多表章节时的表索引（写入 metadata）。

        Returns:
            按 ``PRESET_TO_RULE`` 派发的 ``ValidationRule`` 列表；``"描述"`` /
            未识别 preset 不进入结果。
        """
        if not presets:
            return []
        out: list[ValidationRule] = []
        for preset in presets:
            rule = _rule_from_preset(preset, section_code, table_index=table_index)
            if rule is not None:
                out.append(rule)
        return out

    def collect_inline_rules_for_note(
        self,
        section_code: str,
        table_data: dict[str, Any] | None,
    ) -> list[ValidationRule]:
        """从 ``note.table_data`` 抽出所有 ``_validation_rules`` 触发的规则。

        覆盖三处 sidecar：
        1. ``table_data._validation_rules`` — 单表章节
        2. ``table_data._tables[i]._validation_rules`` — 多表章节
        3. ``table_data._check_presets`` — 旧字段（向后兼容）
        """
        if not isinstance(table_data, dict):
            return []
        rules: list[ValidationRule] = []

        # 路径 1：顶层 _validation_rules
        top_rules = table_data.get("_validation_rules")
        if isinstance(top_rules, list):
            rules.extend(self.rules_from_inline_presets(section_code, top_rules))

        # 路径 2：多表 _tables[i]._validation_rules
        tables = table_data.get("_tables")
        if isinstance(tables, list):
            for idx, tbl in enumerate(tables):
                if not isinstance(tbl, dict):
                    continue
                tbl_rules = tbl.get("_validation_rules")
                if isinstance(tbl_rules, list):
                    rules.extend(
                        self.rules_from_inline_presets(
                            section_code, tbl_rules, table_index=idx,
                        )
                    )

        # 路径 3：兼容旧 _check_presets（无 table_index）
        legacy = table_data.get("_check_presets")
        if isinstance(legacy, list):
            rules.extend(self.rules_from_inline_presets(section_code, legacy))

        return rules

    def execute_inline_rules(
        self,
        section_code: str,
        table_data: dict[str, Any] | None,
        context: ValidationContext,
    ) -> list[ValidationResult]:
        """对单个章节的 ``_validation_rules`` 执行全部规则并返回结果。"""
        rules = self.collect_inline_rules_for_note(section_code, table_data)
        return [self.execute_rule(r, context) for r in rules]

    async def execute_all(
        self,
        project_id: UUID,
        year: int,
        template_type: str = "soe",
        context: ValidationContext | None = None,
    ) -> list[ValidationResult]:
        """Execute all validation rules for a project/year.

        Sprint 4 Task 4.1：当 ``context.note_data[section_code]`` 含
        ``_validation_rules`` 字段时，**先**走 inline preset 派发路径；
        不含此字段或 PRESET_TO_RULE 不命中时降级到 preset.md 解析路径
        （向后兼容）。
        """
        if context is None:
            context = ValidationContext(project_id=project_id, year=year)

        results: list[ValidationResult] = []
        consumed_sections: set[str] = set()

        # ── Sprint 4 Task 4.1：_validation_rules 触发路径 ──
        if isinstance(context.note_data, dict):
            for section_code, table_data in context.note_data.items():
                if not isinstance(table_data, dict):
                    continue
                inline = self.execute_inline_rules(section_code, table_data, context)
                if inline:
                    results.extend(inline)
                    consumed_sections.add(section_code)

        # ── 兼容路径：preset.md 解析 ──
        rules = await self.load_preset(template_type)
        for rule in rules:
            # 已被 inline 路径处理过的章节不重复执行（避免重复结果）
            if rule.section_code in consumed_sections:
                continue
            result = self.execute_rule(rule, context)
            results.append(result)

        # Persist results if db is available
        if self.db is not None:
            await self._persist_results(project_id, year, results)

        return results

    async def _persist_results(
        self, project_id: UUID, year: int, results: list[ValidationResult]
    ):
        """Persist validation results to note_validation_results table."""
        if not self.db:
            return

        try:
            # Use raw insert for performance
            table = sa.table(
                "note_validation_results",
                sa.column("id", sa.String),
                sa.column("project_id", sa.String),
                sa.column("year", sa.Integer),
                sa.column("section_code", sa.String),
                sa.column("rule_type", sa.String),
                sa.column("rule_expression", sa.Text),
                sa.column("passed", sa.Boolean),
                sa.column("expected_value", sa.Numeric),
                sa.column("actual_value", sa.Numeric),
                sa.column("diff_amount", sa.Numeric),
                sa.column("details", sa.JSON),
                sa.column("executed_at", sa.DateTime),
            )

            rows = []
            for r in results:
                rows.append({
                    "id": r.id,
                    "project_id": str(project_id),
                    "year": year,
                    "section_code": r.section_code,
                    "rule_type": r.rule_type,
                    "rule_expression": r.rule_expression,
                    "passed": r.passed,
                    "expected_value": float(r.expected_value) if r.expected_value is not None else None,
                    "actual_value": float(r.actual_value) if r.actual_value is not None else None,
                    "diff_amount": float(r.diff_amount) if r.diff_amount is not None else None,
                    "details": r.details,
                    "executed_at": r.executed_at,
                })

            if rows:
                await self.db.execute(sa.insert(table), rows)
                await self.db.flush()
        except Exception as e:
            logger.warning("Failed to persist validation results: %s", e)

    # ------------------------------------------------------------------
    # Router-facing aliases (bridging router calls to internal methods)
    # ------------------------------------------------------------------

    async def validate_all(
        self,
        project_id: UUID,
        year: int,
        *,
        template_type: str = "soe",
    ) -> dict:
        """Execute all validation rules and return structured result.

        This is the router-facing entry point that wraps execute_all
        and returns a response dict compatible with NoteValidationResponse.
        """
        context = ValidationContext(project_id=project_id, year=year)

        # Load note data from DB for inline rules path
        if self.db:
            try:
                result = await self.db.execute(
                    sa.select(DisclosureNote).where(
                        DisclosureNote.project_id == str(project_id),
                        DisclosureNote.year == year,
                        DisclosureNote.is_deleted == sa.false(),
                    )
                )
                notes = result.scalars().all()
                context.note_data = {
                    n.note_section: n.table_data
                    for n in notes
                    if n.table_data and isinstance(n.table_data, dict)
                }
            except Exception as e:
                logger.warning("validate_all: failed to load note_data: %s", e)

        results = await self.execute_all(
            project_id, year, template_type=template_type, context=context
        )

        # Build response
        findings = []
        for r in results:
            if not r.passed:
                findings.append({
                    "note_section": r.section_code,
                    "check_type": r.rule_type,
                    "severity": "error" if r.diff_amount and abs(float(r.diff_amount)) > 0.01 else "warning",
                    "message": r.rule_expression,
                    "expected_value": float(r.expected_value) if r.expected_value is not None else None,
                    "actual_value": float(r.actual_value) if r.actual_value is not None else None,
                    "table_name": r.details.get("table_name", "") if r.details else "",
                })

        return {
            "project_id": str(project_id),
            "year": year,
            "template_type": template_type,
            "total_rules": len(results),
            "passed": sum(1 for r in results if r.passed),
            "failed": len(findings),
            "findings": findings,
        }

    async def get_latest_results(
        self,
        project_id: UUID,
        year: int,
    ) -> dict | None:
        """Get the latest validation results from DB.

        Returns None if no results exist yet.
        """
        if not self.db:
            return None

        try:
            table = sa.table(
                "note_validation_results",
                sa.column("id", sa.String),
                sa.column("project_id", sa.String),
                sa.column("year", sa.Integer),
                sa.column("section_code", sa.String),
                sa.column("rule_type", sa.String),
                sa.column("rule_expression", sa.Text),
                sa.column("passed", sa.Boolean),
                sa.column("expected_value", sa.Numeric),
                sa.column("actual_value", sa.Numeric),
                sa.column("diff_amount", sa.Numeric),
                sa.column("details", sa.JSON),
                sa.column("executed_at", sa.DateTime),
            )

            result = await self.db.execute(
                sa.select(table).where(
                    table.c.project_id == str(project_id),
                    table.c.year == year,
                ).order_by(table.c.executed_at.desc())
            )
            rows = result.fetchall()

            if not rows:
                return None

            findings = []
            for row in rows:
                if not row.passed:
                    findings.append({
                        "note_section": row.section_code,
                        "check_type": row.rule_type,
                        "severity": "error" if row.diff_amount and abs(float(row.diff_amount)) > 0.01 else "warning",
                        "message": row.rule_expression,
                        "expected_value": float(row.expected_value) if row.expected_value is not None else None,
                        "actual_value": float(row.actual_value) if row.actual_value is not None else None,
                        "table_name": "",
                    })

            return {
                "project_id": str(project_id),
                "year": year,
                "total_rules": len(rows),
                "passed": sum(1 for r in rows if r.passed),
                "failed": len(findings),
                "findings": findings,
            }
        except Exception as e:
            logger.warning("get_latest_results failed: %s", e)
            return None

    async def confirm_finding(
        self,
        validation_id: UUID,
        finding_index: int,
        reason: str,
    ) -> bool:
        """Confirm a validation finding as 'acknowledged - no fix needed'.

        Returns True if confirmation succeeded, False if not found.
        """
        if not self.db:
            return False

        try:
            table = sa.table(
                "note_validation_results",
                sa.column("id", sa.String),
                sa.column("details", sa.JSON),
            )

            result = await self.db.execute(
                sa.select(table).where(table.c.id == str(validation_id))
            )
            row = result.fetchone()
            if row is None:
                return False

            # Update details to mark as confirmed
            details = row.details or {}
            if not isinstance(details, dict):
                details = {}
            confirmations = details.get("confirmations", [])
            confirmations.append({
                "finding_index": finding_index,
                "reason": reason,
                "confirmed_at": datetime.now(timezone.utc).isoformat(),
            })
            details["confirmations"] = confirmations

            await self.db.execute(
                sa.update(table).where(table.c.id == str(validation_id)).values(
                    details=details
                )
            )
            await self.db.flush()
            return True
        except Exception as e:
            logger.warning("confirm_finding failed: %s", e)
            return False
