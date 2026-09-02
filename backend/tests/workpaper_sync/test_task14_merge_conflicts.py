# -*- coding: utf-8 -*-
"""Task 14 守卫：stable-field 三方 merge 与冲突 domain。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 1 Task 14
Requirements: 6.6, 6.7, 6.8, 6.9, 7.4, 8.1, 8.5
Properties: **P24**（保护字段修改形成冲突）/ **P25**（不同字段自动三方合并）/
**P26**（同字段异值必冲突）/ **P27**（delete/update 冲突不整表覆盖）/
**P32**（Word 多实例异值冲突）/ **P35**（冲突记录双侧可追溯）

═══ 判据落在哪 ═══

* **真值表落在真实执行上**：`TestThreeWayTruthTable` 把模块 docstring 里那张九行表
  参数化成 `(b, c, i) → (verdict, merged)`，逐行跑 `merge_projections`。不是「源码里有
  没有这个分支」，而是「这组输入真的走到了这一行」。
* **MISSING 非折叠用反例证明**：`i=MISSING`（行/载体被删）与 `i=None`（在 OO 里清空）
  必须产出**不同**的 merged。若有人把 MISSING 折叠成 None，这条立刻打红 ——
  否定式承诺（「永不折叠」）无法用短路变异证明，只能用反例（变异脚本 M21/M22 做注入）。
* **「不自动选边」同理**：`TestProperty26` 断言 merged 等于 current 且**不等于**
  incoming，`apply_resolutions` 缺裁决必抛；变异脚本往冲突分支注入 `return incoming`
  （M23）来证明判据可 falsify。
* **异常类型两两不遮蔽**：受保护覆盖 / 结构不可裁决 / 实例未指定 / 目标不存在四条
  拒绝路径抛四种互不继承的异常，`test_four_rejection_types_are_pairwise_distinct`
  双向断言。Task 12/13 实测的最贵一类假绿正是「同类型异常互相遮蔽」。
* **落库形态与 DB 双向锁死**：`ConflictKind` 逐字对 V151 的 `ck_wpsc_conflict_kind`
  CHECK，`to_row()` 逐列对 `WorkpaperSyncConflict` 的 ORM 列。

═══ 本任务边界 ═══

`TestTask14ScopeBoundary`：零 openpyxl/python-docx、零 sqlalchemy/repository/outbox、
零 commit 面；仍未接线的能力必须带 `blocking_task` 登记在 `DEFERRED_CONSUMERS` 里。

**2026-08-26 更新（Task 15 落地）**：`merge_projections / MergeOutcome` 那条延后已退役。
边界判据随之**翻转而不是删除** —— 从「零生产消费方」变成「恰一个生产消费方，且正是
`RETIRED_DEFERRALS` 登记的那个模块（`content_mutation.py`）」。多一个消费方（有人绕过
唯一 commit 入口）与零消费方（有人把接线删了、能力退回死代码）都打红。
"""

from __future__ import annotations

import copy
import hashlib
import os
import pickle
import re
import sys
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Final, Mapping

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:  # pragma: no cover - import 环境自举
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.workpaper_sync import conflicts as CF  # noqa: E402
from app.services.workpaper_sync import contracts as C  # noqa: E402
from app.services.workpaper_sync import merge as M  # noqa: E402
from app.services.workpaper_sync.adapters.base import FieldValue, Projection  # noqa: E402
from app.services.workpaper_sync.models import (  # noqa: E402
    OperationScope,
    OperationState,
    SyncDomainError,
)

_SYNC_DIR = _BACKEND / "app" / "services" / "workpaper_sync"
_MERGE_PY = _SYNC_DIR / "merge.py"
_CONFLICTS_PY = _SYNC_DIR / "conflicts.py"
_V151 = _BACKEND / "migrations" / "V151__workpaper_sync_content_application_bundle_scope.sql"

# 双哨兵：单哨兵会被历史空目录骗停。
assert (_BACKEND / "app" / "main.py").is_file(), "哨兵失效：backend/app/main.py 不存在"
assert _V151.is_file(), f"哨兵失效：{_V151} 不存在"

#: 属性检验样本量。判据是纯函数、单例 <1ms，平台 PBT 默认的 `max_examples=5` 对
#: 「任意合法值下不变式仍成立」这种全称命题几乎等于定向测试，故本文件取 60
#: （全部四条属性实测合计 <1s）。
_HYP = settings(max_examples=60, deadline=None)


# ═══════════════════════════════════════════════════════════════════════════
# 0. 契约与 projection 构造器
# ═══════════════════════════════════════════════════════════════════════════


def _d(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


TEMPLATE_DEF = _d("template-definition")
INSTR_DEF = _d("instrumentation-definition")

R1 = "11111111-1111-4111-8111-111111111111"
R2 = "22222222-2222-4222-8222-222222222222"
R3 = "33333333-3333-4333-8333-333333333333"

XKEY = "equity_changes/{row}/{leaf}"


def ek(row: str, leaf: str) -> str:
    """行域 stable key（已实例化）。"""
    return f"equity_changes/{row}/{leaf}"


PERIOD = "header_block/period_label"
TOTAL = "header_block/total_amount"


def xlsx_payload(contract_id: str = "g7.disclosure.listed") -> dict[str, Any]:
    """一份合法 xlsx 契约：动态行 + 两级表头 + formula mask + footer + 动态列。

    刻意覆盖四种保护策略：`editable` / `formula` / `auto_source` /
    **mask 覆盖的 editable 格**（第四种是 AC 6.6 的「受保护单元格」，与前两种是
    独立判据 —— 契约层只校验「formula 字段必须在 mask 内」的正向，没有反向）。
    """
    return {
        "schema_version": C.CONTRACT_SCHEMA_VERSION,
        "contract_id": contract_id,
        "semantic_version": "1.0.0",
        "review_status": "reviewed",
        "document_type": "xlsx",
        "template_definition_sha256": TEMPLATE_DEF,
        "instrumentation_definition_sha256": INSTR_DEF,
        "template": {
            "relative_path": "G/G7 权益工具投资.xlsx",
            "template_sha256": _d("template-blob"),
            "normalized_structure_hash": _d("template-structure"),
        },
        "identity_carriers": ["hidden_sheet", "defined_name", "hidden_uuid_column"],
        "sheets": [
            {
                "sheet_key": "g7-disclosure",
                "excel_name": "G7 披露表",
                "locator": {"anchor": "defined_name_ref"},
                "tables": [
                    {
                        "table_key": "equity_changes",
                        "anchor": "A7",
                        "header_rows": 2,
                        "row_identity": {"kind": "field", "json_pointer": "/rows/*/rowUuid"},
                        "delete_policy": "tombstone",
                        "dynamic_columns": {
                            "identity": "{slot}_{seq}",
                            "source_ref": "源xlsx!B6:Z6",
                        },
                        "footer_anchor": {"marker": "合计", "search_column": "A"},
                        "formula_mask": ["I8:I200", "K8:K200"],
                        "fields": [
                            {
                                "stable_field_key": "equity_changes/{row_uuid}/name",
                                "json_pointer": "/rows/{row_uuid}/name",
                                "column_key": "name",
                                "cell": {"column": "G", "row_from": "row_identity"},
                                "mode": "editable",
                                "value_type": "text",
                                "source_ref": "源xlsx!G8",
                            },
                            {
                                "stable_field_key": "equity_changes/{row_uuid}/closing_amount",
                                "json_pointer": "/rows/{row_uuid}/closingAmount",
                                "column_key": "closing_amount",
                                "cell": {"column": "H", "row_from": "row_identity"},
                                "mode": "editable",
                                "value_type": "amount",
                                "source_ref": "源xlsx!H8",
                            },
                            {
                                "stable_field_key": "equity_changes/{row_uuid}/subtotal",
                                "json_pointer": "/rows/{row_uuid}/subtotal",
                                "column_key": "subtotal",
                                "cell": {"column": "I", "row_from": "row_identity"},
                                "mode": "formula",
                                "value_type": "amount",
                                "source_ref": "源xlsx!I8",
                            },
                            {
                                "stable_field_key": "equity_changes/{row_uuid}/tb_amount",
                                "json_pointer": "/rows/{row_uuid}/tbAmount",
                                "column_key": "tb_amount",
                                "cell": {"column": "J", "row_from": "row_identity"},
                                "mode": "auto_source",
                                "value_type": "amount",
                                "source_ref": "源xlsx!J8",
                            },
                            {
                                "stable_field_key": "equity_changes/{row_uuid}/masked_note",
                                "json_pointer": "/rows/{row_uuid}/maskedNote",
                                "column_key": "masked_note",
                                "cell": {"column": "K", "row_from": "row_identity"},
                                "mode": "editable",
                                "value_type": "text",
                                "source_ref": "源xlsx!K8",
                            },
                        ],
                    },
                    {
                        "table_key": "header_block",
                        "anchor": "A1",
                        "header_rows": 1,
                        "fields": [
                            {
                                "stable_field_key": "header_block/period_label",
                                "json_pointer": "/header/periodLabel",
                                "column_key": "period_label",
                                "cell": {"column": "B", "row_from": 2},
                                "mode": "editable",
                                "value_type": "text",
                                "source_ref": "源xlsx!B2",
                            },
                            {
                                "stable_field_key": "header_block/total_amount",
                                "json_pointer": "/header/totalAmount",
                                "column_key": "total_amount",
                                "cell": {"column": "C", "row_from": 3},
                                "mode": "editable",
                                "value_type": "amount",
                                "source_ref": "源xlsx!C3",
                            },
                        ],
                    },
                ],
            }
        ],
    }


def docx_payload(contract_id: str = "f2.stocktake.plan") -> dict[str, Any]:
    return {
        "schema_version": C.CONTRACT_SCHEMA_VERSION,
        "contract_id": contract_id,
        "semantic_version": "1.0.0-sdt1",
        "review_status": "reviewed",
        "document_type": "docx",
        "template_definition_sha256": TEMPLATE_DEF,
        "instrumentation_definition_sha256": INSTR_DEF,
        "template": {
            "relative_path": "F/F2 存货监盘计划.docx",
            "template_sha256": _d("docx-blob"),
            "normalized_structure_hash": _d("docx-structure"),
        },
        "identity_carriers": ["field_sdt_inline", "cell_level_field_sdt_tag_carrying_row_uuid"],
        "fields": [
            {
                "stable_field_key": "plan/location",
                "json_pointer": "/plan/location",
                "sdt_tag": f"gt:field:{contract_id}:plan/location",
                "mode": "editable",
                "value_type": "text",
                "source_ref": "源docx!监盘地点",
                "instances": "many",
            },
            {
                "stable_field_key": "plan/free_notes",
                "json_pointer": "/plan/freeNotes",
                "sdt_tag": f"gt:field:{contract_id}:plan/free_notes",
                "mode": "word_only",
                "value_type": "text",
                "source_ref": "源docx!补充说明",
            },
        ],
        "repeaters": [
            {
                "stable_field_key": "plan/members/{row_uuid}/name",
                "json_pointer": "/plan/members/{row_uuid}/name",
                "sdt_tag": f"gt:field:{contract_id}:plan/members/{{row_uuid}}/name",
                "mode": "editable",
                "value_type": "text",
                "source_ref": "源docx!监盘人员表",
                "instances": "many",
            }
        ],
    }


@pytest.fixture(scope="module")
def xc() -> C.SyncContract:
    return C.parse_contract(xlsx_payload())


@pytest.fixture(scope="module")
def dc() -> C.SyncContract:
    return C.parse_contract(docx_payload())


def proj(
    contract: C.SyncContract,
    values: Mapping[str, Any],
    *,
    row_keys: Mapping[str, tuple[str, ...]] | None = None,
) -> Projection:
    """按 stable key → 原值构造 projection；mode/value_type 从契约取（单一真源）。

    `M.MISSING` 作为值表示「不写这个键」—— 用它来书写反例更贴近语义。
    """
    index = M.ContractIndex(contract)
    fields: dict[str, FieldValue] = {}
    for key, raw in values.items():
        if raw is M.MISSING:
            continue
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
        row_keys=dict(row_keys or {}),
    )


def row_values(row: str, *, name: str, closing: Any, subtotal: Any = None) -> dict[str, Any]:
    out: dict[str, Any] = {ek(row, "name"): name, ek(row, "closing_amount"): closing}
    if subtotal is not None:
        out[ek(row, "subtotal")] = subtotal
    return out


def single(contract: C.SyncContract, b: Any, c: Any, i: Any, key: str = TOTAL):
    """把一组 (base, current, incoming) 值跑成一次 merge —— 真值表的最小执行体。"""
    return M.merge_projections(
        base=proj(contract, {key: b}),
        current=proj(contract, {key: c}),
        incoming=proj(contract, {key: i}),
        contract=contract,
    )


def _read(path: Path) -> str:
    assert path.is_file(), f"文件不存在: {path}"
    return path.read_text(encoding="utf-8")


def _stripped(path: Path) -> str:
    """剥注释/docstring —— 防「说明文字里的反例」被数成真实代码（Task 13 实测过的假红）。"""
    sys.path.insert(0, str(_BACKEND / "scripts" / "gen"))
    from generate_workpaper_resolver_migration_matrix import (  # noqa: PLC0415
        strip_comments_and_docstrings,
    )

    return strip_comments_and_docstrings(_read(path))


# ═══════════════════════════════════════════════════════════════════════════
# 1. MISSING 哨兵：与 None / "" / 0 / False 永不折叠
# ═══════════════════════════════════════════════════════════════════════════


class TestMissingSentinel:
    """「字段缺失」与「字段被显式清空」是两种输入 —— 表示层与行为层双向锁死。"""

    @pytest.mark.parametrize("other", [None, "", 0, 0.0, False, [], {}, "MISSING"])
    def test_missing_never_equals_any_empty_value(self, other: Any) -> None:
        assert M.MISSING != other
        assert not (M.MISSING == other)
        assert M.MISSING is not other

    def test_missing_is_truthy_so_if_value_cannot_swallow_it(self) -> None:
        """刻意保持默认真值：falsy 的哨兵会被一句 `if value:` 与 None/""/0 一起吞掉。"""
        assert bool(M.MISSING) is True

    def test_missing_survives_copy_deepcopy_and_pickle(self) -> None:
        assert copy.copy(M.MISSING) is M.MISSING
        assert copy.deepcopy(M.MISSING) is M.MISSING
        assert pickle.loads(pickle.dumps(M.MISSING)) is M.MISSING

    @pytest.mark.parametrize("vt", list(C.ValueType))
    def test_normalize_returns_missing_identically_for_every_value_type(
        self, vt: C.ValueType
    ) -> None:
        assert M.normalize_value(M.MISSING, vt) is M.MISSING

    @pytest.mark.parametrize("vt", list(C.ValueType))
    def test_missing_vs_none_is_never_equal(self, vt: C.ValueType) -> None:
        assert M.values_equal(M.MISSING, M.MISSING, vt) is True
        assert M.values_equal(None, None, vt) is True
        assert M.values_equal(M.MISSING, None, vt) is False
        assert M.values_equal(None, M.MISSING, vt) is False

    def test_envelope_absent_and_present_null_have_different_jsonb(self) -> None:
        absent = CF.ValueEnvelope.absent().to_jsonb()
        cleared = CF.ValueEnvelope.of(None).to_jsonb()
        assert absent != cleared
        assert absent == {"present": False}
        assert cleared == {"present": True, "value": None}

    def test_absent_envelope_must_not_carry_a_value(self) -> None:
        with pytest.raises(CF.ConflictRecordError, match="present=False"):
            CF.ValueEnvelope(present=False, value=1)

    def test_envelopes_equal_never_folds_absent_into_null(self) -> None:
        assert (
            M.envelopes_equal(
                CF.ValueEnvelope.absent(), CF.ValueEnvelope.of(None), C.ValueType.text
            )
            is False
        )

    def test_deleted_and_cleared_produce_different_merged_results(
        self, xc: C.SyncContract
    ) -> None:
        """🔴 反例式证明（否定式承诺无法用短路变异证明）。

        `i=MISSING`（载体/行被删）与 `i=None`（用户在 OO 里清空）必须产出不同 merged：
        前者键消失，后者键存在且值为 null。折叠 MISSING→None 会让两者相同 ⇒ 本条打红。
        """
        deleted = M.merge_projections(
            base=proj(xc, {ek(R1, "name"): "A", ek(R1, "closing_amount"): 10}),
            current=proj(xc, {ek(R1, "name"): "A", ek(R1, "closing_amount"): 10}),
            incoming=proj(xc, {ek(R1, "name"): "A"}),
            contract=xc,
        )
        cleared = M.merge_projections(
            base=proj(xc, {ek(R1, "name"): "A", ek(R1, "closing_amount"): 10}),
            current=proj(xc, {ek(R1, "name"): "A", ek(R1, "closing_amount"): 10}),
            incoming=proj(xc, {ek(R1, "name"): "A", ek(R1, "closing_amount"): None}),
            contract=xc,
        )
        key = ek(R1, "closing_amount")
        assert deleted.value_of(key) == CF.ValueEnvelope.absent()
        assert cleared.value_of(key) == CF.ValueEnvelope.of(None)
        assert deleted.value_of(key) != cleared.value_of(key)
        assert deleted.merged.get(key) is None and cleared.merged.get(key) is not None


