# -*- coding: utf-8 -*-
"""OnlyOffice 重算公式格的「公式证据」（spec oo-formula-recompute-not-tamper R1 / R2）。

═══ 要解决的事 ═══

OnlyOffice 打开文档就会重算公式：用户在 OO 里改了某个公式的输入，这个公式格在 OO 一侧必然
「变了值」。三方合并原先只看值，于是把每一次重算都当成「用户在 OO 里改了公式格」（AC 6.6 /
Property 24）—— D2-2 在线编辑改金额，期末余额 / 期末未审 / 期末审定三列必冲突。真库现有的
351 条受保护冲突全部是这一种形态。

区分「重算」与「篡改」要看公式本身有没有被动过。公式文本提取时本来就读到了（`formula_inventory`），
本模块把它归一成**公式签名**，并给出合并要用的判定。

═══ 公式签名 ═══

单元格公式里「引用本行的地址」换成 ``{r}``，其余逐字保留：

* ``=E13+O13-P13``（在第 13 行）→ ``=E{r}+O{r}-P{r}``；OO 在上方插一行后它变成第 14 行的
  ``=E14+O14-P14``，签名不变 —— 原文比较会把每一次插行都判成「公式被改写」；
* ``$`` 锁定照样换（插行时 OO 也会推动锁定的行）：``$E$13`` → ``$E${r}``；区间逐端点换；
* 引用别的行（``$C$24`` 合计行）、带表名的引用（任何 ``Sheet!``）、结构化引用、名称、字符串
  字面量**逐字保留** —— 它们的行号在插行后会变，签名随之不同，那一次保存若值也变了就仍按现状
  报冲突（不比现在差）。

分词只调用 :func:`excel_row_shift._rewrite_formula_refs` —— 全仓唯一的 A1 改写入口
（Property 27），这里只读使用：它已处理字符串字面量、跨表前缀、``LOG10(`` 这类带数字的函数名
与 ``&quot;`` 实体。remap 把本行映射到一个真实引用不可能出现的哨兵行，再把哨兵换成 ``{r}``。

═══ 依赖方向 ═══

``excel_extract``（算签名）与 ``merge``（读签名判定）都依赖本模块；本模块**不** import
merge / conflicts —— 否则就成了 merge 域的消费方（Task 14 的双向等值登记表会打红）。
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Final, Iterable, Mapping

__all__ = [
    "SAME_ROW",
    "FormulaEvidence",
    "classify_formula_evidence",
    "formula_families",
    "formula_signature",
    "protected_conflict_reason",
    "recompute_drift_reason",
    "signature_in_family",
    "template_key",
    "union_formula_signatures",
]

#: 签名里「本行」的记号。
SAME_ROW: Final[str] = "{r}"

#: Excel 最大行号 1048576 + 1：任何真实引用都用不到它，用作「本行」的临时替身。
_SENTINEL_ROW: Final[int] = 1_048_577
_SENTINEL_TEXT: Final[str] = str(_SENTINEL_ROW)


def formula_signature(text: str, *, own_row: int) -> str:
    """把公式文本归一成与所在行号无关的签名（见模块 docstring）。

    原文里已经出现哨兵数字串时**不归一**、原样返回：此时无法区分哪一处是替身，宁可让签名
    对行号敏感（只会多出冲突，不会少）。
    """
    if not text or _SENTINEL_TEXT in text:
        return text
    from app.services.workpaper_sync.excel_row_shift import _rewrite_formula_refs

    rewritten, _changed = _rewrite_formula_refs(
        text, remap=lambda row: _SENTINEL_ROW if row == own_row else row
    )
    return rewritten.replace(_SENTINEL_TEXT, SAME_ROW)


def union_formula_signatures(parts: Iterable[Any]) -> Mapping[str, str] | None:
    """多个 binding 提取结果的签名并集；没有任何一份带签名 ⇒ None（来源不提供证据）。"""
    merged: dict[str, str] | None = None
    for part in parts:
        signatures = getattr(part, "formula_signatures", None)
        if signatures is None:
            continue
        if merged is None:
            merged = {}
        merged.update(signatures)
    return merged


class FormulaEvidence(str, Enum):
    """受保护字段在 base 与 OO 一侧（incoming）之间的公式变化。"""

    #: 任一侧不提供证据（Word、非 xlsx 适配器、转置表…）⇒ 合并按原规则处理。
    unobserved = "unobserved"
    #: 两侧签名都在且相同 ⇒ 公式没动过，值的变化来自重算。
    intact = "intact"
    #: base 是公式、OO 一侧不是 ⇒ 公式被换成了数值。
    formula_removed = "formula_removed"
    #: 两侧都是公式但签名不同 ⇒ 公式被改写。
    formula_changed = "formula_changed"
    #: base 不是公式、OO 一侧是 ⇒ 只读的数值格被写入了公式。
    formula_added = "formula_added"
    #: 两侧都没有读到公式 ⇒ 只读的数值格被改了值。
    literal_changed = "literal_changed"


def classify_formula_evidence(
    base_signatures: Mapping[str, str] | None,
    incoming_signatures: Mapping[str, str] | None,
    key: str,
) -> FormulaEvidence:
    """按两侧签名判定 `key` 的公式变化（六类互不重叠）。"""
    if base_signatures is None or incoming_signatures is None:
        return FormulaEvidence.unobserved
    before = base_signatures.get(key)
    after = incoming_signatures.get(key)
    if before and after:
        return FormulaEvidence.intact if before == after else FormulaEvidence.formula_changed
    if before:
        return FormulaEvidence.formula_removed
    if after:
        return FormulaEvidence.formula_added
    return FormulaEvidence.literal_changed


def template_key(stable_key: str, row_key: str | None) -> str | None:
    """行域字段的「列」身份：把行身份那一段换回 ``{row_uuid}``；静态字段返回 None。"""
    if not row_key:
        return None
    parts = stable_key.split("/")
    if row_key not in parts:
        return None
    return "/".join("{row_uuid}" if part == row_key else part for part in parts)


def formula_families(
    signatures: Mapping[str, str] | None, projection: Any
) -> dict[str, frozenset[str]]:
    """base 里每一列（行域字段模板）出现过的公式签名集合 —— 给 OO 新增行比对用。"""
    if not signatures:
        return {}
    families: dict[str, set[str]] = {}
    for key, signature in signatures.items():
        field = projection.get(key)
        column = template_key(key, getattr(field, "row_key", None)) if field is not None else None
        if column is not None and signature:
            families.setdefault(column, set()).add(signature)
    return {column: frozenset(found) for column, found in families.items()}


def signature_in_family(
    signatures: Mapping[str, str] | None,
    key: str,
    row_key: str | None,
    families: Mapping[str, frozenset[str]],
) -> bool:
    """OO 新增行的这一格是否就是 base 同一列已有的公式（行号归一后逐字相同）。"""
    if not signatures:
        return False
    signature = signatures.get(key)
    column = template_key(key, row_key)
    return bool(signature) and column is not None and signature in families.get(column, ())


def _clip(text: str | None, limit: int = 80) -> str:
    value = text or ""
    return value if len(value) <= limit else value[: limit - 1] + "…"


def protected_conflict_reason(
    policy: str,
    evidence: FormulaEvidence,
    *,
    base_signature: str | None = None,
    incoming_signature: str | None = None,
) -> str:
    """受保护冲突的原因文案。无证据时与修订前逐字相同（R1.4）。"""
    if evidence is FormulaEvidence.formula_removed:
        what = "的公式在 OO 侧被换成了数值"
    elif evidence is FormulaEvidence.formula_changed:
        what = (
            f"的公式在 OO 侧被改写（{_clip(base_signature)} → {_clip(incoming_signature)}）"
        )
    elif evidence is FormulaEvidence.formula_added:
        what = "原本不是公式，OO 侧写入了公式"
    elif evidence is FormulaEvidence.literal_changed:
        what = "两侧都没有读到公式，OO 侧的值与打开时不同"
    else:
        return (
            f"受保护字段（{policy}）在 OO 侧被改动 —— "
            "公式/auto-source 结果不得被覆盖（AC 6.6），"
            "incoming 值只用于篡改检测"
        )
    return f"受保护字段（{policy}）{what} —— 只读格的结果不得被覆盖（AC 6.6），保留服务器侧的值"


def recompute_drift_reason(drift: str) -> str:
    """公式完好但输入不一致时的原因文案（R1.2），点名第一处差异。"""
    return (
        "公式格在 OO 侧按 OO 一侧的输入重算过，但合并结果里还有 OO 一侧没有的改动"
        f"（{_clip(drift, 120)}）—— 这次 OO 算出的值不能直接采用，保留服务器侧的值"
        "（AC 6.6，spec oo-formula-recompute-not-tamper R1.2）"
    )
