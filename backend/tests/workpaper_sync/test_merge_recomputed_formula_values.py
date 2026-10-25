# -*- coding: utf-8 -*-
"""OO 重算的受保护字段按「分」比较（spec d2-online-edit-platform-closure · R10）。

═══ 真栈缺陷 ═══

和平药房 D2-2 在 OnlyOffice 里改一格「公司代码」后保存，OO→HTML 直接落成
`state=conflict`，**108 条** `protected` 冲突 —— 全是公式字段（期末余额 / 本期未审数 /
本期审定数）。base/current 是 HTML 侧 JS 加减后存进 store 的值，incoming 是 OO 打开时
重算的值，两边都是二进制浮点、累加顺序不同：

    3511.0600000000004 vs 3511.06              （第 17 位）
    -368.0000000000018 vs -367.9999999999982   （第 13 位，多项累加）
    0                  vs -2.2737367544323206e-13（相消残差）

Property 24 的篡改检测用精确比较，把「OO 重算了一遍」当成「用户在 OO 里改了公式格」⇒
每次保存都要逐条裁决，双向回写整条不可用。第一版只吸收 15 位有效数字以外的尾差，
108 条降到 54 条（剩下的尾差落在第 12~14 位）；按分取整后全部消失。

═══ 判据 ═══

* OO 会重算的受保护字段（公式字段 / formula mask 里的格）：金额按分取整后相等 ⇒ 不是篡改，
  保留 current、零冲突、无需重载客户端；
* 没有公式证据时差一分及以上仍是 protected 冲突（spec oo-formula-recompute-not-tamper 修订：
  带公式证据时按 `test_merge_formula_recompute.py` 的判据区分重算与篡改）；
* auto-source 字段 OO 不重算，保持精确比较；
* 可编辑字段不走这条规则（OO 不重算它们，任何差异都是用户真改的）；
* 非金额数值（rate / ratio / percent_points）不按两位取整，只吸收 float 的 15 位以外尾差。
"""
from __future__ import annotations

import copy
import hashlib
import os
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:  # pragma: no cover - import 环境自举
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.workpaper_sync import conflicts as CF  # noqa: E402
from app.services.workpaper_sync import contracts as C  # noqa: E402
from app.services.workpaper_sync import merge as M  # noqa: E402
from app.services.workpaper_sync.adapters.base import FieldValue, Projection  # noqa: E402

ROW = "11111111-1111-4111-8111-111111111111"

#: 真栈 D2 实测样本（`working_paper_sync_conflict` 两轮冲突里逐字抄录：前 4 条是第一轮 108 条
#: 里的，后 5 条是只吸收 15 位尾差后仍剩的 54 条里的）。(base/current, incoming)
REAL_D2_TAILS: tuple[tuple[float, float], ...] = (
    (3511.0600000000004, 3511.06),
    (1263077.4699999983, 1263077.4700000002),
    (22647.92, 22647.920000000006),
    (6917.400000000001, 6917.4),
    (-303.1999999999998, -303.1999999999989),
    (8123.950000000012, 8123.95000000007),
    (-368.0000000000018, -367.9999999999982),
    (0, -2.2737367544323206e-13),
    (8201.000000000015, 8200.999999999985),
)


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
    "contract_id": "d2.recomputed.fixture",
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
                    # I / L 列 = 公式字段；K 列 = 落在 mask 里的 editable 金额格（受保护单元格）
                    "formula_mask": ["I8:I200", "K8:K200", "L8:L200"],
                    "fields": [
                        _field("company_code", "G", "editable", "text"),
                        _field("opening", "H", "editable", "amount"),
                        _field("end_balance", "I", "formula", "amount"),
                        _field("tb_amount", "J", "auto_source", "amount"),
                        _field("masked_amount", "K", "editable", "amount"),
                        _field("aging_rate", "L", "formula", "rate"),
                    ],
                }
            ],
        }
    ],
}


