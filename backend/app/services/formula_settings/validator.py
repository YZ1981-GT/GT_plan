"""服务端统一公式定义校验（需求 12.1、12.2，ADR-FHIC-09）。

全部写入入口在写库前调 ``validate_formula_definition``，按域校验定义合法性。
域 → 校验器表：
- report / tb_detail / cross_check：L1 解析 + 函数名 ⊆ _REGISTRY + 常量零除数检查
- wp：``checked_wp_definition``（含 ``unsupported_formula_function_issues``）
- note：``check_note_definition``
- consol_note：``validate_note_formula``
- push：``validate_push_definition``

通用检查：长度 ≤4000、括号嵌套 ≤50。
常量零除数：遍历 L1 AST，对每个除法节点右操作数做常量折叠
（只折叠数字字面量与 +-*/ 运算，遇函数调用 / 行引用即视为非常量），
折叠结果为 0 ⇒ 422。``1/TB(...)`` 过（运行时取数不在编译期拒）。
"""
from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from app.services.formula_settings.definitions import is_disabled
from app.services.formula_settings.errors import FormulaSettingError

logger = logging.getLogger(__name__)

MAX_DEFINITION_LENGTH = 4000
MAX_NESTING_DEPTH = 50

# ── 通用结构检查 ──────────────────────────────────────────────────────────────


def _formula_text(domain: str, definition: Mapping[str, Any]) -> str:
    """从定义字典中提取公式文本（用于长度和嵌套检查）。"""
    if domain in ("wp", "push"):
        return str(definition.get("expression") or "")
    if domain == "cross_check":
        # cross_check 域有 left_ref 和 right_ref 两个公式字段，取最长的做通用检查
        left = str(definition.get("left_ref") or "")
        right = str(definition.get("right_ref") or "")
        return left if len(left) >= len(right) else right
    return str(definition.get("formula") or "")


def _check_length(text: str, label: str) -> list[str]:
    if len(text) > MAX_DEFINITION_LENGTH:
        return [f"{label}：公式长度 {len(text)} 超过上限 {MAX_DEFINITION_LENGTH}"]
    return []


def _check_nesting(text: str, label: str) -> list[str]:
    depth = 0
    max_depth = 0
    for ch in text:
        if ch == "(":
            depth += 1
            if depth > max_depth:
                max_depth = depth
        elif ch == ")":
            depth -= 1
    if max_depth > MAX_NESTING_DEPTH:
        return [f"{label}：括号嵌套深度 {max_depth} 超过上限 {MAX_NESTING_DEPTH}"]
    return []


# ── 常量零除数检查（L1 AST） ─────────────────────────────────────────────────


def _constant_fold(node: Any) -> Decimal | None:
    """对 AST 节点做常量折叠。

    只折叠数字字面量与 +-*/ 一元二元运算。
    遇函数调用、行引用等 → 返回 None（非常量）。
    """
    from app.services.formula_engine import ASTBinOp, ASTNumber, ASTUnary

    if isinstance(node, ASTNumber):
        return node.value

    if isinstance(node, ASTUnary) and node.op == "-":
        inner = _constant_fold(node.operand)
        if inner is not None:
            return -inner
        return None

    if isinstance(node, ASTBinOp) and node.op in ("+", "-", "*", "/"):
        left = _constant_fold(node.left)
        right = _constant_fold(node.right)
        if left is None or right is None:
            return None
        try:
            if node.op == "+":
                return left + right
            if node.op == "-":
                return left - right
            if node.op == "*":
                return left * right
            if node.op == "/":
                if right == 0:
                    return Decimal("0")  # 标记为 0，由调用方判断
                return left / right
        except (InvalidOperation, ZeroDivisionError):
            return Decimal("0")

    # 函数调用、行引用、字符串等 → 非常量
    return None


def _check_constant_zero_divisor(node: Any) -> list[str]:
    """遍历 AST 节点，检查是否存在常量零除数。"""
    from app.services.formula_engine import (
        ASTBinOp,
        ASTCompare,
        ASTFuncCall,
        ASTUnary,
    )

    problems: list[str] = []

    if isinstance(node, ASTBinOp):
        if node.op == "/":
            right_val = _constant_fold(node.right)
            if right_val is not None and right_val == 0:
                problems.append("除数恒为 0")
        problems.extend(_check_constant_zero_divisor(node.left))
        problems.extend(_check_constant_zero_divisor(node.right))

    elif isinstance(node, ASTUnary):
        problems.extend(_check_constant_zero_divisor(node.operand))

    elif isinstance(node, ASTFuncCall):
        for arg in node.args:
            problems.extend(_check_constant_zero_divisor(arg))

    elif isinstance(node, ASTCompare):
        problems.extend(_check_constant_zero_divisor(node.left))
        problems.extend(_check_constant_zero_divisor(node.right))

    return problems


# ── 报表 / tb_detail / cross_check 域校验 ────────────────────────────────────


