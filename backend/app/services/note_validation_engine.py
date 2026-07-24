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
from functools import lru_cache
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
    # 账龄衔接校验用：上年（year-1）附注表格数据 section_code -> table_data（可选，向后兼容）
    prior_note_data: dict[str, Any] = field(default_factory=dict)
    # 完整性校验用：account_code -> note_section（可选；空则完整性回退 section-scope 粗检，Req7.3）
    account_section_map: dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Preset Loader
# ---------------------------------------------------------------------------

# 校验公式预设 md 相对项目根（``Path(__file__).parents[3]`` = ``d:\GT_plan``）的路径。
# 实际文件位于 ``基础数据/附注模版/`` 下（历史缺 ``基础数据/`` 前缀导致路径永远找不到）。
_PRESET_FILES = {
    "soe": "基础数据/附注模版/国企版校验公式预设.md",
    "listed": "基础数据/附注模版/上市版校验公式预设.md",
}

# markdown 表头行首列 token（跳过表头，不当数据行）
_PRESET_TABLE_HEADER_C0 = ("编号", "序号")
# markdown 分隔行单元格：``---`` / ``:---:`` / ``:--``
_MD_SEPARATOR_CELL_RE = re.compile(r"^:?-{2,}:?$")


def _split_md_table_row(line: str) -> list[str] | None:
    """把一行 markdown 表格行拆成单元格列表（去首尾竖线）。非表格行返回 None。"""
    s = line.strip()
    if not s.startswith("|"):
        return None
    inner = s[1:]
    if inner.endswith("|"):
        inner = inner[:-1]
    return [c.strip() for c in inner.split("|")]


def _is_md_separator_row(cells: list[str]) -> bool:
    """判定是否为 markdown 表格分隔行（``|---|---|``）。"""
    non_empty = [c for c in cells if c != ""]
    if not non_empty:
        return False
    return all(_MD_SEPARATOR_CELL_RE.match(c) for c in non_empty)


def _clean_section_header(title: str) -> str:
    """清理 markdown 标题为 section_code：去尾随 ``#``、首尾空白。"""
    return title.strip().rstrip("#").strip()


def _normalize_expr_for_dedup(expr: str) -> str:
    """去重归一：剥离反引号 + 全部空白（同一公式的 bullet 与表格写法归一为同键）。"""
    return re.sub(r"\s+", "", (expr or "").replace("`", ""))


def _parse_preset_md(content: str) -> list[ValidationRule]:
    """把校验公式预设 md 解析成 ValidationRule 列表。

    支持两种并存格式（Req5.2 / Req5.4）：

    1. **markdown 表格**（附注模版 preset.md 实际格式，逐科目/逐表格列出）::

           ## 一、资产负债表科目
           ### 4. 应收票据
           | 编号 | 公式类型 | 校验公式 |
           |------|----------|----------|
           | F4-1 | 余额 | `报表.应收票据期末 = ①分类表.合计行.期末账面价值` |

       - 表头行（首列为「编号/序号」或含「公式类型」「校验公式」）自动跳过。
       - 分隔行（``|---|---|``）自动跳过。
       - 数据行：第 1 列=编号（存 metadata.rule_id）、第 2 列=公式类型、第 3 列=校验公式；
         若公式内含 ``|`` 被误切，则把第 3 列及之后重新拼回（robust）。
       - 无表头行的裸数据行（如 ``**⑨ 核销** `` 下直接列 ``| F4-24 | 其中项 | ... |``）
         同样能解析（不依赖表头存在）。

    2. **bullet 行**（历史格式，向后兼容）::

           ## 五、18: 存货
           - [余额] 报表.存货期末 = ①分类表.合计行.期末账面价值 : 描述

    去重（Req5.4）：同一规则以 bullet 与表格两种格式书写时（同 section_code + 公式类型 +
    归一表达式），只保留一条，不重复执行。
    """
    rules: list[ValidationRule] = []
    seen: set[tuple[str, str, str]] = set()
    current_section = ""

    bullet_pattern = re.compile(r"^[-*]\s*\[([^\]]+)\]\s*(.+?)(?:\s*[:：]\s*(.+))?$")
    header_pattern = re.compile(r"^#{1,6}\s+(.+?)\s*$")

    def _emit(
        section: str,
        type_str: str,
        expression: str,
        description: str,
        metadata: dict[str, Any],
    ) -> None:
        type_str = (type_str or "").strip()
        expression = (expression or "").strip()
        if not expression:
            return
        try:
            rule_type = ValidationType(type_str)
        except ValueError:
            logger.debug("Unknown validation type: %s", type_str)
            return
        key = (section, rule_type.value, _normalize_expr_for_dedup(expression))
        if key in seen:
            return  # 去重（bullet ↔ 表格同一规则）
        seen.add(key)
        rules.append(ValidationRule(
            section_code=section,
            rule_type=rule_type,
            expression=expression,
            description=(description or "").strip(),
            metadata=metadata,
        ))

    for raw in content.split("\n"):
        line = raw.strip()
        if not line:
            continue

        # ── markdown 表格行（优先于 bullet/header 判定：表格行以 | 起始）──
        if line.startswith("|"):
            cells = _split_md_table_row(line)
            if not cells or len(cells) < 3:
                continue
            if _is_md_separator_row(cells):
                continue
            c0, c1 = cells[0].strip(), cells[1].strip()
            # 公式列：若被内嵌 | 误切，拼回第 3 列及之后
            expr = cells[2].strip() if len(cells) == 3 else "|".join(cells[2:]).strip()
            # 跳过表头行（编号/公式类型/校验公式）
            if c0 in _PRESET_TABLE_HEADER_C0 or "公式类型" in c1 or "校验公式" in expr:
                continue
            _emit(
                current_section, c1, expr, "",
                {"rule_id": c0, "trigger_source": "preset_md_table"},
            )
            continue

        # ── markdown 标题 → 更新 current_section ──
        hm = header_pattern.match(line)
        if hm:
            current_section = _clean_section_header(hm.group(1))
            continue

        # ── bullet 规则（向后兼容）──
        bm = bullet_pattern.match(line)
        if bm:
            _emit(
                current_section, bm.group(1), bm.group(2), bm.group(3) or "",
                {"trigger_source": "preset_md_bullet"},
            )

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
# account_code → note_section 映射（完整性校验科目粒度用，Req7）
# ---------------------------------------------------------------------------

