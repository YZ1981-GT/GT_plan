"""公式取数告警收集器（spec formula-hub-integrity-closure 需求 4.3，ADR-FHIC-03）。

取数函数（试算表叶子口径 :mod:`app.services.tb_leaf_codes` 等）取数时 :func:`emit` 告警；结果合并点
（报表 L2 ``report_engine.evaluate_formula_result``、推送 ``formula_push.engine`` 的运行结果，以及后续任务接入的
中央 execute / debug、报表逐行计算）用 :func:`collect` 包住取数过程，把收集到的告警写进各自结果的 ``warnings``。

* ``collect()`` 可嵌套：告警进入当前**全部**活动收集器（内层收到的外层也收到）；同一收集器内按值去重。
* 没有活动收集器时 :func:`emit` 只记 ``logger.info``，不抛错、不改取数结果。
* 上下文用 ``ContextVar``：asyncio 子任务创建时复制上下文 ⇒ ``gather`` 出去的取数也进同一收集器。

告警是 dict（试算表叶子告警的键见 ``tb_leaf_codes.select_leaves``），合并到 ``list[str]`` 形态的结果时只取
``message``（:func:`messages` / :func:`merge_into`）。
"""
from __future__ import annotations

import logging
from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

logger = logging.getLogger(__name__)

#: 当前活动的收集器（外 → 内）；元组不可变，嵌套时整体替换、退出时 reset
_ACTIVE: ContextVar[tuple[list[dict[str, Any]], ...]] = ContextVar("formula_warning_collectors", default=())


@contextmanager
def collect() -> Iterator[list[dict[str, Any]]]:
    """开启一个告警收集器；``with`` 块内（含其中 await 的取数）emit 的告警都进产出的 list。"""
    bucket: list[dict[str, Any]] = []
    token = _ACTIVE.set((*_ACTIVE.get(), bucket))
    try:
        yield bucket
    finally:
        _ACTIVE.reset(token)


def emit(warnings: Mapping[str, Any] | Iterable[Mapping[str, Any]]) -> None:
    """发出一条或多条告警（dict 或 dict 的可迭代对象）。"""
    items = [warnings] if isinstance(warnings, Mapping) else list(warnings)
    if not items:
        return
    active = _ACTIVE.get()
    for item in items:
        warning = dict(item)
        if not active:
            logger.info("公式取数告警（当前没有收集器）：%s", warning.get("message", warning))
            continue
        for bucket in active:
            if warning not in bucket:
                bucket.append(warning)


def messages(warnings: Iterable[Mapping[str, Any]]) -> list[str]:
    """告警 → 去重后的文案（保持出现顺序；没有 ``message`` 的跳过）。"""
    out: list[str] = []
    for warning in warnings:
        text = str(warning.get("message") or "").strip()
        if text and text not in out:
            out.append(text)
    return out


def merge_into(target: list[str], warnings: Iterable[Mapping[str, Any]]) -> list[str]:
    """把告警文案并入 ``target``（原地、去重），返回 ``target``。"""
    for text in messages(warnings):
        if text not in target:
            target.append(text)
    return target
