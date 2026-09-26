# -*- coding: utf-8 -*-
"""D1 多受管 sheet 扩容 —— `phase5_d1_notes_receivable` 的伴生模块。

spec: d1-sync-row-table-engine-and-d1-coverage · Task 23 · Requirements 3.3 / 5.2 / 5.3

═══ 为什么抽成伴生模块而不是追加进 entry 模块 ═══

entry 模块（`phase5_d1_notes_receivable`）已是 1035 行，仓库的文件行数门禁
（`backend/scripts/file_size_whitelist.txt`）对它的基线是 1040 行，且门禁的措辞是
「**打磨应让文件变小不变大**」。扩容代码追加进去会顶穿 +5% 阈值。

伴生模块的边界：entry 模块持有**冻结身份**（ENTRY_ID / ADAPTER_ID / 模板哨兵 / 契约装配 /
发布编排）；本模块持有**扩容面**（灰度开关 / 受管 sheet 清单 / instrumentation 复数 /
store item 单一口径 / 对齐守卫）。两者都不含投影合并算法（那在框架层
`phase5_row_table_sheet`）。

🔴 灰度开关逐张接入，不做大爆炸（照 D4 实测的 18 个 `_INCLUDE_*: Final[bool]` 模式）。
   每张新 sheet = 一个 `phase5_d1_XX_*.py` 声明 + 一个开关 + 一条判据，可独立开关、
   独立验证、独立回滚。

   事故背书：D4-35 曾「由并发会话加入契约 sheets（8 张）但漏了 instrumentation spec」，
   导致 specs(7) 与 sheets(8) 不对齐、**整个 entry attach fail-closed**。开关 + 对齐计数
   守卫能让这类不对齐在接入时就红，而不是上线后整册 500。
"""
from __future__ import annotations

from typing import Any, Final, Mapping

from app.services.workpaper_sync.contracts import SyncContract
from app.services.workpaper_sync.excel_instrumentation import ExcelInstrumentationSpec
from app.services.workpaper_sync.phase5_d1_notes_receivable import (
    ADAPTER_ID,
    ENTRY_ID,
    STORE_ITEM_ID,
    TEMPLATE_RELATIVE_PATH,
    EntrySelectionError,
)

__all__ = [
    "managed_row_table_specs",
    "instrumentation_specs",
    "all_store_item_ids",
    "assert_specs_align_with_contract_sheets",
]


#: 批次 1 第一张：D1-2 原值明细表（按类别）。3 固定票据种类行（稳定 key 固定行，D4-6 范式）。
_INCLUDE_D102_CATEGORY: Final[bool] = False

#: 批次 1 第二张：D1-4 坏账准备明细表**前两区**（个别计提 13-16 / 组合计提 18-21）。
#: 🔴 第三区（票据种类小计 R23-24）在 footer R22 **之下** ⇒ 走 static_region 寄生声明，
#:    不进本开关（`ExcelInstrumentationSpec.__post_init__` 强制 footer_row > last_data_row，
#:    动态 spec 表达不了 footer 下的区域 —— 这正是它必须走静态路径的硬证据）。
_INCLUDE_D104_BAD_DEBT: Final[bool] = False

#: 批次 1 第二张的第三区：D1-4 票据种类小计（static_region，绝对坐标直写、绕开位移链）。
_INCLUDE_D104_NOTETYPE_STATIC: Final[bool] = False

#: 批次 2 第一张：D1-8 贴现明细（双区：贴现 R14-21 + 背书 R26-33）。
_INCLUDE_D108_ENDORSEMENT: Final[bool] = False

#: 批次 2 第二张：D1-16 核销检查（双区：转回 R12-14 + 核销 R18-20）。
_INCLUDE_D116_WRITEOFF: Final[bool] = False

#: 批次 3 第一张：D1-9 贴息检查（单区 R11-17，有数据区行级公式 H/J/L）。
_INCLUDE_D109_INTEREST: Final[bool] = False

#: 批次 3 第二张：D1-11 关联方检查（单区 R11-13，有数据区行级公式 F/H）。
_INCLUDE_D111_RELATED_PARTY: Final[bool] = False

#: 批次 3 第三张：D1-12 质押检查（单区 R12-17，无数据区公式）。
_INCLUDE_D112_PLEDGE: Final[bool] = False

#: 批次 3 第四张：D1-10 监盘表（单区 R14-20，核对区纯公式不受管）。
_INCLUDE_D110_INVENTORY: Final[bool] = False

