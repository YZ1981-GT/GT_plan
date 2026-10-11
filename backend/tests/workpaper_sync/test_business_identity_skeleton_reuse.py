"""P1：骨架无关业务身份复用（spec workpaper-sync-switch-performance · 需求 2）。

三层判据：

1. 纯函数语义（`business_identity`）：未声明骨架行忽略 / 声明骨架行集合比较 / 非骨架严格保序 /
   任何真实差异都打红 / 铸造身份不是骨架；PBT（max_examples=5）。
2. canonical 字节幂等：落盘工件（json 载回）与现算载荷走同一序列化 —— 两侧可比的前提。
3. 协调器接线：逐字节摘要未命中才走第二判据；命中带注明的 hit 判词；表示腿照校验（AST + 假会话）。
"""

from __future__ import annotations

import ast
import json
import uuid
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.workpaper_sync.adapters.base import FieldValue, Projection
from app.services.workpaper_sync.business_identity import (
    business_identity_equal,
    compare_business_identity,
)
from app.services.workpaper_sync.content_mutation import _projection_payload
from app.services.workpaper_sync.contracts import FieldMode, ValueType
from app.services.workpaper_sync.definitions import canonical_json_bytes

_COORDINATOR_PY = (
    Path(__file__).resolve().parents[2]
    / "app/services/workpaper_sync/materialize_coordinator.py"
)

SK1, SK2, SK3 = "GTROW-D23CMB-0018", "GTROW-D23CMB-0019", "GTROW-D22-0013"


def _payload(
    rows: dict[str, list[str]],
    values: dict[str, tuple[Any, str | None]],
    *,
    contract_id: str = "c.demo",
) -> dict[str, Any]:
    """`_projection_payload` 同形载荷（与落盘工件 json 载回后的形态一致）。"""
    return {
        "schema_version": "workpaper-projection:v1",
        "contract_id": contract_id,
        "semantic_version": "1.0.0",
        "document_type": "xlsx",
        "values": {
            key: {"value": value, "value_type": "amount", "mode": "formula", "row_key": row}
            for key, (value, row) in values.items()
        },
        "row_keys": {table: list(ids) for table, ids in rows.items()},
    }


def _oo_side() -> dict[str, Any]:
    """OO 侧（extract）：骨架行在表头，坏账表带 HTML 不认领的骨架行。"""
    return _payload(
        {"detail": [SK3, "dr-1", "dr-2"], "bad_debt": [SK1, SK2]},
        {
            f"detail/{SK3}/seq": ("1", SK3),
            "detail/dr-1/amount": ("10", "dr-1"),
            "detail/dr-2/amount": ("20", "dr-2"),
            f"bad_debt/{SK1}/current_audited": ("0", SK1),
            f"bad_debt/{SK1}/label": ("其中：", SK1),
            f"bad_debt/{SK2}/current_audited": ("0", SK2),
            "static/total": ("30", None),
        },
    )


def _html_side() -> dict[str, Any]:
    """HTML 侧（store ⊕ 基线）：同一份业务内容，骨架行在表尾，坏账表 0 行。"""
    return _payload(
        {"detail": ["dr-1", "dr-2", SK3], "bad_debt": []},
        {
            "detail/dr-1/amount": ("10", "dr-1"),
            "detail/dr-2/amount": ("20", "dr-2"),
            f"detail/{SK3}/seq": ("1", SK3),
            "static/total": ("30", None),
        },
    )