# ═══════════════════════════════════════════════════════════════════════════
# 2. 类型规范化：该等的等、不该等的坚决不等
# ═══════════════════════════════════════════════════════════════════════════


class TestTypeNormalization:
    """design §Merge Algorithm：金额 Decimal、日期 ISO、字符串只规范 OO 非语义控制字符。"""

    @pytest.mark.parametrize(
        ("left", "right"),
        [
            ("1234.50", Decimal("1234.5")),
            ("1234.50", 1234.5),
            (1234.5, Decimal("1234.5")),
            (Decimal("1e2"), 100),
            ("  1234.50  ", 1234.5),
            ("0.1", 0.1),
        ],
    )
    def test_amount_representations_that_are_the_same_number_are_equal(
        self, left: Any, right: Any
    ) -> None:
        assert M.values_equal(left, right, C.ValueType.amount) is True

    @pytest.mark.parametrize(
        ("left", "right"),
        [(None, 0), (0, None), (Decimal("1"), Decimal("1.01")), (None, Decimal(0))],
    )
    def test_amount_null_is_not_zero(self, left: Any, right: Any) -> None:
        assert M.values_equal(left, right, C.ValueType.amount) is False

    @pytest.mark.parametrize("bad", ["", "   ", "1,234.50", "abc", True, False, [1]])
    def test_amount_rejects_non_numeric_inputs(self, bad: Any) -> None:
        with pytest.raises(M.ValueNormalizationError):
            M.normalize_value(bad, C.ValueType.amount)

    def test_integer_accepts_integral_float_but_rejects_bool_and_fraction(self) -> None:
        assert M.values_equal(2, 2.0, C.ValueType.integer) is True
        assert M.values_equal("2", 2, C.ValueType.integer) is True
        with pytest.raises(M.ValueNormalizationError, match="bool"):
            M.normalize_value(True, C.ValueType.integer)
        with pytest.raises(M.ValueNormalizationError, match="非整值"):
            M.normalize_value(2.5, C.ValueType.integer)

    def test_boolean_rejects_zero_one_and_capitalised_strings(self) -> None:
        assert M.values_equal("true", True, C.ValueType.boolean) is True
        for bad in (1, 0, "True", "FALSE", "yes"):
            with pytest.raises(M.ValueNormalizationError):
                M.normalize_value(bad, C.ValueType.boolean)

    @pytest.mark.parametrize(
        ("left", "right", "expected"),
        [
            ("a\r\nb", "a\nb", True),
            ("a\rb", "a\nb", True),
            ("\ufeffabc", "abc", True),
            ("a ", "a", False),
            (" a", "a", False),
            ("a\u00a0b", "a b", False),
            ("a\u200bb", "ab", False),
            ("A", "a", False),
        ],
    )
    def test_text_normalizes_only_line_endings_and_bom(
        self, left: str, right: str, expected: bool
    ) -> None:
        """不 trim 用户有意义空格、不折叠 NBSP/零宽 —— 只归一换行与 BOM。"""
        assert M.values_equal(left, right, C.ValueType.text) is expected

    def test_text_refuses_to_coerce_numbers(self) -> None:
        with pytest.raises(M.ValueNormalizationError, match="text"):
            M.normalize_value(1, C.ValueType.text)

    def test_date_and_datetime_do_not_fold_into_each_other(self) -> None:
        assert M.values_equal("2026-08-25", date(2026, 8, 25), C.ValueType.date) is True
        with pytest.raises(M.ValueNormalizationError, match="date 字段收到 datetime"):
            M.normalize_value(datetime(2026, 8, 25, 0, 0), C.ValueType.date)
        with pytest.raises(M.ValueNormalizationError, match="datetime 字段收到 date"):
            M.normalize_value(date(2026, 8, 25), C.ValueType.datetime)

    def test_naive_and_aware_datetimes_are_not_equal(self) -> None:
        naive = "2026-08-25T10:00:00"
        aware = "2026-08-25T10:00:00+00:00"
        assert M.values_equal(naive, aware, C.ValueType.datetime) is False
        assert (
            M.values_equal(
                aware, datetime(2026, 8, 25, 10, 0, tzinfo=timezone.utc), C.ValueType.datetime
            )
            is True
        )

    def test_enum_is_case_sensitive(self) -> None:
        assert M.values_equal("Listed", "Listed", C.ValueType.enum) is True
        assert M.values_equal("Listed", "listed", C.ValueType.enum) is False

    def test_json_is_key_order_insensitive_but_value_sensitive(self) -> None:
        assert M.values_equal({"a": 1, "b": 2}, {"b": 2, "a": 1}, C.ValueType.json) is True
        assert M.values_equal({"a": 1}, {"a": 2}, C.ValueType.json) is False
        assert M.values_equal([1, 2], [2, 1], C.ValueType.json) is False

    def test_normalization_failure_messages_name_the_value_type(self) -> None:
        """每种类型的失败文案带自己的 value_type —— 合并文案会让「哪条判据」不可分辨。"""
        seen: dict[str, str] = {}
        probes = {
            C.ValueType.amount: "abc",
            C.ValueType.integer: 2.5,
            C.ValueType.date: "not-a-date",
            C.ValueType.datetime: "not-a-time",
            C.ValueType.boolean: 1,
            C.ValueType.enum: 5,
            C.ValueType.text: 1,
        }
        for vt, bad in probes.items():
            with pytest.raises(M.ValueNormalizationError) as exc:
                M.normalize_value(bad, vt)
            seen[vt.value] = str(exc.value)
            assert vt.value in seen[vt.value], f"{vt.value} 的失败文案未点名自己"
        assert len(set(seen.values())) == len(seen), "失败文案有重合，无法分辨成因"


# ═══════════════════════════════════════════════════════════════════════════
# 3. 三方真值表（design §Merge Algorithm 原文 + MISSING 扩展）
# ═══════════════════════════════════════════════════════════════════════════

_MISS = M.MISSING

#: (b, c, i, 期望 verdict, 期望 merged 值) —— 模块 docstring 那张表的可执行形态。
TRUTH_TABLE: list[tuple[Any, Any, Any, M.FieldVerdict, Any]] = [
    # i == b ⇒ 保留服务器新值（OO 未改）
    (10, 20, 10, M.FieldVerdict.kept_current, 20),
    (10, 10, 10, M.FieldVerdict.kept_current, 10),
    # c == b ⇒ 仅 OO 改
    (10, 10, 30, M.FieldVerdict.took_incoming, 30),
    # c == i ⇒ 两侧同改为相同值
    (10, 40, 40, M.FieldVerdict.both_sides_agree, 40),
    # 三值互异 ⇒ value 冲突，merged 保持 current（绝不 last-write-wins）
    (10, 20, 30, M.FieldVerdict.conflict_value, 20),
    # OO 新增（b/c 缺失）
    (_MISS, _MISS, 30, M.FieldVerdict.took_incoming, 30),
    # current 删除、OO 未改 ⇒ 保留删除
    (10, _MISS, 10, M.FieldVerdict.kept_current, _MISS),
    # **静态**受管格在 incoming 侧消失 = 载体漂移 ⇒ 走真值表第 3 行（先于第 5~7 行短路）。
    # 「两侧同时删除 ⇒ 删除」只对**行域**字段成立，见
    # `test_row_scoped_field_deleted_on_both_sides_agrees_without_conflict`。
    (10, _MISS, _MISS, M.FieldVerdict.conflict_schema, _MISS),
    # 显式清空（None）不是删除
    (10, 10, None, M.FieldVerdict.took_incoming, None),
    (10, None, 10, M.FieldVerdict.kept_current, None),
]


class TestThreeWayTruthTable:
    """真值表逐行跑真实执行 —— 不是「源码里有这个分支」而是「这组输入真的走到它」。"""

    @pytest.mark.parametrize(("b", "c", "i", "verdict", "expected"), TRUTH_TABLE)
    def test_row(
        self,
        xc: C.SyncContract,
        b: Any,
        c: Any,
        i: Any,
        verdict: M.FieldVerdict,
        expected: Any,
    ) -> None:
        outcome = single(xc, b, c, i)
        assert outcome.verdicts[TOTAL] is verdict, (
            f"(b={b!r}, c={c!r}, i={i!r}) 应走 {verdict.value}，实得 "
            f"{outcome.verdicts[TOTAL].value}"
        )
        got = outcome.value_of(TOTAL)
        want = (
            CF.ValueEnvelope.absent() if expected is _MISS else CF.ValueEnvelope.of(expected)
        )
        assert got == want
        assert outcome.has_conflicts is verdict.is_conflict

    def test_current_delete_vs_incoming_update_is_delete_update_not_value(
        self, xc: C.SyncContract
    ) -> None:
        outcome = single(xc, 10, _MISS, 30)
        assert outcome.verdicts[TOTAL] is M.FieldVerdict.conflict_delete_update
        assert outcome.conflicts.records[0].kind is CF.ConflictKind.delete_update

    def test_key_absent_from_all_three_sides_is_outside_the_key_domain(
        self, xc: C.SyncContract
    ) -> None:
        """三方都没有这个键 ⇒ 它不在键域内，既无 verdict 也不进 merged。

        🔴 这条**不能**写成真值表的一行（`(MISSING, MISSING, MISSING)` → kept_current）：
        键域是 `base ∪ current ∪ incoming`，三方全缺时根本没有可判定的对象。写成真值表行
        会逼实现去遍历整份契约的键空间 —— 而行域字段的 `{row_uuid}` 模板本就无法枚举，
        真那么做等于给从未出现的行凭空造 verdict。
        """
        outcome = single(xc, _MISS, _MISS, _MISS)
        assert TOTAL not in outcome.verdicts, "三方全缺的键不该有 verdict"
        assert TOTAL not in outcome.merged.values, "三方全缺的键不该出现在 merged"
        assert outcome.value_of(TOTAL) == CF.ValueEnvelope.absent()
        assert outcome.conflict_count == 0

    def test_row_scoped_field_deleted_on_both_sides_agrees_without_conflict(
        self, xc: C.SyncContract
    ) -> None:
        """行域字段两侧同时删除 ⇒ both_sides_agree，不是载体漂移。

        与真值表里静态键的 `(10, MISSING, MISSING) → conflict_schema` 成对：
        「incoming 缺失」在静态受管格上是**载体消失**（fail closed），在动态行上是
        **合法删除**。合成一条判据会让其中一支永不被测到。
        """
        base = proj(xc, row_values(R1, name="甲", closing=100), row_keys={"equity_changes": (R1,)})
        empty = proj(xc, {}, row_keys={"equity_changes": ()})
        outcome = M.merge_projections(
            base=base, current=empty, incoming=empty, contract=xc
        )
        for leaf in ("name", "closing_amount"):
            assert outcome.verdicts[ek(R1, leaf)] is M.FieldVerdict.both_sides_agree
            assert outcome.value_of(ek(R1, leaf)) == CF.ValueEnvelope.absent()
        assert outcome.conflict_count == 0
        assert [d.lifecycle for d in outcome.rows] == [M.RowLifecycle.deleted_by_incoming]

    def test_never_last_write_wins(self, xc: C.SyncContract) -> None:
        """同字段异值时 merged 必须**不等于** incoming —— 否则就是 last-write-wins。"""
        outcome = single(xc, 10, 20, 30)
        assert outcome.value_of(TOTAL) == CF.ValueEnvelope.of(20)
        assert outcome.value_of(TOTAL) != CF.ValueEnvelope.of(30)

    def test_unchanged_incoming_preserves_newer_server_value(
        self, xc: C.SyncContract
    ) -> None:
        """AC 6.7「仅 current 变更则保 current」—— OO 未改动不得把服务器新值打回旧值。"""
        outcome = single(xc, 10, 999, 10)
        assert outcome.value_of(TOTAL) == CF.ValueEnvelope.of(999)
        assert outcome.conflict_count == 0


# ═══════════════════════════════════════════════════════════════════════════
# 4. Property 24：保护字段修改形成冲突
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty24ProtectedField:
    """AC 6.6：公式 / auto-source / 受保护单元格默认只读；OO 改动 ⇒ protected 冲突。

    三类保护来源是**三条独立判据**（`ProtectionPolicy` 三个成员），因此三个反例分别写。
    """

    @pytest.mark.parametrize(
        ("leaf", "policy", "source"),
        [
            ("subtotal", CF.ProtectionPolicy.read_only_formula, CF.FieldSource.server_formula),
            (
                "tb_amount",
                CF.ProtectionPolicy.read_only_auto_source,
                CF.FieldSource.auto_data_source,
            ),
            (
                "masked_note",
                CF.ProtectionPolicy.read_only_masked_cell,
                CF.FieldSource.onlyoffice_cell,
            ),
        ],
    )
    def test_oo_edit_on_protected_field_yields_protected_conflict(
        self,
        xc: C.SyncContract,
        leaf: str,
        policy: CF.ProtectionPolicy,
        source: CF.FieldSource,
    ) -> None:
        key = ek(R1, leaf)
        server = "服务器值" if leaf == "masked_note" else 100
        tampered = "OO 改的" if leaf == "masked_note" else 777
        outcome = M.merge_projections(
            base=proj(xc, {key: server}),
            current=proj(xc, {key: server}),
            incoming=proj(xc, {key: tampered}),
            contract=xc,
        )
        assert outcome.conflict_count == 1
        record = outcome.conflicts.records[0]
        assert record.kind is CF.ConflictKind.protected
        assert record.locator.protection_policy is policy
        assert record.locator.field_source is source
        assert record.suggested_action is CF.SuggestedAction.keep_current
        # current 的值不被覆盖（AC 6.6「不得覆盖公式结果」）
        assert outcome.value_of(key) == CF.ValueEnvelope.of(server)
        assert record.incoming == CF.ValueEnvelope.of(tampered)

    def test_protected_field_untouched_by_oo_keeps_recomputed_server_value(
        self, xc: C.SyncContract
    ) -> None:
        """OO 未改（i == b）时不报冲突，且服务器新算的公式值胜出。"""
        key = ek(R1, "subtotal")
        outcome = M.merge_projections(
            base=proj(xc, {key: 100}),
            current=proj(xc, {key: 250}),
            incoming=proj(xc, {key: 100}),
            contract=xc,
        )
        assert outcome.conflict_count == 0
        assert outcome.value_of(key) == CF.ValueEnvelope.of(250)

    def test_new_row_added_in_oo_does_not_conflict_on_its_formula_cell(
        self, xc: C.SyncContract
    ) -> None:
        """OO 新增行时公式格由服务端重算 —— 不得因「b 缺失、i 有值」误报 protected 冲突。"""
        outcome = M.merge_projections(
            base=proj(xc, {}),
            current=proj(xc, {}),
            incoming=proj(
                xc, {ek(R1, "name"): "新行", ek(R1, "subtotal"): 42}
            ),
            contract=xc,
        )
        assert outcome.conflict_count == 0
        assert outcome.verdicts[ek(R1, "subtotal")] is M.FieldVerdict.took_incoming

    def test_row_deleted_in_oo_does_not_conflict_on_its_protected_cells(
        self, xc: C.SyncContract
    ) -> None:
        """删行时公式格随行消失。若 protected 判据不看行生命周期，每次删行都会假冲突。"""
        base = proj(
            xc,
            {ek(R1, "name"): "A", ek(R1, "subtotal"): 100, ek(R1, "tb_amount"): 100},
        )
        outcome = M.merge_projections(
            base=base, current=base, incoming=proj(xc, {}), contract=xc
        )
        assert outcome.conflict_count == 0
        assert outcome.rows[0].lifecycle is M.RowLifecycle.deleted_by_incoming
        assert outcome.value_of(ek(R1, "subtotal")) == CF.ValueEnvelope.absent()

    def test_protected_conflict_cannot_be_resolved_by_taking_incoming(
        self, xc: C.SyncContract
    ) -> None:
        key = ek(R1, "subtotal")
        outcome = M.merge_projections(
            base=proj(xc, {key: 100}),
            current=proj(xc, {key: 100}),
            incoming=proj(xc, {key: 777}),
            contract=xc,
        )
        record = outcome.conflicts.records[0]
        for kind in (CF.ResolutionKind.take_incoming,):
            with pytest.raises(CF.ProtectedFieldOverrideError, match="read_only_formula"):
                CF.resolved_value_for(
                    record,
                    CF.ResolutionChoice(
                        stable_field_key=key,
                        row_key=record.locator.row_key,
                        oo_location=record.locator.oo_location,
                        kind=kind,
                    ),
                )
        with pytest.raises(CF.ProtectedFieldOverrideError):
            CF.resolved_value_for(
                record,
                CF.ResolutionChoice(
                    stable_field_key=key,
                    row_key=record.locator.row_key,
                    oo_location=record.locator.oo_location,
                    kind=CF.ResolutionKind.manual,
                    manual=CF.ValueEnvelope.of(1),
                ),
            )
        kept = CF.resolved_value_for(
            record,
            CF.ResolutionChoice(
                stable_field_key=key,
                row_key=record.locator.row_key,
                oo_location=record.locator.oo_location,
                kind=CF.ResolutionKind.keep_current,
            ),
        )
        assert kept == CF.ValueEnvelope.of(100)

    def test_protected_record_with_editable_policy_is_rejected(self) -> None:
        """记录自洽性：protected 冲突不许挂在 editable 字段上。"""
        loc = CF.FieldLocator(
            stable_field_key="a/b",
            business_label="标签",
            json_pointer="/a/b",
            oo_location="S!A1",
            field_source=CF.FieldSource.onlyoffice_cell,
            protection_policy=CF.ProtectionPolicy.editable,
            value_type=C.ValueType.text,
            mode=C.FieldMode.editable,
        )
        with pytest.raises(CF.ConflictRecordError, match="自相矛盾"):
            CF.ConflictRecord(
                locator=loc,
                kind=CF.ConflictKind.protected,
                base=CF.ValueEnvelope.of("x"),
                current=CF.ValueEnvelope.of("x"),
                incoming=CF.ValueEnvelope.of("y"),
                suggested_action=CF.SuggestedAction.keep_current,
                reason="足够长的原因文案",
            )


