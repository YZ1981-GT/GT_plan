"""`RowReader` 适配层（Task 3.4）的边界判据。

spec: workpaper-sync-adopt-overwrite-and-refresh-source · Task 3.4
Requirements 4.1 / 4.4 / 4.5

本文件**不是** Property 测试（Property 10 / 9 分属 Task 3.5 / 3.6）。它守的是适配层自己的
四条契约，每条都配反证（判据必须能为 False）：

1. **禁回退**（design §4.1b L3）：item-aware 门面只准收到「显式传本 item」这一种调法 ——
   门面普遍写成 `_spec_of_store_item(store_item_id or STORE_ITEM_ID)`，不传就落到门面定义
   模块自己的 item ⇒ 任何假 item_id 都会被判可枚举（探针 v1 的实际缺陷）。
2. **必须消费生成器**（L4）：G 循环门面是 `yield from`，`specs_for` 的抛错发生在**首次迭代**。
3. **禁硬编码键名**（Requirement 4.5）：身份键与分区字段一律取自声明。
4. **载荷不可解析 ⇒ fail visible**（Requirement 4.4）：不得当零行处理，错误须带 item_id。
"""
from __future__ import annotations

import importlib
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pytest

from app.services.workpaper_sync.adopt_overwrite_plan import (
    OverwritePlanShapeError,
    SkipReason,
)
from app.services.workpaper_sync.adopt_row_reader import (
    RowReaderResolution,
    _diagnose_via_facade,
    _FacadeRowReader,
    diagnose_row_reader,
    resolve_row_reader,
)

_G9 = "app.services.workpaper_sync.phase5_g9_other_noncurrent"
_G1 = "app.services.workpaper_sync.phase5_g1_trading_financial_assets"
_G3 = "app.services.workpaper_sync.phase5_g3_dividend_receivable"
_G5 = "app.services.workpaper_sync.phase5_g5_long_term_receivable"
_G10 = "app.services.workpaper_sync.phase5_g10_trading_liabilities"
_G11 = "app.services.workpaper_sync.phase5_g11_investment_income"
_G14 = "app.services.workpaper_sync.phase5_g14_credit_impairment"
_D4 = "app.services.workpaper_sync.phase5_d4_revenue_detail"
_H1 = "app.services.workpaper_sync.pilot_h1_grouped_dynamic"


def _mod(path: str) -> Any:
    return importlib.import_module(path)


def _declared_identity_key(module_path: str, item_id: str) -> str:
    """从**声明**取身份键（spec 优先，item-blind 门面退到模块常量）—— 测试里也不许写字面量。"""
    mod = _mod(module_path)
    specs = [
        s
        for s in getattr(mod, "managed_row_table_specs", lambda: ())()
        if s.store_item_id == item_id
    ]
    if specs:
        return str(specs[0].row_identity_key)
    return str(getattr(mod, "ROW_IDENTITY_STORE_KEY", ""))


@dataclass(frozen=True)
class _StubSpec:
    store_item_id: str
    table_key: str
    row_identity_key: str = "someOtherKey"
    row_section_field: str = ""
    row_section_value: str = ""


def _stub_provider(*, specs: tuple[_StubSpec, ...], calls: list[dict[str, Any]]) -> Any:
    """item-aware 门面的替身，记录每次调用的关键字 —— 「禁回退」的直接行为锁。"""

    def iter_store_rows(payload: Any, *, store_item_id: str | None = None):
        calls.append({"store_item_id": store_item_id})
        picked = [s for s in specs if s.store_item_id == store_item_id]
        if not picked:
            raise LookupError(f"store item {store_item_id!r} 不在替身受管清单里")
        for row in payload:
            for spec in picked:
                if spec.row_section_field and str(
                    row.get(spec.row_section_field) or ""
                ) != spec.row_section_value:
                    continue
                yield str(row[spec.row_identity_key]), row

    return SimpleNamespace(
        __name__=__name__,
        iter_store_rows=iter_store_rows,
        managed_row_table_specs=lambda: specs,
    )