class TestSemantics:
    def test_the_measured_d2_shape_is_equivalent(self) -> None:
        """真库形态：未声明骨架行忽略、两侧都有的骨架行与位置无关。"""
        result = compare_business_identity(_oo_side(), _html_side())
        assert result.equal is True
        assert result.ignored_skeleton_rows == 2
        assert result.ignored_skeleton_values == 3
        assert result.position_free_skeleton_rows == 1
        assert "template_skeleton_equivalent" in result.note()

    def test_byte_digest_of_the_same_pair_differs(self) -> None:
        """反空转：这一对的逐字节摘要确实不等（否则本 spec 修的不是这件事）。"""
        assert canonical_json_bytes(_oo_side()) != canonical_json_bytes(_html_side())

    def test_declared_skeleton_rows_compare_as_a_set(self) -> None:
        """两侧都声明的骨架行按集合比较：物化按身份落位，不按投影序搬行（真库实测）。"""
        values = {
            f"t/{SK1}/seq": ("1", SK1), f"t/{SK2}/seq": ("2", SK2), "t/dr-1/amount": ("5", "dr-1"),
        }
        oo = _payload({"t": [SK1, SK2, "dr-1"]}, values)
        html = _payload({"t": ["dr-1", SK2, SK1]}, values)
        result = compare_business_identity(oo, html)
        assert result.equal is True and result.position_free_skeleton_rows == 2

    def test_non_skeleton_row_order_is_strict(self) -> None:
        html = _html_side()
        html["row_keys"]["detail"] = ["dr-2", "dr-1", SK3]
        assert business_identity_equal(_oo_side(), html) is False

    def test_a_changed_business_value_breaks_equality(self) -> None:
        html = _html_side()
        html["values"]["detail/dr-1/amount"]["value"] = "11"
        assert business_identity_equal(_oo_side(), html) is False

    def test_a_changed_value_on_a_declared_skeleton_row_breaks_equality(self) -> None:
        html = _html_side()
        html["values"][f"detail/{SK3}/seq"]["value"] = "99"
        assert business_identity_equal(_oo_side(), html) is False

    def test_a_carried_key_on_an_undeclared_skeleton_row_is_compared(self) -> None:
        """HTML 侧携带了某骨架行的字段（哪怕行没声明）⇒ 该键严格比较，不得被忽略。"""
        html = _html_side()
        html["values"][f"bad_debt/{SK1}/label"] = {
            "value": "用户改过", "value_type": "amount", "mode": "formula", "row_key": SK1,
        }
        assert business_identity_equal(_oo_side(), html) is False

    def test_a_carried_key_with_the_same_value_stays_comparable(self) -> None:
        """反向：携带的键值相同 ⇒ 仍等价（携带即参与比较，而不是一律剔除）。"""
        html = _html_side()
        html["values"][f"bad_debt/{SK1}/label"] = {
            "value": "其中：", "value_type": "amount", "mode": "formula", "row_key": SK1,
        }
        assert business_identity_equal(_oo_side(), html) is True

    def test_incoming_declaring_a_skeleton_row_the_base_lacks_is_not_equal(self) -> None:
        html = _html_side()
        html["row_keys"]["detail"] = ["dr-1", "dr-2", SK3, "GTROW-D22-0014"]
        assert business_identity_equal(_oo_side(), html) is False

    def test_an_extra_business_row_on_either_side_is_not_equal(self) -> None:
        oo = _oo_side()
        oo["row_keys"]["detail"] = [SK3, "dr-1", "dr-2", "dr-3"]
        assert business_identity_equal(oo, _html_side()) is False

    def test_minted_identities_are_business_rows(self) -> None:
        """`GTROW-MINTED-*` 不是模板骨架（与 roundtrip 豁免同一真源）⇒ 不得被忽略。"""
        oo = _oo_side()
        oo["row_keys"]["bad_debt"] = [SK1, SK2, "GTROW-MINTED-abc"]
        assert business_identity_equal(oo, _html_side()) is False

    def test_contract_identity_must_match(self) -> None:
        html = _html_side()
        html["contract_id"] = "c.other"
        assert business_identity_equal(_oo_side(), html) is False

    def test_a_table_missing_on_the_html_side_is_not_equal(self) -> None:
        html = _html_side()
        del html["row_keys"]["detail"]
        assert business_identity_equal(_oo_side(), html) is False


_business_rows = st.lists(
    st.text(alphabet="abcdef0123456789", min_size=4, max_size=6).map(lambda s: f"dr-{s}"),
    min_size=1, max_size=5, unique=True,
)


