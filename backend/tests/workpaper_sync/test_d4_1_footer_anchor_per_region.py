# -*- coding: utf-8 -*-
"""D4-1 同 sheet 双区 footer-anchor per-region 解析 —— 行为级验证（judge-first）。

spec: d4-1-adjudication-bidirectional-writeback-and-formula-io · Task 6 判据② materialize 侧
Requirements 1.1 / 1.2 / 5.4：materialize 侧 footer 门必须按 **region** 解析冻结 footer 行
（一个 sheet_key 对应 N 个 template_id 时），不回归单 region / 多 sheet-单区 场景。

═══ 已核实的 ROOT CAUSE ═══

`excel_materialize.assert_footer_anchor_stable(..., table_key=X)` 原来用
`_resolve_frozen_footer_row(runtime_binding, sheet_key=sheet_for_table.sheet_key)` 取冻结
footer 行，而 `_template_ids_from_sheet_key('d41-managed')` 只得到单个 `D41`。但
instrumentation 写的是 per-SPEC 键 `GT_FOOTER_ROW_D41MAIN`(=12) / `GT_FOOTER_ROW_D41OTHER`
(=18)（D4-1 两 spec 的 template_id 各为 D41MAIN/D41OTHER，共享 sheet_key `d41-managed`）。
于是 `GT_FOOTER_ROW_D41` 找不到 → 回退裸 `GT_FOOTER_ROW`（combined entry 里 = D4-2 primary
的 31）→ 主营区 `小计` 实测 R12、冻结 31 → `FooterAnchorDriftError`。

此外可见侧同一 marker（`小计`）在每区各出现一次（主营 R12 / 其他 R18），原全局搜索恒取
第一处（R12），给「其他」区判 footer 时会误取主营的 R12。

═══ 修复 ═══

* 冻结侧：`_resolve_frozen_footer_row` 优先按本 region 的物理 `table_name`（binding/region）
  经隐藏 `_GT_SYNC` 平行清册 `GT_MANAGED_TABLES`/`GT_TEMPLATE_IDS` 定位 template_id，取
  `GT_FOOTER_ROW_{TID}`；缺省退回 sheet_key 路径，最后裸 `GT_FOOTER_ROW`。
* 可见侧：`_find_marker_row(..., min_row=region.first_row)` 从本区数据首行起搜，
  两区各归各的 marker 行。

本文件锁死判据：
1. resolver：main table_name → 12，other → 18（给平行清册 + per-TID footer 键）。
2. assert_footer_anchor_stable 在真实双区注入产物上，对两区各自通过（R12↔12 / R18↔18），
   即使裸 `GT_FOOTER_ROW`=31（模拟 combined entry 的 D4-2 primary 回退）。
3. 变异守卫：退回 sheet_key-only 冻结解析（不传 table_name）→ 回退裸 31 → drift 必红。
4. 无回归：单 region / 多 sheet-单区（sheet_key→单 TID）解析逐字不变。
5. 不削弱漂移检测：真移了 footer（marker 与冻结不符）仍抛 drift。
"""
from __future__ import annotations

import io
import os
import sys
import zipfile
from pathlib import Path
from typing import Any

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.workpaper_sync import excel_materialize as M  # noqa: E402
from app.services.workpaper_sync import phase5_d4_adjudication_sheet as D41  # noqa: E402
from app.services.workpaper_sync import phase5_d4_revenue_detail as D4  # noqa: E402
from app.services.workpaper_sync.contracts import parse_contract  # noqa: E402
from app.services.workpaper_sync.excel_extract import (  # noqa: E402
    ExcelIdentityBinding,
    read_runtime_binding_pairs,
    resolve_managed_region,
)