# ═══════════════════════════════════════════════════════════════════════════
# 5. Property 25：不同字段自动三方合并
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty25DifferentFieldsAutoMerge:
    """AC 6.8：不同字段的并行修改自动合并、conflict_count = 0。"""

    def test_current_changes_a_incoming_changes_b(self, xc: C.SyncContract) -> None:
        base = proj(xc, {PERIOD: "2025年度", TOTAL: 100})
        current = proj(xc, {PERIOD: "2026年度", TOTAL: 100})
        incoming = proj(xc, {PERIOD: "2025年度", TOTAL: 300})
        outcome = M.merge_projections(
            base=base, current=current, incoming=incoming, contract=xc
        )
        assert outcome.conflict_count == 0
        assert outcome.value_of(PERIOD) == CF.ValueEnvelope.of("2026年度")
        assert outcome.value_of(TOTAL) == CF.ValueEnvelope.of(300)
        assert outcome.auto_merged_keys == (TOTAL,)

    def test_parallel_edits_on_different_rows_of_the_same_table(
        self, xc: C.SyncContract
    ) -> None:
        base = proj(
            xc,
            {**row_values(R1, name="甲", closing=1), **row_values(R2, name="乙", closing=2)},
            row_keys={"equity_changes": (R1, R2)},
        )
        current = proj(
            xc,
            {**row_values(R1, name="甲改", closing=1), **row_values(R2, name="乙", closing=2)},
            row_keys={"equity_changes": (R1, R2)},
        )
        incoming = proj(
            xc,
            {**row_values(R1, name="甲", closing=1), **row_values(R2, name="乙", closing=222)},
            row_keys={"equity_changes": (R1, R2)},
        )
        outcome = M.merge_projections(
            base=base, current=current, incoming=incoming, contract=xc
        )
        assert outcome.conflict_count == 0
        assert outcome.value_of(ek(R1, "name")) == CF.ValueEnvelope.of("甲改")
        assert outcome.value_of(ek(R2, "closing_amount")) == CF.ValueEnvelope.of(222)

    def test_row_reorder_alone_produces_no_conflict_and_no_value_change(
        self, xc: C.SyncContract
    ) -> None:
        """AC 6.9：重排只改展示顺序 —— 值一个不变、冲突为 0、行集合不变。"""
        values = {
            **row_values(R1, name="甲", closing=1),
            **row_values(R2, name="乙", closing=2),
            **row_values(R3, name="丙", closing=3),
        }
        base = proj(xc, values, row_keys={"equity_changes": (R1, R2, R3)})
        current = proj(xc, values, row_keys={"equity_changes": (R1, R2, R3)})
        incoming = proj(xc, values, row_keys={"equity_changes": (R3, R1, R2)})
        outcome = M.merge_projections(
            base=base, current=current, incoming=incoming, contract=xc
        )
        assert outcome.conflict_count == 0
        assert dict(outcome.merged.values).keys() == values.keys()
        for key, raw in values.items():
            assert outcome.value_of(key) == CF.ValueEnvelope.of(raw)
        assert outcome.merged.row_keys["equity_changes"] == (R3, R1, R2)
        assert all(d.lifecycle is M.RowLifecycle.unchanged for d in outcome.rows)

    def test_footer_shift_after_row_insert_is_not_a_conflict(
        self, xc: C.SyncContract
    ) -> None:
        """插行会让 footer 下移。footer 字段按 stable key 定位，位置变化不产生冲突。"""
        base = proj(
            xc,
            {**row_values(R1, name="甲", closing=1), TOTAL: 1},
            row_keys={"equity_changes": (R1,)},
        )
        current = base
        incoming = proj(
            xc,
            {
                **row_values(R1, name="甲", closing=1),
                **row_values(R2, name="新增", closing=5),
                TOTAL: 1,
            },
            row_keys={"equity_changes": (R1, R2)},
        )
        outcome = M.merge_projections(
            base=base, current=current, incoming=incoming, contract=xc
        )
        assert outcome.conflict_count == 0
        assert outcome.value_of(ek(R2, "name")) == CF.ValueEnvelope.of("新增")
        assert outcome.value_of(TOTAL) == CF.ValueEnvelope.of(1)
        added = [d for d in outcome.rows if d.row_key == R2][0]
        assert added.lifecycle is M.RowLifecycle.added_by_incoming


# ═══════════════════════════════════════════════════════════════════════════
# 6. Property 26：同字段异值必冲突，且不自动选边
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty26SameFieldDifferentValues:
    """base=A / current=B / incoming=C ⇒ 不得应用任一侧，三值完整。"""

    def test_three_values_are_complete_and_neither_side_applied(
        self, xc: C.SyncContract
    ) -> None:
        outcome = single(xc, "A", "B", "C", key=PERIOD)
        assert outcome.conflict_count == 1
        record = outcome.conflicts.records[0]
        assert record.kind is CF.ConflictKind.value
        assert record.base == CF.ValueEnvelope.of("A")
        assert record.current == CF.ValueEnvelope.of("B")
        assert record.incoming == CF.ValueEnvelope.of("C")
        assert outcome.value_of(PERIOD) != CF.ValueEnvelope.of("C")

    def test_both_sides_changed_to_the_same_value_merges(self, xc: C.SyncContract) -> None:
        outcome = single(xc, "A", "B", "B", key=PERIOD)
        assert outcome.conflict_count == 0
        assert outcome.value_of(PERIOD) == CF.ValueEnvelope.of("B")

    def test_unresolved_conflict_blocks_apply(self, xc: C.SyncContract) -> None:
        """缺裁决必抛 —— 域内绝不回落到任何一侧（AC 4.6 / Property 26）。"""
        outcome = single(xc, "A", "B", "C", key=PERIOD)
        with pytest.raises(CF.UnresolvedConflictError, match="未裁决"):
            M.apply_resolutions(outcome, [], contract=xc)

    def test_resolution_can_pick_either_side_or_a_manual_value(
        self, xc: C.SyncContract
    ) -> None:
        outcome = single(xc, "A", "B", "C", key=PERIOD)
        record = outcome.conflicts.records[0]
        base_kwargs = {
            "stable_field_key": PERIOD,
            "row_key": record.locator.row_key,
            "oo_location": record.locator.oo_location,
        }
        taken = M.apply_resolutions(
            outcome,
            [CF.ResolutionChoice(**base_kwargs, kind=CF.ResolutionKind.take_incoming)],
            contract=xc,
        )
        assert taken.get(PERIOD).value == "C"
        kept = M.apply_resolutions(
            outcome,
            [CF.ResolutionChoice(**base_kwargs, kind=CF.ResolutionKind.keep_current)],
            contract=xc,
        )
        assert kept.get(PERIOD).value == "B"
        manual = M.apply_resolutions(
            outcome,
            [
                CF.ResolutionChoice(
                    **base_kwargs,
                    kind=CF.ResolutionKind.manual,
                    manual=CF.ValueEnvelope.of("B+C"),
                )
            ],
            contract=xc,
        )
        assert manual.get(PERIOD).value == "B+C"
        cleared = M.apply_resolutions(
            outcome,
            [
                CF.ResolutionChoice(
                    **base_kwargs,
                    kind=CF.ResolutionKind.manual,
                    manual=CF.ValueEnvelope.absent(),
                )
            ],
            contract=xc,
        )
        assert cleared.get(PERIOD) is None

    def test_resolution_pointing_at_a_nonexistent_conflict_is_rejected(
        self, xc: C.SyncContract
    ) -> None:
        """多给一条指向不存在冲突的裁决 ⇒ `UnknownConflictResolutionError`。

        🔴 真实冲突必须**同时给上裁决**：`assert_all_conflicts_resolved` 先查 missing、
        后查 unknown，只给一条假裁决会先撞 `UnresolvedConflictError` ——
        于是「unknown 目标」这条判据永远测不到（同类型/同顺序遮蔽，Task 12/13 实测过的
        最贵一类假绿）。下一条测试断言两者是**两种**异常。
        """
        outcome = single(xc, "A", "B", "C", key=PERIOD)
        real = outcome.conflicts.records[0]
        good = CF.ResolutionChoice(
            stable_field_key=PERIOD,
            oo_location=real.locator.oo_location,
            kind=CF.ResolutionKind.keep_current,
        )
        bogus = CF.ResolutionChoice(
            stable_field_key="header_block/total_amount",
            oo_location="G7 披露表!C3",
            kind=CF.ResolutionKind.keep_current,
        )
        with pytest.raises(CF.UnknownConflictResolutionError, match="不存在"):
            M.apply_resolutions(outcome, [good, bogus], contract=xc)

    def test_missing_and_unknown_resolutions_are_two_distinguishable_types(
        self, xc: C.SyncContract
    ) -> None:
        """「少裁决」与「裁决指向不存在的冲突」必须可分辨，且各带自己的文案。"""
        outcome = single(xc, "A", "B", "C", key=PERIOD)
        with pytest.raises(CF.UnresolvedConflictError) as missing:
            M.apply_resolutions(outcome, [], contract=xc)
        assert "未裁决" in str(missing.value)
        assert not issubclass(
            CF.UnresolvedConflictError, CF.UnknownConflictResolutionError
        )
        assert not issubclass(
            CF.UnknownConflictResolutionError, CF.UnresolvedConflictError
        )

    def test_duplicate_resolutions_for_one_conflict_are_rejected(
        self, xc: C.SyncContract
    ) -> None:
        outcome = single(xc, "A", "B", "C", key=PERIOD)
        record = outcome.conflicts.records[0]
        choice = CF.ResolutionChoice(
            stable_field_key=PERIOD,
            oo_location=record.locator.oo_location,
            kind=CF.ResolutionKind.keep_current,
        )
        with pytest.raises(CF.UnknownConflictResolutionError, match="重复"):
            M.apply_resolutions(outcome, [choice, choice], contract=xc)


# ═══════════════════════════════════════════════════════════════════════════
# 7. Property 27：delete/update 冲突不整表覆盖
# ═══════════════════════════════════════════════════════════════════════════


def _two_row_scenario(
    xc: C.SyncContract, *, incoming_drops_r1: bool, current_edits_r1: bool
):
    """R1/R2 两行；R1 一侧删一侧改，R2 只有 OO 改动（必须照常合并）。"""
    base_vals = {
        **row_values(R1, name="甲", closing=1),
        **row_values(R2, name="乙", closing=2),
    }
    cur_vals = dict(base_vals)
    if current_edits_r1:
        cur_vals[ek(R1, "closing_amount")] = 111
    inc_vals = dict(base_vals)
    inc_vals[ek(R2, "closing_amount")] = 222
    if incoming_drops_r1:
        for leaf in ("name", "closing_amount"):
            inc_vals.pop(ek(R1, leaf))
    return M.merge_projections(
        base=proj(xc, base_vals, row_keys={"equity_changes": (R1, R2)}),
        current=proj(xc, cur_vals, row_keys={"equity_changes": (R1, R2)}),
        incoming=proj(
            xc,
            inc_vals,
            row_keys={"equity_changes": (R2,) if incoming_drops_r1 else (R1, R2)},
        ),
        contract=xc,
    )


class TestProperty27DeleteUpdate:
    """AC 6.9：一侧删行、另一侧改同 row_uuid ⇒ 只生成该行冲突，其他行照常合并。"""

    def test_incoming_deletes_row_current_updates_it(self, xc: C.SyncContract) -> None:
        outcome = _two_row_scenario(xc, incoming_drops_r1=True, current_edits_r1=True)
        kinds = {r.kind for r in outcome.conflicts}
        assert kinds == {CF.ConflictKind.delete_update}
        rows_in_conflict = {r.locator.row_key for r in outcome.conflicts}
        assert rows_in_conflict == {R1}, "冲突必须只锁 R1，不得扩散成整表"
        # R2 的 OO 改动照常合并
        assert outcome.value_of(ek(R2, "closing_amount")) == CF.ValueEnvelope.of(222)
        # R1 整行 hold 在 current（既不半删也不被 incoming 覆盖）
        r1 = [d for d in outcome.rows if d.row_key == R1][0]
        assert r1.lifecycle is M.RowLifecycle.delete_update_conflict and r1.held is True
        assert outcome.value_of(ek(R1, "closing_amount")) == CF.ValueEnvelope.of(111)
        assert outcome.value_of(ek(R1, "name")) == CF.ValueEnvelope.of("甲")
        assert outcome.verdicts[ek(R1, "name")] is M.FieldVerdict.held_by_row_conflict

    def test_current_deletes_row_incoming_updates_it(self, xc: C.SyncContract) -> None:
        base_vals = {
            **row_values(R1, name="甲", closing=1),
            **row_values(R2, name="乙", closing=2),
        }
        cur_vals = {k: v for k, v in base_vals.items() if R1 not in k}
        inc_vals = dict(base_vals)
        inc_vals[ek(R1, "closing_amount")] = 999
        inc_vals[ek(R2, "closing_amount")] = 222
        outcome = M.merge_projections(
            base=proj(xc, base_vals, row_keys={"equity_changes": (R1, R2)}),
            current=proj(xc, cur_vals, row_keys={"equity_changes": (R2,)}),
            incoming=proj(xc, inc_vals, row_keys={"equity_changes": (R1, R2)}),
            contract=xc,
        )
        assert {r.kind for r in outcome.conflicts} == {CF.ConflictKind.delete_update}
        assert {r.locator.row_key for r in outcome.conflicts} == {R1}
        assert outcome.value_of(ek(R2, "closing_amount")) == CF.ValueEnvelope.of(222)
        # 🔴 必须断言到**行级**判定，不能只看「有一条 delete_update 冲突」：
        # 被改动的那个字段（closing_amount）单靠真值表第 8 行就会产出 delete_update 冲突，
        # 于是即使行生命周期分类被短路成 deleted_by_current，上面三条断言仍全部成立。
        # 变异 M32 首轮实测正是靠这个缺口判 GREEN —— 补齐后与
        # `test_incoming_deletes_row_current_updates_it` 对称。
        r1 = [d for d in outcome.rows if d.row_key == R1][0]
        assert r1.lifecycle is M.RowLifecycle.delete_update_conflict
        assert r1.held is True, (
            "整行必须被 hold —— 否则行内**未被改动**的字段会按三方规则被静默处置，"
            "「一侧删一侧改」退化成「只对改动字段报冲突」"
        )
        assert outcome.verdicts[ek(R1, "name")] is M.FieldVerdict.held_by_row_conflict

    def test_plain_row_delete_is_accepted_without_conflict(
        self, xc: C.SyncContract
    ) -> None:
        outcome = _two_row_scenario(xc, incoming_drops_r1=True, current_edits_r1=False)
        assert outcome.conflict_count == 0
        r1 = [d for d in outcome.rows if d.row_key == R1][0]
        assert r1.lifecycle is M.RowLifecycle.deleted_by_incoming
        assert outcome.value_of(ek(R1, "name")) == CF.ValueEnvelope.absent()
        assert outcome.merged.row_keys["equity_changes"] == (R2,)
        assert set(outcome.deleted_keys) == {ek(R1, "name"), ek(R1, "closing_amount")}

    def test_resolving_delete_update_as_delete_removes_the_whole_row(
        self, xc: C.SyncContract
    ) -> None:
        outcome = _two_row_scenario(xc, incoming_drops_r1=True, current_edits_r1=True)
        choices = [
            CF.ResolutionChoice(
                stable_field_key=r.locator.stable_field_key,
                row_key=r.locator.row_key,
                oo_location=r.locator.oo_location,
                kind=CF.ResolutionKind.take_incoming,
            )
            for r in outcome.conflicts
        ]
        resolved = M.apply_resolutions(outcome, choices, contract=xc)
        assert resolved.get(ek(R1, "name")) is None, "接受删除后整行应消失，不留半行"
        assert resolved.get(ek(R1, "closing_amount")) is None
        assert resolved.get(ek(R2, "closing_amount")).value == 222

    def test_resolving_delete_update_as_keep_current_retains_the_row(
        self, xc: C.SyncContract
    ) -> None:
        outcome = _two_row_scenario(xc, incoming_drops_r1=True, current_edits_r1=True)
        choices = [
            CF.ResolutionChoice(
                stable_field_key=r.locator.stable_field_key,
                row_key=r.locator.row_key,
                oo_location=r.locator.oo_location,
                kind=CF.ResolutionKind.keep_current,
            )
            for r in outcome.conflicts
        ]
        resolved = M.apply_resolutions(outcome, choices, contract=xc)
        assert resolved.get(ek(R1, "closing_amount")).value == 111
        assert resolved.get(ek(R1, "name")).value == "甲"

    def test_delete_update_record_requires_exactly_one_absent_side(self) -> None:
        loc = CF.FieldLocator(
            stable_field_key=ek(R1, "name"),
            business_label="标签",
            json_pointer=f"/rows/{R1}/name",
            oo_location="G7 披露表!G@row=" + R1,
            field_source=CF.FieldSource.onlyoffice_cell,
            protection_policy=CF.ProtectionPolicy.editable,
            value_type=C.ValueType.text,
            mode=C.FieldMode.editable,
            row_key=R1,
        )
        with pytest.raises(CF.ConflictRecordError, match="恰好一侧"):
            CF.ConflictRecord(
                locator=loc,
                kind=CF.ConflictKind.delete_update,
                base=CF.ValueEnvelope.of("x"),
                current=CF.ValueEnvelope.of("y"),
                incoming=CF.ValueEnvelope.of("z"),
                suggested_action=CF.SuggestedAction.manual_merge,
                reason="足够长的原因文案",
            )


