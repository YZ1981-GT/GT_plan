# -*- coding: utf-8 -*-
"""「受保护字段」只有一个判定来源（spec oo-writeback-template-parity-closure R7）。

修前三处口径不同：`contracts.PROTECTED_MODES` 含 cross_sheet，`FieldValue.is_protected` 不含，
`merge._protection` 把 cross_sheet 当可编辑。落到 G3-1 / G11-1 的 25 格（模板里全是引用明细表
的公式）：OO 改了不报冲突、直接合并，物化时还按字面量写进公式格。

判据：
* 每个 FieldMode 下，契约字段、projection 字段、合并定位三处的「受保护」逐值相同；
* cross_sheet 走公式字段的规则：有签名且一致 ⇒ 采纳重算；没有证据 ⇒ 受保护冲突；
* 采纳的跨表重算值进 store 镜像；物化只写缓存值；
* 真契约 25 格逐格按公式字段定位；
* workpaper_sync 代码里不再单写 `mode is FieldMode.formula` 判「公式字段」（AST，登记一处例外）。
"""
from __future__ import annotations

import ast
import copy
import hashlib
import os
import sys
from pathlib import Path
from typing import Any, Mapping

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:  # pragma: no cover - import 环境自举
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.workpaper_sync import conflicts as CF  # noqa: E402
from app.services.workpaper_sync import contracts as C  # noqa: E402
from app.services.workpaper_sync import excel_materialize as XM  # noqa: E402
from app.services.workpaper_sync import merge as M  # noqa: E402
from app.services.workpaper_sync.adapters.base import FieldValue, Projection  # noqa: E402
from app.services.workpaper_sync.cleared_field_view import (  # noqa: E402
    RecomputedFieldValue,
    store_view_with_recomputed_formulas,
)

R1 = "11111111-1111-4111-8111-111111111111"
_SYNC_DIR = _BACKEND / "app" / "services" / "workpaper_sync"