class TestIdentityKeyIndependence:
    """Requirement 4.5：身份识别与键名无关，键名一律来自声明。"""

    CASES = (
        (_G10, "G10-detail-rows"),
        (_G11, "G11-detail-rows"),
        (_G14, "G14-detail-rows"),
        (_H1, "H1-8-rows"),  # item-blind 门面（键取自模块常量）
    )

    def test_each_declared_key_enumerates(self) -> None:
        seen_keys: set[str] = set()
        for module_path, item_id in self.CASES:
            key = _declared_identity_key(module_path, item_id)
            assert key, f"{item_id} 取不到声明的身份键"
            seen_keys.add(key)
            reader = resolve_row_reader(provider=_mod(module_path), store_item_id=item_id)
            assert reader is not None, f"{item_id} 应可枚举"
            got = list(reader.iter_rows([{key: "k1", "x": 1}, {key: "k2", "x": 2}]))
            assert [i for i, _ in got] == ["k1", "k2"], item_id
            assert all(isinstance(r, dict) for _, r in got), item_id
        # 变异证明：这些用例真的跨了多种键名（≥3），不是同一个键测了四遍
        assert len(seen_keys) >= 3, f"实得键名只有 {sorted(seen_keys)}"

    def test_payload_carrying_a_foreign_key_is_not_silently_accepted(self) -> None:
        """反证：把身份放在**别的**键上（哪怕是别家 item 的合法键）必须 fail visible。"""
        item_id = "G10-detail-rows"
        key = _declared_identity_key(item_id=item_id, module_path=_G10)
        foreign = _declared_identity_key(item_id="G14-detail-rows", module_path=_G14)
        assert foreign != key
        reader = resolve_row_reader(provider=_mod(_G10), store_item_id=item_id)
        assert reader is not None
        with pytest.raises(Exception) as excinfo:
            list(reader.iter_rows([{foreign: "k1"}]))
        assert item_id in str(excinfo.value)


class TestNoFallbackCall:
    """design §4.1b L3：item-aware 门面只准收到「显式传本 item」这一种调法。"""

    def test_every_facade_call_carries_the_asked_item(self) -> None:
        calls: list[dict[str, Any]] = []
        provider = _stub_provider(
            specs=(_StubSpec(store_item_id="ITEM-A", table_key="t_a"),), calls=calls
        )
        res = diagnose_row_reader(provider=provider, store_item_id="ITEM-A")
        assert res.is_enumerable
        list(res.reader.iter_rows([{"someOtherKey": "r1"}]))
        assert calls, "门面一次都没被调到 —— 判据恒真"
        assert all(c["store_item_id"] == "ITEM-A" for c in calls), calls

    def test_fake_item_id_is_not_enumerable(self) -> None:
        """真实门面上的同一条：假 item_id 不得被判可枚举（探针 v1 在此打红）。"""
        fake = diagnose_row_reader(provider=_mod(_G10), store_item_id="NOT-A-REAL-ITEM")
        assert not fake.is_enumerable
        assert fake.skip_reason is SkipReason.item_unresolvable
        # 变异对照：同一段代码对**真** item 必须判可枚举，否则上面的 False 没有区分力
        assert diagnose_row_reader(provider=_mod(_G10), store_item_id="G10-detail-rows").is_enumerable

    def test_item_blind_facade_only_serves_its_bound_item(self) -> None:
        d4 = _mod(_D4)
        bound = str(d4.STORE_ITEM_ID)
        assert diagnose_row_reader(provider=d4, store_item_id=bound).is_enumerable
        other = diagnose_row_reader(provider=d4, store_item_id="D4-10-data")
        assert not other.is_enumerable
        assert other.skip_reason is SkipReason.item_blind