D41_TABLE_NAME_MAIN = "GT_D41_MAIN_ROWS"
D41_TABLE_NAME_OTHER = "GT_D41_OTHER_ROWS"
D41_TABLE_KEY_MAIN = "adjudication_main_rows"
D41_TABLE_KEY_OTHER = "adjudication_other_rows"
FOOTER_MAIN = "12"
FOOTER_OTHER = "18"
#: combined entry 里裸 `GT_FOOTER_ROW` = D4-2 primary sheet 的 footer 行（缺陷回退值）。
PRIMARY_FALLBACK = "31"


def _contract() -> Any:
    return parse_contract(D4.build_contract_payload(), adapter_id=D4.ADAPTER_ID)


def _binding_main() -> ExcelIdentityBinding:
    return ExcelIdentityBinding(
        table_name=D41_TABLE_NAME_MAIN, uuid_column="W", table_key=D41_TABLE_KEY_MAIN
    )


def _binding_other() -> ExcelIdentityBinding:
    return ExcelIdentityBinding(
        table_name=D41_TABLE_NAME_OTHER, uuid_column="X", table_key=D41_TABLE_KEY_OTHER
    )


def _combined_binding_manifest() -> dict[str, str]:
    """模拟 combined entry 的 runtime binding：平行清册 + per-TID footer 键 + 裸主键=31。

    裸 `GT_FOOTER_ROW`=31（D4-2 primary），per-region 键 D41MAIN=12 / D41OTHER=18。
    """
    return {
        "GT_MANAGED_TABLES": f"{D41_TABLE_NAME_MAIN},{D41_TABLE_NAME_OTHER}",
        "GT_TEMPLATE_IDS": "D41MAIN,D41OTHER",
        "GT_FOOTER_ROW": PRIMARY_FALLBACK,
        "GT_FOOTER_ROW_D41MAIN": FOOTER_MAIN,
        "GT_FOOTER_ROW_D41OTHER": FOOTER_OTHER,
    }


# ═══════════════════════════════════════════════════════════════════════════
# 判据 1：resolver 按 table_name → per-region template_id → GT_FOOTER_ROW_{TID}
# ═══════════════════════════════════════════════════════════════════════════


def test_resolver_maps_table_name_to_per_region_footer() -> None:
    rb = _combined_binding_manifest()
    assert (
        M._resolve_frozen_footer_row(rb, sheet_key="d41-managed", table_name=D41_TABLE_NAME_MAIN)
        == FOOTER_MAIN
    )
    assert (
        M._resolve_frozen_footer_row(rb, sheet_key="d41-managed", table_name=D41_TABLE_NAME_OTHER)
        == FOOTER_OTHER
    )


def test_resolver_sheet_key_only_falls_back_to_bare_primary_bug_shape() -> None:
    """不传 table_name（旧 sheet_key-only）：`GT_FOOTER_ROW_D41` 不存在 → 回退裸 31（缺陷值）。

    非空证明：正确路径（12/18）与缺陷路径（31）必须分道，否则 fix 是空转。
    """
    rb = _combined_binding_manifest()
    bug = M._resolve_frozen_footer_row(rb, sheet_key="d41-managed")
    assert bug == PRIMARY_FALLBACK, bug
    assert bug != FOOTER_MAIN and bug != FOOTER_OTHER


def test_template_id_for_table_name_helper() -> None:
    rb = _combined_binding_manifest()
    assert M._template_id_for_table_name(rb, D41_TABLE_NAME_MAIN) == "D41MAIN"
    assert M._template_id_for_table_name(rb, D41_TABLE_NAME_OTHER) == "D41OTHER"
    # 不在清册 / 缺清册 / 空 → None（调用方回退 sheet_key 路径）。
    assert M._template_id_for_table_name(rb, "GT_NOT_THERE") is None
    assert M._template_id_for_table_name({}, D41_TABLE_NAME_MAIN) is None
    assert M._template_id_for_table_name(rb, None) is None


# ═══════════════════════════════════════════════════════════════════════════
# 真实双区注入产物：两区 footer 门各自通过
# ═══════════════════════════════════════════════════════════════════════════


