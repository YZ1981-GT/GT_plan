# -*- coding: utf-8 -*-
"""三方合并：OO 重算公式格不再当成篡改（spec oo-formula-recompute-not-tamper R1）。

═══ 修的是什么 ═══

用户在 D2-2 在线编辑里改借方发生 ⇒ OO 重算期末余额 / 期末未审 / 期末审定 ⇒ 这三格在 OO 一侧
「变了值」⇒ 修订前一律记受保护冲突（AC 6.6 / Property 24），整次保存进入冲突。真库 351 条受保护
冲突全是这一形态（最新一条 `7cdfbe36`：base 1000 / current 1000 / incoming 2500）。

═══ 判据 ═══

* 公式签名两侧相同 + 输入一致 ⇒ `took_recomputed`，merged 取 OO 一侧、零冲突、不要求重载；
* 输入不一致（current 独有改动 / 任何冲突 / 搁置）⇒ 仍是 protected 冲突，原因写明；
* 公式被换成数值 / 被改写 / 数值格写入公式 / 只读数值格被改 ⇒ protected 冲突，原因分别写明；
* 没有证据 ⇒ 与修订前逐字相同；自动取数精确比较不变；R10 尾差不变；
* OO 新增行的公式属于同列公式族 ⇒ `took_recomputed`（merged 与修订前同为 incoming）；
* R1.7：新规则下的冲突集合 ⊆ 修订前的冲突集合，修订前不冲突的键 merged 值逐个不变（穷举）。
"""
from __future__ import annotations

import copy
import hashlib
import itertools
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
from app.services.workpaper_sync import formula_recompute_evidence as FE  # noqa: E402
from app.services.workpaper_sync import merge as M  # noqa: E402
from app.services.workpaper_sync.adapters.base import FieldValue, Projection  # noqa: E402

R1 = "11111111-1111-4111-8111-111111111111"
R2 = "22222222-2222-4222-8222-222222222222"
NEW = "33333333-3333-4333-8333-333333333333"
EB_SIG = "=H{r}+M{r}-N{r}"


