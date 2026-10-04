"""R3 兜底路径（第 ② 级）的契约与变异反证。

spec: workpaper-sync-adopt-overwrite-and-refresh-source · **Task 3.7** · ADR-AOS-005
Requirements 4.1 / 4.4 / 4.5

🔴 为什么是伴生测试文件：`test_aos_row_reader_adapter.py`（Task 3.4，29 例）交付后 **469** 行，
而 `.py` 行数门禁上限 **800** 且 pre-commit 对**暂存的测试文件同样生效**
（`.git-hooks/pre-commit` 把全部 `*.py` 暂存文件都喂给 `check_file_size.py`）⇒ 本任务的
七组判据 + 四组变异反证塞进去会把它顶到门禁边缘。原文件只做**最小改动**（4 例判据下移到 ① 级
+ 棘轮基线清空），Task 3.7 的新判据全在本文件。

每组判据都配反证（判据必须能为 False）：

| 组 | 判据 | 反证 |
| --- | --- | --- |
| 索引覆盖伴生模块 | D1 的 17 个 item 在全域索引里 | 「只看 registry 指定模块」的变体必须漏掉这 17 条 |
| G1 三段 | 3 个 `acctClass` 身份都被 yield | ① 级单独看必须仍只覆盖 1/3（在原文件里断言） |
| 4 条转正 | 门面被借给 G9 的 4 条现在可枚举 | ① 级单独看必须仍是 `row_reader_bound_to_other_entry` |
| 去重 | `D1-memo-rows` / `I5-2-rows` 不把行数两次 | 去掉去重必须翻倍 |
| 对账 | 两路身份集合相等 | 造一个不等的场景必须 fail visible |
| 棘轮 | 顶层未裁决形态 = 空集 | 分母非空 + 基线无僵尸条目 |
| 跳过清单 | 现算 62 并与 ADR 预期对账 | 桶内条数逐项相加必须等于总数 |
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
    _diagnose_via_engine,
    _diagnose_via_facade,
    diagnose_row_reader,
)
from app.services.workpaper_sync.adopt_row_reader_r3 import (
    EngineRowReader,
    ReconcilingRowReader,
    dedup_specs,
    global_spec_index,
    section_value_of,
)

#: ADR-AOS-005 §3 的**预期**值（不是承诺值）。判据现算后与它对账，不符即在断言消息里点名差异。
#: 🔴 **棘轮上界，不是等值** —— tasks.md 顶部纪律明写「R3 相关判据**禁写死 104 / 62
#: 这类计数**…不得断言等于某个常量」。等值断言会把「有人给某个 provider 补上行枚举器
#: 门面」这种**改善**判成失败（实测已发生：`absent` 8→7、跳过清单 62→61）。
#: 先例 = 同域 `test_aos_skip_whitelist_guard.py`（Task 4.8）对**同一个数**已经只当棘轮上限用。
ADR_EXPECTED_SKIP_TOTAL = 62
ADR_EXPECTED_SKIP_BEFORE_R3 = 104
#: design §4.1b (4) 现算「有 R3 替代路径」的条数（预期值，同上）。
ADR_EXPECTED_R3_RESCUED = 42

#: ADR §2(b) 勘误后的 4 条（**不是** `G4-2-rows` / `G6-2-rows`）。
BOUND_TO_G9 = (
    ("g3.dividend_receivable_detail", "G3-2-detail-rows"),
    ("g4.bond_main", "G4-7-items"),
    ("g5.long_term_receivable_detail", "G5-2-rows"),
    ("g6.other_bond_main", "G6-5-fair-value-data"),
)

#: ADR §5(3) 的两个去重陷阱：多 spec 但无分区字段。
DEDUP_TRAPS = ("D1-memo-rows", "I5-2-rows")


def _mod(path: str) -> Any:
    return importlib.import_module("app.services.workpaper_sync." + path)


@dataclass(frozen=True)
class _StubSpec:
    """替身 spec —— 只带引擎与本层真正读的那几个声明字段。"""

    store_item_id: str
    table_key: str
    row_identity_key: str = "someOtherKey"
    row_section_field: str = ""
    row_section_value: str = ""


def _synthetic_payload(item_id: str) -> list[dict[str, Any]]:
    """按**声明**为一个 item 造一行/段的合成载荷（测试里也不许写键名字面量）。"""
    specs = dedup_specs(global_spec_index()[item_id], store_item_id=item_id)
    rows: list[dict[str, Any]] = []
    for ordinal, spec in enumerate(specs):
        row: dict[str, Any] = {spec.row_identity_key: f"synth-{ordinal}"}
        if spec.row_section_field:
            row[spec.row_section_field] = spec.row_section_value
        rows.append(row)
    return rows


def _census() -> dict[str, Any]:
    """三级优先级生效后的全域普查（B 分母 = adopt 真实枚举的集合）。

    🔴 现算，禁写死：ADR §3 明写 62 是**预期值**而非承诺值。
    """
    from app.services.workpaper_sync.adapters import registry as reg
    from app.services.workpaper_sync.store_projection_response import (
        resolve_store_projection_provider,
    )

    out: dict[str, Any] = {
        "enumerable": [],
        "reconciled": [],
        "r3_only": [],
        "facade_only": [],
        "unruled": set(),
        "skipped": [],
        "no_store_item": 0,
    }
    for adapter_id in sorted(
        {str(r.get("contract_id") or "") for r in reg.DELIVERED_PER_ENTRY_CONTRACTS} - {""}
    ):
        try:
            provider = resolve_store_projection_provider(adapter_id)
        except Exception:  # noqa: BLE001 —— adapter 级 import 失败不在本层观测范围（L1）
            continue
        fn = getattr(provider, "all_store_item_ids", None)
        if callable(fn):
            items = tuple(str(x) for x in fn())
        else:
            single = str(getattr(provider, "STORE_ITEM_ID", "") or "")
            items = (single,) if single else ()
        if not items:
            out["no_store_item"] += 1
            continue
        for item in items:
            res = diagnose_row_reader(provider=provider, store_item_id=item)
            pair = (adapter_id, item)
            if res.is_enumerable:
                out["enumerable"].append(pair)
                if isinstance(res.reader, ReconcilingRowReader):
                    out["reconciled"].append(pair)
                elif isinstance(res.reader, EngineRowReader):
                    out["r3_only"].append(pair)
                else:
                    out["facade_only"].append(pair)
            elif res.is_unruled_shape:
                out["unruled"].add(pair)
            else:
                out["skipped"].append((adapter_id, item, res.skip_reason.value))
    return out


class TestGlobalSpecIndexCoversCompanionModules:
    """🔴 ADR §4(1)：索引必须覆盖伴生模块，否则 D1 的 17 条假阴。"""

    D1_PROVIDER = "phase5_d1_notes_receivable"
    D1_COMPANION = "phase5_d1_expansion"

    def _registry_only_index(self) -> dict[str, tuple[Any, ...]]:
        """**变异体**：同一索引器只看 registry 指定模块（`_declared_specs` 的口径）。"""
        from app.services.workpaper_sync.adapters import registry as reg
        from app.services.workpaper_sync.adopt_row_reader_r3 import SPECS_NAME
        from app.services.workpaper_sync.store_projection_response import (
            resolve_store_projection_provider,
        )

        index: dict[str, list[Any]] = {}
        for rec in reg.DELIVERED_PER_ENTRY_CONTRACTS:
            adapter_id = str(rec.get("contract_id") or "")
            if not adapter_id:
                continue
            try:
                provider = resolve_store_projection_provider(adapter_id)
                fn = getattr(provider, SPECS_NAME, None)
                specs = tuple(fn()) if callable(fn) else ()
            except Exception:  # noqa: BLE001
                continue
            for spec in specs:
                index.setdefault(str(getattr(spec, "store_item_id", "")), []).append(spec)
        return {k: tuple(v) for k, v in index.items()}

    def test_registry_designated_module_really_has_no_declaration_surface(self) -> None:
        """前提事实现读：registry 指向的模块确实没有声明面，spec 确实住在伴生模块。"""
        from app.services.workpaper_sync.adopt_row_reader_r3 import SPECS_NAME

        assert not callable(getattr(_mod(self.D1_PROVIDER), SPECS_NAME, None))
        companion = tuple(getattr(_mod(self.D1_COMPANION), SPECS_NAME)())
        assert companion, "伴生模块声明面为空 ⇒ 下面的判据会变成空分母"

    def test_full_index_covers_all_d1_items(self) -> None:
        full = global_spec_index()
        d1_items = {
            str(s.store_item_id)
            for s in tuple(_mod(self.D1_COMPANION).managed_row_table_specs())
        }
        assert d1_items <= set(full), sorted(d1_items - set(full))
        # 与 ADR §4(1) 的 17 对账（现算为准，不符则点名差异）
        assert len(d1_items) == 17, f"D1 item 现算 {len(d1_items)}，ADR §4(1) 记 17"

    def test_mutation_registry_only_index_misses_all_d1_items(self) -> None:
        """🔴 变异反证：只看 registry 指定模块的索引器必须**一条 D1 都索引不到**。

        漏不掉就说明索引器根本没在按模块取 spec（比如偷偷扫了全仓常量），判据失效。
        """
        narrow = self._registry_only_index()
        full = global_spec_index()
        d1_items = {
            str(s.store_item_id)
            for s in tuple(_mod(self.D1_COMPANION).managed_row_table_specs())
        }
        assert d1_items & set(narrow) == set(), sorted(d1_items & set(narrow))
        assert d1_items <= set(full)
        # 分母非空：变异体本身不是空索引（否则「漏掉」恒成立）
        assert len(narrow) > 0 and len(full) > len(narrow)

    def test_index_is_not_cached(self) -> None:
        """🔴 ADR §5(1) 禁缓存：两次调用必须是**不同对象**（灰度开关一开就得看见）。"""
        first, second = global_spec_index(), global_spec_index()
        assert first is not second
        assert first.keys() == second.keys()


class TestR3SolvesG1SectionCoverage:
    """ADR §2(a)：`G1-2-rows` 的 3 段全部可寻址（① 级只覆盖 1/3）。"""

    ITEM = "G1-2-rows"

    def test_three_declared_sections_are_all_yielded(self) -> None:
        specs = dedup_specs(global_spec_index()[self.ITEM], store_item_id=self.ITEM)
        values = [s.row_section_value for s in specs]
        # 分区值取自**声明**，这里只断言它确实是 ADR 点名的那三段
        assert set(values) == {"trading", "classified_fvpl", "designated_fvpl"}
        assert {s.row_section_field for s in specs} == {"acctClass"}
        res = diagnose_row_reader(
            provider=_mod("phase5_g1_trading_financial_assets"), store_item_id=self.ITEM
        )
        assert res.is_enumerable, res.detail
        assert isinstance(res.reader, EngineRowReader)
        payload = _synthetic_payload(self.ITEM)
        got = list(res.reader.iter_rows(payload))
        assert [res.reader.section_of(row) for _identity, row in got] == values
        assert len(got) == 3
        assert set(res.covered_sections) == set(values)
        assert len(res.declared_scopes) == 3

    def test_detail_records_that_the_facade_path_was_the_one_that_failed(self) -> None:
        """降级必须**可读**：顶层 detail 要说明是门面路不行才走的 R3。"""
        res = diagnose_row_reader(
            provider=_mod("phase5_g1_trading_financial_assets"), store_item_id=self.ITEM
        )
        assert "R3" in res.detail and "门面" in res.detail


class TestR3TakesOverBoundFacades:
    """ADR §2(b)：门面 re-export 自 `phase5_g9_store_facade` 的 4 条转为可枚举。"""

    @pytest.mark.parametrize(("adapter_id", "item_id"), BOUND_TO_G9)
    def test_facade_level_is_still_bound_to_other_entry(
        self, adapter_id: str, item_id: str
    ) -> None:
        """反证：① 级那条真缺陷**没被洗掉**（工单仍在，只是被兜住了）。"""
        from app.services.workpaper_sync.store_projection_response import (
            resolve_store_projection_provider,
        )

        provider = resolve_store_projection_provider(adapter_id)
        facade = _diagnose_via_facade(provider=provider, store_item_id=item_id)
        assert facade.skip_reason is SkipReason.row_reader_bound_to_other_entry
        assert facade.facade_module.endswith("phase5_g9_store_facade")

    @pytest.mark.parametrize(("adapter_id", "item_id"), BOUND_TO_G9)
    def test_top_level_is_enumerable_via_engine(self, adapter_id: str, item_id: str) -> None:
        from app.services.workpaper_sync.store_projection_response import (
            resolve_store_projection_provider,
        )

        provider = resolve_store_projection_provider(adapter_id)
        res = diagnose_row_reader(provider=provider, store_item_id=item_id)
        assert res.is_enumerable, res.detail
        assert isinstance(res.reader, EngineRowReader)
        assert res.skip_reason is None
        # 真枚举一遍：声明的每个分区都必须被 yield
        got = list(res.reader.iter_rows(_synthetic_payload(item_id)))
        assert len(got) == len(res.declared_scopes)
        assert set(res.covered_sections) == {
            section for _table, section in res.declared_scopes
        }


class TestPerSectionDedup:
    """ADR §5(3)：逐 spec 枚举必须按 `(item, row_section_value)` 去重。"""

    @pytest.mark.parametrize("item_id", DEDUP_TRAPS)
    def test_trap_really_is_multi_spec_without_section_field(self, item_id: str) -> None:
        """前提事实现算：确实是「多 spec 且无分区字段」，否则下面的判据是空分母。"""
        raw = global_spec_index()[item_id]
        assert len(raw) > 1
        assert {str(s.row_section_field or "") for s in raw} == {""}

    @pytest.mark.parametrize("item_id", DEDUP_TRAPS)
    def test_row_count_is_not_doubled(self, item_id: str) -> None:
        raw = global_spec_index()[item_id]
        deduped = dedup_specs(raw, store_item_id=item_id)
        assert len(deduped) == 1, [s.table_key for s in deduped]
        res = _diagnose_via_engine(store_item_id=item_id)
        assert res.is_enumerable, res.detail
        key = deduped[0].row_identity_key
        payload = [{key: "a"}, {key: "b"}]
        got = list(res.reader.iter_rows(payload))
        assert [identity for identity, _row in got] == ["a", "b"]

    @pytest.mark.parametrize("item_id", DEDUP_TRAPS)
    def test_mutation_without_dedup_the_row_count_doubles(self, item_id: str) -> None:
        """🔴 变异反证：去掉去重（直接喂 raw spec）行数必须翻倍。"""
        raw = global_spec_index()[item_id]
        key = raw[0].row_identity_key
        payload = [{key: "a"}, {key: "b"}]
        no_dedup = EngineRowReader(item_id=item_id, specs=raw)
        got = list(no_dedup.iter_rows(payload))
        assert len(got) == 2 * len(payload) == 4
        assert [identity for identity, _row in got] == ["a", "b", "a", "b"]

    def test_sectioned_item_keeps_every_section(self) -> None:
        """反向：有分区字段时去重**不得**把段合并掉（G5 的 12 段必须全留）。"""
        raw = global_spec_index()["G5-2-rows"]
        assert len(dedup_specs(raw, store_item_id="G5-2-rows")) == len(raw) == 12

    def test_mixed_section_field_declaration_fails_visible(self) -> None:
        """结构性零的变异证明：现算 0 例「部分声明分区字段」，stub 造一例必须打红。"""
        mixed = (
            _StubSpec("ITEM-M", "t1", row_section_field="acctClass", row_section_value="a"),
            _StubSpec("ITEM-M", "t2"),
        )
        with pytest.raises(OverwritePlanShapeError) as excinfo:
            dedup_specs(mixed, store_item_id="ITEM-M")
        assert "ITEM-M" in str(excinfo.value)
        # 同一段判据在全域真实 spec 上必须一条都不打红（那个 0 是事实）
        index = global_spec_index()
        for item, specs in index.items():
            dedup_specs(specs, store_item_id=item)

    def test_duplicate_scope_with_conflicting_identity_key_fails_visible(self) -> None:
        """同 (item, 分区) 的重复 spec 身份键不一致 ⇒ 留哪条都会换口径 ⇒ 当场抛。"""
        conflicting = (
            _StubSpec("ITEM-K", "t1", row_identity_key="rowId"),
            _StubSpec("ITEM-K", "t2", row_identity_key="id"),
        )
        with pytest.raises(OverwritePlanShapeError) as excinfo:
            dedup_specs(conflicting, store_item_id="ITEM-K")
        assert "row_identity_key" in str(excinfo.value)
        # 反证：身份键一致时不抛（判据不是恒真）
        assert len(dedup_specs(
            (
                _StubSpec("ITEM-K", "t1", row_identity_key="rowId"),
                _StubSpec("ITEM-K", "t2", row_identity_key="rowId"),
            ),
            store_item_id="ITEM-K",
        )) == 1


class _StubReader:
    """只 yield 给定身份的 reader 替身 —— 用来造「两路不等」的场景。"""

    def __init__(self, identities: tuple[str, ...], *, field: str = "") -> None:
        self._identities = identities
        self.section_field = field
        self.declared_scopes: tuple[tuple[str, str | None], ...] = ()

    def iter_rows(self, payload: Any):  # noqa: ANN201 —— 协议形态，返回迭代器
        for identity in self._identities:
            yield identity, {"payload_seen": payload}

    def section_of(self, row: Any) -> str | None:
        return section_value_of(row, field=self.section_field, item_id="stub")


class TestTwoPathReconciliation:
    """ADR §5(2)：两路都可用 ⇒ 门面优先 + 身份集合对账，不等即 fail visible。"""

    def test_both_paths_available_items_are_wrapped(self) -> None:
        census = _census()
        assert census["reconciled"], "一条被包的都没有 ⇒ 对账根本没接上"
        # 门面独占（无 R3 spec）与 R3 独占的两类也必须各自非空，否则三级编排退化成两级
        assert census["facade_only"], "没有「只有门面路」的 item ⇒ 分支未被覆盖"
        assert census["r3_only"], "没有「只有 R3」的 item ⇒ 兜底分支未被覆盖"

    def test_every_wrapped_item_agrees_on_a_synthetic_payload(self) -> None:
        """真跑一遍：每个被包的 item 在按声明合成的载荷上两路必须一致（不抛即一致）。"""
        from app.services.workpaper_sync.store_projection_response import (
            resolve_store_projection_provider,
        )

        census = _census()
        checked = 0
        for adapter_id, item_id in census["reconciled"]:
            provider = resolve_store_projection_provider(adapter_id)
            reader = diagnose_row_reader(provider=provider, store_item_id=item_id).reader
            assert isinstance(reader, ReconcilingRowReader)
            got = list(reader.iter_rows(_synthetic_payload(item_id)))
            assert got, f"{item_id} 两路一致但零行 ⇒ 合成载荷没造对"
            checked += 1
        assert checked == len(census["reconciled"]) > 0

    def test_divergent_paths_fail_visible(self) -> None:
        """🔴 造一个不等的场景：必须当场抛，且文案点名两侧各自独有的身份。"""
        primary = _StubReader(("a", "b"))
        shadow = _StubReader(("a", "c"))
        reader = ReconcilingRowReader(item_id="ITEM-X", primary=primary, shadow=shadow)
        with pytest.raises(OverwritePlanShapeError) as excinfo:
            list(reader.iter_rows([]))
        message = str(excinfo.value)
        assert "ITEM-X" in message and "'b'" in message and "'c'" in message

    def test_mutation_without_reconciliation_the_divergence_goes_unnoticed(self) -> None:
        """🔴 变异反证：去掉对账（直接用 primary），同一场景必须**不再**报错。

        这证明上一条打红是对账在起作用，而不是场景本身自带异常。
        """
        primary = _StubReader(("a", "b"))
        got = list(primary.iter_rows([]))
        assert [identity for identity, _row in got] == ["a", "b"]

    def test_equal_sets_yield_the_primary_rows_verbatim(self) -> None:
        """相等时按 primary 原样 yield（门面优先），不取并集也不重排。"""
        reader = ReconcilingRowReader(
            item_id="ITEM-Y",
            primary=_StubReader(("a", "b")),
            shadow=_StubReader(("b", "a")),
        )
        got = list(reader.iter_rows(["载荷原样透传"]))
        assert [identity for identity, _row in got] == ["a", "b"]
        assert got[0][1] == {"payload_seen": ["载荷原样透传"]}

    def test_wrapper_exposes_the_same_attribute_surface(self) -> None:
        """包装器不得让「包不包」变成调用方可观测的差异。"""
        inner = _StubReader(("a",), field="acctClass")
        inner.declared_scopes = (("t1", "alpha"),)
        reader = ReconcilingRowReader(item_id="ITEM-Z", primary=inner, shadow=inner)
        assert reader.section_field == "acctClass"
        assert reader.declared_scopes == (("t1", "alpha"),)
        assert reader.section_of({"acctClass": "alpha"}) == "alpha"


class TestSkipCensusRecount:
    """跳过清单复算 + 与 ADR §3 预期对账（🔴 现算为准，不符即点名差异）。"""

    def test_skip_total_reconciles_with_adr_expectation(self) -> None:
        census = _census()
        total = len(census["skipped"]) + len(census["unruled"])
        by_reason: dict[str, int] = {}
        for _adapter, _item, reason in census["skipped"]:
            by_reason[reason] = by_reason.get(reason, 0) + 1
        # 桶内逐项相加必须等于总数（分桶登记不得漏项）
        assert sum(by_reason.values()) + len(census["unruled"]) == total
        assert total > 0, "跳过清单为空 ⇒ 普查没真跑，棘轮在空集上恒真"
        assert total <= ADR_EXPECTED_SKIP_TOTAL, (
            f"跳过清单现算 {total} > ADR-AOS-005 §3 棘轮上限 "
            f"{ADR_EXPECTED_SKIP_TOTAL} ⇒ 有 item **退回了不可枚举**（只许变短）；"
            f"分桶 {by_reason} · 未裁决 {sorted(census['unruled'])}"
        )

    def test_r3_rescued_count_reconciles_with_design(self) -> None:
        """R3 救回的条数**必须按来源分两桶**，否则三层对账差 1。

        🔴 Task 3.7 现算抓到的差异：R3 救回合计 **43**，而 design §4.1b(4) 记 **42**。
        两个数都对，因为它们的**分母不同** —— 42 是「104 条跳过清单里有 R3 路径的」，而
        `G1-2-rows` 从来**不在**那 104 里：Task 1.2 把它算进「可枚举 25」，Task 3.4 的覆盖面
        判据才把它挪进「未裁决形态」（那一轮的普查是 `24 + 104 + 1 = 129`）。
        ⇒ `43 = 42（来自跳过清单）+ 1（来自未裁决形态，即 G1）`，两条等式分别断言。
        """
        from app.services.workpaper_sync.store_projection_response import (
            resolve_store_projection_provider,
        )

        census = _census()
        from_unruled: list[str] = []
        from_skip: list[str] = []
        for adapter_id, item_id in census["r3_only"]:
            provider = resolve_store_projection_provider(adapter_id)
            facade = _diagnose_via_facade(provider=provider, store_item_id=item_id)
            (from_unruled if facade.is_unruled_shape else from_skip).append(item_id)
        assert len(from_skip) + len(from_unruled) == len(census["r3_only"])
        # ① 104 = 62（仍跳过）+ 42（跳过清单里被 R3 救回的）
        assert len(from_skip) > 0, "被救回的一桶为空 ⇒ 下面的守恒在空集上恒真"
        assert len(census["skipped"]) + len(from_skip) <= ADR_EXPECTED_SKIP_BEFORE_R3, (
            f"104 = 62 + 42 的对账不成立：现算 跳过 {len(census['skipped'])} + "
            f"跳过清单里被救回 {len(from_skip)}"
        )
        # 🔴 **不**断言 `len(from_skip) == 42`：它两个方向都会合法移动
        #    （item 得到门面而彻底离开跳过清单 ⇒ 变小；新增 R3 路径 ⇒ 变大），
        #    写成等值就是本轮要根治的那个缺陷。守恒由上面那条棘轮兼顾。
        assert len(from_skip) <= ADR_EXPECTED_SKIP_BEFORE_R3, len(from_skip)
        # ② 另一桶恰是 G1 那一条（来自未裁决形态，不属那 104）
        assert from_unruled == ["G1-2-rows"], from_unruled

    def test_the_ratchet_can_actually_go_red(self) -> None:
        """🔴 棘轮必须配变异反证 —— 一个永远不会红的棘轮等于没有守卫。

        本轮把两条等值对账改成了「只许变小」（依据 = tasks.md 顶部纪律「R3 相关判据
        禁写死 104 / 62…不得断言等于某个常量」）。改完必须证明：**数变大仍然会红** ——
        否则改棘轮只是把假红换成了恒绿（平台铁律 ㉻：有门禁 ≠ 门禁生效）。

        判据形态 = 把棘轮谓词在**合成值**上跑三档：变小（改善）/ 持平 / 变大（退回）。
        不碰真普查 ⇒ 不依赖当前并发会话把数推到了哪里。
        """
        ceiling = ADR_EXPECTED_SKIP_TOTAL

        def ratchet_holds(current: int) -> bool:
            return current > 0 and current <= ceiling

        assert ratchet_holds(ceiling - 1), "变小（改善）被判成失败 ⇒ 棘轮方向反了"
        assert ratchet_holds(ceiling), "持平应当通过"
        assert not ratchet_holds(ceiling + 1), (
            "数变大竟然不红 ⇒ 棘轮是恒绿的，比原来的等值断言更糟"
        )
        assert not ratchet_holds(0), (
            "普查塔缩成 0 竟然通过 ⇒ 扫描器坏了也看不出来（结构性零陷阱）"
        )
        # 反向：现算值确实落在棘轮内（否则上面三档是在评估一个与现实无关的谓词）
        census = _census()
        live = len(census["skipped"]) + len(census["unruled"])
        assert ratchet_holds(live), f"现算 {live} 不在棘轮内"

    def test_skip_reason_domain_is_unchanged(self) -> None:
        """🔴 ADR §5(4)：走 R3 解题 ⇒ `SkipReason` 封闭域**六成员不变**（不得为本任务扩域）。"""
        assert [m.value for m in SkipReason] == [
            "import_failed",
            "absent",
            "item_blind",
            "item_unresolvable",
            "row_reader_bound_to_other_entry",
            "no_store_item",
        ]

    def test_remaining_skips_really_have_no_r3_path(self) -> None:
        """留在跳过清单里的每一条都必须**确实**没有 R3 路径（否则是失效的白名单条目）。"""
        census = _census()
        index = global_spec_index()
        leaked = [
            (adapter, item, reason)
            for adapter, item, reason in census["skipped"]
            if item in index
        ]
        assert leaked == [], leaked
        # 分母非空：索引本身覆盖了大量 item（否则「都不在索引里」恒成立）
        assert len(index) > len(census["skipped"]) // 2 > 0


class TestTopLevelUnruledRatchetIsEmpty:
    """子项 7：顶层未裁决形态冻结集合 = **空集**，且基线无僵尸条目。"""

    BASELINE: frozenset[tuple[str, str]] = frozenset()

    def test_top_level_unruled_set_is_empty(self) -> None:
        census = _census()
        assert census["unruled"] == set(), (
            f"顶层仍有未裁决形态 {sorted(census['unruled'])} —— 如实登记，不得放宽判据凑空集"
        )
        # 分母非空：普查真跑了
        assert len(census["enumerable"]) > 0

    def test_baseline_has_no_zombie_entry(self) -> None:
        """基线是空集 ⇒ 僵尸条目检查退化为「空集减空集」，故显式断言它**确实**是空集。

        这条不是同义反复：若有人为了让别处变绿往 BASELINE 里塞条目，这里立刻打红。
        """
        census = _census()
        assert self.BASELINE == frozenset()
        assert not (self.BASELINE - census["unruled"])

    def test_facade_level_still_produces_one_unruled_case(self) -> None:
        """🔴 空集不是「判据失效」：① 级单独看现算仍恰 1 例（G1），证明扫描器还在工作。"""
        facade_unruled = {
            item
            for item in ("G1-2-rows",)
            if _diagnose_via_facade(
                provider=_mod("phase5_g1_trading_financial_assets"), store_item_id=item
            ).is_unruled_shape
        }
        assert facade_unruled == {"G1-2-rows"}
