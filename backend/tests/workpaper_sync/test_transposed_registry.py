"""Task 2 (TDD 锚): TransposedSheetSpec 契约结构 + resolve_transposed_specs 分派语义。

spec: d4-12-transposed-writeback / Requirement 1.1, 1.2 / Property 2

此测试先于通用引擎落地写就（TDD 红锚）：Task 3/4 建 phase5_transposed_sheet /
transposed_registry 后转绿。断言两件事：
1. `TransposedSheetSpec` 数据类字段齐全（含 D4-12 逼出的参数化字段
   first_entity_column / header_field_key / nested_fields_key）。
2. `resolve_transposed_specs(contract)` 按注册表命中：含 d4-29-managed 命中 SPEC_D429、
   含 d4-12-managed 命中 SPEC_D412、两者都含都命中、都不含返空；`is_enabled` 兼容为
   `bool(resolve_transposed_specs(...))`。
"""
from __future__ import annotations

import dataclasses

import pytest

from app.services.workpaper_sync.contracts import load_contract, parse_contract


@pytest.fixture
def contract():
    return load_contract("d4.revenue_detail")


def _contract_with_sheets(contract, sheet_keys):
    """把真实契约裁到只含指定 sheet_key 的子集契约。"""
    payload = dict(contract.canonical_payload)
    payload["sheets"] = [s for s in payload["sheets"] if s["sheet_key"] in sheet_keys]
    return parse_contract(payload, adapter_id=contract.contract_id)


# ── 1. TransposedSheetSpec 字段齐全 ──────────────────────────────────────


def test_spec_dataclass_fields_complete():
    from app.services.workpaper_sync.phase5_transposed_sheet import TransposedSheetSpec

    fields = {f.name for f in dataclasses.fields(TransposedSheetSpec)}
    required = {
        "managed_sheet",
        "sheet_key",
        "table_key",
        "template_id",
        "store_item_id",
        "identity_key",
        "header_row",
        "field_rows",
        "footer_rows",
        "static_prompt_first_row",
        "first_entity_column",
        "initial_entity_column",
        "identity_carrier_row",
        "identity_carrier_prefix",
        "defined_name",
        "managed_ref",
        # D4-12 逼出的参数化：header_row 是否存受管字段 / store 是否嵌套 fields。
        "header_field_key",
        "nested_fields_key",
    }
    missing = required - fields
    assert not missing, f"TransposedSheetSpec 缺字段: {sorted(missing)}"


def test_spec_d429_and_d412_instantiated():
    from app.services.workpaper_sync.phase5_d4_29_customer_detail import SPEC_D429
    from app.services.workpaper_sync.phase5_d4_12_contract import SPEC_D412

    # D4-29 蓝本几何（不得回归）。
    assert SPEC_D429.sheet_key == "d4-29-managed"
    assert SPEC_D429.first_entity_column == "C"
    assert SPEC_D429.header_field_key == "name"
    assert SPEC_D429.nested_fields_key == "fields"

    # D4-12 目标几何（Task 1 冻结）。
    assert SPEC_D412.sheet_key == "d4-12-managed"
    assert SPEC_D412.table_key == "contract_inspection_transposed"
    assert SPEC_D412.store_item_id == "D4-12-contracts-v2"
    assert SPEC_D412.header_row == 10
    assert SPEC_D412.first_entity_column == "B"  # DEC-4: 首列 B 非 C
    assert SPEC_D412.initial_entity_column == "K"
    assert SPEC_D412.identity_carrier_prefix == "GT-CONTRACT-"
    assert SPEC_D412.defined_name == "GT_MANAGED_REGION_D412"
    assert SPEC_D412.managed_ref == "$B$10:$K$31"
    assert SPEC_D412.header_field_key is None  # header 存 indexNo 非受管
    assert SPEC_D412.nested_fields_key is None  # 扁平 store 无 fields 嵌套
    assert len(SPEC_D412.field_rows) == 21
    assert tuple(SPEC_D412.field_rows.values()) == tuple(range(11, 32))


# ── 2. resolve_transposed_specs 分派语义 ─────────────────────────────────


def test_resolve_hits_d429(contract):
    from app.services.workpaper_sync.transposed_registry import resolve_transposed_specs

    specs = resolve_transposed_specs(_contract_with_sheets(contract, {"d4-29-managed"}))
    assert [s.sheet_key for s in specs] == ["d4-29-managed"]


def _contract_with_synthetic_d412(contract, extra_sheet_keys=()):
    """把 D4-12 provider 的 sheet_payload 合成插入契约（Task 8 落盘前用于验证分派）。

    D4-12 sheet_payload 是纯数据（不读文件），字段结构与 D4-29 同构, 可过 parse_contract
    schema 校验。此 helper 让 registry 分派语义在契约正式落盘前即可独立验证。
    """
    from app.services.workpaper_sync import phase5_d4_12_contract as d412

    payload = dict(contract.canonical_payload)
    keep = {"d4-29-managed"} | set(extra_sheet_keys)
    sheets = [s for s in payload["sheets"] if s["sheet_key"] in keep]
    sheets.append(d412.sheet_payload())
    payload["sheets"] = sheets
    return parse_contract(payload, adapter_id=contract.contract_id)


