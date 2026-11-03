"""ProcedureInstance 身份的唯一规范化边界。

数据库约束和所有写/精确读入口都使用同一规则：循环、程序编码、底稿编码去首尾空白并转大写。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProcedureIdentity:
    audit_cycle: str
    procedure_code: str
    wp_code: str | None


def normalize_cycle(value: str | None) -> str:
    cycle = (value or "").strip().upper()
    if not cycle:
        raise ValueError("审计循环不能为空")
    if len(cycle) > 10:
        raise ValueError("审计循环不能超过 10 个字符")
    return cycle


def normalize_procedure_code(value: str | None) -> str:
    code = (value or "").strip().upper()
    if not code:
        raise ValueError("程序编码不能为空")
    if len(code) > 50:
        raise ValueError("程序编码不能超过 50 个字符")
    return code


def normalize_wp_code(value: str | None, *, fallback: str | None = None) -> str | None:
    raw = value if value is not None and str(value).strip() else fallback
    if raw is None:
        return None
    code = str(raw).strip().upper()
    if not code:
        return None
    if len(code) > 50:
        raise ValueError("底稿编码不能超过 50 个字符")
    return code


def normalize_procedure_identity(
    cycle: str | None,
    procedure_code: str | None,
    wp_code: str | None = None,
) -> ProcedureIdentity:
    code = normalize_procedure_code(procedure_code)
    return ProcedureIdentity(
        audit_cycle=normalize_cycle(cycle),
        procedure_code=code,
        wp_code=normalize_wp_code(wp_code, fallback=code),
    )