class TestGeneratorMustBeConsumed:
    """design §4.1b L4：抛错发生在**首次迭代**，只调不消费会把真缺陷全判通过。"""

    ITEM = "G3-2-detail-rows"

    def test_calling_without_consuming_raises_nothing(self) -> None:
        g3 = _mod(_G3)
        g3.iter_store_rows([], store_item_id=self.ITEM)  # 不抛即证明惰性

    def test_consuming_raises_and_resolution_records_the_real_cause(self) -> None:
        """🔴 判据落在**第 ① 级**（`_diagnose_via_facade`）。

        Task 3.7 起 `diagnose_row_reader` 是三级编排：G3 的门面仍然坏着（本测试守的就是
        「必须消费生成器才看得见它坏」），但 R3 兜住了它 ⇒ 顶层结论变成可枚举。把判据改成
        「顶层可枚举」会让「必须消费」这条纪律失去守卫，故改判在 ① 级；顶层的转正由
        `TestR3TakesOverBoundFacades` 单独断言。
        """
        g3 = _mod(_G3)
        with pytest.raises(Exception):
            list(g3.iter_store_rows([], store_item_id=self.ITEM))
        res = _diagnose_via_facade(provider=g3, store_item_id=self.ITEM)
        assert not res.is_enumerable
        # 门面 re-export 自 phase5_g9_store_facade ⇒ 比 item_unresolvable 更精确的那一个
        assert res.skip_reason is SkipReason.row_reader_bound_to_other_entry
        assert res.facade_module.endswith("phase5_g9_store_facade")
        # 三级编排把 ① 级的成因原样带进 detail（不得把「门面坏了」这件事洗掉）
        top = diagnose_row_reader(provider=g3, store_item_id=self.ITEM)
        assert SkipReason.row_reader_bound_to_other_entry.value in top.detail
        assert top.facade_module.endswith("phase5_g9_store_facade")


class TestUnreadablePayloadFailsVisible:
    """Requirement 4.4：四种不可解析形态一律抛且带 item_id，**不得**当零行处理。"""

    ITEM = "G9-detail-rows"
    FORMS = ("{not json", '{"a": 1}', "42", "[1]")

    def _reader(self) -> Any:
        reader = resolve_row_reader(provider=_mod(_G9), store_item_id=self.ITEM)
        assert reader is not None
        return reader

    @pytest.mark.parametrize("payload", FORMS)
    def test_each_form_raises_with_item_id(self, payload: str) -> None:
        with pytest.raises(Exception) as excinfo:
            list(self._reader().iter_rows(payload))
        assert self.ITEM in str(excinfo.value)

    def test_row_without_any_identity_key_raises(self) -> None:
        """正面判据非恒真的反证（design §4.1b 变异对照 #8）。"""
        with pytest.raises(Exception) as excinfo:
            list(self._reader().iter_rows([{"section": "main", "noteName": "无身份键"}]))
        assert self.ITEM in str(excinfo.value)

    def test_legal_payload_still_enumerates(self) -> None:
        """变异对照：同一个 reader 对合法载荷必须**不**抛，否则上面四条没有区分力。"""
        key = _declared_identity_key(module_path=_G9, item_id=self.ITEM)
        got = list(self._reader().iter_rows([{key: "r1", "section": "main"}]))
        assert [i for i, _ in got] == ["r1"]