def _validate_report_family(domain: str, definition: Mapping[str, Any], label: str,
                            slot_key: str) -> list[str]:
    """report / tb_detail / cross_check 域：L1 解析 + 函数名检查 + 常量零除数。"""
    from app.services.formula_engine import (
        FormulaParseError,
        _REGISTRY,
        parse_to_ast,
    )

    problems: list[str] = []
    known = _REGISTRY.known_function_names()

    if domain == "cross_check":
        # cross_check 域分别校验 left_ref 和 right_ref
        for field_name in ("left_ref", "right_ref"):
            text = str(definition.get(field_name) or "").strip()
            if not text:
                continue
            try:
                ast_node = parse_to_ast(text)
            except FormulaParseError as exc:
                problems.append(f"{label}（{field_name}）：公式无法解析（{exc}）")
                continue
            unknown = _collect_unknown_functions(ast_node, known)
            for name in sorted(unknown):
                problems.append(f"{label}（{field_name}）：未注册的函数 {name}")
            zero_problems = _check_constant_zero_divisor(ast_node)
            for p in zero_problems:
                problems.append(f"{label}（{field_name}）：{p}")
        return problems

    text = _formula_text(domain, definition)
    if not text.strip():
        return problems  # 空公式由各域自己的写入逻辑决定是否允许

    # L1 解析
    try:
        ast_node = parse_to_ast(text)
    except FormulaParseError as exc:
        problems.append(f"{label}：公式无法解析（{exc}）")
        return problems

    # 函数名 ⊆ _REGISTRY
    unknown = _collect_unknown_functions(ast_node, known)
    for name in sorted(unknown):
        problems.append(f"{label}：未注册的函数 {name}")

    # 常量零除数
    zero_problems = _check_constant_zero_divisor(ast_node)
    for p in zero_problems:
        problems.append(f"{label}：{p}")

    return problems


def _collect_unknown_functions(node: Any, known: set[str]) -> set[str]:
    """收集 AST 中未注册的函数名。"""
    from app.services.formula_engine import (
        ASTBinOp,
        ASTCompare,
        ASTFuncCall,
        ASTUnary,
    )

    unknown: set[str] = set()
    if isinstance(node, ASTFuncCall):
        if node.name not in known:
            unknown.add(node.name)
        for arg in node.args:
            unknown |= _collect_unknown_functions(arg, known)
    elif isinstance(node, ASTBinOp):
        unknown |= _collect_unknown_functions(node.left, known)
        unknown |= _collect_unknown_functions(node.right, known)
    elif isinstance(node, ASTUnary):
        unknown |= _collect_unknown_functions(node.operand, known)
    elif isinstance(node, ASTCompare):
        unknown |= _collect_unknown_functions(node.left, known)
        unknown |= _collect_unknown_functions(node.right, known)
    return unknown


# ── 域路由 ────────────────────────────────────────────────────────────────────


def validate_formula_definition(domain: str, definition: Mapping[str, Any] | None, *,
                                label: str = "", slot_key: str = "") -> None:
    """统一的公式定义校验入口（需求 12.1）。

    在各域写入方写库前调用，422 拒绝不合法的定义。
    ``disabled=true`` 的定义只做结构检查（长度、嵌套），不做语义校验。

    Args:
        domain: 公式域（report / tb_detail / cross_check / wp / note / consol_note / push）
        definition: 公式定义字典；None 表示删除，不校验
        label: 人类可读的公式位标签（用于错误消息）
        slot_key: 公式位键（推送域用来查规则）
    """
    if definition is None:
        return

    lbl = label or slot_key or domain

    # 停用的定义只做结构检查
    disabled = is_disabled(definition)
    text = _formula_text(domain, definition)

    problems: list[str] = []

    # 通用：长度 + 嵌套
    problems.extend(_check_length(text, lbl))
    problems.extend(_check_nesting(text, lbl))

    if problems:
        _raise(problems, slot_key)

    if disabled:
        return  # 停用不做语义校验

    # 按域路由
    if domain in ("report", "tb_detail", "cross_check"):
        problems.extend(_validate_report_family(domain, definition, lbl, slot_key))
    elif domain == "wp":
        _validate_wp(definition, lbl)
        return  # wp 校验器自己抛异常
    elif domain == "note":
        _validate_note(definition, lbl)
        return
    elif domain == "consol_note":
        _validate_consol_note(definition, lbl)
        return
    elif domain == "push":
        _validate_push(definition, lbl, slot_key)
        return

    if problems:
        _raise(problems, slot_key)


def _validate_wp(definition: Mapping[str, Any], label: str) -> None:
    """底稿域：转发到 checked_wp_definition。"""
    from app.services.formula_settings.domain_stores import checked_wp_definition
    checked_wp_definition(dict(definition), label)


def _validate_note(definition: Mapping[str, Any], label: str) -> None:
    """附注域：转发到 check_note_definition。"""
    from app.services.formula_settings.domain_stores import check_note_definition
    check_note_definition(dict(definition), label)


def _validate_consol_note(definition: Mapping[str, Any], label: str) -> None:
    """合并附注域：转发到 validate_note_formula。"""
    from app.services.consol_note_formula_service import NoteFormulaError, validate_note_formula
    try:
        validate_note_formula(str(definition.get("formula") or ""))
    except NoteFormulaError as exc:
        raise FormulaSettingError(
            f"{label}：{exc}",
            code="FORMULA_DEFINITION_INVALID",
            status_code=422,
            detail={"problems": [{"slot_key": "", "message": str(exc)}]},
        ) from exc


def _validate_push(definition: Mapping[str, Any], label: str, slot_key: str) -> None:
    """推送域：转发到 validate_push_definition。"""
    from app.services.formula_settings.push_settings import validate_push_definition
    validate_push_definition(slot_key, dict(definition), label)


def _raise(problems: list[str], slot_key: str = "") -> None:
    """将问题列表汇总为 422 错误。"""
    raise FormulaSettingError(
        "；".join(problems),
        code="FORMULA_DEFINITION_INVALID",
        status_code=422,
        detail={"problems": [{"slot_key": slot_key, "message": p} for p in problems]},
    )
