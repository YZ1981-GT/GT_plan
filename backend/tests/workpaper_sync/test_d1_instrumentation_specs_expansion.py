# -*- coding: utf-8 -*-
"""D1 多受管 sheet 扩容判据（Task 23）。

spec: d1-sync-row-table-engine-and-d1-coverage · Requirements 5.2 / 5.3 / 3.3

═══ 判据面 ═══

1. **开关全 False ⇒ 与现状等价**（复数 `instrumentation_specs()` == 单数一张，零回归）。
2. **逐张打开 ⇒ 受管区按预期增长**（受管区计数：1 → 2(D1-2) → 4(D1-4 前两区) → 5(+静态第三区)）。
3. **翻译正确性**：每个 `ExcelInstrumentationSpec` 的几何 == 对应 `RowTableSheetSpec`。
4. **`ExcelInstrumentationSpec` 的硬约束被遵守**：footer_row > last_data_row、
   uuid_col 在 managed_last_col 右侧、table_name 合法。
5. **D1-4 第三区表达不了动态 spec**（footer 之下 ⇒ 构造 ExcelInstrumentationSpec 必抛）——
   这是它必须走 static_region 的**硬证据**，不是设计偏好。
6. **静态区寄生在首个动态 spec 的 `static_sheets` 上**（与 transposed_sheets 同构）。
7. **两方向 store item 同源**：`all_store_item_ids()` 随开关增长且无重复（需求 3.3）。
8. **对齐计数守卫**：specs 与契约 sheets 不对齐 ⇒ fail-closed 且精确报差集（D4-35 事故形态）。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.workpaper_sync import phase5_d1_02_category as D102
from app.services.workpaper_sync import phase5_d1_04_bad_debt as D104
from app.services.workpaper_sync import phase5_d1_expansion as P
from app.services.workpaper_sync import phase5_d1_notes_receivable as ENTRY
from app.services.workpaper_sync.excel_instrumentation import (
    ExcelInstrumentationSpec,
    InstrumentationError,
)


#: 静态第三区（D1-4 票据种类小计）当前是否进受管面。
#:
#: 🔴 T7 裁决 A（2026-09-28）把它撤回了 —— 不是删代码，而是把
#: `_INCLUDE_D104_NOTETYPE_STATIC` 翻 False，整条静态通路同源空转。
#: 本文件里**跟静态区有关的期望值**一律从这个常量派生，不写死，
#: 这样开关翻回 True 时判据自动跟着复活，不需要再改一遍。
#:
#: 开关状态本身的权威断言（含失效条目反向检查）在
#: `test_d104_static_region_excluded.py` —— 本文件不重复那个判断，
#: 否则就是两处各写一份「开关现在是什么」，翻开关要改两地。
_STATIC_ON = P._INCLUDE_D104_NOTETYPE_STATIC

#: 全量 store item 数：动态区 17 个 + 静态区 1 个（仅当静态区开启）。
_EXPECTED_STORE_ITEMS = 18 if _STATIC_ON else 17


def test_switches_off_equals_current_state() -> None:
    """两个动态灰度开关已永久 ON；静态第三区按 T7 裁决 A 处于撤回态。"""
    assert P._INCLUDE_D102_CATEGORY is True
    assert P._INCLUDE_D104_BAD_DEBT is True

    specs = P.instrumentation_specs()
    # 🔴 静态区寄生在首个动态 spec 的 `static_sheets` 上，**不产生独立 spec** ⇒
    #    spec 数与静态开关无关，恒 18（D1-3 + 11 扩容 sheet 上的 18 张行表）。
    #    这条与 `_EXPECTED_STORE_ITEMS` 的可变性形成对照：一个不随开关变，一个随。
    assert len(specs) == 18
    items = P.all_store_item_ids()
    assert len(items) == len(set(items)), f"store item 重复：{items}"
    assert len(items) == _EXPECTED_STORE_ITEMS, items


def test_enabling_d102_adds_one_managed_region(monkeypatch: pytest.MonkeyPatch) -> None:
    """D1-2 已永久开启，验证它贡献了正确的 sheet_key。"""
    specs = P.instrumentation_specs()
    keys = [s.resolved_sheet_key for s in specs]
    assert D102.SHEET_KEY_D102 in keys
    assert ENTRY.STORE_ITEM_ID in P.all_store_item_ids()
    assert D102.STORE_ITEM_ID_D102 in P.all_store_item_ids()


def test_enabling_d104_adds_two_dynamic_regions(monkeypatch: pytest.MonkeyPatch) -> None:
    """D1-4 已永久开启，两动态区 + 一静态区均存在。"""
    specs = P.instrumentation_specs()
    keys = [s.resolved_sheet_key for s in specs]
    assert keys.count(D104.SHEET_KEY_D104) == 2  # individual + portfolio
    items = set(P.all_store_item_ids())
    assert {"D1-bd-individual-rows", "D1-bd-portfolio-rows"} <= items
    # 🔴 2026-09-28：本断言原写 `D1-notetype-rows`，把声明层的键名错误钉成了断言
    #    （前端真源 `d1AdjudicationModel.D1_BD_NOTETYPE_KEY` / `prefill_anchor_map` /
    #     `d_cycle_extraction.presets` 三处都是 `D1-bd-notetype-rows`，真库亦然）。
    #    三键统一 `D1-bd-` 前缀，判据不得再给错键背书。
    #
    # 🔴 同日 T7 裁决 A 撤回静态第三区 ⇒ 这条改成**双向**断言：开着必须在、
    #    关着必须不在。只断言「开着必须在」的话，撤回态下它是红的；
    #    只断言「关着必须不在」的话，开关翻回 True 时它又变成假绿。
    if _STATIC_ON:
        assert "D1-bd-notetype-rows" in items
    else:
        assert "D1-bd-notetype-rows" not in items, (
            "静态第三区已按 T7 裁决 A 撤回，但 store item 清单里还有它 —— "
            "说明存在绕过 `_INCLUDE_D104_NOTETYPE_STATIC` 的第二个装配点"
        )


def test_enabling_static_third_region_parasites_on_primary(monkeypatch: pytest.MonkeyPatch) -> None:
    """静态第三区寄生在**首个**动态 spec 的 static_sheets 上（与 transposed_sheets 同构）。"""
    monkeypatch.setattr(P, "_INCLUDE_D104_BAD_DEBT", True)
    monkeypatch.setattr(P, "_INCLUDE_D104_NOTETYPE_STATIC", True)
    specs = P.instrumentation_specs()
    primary = specs[0]
    assert primary.static_sheets, "静态区未寄生到首个动态 spec"
    static = primary.static_sheets[0]
    assert static["region_kind"] == "static"
    assert static["defined_name"] == D104.SPEC_D104_NOTETYPE.defined_name
    assert (static["first_data_row"], static["last_data_row"]) == (23, 24)
    # store item 清单含第三区（键名见上方 2026-09-28 勘误注释）
    assert "D1-bd-notetype-rows" in P.all_store_item_ids()


def test_third_region_cannot_be_a_dynamic_instrumentation_spec() -> None:
    """🔴 硬证据：D1-4 第三区在 footer 之下 ⇒ 构造动态 ExcelInstrumentationSpec 必抛。

    `ExcelInstrumentationSpec.__post_init__` 强制 `footer_row > last_data_row`
    （「footer 落在动态行内会被插删行推走」）。第三区 last_data_row=24 > footer_row=22
    ⇒ 它**表达不了**动态 spec。这不是设计偏好，是引擎的硬约束 —— 故必须走 static_region。
    """
    with pytest.raises(InstrumentationError, match="footer_row"):
        ExcelInstrumentationSpec(
            entry_id=ENTRY.ENTRY_ID,
            template_id="D14NOTETYPE",
            template_relative_path=ENTRY.TEMPLATE_RELATIVE_PATH,
            managed_sheet=D104.MANAGED_SHEET_D104,
            first_data_row=23,
            last_data_row=24,
            footer_row=D104.FOOTER_ROW_D104,  # 22 < 24
            managed_last_col="N",
            uuid_col="Q",
            table_name="GT_D14NOTETYPE_ROWS",
        )


@pytest.mark.parametrize(
    "row_spec",
    [D102.SPEC_D102, D104.SPEC_D104_INDIVIDUAL, D104.SPEC_D104_PORTFOLIO],
    ids=["d1-2", "d1-4-individual", "d1-4-portfolio"],
)
def test_translation_preserves_geometry(row_spec) -> None:
    """翻译正确性：ExcelInstrumentationSpec 的几何 == RowTableSheetSpec 的几何。"""
    instr = P._instrumentation_of(row_spec)
    assert instr.managed_sheet == row_spec.managed_sheet
    assert instr.first_data_row == row_spec.first_data_row
    assert instr.last_data_row == row_spec.last_data_row
    assert instr.footer_row == row_spec.footer_row
    assert instr.uuid_col == row_spec.uuid_col
    assert instr.table_name == row_spec.table_name
    assert instr.resolved_sheet_key == row_spec.sheet_key
    # uuid_col 必须在受管业务列右侧（__post_init__ 已校验，这里显式断言语义）
    from app.services.workpaper_sync.sheet_geometry import col_index

    assert col_index(instr.uuid_col) > col_index(instr.managed_last_col)


def test_store_item_ids_have_no_duplicates(monkeypatch: pytest.MonkeyPatch) -> None:
    items = P.all_store_item_ids()
    assert len(items) == len(set(items)), f"store item 重复：{items}"
    assert len(items) == _EXPECTED_STORE_ITEMS, items


def test_alignment_guard_reports_exact_diff(monkeypatch: pytest.MonkeyPatch) -> None:
    """对齐计数守卫：specs 与契约 sheets 对齐（全量开启后契约已重生成）。"""
    from app.services.workpaper_sync.contracts import parse_contract

    contract = parse_contract(ENTRY.build_contract_payload(), adapter_id=ENTRY.ADAPTER_ID)
    # 全量开启应对齐（契约已含 12 sheets = 全部启用 sheet）
    P.assert_specs_align_with_contract_sheets(contract)