class TestSectionComesFromDeclaration:
    """Requirement 1.4 / 4.5：分区字段读 `RowTableSheetSpec.row_section_field`，禁硬编码。"""

    def test_g9_three_sections_are_classified(self) -> None:
        reader = resolve_row_reader(provider=_mod(_G9), store_item_id="G9-detail-rows")
        assert reader is not None
        field = reader.section_field
        specs = [
            s
            for s in _mod(_G9).managed_row_table_specs()
            if s.store_item_id == "G9-detail-rows"
        ]
        assert field == specs[0].row_section_field
        values = [s.row_section_value for s in specs]
        assert len(set(values)) == 3
        key = _declared_identity_key(module_path=_G9, item_id="G9-detail-rows")
        payload = [{key: f"r{i}", field: v} for i, v in enumerate(values)]
        got = list(reader.iter_rows(payload))
        assert [reader.section_of(r) for _, r in got] == values
        assert reader.declared_scopes == tuple(
            sorted((s.table_key, s.row_section_value) for s in specs)
        )

    def test_section_field_name_is_not_the_literal_section_for_every_item(self) -> None:
        """反证「硬编码 `'section'` 也能过」：G5 声明的是 `sectionKey`，且有 12 段。"""
        specs = [
            s
            for s in _mod(_G5).managed_row_table_specs()
            if s.store_item_id == "G5-2-rows"
        ]
        fields = {s.row_section_field for s in specs}
        assert fields == {"sectionKey"} and "section" not in fields
        # ① 级：门面借给了 G9 ⇒ 门面路不可枚举（Task 3.7 后这条事实不变，只是不再是终态）
        facade = _diagnose_via_facade(provider=_mod(_G5), store_item_id="G5-2-rows")
        assert facade.skip_reason is SkipReason.row_reader_bound_to_other_entry
        # 顶层：R3 兜住 ⇒ 12 段全在，且**声明层**仍被如实读出
        res = diagnose_row_reader(provider=_mod(_G5), store_item_id="G5-2-rows")
        assert res.is_enumerable, res.detail
        assert len(res.declared_scopes) == 12
        assert {section for _table, section in res.declared_scopes} == {
            s.row_section_value for s in specs
        }

    def test_undeclared_section_value_is_returned_verbatim(self) -> None:
        """未声明的分区值**不得**归一成 None —— 那会把作用域外的行混进「无分区」桶。"""
        reader = resolve_row_reader(provider=_mod(_G9), store_item_id="G9-detail-rows")
        assert reader is not None
        assert reader.section_of({reader.section_field: "未声明的段"}) == "未声明的段"
        assert reader.section_of({}) is None

    def test_a_non_section_field_name_is_honoured_end_to_end(self) -> None:
        """🔴 硬编码 `'section'` 的反证。

        真实树上唯一**可枚举**的多分区 item 恰好用的就是 `section`（G9）—— 只拿它测，
        生产代码把字段名写死成 `"section"` 也会全绿。故用替身声明一个 `acctClass` 两段的
        item：字段名必须逐字来自声明，分区归属必须按它算。
        """
        calls: list[dict[str, Any]] = []
        provider = _stub_provider(
            specs=(
                _StubSpec("ITEM-A", "t1", row_section_field="acctClass", row_section_value="alpha"),
                _StubSpec("ITEM-A", "t2", row_section_field="acctClass", row_section_value="beta"),
            ),
            calls=calls,
        )
        res = diagnose_row_reader(provider=provider, store_item_id="ITEM-A")
        assert res.is_enumerable, res.detail
        reader = res.reader
        assert reader.section_field == "acctClass"
        assert reader.declared_scopes == (("t1", "alpha"), ("t2", "beta"))
        rows = [
            {"someOtherKey": "a1", "acctClass": "alpha"},
            {"someOtherKey": "b1", "acctClass": "beta"},
        ]
        got = list(reader.iter_rows(rows))
        assert [(i, reader.section_of(r)) for i, r in got] == [
            ("a1", "alpha"),
            ("b1", "beta"),
        ]
        assert set(res.covered_sections) == {"alpha", "beta"}