#: 批次 3 第五张：D1-15 ECL 测算表（双区 单项R14-17 / 组合R22-24，行级乘法公式 D=B*C）。
_INCLUDE_D115_ECL: Final[bool] = False

#: 批次 4 第一张：D1-13 抽凭检查（双区 增减R16-31 / 期后R37-44，17 列宽表）。
_INCLUDE_D113_SAMPLING: Final[bool] = False

#: 批次 4 第二张：D1-7 备查簿核对（双区 银行R13-17 / 商业R19-23，31 列宽表，dict store）。
_INCLUDE_D107_MEMO: Final[bool] = False


def _managed_last_col_of(spec: Any) -> str:
    """从 RowTableSheetSpec 的 field_specs 取最后一个受管业务列（按列序）。"""
    from app.services.workpaper_sync.sheet_geometry import col_index

    if not spec.field_specs:
        raise EntrySelectionError(f"{spec.managed_sheet} 未声明任何受管字段")
    return max((row[1] for row in spec.field_specs), key=col_index)


def _instrumentation_of(spec: Any) -> ExcelInstrumentationSpec:
    """把一个 `RowTableSheetSpec` 翻成 `ExcelInstrumentationSpec`（框架层声明 → 注入声明）。

    🔴 只翻**动态**（`excel_table`）spec。静态区走 `static_sheets` 寄生声明（见
    :func:`_static_sheet_declarations`），因为 `ExcelInstrumentationSpec.__post_init__`
    强制 `footer_row > last_data_row`，而静态区可以落在 footer 之下。
    """
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


def _static_sheet_declarations() -> tuple[dict[str, Any], ...]:
    """静态受管区寄生声明（`region_kind=static`：只写 definedName，不建 Table、不注 UUID 列）。

    当前唯一项：D1-4 第三区（票据种类小计 R23-24，在 footer R22 之下）。
    """
    if not _INCLUDE_D104_NOTETYPE_STATIC:
        return ()
    from app.services.workpaper_sync import phase5_d1_04_bad_debt as _d104

    spec = _d104.SPEC_D104_NOTETYPE
    return (
        {
            "sheet_key": spec.sheet_key,
            "managed_sheet": spec.managed_sheet,
            "defined_name": spec.defined_name,
            "first_data_row": spec.first_data_row,
            "last_data_row": spec.last_data_row,
            "region_kind": "static",
        },
    )


def managed_row_table_specs() -> tuple[Any, ...]:
    """本 entry 当前受管的**行表型** spec 清单（按灰度开关，顺序稳定）。

    D1-3 恒在（已交付）；其余按 `_INCLUDE_*` 开关逐张加入。
    """
    from app.services.workpaper_sync import phase5_d1_03_customer as _d103

    specs: list[Any] = [_d103.SPEC_D103]
    if _INCLUDE_D102_CATEGORY:
        from app.services.workpaper_sync import phase5_d1_02_category as _d102

        specs.append(_d102.SPEC_D102)
    if _INCLUDE_D104_BAD_DEBT:
        from app.services.workpaper_sync import phase5_d1_04_bad_debt as _d104

        specs.extend((_d104.SPEC_D104_INDIVIDUAL, _d104.SPEC_D104_PORTFOLIO))
    if _INCLUDE_D108_ENDORSEMENT:
        from app.services.workpaper_sync import phase5_d1_08_endorsement as _d108

        specs.extend((_d108.SPEC_D108_DISCOUNT, _d108.SPEC_D108_TRANSFER))
    if _INCLUDE_D116_WRITEOFF:
        from app.services.workpaper_sync import phase5_d1_16_writeoff as _d116

        specs.extend((_d116.SPEC_D116_REVERSAL, _d116.SPEC_D116_WRITEOFF))
    if _INCLUDE_D109_INTEREST:
        from app.services.workpaper_sync import phase5_d1_09_interest as _d109

        specs.append(_d109.SPEC_D109)
    if _INCLUDE_D111_RELATED_PARTY:
        from app.services.workpaper_sync import phase5_d1_11_related_party as _d111

        specs.append(_d111.SPEC_D111)
    if _INCLUDE_D112_PLEDGE:
        from app.services.workpaper_sync import phase5_d1_12_pledge as _d112

        specs.append(_d112.SPEC_D112)
    if _INCLUDE_D110_INVENTORY:
        from app.services.workpaper_sync import phase5_d1_10_inventory as _d110

        specs.append(_d110.SPEC_D110)
    if _INCLUDE_D115_ECL:
        from app.services.workpaper_sync import phase5_d1_15_ecl as _d115

        specs.extend((_d115.SPEC_D115_INDIVIDUAL, _d115.SPEC_D115_PORTFOLIO))
    if _INCLUDE_D113_SAMPLING:
        from app.services.workpaper_sync import phase5_d1_13_sampling as _d113

        specs.extend((_d113.SPEC_D113_VOUCHING, _d113.SPEC_D113_SPECIFIC))
    if _INCLUDE_D107_MEMO:
        from app.services.workpaper_sync import phase5_d1_07_memo as _d107

        specs.extend((_d107.SPEC_D107_BANK, _d107.SPEC_D107_COMMERCIAL))
    return tuple(specs)


