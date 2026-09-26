# -*- coding: utf-8 -*-
"""D3 多受管 sheet 扩容 —— `phase5_d3_prepaid_receipts` 的伴生模块。

spec: d3-sync-coverage-via-row-table-engine · Task 6 · Requirements 1.1 / 6.6

═══ 为什么抽成伴生模块而不是追加进 entry 模块 ═══

entry 模块（`phase5_d3_prepaid_receipts.py`）当前 869 行，仓库文件行数门禁
（`backend/scripts/file_size_whitelist.txt`）对它的基线是 967 行。虽然还有约 98 行余量，但
D1 lane 已立下的架构范式是「entry 模块持有冻结身份，扩容面单独放伴生模块」——这条边界不是
被行数逼出来的临时措施，是为了让 Task 8（D3-4 双区）/ Task 9（D3-5）/ Task 11（D3-7 双区）
复用同一个伴生模块，而不是让四个任务各自往 entry 模块里加代码、逐次顶穿门禁。新建本模块与
D3 lane 后续三个任务共享同一套灰度开关 + 聚合函数骨架，保持与 D1/E1 一致的架构范式。

伴生模块的边界（与 `phase5_d1_expansion.py` 同构）：entry 模块持有**冻结身份**（ENTRY_ID /
ADAPTER_ID / 模板哨兵 / 契约装配 / 发布编排，含 D3-2 自身单数 `instrumentation_spec()`，
golden digest 门钉住，**不动**）；本模块持有**扩容面**（灰度开关 / 受管 sheet 清单 /
instrumentation 复数 / store item 单一口径 / 对齐守卫）。两者都不含投影合并算法（那在框架层
`phase5_row_table_sheet`）。

🔴 灰度开关逐张接入，不做大爆炸（照 D1/D4 已验证的 `_INCLUDE_*: Final[bool]` 模式）。每张新
   sheet = 一个 `phase5_d3_XX_*.py` 声明 + 一个开关 + 一条判据，可独立开关、独立验证、独立
   回滚。本任务（Task 6）的开关初始为 **False**——"声明 + 灰度开关"指开关存在但不激活，
   Task 7（D3-6 接入验收）再决定是否打开。

事故背书：D4-35 曾「由并发会话加入契约 sheets（8 张）但漏了 instrumentation spec」，导致
specs(7) 与 sheets(8) 不对齐、**整个 entry attach fail-closed**。开关 + 对齐计数守卫能让这类
不对齐在接入时就红，而不是上线后整册 500。

═══ D3 与 D1 的一处差异（本模块暂不需要静态区寄生逻辑）═══

D1 伴生模块的 `_static_sheet_declarations()`/静态寄生分支是为 D1-4 第三区（footer 之下的
票据种类小计）而存在。Task 1 的六张 D3 sheet 形态实测结论是「六张里没有一张属 static_region」
（`evidence/task1-sheet-morphology-and-geometry.md` §一）——D3-6 是纯 UUID 动态行，不涉及
静态区寄生。本模块首版不含 D1 那套 `_static_sheet_declarations()`/`static_sheets` 拼接逻辑，
待后续任务（D3-4/D3-5/D3-7/D3-1）若实测出需要静态路径再补，不预先造未用到的分支。
"""
from __future__ import annotations

from typing import Any, Final, Mapping

