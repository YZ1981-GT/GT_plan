"""附注校验规则执行器 — 从 note_validation_engine.py 抽出的伴生模块

包含 11 个 _execute_* 纯函数 + _EXECUTORS 分发表。
每个执行器接收 (ValidationRule, ValidationContext) → ValidationResult。

由 NoteValidationEngine.execute_rule 通过 _EXECUTORS[rule.rule_type] 分发调用。
"""

from __future__ import annotations

import logging
import re
from decimal import Decimal
from typing import Any

from app.services.note_validation_engine import (
    ValidationContext,
    ValidationResult,
    ValidationRule,
    ValidationType,
    _resolve_tolerance,
)
from app.services.note_section_catalog import normalize_section_code
from app.services.note_wp_mapping_service import DEFAULT_WP_MAPPING

# LLM 文本审核入口（async，返回 str；失败/超时/熔断返回占位串不抛，见 _is_llm_placeholder）。
# 顶层导入以便测试在本模块命名空间 patch（app.services.note_validation_executors.chat_completion）。
from app.services.llm_client import chat_completion

logger = logging.getLogger(__name__)

# 账龄段已知 label（来自 aging_config PRESET_SEGMENTS，供 header 识别；取不到 fail-open）
try:  # pragma: no cover - import guard
    from app.services.aging_config_service import PRESET_SEGMENTS as _AGING_PRESETS

    _KNOWN_AGING_LABELS: frozenset[str] = frozenset(
        seg.label for segs in _AGING_PRESETS.values() for seg in segs
    )
except Exception:  # pragma: no cover
    _KNOWN_AGING_LABELS = frozenset(
        {"1年以内", "1-2年", "2-3年", "3-4年", "4-5年", "3年以上", "5年以上"}
    )


# ---------------------------------------------------------------------------
# Shared helpers（只读、无副作用）
# ---------------------------------------------------------------------------

# 账龄分桶 header 模式：如 "1-2年" / "2-3年" / "1年以内" / "5年以上" / "1年以上"
_AGING_LABEL_RE = re.compile(
    r"\d+\s*[-–—~至]\s*\d+\s*年"      # 1-2年 / 2至3年
    r"|\d+\s*年\s*以[内上]"           # 1年以内 / 5年以上
)
# 合计/总额列 token（账龄行的总额基准列）
_TOTAL_HEADER_TOKENS = ("合计", "总计", "小计", "账面余额", "账面价值", "期末余额", "余额")
_OPEN_HEADER_TOKENS = ("期初", "年初", "上年年末", "上年期末")
_CLOSE_HEADER_TOKENS = ("期末", "年末", "本年年末")


def _to_decimal(value: Any) -> Decimal:
    """宽松金额解析：None/空串/非数 → 0，支持千分位与 dict 单元格。"""
    if isinstance(value, dict):
        value = value.get("value", value.get("amount", value.get("manual_value")))
    if value is None or value == "":
        return Decimal("0")
    try:
        return Decimal(str(value).replace(",", "").strip() or "0")
    except Exception:
        return Decimal("0")


def _norm_headers(table_data: dict) -> list[str]:
    """归一表头为 list[str]（支持 headers/columns，元素可为 str 或 dict）。"""
    raw = table_data.get("headers") or table_data.get("columns") or []
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for x in raw:
        if isinstance(x, dict):
            out.append(str(x.get("label") or x.get("name") or x.get("title") or ""))
        else:
            out.append(str(x))
    return out


def _row_values(row: Any) -> list | None:
    """取行的位置值列表（支持 values/cells/amounts/data）。"""
    if not isinstance(row, dict):
        return None
    for k in ("values", "cells", "amounts", "data"):
        v = row.get(k)
        if isinstance(v, list):
            return v
    return None


def _is_aging_header(header: str) -> bool:
    hs = str(header).strip()
    if hs in _KNOWN_AGING_LABELS:
        return True
    return bool(_AGING_LABEL_RE.search(hs))


def _is_total_header(header: str) -> bool:
    hs = str(header).strip()
    if not hs or _is_aging_header(hs):
        return False
    return any(tok in hs for tok in _TOTAL_HEADER_TOKENS)


def _find_header_index(headers: list[str], tokens: tuple[str, ...]) -> int | None:
    for i, h in enumerate(headers):
        if _is_aging_header(h):
            continue
        if any(t in str(h) for t in tokens):
            return i
    return None


def _resolve_section_table(
    section: str, note_map: dict[str, Any]
) -> Any:
    """按 section / 归一化 section 匹配 note_map 中的 table_data。缺失返回 None。"""
    if section in note_map:
        return note_map[section]
    norm = normalize_section_code(section)
    if norm in note_map:
        return note_map[norm]
    for key, val in note_map.items():
        if key == section:
            return val
        try:
            if normalize_section_code(key) == norm:
                return val
        except Exception:
            continue
    return None


def _is_note_empty(table_data: Any) -> bool:
    """判定附注章节是否为空（缺披露）。保守：不确定时判为非空（宁漏报不误报）。"""
    if table_data is None:
        return True
    if not isinstance(table_data, dict):
        return not bool(table_data)
    if table_data.get("is_empty") is True:
        return True
    if str(table_data.get("text_content") or "").strip():
        return False
    rows = table_data.get("rows")
    if isinstance(rows, list):
        for r in rows:
            if isinstance(r, dict):
                if str(r.get("label") or r.get("name") or "").strip():
                    return False
                if _row_values(r):
                    return False
                if r.get("amount") not in (None, ""):
                    return False
            elif r:
                return False
    tables = table_data.get("_tables")
    if isinstance(tables, list):
        for t in tables:
            if isinstance(t, dict) and not _is_note_empty(t):
                return False
    if _to_decimal(table_data.get("total")) != 0:
        return False
    values = table_data.get("values")
    if isinstance(values, list) and any(_to_decimal(c) != 0 for c in values):
        return False
    return True


# ---------------------------------------------------------------------------
# 章节合计 + 跨表引用解析（cross / cross_account 复用；只读）
# ---------------------------------------------------------------------------

