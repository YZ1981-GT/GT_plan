# -*- coding: utf-8 -*-
"""公式证据：签名、六类判定、同列公式族（spec oo-formula-recompute-not-tamper R2.1）。

纯函数判据；合并怎么用这些判定见 `test_merge_formula_recompute.py`。
"""
from __future__ import annotations

import ast
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:  # pragma: no cover - import 环境自举
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.workpaper_sync import formula_recompute_evidence as FE  # noqa: E402

_MODULE = _BACKEND / "app" / "services" / "workpaper_sync" / "formula_recompute_evidence.py"


# ── 签名 ────────────────────────────────────────────────────────────────────

SIGNATURES: list[tuple[str, int, str]] = [
    # D2-2 期末余额：本行引用全部归一
    ("=E13+O13-P13", 13, "=E{r}+O{r}-P{r}"),
    # `$` 锁定照样归一、标记保留
    ("=$E$13+O13", 13, "=$E${r}+O{r}"),
    ("=$A13+A$13", 13, "=$A{r}+A${r}"),
    # 本行区间逐端点归一（D4-2 期间合计）
    ("=SUM(B12:M12)", 12, "=SUM(B{r}:M{r})"),
    # 引用别的行原样（D2-3 小计、D4-9 合计行）
    ("=SUM(E13:E16)", 12, "=SUM(E13:E16)"),
    ("=IF(C13=0,0,C13/$C$24)", 13, "=IF(C{r}=0,0,C{r}/$C$24)"),
    ("=IF(YEAR(C13)=YEAR($B$10)-1,H13,0)", 13, "=IF(YEAR(C{r})=YEAR($B$10)-1,H{r},0)"),
    # 带表名的引用一律原样（哪怕指向本表）
    ("='明细表D2-2'!E13+O13", 13, "='明细表D2-2'!E13+O{r}"),
    ("=Sheet1!A13+A13", 13, "=Sheet1!A13+A{r}"),
    # 字符串字面量、结构化引用、带数字的函数名、数字常量不动
    ('=IF(A13="K13","是","否")', 13, '=IF(A{r}="K13","是","否")'),
    ("=GT_D22_ROWS[[#This Row],[GTCol8]]", 13, "=GT_D22_ROWS[[#This Row],[GTCol8]]"),
    ("=LOG10(A13)", 13, "=LOG10(A{r})"),
    ("=I11/365*H11*B11", 11, "=I{r}/365*H{r}*B{r}"),
    # 原文已有哨兵数字串 ⇒ 不归一（只会多报，不会少报）
    ("=A13+1048577", 13, "=A13+1048577"),
    ("", 13, ""),
]


@pytest.mark.parametrize(("text", "row", "expected"), SIGNATURES)
def test_signature_table(text: str, row: int, expected: str) -> None:
    assert FE.formula_signature(text, own_row=row) == expected


@pytest.mark.parametrize(
    ("before", "after"),
    [
        (("=E13+O13-P13", 13), ("=E14+O14-P14", 14)),  # 上方插一行
        (("=E13+O13-P13", 13), ("=E12+O12-P12", 12)),  # 上方删一行
        (("=SUM(B12:M12)", 12), ("=SUM(B40:M40)", 40)),
        (("=$E$13+O13", 13), ("=$E$20+O20", 20)),
    ],
)
def test_signature_survives_row_moves(before: tuple[str, int], after: tuple[str, int]) -> None:
    """同一列的公式在行增删后签名不变 —— 原文比较会把每一次插行判成「公式被改写」。"""
    assert FE.formula_signature(before[0], own_row=before[1]) == FE.formula_signature(
        after[0], own_row=after[1]
    )


@pytest.mark.parametrize(
    ("original", "tampered"),
    [
        ("=E13+O13-P13", "=E13+O13-P13+100"),  # 加常量
        ("=E13+O13-P13", "=E12+O13-P13"),  # 改成引用上一行
        ("=E13+O13-P13", "=E13+O13"),  # 删项
        ("=SUM(B12:M12)", "=SUM(B12:L12)"),  # 缩区间
        ("=IF(C13=0,0,C13/$C$24)", "=IF(C13=0,0,C13/$C$25)"),
    ],
)
def test_signature_still_sees_edits(original: str, tampered: str) -> None:
    """归一只抹掉「所在行号」，公式本身的任何改动仍可见。"""
    row = 13 if "13" in original else 12
    assert FE.formula_signature(original, own_row=row) != FE.formula_signature(
        tampered, own_row=row
    )