class TestProperties:
    @settings(max_examples=5, deadline=None)
    @given(rows=_business_rows, skeleton_count=st.integers(min_value=0, max_value=3),
           declared_count=st.integers(min_value=0, max_value=3))
    def test_moving_or_dropping_skeleton_rows_keeps_equality(
        self, rows: list[str], skeleton_count: int, declared_count: int
    ) -> None:
        skeletons = [f"GTROW-T-{i:04d}" for i in range(skeleton_count)]
        declared = skeletons[: min(declared_count, skeleton_count)]
        values = {f"t/{r}/amount": (str(i), r) for i, r in enumerate(rows)}
        values.update({f"t/{s}/seq": ("0", s) for s in skeletons})
        base = _payload({"t": skeletons + rows}, values)
        html_values = {f"t/{r}/amount": (str(i), r) for i, r in enumerate(rows)}
        html_values.update({f"t/{s}/seq": ("0", s) for s in declared})
        html = _payload({"t": rows + list(reversed(declared))}, html_values)
        assert business_identity_equal(base, html) is True

    @settings(max_examples=5, deadline=None)
    @given(rows=_business_rows, pick=st.integers(min_value=0, max_value=10))
    def test_any_business_value_change_breaks_equality(self, rows: list[str], pick: int) -> None:
        values = {f"t/{r}/amount": (str(i), r) for i, r in enumerate(rows)}
        base = _payload({"t": ["GTROW-T-0001", *rows]}, {**values, "t/GTROW-T-0001/x": ("0", "GTROW-T-0001")})
        changed = dict(values)
        target = f"t/{rows[pick % len(rows)]}/amount"
        changed[target] = ("changed", rows[pick % len(rows)])
        html = _payload({"t": rows}, changed)
        assert business_identity_equal(base, html) is False


def _fv(key: str, value: Any, vt: ValueType, row: str | None = None) -> FieldValue:
    return FieldValue(stable_key=key, value=value, value_type=vt, mode=FieldMode.editable, row_key=row)


def test_loaded_artifact_and_fresh_payload_serialise_identically() -> None:
    """落盘工件是 canonical 字节；json 载回再序列化必须逐字节相同（两侧可比的前提）。"""
    projection = Projection(
        contract_id="c.demo", semantic_version="1.0.0", document_type="xlsx",
        values={
            "t/dr-1/amount": _fv("t/dr-1/amount", Decimal("1234.50"), ValueType.amount, "dr-1"),
            "t/dr-1/note": _fv("t/dr-1/note", None, ValueType.text, "dr-1"),
            "t/dr-1/flag": _fv("t/dr-1/flag", True, ValueType.boolean, "dr-1"),
            "static/meta": _fv("static/meta", {"b": [1, 2], "a": "x"}, ValueType.json),
        },
        row_keys={"t": ("dr-1",)},
    )
    fresh = _projection_payload(projection)
    stored = canonical_json_bytes(fresh)
    assert canonical_json_bytes(json.loads(stored.decode("utf-8"))) == stored
    assert business_identity_equal(json.loads(stored.decode("utf-8")), fresh) is True


# ─────────────────────────────────────────────────────────────────────────
# 协调器接线
# ─────────────────────────────────────────────────────────────────────────