# ═══════════════════════════════════════════════════════════════════════════
# 8. Property 32：Word 同 tag 多实例异值冲突
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty32WordDuplicateInstances:
    """AC 7.4：值一致可合并；不一致 ⇒ duplicate 冲突并列出全部 OO 位置。"""

    def _obs(self, *pairs: tuple[str, Any]) -> M.WordInstanceObservation:
        return M.WordInstanceObservation(
            stable_field_key="plan/location",
            instances=tuple(M.WordInstance(xpath=x, value=v) for x, v in pairs),
        )

    def test_consistent_instances_collapse_to_one_field(self, dc: C.SyncContract) -> None:
        outcome = M.merge_projections(
            base=proj(dc, {"plan/location": "旧仓库"}),
            current=proj(dc, {"plan/location": "旧仓库"}),
            incoming=proj(dc, {"plan/location": "新仓库"}),
            contract=dc,
            word_instances=[
                self._obs(("/w:body/w:p[2]/w:sdt", "新仓库"), ("/w:body/w:tbl/w:sdt", "新仓库"))
            ],
        )
        assert outcome.conflict_count == 0
        assert outcome.value_of("plan/location") == CF.ValueEnvelope.of("新仓库")

    def test_divergent_instances_yield_duplicate_conflict_with_every_xpath(
        self, dc: C.SyncContract
    ) -> None:
        xpaths = ("/w:body/w:p[9]/w:sdt", "/w:body/w:p[2]/w:sdt", "/w:body/w:tbl/w:sdt")
        outcome = M.merge_projections(
            base=proj(dc, {"plan/location": "旧仓库"}),
            current=proj(dc, {"plan/location": "旧仓库"}),
            incoming=proj(dc, {"plan/location": "甲仓库"}),
            contract=dc,
            word_instances=[
                self._obs((xpaths[0], "丙仓库"), (xpaths[1], "甲仓库"), (xpaths[2], "乙仓库"))
            ],
        )
        assert outcome.conflict_count == 1
        record = outcome.conflicts.records[0]
        assert record.kind is CF.ConflictKind.duplicate_word_instance
        assert [ref.xpath for ref in record.word_instances] == sorted(xpaths)
        assert record.suggested_action is CF.SuggestedAction.pick_instance
        # OO 地址 = 实例化后的 sdt_tag（docx 侧的「OO 位置」）
        assert record.locator.oo_location == "gt:field:f2.stocktake.plan:plan/location"
        assert (
            outcome.verdicts["plan/location"]
            is M.FieldVerdict.conflict_duplicate_word_instance
        )
        # hold 在 current，不挑一个实例静默应用
        assert outcome.value_of("plan/location") == CF.ValueEnvelope.of("旧仓库")

    def test_take_incoming_is_ambiguous_and_must_be_rejected(
        self, dc: C.SyncContract
    ) -> None:
        outcome = M.merge_projections(
            base=proj(dc, {"plan/location": "旧"}),
            current=proj(dc, {"plan/location": "旧"}),
            incoming=proj(dc, {"plan/location": "甲"}),
            contract=dc,
            word_instances=[self._obs(("/a", "甲"), ("/b", "乙"))],
        )
        record = outcome.conflicts.records[0]
        kw = {
            "stable_field_key": "plan/location",
            "oo_location": record.locator.oo_location,
        }
        with pytest.raises(CF.InstanceSelectionRequiredError, match="take_instance"):
            CF.resolved_value_for(
                record, CF.ResolutionChoice(**kw, kind=CF.ResolutionKind.take_incoming)
            )
        picked = CF.resolved_value_for(
            record,
            CF.ResolutionChoice(
                **kw, kind=CF.ResolutionKind.take_instance, instance_xpath="/b"
            ),
        )
        assert picked == CF.ValueEnvelope.of("乙")
        with pytest.raises(CF.UnknownConflictResolutionError, match="不在实例清单"):
            CF.resolved_value_for(
                record,
                CF.ResolutionChoice(
                    **kw, kind=CF.ResolutionKind.take_instance, instance_xpath="/zzz"
                ),
            )

    def test_all_equal_instances_cannot_be_recorded_as_duplicate_conflict(self) -> None:
        loc = CF.FieldLocator(
            stable_field_key="plan/location",
            business_label="监盘地点",
            json_pointer="/plan/location",
            oo_location="gt:field:x:plan/location",
            field_source=CF.FieldSource.onlyoffice_sdt,
            protection_policy=CF.ProtectionPolicy.editable,
            value_type=C.ValueType.text,
            mode=C.FieldMode.editable,
        )
        for instances, pattern in (
            ((CF.WordInstanceRef("/a", CF.ValueEnvelope.of("同")),), "≥2"),
            (
                (
                    CF.WordInstanceRef("/a", CF.ValueEnvelope.of("同")),
                    CF.WordInstanceRef("/b", CF.ValueEnvelope.of("同")),
                ),
                "值相同",
            ),
        ):
            with pytest.raises(CF.ConflictRecordError, match=pattern):
                CF.ConflictRecord(
                    locator=loc,
                    kind=CF.ConflictKind.duplicate_word_instance,
                    base=CF.ValueEnvelope.absent(),
                    current=CF.ValueEnvelope.absent(),
                    incoming=CF.ValueEnvelope.of("同"),
                    suggested_action=CF.SuggestedAction.pick_instance,
                    reason="足够长的原因文案",
                    word_instances=instances,
                )

    def test_duplicate_xpath_in_observation_is_rejected(self) -> None:
        with pytest.raises(M.MergeInputError, match="XPath 重复"):
            self._obs(("/a", "x"), ("/a", "y"))

    def test_word_only_field_never_enters_the_html_projection(
        self, dc: C.SyncContract
    ) -> None:
        """AC 7.3：SDT 外自由正文属 Word，永不回填 HTML，也不产生冲突。"""
        outcome = M.merge_projections(
            base=proj(dc, {"plan/free_notes": "旧正文"}),
            current=proj(dc, {"plan/free_notes": "旧正文"}),
            incoming=proj(dc, {"plan/free_notes": "审计师补写的大段正文"}),
            contract=dc,
        )
        assert outcome.conflict_count == 0
        assert outcome.word_only_keys == ("plan/free_notes",)
        assert outcome.merged.get("plan/free_notes") is None
        assert outcome.verdicts["plan/free_notes"] is M.FieldVerdict.word_only


# ═══════════════════════════════════════════════════════════════════════════
# 9. Property 35：冲突记录双侧可追溯 + 落库形态与 DB/ORM 双向锁死
# ═══════════════════════════════════════════════════════════════════════════

#: AC 8.1 要求的九个要素在 `working_paper_sync_conflict` 上的列名。
AC81_COLUMNS = {
    "stable_field_key",
    "business_label",
    "sheet_key",
    "table_key",
    "row_key",
    "json_pointer",
    "oo_location",
    "field_source",
    "protection_policy",
    "suggested_action",
    "conflict_kind",
    "base_value",
    "current_value",
    "incoming_value",
}


def _mixed_scenario(xc: C.SyncContract) -> M.MergeOutcome:
    """一次同时产出 value / protected / delete_update / schema 四类冲突的场景。"""
    base_vals = {
        **row_values(R1, name="甲", closing=1, subtotal=10),
        **row_values(R2, name="乙", closing=2),
        PERIOD: "2025年度",
    }
    cur_vals = dict(base_vals)
    cur_vals[ek(R1, "closing_amount")] = 111  # current 改 R1
    cur_vals[PERIOD] = "2026年度"
    inc_vals = dict(base_vals)
    inc_vals.pop(ek(R1, "name"))
    inc_vals.pop(ek(R1, "closing_amount"))
    inc_vals.pop(ek(R1, "subtotal"))  # incoming 删掉 R1 整行
    inc_vals[ek(R2, "closing_amount")] = "坏值"  # 类型规范化失败
    inc_vals[PERIOD] = "2027年度"  # 同字段异值
    return M.merge_projections(
        base=proj(xc, base_vals, row_keys={"equity_changes": (R1, R2)}),
        current=proj(xc, cur_vals, row_keys={"equity_changes": (R1, R2)}),
        incoming=proj(xc, inc_vals, row_keys={"equity_changes": (R2,)}),
        contract=xc,
    )


class TestProperty35ConflictTraceability:
    """每条冲突都能定位 JSON Pointer 与 OO cell/XPath，三方值与 kind 非空。"""

    def test_every_conflict_carries_both_side_locations_and_three_values(
        self, xc: C.SyncContract
    ) -> None:
        outcome = _mixed_scenario(xc)
        assert outcome.conflict_count >= 3
        kinds = {r.kind for r in outcome.conflicts}
        assert CF.ConflictKind.value in kinds
        assert CF.ConflictKind.delete_update in kinds
        assert CF.ConflictKind.schema in kinds
        for record in outcome.conflicts:
            loc = record.locator
            assert loc.json_pointer.startswith("/"), loc.stable_field_key
            assert loc.oo_location.strip()
            assert loc.business_label.strip()
            assert record.kind in CF.ConflictKind
            assert isinstance(record.base, CF.ValueEnvelope)
            assert isinstance(record.current, CF.ValueEnvelope)
            assert isinstance(record.incoming, CF.ValueEnvelope)
            assert len(record.reason) >= 8

    def test_xlsx_oo_location_is_cell_for_static_and_row_addressed_for_dynamic(
        self, xc: C.SyncContract
    ) -> None:
        index = M.ContractIndex(xc)
        assert index.resolve(PERIOD).oo_location == "G7 披露表!B2"
        dynamic = index.resolve(ek(R1, "closing_amount"))
        assert dynamic.oo_location == f"G7 披露表!H@row={R1}"
        assert R1 in dynamic.oo_location, "动态行地址必须携带行身份（行号不是稳定身份）"
        assert dynamic.json_pointer == f"/rows/{R1}/closingAmount"
        assert dynamic.row_key == R1
        assert dynamic.sheet_key == "g7-disclosure"
        assert dynamic.table_key == "equity_changes"

    def test_docx_oo_location_is_the_instantiated_sdt_tag(self, dc: C.SyncContract) -> None:
        index = M.ContractIndex(dc)
        loc = index.resolve(f"plan/members/{R1}/name")
        assert loc.oo_location == f"gt:field:f2.stocktake.plan:plan/members/{R1}/name"
        assert loc.field_source is CF.FieldSource.onlyoffice_sdt
        assert loc.row_key == R1

    def test_dedupe_key_matches_the_unique_constraint(self, xc: C.SyncContract) -> None:
        outcome = _mixed_scenario(xc)
        keys = [r.dedupe_key for r in outcome.conflicts]
        assert len(set(keys)) == len(keys)
        for record in outcome.conflicts:
            assert record.dedupe_key == (
                record.locator.stable_field_key,
                record.locator.row_key,
                record.locator.oo_location,
            )

    def test_duplicate_dedupe_key_in_a_set_is_rejected(self, xc: C.SyncContract) -> None:
        outcome = _mixed_scenario(xc)
        first = outcome.conflicts.records[0]
        with pytest.raises(CF.ConflictSetIntegrityError, match="uq_wpsc_field"):
            CF.ConflictSet((first, first))

    def test_conflict_kinds_match_the_database_check_constraint(self) -> None:
        """`ConflictKind` 与 V151 的 `ck_wpsc_conflict_kind` 逐字一致（双向）。"""
        sql = _read(_V151)
        match = re.search(
            r"ck_wpsc_conflict_kind\s+CHECK\s+\(conflict_kind\s+IN\s+\((?P<body>.*?)\)\)",
            sql,
            re.DOTALL,
        )
        assert match is not None, "未在 V151 找到 ck_wpsc_conflict_kind —— 锚点漂了"
        db_kinds = set(re.findall(r"'([a-z_]+)'", match.group("body")))
        assert db_kinds == {k.value for k in CF.ConflictKind}

    def test_row_covers_every_ac81_column(self, xc: C.SyncContract) -> None:
        from app.models.workpaper_sync_models import WorkpaperSyncConflict  # noqa: PLC0415

        orm_columns = {c.key for c in WorkpaperSyncConflict.__table__.columns}
        assert AC81_COLUMNS <= orm_columns, "AC 8.1 的列在 ORM 上缺失"
        outcome = _mixed_scenario(xc)
        for record in outcome.conflicts:
            row = record.to_row()
            assert set(row) == AC81_COLUMNS
            assert set(row) <= orm_columns
            assert row["base_value"] is not None and row["current_value"] is not None
            assert row["incoming_value"] is not None

    def test_grouped_by_sheet_table_row_for_the_preview(self, xc: C.SyncContract) -> None:
        outcome = _mixed_scenario(xc)
        grouped = outcome.conflicts.grouped()
        assert grouped, "冲突预览必须能按 sheet/table/row 分组（AC 8.2）"
        for (sheet, table, row), records in grouped.items():
            for record in records:
                assert (record.locator.sheet_key or "") == sheet
                assert (record.locator.table_key or "") == table
                assert record.locator.row_key == row

    def test_locator_rejects_empty_label_pointer_or_location(self) -> None:
        kwargs = dict(
            stable_field_key="a/b",
            business_label="标签",
            json_pointer="/a/b",
            oo_location="S!A1",
            field_source=CF.FieldSource.onlyoffice_cell,
            protection_policy=CF.ProtectionPolicy.editable,
            value_type=C.ValueType.text,
            mode=C.FieldMode.editable,
        )
        CF.FieldLocator(**kwargs)  # 正例
        for field, bad, pattern in (
            ("business_label", "  ", "business_label"),
            ("oo_location", "", "oo_location"),
            ("json_pointer", "a/b", "json_pointer"),
            ("stable_field_key", "", "stable_field_key"),
        ):
            with pytest.raises(CF.ConflictRecordError, match=pattern):
                CF.FieldLocator(**{**kwargs, field: bad})

    def test_four_rejection_types_are_pairwise_distinct(self) -> None:
        """🔴 同类型异常互相遮蔽是 Task 12/13 实测的最贵一类假绿 —— 双向断言不继承。"""
        types = [
            CF.ProtectedFieldOverrideError,
            CF.StructuralConflictNotAdjudicableError,
            CF.InstanceSelectionRequiredError,
            CF.UnknownConflictResolutionError,
            CF.UnresolvedConflictError,
        ]
        for a in types:
            for b in types:
                if a is b:
                    continue
                assert not issubclass(a, b), f"{a.__name__} 是 {b.__name__} 的子类 ⇒ 会互相遮蔽"
        codes = {t.error_code for t in types}
        assert len(codes) == len(types), "error_code 有重复，日志/告警无法分辨"