_ACCOUNT_SECTION_SEED_PATH = (
    Path(__file__).resolve().parent.parent.parent / "data" / "note_templates_seed.json"
)


@lru_cache(maxsize=1)
def build_account_section_map(base_dir: Path | None = None) -> dict[str, str]:
    """构建 ``account_code → note_section`` 映射（Req7.1）。

    真源复用披露模板 ``note_templates_seed.json`` 的 ``account_mapping_template``——
    每个披露章节的 ``table_template.rows[].account_codes`` 直接给出科目码 → note_section，
    **不新造孤立真源**。供完整性 executor 落到科目粒度（Req7.2）。

    fail-open（Req7.3）：文件缺失/解析异常 → 返回 ``{}``（完整性校验回退 section-scope 粗检）。
    结果 lru_cache（映射为静态种子，进程内不变）。

    Returns:
        ``{account_code(str): note_section(str)}``；同一科目码多处出现时保留首个（setdefault）。
    """
    import json

    seed_path = (base_dir / "note_templates_seed.json") if base_dir else _ACCOUNT_SECTION_SEED_PATH
    try:
        if not seed_path.exists():
            logger.warning("account_section_map seed not found: %s", seed_path)
            return {}
        data = json.loads(seed_path.read_text(encoding="utf-8-sig"))
    except Exception as e:  # fail-open
        logger.warning("build_account_section_map fail-open: %s", e)
        return {}

    out: dict[str, str] = {}
    for entry in data.get("account_mapping_template", []) or []:
        if not isinstance(entry, dict):
            continue
        section = str(entry.get("note_section") or "").strip()
        if not section:
            continue
        table_template = entry.get("table_template") or {}
        for row in table_template.get("rows", []) or []:
            if not isinstance(row, dict):
                continue
            for code in row.get("account_codes", []) or []:
                c = str(code).strip()
                if c:
                    out.setdefault(c, section)
    return out


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
from app.services.note_validation_executors import (
    EXECUTORS as _EXECUTORS,
    _execute_llm_review_async,
)


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

    async def _run_rule(
        self, rule: ValidationRule, context: ValidationContext
    ) -> ValidationResult:
        """按规则类型分发执行：LLM_REVIEW 走 async 特例（需 await chat_completion），
        其余 10 个同步执行器沿用同步 ``execute_rule``（行为不变）。

        LLM async 全程 fail-open（不阻断其余规则）：async 执行器内部已 try/except，
        此处再兜底一层，异常 → passed=True + skipped。
        """
        if rule.rule_type == ValidationType.LLM_REVIEW:
            try:
                return await _execute_llm_review_async(rule, context)
            except Exception as e:  # pragma: no cover - defensive fail-open
                logger.warning("LLM review async fail-open: %s", e)
                return ValidationResult(
                    section_code=rule.section_code,
                    rule_type=rule.rule_type.value,
                    rule_expression=rule.expression,
                    passed=True,
                    details={"check": "llm_review", "skipped": True, "reason": str(e), "ai_hint": True},
                )
        return self.execute_rule(rule, context)

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
                inline_rules = self.collect_inline_rules_for_note(section_code, table_data)
                if inline_rules:
                    for r in inline_rules:
                        results.append(await self._run_rule(r, context))
                    consumed_sections.add(section_code)

        # ── 兼容路径：preset.md 解析 ──
        rules = await self.load_preset(template_type)
        for rule in rules:
            # 已被 inline 路径处理过的章节不重复执行（避免重复结果）
            if rule.section_code in consumed_sections:
                continue
            results.append(await self._run_rule(rule, context))

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

    # ------------------------------------------------------------------
    # ValidationContext 数据装配（只读，每源独立 fail-open）
    # ------------------------------------------------------------------

    async def _load_report_data(self, project_id: UUID, year: int) -> dict[str, Decimal]:
        """加载报表行次审定金额 → {row_code: current_period_amount}。

        权威源：FinancialReport（BS+IS 等全部报表类型），取审定口径
        current_period_amount。异常 fail-open 置 {}。只读。
        """
        if not self.db:
            return {}
        try:
            from app.models.report_models import FinancialReport

            result = await self.db.execute(
                sa.select(
                    FinancialReport.row_code,
                    FinancialReport.current_period_amount,
                ).where(
                    FinancialReport.project_id == project_id,
                    FinancialReport.year == year,
                    FinancialReport.is_deleted == sa.false(),
                )
            )
            data: dict[str, Decimal] = {}
            for row_code, amount in result.all():
                if not row_code or amount is None:
                    continue
                # 同一 row_code 可能跨报表类型出现；保留首个非空审定金额
                if row_code not in data:
                    data[row_code] = Decimal(str(amount))
            return data
        except Exception as e:
            logger.warning("_load_report_data fail-open: %s", e)
            return {}

    async def _load_tb_data(self, project_id: UUID, year: int) -> dict[str, Decimal]:
        """加载试算表审定余额 → {standard_account_code: audited_amount}。

        经 get_active_filter（dataset 版本治理统一入口）取当前 active 数据集；
        多 company_code 时按科目汇总。异常 fail-open 置 {}。只读。
        """
        if not self.db:
            return {}
        try:
            from app.models.audit_platform_models import TrialBalance
            from app.services.dataset_query import get_active_filter

            active_filter = await get_active_filter(
                self.db, TrialBalance.__table__, project_id, year
            )
            result = await self.db.execute(
                sa.select(
                    TrialBalance.standard_account_code,
                    sa.func.sum(TrialBalance.audited_amount),
                )
                .where(active_filter)
                .group_by(TrialBalance.standard_account_code)
            )
            data: dict[str, Decimal] = {}
            for code, amount in result.all():
                if not code or amount is None:
                    continue
                data[code] = Decimal(str(amount))
            return data
        except Exception as e:
            logger.warning("_load_tb_data fail-open: %s", e)
            return {}

    async def _load_prior_notes(self, project_id: UUID, prior_year: int) -> dict[str, Any]:
        """加载上年附注表格 → {note_section: table_data}（账龄衔接用）。

        prior_year = 本年 - 1。异常 fail-open 置 {}。只读。
        """
        if not self.db:
            return {}
        try:
            result = await self.db.execute(
                sa.select(DisclosureNote).where(
                    DisclosureNote.project_id == str(project_id),
                    DisclosureNote.year == prior_year,
                    DisclosureNote.is_deleted == sa.false(),
                )
            )
            notes = result.scalars().all()
            return {
                n.note_section: n.table_data
                for n in notes
                if n.table_data and isinstance(n.table_data, dict)
            }
        except Exception as e:
            logger.warning("_load_prior_notes fail-open: %s", e)
            return {}

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

            # ── 本 spec 新增：装配 report_data / tb_data / prior_note_data ──
            # 每源独立 fail-open（异常记 warning 置 {}），不阻断整体校验。
            context.report_data = await self._load_report_data(project_id, year)
            context.tb_data = await self._load_tb_data(project_id, year)
            context.prior_note_data = await self._load_prior_notes(project_id, year - 1)

        # ── Wave4 (Task 5.4)：装配 account_code → note_section 映射（供完整性校验科目粒度）──
        # fail-open 返 {}（完整性回退 section-scope，Req7.3）；不依赖 db，无 db 时也装配。
        try:
            context.account_section_map = build_account_section_map()
        except Exception as e:  # pragma: no cover - defensive fail-open
            logger.warning("assemble account_section_map fail-open: %s", e)
            context.account_section_map = {}

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