def _d(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _field(leaf: str, column: str, mode: str) -> dict[str, Any]:
    return {
        "stable_field_key": f"rows/{{row_uuid}}/{leaf}",
        "json_pointer": f"/rows/{{row_uuid}}/{leaf}",
        "column_key": leaf,
        "cell": {"column": column, "row_from": "row_identity"},
        "mode": mode,
        "value_type": "amount",
        "source_ref": f"源xlsx!{column}8",
    }


_PAYLOAD: dict[str, Any] = {
    "schema_version": C.CONTRACT_SCHEMA_VERSION,
    "contract_id": "protected.single.source",
    "semantic_version": "1.0.0",
    "review_status": "reviewed",
    "document_type": "xlsx",
    "template_definition_sha256": _d("template-definition"),
    "instrumentation_definition_sha256": _d("instrumentation-definition"),
    "template": {
        "relative_path": "G/G3 应收股利.xlsx",
        "template_sha256": _d("template-blob"),
        "normalized_structure_hash": _d("template-structure"),
    },
    "identity_carriers": ["hidden_sheet", "defined_name", "hidden_uuid_column"],
    "sheets": [
        {
            "sheet_key": "g31-managed",
            "excel_name": "审定表G3-1",
            "locator": {"anchor": "defined_name_ref"},
            "tables": [
                {
                    "table_key": "rows",
                    "anchor": "A7",
                    "header_rows": 1,
                    "row_identity": {"kind": "field", "json_pointer": "/rows/*/rowUuid"},
                    "delete_policy": "tombstone",
                    "formula_mask": ["C8:C200"],
                    "fields": [
                        _field("opening", "B", "editable"),
                        _field("total", "C", "formula"),
                        _field("from_detail", "D", "cross_sheet"),
                        _field("tb_amount", "E", "auto_source"),
                    ],
                }
            ],
        }
    ],
}


def k(leaf: str) -> str:
    return f"rows/{R1}/{leaf}"


@pytest.fixture(scope="module")
def contract() -> C.SyncContract:
    return C.parse_contract(copy.deepcopy(_PAYLOAD))


def proj(contract, values: Mapping[str, Any], signatures: Mapping[str, str] | None) -> Projection:
    index = M.ContractIndex(contract)
    fields = {}
    for key, raw in values.items():
        loc = index.resolve(key)
        fields[key] = FieldValue(stable_key=key, value=raw, value_type=loc.value_type,
                                 mode=loc.mode, row_key=loc.row_key or None)
    return Projection(
        contract_id=contract.contract_id, semantic_version=contract.semantic_version,
        document_type=contract.document_type, values=fields, row_keys={"rows": (R1,)},
        formula_signatures=None if signatures is None else dict(signatures),
    )


BASE = {k("opening"): 100, k("total"): 100, k("from_detail"): 500, k("tb_amount"): 7}
SIG = {k("total"): "=B{r}", k("from_detail"): "='明细表G3-2'!C21"}


def merge3(contract, incoming, *, sig=SIG):
    return M.merge_projections(
        base=proj(contract, BASE, sig), current=proj(contract, BASE, sig),
        incoming=proj(contract, incoming, sig), contract=contract,
    )


# ── 三处口径逐值相同 ─────────────────────────────────────────────────────────


def test_formula_modes_partition() -> None:
    assert C.FORMULA_MODES == {C.FieldMode.formula, C.FieldMode.cross_sheet}
    assert C.PROTECTED_MODES - C.FORMULA_MODES == {C.FieldMode.auto_source}


@pytest.mark.parametrize("mode", list(C.FieldMode))
def test_three_definitions_agree(contract, mode: C.FieldMode) -> None:
    spec = C.FieldSpec(stable_field_key="x", json_pointer="/x", mode=mode,
                       value_type=C.ValueType.amount, source_ref="源xlsx!A1", row_scoped=False)
    fv = FieldValue(stable_key="x", value=1, value_type=C.ValueType.amount, mode=mode)
    template = M._FieldTemplate(spec=spec, sheet_key=None, sheet_excel_name=None,
                                table_key=None, formula_mask=())
    policy = M.ContractIndex._protection(template)
    expected = mode in C.PROTECTED_MODES
    assert spec.is_protected is expected
    assert fv.is_protected is expected
    assert policy.is_protected is expected, policy
    if mode in C.FORMULA_MODES:
        assert policy is CF.ProtectionPolicy.read_only_formula
        assert M.ContractIndex._field_source(spec, "xlsx") is CF.FieldSource.server_formula


# ── cross_sheet 走公式字段规则 ───────────────────────────────────────────────


def test_cross_sheet_recompute_is_taken(contract) -> None:
    outcome = merge3(contract, {**BASE, k("from_detail"): 800})
    assert outcome.conflict_count == 0, [r.reason for r in outcome.conflicts.records]
    assert outcome.verdicts[k("from_detail")] is M.FieldVerdict.took_recomputed
    view, keys = store_view_with_recomputed_formulas(outcome.merged, merge=outcome)
    assert keys == (k("from_detail"),)
    assert isinstance(view.get(k("from_detail")), RecomputedFieldValue)


def test_cross_sheet_change_without_evidence_is_protected_conflict(contract) -> None:
    outcome = merge3(contract, {**BASE, k("from_detail"): 800}, sig=None)
    assert outcome.verdicts[k("from_detail")] is M.FieldVerdict.conflict_protected
    (record,) = outcome.conflicts.records
    assert record.kind is CF.ConflictKind.protected
    assert outcome.value_of(k("from_detail")) == CF.ValueEnvelope.of(500)


def test_cross_sheet_formula_replaced_by_number_is_conflict(contract) -> None:
    sig_i = {k("total"): "=B{r}"}  # D 格没有公式了
    outcome = M.merge_projections(
        base=proj(contract, BASE, SIG), current=proj(contract, BASE, SIG),
        incoming=proj(contract, {**BASE, k("from_detail"): 800}, sig_i), contract=contract,
    )
    assert outcome.verdicts[k("from_detail")] is M.FieldVerdict.conflict_protected
    assert "换成了数值" in outcome.conflicts.records[0].reason


def test_cross_sheet_is_materialized_as_cached_value_only() -> None:
    spec = C.FieldSpec(stable_field_key="x", json_pointer="/x", mode=C.FieldMode.cross_sheet,
                       value_type=C.ValueType.amount, source_ref="源xlsx!A1", row_scoped=False)
    assert XM._write_kind_for(spec) is XM.CellWriteKind.cached_value_only


# ── 真契约 25 格 ────────────────────────────────────────────────────────────


@pytest.mark.parametrize("adapter_id", ["g3.dividend_receivable_detail", "g11.investment_income_detail"])
def test_real_cross_sheet_fields_locate_as_formula(adapter_id: str) -> None:
    contract = C.load_contract(adapter_id)
    index = M.ContractIndex(contract)
    cross = [t for t in index._templates if t.spec.mode is C.FieldMode.cross_sheet]
    assert len(cross) == {"g3.dividend_receivable_detail": 21, "g11.investment_income_detail": 4}[adapter_id]
    for template in cross:
        assert M.ContractIndex._protection(template) is CF.ProtectionPolicy.read_only_formula
        assert template.spec.is_protected


# ── 代码里不再单写 FieldMode.formula 判公式字段 ─────────────────────────────

#: (文件, 函数) → 只认本表公式的理由。
_ALLOWED: dict[tuple[str, str], str] = {
    ("contracts.py", "_parse_table"): "CS-13 只约束本表公式落在 formula_mask 内；cross_sheet 按 mode 受保护",
}


def _formula_only_compares() -> list[tuple[str, str, int]]:
    hits: list[tuple[str, str, int]] = []
    for path in sorted(_SYNC_DIR.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        parents: dict[ast.AST, ast.AST] = {}
        for node in ast.walk(tree):
            for child in ast.iter_child_nodes(node):
                parents[child] = node
        for node in ast.walk(tree):
            if not isinstance(node, ast.Compare):
                continue
            ops_ok = all(isinstance(op, (ast.Is, ast.IsNot, ast.Eq, ast.NotEq)) for op in node.ops)
            names = [c for c in node.comparators if isinstance(c, ast.Attribute)]
            if not ops_ok or not any(
                a.attr == "formula" and isinstance(a.value, ast.Name) and a.value.id == "FieldMode"
                for a in names
            ):
                continue
            func, cur = "<module>", node
            while cur in parents:
                cur = parents[cur]
                if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    func = cur.name
                    break
            hits.append((path.name, func, node.lineno))
    return hits


def test_no_bare_formula_mode_compare_outside_allowlist() -> None:
    offenders = [h for h in _formula_only_compares() if (h[0], h[1]) not in _ALLOWED]
    assert offenders == [], f"请改用 contracts.FORMULA_MODES：{offenders}"


def test_allowlist_entries_are_live() -> None:
    live = {(f, fn) for f, fn, _ in _formula_only_compares()}
    assert set(_ALLOWED) <= live, f"例外表有失效条目：{set(_ALLOWED) - live}"