# REPORT('row_code','period') / NOTE('section','*','period') / TB('account','column')
# 复用 execute_note_formulas 的 token 惯例（note_formula_generator）。
_REPORT_TOKEN_RE = re.compile(r"REPORT\('([^']+)'(?:\s*,\s*'[^']*')*\)")
_NOTE_TOKEN_RE = re.compile(r"NOTE\('([^']+)'(?:\s*,\s*'[^']*')*\)")
_TB_TOKEN_RE = re.compile(r"TB\('([^']+)'(?:\s*,\s*'[^']*')*\)")
# 4 位及以上数字科目码（从 metadata/expression 兜底提取）
_ACCOUNT_CODE_RE = re.compile(r"\b(\d{4,})\b")


def _as_list(value: Any) -> list:
    """把标量/None/列表统一成列表（None/空 → []）。"""
    if value is None or value == "":
        return []
    if isinstance(value, (list, tuple)):
        return [v for v in value if v not in (None, "")]
    return [value]


def _parse_tb_account_codes(expression: Any) -> list[str]:
    """从表达式提取 TB() token 科目码 + 裸 4+ 位数字科目码（去重保序）。"""
    if not expression or not isinstance(expression, str):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for code in _TB_TOKEN_RE.findall(expression):
        c = str(code).strip()
        if c and c not in seen:
            seen.add(c)
            out.append(c)
    for code in _ACCOUNT_CODE_RE.findall(expression):
        c = str(code).strip()
        if c and c not in seen:
            seen.add(c)
            out.append(c)
    return out


def _note_section_total(table_data: Any) -> Decimal | None:
    """统一取章节合计：``total`` 字段 → ``is_total`` 行 amount/总额列 → 明细行总额列求和。

    取不到任何合计表征 → None（供 executor Skip_On_Missing）。只读、无副作用。
    """
    if not isinstance(table_data, dict):
        return None

    # 1. total 字段（存在即用，含 0）
    if table_data.get("total") not in (None, ""):
        return _to_decimal(table_data.get("total"))

    rows = table_data.get("rows") if isinstance(table_data.get("rows"), list) else []
    headers = _norm_headers(table_data)
    total_idx = next((i for i, h in enumerate(headers) if _is_total_header(h)), None)

    # 2. is_total 行：amount 字段优先，否则总额列
    for r in rows:
        if isinstance(r, dict) and r.get("is_total"):
            if r.get("amount") not in (None, ""):
                return _to_decimal(r.get("amount"))
            vals = _row_values(r)
            if vals and total_idx is not None and total_idx < len(vals):
                return _to_decimal(vals[total_idx])

    # 3. 明细行总额列求和
    if total_idx is not None:
        acc = Decimal("0")
        found = False
        for r in rows:
            if not isinstance(r, dict) or r.get("is_total"):
                continue
            vals = _row_values(r)
            if vals and total_idx < len(vals):
                acc += _to_decimal(vals[total_idx])
                found = True
        if found:
            return acc

    return None


def _execute_balance(rule: ValidationRule, ctx: ValidationContext) -> ValidationResult:
    """余额校验：报表行次金额 = 附注合计行金额"""
    result = ValidationResult(
        section_code=rule.section_code,
        rule_type=rule.rule_type.value,
        rule_expression=rule.expression,
    )
    expected = ctx.report_data.get(rule.section_code, Decimal("0"))
    note_section_data = ctx.note_data.get(rule.section_code, {})
    actual = Decimal(str(note_section_data.get("total", 0)))

    result.expected_value = expected
    result.actual_value = actual
    diff = abs(expected - actual)
    result.diff_amount = diff
    tolerance = _resolve_tolerance(rule.tolerance, expected, actual)
    result.passed = diff <= tolerance
    result.details = {"check": "report_amount == note_total"}
    return result


def _execute_wide_table(rule: ValidationRule, ctx: ValidationContext) -> ValidationResult:
    """宽表校验：期初余额 + 本期增加 - 本期减少 = 期末余额"""
    result = ValidationResult(
        section_code=rule.section_code,
        rule_type=rule.rule_type.value,
        rule_expression=rule.expression,
    )
    note_section_data = ctx.note_data.get(rule.section_code, {})
    rows = note_section_data.get("rows", [])

    errors = []
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        opening = Decimal(str(row.get("opening", 0) or 0))
        increase = Decimal(str(row.get("increase", 0) or 0))
        decrease = Decimal(str(row.get("decrease", 0) or 0))
        closing = Decimal(str(row.get("closing", 0) or 0))

        expected_closing = opening + increase - decrease
        diff = abs(expected_closing - closing)
        tolerance = _resolve_tolerance(rule.tolerance, opening, increase, decrease, closing)
        if diff > tolerance:
            errors.append({
                "row_index": i,
                "expected": float(expected_closing),
                "actual": float(closing),
                "diff": float(diff),
            })

    result.passed = len(errors) == 0
    result.details = {"unbalanced_rows": errors}
    if errors:
        result.diff_amount = Decimal(str(errors[0]["diff"]))
    return result


def _execute_vertical(rule: ValidationRule, ctx: ValidationContext) -> ValidationResult:
    """纵向校验：各明细行之和 = 合计行"""
    result = ValidationResult(
        section_code=rule.section_code,
        rule_type=rule.rule_type.value,
        rule_expression=rule.expression,
    )
    note_section_data = ctx.note_data.get(rule.section_code, {})
    rows = note_section_data.get("rows", [])

    total_value = Decimal("0")
    detail_sum = Decimal("0")
    found_total = False

    for row in rows:
        if not isinstance(row, dict):
            continue
        if row.get("is_total"):
            total_value = Decimal(str(row.get("amount", 0) or 0))
            found_total = True
        else:
            detail_sum += Decimal(str(row.get("amount", 0) or 0))

    if not found_total:
        result.passed = True
        result.details = {"note": "no total row found, skipped"}
        return result

    diff = abs(detail_sum - total_value)
    result.expected_value = total_value
    result.actual_value = detail_sum
    result.diff_amount = diff
    tolerance = _resolve_tolerance(rule.tolerance, total_value, detail_sum)
    result.passed = diff <= tolerance
    result.details = {"check": "sum(detail_rows) == total_row"}
    return result


