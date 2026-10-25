# -*- coding: utf-8 -*-
"""H2~H10 definition provisioning 与 Task 76 宿主容错的回归判据。

spec: h-cycle-sync-foundation-and-first-canary + 三份 H lane spec（剩余 Task 16/18 前置）

本文件守三条真实断点：
1. 九个 provider 必须同时导出 `publish_pilot_definitions` + `PILOT_WP_CODES`；缺任一时
   `ProjectionDefinitionProvisioner` 把它判成「provider 空壳」，永远产不出 approved bundle。
2. 共享 publisher 必须真发布四段 definition + typed bundle，且两条契约单向引用校验真跑。
3. Task 76 的 `--check` 遇到别家空壳必须记一条 unresolved 后继续，而不是在第一个缺口
   上抛异常、让全表 51 条只读诊断入口整体不可用。
"""
from __future__ import annotations

import importlib
import importlib.util
import json
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.services.workpaper_sync.definitions import (  # noqa: E402
    bundle_canonical_digest,
    canonical_digest,
    validate_definition_payload,
)
from app.services.workpaper_sync.models import DefinitionKind  # noqa: E402

H_PROVIDERS: dict[str, str] = {
    "h2": "phase5_h2_construction_in_progress",
    "h3": "phase5_h3_investment_property",
    "h4": "phase5_h4_engineering_materials",
    "h5": "phase5_h5_oil_gas_assets",
    "h6": "phase5_h6_asset_disposal_clearing",
    "h7": "phase5_h7_biological_assets",
    "h8": "phase5_h8_right_of_use_assets",
    "h9": "phase5_h9_lease_liabilities",
    "h10": "phase5_h10_asset_disposal_income",
}


@dataclass(frozen=True)
class _Definition:
    definition_id: uuid.UUID
    sha256: str


@dataclass(frozen=True)
class _Bundle:
    bundle_id: uuid.UUID
    canonical_sha256: str


class _DigestingPublisher:
    """与生产 publisher 同尺度算 canonical digest，但不触库。

    这不是「拿 provider 自己算的期望喂回 provider」：definition payload 由 provider 给，
    digest 与 schema 校验由独立的 definitions 内核做；契约冻结 digest 来自磁盘 JSON。
    三方来源不同，任何一侧漂移都会打红。
    """

    def __init__(self) -> None:
        self.definitions: list[tuple[DefinitionKind, str, str]] = []
        self.bundle_slots: dict[Any, Any] | None = None

    async def publish_definition(
        self,
        *,
        kind: Any,
        payload: Any,
        logical_id: str,
        semantic_version: str,
        blob_bytes: bytes | None = None,
        structure_hash: str | None = None,
        approved: bool = True,
    ) -> _Definition:
        resolved = kind if isinstance(kind, DefinitionKind) else DefinitionKind(kind)
        validate_definition_payload(resolved, dict(payload))
        digest = canonical_digest(dict(payload))
        self.definitions.append((resolved, logical_id, digest))
        return _Definition(uuid.uuid5(uuid.NAMESPACE_URL, f"h-test/{resolved.value}/{digest}"), digest)

    async def publish_bundle(
        self,
        *,
        authority_model_definition_id: uuid.UUID,
        authority_model: Any,
        authority_model_definition_sha256: str,
        slots: Any,
        approved: bool = True,
    ) -> _Bundle:
        self.bundle_slots = dict(slots)
        digest = bundle_canonical_digest(
            authority_model=authority_model,
            authority_model_definition_sha256=authority_model_definition_sha256,
            slots=slots,
        )
        return _Bundle(uuid.uuid5(uuid.NAMESPACE_URL, f"h-test/bundle/{digest}"), digest)