def _instrument_d41_dual_region() -> bytes:
    from app.services.workpaper_sync import excel_instrumentation as EI
    from app.services.workpaper_sync.phase5_d4_revenue_detail import excel_carrier_gate

    template = _REPO / "backend" / "wp_templates" / D41.TEMPLATE_RELATIVE_PATH
    if not template.is_file():
        pytest.skip(f"D4-1 权威模板缺失: {template}")
    specs = list(
        D41.instrumentation_spec_d41(
            entry_id="gt-d4-operating-revenue",
            template_relative_path=D41.TEMPLATE_RELATIVE_PATH,
        )
    )
    inst = EI.instrument_workbook_bytes_multi(
        template.read_bytes(), specs, gate=excel_carrier_gate()
    )
    return inst.instrumented_bytes


@pytest.fixture(scope="module")
def dual_region_artifact() -> dict[str, Any]:
    data = _instrument_d41_dual_region()
    contract = _contract()
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        rb = dict(read_runtime_binding_pairs(zf))
        region_main = resolve_managed_region(zf, contract=contract, binding=_binding_main())
        region_other = resolve_managed_region(zf, contract=contract, binding=_binding_other())
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        entries = {n: zf.read(n) for n in zf.namelist()}
    return {
        "entries": entries,
        "contract": contract,
        "rb": rb,
        "region_main": region_main,
        "region_other": region_other,
    }


def test_instrumentation_wrote_parallel_manifest_and_per_region_footers(
    dual_region_artifact: dict[str, Any],
) -> None:
    rb = dual_region_artifact["rb"]
    assert rb.get("GT_MANAGED_TABLES") == f"{D41_TABLE_NAME_MAIN},{D41_TABLE_NAME_OTHER}"
    assert rb.get("GT_TEMPLATE_IDS") == "D41MAIN,D41OTHER"
    assert rb.get("GT_FOOTER_ROW_D41MAIN") == FOOTER_MAIN
    assert rb.get("GT_FOOTER_ROW_D41OTHER") == FOOTER_OTHER


def test_both_regions_pass_footer_gate_even_with_bare_primary_fallback(
    dual_region_artifact: dict[str, Any],
) -> None:
    """两区 footer 门各自通过（R12↔12 / R18↔18），即使裸 `GT_FOOTER_ROW`=31（combined 场景）。"""
    art = dual_region_artifact
    rb = dict(art["rb"])
    rb["GT_FOOTER_ROW"] = PRIMARY_FALLBACK  # 模拟 combined entry 的 D4-2 primary 回退
    region_main = art["region_main"]
    region_other = art["region_other"]

    fm = M.assert_footer_anchor_stable(
        entries=art["entries"],
        sheet_part=region_main.sheet_part,
        contract=art["contract"],
        runtime_binding=rb,
        table_key=D41_TABLE_KEY_MAIN,
        table_name=D41_TABLE_NAME_MAIN,
        search_from_row=region_main.first_row,
    )
    fo = M.assert_footer_anchor_stable(
        entries=art["entries"],
        sheet_part=region_other.sheet_part,
        contract=art["contract"],
        runtime_binding=rb,
        table_key=D41_TABLE_KEY_OTHER,
        table_name=D41_TABLE_NAME_OTHER,
        search_from_row=region_other.first_row,
    )
    assert fm == 12, fm
    assert fo == 18, fo


def test_reverting_to_sheet_key_only_resolution_makes_dual_region_red(
    dual_region_artifact: dict[str, Any],
) -> None:
    """变异守卫：不传 table_name（退回 sheet_key-only 冻结解析）→ 裸 31 → drift 必红。

    证明 per-region 冻结解析是 load-bearing：撤掉它，主营区 marker R12 ≠ 冻结 31 → 抛。
    """
    art = dual_region_artifact
    rb = dict(art["rb"])
    rb["GT_FOOTER_ROW"] = PRIMARY_FALLBACK
    region_main = art["region_main"]
    with pytest.raises(M.FooterAnchorDriftError, match="已下移"):
        M.assert_footer_anchor_stable(
            entries=art["entries"],
            sheet_part=region_main.sheet_part,
            contract=art["contract"],
            runtime_binding=rb,
            table_key=D41_TABLE_KEY_MAIN,
            # 故意不传 table_name / search_from_row —— 退回缺陷路径。
        )