def _execute_cross(rule: ValidationRule, ctx: ValidationContext) -> ValidationResult:
    """交叉勾稽（Req4）：附注章节合计 = 报表对应行次金额，或 = 关联附注章节合计。

    比对目标解析（只读，不臆造）：
    - 报表行：``rule.metadata['report_row']`` 或 expression 含 ``REPORT('row_code',...)``
      → 比对 ``ctx.report_data[row_code]``（附注 ↔ 报表）。
    - 关联章节：``rule.metadata['cross_section']`` 或 expression 含 ``NOTE('section',...)``
      → 比对另一 note 章节合计（附注 ↔ 附注）。
    审计严谨（Req4.3/Req8.2）：本章节无合计 / 章节为空 / 引用目标数据缺失 / 无引用信息
    → Skip_On_Missing（passed=True + details.skipped）。差异超容差 → finding。
    """
    result = ValidationResult(
        section_code=rule.section_code,
        rule_type=rule.rule_type.value,
        rule_expression=rule.expression,
    )

    section = (rule.section_code or "").strip()
    note_map = ctx.note_data if isinstance(ctx.note_data, dict) else {}
    td = _resolve_section_table(section, note_map)

    # 本章节合计缺失 / 章节为空 → skip（不误报）
    cur_total = _note_section_total(td)
    if cur_total is None or _is_note_empty(td):
        result.passed = True
        result.details = {
            "check": "cross",
            "skipped": True,
            "reason": "current section total unavailable or section empty",
        }
        return result

    meta = rule.metadata or {}
    expr = rule.expression or ""

    # ── 确定比对目标：优先报表行，其次关联章节 ──
    report_row = str(meta.get("report_row") or "").strip()
    if not report_row:
        m = _REPORT_TOKEN_RE.search(expr)
        if m:
            report_row = m.group(1).strip()

    cross_section = str(meta.get("cross_section") or "").strip()
    if not cross_section:
        m = _NOTE_TOKEN_RE.search(expr)
        if m:
            cross_section = m.group(1).strip()

    expected: Decimal | None = None
    target_kind = ""
    target_ref = ""
    report_data = ctx.report_data if isinstance(ctx.report_data, dict) else {}

    if report_row:
        if report_row not in report_data:
            result.passed = True
            result.details = {
                "check": "cross",
                "skipped": True,
                "reason": f"report row {report_row!r} missing in report_data",
            }
            return result
        expected = _to_decimal(report_data[report_row])
        target_kind = "report"
        target_ref = report_row
    elif cross_section:
        cross_td = _resolve_section_table(cross_section, note_map)
        cross_total = _note_section_total(cross_td)
        if cross_total is None:
            result.passed = True
            result.details = {
                "check": "cross",
                "skipped": True,
                "reason": f"cross note section {cross_section!r} total unavailable",
            }
            return result
        expected = cross_total
        target_kind = "note"
        target_ref = cross_section
    else:
        # 无可解析引用信息 → 不臆造勾稽关系
        result.passed = True
        result.details = {
            "check": "cross",
            "skipped": True,
            "reason": "no report_row / cross_section reference in rule",
        }
        return result

    diff = abs(expected - cur_total)
    tolerance = _resolve_tolerance(rule.tolerance, expected, cur_total)
    result.expected_value = expected
    result.actual_value = cur_total
    result.diff_amount = diff
    result.passed = diff <= tolerance
    result.details = {
        "check": "cross",
        "target_kind": target_kind,
        "target_ref": target_ref,
        "section_total": float(cur_total),
    }
    return result


def _collect_tb_sum(accounts: list, tb_data: dict) -> Decimal | None:
    """汇总 tb_data 中给定科目余额；任一科目缺失 / 无科目 → None（Skip_On_Missing）。"""
    if not accounts:
        return None
    acc = Decimal("0")
    for a in accounts:
        code = str(a).strip()
        if code not in tb_data:
            return None
        acc += _to_decimal(tb_data[code])
    return acc


