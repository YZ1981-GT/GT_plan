"""QC 规则执行器 — Python 类型 + JSONPath 类型 + audit_log 类型分派

Refinement Round 3 — 需求 1, 12：
- expression_type='python': 加载 dotted path 类，沙箱 timeout=10s
- expression_type='jsonpath': 只读 parsed_data，用 jsonpath-ng 库
- scope='audit_log': 查询 audit_log_entries 表，JSONPath 过滤 payload
- expression_type='sql' / 'regex': 预留，抛 NotImplementedError

执行器作为独立模块，由 QCEngine 委托调用。
"""

from __future__ import annotations

import asyncio
import importlib
import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log_models import AuditLogEntry
from app.models.qc_rule_models import QcRuleDefinition

logger = logging.getLogger(__name__)

# 默认 Python 类型规则执行超时（秒）
PYTHON_RULE_TIMEOUT_SECONDS = 10


class RuleExecutionError(Exception):
    """规则执行过程中的错误。"""

    def __init__(self, rule_code: str, message: str):
        self.rule_code = rule_code
        self.message = message
        super().__init__(f"[{rule_code}] {message}")


class RuleExecutionResult:
    """规则执行结果。"""

    def __init__(
        self,
        rule_code: str,
        passed: bool,
        findings: list[dict] | None = None,
        error: str | None = None,
    ):
        self.rule_code = rule_code
        self.passed = passed
        self.findings = findings or []
        self.error = error

    def to_dict(self) -> dict:
        return {
            "rule_code": self.rule_code,
            "passed": self.passed,
            "findings": self.findings,
            "error": self.error,
        }


# ---------------------------------------------------------------------------
# Python 类型执行器
# ---------------------------------------------------------------------------


def _load_class_from_dotted_path(dotted_path: str) -> type:
    """从 dotted path 加载类。

    例如: 'app.services.qc_engine.ConclusionNotEmptyRule'
    -> 导入 app.services.qc_engine 模块，取 ConclusionNotEmptyRule 属性
    """
    parts = dotted_path.rsplit(".", 1)
    if len(parts) != 2:
        raise ImportError(
            f"Invalid dotted path '{dotted_path}': expected 'module.ClassName'"
        )
    module_path, class_name = parts
    try:
        module = importlib.import_module(module_path)
    except ModuleNotFoundError as e:
        raise ImportError(f"Module '{module_path}' not found: {e}") from e
    cls = getattr(module, class_name, None)
    if cls is None:
        raise ImportError(
            f"Class '{class_name}' not found in module '{module_path}'"
        )
    return cls


