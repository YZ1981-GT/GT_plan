"""公式实际输入收集器。

与 formula_warnings 使用同样的 ContextVar 嵌套语义。没有活动收集器时
emit 是静默 no-op，避免旧调用方为了接入来源摘要必须改变行为。
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from app.services.formula_provenance import (
    InputAtom,
    input_digest,
    input_summary,
    normalize_input_atom,
)

_ACTIVE: ContextVar[tuple[list[InputAtom], ...]] = ContextVar(
    "formula_input_collectors", default=()
)


@contextmanager
def collect() -> Iterator[list[InputAtom]]:
    """开启可嵌套的输入收集器。"""
    bucket: list[InputAtom] = []
    token = _ACTIVE.set((*_ACTIVE.get(), bucket))
    try:
        yield bucket
    finally:
        _ACTIVE.reset(token)


def emit(
    kind: str,
    key: str,
    value: Any,
    source_ref: str | None = None,
    source_project_id: str | None = None,
) -> None:
    """把一次实际取数广播给当前全部活动收集器。"""
    atom = normalize_input_atom(kind, key, value, source_ref, source_project_id)
    for bucket in _ACTIVE.get():
        bucket.append(atom)


def summarize(
    inputs: list[InputAtom], *, limit: int = 200
) -> tuple[list[InputAtom], int, bool, str]:
    """把收集结果转换成展示列表、总数、截断标志和 digest。"""
    return input_summary(inputs, limit=limit)


__all__ = ["collect", "emit", "input_digest", "summarize"]
