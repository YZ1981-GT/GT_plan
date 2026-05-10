"""Import 异常 → 用户友好提示映射（E1 / Batch 3 M4 拆分）。

本模块从 `import_job_runner.py` 拆出，独立承担错误映射职责。
- `_ErrorRule` / `_ERROR_RULES`: 规则注册表（开闭原则）
- `register_error_rule()`: 扩展点
- `_humanize_import_error()`: 核心映射函数

使用方：
- `import_job_runner._execute` / `_execute_v2` 失败分支
- 未来其他 worker/任务的失败提示

历史兼容：`import_job_runner` 中 re-export 了本模块所有符号，
旧代码 `from app.services.import_job_runner import _humanize_import_error`
和测试用法保持不变。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

from app.services.smart_import_engine import SmartImportError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _ErrorRule:
    """错误映射规则：matcher 返回 True 时使用 formatter 生成用户提示。"""
    name: str
    matcher: Callable[[Exception, str, str], bool]  # (exc, exc_name_lower, msg_lower) -> bool
    formatter: Callable[[Exception, str], str]       # (exc, msg_full) -> user_message


# 默认规则表（顺序即优先级，首个匹配即返回）
# E1: 开闭原则——新增规则只在此 append 一条或调 register_error_rule，不改核心函数
_ERROR_RULES: list[_ErrorRule] = [
    _ErrorRule(
        name="smart_import_error",
        matcher=lambda exc, _n, _m: isinstance(exc, SmartImportError),
        formatter=lambda _e, msg: msg[:500],
    ),
    _ErrorRule(
        name="foreign_key_violation",
        matcher=lambda _e, name, msg: "foreignkeyviolation" in name or "foreign key" in msg,
        formatter=lambda _e, msg: f"数据关联错误：存在无效的引用关系。原始信息：{msg[:200]}",
    ),
    _ErrorRule(
        name="unique_violation",
        matcher=lambda _e, name, msg: "uniqueviolation" in name or "duplicate key" in msg,
        formatter=lambda _e, msg: f"数据重复：同一科目/年度已存在相同记录。原始信息：{msg[:200]}",
    ),
    _ErrorRule(
        name="invalid_text_representation",
        matcher=lambda _e, name, msg: "invalidtextrepresentation" in name or "invalid input" in msg,
        formatter=lambda _e, msg: f"字段格式错误：某列的值无法解析（如日期/金额/枚举）。原始信息：{msg[:300]}",
    ),
    _ErrorRule(
        name="not_null_violation",
        matcher=lambda _e, name, msg: "notnullviolation" in name or "null value" in msg,
        formatter=lambda _e, msg: f"必填字段为空：原始文件某必填列缺失值。原始信息：{msg[:200]}",
    ),
    _ErrorRule(
        name="connection_error",
        matcher=lambda _e, name, msg: "connectionrefused" in name or "connection reset" in msg,
        formatter=lambda _e, _m: "数据库连接中断，请稍后重试或联系管理员",
    ),
    _ErrorRule(
        name="bad_zip_file",
        matcher=lambda exc, _n, _m: exc.__class__.__name__ in ("BadZipFile", "InvalidFileException"),
        formatter=lambda _e, msg: f"文件格式损坏或无法识别：{msg[:200]}",
    ),
    _ErrorRule(
        name="unicode_error",
        matcher=lambda exc, _n, _m: exc.__class__.__name__ in ("UnicodeDecodeError", "UnicodeError"),
        formatter=lambda _e, _m: "文件编码错误：自动探测失败，请另存为 UTF-8 或 GBK 后重试",
    ),
    _ErrorRule(
        name="key_column_empty",
        matcher=lambda _e, _n, msg: "key column" in msg and "empty" in msg,
        formatter=lambda _e, msg: f"关键列缺失：{msg[:200]}（建议核对列映射）",
    ),
    _ErrorRule(
        name="memory_error",
        matcher=lambda exc, name, _m: exc.__class__.__name__ == "MemoryError" or "memoryerror" in name,
        formatter=lambda _e, _m: "内存不足：文件过大，建议拆分后分批导入",
    ),
    _ErrorRule(
        name="timeout",
        matcher=lambda _e, name, msg: "timeout" in name or "timeout" in msg,
        formatter=lambda _e, msg: f"操作超时：{msg[:200]}",
    ),
]


def register_error_rule(rule: _ErrorRule, *, priority: int | None = None) -> None:
    """扩展点：运行时追加新规则。

    Args:
        rule: 要添加的规则
        priority: 插入位置（None = 末尾，0 = 最高优先级）
    """
    if priority is None or priority >= len(_ERROR_RULES):
        _ERROR_RULES.append(rule)
    else:
        _ERROR_RULES.insert(max(0, priority), rule)


def _humanize_import_error(exc: Exception) -> str:
    """把技术异常转成用户友好提示（E1 重构：规则注册表模式，开闭原则）。

    规则查找：遍历 `_ERROR_RULES` 首个 matcher 返回 True 的规则生效。
    未命中时兜底返回 `[ExcClassName] msg[:500]`。

    扩展方式：不再改本函数，用 `register_error_rule()` 追加规则。
    """
    msg = str(exc)
    exc_name = exc.__class__.__name__
    lower_msg = msg.lower()
    lower_name = exc_name.lower()

    for rule in _ERROR_RULES:
        try:
            if rule.matcher(exc, lower_name, lower_msg):
                return rule.formatter(exc, msg)
        except Exception:
            logger.debug("error rule %r matcher raised", rule.name, exc_info=True)
            continue

    return f"[{exc_name}] {msg[:500]}"