def _execute_cross_account(rule: ValidationRule, ctx: ValidationContext) -> ValidationResult:
    """跨科目勾稽（Req5）：不同科目附注章节 / 试算表科目间的金额勾稽。

    引用解析（只读，不臆造）：
    - 章节合计经 ``_note_section_total``；科目余额经 ``ctx.tb_data[account]``。
    - metadata: ``left_section`` / ``left_accounts`` 定左侧；``right_section(s)`` /
      ``right_accounts`` 定右侧；``accounts`` 简写 = 本章节合计 vs Σ科目余额；
      ``relation`` ∈ {eq, sum_eq}（sum_eq 时右侧多章节/科目求和）。
    - expression 兜底：NOTE()/TB()/裸科目码。
    审计严谨（Req5.2/Req8.2）：任一操作数缺失 / 无引用信息 → Skip_On_Missing。
    差异超容差 → finding。
    """
    result = ValidationResult(
        section_code=rule.section_code,
        rule_type=rule.rule_type.value,
        rule_expression=rule.expression,
    )

    meta = rule.metadata or {}
    expr = rule.expression or ""
    relation = str(meta.get("relation", "eq")).strip().lower()
    note_map = ctx.note_data if isinstance(ctx.note_data, dict) else {}
    tb_data = ctx.tb_data if isinstance(ctx.tb_data, dict) else {}

    def _skip(reason: str) -> ValidationResult:
        result.passed = True
        result.details = {"check": "cross_account", "skipped": True, "reason": reason}
        return result

    left_val: Decimal | None = None
    left_ref = ""
    right_val: Decimal | None = None
    right_ref = ""

    # ── 左侧 ──
    if meta.get("left_section"):
        left_val = _note_section_total(
            _resolve_section_table(str(meta["left_section"]), note_map)
        )
        left_ref = f"note:{meta['left_section']}"
    elif meta.get("left_accounts"):
        left_accounts = _as_list(meta.get("left_accounts"))
        left_val = _collect_tb_sum(left_accounts, tb_data)
        left_ref = f"tb:{'+'.join(str(a) for a in left_accounts)}"

    # ── 右侧（支持多章节/多科目求和：sum_eq）──
    right_sections = _as_list(meta.get("right_sections") or meta.get("right_section"))
    right_accounts = _as_list(meta.get("right_accounts"))
    if right_sections or right_accounts:
        parts: list[Decimal] = []
        ok = True
        for sec in right_sections:
            tot = _note_section_total(_resolve_section_table(str(sec), note_map))
            if tot is None:
                ok = False
                break
            parts.append(tot)
        if ok and right_accounts:
            tb_sum = _collect_tb_sum(right_accounts, tb_data)
            if tb_sum is None:
                ok = False
            else:
                parts.append(tb_sum)
        if ok and parts:
            right_val = sum(parts, Decimal("0"))
            right_ref = f"sections={right_sections},accounts={right_accounts}"

    # ── 简写 accounts：本章节合计 vs Σ科目余额 ──
    if left_val is None and right_val is None and meta.get("accounts"):
        left_val = _note_section_total(
            _resolve_section_table((rule.section_code or "").strip(), note_map)
        )
        left_ref = f"note:{rule.section_code}"
        accounts = _as_list(meta.get("accounts"))
        right_val = _collect_tb_sum(accounts, tb_data)
        right_ref = f"tb:{'+'.join(str(a) for a in accounts)}"

    # ── expression 兜底：本章节 vs NOTE()/TB()/裸科目码 ──
    if left_val is None and right_val is None:
        cur = _note_section_total(
            _resolve_section_table((rule.section_code or "").strip(), note_map)
        )
        note_secs = _NOTE_TOKEN_RE.findall(expr)
        codes = _parse_tb_account_codes(expr)
        if cur is not None and note_secs:
            left_val = cur
            left_ref = f"note:{rule.section_code}"
            right_val = _note_section_total(
                _resolve_section_table(str(note_secs[0]), note_map)
            )
            right_ref = f"note:{note_secs[0]}"
        elif cur is not None and codes:
            left_val = cur
            left_ref = f"note:{rule.section_code}"
            right_val = _collect_tb_sum(codes, tb_data)
            right_ref = f"tb:{'+'.join(codes)}"

    if left_val is None or right_val is None:
        return _skip("insufficient cross-account reference (missing operand)")

    diff = abs(left_val - right_val)
    tolerance = _resolve_tolerance(rule.tolerance, left_val, right_val)
    result.expected_value = left_val
    result.actual_value = right_val
    result.diff_amount = diff
    result.passed = diff <= tolerance
    result.details = {
        "check": "cross_account",
        "relation": relation,
        "left_ref": left_ref,
        "right_ref": right_ref,
    }
    return result


def _execute_sub_item(rule: ValidationRule, ctx: ValidationContext) -> ValidationResult:
    """其中项校验：sum(明细行) = 合计行"""
    result = ValidationResult(
        section_code=rule.section_code,
        rule_type=rule.rule_type.value,
        rule_expression=rule.expression,
    )
    note_section_data = ctx.note_data.get(rule.section_code, {})
    rows = note_section_data.get("rows", [])

    total_value = Decimal("0")
    detail_sum = Decimal("0")
    found_total = False

    for row in rows:
        if not isinstance(row, dict):
            continue
        if row.get("is_total"):
            total_value = Decimal(str(row.get("amount", 0) or 0))
            found_total = True
        else:
            detail_sum += Decimal(str(row.get("amount", 0) or 0))

    if not found_total:
        result.passed = True
        result.details = {"note": "no total row found, skipped"}
        return result

    diff = abs(detail_sum - total_value)
    result.expected_value = total_value
    result.actual_value = detail_sum
    result.diff_amount = diff
    tolerance = _resolve_tolerance(rule.tolerance, total_value, detail_sum)
    result.passed = diff <= tolerance
    result.details = {"check": "sum(sub_items) == total"}
    return result


# ---------------------------------------------------------------------------
# 二级明细结构识别 helper（secondary_detail 专用；只读、无副作用）
# ---------------------------------------------------------------------------

def _row_level(row: Any) -> int | None:
    """取行的层级（level/indent/depth，数值或数字串）。取不到 → None。"""
    if not isinstance(row, dict):
        return None
    for k in ("level", "indent", "depth"):
        v = row.get(k)
        if isinstance(v, bool):
            continue
        if isinstance(v, (int, float)):
            return int(v)
        if isinstance(v, str):
            s = v.strip()
            if s.lstrip("-").isdigit():
                return int(s)
    return None


def _row_idents(row: Any) -> list[str]:
    """取行可被其它行 ``parent`` 引用的标识候选（id/row_id/key/code/label/name）。"""
    if not isinstance(row, dict):
        return []
    out: list[str] = []
    for k in ("id", "row_id", "key", "code", "label", "name"):
        v = row.get(k)
        if v not in (None, ""):
            out.append(str(v).strip())
    return out


def _row_parent_ref(row: Any) -> str | None:
    """取行声明的父引用（parent/parent_id/parent_label/parent_key）。"""
    if not isinstance(row, dict):
        return None
    for k in ("parent", "parent_id", "parent_label", "parent_key", "parent_code"):
        v = row.get(k)
        if v not in (None, ""):
            return str(v).strip()
    return None


def _row_amount(row: Any, total_idx: int | None) -> Decimal:
    """取行金额：``amount`` 优先 → 总额列 → ``total`` 字段 → 0。"""
    if not isinstance(row, dict):
        return Decimal("0")
    if row.get("amount") not in (None, ""):
        return _to_decimal(row.get("amount"))
    vals = _row_values(row)
    if vals and total_idx is not None and total_idx < len(vals):
        return _to_decimal(vals[total_idx])
    if row.get("total") not in (None, ""):
        return _to_decimal(row.get("total"))
    return Decimal("0")


