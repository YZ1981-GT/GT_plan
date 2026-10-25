# -*- coding: utf-8 -*-
"""I 循环五环发布 + I5 同 store 双物理区回归守卫。

spec: i-cycle-sync-foundation-and-first-canary + 两份 I lane spec（2026-10-01 门收口）
"""
from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]

I_PROVIDERS = {
    "xlsx/gt-i1-intangible-assets": "phase5_i1_intangible_assets",
    "xlsx/gt-i2-development-expenditure": "phase5_i2_development_expenditure",
    "xlsx/gt-i3-goodwill": "phase5_i3_goodwill",
    "xlsx/gt-i4-long-term-prepaid": "phase5_i4_long_term_prepaid",
    "xlsx/gt-i5-other-noncurrent-assets": "phase5_i5_other_noncurrent_assets",
    "xlsx/gt-i6-research-development-expense": "phase5_i6_research_development_expense",
}


def _provider(name: str):
    return importlib.import_module(f"app.services.workpaper_sync.{name}")


@pytest.mark.parametrize("entry_id,module", I_PROVIDERS.items())
def test_each_i_provider_has_complete_five_ring_surface(entry_id: str, module: str) -> None:
    """缺任一符号，task76/首版发布/运行时 attach 至少断一环。"""
    p = _provider(module)
    assert p.ENTRY_ID == entry_id
    for name in (
        "publish_pilot_definitions", "attach_pilot_adapters", "PILOT_WP_CODES",
        "instrumentation_spec", "instrumentation_specs", "build_store_projection",
        "merge_projection_into_store_rows", "iter_store_rows", "assert_contract_file_matches_source",
    ):
        assert hasattr(p, name), f"{module}: 缺 {name}"
    assert p.UUID_COL == p.instrumentation_spec().uuid_col
    assert p.ROWS_TABLE_KEY == p.managed_row_table_specs()[0].table_key
    assert p.assert_contract_file_matches_source().contract_id == p.ADAPTER_ID


def test_live_manifest_marks_all_six_i_entries_bidirectional() -> None:
    manifest = json.loads(
        (ROOT / "backend/data/workpaper_sync_entry_manifest.json").read_text(encoding="utf-8")
    )
    by_id = {e["entry_id"]: e for e in manifest["entries"]}
    assert set(I_PROVIDERS) <= set(by_id)
    for entry_id, module in I_PROVIDERS.items():
        p = _provider(module)
        live = by_id[entry_id]
        assert live["capability"] == "bidirectional"
        assert live["migration_state"] == "adapter_registered"
        assert live["adapter_id"] == p.ADAPTER_ID
        assert live["canonical_resolver"] == "workpaper_sync_published_representation"


def _i5_rows() -> list[dict]:
    return [
        {
            "rowId": f"row-{n}",
            "projectName": f"项目{n}",
            "gross": {"unadjOpening": n * 100, "ajeIncrease": n * 7},
            "impairment": {"unadjOpening": n * 10, "ajeIncrease": n * 3},
        }
        for n in range(1, 4)
    ]


def test_i5_two_physical_regions_have_distinct_uuid_columns_and_exclude_placeholder() -> None:
    p = _provider("phase5_i5_other_noncurrent_assets")
    gross, impairment = p.managed_row_table_specs()
    assert gross.store_item_id == impairment.store_item_id == "I5-2-rows"
    assert (gross.uuid_col, impairment.uuid_col) == ("R", "S")
    assert (gross.first_data_row, gross.last_data_row, gross.footer_row) == (11, 20, 22)
    assert (impairment.first_data_row, impairment.last_data_row, impairment.footer_row) == (24, 33, 35)


def test_i5_shared_store_projection_namespaces_sibling_and_merges_back_to_one_row_set() -> None:
    p = _provider("phase5_i5_other_noncurrent_assets")
    rows = _i5_rows()
    contract = p.assert_contract_file_matches_source()
    projection = p.build_store_projection(json.dumps(rows, ensure_ascii=False), contract=contract)
    gross, impairment = p.managed_row_table_specs()
    assert projection.row_keys[gross.table_key] == ("row-1", "row-2", "row-3")
    sibling = projection.row_keys[impairment.table_key]
    assert len(sibling) == 3
    assert all(r.endswith(f"~gt:{impairment.table_key}") for r in sibling)

    merged, *_ = p.merge_projection_into_store_rows(projection=projection, base_rows=rows)
    assert [r["rowId"] for r in merged] == ["row-1", "row-2", "row-3"]
    assert [r["gross"]["unadjOpening"] for r in merged] == [100, 200, 300]
    assert [r["impairment"]["unadjOpening"] for r in merged] == [10, 20, 30]


def test_sanitized_i_templates_pass_ooxml_gate() -> None:
    """提交态只要求 live 模板通过安全门；`.preclean.bak` 是本地净化脚本的忽略态审计负例。"""
    from app.services.workpaper_sync.ooxml_security import validate_ooxml_artifact

    for name in ("I2 开发支出.xlsx", "I3 商誉.xlsx", "I4 长期待摊费用.xlsx", "I5 其他非流动资产.xlsx"):
        live = ROOT / "backend/wp_templates/I" / name
        validate_ooxml_artifact(live, document_type="xlsx")