def test_only_the_single_rewriter_is_used() -> None:
    """不另写 A1 分词：模块里不出现 `re` 与 A1 正则，只 import `_rewrite_formula_refs`（Property 27）。"""
    tree = ast.parse(_MODULE.read_text(encoding="utf-8"))
    imported = {
        (node.module, alias.name)
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    assert ("app.services.workpaper_sync.excel_row_shift", "_rewrite_formula_refs") in imported
    plain = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    assert "re" not in plain, "不得自带正则分词"


def test_module_is_not_a_merge_domain_consumer() -> None:
    """本模块被 merge import；它自己 import merge / conflicts 就成了未登记的 merge 域消费方。"""
    text = _MODULE.read_text(encoding="utf-8")
    for forbidden in (
        "from app.services.workpaper_sync.merge import",
        "from app.services.workpaper_sync import merge",
        "from app.services.workpaper_sync.conflicts import",
        "from app.services.workpaper_sync import conflicts",
    ):
        assert forbidden not in text


# ── 六类判定 ────────────────────────────────────────────────────────────────

K = "rows/r1/end_balance"


@pytest.mark.parametrize(
    ("base", "incoming", "expected"),
    [
        (None, {K: "=E{r}"}, FE.FormulaEvidence.unobserved),
        ({K: "=E{r}"}, None, FE.FormulaEvidence.unobserved),
        ({K: "=E{r}+O{r}"}, {K: "=E{r}+O{r}"}, FE.FormulaEvidence.intact),
        ({K: "=E{r}+O{r}"}, {}, FE.FormulaEvidence.formula_removed),
        ({K: "=E{r}+O{r}"}, {K: "=E{r}+O{r}+1"}, FE.FormulaEvidence.formula_changed),
        ({}, {K: "=E{r}"}, FE.FormulaEvidence.formula_added),
        ({}, {}, FE.FormulaEvidence.literal_changed),
    ],
)
def test_classification(base, incoming, expected) -> None:
    assert FE.classify_formula_evidence(base, incoming, K) is expected


def test_classification_values_are_distinct() -> None:
    assert len({e.value for e in FE.FormulaEvidence}) == 6


def test_unobserved_reason_is_the_pre_amendment_text_verbatim() -> None:
    """无证据时原因与修订前逐字相同（R1.4）—— 文案出自修订前 `merge.py` 受保护分支。"""
    assert FE.protected_conflict_reason("read_only_formula", FE.FormulaEvidence.unobserved) == (
        "受保护字段（read_only_formula）在 OO 侧被改动 —— 公式/auto-source 结果不得被覆盖（AC 6.6），"
        "incoming 值只用于篡改检测"
    )


@pytest.mark.parametrize(
    ("evidence", "needle"),
    [
        (FE.FormulaEvidence.formula_removed, "换成了数值"),
        (FE.FormulaEvidence.formula_changed, "被改写"),
        (FE.FormulaEvidence.formula_added, "写入了公式"),
        (FE.FormulaEvidence.literal_changed, "都没有读到公式"),
    ],
)
def test_tamper_reasons_name_what_happened(evidence, needle) -> None:
    reason = FE.protected_conflict_reason(
        "read_only_formula", evidence, base_signature="=E{r}", incoming_signature="=E{r}+1"
    )
    assert needle in reason and "AC 6.6" in reason


def test_drift_reason_names_the_first_difference() -> None:
    reason = FE.recompute_drift_reason("rows/r2/remark")
    assert "rows/r2/remark" in reason and "R1.2" in reason


# ── 签名并集与同列公式族 ──────────────────────────────────────────────────────


def test_union_of_signatures() -> None:
    parts = [
        SimpleNamespace(formula_signatures={"a/r1/x": "=A{r}"}),
        SimpleNamespace(formula_signatures=None),  # 转置表这类不提供证据的 part
        SimpleNamespace(formula_signatures={"b/r1/y": "=B{r}"}),
    ]
    assert FE.union_formula_signatures(parts) == {"a/r1/x": "=A{r}", "b/r1/y": "=B{r}"}
    assert FE.union_formula_signatures([SimpleNamespace(formula_signatures=None)]) is None
    assert FE.union_formula_signatures([SimpleNamespace(formula_signatures={})]) == {}


def test_template_key() -> None:
    assert FE.template_key("rows/dr-1/end_balance", "dr-1") == "rows/{row_uuid}/end_balance"
    assert FE.template_key("summary/total", None) is None
    assert FE.template_key("rows/dr-1/end_balance", "dr-9") is None


class _Proj:
    def __init__(self, row_of: dict[str, str]) -> None:
        self._row_of = row_of

    def get(self, key: str):
        row = self._row_of.get(key)
        return None if row is None else SimpleNamespace(row_key=row)


def test_new_row_formula_must_match_its_column() -> None:
    base_sigs = {
        "rows/r1/end_balance": "=E{r}+O{r}-P{r}",
        "rows/r2/end_balance": "=E{r}+O{r}-P{r}",
        "rows/r1/current_unadjusted": "=Q{r}+R{r}",
    }
    families = FE.formula_families(
        base_sigs, _Proj({k: k.split("/")[1] for k in base_sigs})
    )
    assert families["rows/{row_uuid}/end_balance"] == frozenset({"=E{r}+O{r}-P{r}"})
    new = {"rows/n1/end_balance": "=E{r}+O{r}-P{r}", "rows/n1/current_unadjusted": "=Q{r}"}
    assert FE.signature_in_family(new, "rows/n1/end_balance", "n1", families) is True
    # 同一行另一列的公式被改写 ⇒ 不属于本列公式族
    assert FE.signature_in_family(new, "rows/n1/current_unadjusted", "n1", families) is False
    # 新行这一格不是公式 / 没有证据
    assert FE.signature_in_family({}, "rows/n1/end_balance", "n1", families) is False
    assert FE.signature_in_family(None, "rows/n1/end_balance", "n1", families) is False
    # 静态字段没有「列」可比
    assert FE.signature_in_family({"total": "=SUM(A1:A9)"}, "total", None, families) is False
    assert FE.formula_families(None, _Proj({})) == {}