def _detect_secondary_groups(rows: list) -> list[tuple[Any, list]]:
    """识别二级明细结构：返回 [(一级父行, [二级子行, ...]), ...]。

    仅识别可靠的「二级层次」信号（与 vertical/sub_item 的单层求和区分）：
    - Strategy A：显式 ``parent`` 引用（子行 parent 命中另一行的 id/label 等标识）。
    - Strategy B：``level``/``indent`` 层级（父层 L 之后、层级为 L+1 的直属子行，
      遇层级 ≤ L 或无层级即止）。
    找不到任何父子分组 → 返回 []（executor 据此 Skip_On_Missing，不误报）。
    """
    groups: list[tuple[Any, list]] = []

    # ── Strategy A：显式 parent 引用 ──
    ident_to_idx: dict[str, int] = {}
    for i, r in enumerate(rows):
        for ident in _row_idents(r):
            ident_to_idx.setdefault(ident, i)
    children_by_parent: dict[int, list] = {}
    for i, r in enumerate(rows):
        ref = _row_parent_ref(r)
        if ref is None:
            continue
        pidx = ident_to_idx.get(ref)
        if pidx is None or pidx == i:
            continue
        children_by_parent.setdefault(pidx, []).append(r)
    if children_by_parent:
        for pidx in sorted(children_by_parent):
            children = children_by_parent[pidx]
            if children:
                groups.append((rows[pidx], children))
        return groups

    # ── Strategy B：level / indent 层级 ──
    levels = [_row_level(r) for r in rows]
    present = [lv for lv in levels if lv is not None]
    if len(set(present)) >= 2:
        n = len(rows)
        for i, r in enumerate(rows):
            li = levels[i]
            if li is None:
                continue
            children: list = []
            for j in range(i + 1, n):
                lj = levels[j]
                if lj is None or lj <= li:
                    break
                if lj == li + 1:
                    children.append(rows[j])
            if children:
                groups.append((r, children))
        return groups

    return []


def _execute_secondary_detail(rule: ValidationRule, ctx: ValidationContext) -> ValidationResult:
    """二级明细汇总校验（Req6 / 属性 P8）。

    识别章节内「一级项目下挂二级明细」的父子结构（显式 ``parent`` 引用 或
    ``level``/``indent`` 层级），校验 Σ二级明细行 = 对应一级项目金额（容差内）。

    审计严谨（Req6.2 / Req8.2）：
    - 章节 table_data 缺失 / 为空 / 无 rows → Skip_On_Missing。
    - 找不到父子分组（仅单层明细，无二级层次）→ Skip_On_Missing（与 vertical/sub_item
      的「明细和=合计」语义区分，不臆造层次）。
    - 不平超容差 → finding（details 含父项、子项和、diff）。
    只读、绝不改数据。
    """
    result = ValidationResult(
        section_code=rule.section_code,
        rule_type=rule.rule_type.value,
        rule_expression=rule.expression,
    )

    section = (rule.section_code or "").strip()
    note_map = ctx.note_data if isinstance(ctx.note_data, dict) else {}
    td = _resolve_section_table(section, note_map)

    if not isinstance(td, dict) or _is_note_empty(td):
        result.passed = True
        result.details = {
            "check": "secondary_detail",
            "skipped": True,
            "reason": "section table_data missing or empty",
        }
        return result

    rows = td.get("rows") if isinstance(td.get("rows"), list) else []
    if not rows:
        result.passed = True
        result.details = {
            "check": "secondary_detail",
            "skipped": True,
            "reason": "no rows in section",
        }
        return result

    groups = _detect_secondary_groups(rows)
    if not groups:
        result.passed = True
        result.details = {
            "check": "secondary_detail",
            "skipped": True,
            "reason": "no secondary (parent/child) detail structure detected",
        }
        return result

    headers = _norm_headers(td)
    total_idx = next((i for i, h in enumerate(headers) if _is_total_header(h)), None)

    imbalances: list[dict[str, Any]] = []
    max_diff = Decimal("0")
    for parent, children in groups:
        parent_amt = _row_amount(parent, total_idx)
        child_sum = sum((_row_amount(c, total_idx) for c in children), Decimal("0"))
        if parent_amt == 0 and child_sum == 0:
            continue  # 空组跳过
        diff = abs(parent_amt - child_sum)
        tol = _resolve_tolerance(rule.tolerance, parent_amt, child_sum)
        if diff > tol:
            parent_label = ""
            if isinstance(parent, dict):
                parent_label = str(parent.get("label") or parent.get("name") or "").strip()
            imbalances.append(
                {
                    "parent": parent_label,
                    "parent_amount": float(parent_amt),
                    "children_sum": float(child_sum),
                    "child_count": len(children),
                    "diff": float(diff),
                }
            )
            if diff > max_diff:
                max_diff = diff

    result.passed = len(imbalances) == 0
    result.details = {
        "check": "secondary_detail",
        "group_count": len(groups),
        "imbalances": imbalances,
    }
    if max_diff > 0:
        result.diff_amount = max_diff
    return result