def _key(leaf: str) -> str:
    return f"rows/{ROW}/{leaf}"


@pytest.fixture(scope="module")
def contract() -> C.SyncContract:
    return C.parse_contract(copy.deepcopy(_PAYLOAD))


def _proj(contract: C.SyncContract, values: Mapping[str, Any]) -> Projection:
    index = M.ContractIndex(contract)
    fields: dict[str, FieldValue] = {}
    for key, raw in values.items():
        loc = index.resolve(key)
        fields[key] = FieldValue(
            stable_key=key,
            value=raw,
            value_type=loc.value_type,
            mode=loc.mode,
            row_key=loc.row_key or None,
        )
    return Projection(
        contract_id=contract.contract_id,
        semantic_version=contract.semantic_version,
        document_type=contract.document_type,
        values=fields,
        row_keys={},
    )


def _merge(
    contract: C.SyncContract, leaf: str, b: Any, c: Any, i: Any
) -> tuple[M.MergeOutcome, Projection]:
    key = _key(leaf)
    incoming = _proj(contract, {key: i})
    outcome = M.merge_projections(
        base=_proj(contract, {key: b}),
        current=_proj(contract, {key: c}),
        incoming=incoming,
        contract=contract,
    )
    return outcome, incoming


def test_fixture_policies_are_what_the_cases_assume(contract: C.SyncContract) -> None:
    """前提自检：各字段的保护策略恰是用例假设的那几种（否则下面的用例测错了对象）。"""
    index = M.ContractIndex(contract)
    got = {
        leaf: index.resolve(_key(leaf)).protection_policy
        for leaf in ("opening", "end_balance", "tb_amount", "masked_amount", "aging_rate")
    }
    assert got == {
        "opening": CF.ProtectionPolicy.editable,
        "end_balance": CF.ProtectionPolicy.read_only_formula,
        "tb_amount": CF.ProtectionPolicy.read_only_auto_source,
        "masked_amount": CF.ProtectionPolicy.read_only_masked_cell,
        "aging_rate": CF.ProtectionPolicy.read_only_formula,
    }


@pytest.mark.parametrize(("server", "recomputed"), REAL_D2_TAILS)
@pytest.mark.parametrize("leaf", ["end_balance", "masked_amount"])
def test_oo_recompute_tail_is_not_tamper(
    contract: C.SyncContract, leaf: str, server: float, recomputed: float
) -> None:
    """OO 重算出的同一个数（按分相等）⇒ 零冲突、保留 current、无需重载客户端。"""
    outcome, incoming = _merge(contract, leaf, server, server, recomputed)
    assert outcome.conflict_count == 0, [r.reason for r in outcome.conflicts.records]
    assert outcome.verdicts[_key(leaf)] is M.FieldVerdict.kept_current
    assert outcome.value_of(_key(leaf)) == CF.ValueEnvelope.of(server)
    assert outcome.requires_client_refresh(incoming) is False


@pytest.mark.parametrize("leaf", ["end_balance", "masked_amount"])
@pytest.mark.parametrize("tampered", [3511.07, 3511.05, "3511.07", 0.01])
def test_one_cent_is_a_real_tamper(contract: C.SyncContract, leaf: str, tampered: Any) -> None:
    """**没有公式证据时**差一分就按改了处理：仍是 protected 冲突，current 不被覆盖。

    🔴 判据修订（spec oo-formula-recompute-not-tamper R1.4）：原判据是「差一分就是篡改」，
    不分来源。修订后只在两侧 projection 不带公式签名时成立（本文件的 `_proj` 不带签名，
    即 Word / 非 xlsx 来源的形态）；带签名且公式完好、输入一致时差一分也是重算结果、应采纳 ——
    见 `test_merge_formula_recompute.py`。
    """
    outcome, _ = _merge(contract, leaf, 3511.0600000000004, 3511.0600000000004, tampered)
    assert [r.kind for r in outcome.conflicts.records] == [CF.ConflictKind.protected]
    assert outcome.value_of(_key(leaf)) == CF.ValueEnvelope.of(3511.0600000000004)