class TestStructuralConflicts:
    """结构/身份异常收成 `schema` 冲突，并把受影响区域 fail closed 在 current。"""

    def test_type_normalization_failure_keeps_raw_values_for_adjudication(
        self, xc: C.SyncContract
    ) -> None:
        key = ek(R2, "closing_amount")
        outcome = M.merge_projections(
            base=proj(xc, {key: 2}),
            current=proj(xc, {key: 2}),
            incoming=proj(xc, {key: "两块"}),
            contract=xc,
        )
        assert outcome.conflict_count == 1
        record = outcome.conflicts.records[0]
        assert record.kind is CF.ConflictKind.schema
        assert record.schema_anomaly is CF.SchemaAnomalyKind.type_normalization_failure
        assert record.incoming == CF.ValueEnvelope.of("两块")  # 原值保留供裁决
        assert outcome.value_of(key) == CF.ValueEnvelope.of(2)
        assert record.adjudicable_by_value_choice is True

    def test_missing_static_carrier_in_incoming_fails_closed(
        self, xc: C.SyncContract
    ) -> None:
        """静态受管格在 incoming 消失 = 载体漂移 ⇒ schema 冲突，不按位置猜测。"""
        outcome = M.merge_projections(
            base=proj(xc, {PERIOD: "2025年度"}),
            current=proj(xc, {PERIOD: "2025年度"}),
            incoming=proj(xc, {}),
            contract=xc,
        )
        assert outcome.conflict_count == 1
        record = outcome.conflicts.records[0]
        assert record.schema_anomaly is CF.SchemaAnomalyKind.missing_identity_carrier
        assert outcome.value_of(PERIOD) == CF.ValueEnvelope.of("2025年度")

    def test_reported_row_identity_anomaly_blocks_only_that_row(
        self, xc: C.SyncContract
    ) -> None:
        base_vals = {
            **row_values(R1, name="甲", closing=1),
            **row_values(R2, name="乙", closing=2),
        }
        inc_vals = dict(base_vals)
        inc_vals[ek(R1, "closing_amount")] = 111
        inc_vals[ek(R2, "closing_amount")] = 222
        outcome = M.merge_projections(
            base=proj(xc, base_vals, row_keys={"equity_changes": (R1, R2)}),
            current=proj(xc, base_vals, row_keys={"equity_changes": (R1, R2)}),
            incoming=proj(xc, inc_vals, row_keys={"equity_changes": (R1, R2)}),
            contract=xc,
            structural_anomalies=[
                M.StructuralAnomaly(
                    kind=CF.SchemaAnomalyKind.duplicate_row_identity,
                    stable_field_key=ek(R1, "name"),
                    detail=f"复制行产生重复 row UUID {R1}，无法判定归属",
                    row_key=R1,
                    table_key="equity_changes",
                    blocks_row_key=R1,
                )
            ],
        )
        assert outcome.conflict_count == 1
        record = outcome.conflicts.records[0]
        assert record.schema_anomaly is CF.SchemaAnomalyKind.duplicate_row_identity
        assert record.adjudicable_by_value_choice is False
        assert record.suggested_action is CF.SuggestedAction.fix_structure
        # 被封锁行保持 current；未受影响行照常合并
        assert outcome.value_of(ek(R1, "closing_amount")) == CF.ValueEnvelope.of(1)
        assert outcome.value_of(ek(R2, "closing_amount")) == CF.ValueEnvelope.of(222)
        assert outcome.verdicts[ek(R1, "name")] is M.FieldVerdict.held_by_schema_conflict

    def test_key_level_anomaly_blocks_only_that_key(self, xc: C.SyncContract) -> None:
        """不带 `blocks_row_key` 的异常只封锁**自己那个键**，同表其他键照常合并。

        🔴 与 `test_reported_row_identity_anomaly_blocks_only_that_row` 是两条封锁路径：
        前者靠 `blocked_rows`（整行），本条靠 `blocked_keys`（单键）。只测行级那条时，
        把 `blocked_keys.update(...)` 整个短路掉不会打红 —— 变异 M48 首轮实测判 GREEN
        正是这个缺口。
        """
        base_vals = {PERIOD: "2025年度", TOTAL: 100}
        inc_vals = {PERIOD: "OO 改的期间", TOTAL: 200}
        outcome = M.merge_projections(
            base=proj(xc, base_vals),
            current=proj(xc, base_vals),
            incoming=proj(xc, inc_vals),
            contract=xc,
            structural_anomalies=[
                M.StructuralAnomaly(
                    kind=CF.SchemaAnomalyKind.type_normalization_failure,
                    stable_field_key=PERIOD,
                    detail="该格内容含无法规范化的控制字符，保留原值供裁决",
                    table_key="header_block",
                )
            ],
        )
        assert outcome.conflict_count == 1
        assert outcome.conflicts.records[0].locator.stable_field_key == PERIOD
        # 被封锁的键 hold 在 current；同表未受影响的键照常采纳 OO 改动
        assert outcome.verdicts[PERIOD] is M.FieldVerdict.held_by_schema_conflict
        assert outcome.value_of(PERIOD) == CF.ValueEnvelope.of("2025年度")
        assert outcome.verdicts[TOTAL] is M.FieldVerdict.took_incoming
        assert outcome.value_of(TOTAL) == CF.ValueEnvelope.of(200)

    def test_identity_anomaly_cannot_be_resolved_by_picking_a_side(
        self, xc: C.SyncContract
    ) -> None:
        outcome = M.merge_projections(
            base=proj(xc, row_values(R1, name="甲", closing=1)),
            current=proj(xc, row_values(R1, name="甲", closing=1)),
            incoming=proj(xc, row_values(R1, name="甲", closing=2)),
            contract=xc,
            structural_anomalies=[
                M.StructuralAnomaly(
                    kind=CF.SchemaAnomalyKind.empty_row_identity,
                    stable_field_key=ek(R1, "name"),
                    detail="OO 新增行的 row UUID 为空，无法定位持久化身份",
                    row_key=R1,
                    table_key="equity_changes",
                    blocks_row_key=R1,
                )
            ],
        )
        record = outcome.conflicts.records[0]
        with pytest.raises(CF.StructuralConflictNotAdjudicableError, match="empty_row_identity"):
            CF.resolved_value_for(
                record,
                CF.ResolutionChoice(
                    stable_field_key=record.locator.stable_field_key,
                    row_key=record.locator.row_key,
                    oo_location=record.locator.oo_location,
                    kind=CF.ResolutionKind.take_incoming,
                ),
            )

    def test_anomaly_outside_the_contract_must_bring_its_own_traceability(
        self, xc: C.SyncContract
    ) -> None:
        bare = M.StructuralAnomaly(
            kind=CF.SchemaAnomalyKind.unknown_stable_key,
            stable_field_key="ghost/field",
            detail="OO 里出现契约未登记的受管键 ghost/field",
        )
        with pytest.raises(M.MergeInputError, match="business_label"):
            M.merge_projections(
                base=proj(xc, {}),
                current=proj(xc, {}),
                incoming=proj(xc, {}),
                contract=xc,
                structural_anomalies=[bare],
            )
        rich = M.StructuralAnomaly(
            kind=CF.SchemaAnomalyKind.unknown_stable_key,
            stable_field_key="ghost/field",
            detail="OO 里出现契约未登记的受管键 ghost/field",
            business_label="未登记字段",
            json_pointer="/ghost/field",
            oo_location="G7 披露表!ZZ1",
        )
        outcome = M.merge_projections(
            base=proj(xc, {}),
            current=proj(xc, {}),
            incoming=proj(xc, {}),
            contract=xc,
            structural_anomalies=[rich],
        )
        assert outcome.conflicts.records[0].locator.business_label == "未登记字段"

    def test_unknown_stable_key_in_a_projection_fails_closed(
        self, xc: C.SyncContract
    ) -> None:
        rogue = Projection(
            contract_id=xc.contract_id,
            semantic_version=xc.semantic_version,
            document_type=xc.document_type,
            values={
                "header_block/period_label": FieldValue(
                    stable_key="header_block/period_label",
                    value="x",
                    value_type=C.ValueType.text,
                    mode=C.FieldMode.editable,
                )
            },
        )
        # 契约内的键正常
        M.merge_projections(base=rogue, current=rogue, incoming=rogue, contract=xc)
        # 契约外的键必须在 projection 层就被拒（Task 13 的 assert_matches_contract）
        with pytest.raises(SyncDomainError):
            M.merge_projections(
                base=rogue,
                current=rogue,
                incoming=Projection(
                    contract_id=xc.contract_id,
                    semantic_version=xc.semantic_version,
                    document_type=xc.document_type,
                    values={
                        "ghost/field": FieldValue(
                            stable_key="ghost/field",
                            value="x",
                            value_type=C.ValueType.text,
                            mode=C.FieldMode.editable,
                        )
                    },
                ),
                contract=xc,
            )

    def test_schema_conflict_without_anomaly_kind_is_rejected(self) -> None:
        """`schema` 冲突必须给出 `schema_anomaly`，非 schema 冲突不得携带它 —— 双向。

        这两条是**同一个 `__post_init__` 的两个方向**：少了前者「结构哪里坏了」不可诊断
        （AC 5.12），少了后者 `adjudicable_by_value_choice` 会拿别的 kind 去查异常表。
        """
        loc = CF.FieldLocator(
            stable_field_key=PERIOD,
            business_label="期间",
            json_pointer="/header/periodLabel",
            oo_location="G7 披露表!B2",
            field_source=CF.FieldSource.onlyoffice_cell,
            protection_policy=CF.ProtectionPolicy.editable,
            value_type=C.ValueType.text,
            mode=C.FieldMode.editable,
        )
        common = dict(
            locator=loc,
            base=CF.ValueEnvelope.of("A"),
            current=CF.ValueEnvelope.of("B"),
            incoming=CF.ValueEnvelope.of("C"),
            suggested_action=CF.SuggestedAction.manual_merge,
            reason="足够长的原因文案",
        )
        with pytest.raises(CF.ConflictRecordError, match="必须给出 schema_anomaly"):
            CF.ConflictRecord(**common, kind=CF.ConflictKind.schema)
        with pytest.raises(CF.ConflictRecordError, match="只有 schema 冲突"):
            CF.ConflictRecord(
                **common,
                kind=CF.ConflictKind.value,
                schema_anomaly=CF.SchemaAnomalyKind.empty_row_identity,
            )
        # 正例：kind 与 schema_anomaly 匹配时可构造，且分类结果可查
        ok = CF.ConflictRecord(
            **common,
            kind=CF.ConflictKind.schema,
            schema_anomaly=CF.SchemaAnomalyKind.empty_row_identity,
        )
        assert ok.adjudicable_by_value_choice is False

    def test_contract_index_rejects_prefix_only_matches(self, xc: C.SyncContract) -> None:
        index = M.ContractIndex(xc)
        with pytest.raises(M.UnknownStableKeyError):
            index.resolve(f"equity_changes/{R1}/closing_amount/extra")
        with pytest.raises(M.UnknownStableKeyError):
            index.resolve("equity_changes/closing_amount")

    def test_contract_index_rejects_row_key_disagreement(self, xc: C.SyncContract) -> None:
        index = M.ContractIndex(xc)
        with pytest.raises(M.MergeInputError, match="行身份只有一个真源"):
            index.resolve(ek(R1, "name"), declared_row_key=R2)


# ═══════════════════════════════════════════════════════════════════════════
# 10. conflict_set_digest（AC 8.5 的乐观锁材料）
# ═══════════════════════════════════════════════════════════════════════════


class TestConflictSetDigest:
    def test_digest_is_deterministic_and_order_insensitive(self, xc: C.SyncContract) -> None:
        outcome = _mixed_scenario(xc)
        records = outcome.conflicts.records
        assert len(records) >= 2
        forward = CF.ConflictSet(records).digest
        backward = CF.ConflictSet(tuple(reversed(records))).digest
        assert forward == backward == CF.ConflictSet(records).digest
        assert len(forward) == 64

    def test_digest_changes_when_any_of_the_three_values_changes(
        self, xc: C.SyncContract
    ) -> None:
        outcome = single(xc, "A", "B", "C", key=PERIOD)
        original = outcome.conflicts.digest
        variants = {
            # 🔴 base 这一路必须单独覆盖：只变 current/incoming 时，把 `"base"` 从
            # `digest_payload()` 里摘掉照样算出不同的摘要 ⇒ 变异 M56 首轮实测判
            # WRONG-TEST（红的是别的测试）。测试名说「三值中任一变化」，就得真有三路。
            "base": single(xc, "X", "B", "C", key=PERIOD),
            "current": single(xc, "A", "Z", "C", key=PERIOD),
            "incoming": single(xc, "A", "B", "D", key=PERIOD),
        }
        for side, other in variants.items():
            assert other.conflicts.digest != original, (
                f"只变 {side} 时摘要没变 ⇒ 该侧未进 conflict_set_digest，"
                "fence 会把已变的冲突集判成「没变」"
            )

    def test_empty_set_has_a_stable_non_empty_digest(self) -> None:
        empty = CF.ConflictSet(()).digest
        assert len(empty) == 64 and set(empty) != {"0"}
        assert empty == CF.ConflictSet(()).digest


# ═══════════════════════════════════════════════════════════════════════════
# 11. resolve fence（AC 8.5）
# ═══════════════════════════════════════════════════════════════════════════

APP_ID = uuid.UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
OTHER_APP = uuid.UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
DIGEST = _d("conflict-set")


def fence_request(**over: Any) -> CF.ResolveFenceRequest:
    kwargs: dict[str, Any] = dict(
        expected_current_revision=7,
        room_generation=3,
        client_edit_epoch=5,
        canonical_application_id=APP_ID,
        application_effective_request_sequence=9,
        room_latest_durable_application_id=APP_ID,
        room_latest_durable_sequence=9,
        conflict_set_digest=DIGEST,
    )
    kwargs.update(over)
    return CF.ResolveFenceRequest(**kwargs)


def app_fence(**over: Any) -> CF.FrozenApplicationFence:
    kwargs: dict[str, Any] = dict(
        canonical_application_id=APP_ID,
        effective_request_sequence=9,
        write_fence_epoch=2,
        initiator_permission_epoch=4,
        client_edit_epoch=5,
    )
    kwargs.update(over)
    return CF.FrozenApplicationFence(**kwargs)


def room_fence(**over: Any) -> CF.RoomDurableFence:
    kwargs: dict[str, Any] = dict(
        generation=3,
        write_fence_epoch=2,
        initiator_permission_epoch=4,
        state_is_refresh_required=False,
        latest_durable_application_id=APP_ID,
        latest_durable_sequence=9,
        current_revision=7,
        conflict_set_digest=DIGEST,
    )
    kwargs.update(over)
    return CF.RoomDurableFence(**kwargs)


def _scope(**over: Any) -> OperationScope:
    kwargs: dict[str, Any] = dict(
        operation_id=uuid.uuid4(),
        project_id=uuid.UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc"),
        wp_id=uuid.UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd"),
        entry_id="G7Tab@GtOnlyOfficeSheet",
        room_id=uuid.UUID("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"),
        definition_bundle_id=uuid.UUID("ffffffff-ffff-4fff-8fff-ffffffffffff"),
        authority_model_definition_sha256=_d("authority"),
        application_id=None,
        duplicate_of_operation_id=None,
        state=OperationState.duplicate,
    )
    kwargs.update(over)
    return OperationScope(**kwargs)