@pytest.mark.parametrize("family,module_name", H_PROVIDERS.items())
def test_h_provider_exposes_both_provisioning_whitelist_interfaces(
    family: str, module_name: str
) -> None:
    """九条 provider 的发布面必须逐条非空，不用「至少 N 条」覆盖率蒙混。"""
    mod = importlib.import_module(f"app.services.workpaper_sync.{module_name}")
    assert callable(getattr(mod, "publish_pilot_definitions", None)), (
        f"{family}: 缺 publish_pilot_definitions ⇒ Task 76 判 provider 空壳"
    )
    assert getattr(mod, "PILOT_WP_CODES", None) == mod.WP_CODES, (
        f"{family}: PILOT_WP_CODES 必须逐字转引该 provider 自己的 WP_CODES"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("family,module_name", H_PROVIDERS.items())
async def test_h_provider_publishes_four_valid_definitions_and_a_typed_bundle(
    family: str, module_name: str
) -> None:
    """九条都真跑 publisher；任何一条契约/模板/仪器 digest 漂移都会在此打红。"""
    mod = importlib.import_module(f"app.services.workpaper_sync.{module_name}")
    publisher = _DigestingPublisher()
    definitions = await mod.publish_pilot_definitions(publisher)

    kinds = [kind for kind, _logical_id, _digest in publisher.definitions]
    assert kinds == [
        DefinitionKind.authority_model,
        DefinitionKind.template,
        DefinitionKind.instrumentation,
        DefinitionKind.contract,
    ], f"{family}: 四段发布顺序/集合漂移：{kinds}"
    assert definitions.entry_id == mod.ENTRY_ID
    assert definitions.adapter_id == mod.ADAPTER_ID
    assert definitions.template_definition_sha256 == mod.load_contract_from_disk().template_definition_sha256
    assert (
        definitions.instrumentation_definition_sha256
        == mod.load_contract_from_disk().instrumentation_definition_sha256
    )
    assert publisher.bundle_slots is not None
    assert set(str(getattr(k, "value", k)) for k in publisher.bundle_slots) == {
        "template",
        "instrumentation",
        "contract",
    }
    assert len(definitions.bundle_sha256) == 64


def test_h_wp_code_adjudications_cover_all_nine_entries() -> None:
    """H 的 publisher 有了还不够：缺显式 wp_code 裁决时 Task 76 仍然 unresolved。"""
    path = _BACKEND / "data" / "workpaper_sync_entry_wp_code_adjudication.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    by_id = {r["entry_id"]: r for r in doc["adjudications"]}
    for family, module_name in H_PROVIDERS.items():
        mod = importlib.import_module(f"app.services.workpaper_sync.{module_name}")
        row = by_id.get(mod.ENTRY_ID)
        assert row is not None, f"{family}: wp_code 裁决表缺 {mod.ENTRY_ID}"
        assert row["contract_id"] == mod.ADAPTER_ID
        assert row["wp_codes"] == [family.upper()]
        assert row["resolvable_for_provisioning"] is True
        basis = row["basis"]
        assert (_BACKEND / "wp_templates" / basis["template_relative_path"]).is_file()
        assert basis["managed_excel_name"] in {
            sheet["excel_name"] for sheet in mod.build_contract_payload()["sheets"]
        }
        # 幻影 matcher 码必须与 provisioning 真码不同，否则裁决没有解决任何问题。
        assert set(mod.WP_CODES).isdisjoint(row["wp_codes"])


def _load_task76_module() -> Any:
    path = _BACKEND / "scripts" / "fix" / "fix_task76_provision_projection_definitions.py"
    spec = importlib.util.spec_from_file_location("_task76_h_provisioning_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
async def test_task76_records_provider_interface_gap_as_unresolved_instead_of_crashing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """反向判据：第一个 provider 空壳不得让全表只读诊断入口中断。"""
    from app.services.workpaper_sync.adapters import registry as registry_module
    from app.services.workpaper_sync import projection_provisioning

    task76 = _load_task76_module()
    entry_id = "xlsx/gt-z99-interface-gap"
    monkeypatch.setattr(
        registry_module,
        "DELIVERED_PER_ENTRY_CONTRACTS",
        ({
            "entry_id": entry_id,
            "contract_id": "z99.gap",
            "provider_module": "app.services.workpaper_sync.z99_missing",
        },),
    )

    def _raise(_entry_id: str) -> Any:
        assert _entry_id == entry_id
        raise projection_provisioning.ProviderModuleNotAllowedError("provider 是空壳")

    monkeypatch.setattr(projection_provisioning, "load_projection_supply", _raise)

    class _MustNotTouchDb:
        async def execute(self, *_args: Any, **_kwargs: Any) -> Any:
            raise AssertionError("接口缺口应在触库前结算成 unresolved")

    targets = await task76.resolve_targets(_MustNotTouchDb())
    assert len(targets) == 1
    assert targets[0].entry_id == entry_id
    assert targets[0].resolved is False
    assert "publish_pilot_definitions" in str(targets[0].unresolved_reason)
    assert "PILOT_WP_CODES" in str(targets[0].unresolved_reason)


@pytest.mark.parametrize(
    "module_name,expected_table",
    [
        ("phase5_h3_investment_property", "investment_property_cost_detail_rows"),
        ("phase5_h7_biological_assets", "biological_assets_cost_detail_rows"),
    ],
)
def test_first_publication_derives_primary_table_from_first_multi_sheet_spec(
    module_name: str, expected_table: str
) -> None:
    """H3/H7 双 sheet 不抄 ROWS_TABLE_KEY，也必须确定唯一主 binding。

    独立真源：第一张 instrumentation spec 的 managed_sheet + 契约 sheet/table 结构。
    若实现退回「多表必须有 ROWS_TABLE_KEY」，两条都会打红。
    """
    from app.services.workpaper_sync import projection_first_publication as first_pub

    provider = importlib.import_module(f"app.services.workpaper_sync.{module_name}")
    assert not hasattr(provider, "ROWS_TABLE_KEY"), (
        "本判据要求走结构派生；provider 新增常量后分母形态变了，须重判而非让 fallback 空转"
    )
    contract = provider.load_contract_from_disk()
    assert first_pub._row_bearing_table_key(contract=contract, provider=provider) == expected_table


def test_first_publication_reads_the_first_plural_instrumentation_spec() -> None:
    """回归真实 H9 故障：已有 `instrumentation_specs()` 却硬调单数方法。"""
    from app.services.workpaper_sync import projection_first_publication as first_pub

    first, second = object(), object()

    class _PluralOnly:
        @staticmethod
        def instrumentation_specs() -> tuple[object, object]:
            return first, second

    provider = _PluralOnly()
    assert not hasattr(provider, "instrumentation_spec")
    assert first_pub._primary_instrumentation_spec(provider) is first


def test_first_publication_rejects_an_empty_plural_spec_list() -> None:
    """反向判据：复数入口存在但返回空，不得静默退到别的路径。"""
    from app.services.workpaper_sync import projection_first_publication as first_pub

    class _Empty:
        @staticmethod
        def instrumentation_specs() -> tuple[object, ...]:
            return ()

    with pytest.raises(first_pub.SubstrateStagingError, match="返回空序列"):
        first_pub._primary_instrumentation_spec(_Empty())


def test_first_publication_uses_uuid_col_spelling_from_plural_specs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """回归 H9 第二个真实故障：spec 字段叫 `uuid_col`，旧链只读 `uuid_column`。

    旧实现把 `uuid_column_letter=None` 传给 identity_inventory，Table 虽已注入但 UUID 列
    扫描为空，最后报 `resolved_sheet_by=None`。本判据直接观测传给独立 fingerprint 内核的
    参数，不靠函数源码子串。
    """
    from types import SimpleNamespace
    from app.services import excel_structure_fingerprint as fingerprint
    from app.services.workpaper_sync import excel_entry_gate
    from app.services.workpaper_sync import projection_first_publication as first_pub

    captured: dict[str, Any] = {}

    def _identity_inventory(data: bytes, **kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {"sentinel": True}

    monkeypatch.setattr(fingerprint, "identity_inventory", _identity_inventory)
    monkeypatch.setattr(excel_entry_gate, "parse_identity_inventory", lambda raw: raw)

    spec = SimpleNamespace(table_name="GT_H92_ROWS", uuid_col="W")

    class _PluralOnly:
        @staticmethod
        def instrumentation_specs() -> tuple[Any, ...]:
            return (spec,)

    result = first_pub._observe_identity_inventory(
        instrumented=SimpleNamespace(instrumented_bytes=b"xlsx"),
        provider=_PluralOnly(),
    )
    assert result == {"sentinel": True}
    assert captured["expected_table"] == "GT_H92_ROWS"
    assert captured["uuid_column_letter"] == "W"
