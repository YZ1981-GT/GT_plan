# -*- coding: utf-8 -*-
"""D7 多受管 sheet 扩容 —— `phase5_d7_contract_liabilities` 的伴生模块。

spec: d567-sync-coverage-via-row-table-engine · Task 12
D7 aging_layout=nested（与 D3 同路径），是引擎 nested 路径的对照样本。
"""
from __future__ import annotations
from typing import Any, Final
from app.services.workpaper_sync.contracts import SyncContract
from app.services.workpaper_sync.excel_instrumentation import ExcelInstrumentationSpec
from app.services.workpaper_sync.phase5_d7_contract_liabilities import (
    ENTRY_ID, STORE_ITEM_ID, TEMPLATE_RELATIVE_PATH, EntrySelectionError,
)

__all__ = [
    "managed_row_table_specs", "instrumentation_specs",
    "all_store_item_ids", "all_managed_sheet_names",
    "assert_specs_align_with_contract_sheets",
]

# ─── 灰度开关 ───────────────────────────────────────────────────────────────

_INCLUDE_D705_LONG_TERM: Final[bool] = True
_INCLUDE_D706_RELATED_PARTY: Final[bool] = True
_INCLUDE_D704_ANALYSIS: Final[bool] = True
_INCLUDE_D707_INSPECTION: Final[bool] = True
_INCLUDE_D701_ADJUDICATION: Final[bool] = True

# ─── 聚合函数 ──────────────────────────────────────────────────────────────


def _managed_last_col_of(spec: Any) -> str:
    from app.services.workpaper_sync.sheet_geometry import col_index
    if not spec.field_specs:
        raise EntrySelectionError(f"{spec.managed_sheet} 未声明任何受管字段")
    return max((row[1] for row in spec.field_specs), key=col_index)


def _instrumentation_of(spec: Any) -> ExcelInstrumentationSpec:
    return ExcelInstrumentationSpec(
        entry_id=ENTRY_ID,
        template_id=spec.template_id,
        template_relative_path=TEMPLATE_RELATIVE_PATH,
        managed_sheet=spec.managed_sheet,
        first_data_row=spec.first_data_row,
        last_data_row=spec.last_data_row,
        footer_row=spec.footer_row,
        managed_last_col=_managed_last_col_of(spec),
        uuid_col=spec.uuid_col,
        table_name=spec.table_name,
        sheet_key=spec.sheet_key,
    )


def managed_row_table_specs() -> tuple[Any, ...]:
    specs: list[Any] = []
    if _INCLUDE_D705_LONG_TERM:
        from app.services.workpaper_sync.phase5_d7_05_long_term import SPEC_D705
        specs.append(SPEC_D705)
    if _INCLUDE_D706_RELATED_PARTY:
        from app.services.workpaper_sync.phase5_d7_06_related_party import SPEC_D706
        specs.append(SPEC_D706)
    if _INCLUDE_D704_ANALYSIS:
        from app.services.workpaper_sync.phase5_d7_04_analysis import SPEC_D704_DEBIT, SPEC_D704_CREDIT
        specs.extend((SPEC_D704_DEBIT, SPEC_D704_CREDIT))
    if _INCLUDE_D707_INSPECTION:
        from app.services.workpaper_sync.phase5_d7_07_inspection import SPEC_D707_PERIOD, SPEC_D707_POST
        specs.extend((SPEC_D707_PERIOD, SPEC_D707_POST))
    return tuple(specs)


def instrumentation_specs() -> tuple[ExcelInstrumentationSpec, ...]:
    return tuple(_instrumentation_of(s) for s in managed_row_table_specs())


def static_sheet_declarations() -> tuple[dict[str, Any], ...]:
    """扩容面的静态受管区寄生声明（挂到 D7-2 主 spec 的 `static_sheets`）。

    🔴 审定表 D7-1 是**静态受管区**（两区 nature/aging，per-cell 锚点），不是行表 ——
       故它不进 `managed_row_table_specs()`，而以 `static_sheets` 寄生在主动态 spec 上
       （D2-1/D4-13 已验证范式）。

    🔴 这是审定表进入 instrumentation 的**唯一**通道。此前它只被
       `assert_specs_align_with_contract_sheets` 手工加进校验集合，从未进 payload ⇒
       契约声明 `d71-managed` 而 instrumentation 不注入它，attach 期必报结构漂移。
    """
    if not _INCLUDE_D701_ADJUDICATION:
        return ()
    from app.services.workpaper_sync.phase5_adjudication_sheet import (
        static_sheet_payload_for_adjudication,
    )
    from app.services.workpaper_sync.phase5_d7_01_adjudication import SPEC_D701

    return (static_sheet_payload_for_adjudication(SPEC_D701),)


def all_store_item_ids() -> tuple[str, ...]:
    items: list[str] = [STORE_ITEM_ID]
    for spec in managed_row_table_specs():
        if spec.store_item_id and spec.store_item_id not in items:
            items.append(spec.store_item_id)
    return tuple(items)


def all_managed_sheet_names() -> tuple[str, ...]:
    from app.services.workpaper_sync.phase5_d7_contract_liabilities import MANAGED_SHEET
    names: list[str] = [MANAGED_SHEET]
    seen: set[str] = {MANAGED_SHEET}
    for spec in managed_row_table_specs():
        if spec.managed_sheet not in seen:
            names.append(spec.managed_sheet)
            seen.add(spec.managed_sheet)
    if _INCLUDE_D701_ADJUDICATION:
        from app.services.workpaper_sync.phase5_d7_01_adjudication import MANAGED_SHEET_D701
        if MANAGED_SHEET_D701 not in seen:
            names.append(MANAGED_SHEET_D701)
            seen.add(MANAGED_SHEET_D701)
    return tuple(names)


def assert_specs_align_with_contract_sheets(contract: SyncContract) -> None:
    from app.services.workpaper_sync.phase5_d7_contract_liabilities import (
        instrumentation_spec as _d72_spec,
    )
    spec_keys = {s.resolved_sheet_key for s in (_d72_spec(), *instrumentation_specs())}
    if _INCLUDE_D701_ADJUDICATION:
        from app.services.workpaper_sync.phase5_d7_01_adjudication import SPEC_D701
        spec_keys.add(SPEC_D701.sheet_key)
    contract_keys = {s.sheet_key for s in contract.sheets}
    contract_extra = sorted(contract_keys - spec_keys)
    spec_extra = sorted(spec_keys - contract_keys)
    if contract_extra or spec_extra:
        from app.services.workpaper_sync.projection_first_publication import (
            ProviderCapabilityError,
        )
        raise ProviderCapabilityError(
            f"D7 provider 受管 sheet 不对齐 —— "
            f"契约有而 spec 缺: {contract_extra}；spec 有而契约缺: {spec_extra}"
        )