def _d(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _field(leaf: str, column: str, mode: str, value_type: str) -> dict[str, Any]:
    return {
        "stable_field_key": f"rows/{{row_uuid}}/{leaf}",
        "json_pointer": f"/rows/{{row_uuid}}/{leaf}",
        "column_key": leaf,
        "cell": {"column": column, "row_from": "row_identity"},
        "mode": mode,
        "value_type": value_type,
        "source_ref": f"源xlsx!{column}8",
    }


_PAYLOAD: dict[str, Any] = {
    "schema_version": C.CONTRACT_SCHEMA_VERSION,
    "contract_id": "recompute.fixture",
    "semantic_version": "1.0.0",
    "review_status": "reviewed",
    "document_type": "xlsx",
    "template_definition_sha256": _d("template-definition"),
    "instrumentation_definition_sha256": _d("instrumentation-definition"),
    "template": {
        "relative_path": "D/D2 应收账款.xlsx",
        "template_sha256": _d("template-blob"),
        "normalized_structure_hash": _d("template-structure"),
    },
    "identity_carriers": ["hidden_sheet", "defined_name", "hidden_uuid_column"],
    "sheets": [
        {
            "sheet_key": "d22-managed",
            "excel_name": "明细表D2-2",
            "locator": {"anchor": "defined_name_ref"},
            "tables": [
                {
                    "table_key": "rows",
                    "anchor": "A7",
                    "header_rows": 2,
                    "row_identity": {"kind": "field", "json_pointer": "/rows/*/rowUuid"},
                    "delete_policy": "tombstone",
                    "formula_mask": ["I8:I200", "K8:K200"],
                    "fields": [
                        _field("company_code", "G", "editable", "text"),
                        _field("opening", "H", "editable", "amount"),
                        _field("end_balance", "I", "formula", "amount"),
                        _field("tb_amount", "J", "auto_source", "amount"),
                        _field("masked_amount", "K", "editable", "amount"),
                    ],
                }
            ],
        }
    ],
}


def k(leaf: str, row: str = R1) -> str:
    return f"rows/{row}/{leaf}"


@pytest.fixture(scope="module")
def contract() -> C.SyncContract:
    return C.parse_contract(copy.deepcopy(_PAYLOAD))


def proj(
    contract: C.SyncContract,
    values: Mapping[str, Any],
    signatures: Mapping[str, str] | None = None,
) -> Projection:
    index = M.ContractIndex(contract)
    fields: dict[str, FieldValue] = {}
    rows: list[str] = []
    for key, raw in values.items():
        loc = index.resolve(key)
        fields[key] = FieldValue(
            stable_key=key, value=raw, value_type=loc.value_type, mode=loc.mode,
            row_key=loc.row_key or None,
        )
        if loc.row_key and loc.row_key not in rows:
            rows.append(loc.row_key)
    return Projection(
        contract_id=contract.contract_id,
        semantic_version=contract.semantic_version,
        document_type=contract.document_type,
        values=fields,
        row_keys={"rows": tuple(rows)},
        formula_signatures=None if signatures is None else dict(signatures),
    )


SIG = {k("end_balance"): EB_SIG, k("masked_amount"): "=SUM(A{r}:B{r})"}
BASE = {k("company_code"): "C1", k("opening"): 100, k("end_balance"): 1000, k("masked_amount"): 10}


def merge3(contract, base, current, incoming, *, sig_b=SIG, sig_c=SIG, sig_i=SIG, **kw):
    return M.merge_projections(
        base=proj(contract, base, sig_b),
        current=proj(contract, current, sig_c),
        incoming=proj(contract, incoming, sig_i),
        contract=contract,
        **kw,
    )


# ── R1.1 采纳重算 ───────────────────────────────────────────────────────────


def test_d2_amount_edit_is_taken_as_recompute(contract) -> None:
    """真栈形态：只改输入（opening），OO 重算 end_balance ⇒ 零冲突、采纳 2500、不必重载。"""
    incoming = {**BASE, k("opening"): 1600, k("end_balance"): 2500}
    outcome = merge3(contract, BASE, BASE, incoming)
    assert outcome.conflict_count == 0, [r.reason for r in outcome.conflicts.records]
    assert outcome.verdicts[k("end_balance")] is M.FieldVerdict.took_recomputed
    assert outcome.verdicts[k("opening")] is M.FieldVerdict.took_incoming
    assert outcome.value_of(k("end_balance")) == CF.ValueEnvelope.of(2500)
    assert k("end_balance") in outcome.auto_merged_keys
    assert outcome.requires_client_refresh(proj(contract, incoming, SIG)) is False
    assert not M.FieldVerdict.took_recomputed.is_conflict


def test_masked_cell_recompute_is_taken(contract) -> None:
    incoming = {**BASE, k("masked_amount"): 77}
    outcome = merge3(contract, BASE, BASE, incoming)
    assert outcome.conflict_count == 0
    assert outcome.verdicts[k("masked_amount")] is M.FieldVerdict.took_recomputed
    assert outcome.value_of(k("masked_amount")) == CF.ValueEnvelope.of(77)


def test_r10_tail_is_still_kept_current_with_evidence(contract) -> None:
    incoming = {**BASE, k("end_balance"): 1000.0000000001}
    outcome = merge3(contract, BASE, BASE, incoming)
    assert outcome.verdicts[k("end_balance")] is M.FieldVerdict.kept_current
    assert outcome.value_of(k("end_balance")) == CF.ValueEnvelope.of(1000)


# ── R1.2 输入不一致 ─────────────────────────────────────────────────────────


def _assert_drift(outcome, expected_drift_key: str) -> None:
    record = next(r for r in outcome.conflicts.records if r.locator.stable_field_key == k("end_balance"))
    assert record.kind is CF.ConflictKind.protected
    assert record.suggested_action is CF.SuggestedAction.keep_current
    assert "R1.2" in record.reason and expected_drift_key in record.reason
    assert outcome.verdicts[k("end_balance")] is M.FieldVerdict.conflict_protected
    assert outcome.value_of(k("end_balance")) == CF.ValueEnvelope.of(1000)


def test_current_only_edit_blocks_the_recompute(contract) -> None:
    """服务器侧在 OO 编辑期间改了 company_code ⇒ OO 的输入不是合并后的输入。"""
    current = {**BASE, k("company_code"): "C2"}
    incoming = {**BASE, k("opening"): 1600, k("end_balance"): 2500}
    outcome = merge3(contract, BASE, current, incoming)
    _assert_drift(outcome, k("company_code"))
    assert outcome.value_of(k("company_code")) == CF.ValueEnvelope.of("C2")


def test_any_other_conflict_blocks_the_recompute(contract) -> None:
    current = {**BASE, k("opening"): 200}
    incoming = {**BASE, k("opening"): 1600, k("end_balance"): 2500}
    outcome = merge3(contract, BASE, current, incoming)
    _assert_drift(outcome, k("opening"))
    kinds = sorted(r.kind.value for r in outcome.conflicts.records)
    assert kinds == ["protected", "value"]


def test_current_side_formula_change_blocks_the_recompute(contract) -> None:
    """R10 判 kept_current 但 current ≠ base（服务器侧重算过）⇒ 也算输入不一致。"""
    current = {**BASE, k("end_balance"): 1200}
    incoming = {**BASE, k("end_balance"): 1000.0000000001, k("masked_amount"): 77}
    outcome = merge3(contract, BASE, current, incoming)
    record = next(r for r in outcome.conflicts.records if r.locator.stable_field_key == k("masked_amount"))
    assert "R1.2" in record.reason and k("end_balance") in record.reason
    assert outcome.value_of(k("masked_amount")) == CF.ValueEnvelope.of(10)


def test_schema_anomaly_blocks_the_recompute(contract) -> None:
    anomaly = M.StructuralAnomaly(
        kind=CF.SchemaAnomalyKind.type_normalization_failure,
        stable_field_key=k("company_code", R2),
        detail="另一行的公司代码读不成文本（夹具）",
        row_key=R2,
        table_key="rows",
        oo_location="明细表D2-2!G9",
        blocks_stable_keys=(k("company_code", R2),),
    )
    incoming = {**BASE, k("opening"): 1600, k("end_balance"): 2500}
    outcome = merge3(contract, BASE, BASE, incoming, structural_anomalies=[anomaly])
    _assert_drift(outcome, k("company_code", R2))


def test_a_held_row_without_a_conflict_record_blocks_the_recompute(contract) -> None:
    """搁置也算输入不一致（R1.2），即使那一行没留下任何冲突记录。

    OO 删了 R2、服务器侧只填了 R2 原本空的「期初」⇒ R2 整行搁置在 current，但 `_row_conflict_for`
    只给 base 有值的改动格出 delete_update 冲突，这里一条都没有。合并结果保留了 R2、OO 一侧没有它 ——
    只看「current 独有改动 + 冲突」会放过这一形态（磁盘变异 M1e 存活过）。
    """
    base = {**BASE, k("company_code", R2): "D"}
    current = {**base, k("opening", R2): 9}
    incoming = {**BASE, k("opening"): 1600, k("end_balance"): 2500}  # R2 已被 OO 删掉
    outcome = merge3(contract, base, current, incoming)
    assert outcome.verdicts[k("opening", R2)] is M.FieldVerdict.held_by_row_conflict
    assert outcome.verdicts[k("company_code", R2)] is M.FieldVerdict.held_by_row_conflict
    [record] = outcome.conflicts.records
    assert record.locator.stable_field_key == k("end_balance")
    assert record.kind is CF.ConflictKind.protected and "R1.2" in record.reason and R2 in record.reason
    assert outcome.value_of(k("end_balance")) == CF.ValueEnvelope.of(1000)


# ── R1.3 / R1.4 / R1.5 篡改与无证据 ─────────────────────────────────────────


@pytest.mark.parametrize(
    ("sig_b", "sig_i", "needle"),
    [
        ({k("end_balance"): EB_SIG}, {}, "换成了数值"),
        ({k("end_balance"): EB_SIG}, {k("end_balance"): EB_SIG + "+1"}, "被改写"),
        ({}, {k("end_balance"): EB_SIG}, "写入了公式"),
        ({}, {}, "都没有读到公式"),
    ],
)
def test_tamper_is_still_a_protected_conflict(contract, sig_b, sig_i, needle) -> None:
    incoming = {**BASE, k("end_balance"): 2500}
    outcome = merge3(contract, BASE, BASE, incoming, sig_b=sig_b, sig_i=sig_i)
    [record] = outcome.conflicts.records
    assert record.kind is CF.ConflictKind.protected and needle in record.reason
    assert record.suggested_action is CF.SuggestedAction.keep_current
    assert outcome.value_of(k("end_balance")) == CF.ValueEnvelope.of(1000)


@pytest.mark.parametrize(("sig_b", "sig_i"), [(None, SIG), (SIG, None), (None, None)])
def test_no_evidence_is_the_pre_amendment_behaviour(contract, sig_b, sig_i) -> None:
    incoming = {**BASE, k("opening"): 1600, k("end_balance"): 2500}
    outcome = merge3(contract, BASE, BASE, incoming, sig_b=sig_b, sig_i=sig_i)
    [record] = outcome.conflicts.records
    assert record.reason == FE.protected_conflict_reason(
        "read_only_formula", FE.FormulaEvidence.unobserved
    )
    assert "incoming 值只用于篡改检测" in record.reason


def test_auto_source_keeps_exact_comparison_even_with_equal_signatures(contract) -> None:
    sig = {**SIG, k("tb_amount"): "=X{r}"}
    base = {**BASE, k("tb_amount"): 5}
    outcome = merge3(contract, base, base, {**base, k("tb_amount"): 6}, sig_b=sig, sig_c=sig, sig_i=sig)
    [record] = outcome.conflicts.records
    assert record.locator.protection_policy is CF.ProtectionPolicy.read_only_auto_source
    assert "incoming 值只用于篡改检测" in record.reason


# ── R1.6 OO 新增行 ──────────────────────────────────────────────────────────


def _new_row(**over: Any) -> dict[str, Any]:
    return {k("company_code", NEW): "N", k("opening", NEW): 1, k("end_balance", NEW): 5, **over}


@pytest.mark.parametrize(
    ("new_sig", "current_extra", "expected"),
    [
        (EB_SIG, {}, M.FieldVerdict.took_recomputed),  # 本列公式族
        ("=H{r}*2", {}, M.FieldVerdict.took_incoming),  # 不是本列公式
        ("=SUM(A{r}:B{r})", {}, M.FieldVerdict.took_incoming),  # 别的列（遮罩列）的公式（变异 E7 存活过）
        (None, {}, M.FieldVerdict.took_incoming),  # 新行这一格不是公式
        (EB_SIG, {k("company_code"): "C2"}, M.FieldVerdict.took_incoming),  # 输入不一致
    ],
)
def test_new_row_formula(contract, new_sig, current_extra, expected) -> None:
    sig_i = {**SIG, **({} if new_sig is None else {k("end_balance", NEW): new_sig})}
    outcome = merge3(
        contract, BASE, {**BASE, **current_extra}, {**BASE, **_new_row()}, sig_i=sig_i
    )
    assert outcome.verdicts[k("end_balance", NEW)] is expected
    # merged 值与修订前相同：一律 incoming
    assert outcome.value_of(k("end_balance", NEW)) == CF.ValueEnvelope.of(5)


def test_new_row_without_base_evidence_is_unchanged(contract) -> None:
    sig_i = {**SIG, k("end_balance", NEW): EB_SIG}
    outcome = merge3(contract, BASE, BASE, {**BASE, **_new_row()}, sig_b=None, sig_c=None, sig_i=sig_i)
    assert outcome.verdicts[k("end_balance", NEW)] is M.FieldVerdict.took_incoming


def test_store_view_releases_only_recomputed_formula_fields(contract) -> None:
    """store 视图只放行「采纳重算」的公式字段（R3.1）：遮罩格是可编辑 mode，store 合并本就写它；
    took_incoming 的公式字段（OO 新增行里不属本列公式族的格）照旧受保护、不进 store
    （磁盘变异 V2「不看 mode」/ V2b「连 took_incoming 一起放」存活过）。"""
    from app.services.workpaper_sync.cleared_field_view import store_view_with_recomputed_formulas

    sig_i = {**SIG, k("end_balance", NEW): "=H{r}*2"}
    incoming = {**BASE, k("opening"): 1600, k("end_balance"): 2500, k("masked_amount"): 77, **_new_row()}
    outcome = merge3(contract, BASE, BASE, incoming, sig_i=sig_i)
    assert outcome.verdicts[k("masked_amount")] is M.FieldVerdict.took_recomputed
    assert outcome.verdicts[k("end_balance", NEW)] is M.FieldVerdict.took_incoming
    view, keys = store_view_with_recomputed_formulas(outcome.merged, merge=outcome)
    assert keys == (k("end_balance"),)
    assert view.get(k("end_balance")).is_protected is False
    assert view.get(k("end_balance", NEW)).is_protected is True
    assert type(view.get(k("masked_amount"))) is FieldValue


def test_new_row_masked_cell_keeps_the_pre_amendment_verdict(contract) -> None:
    """R1.6 只针对公式字段：新增行的遮罩格是可编辑 mode，修订前就是 took_incoming 并随之进 store，
    不改判（磁盘变异 M10c「新增行不看 mode」存活过）。"""
    sig_i = {**SIG, k("masked_amount", NEW): SIG[k("masked_amount")]}  # 与本列已有公式同签名
    incoming = {**BASE, **_new_row(**{k("masked_amount", NEW): 4})}
    outcome = merge3(contract, BASE, BASE, incoming, sig_i=sig_i)
    assert outcome.verdicts[k("masked_amount", NEW)] is M.FieldVerdict.took_incoming
    assert outcome.value_of(k("masked_amount", NEW)) == CF.ValueEnvelope.of(4)


# ── R1.7 只把冲突变成采纳，不把采纳变成冲突（穷举）──────────────────────────


_EB_SIDES = [1000, 2500]
_OPEN_SIDES = [100, 200, 1600]
_SIG_CASES = {
    "intact": (SIG, SIG),
    "changed": (SIG, {**SIG, k("end_balance"): EB_SIG + "+1"}),
    "removed": (SIG, {k("masked_amount"): SIG[k("masked_amount")]}),
    "none": (None, None),
}


def _strip(outcome_args: dict[str, Projection]) -> dict[str, Projection]:
    import dataclasses

    return {name: dataclasses.replace(p, formula_signatures=None) for name, p in outcome_args.items()}


def test_amendment_only_turns_conflicts_into_acceptance(contract) -> None:
    checked = 0
    for (eb_c, eb_i), (op_c, op_i), (sig_b, sig_i) in itertools.product(
        itertools.product(_EB_SIDES, repeat=2),
        itertools.product(_OPEN_SIDES, repeat=2),
        _SIG_CASES.values(),
    ):
        args = {
            "base": proj(contract, BASE, sig_b),
            "current": proj(contract, {**BASE, k("end_balance"): eb_c, k("opening"): op_c}, sig_b),
            "incoming": proj(contract, {**BASE, k("end_balance"): eb_i, k("opening"): op_i}, sig_i),
        }
        new = M.merge_projections(contract=contract, **args)
        old = M.merge_projections(contract=contract, **_strip(args))
        old_conflicts = {r.locator.stable_field_key for r in old.conflicts.records}
        new_conflicts = {r.locator.stable_field_key for r in new.conflicts.records}
        assert new_conflicts <= old_conflicts, (eb_c, eb_i, op_c, op_i, new_conflicts - old_conflicts)
        for key in set(old.verdicts) - old_conflicts:
            assert new.value_of(key) == old.value_of(key), (key, eb_c, eb_i, op_c, op_i)
        checked += 1
    assert checked == 4 * 9 * 4