class TestResolveFence:
    """AC 8.5 的不可交换顺序，逐步返回可分辨的 reason。"""

    def test_all_fences_match_proceeds(self) -> None:
        ev = CF.evaluate_resolve_fence(
            request=fence_request(), application=app_fence(), room=room_fence()
        )
        assert ev.decision is CF.FenceDecision.proceed
        assert ev.reason is CF.FenceReason.ok
        assert ev.may_apply is True
        assert ev.normalized_effective_request_sequence == 9

    def test_same_application_higher_sequence_folds_and_never_supersedes_itself(self) -> None:
        """🔴 same-app fold 不得判 stale / 不得 supersede 自己（AC 8.5 明文）。"""
        ev = CF.evaluate_resolve_fence(
            request=fence_request(application_effective_request_sequence=6),
            application=app_fence(effective_request_sequence=11),
            room=room_fence(latest_durable_application_id=APP_ID, latest_durable_sequence=11),
        )
        assert ev.decision is CF.FenceDecision.fold
        assert ev.reason is CF.FenceReason.same_application_sequence_fold
        assert ev.decision is not CF.FenceDecision.superseded
        assert ev.normalized_effective_request_sequence == 11
        assert ev.may_apply is True

    def test_newer_different_canonical_application_supersedes(self) -> None:
        ev = CF.evaluate_resolve_fence(
            request=fence_request(),
            application=app_fence(effective_request_sequence=9),
            room=room_fence(
                latest_durable_application_id=OTHER_APP, latest_durable_sequence=12
            ),
        )
        assert ev.decision is CF.FenceDecision.superseded
        assert ev.reason is CF.FenceReason.newer_canonical_application
        assert ev.may_apply is False

    def test_older_different_canonical_application_does_not_supersede(self) -> None:
        ev = CF.evaluate_resolve_fence(
            request=fence_request(),
            application=app_fence(effective_request_sequence=9),
            room=room_fence(
                latest_durable_application_id=OTHER_APP, latest_durable_sequence=4
            ),
        )
        assert ev.decision is CF.FenceDecision.proceed

    def test_current_revision_change_rebases(self) -> None:
        ev = CF.evaluate_resolve_fence(
            request=fence_request(expected_current_revision=7),
            application=app_fence(),
            room=room_fence(current_revision=8),
        )
        assert ev.decision is CF.FenceDecision.rebase
        assert ev.reason is CF.FenceReason.current_revision_changed
        assert ev.may_apply is False

    @pytest.mark.parametrize(
        ("req_over", "app_over", "room_over", "reason"),
        [
            ({"canonical_application_id": OTHER_APP}, {}, {}, CF.FenceReason.canonical_application_mismatch),
            ({"room_generation": 2}, {}, {}, CF.FenceReason.room_generation_changed),
            ({}, {}, {"write_fence_epoch": 3}, CF.FenceReason.write_fence_changed),
            ({}, {}, {"initiator_permission_epoch": 5}, CF.FenceReason.permission_epoch_changed),
            ({"client_edit_epoch": 6}, {}, {}, CF.FenceReason.client_edit_epoch_changed),
            ({}, {}, {"state_is_refresh_required": True}, CF.FenceReason.room_refresh_required),
            ({}, {}, {"conflict_set_digest": _d("other")}, CF.FenceReason.conflict_set_changed),
        ],
    )
    def test_each_fence_break_has_its_own_reason(
        self,
        req_over: dict,
        app_over: dict,
        room_over: dict,
        reason: CF.FenceReason,
    ) -> None:
        ev = CF.evaluate_resolve_fence(
            request=fence_request(**req_over),
            application=app_fence(**app_over),
            room=room_fence(**room_over),
        )
        assert ev.decision is CF.FenceDecision.rejected
        assert ev.reason is reason
        assert ev.may_apply is False
        assert reason.value in {r.value for r in CF.FenceReason}

    def test_every_reason_message_is_pairwise_distinct(self) -> None:
        """🔴 文案重合会让「哪条判据在起作用」不可分辨 ⇒ 短路一条会被另一条遮蔽。"""
        assert set(CF.FENCE_REASON_MESSAGES) == set(CF.FenceReason)
        messages = list(CF.FENCE_REASON_MESSAGES.values())
        assert len(set(messages)) == len(messages)
        assert all(len(m) >= 8 for m in messages)

    def test_valid_duplicate_link_is_canonicalized(self) -> None:
        primary = _scope(application_id=APP_ID, state=OperationState.applied)
        requested = _scope(duplicate_of_operation_id=primary.operation_id)
        ev = CF.evaluate_resolve_fence(
            request=fence_request(),
            application=app_fence(),
            room=room_fence(),
            duplicate_link=CF.RequestedOperationLink(requested=requested, primary=primary),
        )
        assert ev.decision is CF.FenceDecision.proceed
        assert ev.canonical_application_id == APP_ID

    @pytest.mark.parametrize(
        ("broken", "needle"),
        [
            ("self", "self-reference"),
            ("chain_pointer", "禁止链与环"),
            ("chain_state", "禁止链与环"),
            ("stranded", "stranded"),
            ("cross_scope", "跨 scope"),
            ("cross_bundle", "frozen bundle"),
        ],
    )
    def test_invalid_duplicate_link_is_rejected_before_canonicalize(
        self, broken: str, needle: str
    ) -> None:
        """六种非法直指各自**只触发一条**判据，并断言到自己那句话。

        🔴 只断言「reason 是 requested_duplicate_link_invalid + detail 非空」不够：
        六条禁令共用 `DuplicateLinkError` 且都会被收成同一个 reason，一个变异短路掉
        其中一条时，另一条会因为同一份输入也不合法而把它遮蔽 ⇒ 判定 GREEN。
        因此每个反例都构造成「其余五条都成立、只坏一条」，并 match 各自的可分辨文案。
        `chain_pointer` / `chain_state` 是同一个 `if` 的两个面（`models.assert_direct_primary`
        的注释明确要求逐面覆盖）。
        """
        primary = _scope(application_id=APP_ID, state=OperationState.applied)
        requested = _scope(duplicate_of_operation_id=primary.operation_id)
        if broken == "self":
            requested = _scope(duplicate_of_operation_id=requested.operation_id)
            primary = requested
        elif broken == "chain_pointer":
            # 指针面：已绑定同一 application，唯一的错是自己也带 duplicate_of。
            primary = _scope(
                operation_id=primary.operation_id, application_id=APP_ID,
                duplicate_of_operation_id=uuid.uuid4(), state=OperationState.applied,
            )
        elif broken == "chain_state":
            # state 面：指针为空，唯一的错是 state=duplicate。
            primary = _scope(
                operation_id=primary.operation_id, application_id=APP_ID,
                duplicate_of_operation_id=None, state=OperationState.duplicate,
            )
        elif broken == "stranded":
            # 未绑定 application 的 pre-correlation shell（Task 10 的 stranded 形态）。
            primary = _scope(
                operation_id=primary.operation_id, application_id=None,
                state=OperationState.waiting_application,
            )
        elif broken == "cross_scope":
            primary = _scope(
                operation_id=primary.operation_id, application_id=APP_ID,
                state=OperationState.applied, entry_id="OtherEntry@Host",
            )
        else:
            primary = _scope(
                operation_id=primary.operation_id, application_id=APP_ID,
                state=OperationState.applied, definition_bundle_id=uuid.uuid4(),
            )
        ev = CF.evaluate_resolve_fence(
            request=fence_request(),
            application=app_fence(),
            room=room_fence(),
            duplicate_link=CF.RequestedOperationLink(requested=requested, primary=primary),
        )
        assert ev.decision is CF.FenceDecision.rejected
        assert ev.reason is CF.FenceReason.requested_duplicate_link_invalid
        assert ev.detail, "必须带上 models.assert_direct_primary 的具体成因"
        assert needle in ev.detail, (
            f"{broken} 的 detail 未点名自己的成因（实得 {ev.detail!r}）—— "
            "六条禁令共用异常类型，不断言可分辨文案就会互相遮蔽"
        )

    def test_duplicate_link_requires_a_terminal_duplicate_requested_operation(self) -> None:
        primary = _scope(application_id=APP_ID, state=OperationState.applied)
        with pytest.raises(CF.ResolveFenceError, match="terminal duplicate"):
            CF.evaluate_resolve_fence(
                request=fence_request(),
                application=app_fence(),
                room=room_fence(),
                duplicate_link=CF.RequestedOperationLink(requested=primary, primary=primary),
            )

    def test_request_rejects_malformed_digest_and_negative_counters(self) -> None:
        with pytest.raises(CF.ResolveFenceError, match="conflict_set_digest"):
            fence_request(conflict_set_digest="0" * 64)
        with pytest.raises(CF.ResolveFenceError, match="room_generation"):
            fence_request(room_generation=-1)

# ═══════════════════════════════════════════════════════════════════════════
# 12. Hypothesis 属性：幂等 / 未改保持 / 不同字段合并 / 同字段不选边
# ═══════════════════════════════════════════════════════════════════════════

#: 属性检验用的契约实例。**不用 fixture** —— `@given` 与函数级 fixture 混用会让
#: hypothesis 在同一个 fixture 实例上跑全部样例（health check 会警告），
#: 契约本身又是不可变值对象，模块级常量最直白。
_XC: Final = C.parse_contract(xlsx_payload())

#: 非受保护的可编辑受管键：两个静态格 + 两行各两个动态格。
#: 「不同字段自动合并」只在非受保护字段上成立（受保护字段的 OO 改动按 AC 6.6 必冲突），
#: 所以 P25 的属性用这一组；P24 的反例另有定向测试。
_EDITABLE_KEYS: Final[tuple[str, ...]] = (
    PERIOD,
    TOTAL,
    ek(R1, "name"),
    ek(R1, "closing_amount"),
    ek(R2, "name"),
    ek(R2, "closing_amount"),
)
_PROTECTED_KEYS: Final[tuple[str, ...]] = (
    ek(R1, "subtotal"),
    ek(R1, "tb_amount"),
    ek(R1, "masked_note"),
)
_ALL_MANAGED_KEYS: Final[tuple[str, ...]] = _EDITABLE_KEYS + _PROTECTED_KEYS

_TEXT_KEYS: Final[frozenset[str]] = frozenset(
    {PERIOD, ek(R1, "name"), ek(R2, "name"), ek(R1, "masked_note")}
)

_ROW_KEYS: Final[dict[str, tuple[str, ...]]] = {"equity_changes": (R1, R2)}

#: 文本取值字母表刻意**排除** CR/LF/BOM/NBSP/零宽：那些字面量在规范化后会与别的值判等，
#: 会让「两值不同」的前提在属性内部失效。规范化本身的折叠/不折叠方向由
#: `TestTypeNormalization` 的定向反例逐条覆盖，属性检验不重复它。
_TEXT_ALPHABET: Final[str] = "甲乙丙丁戊ABCXYZxyz0123 -_"


def _value_st(key: str) -> st.SearchStrategy[Any]:
    """按 contract 声明的 value_type 生成值；策略对每个键都是**单射**的。

    单射很关键：属性里要用 `assume(a != b)` 表达「两值不同」，若策略能把两个不同的
    抽样映射到规范化后相等的值（`Decimal("1.1")` 与 `Decimal("1.10")`、
    `"a\\r\\nb"` 与 `"a\\nb"`），前提就会假成立而断言随之失真。
    """
    if key in _TEXT_KEYS:
        return st.text(alphabet=_TEXT_ALPHABET, min_size=0, max_size=10)
    return st.integers(min_value=-1_000_000, max_value=1_000_000).map(
        lambda n: Decimal(n) / 100
    )


def _side_st(
    keys: tuple[str, ...], *, allow_missing: bool
) -> st.SearchStrategy[dict[str, Any]]:
    """一侧 projection 的取值字典。`allow_missing=True` 时该键可能整个不存在。"""

    def one(key: str) -> st.SearchStrategy[Any]:
        base = _value_st(key)
        return st.one_of(st.just(M.MISSING), base) if allow_missing else base

    return st.fixed_dictionaries({key: one(key) for key in keys})


def _side(values: Mapping[str, Any]) -> Projection:
    return proj(_XC, values, row_keys=_ROW_KEYS)


def _envs(
    projection: Projection, keys: tuple[str, ...]
) -> dict[str, CF.ValueEnvelope]:
    """把 projection 投影成 `键 → 信封`（缺键 = absent），用于逐键等值比较。

    刻意**不**用 `values_equal` 做比较 —— merged 里存的是胜出那一侧的**原值**，
    直接等值比较比「规范化后相等」更强，能抓到「值被悄悄改写成规范化形态」。
    """
    out: dict[str, CF.ValueEnvelope] = {}
    for key in keys:
        field = projection.get(key)
        out[key] = (
            CF.ValueEnvelope.absent() if field is None else CF.ValueEnvelope.of(field.value)
        )
    return out