def _execute_completeness(rule: ValidationRule, ctx: ValidationContext) -> ValidationResult:
    """完整性校验：有 TB 审定余额的应披露科目必须有对应且非空的附注章节。

    审计严谨（Req2/Req8）：
    - ctx.tb_data 空（试算表未装配/缺失）→ Skip_On_Missing（不误报）。
    - 科目↔note_section 映射不可用/为空 → Skip_On_Missing（不臆造映射）。
    - 仅对「映射内的应披露章节」检查：章节缺失或表格/正文皆空 → finding。
      未在映射内的章节不做判断（不臆造）。
    - 两种模式：
        · 主模式（rule.section_code 命中映射）→ 只校验该章节。
        · 全局模式（section_code 为空/*/all 或 expression 含 "全局"，或 metadata.scope=="global"）
          → 遍历映射内全部应披露章节。
    映射真源：DEFAULT_WP_MAPPING（note_section → 底稿前缀），经 normalize_section_code
    匹配 note_data（国企 "五、N" ↔ canonical "八、N"）。只读、绝不改数据。
    """
    result = ValidationResult(
        section_code=rule.section_code,
        rule_type=rule.rule_type.value,
        rule_expression=rule.expression,
    )

    # Skip_On_Missing：无 TB 审定余额数据（Req2.3）
    tb_data = ctx.tb_data or {}
    if not any(_to_decimal(v) != 0 for v in tb_data.values()):
        result.passed = True
        result.details = {
            "check": "note_completeness",
            "skipped": True,
            "reason": "no non-zero tb audited balance (tb_data missing/empty)",
        }
        return result

    # Skip_On_Missing：映射不可用（Req2.4，不臆造）
    mapping = DEFAULT_WP_MAPPING
    if not mapping:
        result.passed = True
        result.details = {
            "check": "note_completeness",
            "skipped": True,
            "reason": "account→note_section mapping unavailable",
        }
        return result

    section_code = (rule.section_code or "").strip()
    scope_meta = str((rule.metadata or {}).get("scope", "")).lower()
    is_global = (
        section_code in ("", "*", "全部", "all")
        or "全局" in (rule.expression or "")
        or scope_meta == "global"
    )

    if is_global:
        scope_sections = list(mapping.keys())
    elif section_code in mapping:
        scope_sections = [section_code]
    else:
        # 该章节不在应披露映射内 → 不臆造，Skip_On_Missing
        result.passed = True
        result.details = {
            "check": "note_completeness",
            "skipped": True,
            "reason": f"section {section_code!r} not in disclosure mapping",
        }
        return result

    note_map = ctx.note_data if isinstance(ctx.note_data, dict) else {}
    missing_sections: list[dict[str, Any]] = []
    for sec in scope_sections:
        wp_code = mapping.get(sec, "")
        td = _resolve_section_table(sec, note_map)
        if td is None:
            missing_sections.append(
                {"expected_section": sec, "wp_code": wp_code, "reason": "missing"}
            )
        elif _is_note_empty(td):
            missing_sections.append(
                {"expected_section": sec, "wp_code": wp_code, "reason": "empty"}
            )

    # ── Wave4 (Task 5.4)：account 粒度完整性（有 TB 余额但对应 note_section 缺披露 → finding，Req7.2）──
    # gated：仅当 ctx.account_section_map 非空 且 全局模式时启用；否则 undisclosed_accounts 恒 []，
    # 行为与既有 section-scope 逐字节一致（Req7.3 无映射回退 section-scope，不误报）。
    # 无映射科目一律不臆造（跳过）；映射目标经 _resolve_section_table 做 legacy 归一后匹配。
    undisclosed_accounts: list[dict[str, Any]] = []
    acct_map = getattr(ctx, "account_section_map", None) or {}
    if acct_map and is_global:
        for code, bal in tb_data.items():
            if _to_decimal(bal) == 0:
                continue
            sec = acct_map.get(str(code).strip())
            if not sec:
                continue  # 无映射的科目不臆造（保守，宁漏报不误报）
            td = _resolve_section_table(sec, note_map)
            if td is None or _is_note_empty(td):
                undisclosed_accounts.append({
                    "account_code": str(code),
                    "expected_section": sec,
                    "reason": "missing" if td is None else "empty",
                })

    result.passed = len(missing_sections) == 0 and len(undisclosed_accounts) == 0
    result.details = {
        "check": "note_completeness",
        "mode": "global" if is_global else "section",
        "checked_sections": scope_sections,
        "missing_sections": missing_sections,
        "undisclosed_accounts": undisclosed_accounts,
        "account_granularity": bool(acct_map and is_global),
        "tb_nonzero_accounts": sum(1 for v in tb_data.values() if _to_decimal(v) != 0),
    }
    return result


# ---------------------------------------------------------------------------
# LLM 文本合理性审核 helper（llm_review 专用；fail-open、只读）
# ---------------------------------------------------------------------------

def _is_llm_placeholder(text: Any) -> bool:
    """判定是否为 chat_completion 的降级/占位串（``[LLM.../⚠️...``）。"""
    s = str(text).strip()
    if not s:
        return True
    return s.startswith("[LLM") or s.lower().startswith("[llm") or s.startswith("⚠️")


def _invoke_llm_review(text: str) -> str | None:
    """模块级可 mock 的**同步** LLM 审核入口。

    ``chat_completion`` 仅有 async 版本，而 executor 是同步函数
    （``EXECUTORS[type](rule, ctx)`` 同步调用）。为避免在同步函数里
    ``asyncio.run`` 阻塞事件循环，此处默认返回 ``None``（当前无同步 LLM 入口
    → executor Skip_On_Missing）。

    审核语义：仅当发现问题（占位符残留 ``{{}}``/``XX``/``【】``、数字与表格
    明显矛盾、表述空泛）时返回问题描述串；无问题 / 不可用 → 返回 ``None``。

    fail-open：内部任何异常吞掉返回 ``None``，绝不抛。
    测试可 ``monkeypatch`` 本函数注入同步可调用以验证 warning 路径。
    """
    try:
        return None
    except Exception:  # pragma: no cover - defensive fail-open
        return None


def _execute_llm_review(rule: ValidationRule, ctx: ValidationContext) -> ValidationResult:
    """LLM 文本合理性审核（Req7 / 属性 P9 fail-open、P10 只读）。

    取章节 ``text_content``：
    - 无正文 / 空 → Skip_On_Missing（passed=True）。
    - 有正文 → 经可 mock 的 ``_invoke_llm_review`` 审合理性（占位符残留 / 数字与
      表格矛盾 / 表述空泛）→ 有问题时产 **warning 级** finding
      （passed=False + details 标 ``ai_hint=True`` / ``severity=warning``，
      明确为 AI 提示、非权威、不改任何附注数据）。
    - fail-open（Req7.2 / P9）：``_invoke_llm_review`` 抛异常 / 返回 None /
      返回占位串（``[LLM...``/``⚠️...``）→ passed=True + ``skipped``，绝不误报、绝不抛。
    只读（P10）：executor 不写 DB / ctx。
    """
    result = ValidationResult(
        section_code=rule.section_code,
        rule_type=rule.rule_type.value,
        rule_expression=rule.expression,
    )

    section = (rule.section_code or "").strip()
    note_map = ctx.note_data if isinstance(ctx.note_data, dict) else {}
    td = _resolve_section_table(section, note_map)

    text_content = ""
    if isinstance(td, dict):
        text_content = str(td.get("text_content") or "").strip()

    if not text_content:
        result.passed = True
        result.details = {
            "check": "llm_review",
            "skipped": True,
            "reason": "no text_content in section",
        }
        return result

    # fail-open：整个 LLM 调用 try/except 包裹（绝不抛、绝不误报）
    try:
        review = _invoke_llm_review(text_content)
    except Exception as e:  # pragma: no cover - defensive fail-open
        result.passed = True
        result.details = {
            "check": "llm_review",
            "skipped": True,
            "reason": f"LLM review raised, fail-open skip: {e}",
        }
        return result

    if review is None or _is_llm_placeholder(review):
        result.passed = True
        result.details = {
            "check": "llm_review",
            "skipped": True,
            "reason": "LLM 审核不可用/占位串/需异步入口，当前 skip（fail-open）",
        }
        return result

    # 有效审核意见 → warning 级 AI 提示 finding（非阻断，不改附注数据）
    result.passed = False
    result.details = {
        "check": "llm_review",
        "ai_hint": True,
        "severity": "warning",
        "advisory": True,
        "note": "AI 合理性提示（非权威，仅供审计人员参考，未改动任何附注数据）",
        "llm_review": str(review).strip(),
    }
    return result


