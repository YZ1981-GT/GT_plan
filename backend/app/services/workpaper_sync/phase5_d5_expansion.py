# -*- coding: utf-8 -*-
"""D5 多受管 sheet 扩容 —— `phase5_d5_receivables_financing` 的伴生模块。

spec: d567-sync-coverage-via-row-table-engine · Task 6

D5 是三循环中最小的（只新增 D5-4 公允价值表 + 审定表D5），与 D3 expansion 同构但更简。
"""
from __future__ import annotations

from typing import Any, Final, TYPE_CHECKING

from app.services.workpaper_sync.contracts import SyncContract
from app.services.workpaper_sync.excel_instrumentation import ExcelInstrumentationSpec
from app.services.workpaper_sync.phase5_d5_receivables_financing import (
    ENTRY_ID,
    STORE_ITEM_ID,
    TEMPLATE_RELATIVE_PATH,
    EntrySelectionError,
)

if TYPE_CHECKING:
    from app.services.workpaper_sync.phase5_adjudication_sheet import (
        AdjudicationSheetSpec,
    )

__all__ = [
    "managed_row_table_specs",
    "instrumentation_specs",
    "all_store_item_ids",
    "all_managed_sheet_names",
    "assert_specs_align_with_contract_sheets",
]

# ─── 灰度开关 ───────────────────────────────────────────────────────────────

#: D5-4 公允价值测算表。aging_layout=None，引擎「无分组」路径基准样本。
_INCLUDE_D504_FAIR_VALUE: Final[bool] = True
_INCLUDE_D501_ADJUDICATION: Final[bool] = True

# ─── 行表 spec 聚合 ────────────────────────────────────────────────────────


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
    """扩容面行表 spec（不含 D5-2 自身）。"""
    specs: list[Any] = []
    if _INCLUDE_D504_FAIR_VALUE:
        from app.services.workpaper_sync.phase5_d5_04_fair_value import SPEC_D504
        specs.append(SPEC_D504)
    return tuple(specs)


def instrumentation_specs() -> tuple[ExcelInstrumentationSpec, ...]:
    """扩容面 instrumentation（不含 D5-2 自身单数）。"""
    return tuple(_instrumentation_of(s) for s in managed_row_table_specs())


def static_sheet_declarations() -> tuple[dict[str, Any], ...]:
    """扩容面的静态受管区寄生声明（挂到 D5-2 主 spec 的 `static_sheets`）。

    🔴 审定表 D5 是**静态受管区**（`row_mode=fixed_rows`，per-cell 锚点），不是行表 ——
       故它不进 `managed_row_table_specs()`，而以 `static_sheets` 寄生在主动态 spec 上
       （D2-1/D4-13 已验证范式）。

    🔴 这是审定表进入 instrumentation 的**唯一**通道。此前它只被
       `assert_specs_align_with_contract_sheets` 手工加进校验集合，从未进 payload ⇒
       契约声明 `d51-managed` 而 instrumentation 不注入它，已发布 artifact 的 observed
       结构缺这张 sheet，attach 期 `assert_no_structure_drift` 报
       `sync_contract_structure_drift` 打挂整个 entry。
    """
    if not _INCLUDE_D501_ADJUDICATION:
        return ()
    from app.services.workpaper_sync.phase5_adjudication_sheet import (
        static_sheet_payload_for_adjudication,
    )
    from app.services.workpaper_sync.phase5_d5_01_adjudication import SPEC_D501

    return (static_sheet_payload_for_adjudication(SPEC_D501),)


def all_store_item_ids() -> tuple[str, ...]:
    """全部 store item（D5-2 自身 + 扩容面）。"""
    items: list[str] = [STORE_ITEM_ID]
    for spec in managed_row_table_specs():
        if spec.store_item_id and spec.store_item_id not in items:
            items.append(spec.store_item_id)
    return tuple(items)


def all_managed_sheet_names() -> tuple[str, ...]:
    """全部受管 sheet 名（D5-2 + 行表扩容 + 审定表）。"""
    from app.services.workpaper_sync.phase5_d5_receivables_financing import MANAGED_SHEET
    names: list[str] = [MANAGED_SHEET]
    seen: set[str] = {MANAGED_SHEET}
    for spec in managed_row_table_specs():
        if spec.managed_sheet not in seen:
            names.append(spec.managed_sheet)
            seen.add(spec.managed_sheet)
    if _INCLUDE_D501_ADJUDICATION:
        from app.services.workpaper_sync.phase5_d5_01_adjudication import MANAGED_SHEET_D501
        if MANAGED_SHEET_D501 not in seen:
            names.append(MANAGED_SHEET_D501)
            seen.add(MANAGED_SHEET_D501)
    return tuple(names)


def assert_specs_align_with_contract_sheets(contract: SyncContract) -> None:
    """对齐守卫：specs sheet_key 集合 == 契约 sheets 集合。"""
    from app.services.workpaper_sync.phase5_d5_receivables_financing import (
        instrumentation_spec as _d52_spec,
    )

    spec_keys = {s.resolved_sheet_key for s in (_d52_spec(), *instrumentation_specs())}
    if _INCLUDE_D501_ADJUDICATION:
        from app.services.workpaper_sync.phase5_d5_01_adjudication import SPEC_D501
        spec_keys.add(SPEC_D501.sheet_key)
    contract_keys = {s.sheet_key for s in contract.sheets}

    contract_extra = sorted(contract_keys - spec_keys)
    spec_extra = sorted(spec_keys - contract_keys)
    if contract_extra or spec_extra:
        from app.services.workpaper_sync.projection_first_publication import (
            ProviderCapabilityError,
        )
        raise ProviderCapabilityError(
            f"D5 provider 的受管 sheet 集合与契约不对齐 —— "
            f"契约有而 spec 缺: {contract_extra}；spec 有而契约缺: {spec_extra}"
        )