def test_auto_source_keeps_exact_tamper_detection(contract: C.SyncContract) -> None:
    """auto-source 是服务端写死的值、OO 不重算 ⇒ 精确比较一位都不放松。"""
    outcome, _ = _merge(contract, "tb_amount", 3511.0600000000004, 3511.0600000000004, 3511.06)
    assert [r.kind for r in outcome.conflicts.records] == [CF.ConflictKind.protected]


def test_editable_field_semantics_unchanged(contract: C.SyncContract) -> None:
    """可编辑字段不走这条规则：OO 侧的值照常采纳（与本修复无关的路径逐字不变）。"""
    outcome, _ = _merge(contract, "opening", 3511.0600000000004, 3511.0600000000004, 3511.06)
    assert outcome.conflict_count == 0
    assert outcome.verdicts[_key("opening")] is M.FieldVerdict.took_incoming
    assert outcome.value_of(_key("opening")) == CF.ValueEnvelope.of(3511.06)


def test_editable_sub_cent_edit_is_not_swallowed(contract: C.SyncContract) -> None:
    """可编辑格的「不到一分」改动也是用户真改的：照常采纳，不被按两位取整吞掉。"""
    outcome, _ = _merge(contract, "opening", 100.0, 100.0, 100.004)
    assert outcome.verdicts[_key("opening")] is M.FieldVerdict.took_incoming
    assert outcome.value_of(_key("opening")) == CF.ValueEnvelope.of(100.004)


def test_rate_is_not_rounded_to_two_decimals(contract: C.SyncContract) -> None:
    """费率不按两位取整：0.1234 → 0.1239 是两个费率，必须仍报 protected 冲突。"""
    outcome, _ = _merge(contract, "aging_rate", 0.1234, 0.1234, 0.1239)
    assert [r.kind for r in outcome.conflicts.records] == [CF.ConflictKind.protected]


def test_rate_float_tail_is_absorbed(contract: C.SyncContract) -> None:
    """费率的二进制尾差（15 位有效数字以外）仍不算篡改。"""
    outcome, _ = _merge(contract, "aging_rate", 0.30000000000000004, 0.30000000000000004, 0.3)
    assert outcome.conflict_count == 0


def test_refresh_still_required_for_a_real_difference(contract: C.SyncContract) -> None:
    """refresh 判据只放过不到一分的差：差一分照旧要求客户端重载。"""
    key = _key("end_balance")
    settled = _proj(contract, {key: 3511.0600000000004})
    incoming = _proj(contract, {key: 3511.07})
    assert (
        M.projection_requires_client_refresh(
            settled=settled, incoming=incoming, word_only_keys=()
        )
        is True
    )


@pytest.mark.parametrize(
    ("left", "right", "value_type", "expected"),
    [
        (3511.0600000000004, 3511.06, C.ValueType.amount, True),
        (-368.0000000000018, -367.9999999999982, C.ValueType.amount, True),
        (0, -2.2737367544323206e-13, C.ValueType.amount, True),
        (Decimal("3511.0600000000004"), "3511.06", C.ValueType.amount, True),
        (2408, 2408.0, C.ValueType.amount, True),
        (3511.06, 3511.07, C.ValueType.amount, False),
        (0.004, 0.006, C.ValueType.amount, False),
        (None, 0.0, C.ValueType.amount, False),
        (0.30000000000000004, 0.3, C.ValueType.rate, True),
        (0.1234, 0.1239, C.ValueType.rate, False),
        (Decimal("0.30000000000000004"), Decimal("0.3"), C.ValueType.rate, False),
        ("3511.06", "3511.06", C.ValueType.text, False),
    ],
)
def test_recomputed_values_equal_table(
    left: Any, right: Any, value_type: Any, expected: bool
) -> None:
    assert M.recomputed_values_equal(left, right, value_type) is expected
