# -*- coding: utf-8 -*-
"""OO→HTML 物化时把受保护公式格还原成已发布形态的公式（spec oo-writeback-template-parity-closure R4）。

═══ 要解决的事 ═══

OO 一侧把公式格敲成了数字（或把公式改写了），合并判受保护冲突、保留服务器值 —— 受保护冲突
只能「保留服务器值」（`conflict_resolution.ProtectedFieldOverrideError`）。随后物化以 incoming
为底写文件：

* 公式被敲成数字：该格没有 ``<f>``，``_emit`` 判「契约说是公式但 substrate 没公式」直接抛
  ``ProtectedRegionWriteError`` —— 实测（真 D4）这次保存整体失败，不是「发布出一个数字」；
* 公式被改写且值没变：合并不报冲突，``intended_formulas`` 生产上不传 ⇒ 改写后的公式原样进文件。

两种情形都应写回已发布形态（base representation）的公式、值取合并结果。

═══ 公式从哪来 ═══

已发布形态的公式签名（``Projection.formula_signatures``，本行 ``{r}``、表几何 ``{start}`` /
``{end}`` / ``{end+k}`` / ``{r±k}``，见 :mod:`formula_recompute_evidence`）按落点行与 incoming 表
的几何换回公式文本（``instantiate_signature``）。OO 插过行时合计行引用跟着落到新位置 —— 不能直接
拿已发布文件里的公式原文，那是插行前的坐标。

签名经 adapter 自己的 ``extract(base)`` 取（OO→HTML 合并刚提过同一份 base，命中提取缓存）。

═══ 作用域 ═══

物化函数链很深（单趟 / 逐趟 / 静态区三条路径），逐层加参数要改十几处签名；这里用与
``workbook_read_scope`` 同型的作用域：adapter 在 OO→HTML 物化外层进入，``_emit`` 读取。
作用域之外（HTML→OO、首版发布、离线工具）恒为 None，行为与修订前逐字相同。
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Iterator, Mapping

from app.services.workpaper_sync import formula_recompute_evidence as FRE

__all__ = ["restore_scope_for", "wanted_formula"]

_BASE_SIGNATURES: ContextVar[Mapping[str, str] | None] = ContextVar(
    "workpaper_sync_restore_base_signatures", default=None
)


def _incoming_direction(adapter: Any, substrate: Path) -> bool:
    """与 ``ExcelSyncAdapter._materialize_within_scope`` 的 ``incoming_ns`` 同一判据。"""
    from app.services.workpaper_sync.models import ArtifactKind

    return (
        getattr(adapter, "substrate_kind", None) is ArtifactKind.incoming
        or ".incoming" in substrate.resolve().parts
    )


@contextmanager
def restore_scope_for(adapter: Any, substrate: Path, contract: Any) -> Iterator[None]:
    """OO→HTML 且有已发布形态时，在物化期间提供 base 的公式签名；其余情形什么都不做。"""
    base = getattr(adapter, "baseline_representation", None)
    signatures: Mapping[str, str] | None = None
    if base is not None and _incoming_direction(adapter, substrate):
        projection = adapter.extract(artifact=Path(base), contract=contract)
        signatures = getattr(projection, "formula_signatures", None) or None
    token = _BASE_SIGNATURES.set(signatures)
    try:
        yield
    finally:
        _BASE_SIGNATURES.reset(token)


def _family_signature(signatures: Mapping[str, str], template: str) -> str | None:
    """OO 新增行：base 同一列（行域字段模板）只有一种公式时用它。"""
    head, sep, tail = template.partition("{row_uuid}")
    if not sep:
        return None
    found = {
        signature
        for key, signature in signatures.items()
        if key.startswith(head) and key.endswith(tail) and "/" not in key[len(head): len(key) - len(tail)]
    }
    return next(iter(found)) if len(found) == 1 else None


def wanted_formula(
    key: str, template: str, *, row: int, frame: tuple[int, int] | None
) -> tuple[str, str] | None:
    """`(base 签名, 落在第 row 行的公式文本)`；作用域外 / base 无此公式 / 落不了地 ⇒ None。"""
    signatures = _BASE_SIGNATURES.get()
    if not signatures:
        return None
    signature = signatures.get(key) or _family_signature(signatures, template)
    if not signature:
        return None
    text = FRE.instantiate_signature(signature, row=row, frame=frame)
    return None if text is None else (signature, text)