def _summarize_table_context(td: Any) -> str:
    """构造喂给 LLM 的表格上下文摘要串（值全部转字符串，供"数字↔表格矛盾"判断）。

    只读；取合计 + 前若干行 label:amount。缺失/异常 → 空串。
    """
    if not isinstance(td, dict):
        return ""
    parts: list[str] = []
    try:
        total = _note_section_total(td)
        if total is not None:
            parts.append(f"合计：{total}")
        rows = td.get("rows") if isinstance(td.get("rows"), list) else []
        for r in rows[:20]:
            if not isinstance(r, dict):
                continue
            lbl = str(r.get("label") or r.get("name") or "").strip()
            if not lbl:
                continue
            amt = r.get("amount")
            parts.append(f"{lbl}：{'' if amt in (None, '') else amt}")
    except Exception:  # pragma: no cover - defensive
        return ""
    return "\n".join(parts)


async def _execute_llm_review_async(
    rule: ValidationRule, ctx: ValidationContext
) -> ValidationResult:
    """LLM 文本合理性审核（Req7）— **真实 async 调用** ``chat_completion``。

    由 ``NoteValidationEngine.execute_all`` 的 async 特例路径调用（执行器整体为同步纯
    函数，唯 LLM_REVIEW 需 await，故引擎按类型分发到本 async 版本；其余 10 个同步执行器
    行为不变）。

    - 取章节 ``text_content``；无正文/空 → Skip_On_Missing。
    - 构 prompt（system：附注文本合理性初审，只输出问题清单或"无异常"；user：正文 +
      表格数据上下文，**值全部转字符串**）调 ``chat_completion``。
    - fail-open（Req7.2 / P9）：返回占位串（``[.../⚠️...``）/空/异常 → passed=True +
      ``skipped``（不误报、不抛）。
    - 正常返回且指出问题 → **warning 级** finding（``ai_hint=True``/``severity=warning``，
      标为 AI 提示、非权威）；返回"无异常"类 → pass。
    只读（P10）：不改任何附注/DB/ctx 数据。
    """
    result = ValidationResult(
        section_code=rule.section_code,
        rule_type=rule.rule_type.value,
        rule_expression=rule.expression,
    )

    section = (rule.section_code or "").strip()
    note_map = ctx.note_data if isinstance(ctx.note_data, dict) else {}
    td = _resolve_section_table(section, note_map)

    text_content = ""
    if isinstance(td, dict):
        text_content = str(td.get("text_content") or "").strip()

    if not text_content:
        result.passed = True
        result.details = {
            "check": "llm_review",
            "skipped": True,
            "reason": "no text_content in section",
            "ai_hint": True,
        }
        return result

    try:
        table_ctx = _summarize_table_context(td)
        system_prompt = (
            "你是审计附注文本合理性初审助手。仅输出发现的问题清单（每条一行）；"
            '若无异常只回复"无异常"。重点检查：占位符残留（如 XX、【】、{{}}）、'
            "数字与表格数据明显矛盾、表述空泛或明显未填写。不要编造任何数据。"
        )
        user_prompt = f"附注章节：{section}\n【正文】\n{text_content}"
        if table_ctx:
            user_prompt += f"\n\n【表格数据】\n{table_ctx}"
        reply = await chat_completion(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
            max_tokens=800,
        )
    except Exception as e:  # fail-open：绝不抛、绝不误报
        logger.warning("llm_review async fail-open: %s", e)
        result.passed = True
        result.details = {
            "check": "llm_review",
            "skipped": True,
            "reason": f"LLM review raised, fail-open skip: {e}",
            "ai_hint": True,
        }
        return result

    reply_text = str(reply).strip() if isinstance(reply, str) else ""
    # 占位串（[.../⚠️...）/空 → fail-open skip
    if _is_llm_placeholder(reply_text):
        result.passed = True
        result.details = {
            "check": "llm_review",
            "skipped": True,
            "reason": "LLM 不可用/超时/占位串，fail-open skip",
            "ai_hint": True,
        }
        return result

    # "无异常"类 → pass（AI 初审无问题）
    normalized = reply_text.replace(" ", "").replace("\n", "").replace("　", "")
    if (
        normalized.startswith("无异常")
        or normalized in ("无", "none", "n/a", "na", "正常")
    ):
        result.passed = True
        result.details = {
            "check": "llm_review",
            "ai_hint": True,
            "advisory": True,
            "llm_review": reply_text,
            "note": "AI 合理性初审：无异常（非权威，仅供参考）",
        }
        return result

    # 指出问题 → warning 级 AI 提示 finding（无 diff_amount → severity 由 validate_all 判为 warning）
    result.passed = False
    result.details = {
        "check": "llm_review",
        "ai_hint": True,
        "advisory": True,
        "severity": "warning",
        "llm_review": reply_text,
        "note": "AI 合理性提示（非权威，仅供审计人员参考，未改动任何附注数据）",
    }
    return result