from app.services.workpaper_sync.contracts import SyncContract
from app.services.workpaper_sync.excel_instrumentation import ExcelInstrumentationSpec
from app.services.workpaper_sync.phase5_d3_prepaid_receipts import (
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


#: 阶段 1：D3-6 关联关系及交易检查表（单区最简样本）。UUID 动态行，无静态区寄生需要。
#: ✅ 2026-09-26 Task 10（阶段 2 验收）开启：D3-6/D3-4/D3-5 三张统一批量翻开关，同步跑
#: `generate_phase5_d3_contract.py --apply` 重生成磁盘契约（一次性完成，不分三次生成，避免
#: 多次不必要的契约文件 diff——理由见 Task 8/9 的处置原则）。声明层已完整验证
#: （Task 6/7 15+15 用例 + formula_mask/离线 materialize/verify_unmanaged_regions/前端
#: D3TabIndex 全部通过），Task 7 记录的翻开关阻塞（打红 Task 2/4/5 共 11 用例）本次同步解除
#: ——那 3 个文件的"现状必红"断言已随本次接入更新为"已接入"断言，见各文件本体注释。
_INCLUDE_D306_RELATED_PARTY: Final[bool] = True

#: 阶段 2 第一张：D3-4 预收账款分析表**双区**（段①借方 13-15 / 段②贷方 22-23；Task 10 按 BP-21
#: 剔除 A16/A24 续行省略号占位行，原 13-16 / 22-24）。
#: ✅ 2026-09-26 Task 10 开启：上游 D1 spec Task 24（`_multi_region_sheets()` 参数化）已在
#: 本任务开工前确认交付（commit `787cc864c`，`.kiro/specs/d1-sync-row-table-engine-and-d1-
#: coverage/tasks.md` Task 24 现为 `[x]`）——Task 8 记录的"该任务仍 `[ ]` 未完成"结论已过期，
#: 本次开关后 D3-4 双区**自动**进入 `test_sibling_table_ref_row_shift.py::test_all_
#: multi_region_sheets_shift_sibling_table_refs` 的参数化覆盖清单（`phase5_d3_prepaid_
#: receipts` 已在该判据的 `_COMPANION_EXPANSION_MODULES` 登记伴生模块 `phase5_d3_expansion`），
#: 位移链实证结果见 `evidence/task10-stage2-acceptance.md`。
_INCLUDE_D304_ANALYSIS: Final[bool] = True

#: 阶段 2 第二张：D3-5 账龄1年以上的预收账款检查表（单区，六张里几何最小、无数据行公式列）。
#: ✅ 2026-09-26 Task 10 开启，与 D3-6/D3-4 同批统一翻开关 + 重生成磁盘契约。
_INCLUDE_D305_LONG_TERM: Final[bool] = True

#: 阶段 3：D3-7 预收账款检查表**双区**（区①本期 17-26 / 区②期后 31-38；两级表头，两区非同构
#: ——区① G/H 借贷两列、区② G 单列 + H:I 合并支持性文件，见 phase5_d3_07_voucher_check 模块
#: docstring "两区列语义差异"）。
#: 🔴 **初始 False**（Task 11 只声明不翻）：翻开关必须同步跑 `generate_phase5_d3_contract.py
#: --apply` 重生成受版本控制的磁盘契约（`assert_contract_file_matches_source()` 双向锁死机制），
#: 且会让 Property 4（D3-7 双区受管区 5→7）从"未接入红基线"转绿——这两件事一并留给 Task 12
#: （D3-7 接入验收）统一处置，与 Task 8/9 只声明不翻、由验收任务统一翻的处置一致（Task 10 已
#: 确立"翻开关必同步重生成磁盘契约"的纪律）。
#: ✅ 2026-09-26 Task 12（D3-7 接入验收）开启：D3-7 两区无模板缺陷（Task 11 openpyxl 已确认
#: 两区合计行 A27/A39 精确「合计」、SUM 区间 G17:G26/G31:G38 覆盖全部数据行、末行 R26/R38 非
#: BP-21 占位行），翻开关不需要改模板。同步跑 `generate_phase5_d3_contract.py --apply` 重生成
#: 磁盘契约（受管区 5→7：d32 1 + d36 1 + d34 2 + d35 1 + d37 2），`assert_contract_file_
#: matches_source()` 双向锁死通过；Property 4（D3-7 双区受管区 5→7）随之转绿。位移链/整册/
#: golden digest 结果见 `evidence/task12-d3-07-acceptance.md`。
_INCLUDE_D307_VOUCHER_CHECK: Final[bool] = True


def _managed_last_col_of(spec: Any) -> str:
    """从 RowTableSheetSpec 的 field_specs 取最后一个受管业务列（按列序）。"""
    from app.services.workpaper_sync.sheet_geometry import col_index

    if not spec.field_specs:
        raise EntrySelectionError(f"{spec.managed_sheet} 未声明任何受管字段")
    return max((row[1] for row in spec.field_specs), key=col_index)


def _instrumentation_of(spec: Any) -> ExcelInstrumentationSpec:
    """把一个 `RowTableSheetSpec` 翻成 `ExcelInstrumentationSpec`（框架层声明 → 注入声明）。

    🔴 只翻**动态**（`excel_table`）spec。D3 首版六张实测均非 static_region（Task 1 结论），
    本函数暂不需要区分静态路径；若后续任务实测出需要静态区寄生，届时再补 D1 同款分支。
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


def managed_row_table_specs() -> tuple[Any, ...]:
    """本 entry 当前受管的**行表型** spec 清单（按灰度开关，顺序稳定）。

    D3-2（`phase5_d3_prepaid_receipts` 自身）恒在（已交付，走单数 `instrumentation_spec()`，
    不由本函数枚举——本函数只枚举**扩容面**新增的 sheet）。开关全 False 时返回空 tuple，
    与「D3 现状只有 1 个受管区（D3-2）」逐字等价（零回归）。
    """
    specs: list[Any] = []
    if _INCLUDE_D306_RELATED_PARTY:
        from app.services.workpaper_sync import phase5_d3_06_related_party as _d306

        specs.append(_d306.SPEC_D306)
    if _INCLUDE_D304_ANALYSIS:
        from app.services.workpaper_sync import phase5_d3_04_analysis as _d304

        # 🔴 两个 spec 共享 sheet_key="d34-managed"（同 managed_sheet）——顺序即 Excel
        # 行序（段①借方 13-15 在段②贷方 22-23 之上），与 `SPECS_D304` 的声明顺序一致。
        specs.extend((_d304.SPEC_D304_DEBIT, _d304.SPEC_D304_CREDIT))
    if _INCLUDE_D305_LONG_TERM:
        from app.services.workpaper_sync import phase5_d3_05_long_term as _d305

        specs.append(_d305.SPEC_D305)
    if _INCLUDE_D307_VOUCHER_CHECK:
        from app.services.workpaper_sync import phase5_d3_07_voucher_check as _d307

        # 🔴 两个 spec 共享 sheet_key="d37-managed"（同 managed_sheet）——顺序即 Excel
        # 行序（区①本期 17-26 在区②期后 31-38 之上），与 `SPECS_D307` 声明顺序一致。
        specs.extend((_d307.SPEC_D307_CURRENT, _d307.SPEC_D307_POST))
    return tuple(specs)


def instrumentation_specs() -> tuple[ExcelInstrumentationSpec, ...]:
    """本 entry **扩容面**的全部 instrumentation 声明（复数；不含 D3-2 自身单数声明）。

    🔴 D3-2 自身的单数 `phase5_d3_prepaid_receipts.instrumentation_spec()` **保留不动**
       （零回归：golden digest 门钉住它）。本函数是扩容后新增 sheet 的入口；开关全 False 时
       返回空 tuple——调用方需要把它与 D3-2 自身的单数声明**合并**才是 entry 的完整
       instrumentation 清单（合并动作留给循环层 `phase5_d3_prepaid_receipts` 的契约装配处，
       本模块只负责扩容面自己的部分，不重复声明 D3-2）。
    """
    return tuple(_instrumentation_of(s) for s in managed_row_table_specs())


def all_store_item_ids() -> tuple[str, ...]:
    """本 entry**全部**（D3-2 自身 + 扩容面）store item（**单一口径**，出/回两方向都从它取）。

    🔴 D4-35 恒空 / D4-13 写不进 OO 两个 bug 的根因正是「两方向各自维护并集、某一侧漏喂」。
       本函数是 D3 侧的同款收敛点，与 D1 `phase5_d1_expansion.all_store_item_ids()` 同构。
    """
    items: list[str] = [STORE_ITEM_ID]
    for spec in managed_row_table_specs():
        if spec.store_item_id and spec.store_item_id not in items:
            items.append(spec.store_item_id)
    return tuple(items)


def assert_specs_align_with_contract_sheets(contract: SyncContract) -> None:
    """对齐计数守卫：D3-2 自身 sheet + 扩容面 instrumentation specs 的 sheet 集合必须
    == 契约 sheets 的集合。

    🔴 事故背书（D4-35）：契约加了 sheets（8 张）但漏了 instrumentation spec（7 个）⇒
       attach **fail-closed 打挂整个 entry**，而不是只挂那一张。本守卫让这类不对齐在接入时
       就红并**精确报差集**，而不是上线后整册 500。

    🔴 收敛到框架层唯一实现（spec workpaper-sync-registration-isolation Req 2.3）：
       D3 扩容模块的 `instrumentation_specs()` **不含** D3-2 自身（D3-2 走 entry 模块的单数
       `instrumentation_spec()`），而通用守卫需看到完整 spec 集合。因此这里构造一个临时
       适配对象，把 D3-2 自身的单数 spec 并入扩容面的复数 specs，再传通用守卫。异常类型由
       通用守卫统一使用 `ProviderCapabilityError`（不再各写集合比较）。
    """
    from app.services.workpaper_sync.phase5_d3_prepaid_receipts import (
        instrumentation_spec as _d32_spec,
    )
    from app.services.workpaper_sync.phase5_row_table_sheet import (
        assert_provider_specs_align_with_contract,
    )

    # 适配层：合并 D3-2 自身单数 spec（首项）+ 扩容面复数 specs，供通用守卫统一读取。
    _combined = (_d32_spec(), *instrumentation_specs())

    class _D3CombinedProvider:
        @staticmethod
        def instrumentation_specs():
            return _combined

    assert_provider_specs_align_with_contract(_D3CombinedProvider, contract)
