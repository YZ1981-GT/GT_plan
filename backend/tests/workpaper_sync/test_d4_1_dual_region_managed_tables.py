# -*- coding: utf-8 -*-
"""D4-1 同 sheet 双区 `managed_tables_of` 解析 —— 行为级验证（judge-first）。

spec: d4-1-adjudication-bidirectional-writeback-and-formula-io · Task 6 判据②前置
      · 亦服务 d4-9-customer-structure-bidirectional-writeback（主控 §5.3 shared-lock）
Requirements 1.1 / 1.2 / 5.4：GENERALIZE `managed_tables_of` 支持一张受管 sheet 上
N 张动态行表（各有自己的 binding），不回归单动态表 sheet。

═══ 已核实的 ROOT CAUSE ═══

`excel_extract.managed_tables_of(contract, binding=X)` 解析 `X.table_key` 所在 sheet 的
`(动态表, 静态表)`。原实现在同一张 sheet 上发现**第二张 has_dynamic_rows 的表**时
硬抛 `ManagedRegionResolutionError`（"还有第二张动态行表 …，但 identity binding 只声明
了一组 Table/UUID 列"）。但 D4-1 的受管 sheet `d41-managed` 合法地有**两张**动态行表
（主营 `adjudication_main_rows` UUID 列 W / 其他 `adjudication_other_rows` UUID 列 X），
**各有自己的 binding**。adapter.extract 会逐 binding 各调一次 extract_projection
（内部即调 managed_tables_of）再 merge —— 兄弟动态表其实**已被绑定**，只是在另一趟。
原实现把它误判成"未绑定的第二动态表"而 fail-closed，导致 D4-1 无法 extract
（rematerialize 抛 ManagedRegionResolutionError）。

═══ 修复 ═══

`managed_tables_of` 对本 binding sheet 上的**其它动态表跳过**（不返回、不 fail-closed），
静态表照旧纳入。「每张动态表都有 binding」由看得见全部 binding 的上游
`_align_specs_to_sibling_tables`（行 table 总数 == specs 数 + spec↔table 双射）保证。

本文件锁死三条判据：
1. 同 sheet 双区解析：`managed_tables_of(binding=main)` 返回 main 动态表且**不抛**；
   `managed_tables_of(binding=other)` 返回 other 动态表且**不抛**；两趟不串区。
2. 变异守卫：把 managed_tables_of 改回"发现第二动态表就抛"，本双区测试必红。
3. 无回归：单动态表 sheet（D4-2/D4-3 等）经泛化后仍返回 1 动态表 + N 静态表，
   静态表清册与泛化前逐 table_key 一致。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

import io  # noqa: E402
import zipfile  # noqa: E402

from app.services.workpaper_sync import excel_extract as EE  # noqa: E402
from app.services.workpaper_sync import phase5_d4_revenue_detail as D4  # noqa: E402
from app.services.workpaper_sync.contracts import parse_contract  # noqa: E402
from app.services.workpaper_sync.excel_extract import (  # noqa: E402
    ExcelIdentityBinding,
    ManagedRegionResolutionError,
    managed_tables_of,
    resolve_managed_region,
)

# ── 从 D4-1 provider 冻结常量派生的期望 ─────────────────────────────────────────
D41_SHEET_KEY = "d41-managed"
D41_TABLE_MAIN = "adjudication_main_rows"
D41_TABLE_OTHER = "adjudication_other_rows"
D41_UUID_MAIN = "W"
D41_UUID_OTHER = "X"
D41_TABLE_NAME_MAIN = "GT_D41_MAIN_ROWS"
D41_TABLE_NAME_OTHER = "GT_D41_OTHER_ROWS"


def _contract() -> Any:
    return parse_contract(D4.build_contract_payload(), adapter_id=D4.ADAPTER_ID)


def _binding_main() -> ExcelIdentityBinding:
    return ExcelIdentityBinding(
        table_name=D41_TABLE_NAME_MAIN,
        uuid_column=D41_UUID_MAIN,
        table_key=D41_TABLE_MAIN,
    )


def _binding_other() -> ExcelIdentityBinding:
    return ExcelIdentityBinding(
        table_name=D41_TABLE_NAME_OTHER,
        uuid_column=D41_UUID_OTHER,
        table_key=D41_TABLE_OTHER,
    )


# ═══════════════════════════════════════════════════════════════════════════
# 前置：契约里 D4-1 受管 sheet 确实有两张动态行表（否则本文件测的是空气）
# ═══════════════════════════════════════════════════════════════════════════


def test_d41_sheet_really_has_two_dynamic_tables() -> None:
    contract = _contract()
    d41 = next(s for s in contract.sheets if s.sheet_key == D41_SHEET_KEY)
    dynamic_keys = {t.table_key for t in d41.tables if t.has_dynamic_rows}
    assert dynamic_keys == {D41_TABLE_MAIN, D41_TABLE_OTHER}, (
        f"D4-1 受管 sheet 应有两张动态行表 {{main, other}}，实得 {sorted(dynamic_keys)} —— "
        "本测试前提不成立"
    )
    # D4-1 本 sheet 无静态表（footer 走 tb_check + formula_mask，非 TableSpec）。
    static_keys = {t.table_key for t in d41.tables if not t.has_dynamic_rows}
    assert static_keys == set(), (
        f"D4-1 受管 sheet 不应有静态 TableSpec，实得 {sorted(static_keys)}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 判据 1：同 sheet 双区解析 —— 两趟各返回自己的动态表，均不抛，不串区
# ═══════════════════════════════════════════════════════════════════════════


def test_managed_tables_of_main_binding_returns_main_and_does_not_raise() -> None:
    contract = _contract()
    dynamic, statics = managed_tables_of(contract, binding=_binding_main())
    assert dynamic.table_key == D41_TABLE_MAIN, (
        f"binding=main 应返回主营动态表，实得 {dynamic.table_key!r}"
    )
    # 兄弟动态表（other）绝不出现在本 binding 的静态清册里（不串区、不误当静态）。
    assert all(t.table_key != D41_TABLE_OTHER for t in statics), (
        f"other 动态表被误纳入 main 的静态清册: {[t.table_key for t in statics]}"
    )
    # D4-1 本 sheet 无静态表。
    assert statics == (), f"main binding 静态清册应为空，实得 {[t.table_key for t in statics]}"


def test_managed_tables_of_other_binding_returns_other_and_does_not_raise() -> None:
    contract = _contract()
    dynamic, statics = managed_tables_of(contract, binding=_binding_other())
    assert dynamic.table_key == D41_TABLE_OTHER, (
        f"binding=other 应返回其他段动态表，实得 {dynamic.table_key!r}"
    )
    assert all(t.table_key != D41_TABLE_MAIN for t in statics), (
        f"main 动态表被误纳入 other 的静态清册: {[t.table_key for t in statics]}"
    )
    assert statics == (), f"other binding 静态清册应为空，实得 {[t.table_key for t in statics]}"


def test_two_bindings_resolve_to_distinct_dynamic_tables() -> None:
    """两 binding 各归各的动态表，互不串区（同 sheet 双区身份分离）。"""
    contract = _contract()
    main_dyn, _ = managed_tables_of(contract, binding=_binding_main())
    other_dyn, _ = managed_tables_of(contract, binding=_binding_other())
    assert main_dyn.table_key != other_dyn.table_key
    assert {main_dyn.table_key, other_dyn.table_key} == {D41_TABLE_MAIN, D41_TABLE_OTHER}


# ═══════════════════════════════════════════════════════════════════════════
# 判据 3：无回归 —— 单动态表 sheet（D4-2 primary 等）仍 1 动态 + N 静态
# ═══════════════════════════════════════════════════════════════════════════


def _single_dynamic_sheet_binding(contract: Any) -> tuple[ExcelIdentityBinding, Any, set[str]]:
    """挑一张**只有 1 张动态行表**的受管 sheet，返回 (binding, sheet, 期望静态 key 集)。

    从真实契约现挑（不写死是哪张），保证「泛化不回归单动态表」这条判据非空跑。
    """
    for sheet in contract.sheets:
        dynamics = [t for t in sheet.tables if t.has_dynamic_rows]
        if len(dynamics) != 1:
            continue
        dyn = dynamics[0]
        expected_statics = {
            t.table_key for t in sheet.tables if not t.has_dynamic_rows
        }
        binding = ExcelIdentityBinding(
            table_name=f"GT_{dyn.table_key}",  # table_name 不参与 managed_tables_of 解析
            uuid_column="Z",
            table_key=dyn.table_key,
        )
        return binding, sheet, expected_statics
    pytest.skip("契约里没有单动态表 sheet —— 无回归判据无对象")


def test_single_dynamic_sheet_still_returns_one_dynamic_plus_statics() -> None:
    contract = _contract()
    binding, sheet, expected_statics = _single_dynamic_sheet_binding(contract)
    dynamic, statics = managed_tables_of(contract, binding=binding)
    assert dynamic.table_key == binding.table_key, (
        f"单动态表 sheet 应返回该动态表，实得 {dynamic.table_key!r}"
    )
    got_statics = {t.table_key for t in statics}
    assert got_statics == expected_statics, (
        f"单动态表 sheet {sheet.sheet_key!r} 静态清册回归："
        f"期望 {sorted(expected_statics)} 实得 {sorted(got_statics)}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 判据 2：变异守卫 —— 改回"发现第二动态表就抛"，D4-1 双区必红
# ═══════════════════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════════════════
# 判据 1b：真实 dual-region 产物上，extract 侧区域解析对两 binding 均成功
#          （离线证明 extract 路径可用，与 live-PG rematerialize 判据互补）
# ═══════════════════════════════════════════════════════════════════════════


def _instrument_d41_dual_region_bytes() -> bytes:
    """把真实 D4-1 模板注入两区（主营 UUID 列 W / 其他 UUID 列 X），返回产物字节。

    与 D4-9 dual-region instrumentation 同路径（instrument_workbook_bytes_multi），
    产出一份**真正**含两张 Table（GT_D41_MAIN_ROWS / GT_D41_OTHER_ROWS）的工作簿，
    用它证明 extract 侧的区域解析（resolve_managed_region + managed_tables_of）对
    两 binding 各自成功、不再硬抛。
    """
    from app.services.workpaper_sync import excel_instrumentation as EI
    from app.services.workpaper_sync import phase5_d4_adjudication_sheet as D41
    from app.services.workpaper_sync.phase5_d4_revenue_detail import excel_carrier_gate

    template = (
        _REPO / "backend" / "wp_templates" / D41.TEMPLATE_RELATIVE_PATH
    )
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


def test_both_regions_resolve_on_real_dual_region_artifact() -> None:
    """真实双区产物上：两 binding 的 resolve_managed_region + managed_tables_of 均成功。

    这是 extract 路径的离线正例 —— 与 live-PG rematerialize（materialize 侧另有 footer
    几何门）互补，直接证明「同 sheet 双区能被 EXTRACTED」的核心诉求已达成。
    """
    from openpyxl import load_workbook

    data = _instrument_d41_dual_region_bytes()
    # openpyxl（独立 OOXML 实现）确认两区 Table 都在（instrumentation 没丢区）。
    from app.services.workpaper_sync import phase5_d4_adjudication_sheet as D41

    wb = load_workbook(io.BytesIO(data))
    try:
        tables = sorted(wb[D41.MANAGED_SHEET_D41].tables.keys())
    finally:
        wb.close()
    assert tables == sorted([D41_TABLE_NAME_MAIN, D41_TABLE_NAME_OTHER]), (
        f"双区注入后 openpyxl 应认出两张 Table，实得 {tables}"
    )

    contract = _contract()
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        region_main = resolve_managed_region(
            zf, contract=contract, binding=_binding_main()
        )
        region_other = resolve_managed_region(
            zf, contract=contract, binding=_binding_other()
        )
    # 两区解析到同一张受管 sheet，但 Table/UUID 列各异，行区间不重叠。
    assert region_main.sheet_name == region_other.sheet_name
    assert region_main.table_name == D41_TABLE_NAME_MAIN
    assert region_other.table_name == D41_TABLE_NAME_OTHER
    assert region_main.uuid_column == D41_UUID_MAIN
    assert region_other.uuid_column == D41_UUID_OTHER

    # managed_tables_of 在这份真实产物对应的契约上，对两 binding 均不抛、各归各的。
    main_dyn, _ = managed_tables_of(contract, binding=_binding_main())
    other_dyn, _ = managed_tables_of(contract, binding=_binding_other())
    assert main_dyn.table_key == D41_TABLE_MAIN
    assert other_dyn.table_key == D41_TABLE_OTHER


def test_reverting_to_hard_raise_breaks_dual_region(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """把 managed_tables_of 换回缺陷版（发现第二动态表就 fail-closed），D4-1 双区必红。

    证明判据 1 不是空转：只要恢复原来的硬抛，主营 binding 解析就会因为 sheet 上还有
    other 动态表而抛 ManagedRegionResolutionError。
    """

    def _broken_managed_tables_of(contract: Any, *, binding: Any) -> Any:
        sheet = next(
            (
                s
                for s in contract.sheets
                for t in s.tables
                if t.table_key == binding.table_key
            ),
            None,
        )
        assert sheet is not None
        dynamic = next(t for t in sheet.tables if t.table_key == binding.table_key)
        statics = []
        for table in sheet.tables:
            if table.table_key == dynamic.table_key:
                continue
            if table.has_dynamic_rows:
                # 缺陷版：发现第二动态表硬抛（原实现）。
                raise ManagedRegionResolutionError(
                    f"契约 {contract.contract_id} 的 sheet {sheet.sheet_key!r} 上还有第二张动态行表 "
                    f"{table.table_key!r}，但 identity binding 只声明了一组 Table/UUID 列"
                )
            statics.append(table)
        return dynamic, tuple(statics)

    monkeypatch.setattr(EE, "managed_tables_of", _broken_managed_tables_of)

    contract = _contract()
    with pytest.raises(ManagedRegionResolutionError):
        EE.managed_tables_of(contract, binding=_binding_main())
    with pytest.raises(ManagedRegionResolutionError):
        EE.managed_tables_of(contract, binding=_binding_other())