class TestProperty25And26Hypothesis:
    """任务点名的四条 Hypothesis 属性。四条都是**全称命题**，不是穿了 `@given` 的定向例。"""

    # ── 属性一：幂等 ────────────────────────────────────────────────────
    @_HYP
    @given(side=_side_st(_ALL_MANAGED_KEYS, allow_missing=True))
    def test_property_merge_of_three_identical_sides_is_the_identity(
        self, side: dict[str, Any]
    ) -> None:
        """`merge(p, p, p).merged ≡ p`，零冲突、零 conflict verdict。

        含受保护键：`i == b` 时保护判据不触发，所以「稳定态不产生冲突」对全部受管键成立。

        **Validates: Requirements 6.7**
        """
        p = _side(side)
        outcome = M.merge_projections(base=p, current=p, incoming=p, contract=_XC)
        assert outcome.conflict_count == 0, (
            f"稳定态却报出 {outcome.conflict_count} 条冲突: "
            f"{[r.locator.stable_field_key for r in outcome.conflicts]}"
        )
        assert set(outcome.merged.values) == set(p.values), "键集合变了"
        assert _envs(outcome.merged, _ALL_MANAGED_KEYS) == _envs(p, _ALL_MANAGED_KEYS)
        assert not [v for v in outcome.verdicts.values() if v.is_conflict]

    @_HYP
    @given(
        b=_side_st(_ALL_MANAGED_KEYS, allow_missing=True),
        c=_side_st(_ALL_MANAGED_KEYS, allow_missing=True),
        i=_side_st(_ALL_MANAGED_KEYS, allow_missing=True),
    )
    def test_property_merged_result_is_a_fixpoint(
        self, b: dict[str, Any], c: dict[str, Any], i: dict[str, Any]
    ) -> None:
        """任意三方 merge 的结果再喂回三侧 ⇒ 不变且零冲突（`settled_projection` 的语义）。

        这是 AC 8.10 的域内形态：canonical rematerialize 把 merged 写回 incoming
        substrate，于是三方同时前进到 merged。**不加 `assume`** —— 第一次 merge 有冲突时
        merged 被 hold 在 current，二次 merge 仍必须是不动点。

        **Validates: Requirements 6.7**
        """
        first = M.merge_projections(
            base=_side(b), current=_side(c), incoming=_side(i), contract=_XC
        )
        settled = M.settled_projection(first)
        second = M.merge_projections(
            base=settled, current=settled, incoming=settled, contract=_XC
        )
        assert second.conflict_count == 0, (
            "稳定态二次 merge 仍报冲突 ⇒ merged 不是不动点: "
            f"{[r.locator.stable_field_key for r in second.conflicts]}"
        )
        assert _envs(second.merged, _ALL_MANAGED_KEYS) == _envs(
            settled, _ALL_MANAGED_KEYS
        )
        assert set(second.merged.values) == set(settled.values)

    # ── 属性二：未改保持 ────────────────────────────────────────────────
    @_HYP
    @given(
        b=_side_st(_ALL_MANAGED_KEYS, allow_missing=True),
        c=_side_st(_ALL_MANAGED_KEYS, allow_missing=True),
    )
    def test_property_untouched_incoming_preserves_current_everywhere(
        self, b: dict[str, Any], c: dict[str, Any]
    ) -> None:
        """`incoming == base`（OO 一个字都没动）⇒ merged 逐键等于 current，且零冲突。

        AC 6.7「仅 current 变更则保 current」的全称形态。三个方向一起锁：

        * current 改过的键：保 current 的**新**值，不被 base 打回
        * current 删掉的键：merged 也没有（absent 不得被 base 复活）
        * current 新增的键：merged 有（含 base 里没有的键）

        **Validates: Requirements 6.7**
        """
        outcome = M.merge_projections(
            base=_side(b), current=_side(c), incoming=_side(b), contract=_XC
        )
        assert outcome.conflict_count == 0, (
            "OO 未改动却产生冲突: "
            f"{[(r.locator.stable_field_key, r.kind.value) for r in outcome.conflicts]}"
        )
        assert _envs(outcome.merged, _ALL_MANAGED_KEYS) == _envs(
            _side(c), _ALL_MANAGED_KEYS
        ), "merged 与 current 不逐键相等 ⇒ OO 未改动却改变了服务端值"
        assert not [
            key for key, v in outcome.verdicts.items() if v is M.FieldVerdict.took_incoming
        ], "OO 未改动却出现 took_incoming"

    # ── 属性三：不同字段自动合并 ────────────────────────────────────────
    @_HYP
    @given(
        base_side=_side_st(_EDITABLE_KEYS, allow_missing=False),
        delta=_side_st(_EDITABLE_KEYS, allow_missing=False),
        owners=st.lists(
            st.sampled_from(("c", "i", "-")),
            min_size=len(_EDITABLE_KEYS),
            max_size=len(_EDITABLE_KEYS),
        ),
    )
    def test_property_disjoint_field_edits_merge_without_conflict(
        self, base_side: dict[str, Any], delta: dict[str, Any], owners: list[str]
    ) -> None:
        """键被任意划分给 current / incoming / 不动 ⇒ 三边各自的改动全部进 merged，零冲突。

        Property 25 的全称形态：不再是「current 改 A、incoming 改 B」这一个例子，而是
        6 个键的 3^6 种归属划分（含跨行、跨静态/动态）都成立。

        `assume` 只用来保证**非空**：两侧各至少有一个**真的**改动，否则命题退化成
        「两侧都没改 ⇒ 没冲突」这种恒真空转。

        **Validates: Requirements 6.8**
        """
        owned = dict(zip(_EDITABLE_KEYS, owners))
        index = M.ContractIndex(_XC)

        def really_changed(key: str) -> bool:
            vt = index.resolve(key).value_type
            return not M.values_equal(delta[key], base_side[key], vt)

        changed_by_current = [
            k for k in _EDITABLE_KEYS if owned[k] == "c" and really_changed(k)
        ]
        changed_by_incoming = [
            k for k in _EDITABLE_KEYS if owned[k] == "i" and really_changed(k)
        ]
        assume(changed_by_current and changed_by_incoming)

        current = {k: (delta[k] if owned[k] == "c" else base_side[k]) for k in _EDITABLE_KEYS}
        incoming = {k: (delta[k] if owned[k] == "i" else base_side[k]) for k in _EDITABLE_KEYS}
        outcome = M.merge_projections(
            base=_side(base_side),
            current=_side(current),
            incoming=_side(incoming),
            contract=_XC,
        )
        assert outcome.conflict_count == 0, (
            "不相交字段的并行修改却产生冲突: "
            f"{[(r.locator.stable_field_key, r.kind.value) for r in outcome.conflicts]}"
        )
        expected = {
            k: CF.ValueEnvelope.of(delta[k] if owned[k] in ("c", "i") else base_side[k])
            for k in _EDITABLE_KEYS
        }
        assert _envs(outcome.merged, _EDITABLE_KEYS) == expected, (
            "merged 未同时包含两侧的改动 ⇒ 有一侧被静默丢弃"
        )
        auto = set(outcome.auto_merged_keys)
        assert set(changed_by_incoming) <= auto, (
            f"OO 侧真改过的键 {changed_by_incoming} 未被计入 auto_merged_keys {sorted(auto)}"
        )
        for key in changed_by_current:
            assert outcome.verdicts[key] is M.FieldVerdict.kept_current
        for key in changed_by_incoming:
            assert outcome.verdicts[key] is M.FieldVerdict.took_incoming

    # ── 属性四：同字段不自动选边 ────────────────────────────────────────
    @_HYP
    @given(data=st.data())
    def test_property_same_field_three_values_never_auto_picks_a_side(
        self, data: st.DataObject
    ) -> None:
        """任意三个互异值落在同一个键上 ⇒ 必冲突、merged 保持 current、绝不等于 incoming。

        🔴 这是**否定式**承诺（「不得应用任一侧」），断言因此必须同时压住三个方向：

        1. merged **等于** current（不是 incoming、不是 base、不是某种「合并猜测」）
        2. merged **不等于** incoming（last-write-wins 的直接反例）
        3. 冲突记录带全三值 + JSON Pointer + OO 地址（P26 的「三值完整」与 P35）
        4. 不给裁决就要 merged projection ⇒ 抛 `UnresolvedConflictError`，
           而不是回落到任一侧

        用 `st.data()` 交互抽样是为了让三个值与被抽中的键**类型一致**
        （text 键抽字符串、amount 键抽 Decimal）。

        **Validates: Requirements 6.8**
        """
        key = data.draw(st.sampled_from(_EDITABLE_KEYS), label="stable_field_key")
        vt = M.ContractIndex(_XC).resolve(key).value_type
        b = data.draw(_value_st(key), label="base")
        c = data.draw(_value_st(key), label="current")
        i = data.draw(_value_st(key), label="incoming")
        assume(
            not M.values_equal(b, c, vt)
            and not M.values_equal(b, i, vt)
            and not M.values_equal(c, i, vt)
        )
        outcome = M.merge_projections(
            base=_side({key: b}),
            current=_side({key: c}),
            incoming=_side({key: i}),
            contract=_XC,
        )
        assert outcome.conflict_count == 1
        assert outcome.verdicts[key] is M.FieldVerdict.conflict_value
        record = outcome.conflicts.records[0]
        assert record.kind is CF.ConflictKind.value
        assert (record.base, record.current, record.incoming) == (
            CF.ValueEnvelope.of(b),
            CF.ValueEnvelope.of(c),
            CF.ValueEnvelope.of(i),
        ), "冲突记录的三值不完整或被规范化改写"
        assert outcome.value_of(key) == CF.ValueEnvelope.of(c), "merged 不等于 current"
        assert outcome.value_of(key) != CF.ValueEnvelope.of(i), "merged 取了 incoming ⇒ 自动选边"
        assert outcome.value_of(key) != CF.ValueEnvelope.of(b), "merged 回落到 base"
        assert record.locator.json_pointer.startswith("/")
        assert record.locator.oo_location.strip()
        # 行身份必须来自 stable key 本身：行域键带具体行 UUID，静态键为空串。
        expected_row = key.split("/")[1] if key.startswith("equity_changes/") else ""
        assert record.locator.row_key == expected_row, (
            f"{key} 的 row_key 应为 {expected_row!r}，实得 {record.locator.row_key!r}"
        )
        with pytest.raises(CF.UnresolvedConflictError):
            M.apply_resolutions(outcome, [], contract=_XC)


# ═══════════════════════════════════════════════════════════════════════════
# 13. 任务边界：merge 域当前零生产消费方（显式登记的延后）
# ═══════════════════════════════════════════════════════════════════════════

_TASK14_MODULES: Final[tuple[Path, ...]] = (_MERGE_PY, _CONFLICTS_PY)
_APP_DIR: Final[Path] = _BACKEND / "app"

#: 三方 merge **本体**（`merge.py`）被消费的结构化判据。
#:
#: 🔴 与 conflicts 分开列是必需的：`content_mutation.py` 同时 import 两个模块，合成
#: 一张表时「删掉 merge 的 import」仍会命中 conflicts 那条 pattern ⇒ 消费方计数不变
#: ⇒ 「零消费方」这一侧不可 falsify（变异 M40 实测判 WRONG-TEST）。而退役登记的
#: capability 写的是 `merge_projections / MergeOutcome`，也就是 merge 本体。
_MERGE_CONSUMER_PATTERNS: Final[tuple[str, ...]] = (
    "from app.services.workpaper_sync.merge import",
    "from app.services.workpaper_sync import merge",
    "workpaper_sync.merge.",
)

#: 冲突域（`conflicts.py`）被消费的结构化判据。
_CONFLICTS_CONSUMER_PATTERNS: Final[tuple[str, ...]] = (
    "from app.services.workpaper_sync.conflicts import",
    "from app.services.workpaper_sync import conflicts",
    "workpaper_sync.conflicts.",
)

#: merge 域「被生产代码消费」的**结构化**判据：模块级 import 或带点号的属性访问。
#: 不用裸词匹配 —— `DEFERRED_CONSUMERS` 的 `reason` 文案里就写着这些名字。
_CONSUMER_PATTERNS: Final[tuple[str, ...]] = (
    *_MERGE_CONSUMER_PATTERNS,
    *_CONFLICTS_CONSUMER_PATTERNS,
)

#: 本域承诺不出现的依赖与副作用面（merge.py 模块 docstring 的原话）。
_FORBIDDEN_SURFACE: Final[tuple[str, ...]] = (
    "openpyxl",
    "python-docx",
    "lxml",
    "xlsxwriter",
    "sqlalchemy",
    "AsyncSession",
    "repository",
    "outbox",
    ".commit(",
    "session.",
    "file_version",
    "content_revision",
    "EventBus",
)


#: 两张登记表（未接线的延后 + 已退役的欠账）。两者的 `reason`/`consumer` 文案里都逐字
#: 写着 `ContentMutationService.commit(...)`、`repository` 等词，定界时必须一起剔除。
_REGISTRATION_MARKERS: Final[tuple[str, ...]] = ("DEFERRED_CONSUMERS", "RETIRED_DEFERRALS")


def _cut_one_registration_block(body: str, marker: str) -> str:
    """从源码里剔除 `{marker} = (...)` 这**一段**声明。

    🔴 Task 13 实测过的假红形态：「名单/文案里写着某个名字」不等于「正在调用它」。
    本域的登记表逐字写着 `ContentMutationService.commit(...)` 与「不读 repository」，
    直接扫全文会把「明令延后 / 已退役」误判成「正在调用」。

    括号配对计数（不是固定字符窗口、也不是 `index()` 算边界）—— 前者会随文案长度失效。
    """
    lines = body.splitlines(keepends=True)
    start = next((n for n, line in enumerate(lines) if line.startswith(marker)), None)
    assert start is not None, (
        f"源码里找不到 {marker} 声明 —— 登记表被删了，"
        "边界判据失去锚点（这本身就该打红）"
    )
    depth = 0
    end = None
    for n in range(start, len(lines)):
        depth += lines[n].count("(") - lines[n].count(")")
        if n > start and depth <= 0:
            end = n + 1
            break
    assert end is not None, f"{marker} 声明的括号不配对，无法定界"
    return "".join(lines[:start] + lines[end:])


def _cut_registration_block(body: str) -> str:
    """剔除**全部**登记表声明后的源码。"""
    for marker in _REGISTRATION_MARKERS:
        body = _cut_one_registration_block(body, marker)
    return body


def _task14_body(path: Path) -> str:
    """剥注释/docstring + 剔除延后登记表后的**可执行**源码。"""
    body = _stripped(path)
    return _cut_registration_block(body) if path == _MERGE_PY else body


def _merge_domain_consumers() -> dict[str, list[str]]:
    """扫 `backend/app` 里**真的** import/调用 merge 域的生产模块（结构化判据）。

    返回 `{模块相对路径: [命中的 pattern, ...]}`。不用裸词匹配 —— 登记表的 `reason`
    文案里就写着这些名字（`_cut_registration_block` 与本函数是两道互补的定界）。
    """
    wired: dict[str, list[str]] = {}
    for py in sorted(_APP_DIR.rglob("*.py")):
        if py in _TASK14_MODULES:
            continue
        text = py.read_text(encoding="utf-8", errors="replace")
        hits = [pattern for pattern in _CONSUMER_PATTERNS if pattern in text]
        if hits:
            wired[py.relative_to(_BACKEND / "app").as_posix()] = hits
    return wired