def test_resolve_hits_d412(contract):
    from app.services.workpaper_sync.transposed_registry import resolve_transposed_specs

    # 只含 d4-12-managed（+ 一张非转置 d42 保证 parse 不空）。
    from app.services.workpaper_sync import phase5_d4_12_contract as d412

    payload = dict(contract.canonical_payload)
    sheets = [s for s in payload["sheets"] if s["sheet_key"] == "d42-managed"]
    sheets.append(d412.sheet_payload())
    payload["sheets"] = sheets
    synthetic = parse_contract(payload, adapter_id=contract.contract_id)
    specs = resolve_transposed_specs(synthetic)
    assert [s.sheet_key for s in specs] == ["d4-12-managed"]


def test_resolve_hits_both(contract):
    from app.services.workpaper_sync.transposed_registry import resolve_transposed_specs

    specs = resolve_transposed_specs(_contract_with_synthetic_d412(contract))
    assert {s.sheet_key for s in specs} == {"d4-29-managed", "d4-12-managed"}


def test_resolve_hits_none_when_no_transposed_sheet(contract):
    from app.services.workpaper_sync.transposed_registry import resolve_transposed_specs

    # d42-managed 是普通行表, 非转置。
    specs = resolve_transposed_specs(_contract_with_sheets(contract, {"d42-managed"}))
    assert specs == []


def test_resolve_empty_for_foreign_contract_id(contract):
    from app.services.workpaper_sync.transposed_registry import resolve_transposed_specs

    # contract_id 不是 d4.revenue_detail 时, 即便含转置 sheet 也不命中（分派锁死 entry）。
    from types import SimpleNamespace

    fake = SimpleNamespace(
        contract_id="other.entry",
        sheets=[SimpleNamespace(sheet_key="d4-29-managed")],
    )
    assert resolve_transposed_specs(fake) == []


def test_is_enabled_compat_with_registry(contract):
    from app.services.workpaper_sync.phase5_d4_29_customer_detail import is_enabled
    from app.services.workpaper_sync.transposed_registry import resolve_transposed_specs

    d429 = _contract_with_sheets(contract, {"d4-29-managed"})
    none = _contract_with_sheets(contract, {"d42-managed"})
    assert is_enabled(d429) == bool(resolve_transposed_specs(d429)) is True
    assert is_enabled(none) == bool(resolve_transposed_specs(none)) is False


# ── Task 5 变异反证：泛化是纯灰度，D4-29 不依赖 D4-12 存在 ──────────────


def test_d429_unaffected_when_registry_only_d429(contract, monkeypatch):
    """把 REGISTRY 改回只认 D4-29 单例 → D4-29 分派/往返仍绿（证明纯灰度）。

    这是 design.md 变异 1 的正向：泛化后即使注册表退回单张，D4-29 也不受牵连。
    """
    import io

    from app.services.workpaper_sync import phase5_d4_29_customer_detail as d
    from app.services.workpaper_sync import transposed_registry as reg
    from openpyxl import load_workbook

    monkeypatch.setattr(reg, "REGISTRY", (d.SPEC_D429,))

    # 分派仍命中 D4-29。
    d429_only = _contract_with_sheets(contract, {"d4-29-managed"})
    assert [s.sheet_key for s in reg.resolve_transposed_specs(d429_only)] == ["d4-29-managed"]

    # materialize→extract 往返仍逐字段闭合（不依赖 D4-12 在注册表）。
    from app.services.workpaper_sync import phase5_d4_revenue_detail as provider
    from app.services.workpaper_sync.excel_instrumentation import instrument_workbook_bytes_multi

    template = instrument_workbook_bytes_multi(
        provider.read_authoritative_template(), provider.instrumentation_specs(),
        gate=provider.excel_carrier_gate()).instrumented_bytes
    payload = [{"id": f"id{i}", "name": f"客户{i}", "fields": {k: f"{k}-{i}" for k in d.FIELD_KEYS}}
               for i in range(3)]
    data = d.materialize_transposed_workbook(template, payload)
    assert d.extract_transposed_workbook(data) == payload
    assert d.assert_mapping_digest() == d.EXPECTED_MAPPING_DIGEST


def test_d429_mapping_digest_frozen(contract):
    """泛化后 D4-29 mapping_digest 逐字符冻结（零回归硬锚）。"""
    from app.services.workpaper_sync import phase5_d4_29_customer_detail as d

    assert d.compute_mapping_digest() == "e3193dd9b581ac32041d25d7def13df44955108cce34c0341b05ec30eda17856"