async def execute_python_rule(
    rule: QcRuleDefinition,
    context: Any,
    timeout: float = PYTHON_RULE_TIMEOUT_SECONDS,
) -> RuleExecutionResult:
    """执行 Python 类型规则。

    1. 从 rule.expression (dotted path) 加载规则类
    2. 实例化规则对象
    3. 调用 check(context) 方法，带 timeout 沙箱
    4. 返回执行结果
    """
    rule_code = rule.rule_code
    dotted_path = rule.expression

    try:
        rule_cls = _load_class_from_dotted_path(dotted_path)
    except ImportError as e:
        logger.error("[QC_EXECUTOR] Failed to load rule class: %s", e)
        return RuleExecutionResult(
            rule_code=rule_code,
            passed=False,
            error=f"Failed to load rule class: {e}",
        )

    try:
        rule_instance = rule_cls()
    except Exception as e:
        logger.error("[QC_EXECUTOR] Failed to instantiate rule class: %s", e)
        return RuleExecutionResult(
            rule_code=rule_code,
            passed=False,
            error=f"Failed to instantiate rule class: {e}",
        )

    # 执行 check() 方法，带 timeout 沙箱
    try:
        findings = await asyncio.wait_for(
            rule_instance.check(context),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        logger.warning(
            "[QC_EXECUTOR] Rule %s timed out after %ss", rule_code, timeout
        )
        return RuleExecutionResult(
            rule_code=rule_code,
            passed=False,
            error=f"Rule execution timed out after {timeout}s",
        )
    except Exception as e:
        logger.exception("[QC_EXECUTOR] Rule %s raised exception", rule_code)
        return RuleExecutionResult(
            rule_code=rule_code,
            passed=False,
            error=f"Rule execution error: {e}",
        )

    # 转换 findings 为 dict 列表
    finding_dicts = []
    for f in findings:
        if hasattr(f, "to_dict"):
            finding_dicts.append(f.to_dict())
        elif isinstance(f, dict):
            finding_dicts.append(f)
        else:
            finding_dicts.append({"message": str(f)})

    passed = len(finding_dicts) == 0
    return RuleExecutionResult(
        rule_code=rule_code,
        passed=passed,
        findings=finding_dicts,
    )


# ---------------------------------------------------------------------------
# JSONPath 类型执行器
# ---------------------------------------------------------------------------


async def execute_jsonpath_rule(
    rule: QcRuleDefinition,
    parsed_data: dict | None,
) -> RuleExecutionResult:
    """执行 JSONPath 类型规则。

    对 parsed_data 执行 JSONPath 表达式：
    - 如果表达式匹配到结果（非空），视为"命中"（有 finding）
    - 如果表达式无匹配，视为"通过"

    规则的 parameters_schema 可包含:
    - expect_match: bool (默认 True) — True 表示期望匹配到值（匹配=通过），
      False 表示期望不匹配（不匹配=通过）
    - message: str — 自定义 finding 消息

    注意：只读操作，不修改 parsed_data。
    """
    rule_code = rule.rule_code
    expression = rule.expression

    if parsed_data is None:
        parsed_data = {}

    try:
        from jsonpath_ng import parse as jsonpath_parse
    except ImportError as e:
        logger.error("[QC_EXECUTOR] jsonpath-ng not installed: %s", e)
        return RuleExecutionResult(
            rule_code=rule_code,
            passed=False,
            error="jsonpath-ng library not installed",
        )

    try:
        jsonpath_expr = jsonpath_parse(expression)
    except Exception as e:
        logger.error(
            "[QC_EXECUTOR] Invalid JSONPath expression '%s': %s", expression, e
        )
        return RuleExecutionResult(
            rule_code=rule_code,
            passed=False,
            error=f"Invalid JSONPath expression: {e}",
        )

    # 执行 JSONPath 查询（只读）
    try:
        matches = jsonpath_expr.find(parsed_data)
    except Exception as e:
        logger.error("[QC_EXECUTOR] JSONPath evaluation error: %s", e)
        return RuleExecutionResult(
            rule_code=rule_code,
            passed=False,
            error=f"JSONPath evaluation error: {e}",
        )

    # 解析参数
    params = rule.parameters_schema or {}
    expect_match = params.get("expect_match", True)
    custom_message = params.get("message", "")

    has_matches = len(matches) > 0

    # 判定逻辑：
    # expect_match=True: 期望匹配到值 → 匹配到=通过，未匹配=有 finding
    # expect_match=False: 期望不匹配 → 未匹配=通过，匹配到=有 finding
    if expect_match:
        # 期望匹配到值（如"结论不为空"）
        if has_matches:
            # 匹配到了，通过
            return RuleExecutionResult(rule_code=rule_code, passed=True)
        else:
            # 未匹配到，产生 finding
            message = custom_message or (
                f"JSONPath '{expression}' 未匹配到数据"
            )
            return RuleExecutionResult(
                rule_code=rule_code,
                passed=False,
                findings=[
                    {
                        "rule_id": rule_code,
                        "severity": rule.severity,
                        "message": message,
                    }
                ],
            )
    else:
        # 期望不匹配（如"不应存在某字段"）
        if not has_matches:
            # 未匹配到，通过
            return RuleExecutionResult(rule_code=rule_code, passed=True)
        else:
            # 匹配到了，产生 finding
            matched_values = [m.value for m in matches[:5]]
            message = custom_message or (
                f"JSONPath '{expression}' 不应匹配到数据，"
                f"但找到 {len(matches)} 项"
            )
            return RuleExecutionResult(
                rule_code=rule_code,
                passed=False,
                findings=[
                    {
                        "rule_id": rule_code,
                        "severity": rule.severity,
                        "message": message,
                        "matched_values": matched_values,
                    }
                ],
            )


# ---------------------------------------------------------------------------
# Audit Log 类型执行器（scope='audit_log'）
# ---------------------------------------------------------------------------


class AuditLogContext:
    """audit_log 规则执行上下文。"""

    def __init__(
        self,
        project_id: UUID | None = None,
        time_window_start: datetime | None = None,
        time_window_end: datetime | None = None,
    ):
        self.project_id = project_id
        self.time_window_start = time_window_start
        self.time_window_end = time_window_end


async def execute_audit_log_rule(
    rule: QcRuleDefinition,
    db: AsyncSession,
    project_id: UUID | None = None,
    time_window_start: datetime | None = None,
    time_window_end: datetime | None = None,
) -> RuleExecutionResult:
    """执行 audit_log scope 的规则。

    查询 audit_log_entries 表，对每条 entry 的 payload 执行 JSONPath 过滤。
    命中的条目作为 findings 返回。

    Args:
        rule: QcRuleDefinition 实例（scope='audit_log', expression_type='jsonpath'）
        db: AsyncSession 数据库会话
        project_id: 可选项目 ID 过滤
        time_window_start: 时间窗口起始
        time_window_end: 时间窗口结束

    Returns:
        RuleExecutionResult，findings 包含命中的日志条目信息
    """
    rule_code = rule.rule_code
    expression = rule.expression

    # 仅支持 jsonpath 类型的 audit_log 规则（python 类型 deferred to R6+）
    if rule.expression_type == "python":
        return RuleExecutionResult(
            rule_code=rule_code,
            passed=True,
            findings=[],
            error="Python-type audit_log rules deferred to R6+",
        )

    try:
        from jsonpath_ng import parse as jsonpath_parse
    except ImportError as e:
        logger.error("[QC_EXECUTOR] jsonpath-ng not installed: %s", e)
        return RuleExecutionResult(
            rule_code=rule_code,
            passed=False,
            error="jsonpath-ng library not installed",
        )

    try:
        jsonpath_expr = jsonpath_parse(expression)
    except Exception as e:
        logger.error(
            "[QC_EXECUTOR] Invalid JSONPath expression '%s': %s", expression, e
        )
        return RuleExecutionResult(
            rule_code=rule_code,
            passed=False,
            error=f"Invalid JSONPath expression: {e}",
        )

    # 构建查询
    stmt = select(AuditLogEntry)
    conditions = []

    if project_id is not None:
        # audit_log_entries 的 payload 中可能含 project_id，
        # 或通过 object_id 关联项目
        conditions.append(AuditLogEntry.object_id == project_id)

    if time_window_start is not None:
        conditions.append(AuditLogEntry.ts >= time_window_start)

    if time_window_end is not None:
        conditions.append(AuditLogEntry.ts <= time_window_end)

    if conditions:
        stmt = stmt.where(*conditions)

    # 按时间倒序，限制查询量避免性能问题
    stmt = stmt.order_by(AuditLogEntry.ts.desc()).limit(10000)

    try:
        result = await db.execute(stmt)
        entries = result.scalars().all()
    except Exception as e:
        logger.error("[QC_EXECUTOR] Failed to query audit_log_entries: %s", e)
        return RuleExecutionResult(
            rule_code=rule_code,
            passed=False,
            error=f"Failed to query audit_log_entries: {e}",
        )

    # 对每条 entry 的 payload 执行 JSONPath 过滤
    hits: list[dict] = []
    for entry in entries:
        payload = entry.payload or {}
        try:
            matches = jsonpath_expr.find(payload)
            if matches:
                hits.append({
                    "entry_id": str(entry.id),
                    "ts": entry.ts.isoformat() if entry.ts else None,
                    "action_type": entry.action_type,
                    "user_id": str(entry.user_id) if entry.user_id else None,
                    "ip": entry.ip,
                    "matched_values": [m.value for m in matches[:3]],
                    "rule_id": rule_code,
                    "severity": rule.severity,
                    "message": f"审计日志规则 {rule_code} 命中: action={entry.action_type}",
                })
        except Exception:
            # 单条 entry 解析失败不中断整体
            continue

    passed = len(hits) == 0
    return RuleExecutionResult(
        rule_code=rule_code,
        passed=passed,
        findings=hits,
    )


# ---------------------------------------------------------------------------
# 统一分派入口
# ---------------------------------------------------------------------------


async def execute_rule(
    rule: QcRuleDefinition,
    context: Any = None,
    parsed_data: dict | None = None,
    db: AsyncSession | None = None,
    project_id: UUID | None = None,
    time_window_start: datetime | None = None,
    time_window_end: datetime | None = None,
) -> RuleExecutionResult:
    """根据 expression_type 和 scope 分派到对应执行器。

    Args:
        rule: QcRuleDefinition 实例
        context: QCContext 对象（Python 类型规则需要）
        parsed_data: 底稿 parsed_data（JSONPath 类型规则需要）
        db: AsyncSession（audit_log scope 需要）
        project_id: 项目 ID（audit_log scope 过滤用）
        time_window_start: 时间窗口起始（audit_log scope）
        time_window_end: 时间窗口结束（audit_log scope）

    Returns:
        RuleExecutionResult

    Raises:
        NotImplementedError: expression_type 为 'sql' 或 'regex' 时
    """
    # scope='audit_log' 走专用执行器
    if rule.scope == "audit_log":
        if db is None:
            return RuleExecutionResult(
                rule_code=rule.rule_code,
                passed=False,
                error="audit_log scope requires a database session",
            )
        return await execute_audit_log_rule(
            rule, db, project_id, time_window_start, time_window_end
        )

    expression_type = rule.expression_type

    if expression_type == "python":
        if context is None:
            return RuleExecutionResult(
                rule_code=rule.rule_code,
                passed=False,
                error="Python rule requires a QCContext",
            )
        return await execute_python_rule(rule, context)

    elif expression_type == "jsonpath":
        return await execute_jsonpath_rule(rule, parsed_data)

    elif expression_type in ("sql", "regex"):
        raise NotImplementedError(
            f"expression_type='{expression_type}' 执行器尚未实现，"
            f"预留 Round 6+ 补齐"
        )

    else:
        return RuleExecutionResult(
            rule_code=rule.rule_code,
            passed=False,
            error=f"Unknown expression_type: '{expression_type}'",
        )