def instrumentation_specs() -> tuple[ExcelInstrumentationSpec, ...]:
    """本 entry 的全部 instrumentation 声明（复数；D4 同名函数的 D1 对应物）。

    🔴 单数 :func:`instrumentation_spec` **保留不动**（零回归：golden digest 门钉住它）。
       复数是扩容后的新入口；受管 sheet 只有 D1-3 时二者等价（首项相同）。

    🔴 静态区寄生在**第一个**动态 spec 上（与 `transposed_sheets` 同构的挂法）——
       `_static_region_bindings(provider=…)` 会从它自动生成 binding，不需手动接线。
    """
    dynamic = [_instrumentation_of(s) for s in managed_row_table_specs()]
    statics = _static_sheet_declarations()
    if statics and dynamic:
        primary = dynamic[0]
        dynamic[0] = ExcelInstrumentationSpec(
            entry_id=primary.entry_id,
            template_id=primary.template_id,
            template_relative_path=primary.template_relative_path,
            managed_sheet=primary.managed_sheet,
            first_data_row=primary.first_data_row,
            last_data_row=primary.last_data_row,
            footer_row=primary.footer_row,
            managed_last_col=primary.managed_last_col,
            uuid_col=primary.uuid_col,
            table_name=primary.table_name,
            sheet_key=primary.sheet_key,
            transposed_sheets=primary.transposed_sheets,
            static_sheets=statics,
        )
    return tuple(dynamic)


def all_store_item_ids() -> tuple[str, ...]:
    """本 entry 的全部 store item（**单一口径**，出/回两方向都从它取，需求 3.3）。

    🔴 D4-35 恒空 / D4-13 写不进 OO 两个 bug 的根因正是「两方向各自维护并集、某一侧漏喂」。
       本函数是 D1 侧的同款收敛点。
    """
    items: list[str] = [STORE_ITEM_ID]
    for spec in managed_row_table_specs():
        if spec.store_item_id and spec.store_item_id not in items:
            items.append(spec.store_item_id)
    if _INCLUDE_D104_NOTETYPE_STATIC:
        from app.services.workpaper_sync import phase5_d1_04_bad_debt as _d104

        if _d104.SPEC_D104_NOTETYPE.store_item_id not in items:
            items.append(_d104.SPEC_D104_NOTETYPE.store_item_id)
    return tuple(items)


def assert_specs_align_with_contract_sheets(contract: SyncContract) -> None:
    """对齐计数守卫：instrumentation specs 的 sheet 集合必须 == 契约 sheets 的集合。

    🔴 事故背书（D4-35）：契约加了 sheets（8 张）但漏了 instrumentation spec（7 个）⇒
       attach **fail-closed 打挂整个 entry**，而不是只挂那一张。本守卫让这类不对齐在接入时
       就红并**精确报差集**，而不是上线后整册 500。
    """
    # 🔴 收敛到框架层唯一实现（spec workpaper-sync-registration-isolation Req 2.3）：
    #    本模块的复数 `instrumentation_specs()` 已含 D1-3 主 spec（首项）+ 扩容 sheet + 静态区
    #    寄生，正是通用守卫读的形态，故直接把**本扩容模块**当 provider 传入。不再各写一份
    #    集合比较（两份必然漂移）。异常类型改为通用守卫的 `ProviderCapabilityError`（`EntrySelectionError`
    #    仍导入保留供本模块其它路径用）。
    from app.services.workpaper_sync.phase5_row_table_sheet import (
        assert_provider_specs_align_with_contract,
    )

    import sys as _sys

    assert_provider_specs_align_with_contract(_sys.modules[__name__], contract)