class TestDeclarationDriftFailsVisible:
    """声明层漂移当场抛（编程/声明错误 ⇒ 500 + 堆栈，不翻译成用户提示）。"""

    def test_conflicting_section_fields_raise(self) -> None:
        calls: list[dict[str, Any]] = []
        provider = _stub_provider(
            specs=(
                _StubSpec("ITEM-A", "t1", row_section_field="aField", row_section_value="x"),
                _StubSpec("ITEM-A", "t2", row_section_field="bField", row_section_value="y"),
            ),
            calls=calls,
        )
        with pytest.raises(OverwritePlanShapeError) as excinfo:
            diagnose_row_reader(provider=provider, store_item_id="ITEM-A")
        assert "row_section_field" in str(excinfo.value)

    def test_degenerate_section_declaration_raises(self) -> None:
        """声明了分区字段却把 value 留空 —— Task 3.1 明写「Task 4.1 遇到时必须当场抛」。"""
        calls: list[dict[str, Any]] = []
        provider = _stub_provider(
            specs=(_StubSpec("ITEM-A", "t1", row_section_field="aField", row_section_value=""),),
            calls=calls,
        )
        with pytest.raises(OverwritePlanShapeError):
            diagnose_row_reader(provider=provider, store_item_id="ITEM-A")

    def test_no_such_declaration_exists_on_the_current_tree(self) -> None:
        """上面那条的变异对照：现算全域**无**退化声明（否则 Task 4.1 早该炸）。"""
        from app.services.workpaper_sync.adapters import registry as reg
        from app.services.workpaper_sync.store_projection_response import (
            resolve_store_projection_provider,
        )

        degenerate: list[str] = []
        sectioned = 0
        for adapter_id in sorted(
            {str(r.get("contract_id") or "") for r in reg.DELIVERED_PER_ENTRY_CONTRACTS} - {""}
        ):
            try:
                provider = resolve_store_projection_provider(adapter_id)
            except Exception:
                continue
            fn = getattr(provider, "managed_row_table_specs", None)
            if not callable(fn):
                continue
            try:
                specs = tuple(fn())
            except Exception:
                continue
            for spec in specs:
                if not str(getattr(spec, "row_section_field", "") or ""):
                    continue
                sectioned += 1
                if not str(getattr(spec, "row_section_value", "") or ""):
                    degenerate.append(f"{adapter_id}/{spec.store_item_id}/{spec.table_key}")
        assert not degenerate, degenerate
        # 变异证明：这个 0 不是「一条声明了分区的 spec 都没扫到」
        assert sectioned > 0, "没扫到任何声明了 row_section_field 的 spec ⇒ 上面的 0 无意义"


class TestFacadeShapeGuard:
    """门面 yield 三元组时必须打红（现算真有这种门面，按二元组解包会把 table_key 当行身份）。"""

    def test_three_tuple_yield_is_rejected(self) -> None:
        reader = _FacadeRowReader(
            item_id="STUB-ITEM",
            invoke=lambda _payload: iter([("t1", "r1", {"a": 1})]),
        )
        with pytest.raises(OverwritePlanShapeError) as excinfo:
            list(reader.iter_rows([]))
        assert "二元组" in str(excinfo.value)

    def test_two_tuple_yield_is_accepted(self) -> None:
        reader = _FacadeRowReader(
            item_id="STUB-ITEM", invoke=lambda _payload: iter([("r1", {"a": 1})])
        )
        assert [i for i, _ in reader.iter_rows([])] == ["r1"]

    def test_three_tuple_facades_really_exist_on_the_tree(self) -> None:
        """上面那条的变异对照：三元组门面不是假想形态。"""
        import inspect as _inspect

        for path in (
            "app.services.workpaper_sync.phase5_d4_customer_structure",
            "app.services.workpaper_sync.phase5_d2_03_bad_debt",
        ):
            ret = str(_inspect.signature(_mod(path).iter_store_rows).return_annotation)
            assert ret.count("str") >= 2, (path, ret)


class TestResolutionTriState:
    """三态互斥（`RowReaderResolution.__post_init__`）。"""

    def test_reader_and_reason_cannot_coexist(self) -> None:
        reader = _FacadeRowReader(item_id="X", invoke=lambda _p: iter(()))
        with pytest.raises(OverwritePlanShapeError):
            RowReaderResolution(item_id="X", reader=reader, skip_reason=SkipReason.absent)

    def test_unruled_shape_requires_a_detail(self) -> None:
        with pytest.raises(OverwritePlanShapeError):
            RowReaderResolution(item_id="X")
        assert RowReaderResolution(item_id="X", detail="说明").is_unruled_shape

    def test_skipped_resolution_is_not_unruled(self) -> None:
        res = RowReaderResolution(item_id="X", skip_reason=SkipReason.absent)
        assert not res.is_unruled_shape and not res.is_enumerable