def test_marker_search_scoped_to_region_disambiguates_other_from_main(
    dual_region_artifact: dict[str, Any],
) -> None:
    """可见侧变异守卫：不设 search_from_row，「其他」区会误取主营 R12 的 marker → drift。

    冻结侧给对（other=18），但可见侧全局搜到主营 R12 → 12≠18 → 抛。设了 search_from_row
    （从 R14 起）才跳过 R12 命中 R18。
    """
    art = dual_region_artifact
    rb = dict(art["rb"])
    region_other = art["region_other"]
    # 不传 search_from_row：可见侧恒取第一处 小计（R12），而冻结侧 other=18 → drift。
    with pytest.raises(M.FooterAnchorDriftError, match="已下移"):
        M.assert_footer_anchor_stable(
            entries=art["entries"],
            sheet_part=region_other.sheet_part,
            contract=art["contract"],
            runtime_binding=rb,
            table_key=D41_TABLE_KEY_OTHER,
            table_name=D41_TABLE_NAME_OTHER,
            # search_from_row 缺省 0 → 命中主营 R12。
        )


def test_genuine_footer_drift_still_caught_per_region(
    dual_region_artifact: dict[str, Any],
) -> None:
    """不削弱漂移检测：把主营冻结 footer 篡改成 99（≠ 实测 R12）→ 仍抛 drift。"""
    art = dual_region_artifact
    rb = dict(art["rb"])
    rb["GT_FOOTER_ROW_D41MAIN"] = "99"
    region_main = art["region_main"]
    with pytest.raises(M.FooterAnchorDriftError, match="已下移"):
        M.assert_footer_anchor_stable(
            entries=art["entries"],
            sheet_part=region_main.sheet_part,
            contract=art["contract"],
            runtime_binding=rb,
            table_key=D41_TABLE_KEY_MAIN,
            table_name=D41_TABLE_NAME_MAIN,
            search_from_row=region_main.first_row,
        )


# ═══════════════════════════════════════════════════════════════════════════
# 判据 4：无回归 —— 多 sheet-单区（sheet_key→单 TID）冻结解析逐字不变
# ═══════════════════════════════════════════════════════════════════════════


def test_single_region_per_sheet_resolution_unchanged() -> None:
    """D4-23 形态：sheet_key `d4-23-managed` → `D423`，无平行清册 → 走 sheet_key 路径取 24。

    与 test_d4_dual_sheet_managed_tables 的既有判据同口径，锁死泛化不回归多 sheet-单区。
    """
    rb = {
        "GT_FOOTER_ROW": "31",
        "GT_FOOTER_ROW_D42": "31",
        "GT_FOOTER_ROW_D423": "24",
    }
    # 不传 table_name（多 sheet-单区无平行清册歧义）→ sheet_key 路径。
    assert M._resolve_frozen_footer_row(rb, sheet_key="d4-23-managed") == "24"
    # 裸主键回退（单 sheet / 旧 artifact）。
    assert M._resolve_frozen_footer_row({"GT_FOOTER_ROW": "26"}, sheet_key=None) == "26"


def test_table_name_not_in_manifest_falls_back_to_sheet_key() -> None:
    """table_name 传了但不在平行清册里 → 回退 sheet_key 路径（不误伤多 sheet-单区）。"""
    rb = {"GT_FOOTER_ROW": "31", "GT_FOOTER_ROW_D423": "24"}
    assert (
        M._resolve_frozen_footer_row(
            rb, sheet_key="d4-23-managed", table_name="GT_SOMETHING_ELSE"
        )
        == "24"
    )