class TestTask14ScopeBoundary:
    """「只建纯三方 merge 与冲突域」是可验证的承诺，不是自我声明。

    🔴 一个零生产消费方、只有 fixture 测试的域就是**假绿第①源（additive 死代码）**——
    除非把这条边界显式锁死。Task 14 交付时本类证明「当前真的零消费方 + 延后已登记」；
    Task 15 落地后判据**翻转**（不是删除）：

    1. merge 域现在有**恰一个**生产消费方，且正是 `RETIRED_DEFERRALS` 登记的
       `content_mutation.py` —— 零消费方（接线被删）与多消费方（绕过唯一 commit 入口）
       都打红；
    2. 退役登记必须完整（谁在哪个任务接线、接到哪个模块），退役不等于把欠账记录删掉；
    3. 仍未接线的能力（resolve API / extractor 输入形态）继续留在 `DEFERRED_CONSUMERS`
       并带 `blocking_task`；
    4. merge 域本体仍是纯域：零载体库、零 sqlalchemy/repository/outbox、零 commit 面。
    """

    def test_no_carrier_library_or_persistence_surface(self) -> None:
        """零 openpyxl/python-docx、零 sqlalchemy/repository/outbox、零 commit 面。"""
        for path in _TASK14_MODULES:
            body = _task14_body(path)
            for forbidden in _FORBIDDEN_SURFACE:
                assert forbidden not in body, (
                    f"{path.name} 出现 {forbidden!r} —— merge 域是纯域：无载体解析、"
                    "不连库、不提交、不发事件。真正的写入面归 Task 15 的 "
                    "ContentMutationService.commit(...)"
                )

    def test_merge_domain_consumers_match_the_retirement_registry_exactly(self) -> None:
        """生产消费方集合必须与退役登记**双向等值**，且非 commit 入口的消费方不得自建落库面。

        这一条替代了 Task 14 时期的 `test_merge_domain_has_no_production_consumer_yet`，
        并在 Task 26 落地后从「恰一个消费方」升级为「与登记表双向锁死」。判据**没有被
        弱化**：四种偏离各自打红 ——

        * **零消费方** ⇒ 接线被删/能力退回 additive 死代码（假绿第①源复发）；
        * **出现未登记的消费方** ⇒ 有人绕过唯一 `ContentMutationService.commit(...)`
          直接消费 merge 域（Requirement 2.2 / Property 61）；
        * **登记了却不再消费** ⇒ 登记表与事实不符，没人能核对欠账到底还没还；
        * **登记的编排层不再经由 commit 入口落库** ⇒ 它变成了第二个写入边界。

        为什么 Task 26 的 coordinator 是合法的第二个消费方而不是「绕过」：Task 15 的
        `BusinessMutation` 明文把「跑 merge」判给 coordinator（`本模块不重跑 merge`），
        design §Module Layout 也把 `coordinator.py` 列为 OO→HTML 编排方。三方投影
        （frozen base / current published / durable incoming）只有 coordinator 拿得到。
        真正要守的不变量是「**只有一个 commit 边界**」—— 最后一条断言正面钉住它。
        """
        # 🔴 期望集取**全部**退役登记，不再只取 capability 里带 `merge_projections`
        #    的那些（Task 27 实测：只 import 冲突域 fence 的消费方 —— 那条登记的
        #    capability 是 `evaluate_resolve_fence / apply_resolutions` —— 会落在
        #    `wired` 里却不在 `expected` 里，双向等值必假红）。判据没有放宽：下面按
        #    capability 分别要求 merge 本体消费方命中 merge pattern、其余消费方命中
        #    冲突域 pattern，比原来的「一律要求命中 merge 本体」多了一段。
        retired = list(M.RETIRED_DEFERRALS)
        assert len(retired) >= 1, "merge 域退役登记至少要有一条 —— 退役不等于删除记录"
        assert any(
            "merge_projections" in str(entry["capability"]) for entry in retired
        ), "merge_projections 的退役登记不得消失（Task 15/26 接线的记录）"
        expected: dict[str, Mapping[str, Any]] = {}
        for entry in retired:
            module = str(entry["expected_consumer_module"])
            assert module.startswith("app/services/workpaper_sync/"), module
            expected[module.split("app/", 1)[1]] = entry
        assert len(expected) == len(retired), "登记表里出现了同模块的重复条目"

        wired = _merge_domain_consumers()
        assert wired, (
            "merge 域又变回零生产消费方 —— 登记的消费方应当 import 它并消费 "
            "MergeOutcome。零消费方就是假绿第①源（additive 死代码）"
        )
        assert sorted(wired) == sorted(expected), (
            "merge 域的生产消费方集合必须与退役登记**双向等值**，实测:\n  "
            + "\n  ".join(f"{mod} :: {hits}" for mod, hits in sorted(wired.items()))
            + f"\n⇒ 登记为 {sorted(expected)}。多出来的模块意味着有人绕过 "
            "ContentMutationService.commit(...) 直接消费 merge 域；少掉的模块意味着"
            "登记表与事实脱钩"
        )
        # 🔴 还必须真的消费**登记声明的那个域**，不是「import 了两个模块之一就算」。
        #    登记 capability 带 `merge_projections / MergeOutcome` 的消费方必须命中
        #    merge 本体 pattern；其余（如 Task 27 的 resolve fence 消费方）必须至少命中
        #    冲突域 pattern。合成一张表按总数计时，「删掉 merge 的 import」仍命中
        #    conflicts 那条 ⇒ 计数不变 ⇒ 零消费方这一侧不可 falsify
        #    （变异 M40 实测判 WRONG-TEST，真凶是判据粒度而不是接线）。
        for rel, entry in sorted(expected.items()):
            merge_hits = [
                pattern for pattern in wired[rel] if pattern in _MERGE_CONSUMER_PATTERNS
            ]
            conflict_hits = [
                pattern
                for pattern in wired[rel]
                if pattern in _CONFLICTS_CONSUMER_PATTERNS
            ]
            if "merge_projections" in str(entry["capability"]):
                assert merge_hits, (
                    f"{rel} 只命中了冲突域 pattern {wired[rel]}，没有任何 `merge.py` 本体的 "
                    "import/属性访问 —— 登记声明接线的是 `merge_projections / MergeOutcome`"
                )
            else:
                assert merge_hits or conflict_hits, (
                    f"{rel} 一个 merge/conflicts pattern 都没命中，却登记为已接线 "
                    f"{entry['capability']!r} —— 登记与事实脱钩"
                )

        # 🔴 唯一 commit 边界：登记里带 `commits_through` 的编排层必须真的 import 它，
        #    并且自己不含 commit 面（后者由 `_FORBIDDEN_SURFACE` 那条守卫在 merge 域内
        #    保证，这里对编排层再补一次结构判据）。
        for rel, entry in sorted(expected.items()):
            through = entry.get("commits_through")
            if not through:
                continue
            module_text = (_BACKEND / "app" / rel).read_text(
                encoding="utf-8", errors="replace"
            )
            through_module = through.split("app/", 1)[1].removesuffix(".py").replace("/", ".")
            assert f"from app.{through_module} import" in module_text, (
                f"{rel} 登记为「经由 {through} 落库」，但源码里没有 import 它 —— "
                "编排层若自己 commit，就成了第二个写入边界（Property 61）"
            )
            assert "self._session.commit()" not in module_text or (
                "content_mutation" in module_text
            ), f"{rel} 出现独立 commit 面且未经由 {through}"

    def test_retired_deferral_records_who_wired_it(self) -> None:
        """退役登记必须写明 retired_by_task / consumer / 目标模块 / 原因，且目标真的存在。"""
        assert M.RETIRED_DEFERRALS, "退役登记为空 —— 欠账被还了但没人记下来"
        for entry in M.RETIRED_DEFERRALS:
            for field in (
                "capability",
                "intended_status",
                "retired_by_task",
                "consumer",
                "expected_consumer_module",
                "reason",
            ):
                assert entry.get(field), f"{entry.get('capability')!r} 的退役登记缺 {field}"
            assert entry["intended_status"] == "retired"
            assert str(entry["retired_by_task"]).isdigit(), (
                f"retired_by_task={entry['retired_by_task']!r} 必须是任务号"
            )
            assert len(str(entry["reason"])) >= 40
            target = _BACKEND / "app" / str(entry["expected_consumer_module"]).split(
                "app/", 1
            )[1]
            assert target.is_file(), (
                f"退役登记声明的消费方模块 {target} 不存在 —— 登记与事实不符"
            )
        # 同一 capability 不得同时挂在两张表上（否则「还没还」与「已还」并存）。
        deferred_caps = {str(e["capability"]) for e in M.DEFERRED_CONSUMERS}
        retired_caps = {str(e["capability"]) for e in M.RETIRED_DEFERRALS}
        assert not (deferred_caps & retired_caps), (
            f"同一能力同时登记为 deferred 与 retired: {sorted(deferred_caps & retired_caps)}"
        )

    def test_deferred_consumers_registration_is_complete(self) -> None:
        """每条延后都必须带 capability / intended_status / blocking_task / consumer / reason。

        🔴 **空表是合法终态，但只在两个条件同时成立时**（Task 59 收口裁决，2026-08-29）。
        merge 域的延后登记自 `blocking_task="15,26"` 起被 Task 15/26/27/28/37 逐条退役，
        Task 59 还清最后一条（Word 侧 `WordInstanceObservation` / `StructuralAnomaly`
        输入形态）后它必然为空。此处原先开头是无条件的
        `assert M.DEFERRED_CONSUMERS` —— 那把「Task 14 交付时零消费方」这个**过渡事实**
        锁成了永久不变量：真源改对反而打红（假绿第③源的镜像形态，本平台已多次实测）。

        它当初要防的是「一个**零消费方**的域连原因都不登记」。该保护现在由两条**独立**
        断言完整承担，所以去掉无条件非空不留缺口：

        * :meth:`test_retired_deferral_records_who_wired_it` 首句
          `assert M.RETIRED_DEFERRALS` —— 两张表同时为空（登记表被整段删掉以躲判据）
          立刻打红；
        * :meth:`test_merge_domain_consumers_match_the_retirement_registry_exactly` 的
          `assert wired` + 双向等值 —— 零生产消费方、或退役登记与事实脱钩都打红。

        本处仍把这两条前提**在本测试内**再钉一次（不依赖「另一条测试也会红」这种跨测试
        推理，否则单跑本测试时空表恒绿）。变异 M37 用「把 `RETIRED_DEFERRALS` 也清空」
        证明这条分支可被 falsify；M36 用「退役登记指向不存在的模块」证明另一侧。
        """
        if not M.DEFERRED_CONSUMERS:
            assert M.RETIRED_DEFERRALS, (
                "两张登记表同时为空 —— 这不是「欠账已还清」，是登记表被整段删掉。"
                "延后可以退役，退役记录不可以消失"
            )
            assert _merge_domain_consumers(), (
                "延后登记为空、却又零生产消费方 —— 「零消费方的域必须显式登记原因」"
                "这条边界失守（假绿第①源：additive 死代码）"
            )
        seen: set[str] = set()
        for entry in M.DEFERRED_CONSUMERS:
            for field in (
                "capability",
                "intended_status",
                "blocking_task",
                "consumer",
                "reason",
            ):
                assert entry.get(field), f"{entry.get('capability')!r} 缺 {field}"
            assert entry["intended_status"] == "deferred"
            tasks = [t.strip() for t in str(entry["blocking_task"]).split(",")]
            assert tasks and all(t.isdigit() for t in tasks), (
                f"{entry['capability']!r} 的 blocking_task={entry['blocking_task']!r} "
                "必须是逗号分隔的任务号 —— 「以后再说」不是可核对的登记"
            )
            assert len(str(entry["reason"])) >= 40, (
                f"{entry['capability']!r} 的 reason 过短，无法说明为什么现在不能接线"
            )
            assert entry["capability"] not in seen, f"重复登记 {entry['capability']!r}"
            seen.add(str(entry["capability"]))

    def test_content_mutation_service_is_defined_exactly_once(self) -> None:
        """`class ContentMutationService` 在 `backend/app` 里定义**恰一次**，且在唯一模块里。

        🔴 判据是**类定义**而不是词出现：`ContentMutationService` 被 6+ 个模块的注释/文案
        提到，按词判会得出「到处都有」的错误结论。

        本条是 Task 14 时期 `test_blocking_task_15_is_registered_and_its_target_does_not_
        exist_yet` 的翻转版：从「目标还不存在」变成「目标存在且只有一个」。两个方向都
        可 falsify —— 定义 0 次（Task 15 被回退）或 ≥2 次（出现第二个提交边界，
        Requirement 2.2 的「唯一入口」被破）都打红。
        """
        defined = [
            py.relative_to(_BACKEND / "app").as_posix()
            for py in sorted(_APP_DIR.rglob("*.py"))
            if re.search(r"^\s*class\s+ContentMutationService\b", py.read_text(
                encoding="utf-8", errors="replace"), re.MULTILINE)
        ]
        assert defined == ["services/workpaper_sync/content_mutation.py"], (
            "`class ContentMutationService` 必须恰有一处定义且在 "
            f"services/workpaper_sync/content_mutation.py，实测 {defined} —— "
            "0 处=Task 15 被回退；≥2 处=出现第二个业务提交边界（Requirement 2.2）"
        )

    def test_boundary_judgement_distinguishes_mention_from_wiring(self) -> None:
        """反向自检：登记表/文案里的名字不算接线，真 import 与真调用必须被抓。

        没有这条，上面两个判据可能只是恒真空转（假绿第②源：判据只查字符串存在）。
        """
        mention = (
            'DEFERRED = ({"consumer": "ContentMutationService.commit(...)", '
            '"reason": "不读 repository"},)\n'
        )
        real_import = "from app.services.workpaper_sync.merge import merge_projections\n"
        real_class = "class ContentMutationService:\n    pass\n"

        for marker in _REGISTRATION_MARKERS:
            assert not any(p in _cut_one_registration_block(
                f"{marker} = (\n" + mention + ")\n", marker
            ) for p in _FORBIDDEN_SURFACE), f"{marker} 里的文案被误判成副作用面 ⇒ 假红"
        # 剔除定界不得吞掉登记表**之外**的真副作用面（M80 用注入证明这条可 falsify）。
        with_real_surface = (
            "DEFERRED_CONSUMERS = (\n" + mention + ")\n"
            "RETIRED_DEFERRALS = (\n" + mention + ")\n"
            "def settle():\n    outcome.session.commit()\n"
        )
        assert any(
            p in _cut_registration_block(with_real_surface) for p in _FORBIDDEN_SURFACE
        ), "登记表之外的真 `session.commit()` 面被定界吞掉 ⇒ 假绿"
        assert any(p in real_import for p in _CONSUMER_PATTERNS), "真 import 没被抓 ⇒ 假绿"
        assert not any(p in mention for p in _CONSUMER_PATTERNS), (
            "文案提到消费方就被当成已接线 ⇒ 假红"
        )
        assert re.search(r"^\s*class\s+ContentMutationService\b", real_class, re.MULTILINE)
        assert not re.search(
            r"^\s*class\s+ContentMutationService\b", mention, re.MULTILINE
        ), "文案里的类名被当成类定义 ⇒ 假红"

    def test_no_engine_or_router_package_leaked_into_this_task(self) -> None:
        """本任务不建 engine、不注册路由 —— 两者分别归 Tasks 36~38 / 59~61 与 27/28。"""
        adapters_dir = _SYNC_DIR / "adapters"
        assert not (adapters_dir / "excel").exists()
        assert not (adapters_dir / "word").exists()
        for path in _TASK14_MODULES:
            body = _task14_body(path)
            for forbidden in ("APIRouter", "@router.", "Depends("):
                assert forbidden not in body, (
                    f"{path.name} 出现 {forbidden!r} —— resolve API 归 Task 27/28"
                )

    def test_task14_modules_declare_spec_requirements_and_properties(self) -> None:
        """可追溯性：两个模块的 docstring 必须写明 spec / Requirements / Properties。"""
        for path in _TASK14_MODULES:
            head = _read(path)[:2500]
            assert "workpaper-html-onlyoffice-bidirectional-writeback-closure" in head, (
                f"{path.name} 缺 spec 溯源"
            )
            assert "Requirements" in head, f"{path.name} 缺 Requirements 溯源"
            for prop in ("24", "25", "26", "27", "32", "35"):
                assert prop in head, f"{path.name} 的 Properties 溯源缺 P{prop}"


# ═══════════════════════════════════════════════════════════════════════════
# 14. MergeOutcome 的其余公开判据（补零覆盖，防 additive 死代码）
# ═══════════════════════════════════════════════════════════════════════════


class TestMergeOutcomeDerivedJudgements:
    """`requires_client_refresh` / `incoming_managed_keys` / `deleted_keys` / `of_kind`。

    这四个都是 `MergeOutcome` 的公开判据，若无守卫就是**本任务自己新增的死代码**
    （假绿第①源）。`requires_client_refresh` 尤其重要：AC 4.11 / 8.12 用它决定
    「merged 结果与 incoming 不等值 ⇒ room 进 refresh-required、不推进 client-confirmed」。
    """

    def test_requires_client_refresh_is_false_when_merged_equals_incoming(
        self, xc: C.SyncContract
    ) -> None:
        """仅 OO 改动 ⇒ merged 就是 incoming ⇒ 无需重载编辑器。"""
        incoming = proj(xc, {PERIOD: "新期间"})
        outcome = M.merge_projections(
            base=proj(xc, {PERIOD: "旧期间"}),
            current=proj(xc, {PERIOD: "旧期间"}),
            incoming=incoming,
            contract=xc,
        )
        assert outcome.verdicts[PERIOD] is M.FieldVerdict.took_incoming
        assert outcome.requires_client_refresh(incoming) is False

    def test_requires_client_refresh_is_true_when_current_wins(
        self, xc: C.SyncContract
    ) -> None:
        """服务端值胜出 ⇒ merged ≠ incoming ⇒ 必须让编辑器确认新基线。"""
        incoming = proj(xc, {PERIOD: "旧期间"})
        outcome = M.merge_projections(
            base=proj(xc, {PERIOD: "旧期间"}),
            current=proj(xc, {PERIOD: "服务端改过"}),
            incoming=incoming,
            contract=xc,
        )
        assert outcome.requires_client_refresh(incoming) is True

    def test_requires_client_refresh_detects_key_presence_difference(
        self, xc: C.SyncContract
    ) -> None:
        """键存在性差异也算不等值 —— 不能只比有交集的键。"""
        incoming = proj(xc, row_values(R1, name="甲", closing=1))
        outcome = M.merge_projections(
            base=proj(xc, row_values(R1, name="甲", closing=1)),
            current=proj(xc, {**row_values(R1, name="甲", closing=1), PERIOD: "多一个键"}),
            incoming=incoming,
            contract=xc,
        )
        assert PERIOD in outcome.merged.values and PERIOD not in incoming.values
        assert outcome.requires_client_refresh(incoming) is True

    def test_word_only_keys_are_excluded_from_the_refresh_comparison(
        self, dc: C.SyncContract
    ) -> None:
        """`word_only` 永不进 HTML projection，拿它比较会让 Word 底稿恒判需要重载。"""
        incoming = proj(
            dc, {"plan/location": "北京仓", "plan/free_notes": "Word 侧自由文本"}
        )
        outcome = M.merge_projections(
            base=proj(dc, {"plan/location": "北京仓", "plan/free_notes": "旧文本"}),
            current=proj(dc, {"plan/location": "北京仓", "plan/free_notes": "旧文本"}),
            incoming=incoming,
            contract=dc,
        )
        assert "plan/free_notes" in outcome.word_only_keys
        assert outcome.requires_client_refresh(incoming) is False

    def test_incoming_managed_keys_and_deleted_keys(self, xc: C.SyncContract) -> None:
        outcome = M.merge_projections(
            base=proj(xc, row_values(R1, name="甲", closing=1), row_keys={"equity_changes": (R1,)}),
            current=proj(xc, row_values(R1, name="甲", closing=1), row_keys={"equity_changes": (R1,)}),
            incoming=proj(xc, {ek(R1, "name"): "甲"}, row_keys={"equity_changes": (R1,)}),
            contract=xc,
        )
        assert outcome.incoming_managed_keys == (ek(R1, "name"),)
        assert ek(R1, "closing_amount") in outcome.deleted_keys
        assert ek(R1, "name") not in outcome.deleted_keys

    def test_of_kind_partitions_the_conflict_set(self, xc: C.SyncContract) -> None:
        outcome = _mixed_scenario(xc)
        buckets = {kind: outcome.conflicts.of_kind(kind) for kind in CF.ConflictKind}
        assert sum(len(v) for v in buckets.values()) == len(outcome.conflicts)
        for kind, records in buckets.items():
            assert all(r.kind is kind for r in records)
        assert buckets[CF.ConflictKind.value], "混合场景应含 value 冲突"

    def test_digest_payload_carries_the_three_values_and_kind(
        self, xc: C.SyncContract
    ) -> None:
        outcome = single(xc, "A", "B", "C", key=PERIOD)
        payload = outcome.conflicts.records[0].digest_payload()
        assert payload["kind"] == CF.ConflictKind.value.value
        assert payload["base"] == {"present": True, "value": "A"}
        assert payload["current"] == {"present": True, "value": "B"}
        assert payload["incoming"] == {"present": True, "value": "C"}
        assert payload["json_pointer"].startswith("/")
        assert payload["oo_location"]