def _materialize_fn() -> ast.AsyncFunctionDef:
    tree = ast.parse(_COORDINATOR_PY.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "MaterializeCoordinator":
            for item in node.body:
                if isinstance(item, ast.AsyncFunctionDef) and item.name == "materialize":
                    return item
    raise AssertionError("找不到 MaterializeCoordinator.materialize")


def test_second_judgement_runs_only_after_a_byte_digest_miss() -> None:
    fn = _materialize_fn()
    guarded = [
        node for node in ast.walk(fn)
        if isinstance(node, ast.If) and ast.unparse(node.test) == "reuse is None"
        and "_find_skeleton_equivalent_reuse" in ast.unparse(node)
    ]
    assert len(guarded) == 1, "骨架无关判据必须恰在「逐字节未命中」分支里调用一次"


def test_the_hit_verdict_is_forwarded_to_settle_reuse() -> None:
    fn = _materialize_fn()
    calls = [
        node for node in ast.walk(fn)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        and node.func.attr == "_settle_reuse"
    ]
    assert calls and all(
        any(kw.arg == "verdict" and ast.unparse(kw.value) == "hit_verdict" for kw in c.keywords)
        for c in calls
    ), "复用路径必须带上实际判词（骨架等价命中要可观测）"


class _Result:
    def __init__(self, row: Any) -> None:
        self._row = row

    def scalar_one_or_none(self) -> Any:
        return self._row


class _Session:
    """按调用顺序回放 SELECT 结果（version → representation）。"""

    def __init__(self, *rows: Any) -> None:
        self._rows = list(rows)
        self.queries = 0

    async def execute(self, _stmt: Any) -> _Result:
        self.queries += 1
        return _Result(self._rows.pop(0) if self._rows else None)


def _coordinator(session: _Session, base_payload: dict[str, Any] | None):
    from app.services.workpaper_sync import materialize_coordinator as MC

    coordinator = MC.MaterializeCoordinator.__new__(MC.MaterializeCoordinator)
    coordinator._session = session  # type: ignore[attr-defined]

    async def _read_base(**_kw: Any) -> dict[str, Any] | None:
        return base_payload

    coordinator._read_base_projection_payload = _read_base  # type: ignore[method-assign]
    return coordinator


def _request_and_pre(projection: Projection):
    request = SimpleNamespace(projection=projection, wp_id=uuid.uuid4(), entry_id="xlsx/demo")
    pre = SimpleNamespace(
        base_content_version_id=uuid.uuid4(),
        resolution=SimpleNamespace(representation_id=uuid.uuid4()),
    )
    return request, pre


def _html_projection() -> Projection:
    return Projection(
        contract_id="c.demo", semantic_version="1.0.0", document_type="xlsx",
        values={"t/dr-1/amount": _fv("t/dr-1/amount", Decimal("10"), ValueType.amount, "dr-1")},
        row_keys={"t": ("dr-1",)},
    )


def _base_with_skeleton(projection: Projection) -> dict[str, Any]:
    base = json.loads(canonical_json_bytes(_projection_payload(projection)).decode("utf-8"))
    base["row_keys"]["t"] = [SK1, *base["row_keys"]["t"]]
    base["values"][f"t/{SK1}/x"] = {"value": "0", "value_type": "amount", "mode": "formula", "row_key": SK1}
    return base


@pytest.mark.asyncio
async def test_equivalent_base_reuses_with_a_noted_hit() -> None:
    projection = _html_projection()
    version, representation = SimpleNamespace(id=uuid.uuid4()), SimpleNamespace(id=uuid.uuid4())
    session = _Session(version, representation)
    coordinator = _coordinator(session, _base_with_skeleton(projection))
    request, pre = _request_and_pre(projection)
    found = await coordinator._find_skeleton_equivalent_reuse(request=request, pre=pre)
    assert found is not None
    (got_version, got_rep), verdict = found
    assert (got_version, got_rep) == (version, representation)
    assert verdict.decision.value == "hit" and verdict.metric_result == "hit"
    assert "template_skeleton_equivalent" in verdict.differences[0]
    assert session.queries == 2


@pytest.mark.asyncio
async def test_representation_leg_still_gates_the_reuse() -> None:
    projection = _html_projection()
    session = _Session(SimpleNamespace(id=uuid.uuid4()), None)
    coordinator = _coordinator(session, _base_with_skeleton(projection))
    request, pre = _request_and_pre(projection)
    assert await coordinator._find_skeleton_equivalent_reuse(request=request, pre=pre) is None


@pytest.mark.asyncio
async def test_different_business_content_does_not_touch_the_database() -> None:
    projection = _html_projection()
    base = _base_with_skeleton(projection)
    base["values"]["t/dr-1/amount"]["value"] = "999"
    session = _Session()
    coordinator = _coordinator(session, base)
    request, pre = _request_and_pre(projection)
    assert await coordinator._find_skeleton_equivalent_reuse(request=request, pre=pre) is None
    assert session.queries == 0


@pytest.mark.asyncio
async def test_missing_base_payload_is_a_plain_miss() -> None:
    session = _Session()
    coordinator = _coordinator(session, None)
    request, pre = _request_and_pre(_html_projection())
    assert await coordinator._find_skeleton_equivalent_reuse(request=request, pre=pre) is None