class TestUnruledShapeRatchet:
    """🔴 未裁决形态是**冻结集合**：只许变短，新增一条必须打红（不是计数，是集合）。

    Task 3.4 交付时现算恰 1 条（`g1.trading_financial_assets_detail / G1-2-rows`：G1 声明
    3 段 `acctClass`，门面却是单 spec 薄转发 ⇒ 只 yield 第 ① 段）。

    🔴 **Task 3.7（ADR-AOS-005）把基线清成空集** —— R3 按 spec 逐条枚举，G1 的三段都能寻址。
    这不是「放宽判据凑空集」：`test_baseline_is_empty_because_r3_really_covers_g1` 用**实测**
    证明三段身份都被 yield，且 `test_facade_alone_still_only_covers_one_third` 证明 ① 级那条
    缺陷**依然存在**（只是被第 ② 级兜住了，没有被洗掉）。
    """

    BASELINE: frozenset[tuple[str, str]] = frozenset()

    def _census(self) -> tuple[set[tuple[str, str]], int]:
        from app.services.workpaper_sync.adapters import registry as reg
        from app.services.workpaper_sync.store_projection_response import (
            resolve_store_projection_provider,
        )

        unruled: set[tuple[str, str]] = set()
        enumerable = 0
        for adapter_id in sorted(
            {str(r.get("contract_id") or "") for r in reg.DELIVERED_PER_ENTRY_CONTRACTS} - {""}
        ):
            try:
                provider = resolve_store_projection_provider(adapter_id)
            except Exception:
                continue
            fn = getattr(provider, "all_store_item_ids", None)
            if callable(fn):
                items = tuple(str(x) for x in fn())
            else:
                single = str(getattr(provider, "STORE_ITEM_ID", "") or "")
                items = (single,) if single else ()
            for item in items:
                res = diagnose_row_reader(provider=provider, store_item_id=item)
                if res.is_enumerable:
                    enumerable += 1
                elif res.is_unruled_shape:
                    unruled.add((adapter_id, item))
        return unruled, enumerable

    def test_unruled_set_does_not_grow(self) -> None:
        unruled, enumerable = self._census()
        assert unruled <= self.BASELINE, f"新增未裁决形态 {sorted(unruled - self.BASELINE)}"
        # 变异证明：分母非空（普查真跑了），否则空集合恒满足上面的断言
        assert enumerable > 0, "一条可枚举都没有 ⇒ 普查没真跑，上面的断言无意义"

    def test_baseline_has_no_zombie_entry(self) -> None:
        """禁僵尸：基线里的条目必须仍是未裁决形态（修好了就该从基线移除）。"""
        unruled, _ = self._census()
        assert not (self.BASELINE - unruled), (
            f"基线条目已不再是未裁决形态 {sorted(self.BASELINE - unruled)}，请移除"
        )

    def test_facade_alone_still_only_covers_one_third(self) -> None:
        """🔴 ① 级那条缺陷**依然存在** —— 基线清空不是因为门面被修好了。

        （若哪天门面真被修好，本测试会打红 ⇒ 那时该把它改成正面断言并登记。）
        """
        res = _diagnose_via_facade(provider=_mod(_G1), store_item_id="G1-2-rows")
        assert res.is_unruled_shape
        assert "g1_2_rows_r2" in res.detail and "g1_2_rows_r3" in res.detail
        # 变异对照：同型的 G9（多段门面）在 ① 级就必须**不是**未裁决形态
        facade_g9 = _diagnose_via_facade(provider=_mod(_G9), store_item_id="G9-detail-rows")
        assert facade_g9.is_enumerable