def _execute_aging_progression(rule: ValidationRule, ctx: ValidationContext) -> ValidationResult:
    """账龄衔接校验（Req3）：

    1. 各账龄分桶金额之和 = 该行总额列（容差内），不平 → finding。
    2. 若有上年附注（ctx.prior_note_data）且结构可对齐：本年「期初」值 = 上年「期末」值，
       不一致 → finding；无上年/结构不齐 → 该子校验 skip（不误报）。
    审计严谨：无账龄表 / headers 不含账龄段 / 无总额列 → Skip_On_Missing。
    段识别复用 aging_config PRESET_SEGMENTS 的 label + 通用账龄正则（取不到用默认段）。
    只读、绝不改数据。
    """
    result = ValidationResult(
        section_code=rule.section_code,
        rule_type=rule.rule_type.value,
        rule_expression=rule.expression,
    )

    section = (rule.section_code or "").strip()
    note_map = ctx.note_data if isinstance(ctx.note_data, dict) else {}
    td = _resolve_section_table(section, note_map)
    if not isinstance(td, dict):
        result.passed = True
        result.details = {
            "check": "aging_progression",
            "skipped": True,
            "reason": "section table_data missing",
        }
        return result

    headers = _norm_headers(td)
    bucket_idx = [i for i, h in enumerate(headers) if _is_aging_header(h)]
    total_idx = next((i for i, h in enumerate(headers) if _is_total_header(h)), None)

    if not bucket_idx or total_idx is None:
        result.passed = True
        result.details = {
            "check": "aging_progression",
            "skipped": True,
            "reason": "no aging bucket columns or total column in headers",
        }
        return result

    rows = td.get("rows") if isinstance(td.get("rows"), list) else []
    unbalanced: list[dict[str, Any]] = []
    max_diff = Decimal("0")
    for ridx, row in enumerate(rows):
        vals = _row_values(row)
        if not vals or total_idx >= len(vals):
            continue
        bucket_sum = sum(
            (_to_decimal(vals[i]) for i in bucket_idx if i < len(vals)),
            Decimal("0"),
        )
        total = _to_decimal(vals[total_idx])
        if bucket_sum == 0 and total == 0:
            continue  # 空行跳过
        diff = abs(bucket_sum - total)
        tol = _resolve_tolerance(rule.tolerance, bucket_sum, total)
        if diff > tol:
            unbalanced.append(
                {
                    "row_index": ridx,
                    "label": (row.get("label") or row.get("name") or "")
                    if isinstance(row, dict)
                    else "",
                    "expected": float(total),
                    "actual": float(bucket_sum),
                    "diff": float(diff),
                }
            )
            if diff > max_diff:
                max_diff = diff

    # ── 期初=上年期末 衔接子校验（结构对齐时；否则 skip 不误报）──
    continuity_issues: list[dict[str, Any]] = []
    continuity_checked = False
    prior_map = ctx.prior_note_data if isinstance(ctx.prior_note_data, dict) else {}
    prior_td = _resolve_section_table(section, prior_map) if prior_map else None
    if isinstance(prior_td, dict):
        cur_open_idx = _find_header_index(headers, _OPEN_HEADER_TOKENS)
        prior_headers = _norm_headers(prior_td)
        prior_close_idx = _find_header_index(prior_headers, _CLOSE_HEADER_TOKENS)
        if cur_open_idx is not None and prior_close_idx is not None:
            continuity_checked = True
            prior_close_by_label: dict[str, Decimal] = {}
            for prow in prior_td.get("rows") or []:
                pvals = _row_values(prow)
                if not pvals or prior_close_idx >= len(pvals):
                    continue
                label = str(
                    (prow.get("label") or prow.get("name") or "")
                    if isinstance(prow, dict)
                    else ""
                ).strip()
                if label:
                    prior_close_by_label[label] = _to_decimal(pvals[prior_close_idx])
            for ridx, row in enumerate(rows):
                vals = _row_values(row)
                if not vals or cur_open_idx >= len(vals) or not isinstance(row, dict):
                    continue
                label = str(row.get("label") or row.get("name") or "").strip()
                if not label or label not in prior_close_by_label:
                    continue
                cur_open = _to_decimal(vals[cur_open_idx])
                prior_close = prior_close_by_label[label]
                diff = abs(cur_open - prior_close)
                tol = _resolve_tolerance(rule.tolerance, cur_open, prior_close)
                if diff > tol:
                    continuity_issues.append(
                        {
                            "label": label,
                            "current_opening": float(cur_open),
                            "prior_closing": float(prior_close),
                            "diff": float(diff),
                        }
                    )
                    if diff > max_diff:
                        max_diff = diff

    result.passed = len(unbalanced) == 0 and len(continuity_issues) == 0
    result.details = {
        "check": "aging_progression",
        "bucket_columns": [headers[i] for i in bucket_idx],
        "total_column": headers[total_idx],
        "unbalanced_rows": unbalanced,
        "continuity_checked": continuity_checked,
        "continuity_issues": continuity_issues,
    }
    if max_diff > 0:
        result.diff_amount = max_diff
    return result


def _execute_description(rule: ValidationRule, ctx: ValidationContext) -> ValidationResult:
    """描述类 preset：纯文本章节兜底"""
    return ValidationResult(
        section_code=rule.section_code,
        rule_type=rule.rule_type.value,
        rule_expression=rule.expression,
        passed=True,
        details={"check": "description_skipped"},
    )


# Executor dispatch table
EXECUTORS = {
    ValidationType.BALANCE: _execute_balance,
    ValidationType.WIDE_TABLE: _execute_wide_table,
    ValidationType.VERTICAL: _execute_vertical,
    ValidationType.CROSS: _execute_cross,
    ValidationType.CROSS_ACCOUNT: _execute_cross_account,
    ValidationType.SUB_ITEM: _execute_sub_item,
    ValidationType.SECONDARY_DETAIL: _execute_secondary_detail,
    ValidationType.COMPLETENESS: _execute_completeness,
    ValidationType.AGING_PROGRESSION: _execute_aging_progression,
    ValidationType.LLM_REVIEW: _execute_llm_review,
    ValidationType.DESCRIPTION: _execute_description,
}
