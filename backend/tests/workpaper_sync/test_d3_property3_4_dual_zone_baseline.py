# -*- coding: utf-8 -*-
"""D3-4 / D3-7 双区红判据基线（Task 4）。

spec: d3-sync-coverage-via-row-table-engine · Requirements 2.1, 3.1

═══ 判据面（design.md Property 3 / 4，本文件读作 D3-P3 / D3-P4）═══

D3-P3：D3-4 是双区（受管区 2→4），两键各自读回等值。
D3-P4：D3-7 是双区（受管区 5→7），两键各自读回等值。

═══ ✅ Task 10（阶段 2 验收）迁移：D3-P3 转绿，D3-P4 仍红 ═══

D3-6 / D3-4 / D3-5 三个灰度开关在 Task 10 统一打开并重生成磁盘契约后，§1 的三条判据按
「已接入」语义迁移（判据的牙齿不变，只改"现状是什么"）：

* `test_current_d3_managed_region_count_after_stage2_is_five`（原
  `..._is_pre_expansion_baseline`，断言 ==1）：现状实测 5 = D3-2 1 + D3-6 1 + D3-4 2 +
  D3-5 1，按 sheet_key 逐项钉死分布（任何一张多/少一个 table 都红，不止看总数）。
* `test_d3_4_dual_zone_both_keys_declared_in_one_sheet`（原
  `..._not_yet_reaching_target_count_of_four`，断言 <4）：**D3-P3 转绿** —— 同一 sheet 条目
  （共享 `d34-managed`）恰 2 个 table，两键 `D3-ana-debit-rows`/`D3-ana-credit-rows` 各归其表。
  "两键各自读回等值"的往返部分由 `test_d3_04_dual_zone_shift_and_verify.py` 承担。
* `test_d3_7_dual_zone_not_yet_reaching_target_count_of_seven`：**保持红基线**（Task 11/12 范围），
  但修掉一处空转 —— Task 4 原判据用子串查 `stable_field_key`，而它的真实形态是
  `{table_key}/{row_uuid}/{column_key}`，永远不含 `vc-post` 之类 store 键片段（D3-4 真实接入后
  `"ana-debit" in stable_field_key` 仍 0 命中，Task 10 实测）。改为查字段声明的 `store_item_id`，
  并用已接入的 D3-4 两键作"查法非空转"见证。

═══ ✅ Task 12（D3-7 接入验收）迁移：D3-P4 转绿（受管区 5→7）═══

D3-7 灰度开关在 Task 12 打开并重生成磁盘契约后，§1 的 D3-7 相关判据按「已接入」语义再迁移一次
（判据牙齿不变，只改"现状是什么"，同 Task 10 对 D3-4 的处理原则）：

* `test_current_d3_managed_region_count_after_stage2_is_five` → 更新为受管区 **7**（D3-2 1 +
  D3-6 1 + D3-4 2 + D3-5 1 + **D3-7 2**），`_STAGE2_REGIONS_BY_SHEET` 追加 `d37-managed:2`。
  函数名保留（无外部引用，仅本文件与 append-only 证据引用），docstring 更新为「现停在 7」。
* `test_d3_7_dual_zone_not_yet_reaching_target_count_of_seven`（原断言 <7、D3-7 键未出现）：
  **D3-P4 转绿** —— 照抄 D3-4 的 `test_d3_4_dual_zone_both_keys_declared_in_one_sheet` 改法，
  改为断言 D3-7 同一 sheet 条目（共享 `d37-managed`）恰 2 个 table、两键 `D3-vc-current-rows`/
  `D3-vc-post-rows` 各归其表。"两键各自读回等值"的往返 + 位移链由
  `test_d3_07_dual_zone_shift_and_verify.py` 承担。

§2 三组合成变异用例原样保留（Task 10/12 均不动）。下文「为什么现在必须是红判据」是 Task 4
落地时的历史论证，保留备查。

═══ 为什么现在必须是红判据（不是判据代码写错，是接入前的现状） ═══

Task 1 证据（`evidence/task1-sheet-morphology-and-geometry.md`）已实测：D3-4 两个受管区
边界为段①借方分析（行 13-16，`D3-ana-debit-rows`）/ 段②贷方分析（行 22-24，
`D3-ana-credit-rows`）；D3-7 两个受管区边界为区①本期增减变动检查（行 17-26，
`D3-vc-current-rows`）/ 区②期后结转检查（行 31-38，`D3-vc-post-rows`）。但 Task 6/8/9/11
（D3-6/D3-4/D3-5/D3-7 各自的 `RowTableSheetSpec` 声明代码）尚未执行 —— 当前 HEAD 的
`phase5_d3_prepaid_receipts.py`（唯一存在的 D3 provider）只声明了 **D3-2 一个受管区**
（`build_contract_payload()["sheets"]` 长度为 1，该 sheet 内只有一个 table）。

本 spec 也**尚不存在**类似 D1/E1 的 `phase5_d3_expansion.py` 编排层（`_INCLUDE_D306` /
`_INCLUDE_D304` 等灰度开关 + `instrumentation_specs()` 聚合函数）——那是 Task 6 才会新建的
文件。⇒ 此刻没有「逐张开关」可供断言，唯一存在的、可现算的「受管区计数」口径是磁盘契约
`sheets[].tables[]` 的总数（与 `test_d1_instrumentation_specs_expansion.py` /
`test_e1_provider_and_expansion.py` 的计数口径同源：`for sheet in contract.sheets:
for table in sheet.tables: ...`，全仓无第二套计数逻辑，见 `contracts.py` /
`excel_extract.py` / `excel_materialize.py` / `merge.py` 等处处这个双层 for 循环）。

⇒ 本文件的「现状必红」意为：**此刻**受管区计数应停留在接入前的基线值（< 4，< 7），这正是
Task 10/12 完成后「受管区 2→4 / 5→7」转绿的可归因起点。若某天这个基线判据本身变绿（计数
达到或超过 4/7），说明 D3-4/D3-7 已经接入，本文件需要连同 spec 状态一起更新（同
`test_e1p1_current_state_is_red_legacy_fake_bidirectional` 的处理原则）。

═══ 变异检验：判据要有牙齿 ═══

D3-4/D3-7 的真实 `RowTableSheetSpec` 声明代码尚不存在（Task 8/11 待做），故变异检验用
**合成契约**模拟「只声明了一个受管区」的场景（同 sheet 双 table 退化成单 table），验证
判据逻辑本身能检测出「另一键在 OO 视图里不可见」这个缺陷 —— 对应 tasks.md 原文「只声明一个
受管区 ⇒ 另一键数据在 OO 里不可见，必红」。合成契约的双区结构参照已落地的 D4-9
（`phase5_d4_customer_structure.py`：同 managed_sheet、不同 table_key/UUID 列的两个动态
table）与 Task 1 证据记录的 D3-4/D3-7 真实行段边界，不是凭空拍的数字。
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

from app.services.workpaper_sync import phase5_d3_prepaid_receipts as D3
from app.services.workpaper_sync.contracts import (
    CellMapping,
    FieldSpec,
    FieldMode,
    FooterAnchorSpec,
    RowIdentityKind,
    RowIdentitySpec,
    SheetSpec,
    TableSpec,
    ValueType,
)


# ═══════════════════════════════════════════════════════════════════════════
# 0. 受管区计数口径（与 test_d1_instrumentation_specs_expansion.py /
#    test_e1_provider_and_expansion.py 同源：sheets[].tables[] 总数，全仓唯一计数逻辑）
# ═══════════════════════════════════════════════════════════════════════════


def _managed_region_count(sheets: tuple[SheetSpec, ...]) -> int:
    """一个受管区 = 契约里一张 `TableSpec`（同 sheet 多 table = 同 sheet 多受管区，D4-9 范式）。

    这不是本文件自造的口径 —— 是 `contracts.py`/`excel_extract.py`/`excel_materialize.py`/
    `merge.py` 等处处出现的同一个 `for sheet in contract.sheets: for table in sheet.tables:`
    双层遍历的计数版本，全仓没有第二套「受管区数量」定义。
    """
    return sum(len(sheet.tables) for sheet in sheets)


# ═══════════════════════════════════════════════════════════════════════════
# 1. 现状计数 + D3-P3 转绿（Task 10 迁移）+ D3-P4 仍红
# ═══════════════════════════════════════════════════════════════════════════

#: Task 14（D3-1 审定表接入）后的实测受管区分布（sheet_key → table 数）。design.md 路线
#: `1(D3-2) → 2(D3-6) → 4(D3-4双区) → 5(D3-5) → 7(D3-7双区) → 9(D3-1双区块)`，现停在 9。
_STAGE2_REGIONS_BY_SHEET: dict[str, int] = {
    "d32-managed": 1,
    "d36-managed": 1,
    "d34-managed": 2,
    "d35-managed": 1,
    "d37-managed": 2,
    "d31-managed": 2,  # D3-1 审定表两区块（性质+账龄）
}

#: D3-4 分析表 sheet 名与两键（store 键逐字取前端 `useD3Analysis.ts` 的
#: `ITEM_ID_DEBIT_ROWS`/`ITEM_ID_CREDIT_ROWS`，不从 provider 常量回读 —— 独立真源才有牙齿）。
_D34_SHEET_NAME = "预收账款分析表D3-4"
_D34_KEYS: dict[str, str] = {
    "analysis_debit_rows": "D3-ana-debit-rows",
    "analysis_credit_rows": "D3-ana-credit-rows",
}
_D37_SHEET_NAME = "预收账款检查表D3-7"
_D37_KEYS: frozenset[str] = frozenset({"D3-vc-current-rows", "D3-vc-post-rows"})


def _store_item_ids_by_table(contract: object) -> dict[str, frozenset[str]]:
    """table_key → 该表全部字段声明的 `store_item_id` 集合（读 canonical payload）。

    🔴 不用 `stable_field_key` 子串：它的真实形态是 `{table_key}/{row_uuid}/{column_key}`，
    永远不含 store 键片段（Task 4 原判据因此空转）。解析后的 `FieldSpec` 不携带
    `store_item_id`，故读契约原始 payload。
    """
    out: dict[str, frozenset[str]] = {}
    for sheet in contract.canonical_payload["sheets"]:  # type: ignore[attr-defined]
        for table in sheet["tables"]:
            out[table["table_key"]] = frozenset(
                str(field.get("store_item_id") or "") for field in table["fields"]
            )
    return out


def test_current_d3_managed_region_count_after_stage2_is_five() -> None:
    """Task 14（D3-1 审定表接入）后现状：受管区 9 个（D3-2 1 + D3-6 1 + D3-4 2 + D3-5 1 +
    D3-7 2 + D3-1 2），按 sheet 逐项钉死。

    只看总数会放过「D3-7 少一区、另一张多一区」这类互相抵消的错；按 sheet_key 比分布不会。
    （函数名保留 `..._after_stage2_is_five` 是历史沿革；实际断言值已随 Task 10→12 接入从 5
    推进到 7，无外部引用故不改名，避免与 append-only 证据文件的交叉引用漂移。）
    """
    contract = D3.assert_contract_file_matches_source()
    count = _managed_region_count(contract.sheets)
    by_sheet = {sheet.sheet_key: len(sheet.tables) for sheet in contract.sheets}
    assert by_sheet == _STAGE2_REGIONS_BY_SHEET, (
        f"D3 受管区分布与 Task 12 验收值不符：实得 {by_sheet}，应为 {_STAGE2_REGIONS_BY_SHEET}"
    )
    assert count == 9, f"D3 现状受管区计数应为 9，实得 {count}"


def test_d3_4_dual_zone_both_keys_declared_in_one_sheet() -> None:
    """D3-P3 转绿：D3-4 两区都已声明，且同在**一个**契约 sheet 条目里（恰 2 个 table）。

    Property 3「受管区 2→4」的目标值已达到（此后 D3-5 接入使之继续到 5）。
    """
    contract = D3.assert_contract_file_matches_source()
    assert _managed_region_count(contract.sheets) >= 4, "Property 3 目标（受管区达到 4）未达到"
    d34 = [sheet for sheet in contract.sheets if sheet.excel_name == _D34_SHEET_NAME]
    assert len(d34) == 1, (
        f"D3-4 应只有一个契约 sheet 条目（两区共享 sheet_key），实得 {len(d34)} 个 —— "
        "两个条目意味着同一 excel_name 被重复声明"
    )
    sheet = d34[0]
    assert sheet.sheet_key == "d34-managed"
    assert [table.table_key for table in sheet.tables] == list(_D34_KEYS), (
        f"D3-4 应恰 2 个 table 且按 Excel 行序（借方在上），实得 "
        f"{[table.table_key for table in sheet.tables]}"
    )
    stores = _store_item_ids_by_table(contract)
    for table_key, store_key in _D34_KEYS.items():
        assert stores[table_key] == {store_key}, (
            f"{table_key} 的字段应全部归属 {store_key}，实得 {sorted(stores[table_key])} —— "
            "两区串键会让一侧数据在 OO 里不可见"
        )


#: D3-7 检查表两 table_key → store 键（逐字取 `phase5_d3_07_voucher_check` 声明的
#: `store_item_id`，与 Task 3 判据 `REAL_STORE_ITEM_IDS` 同源；不从 provider 常量回读——
#: 独立真源才有牙齿，同 _D34_KEYS 的处理原则）。
_D37_KEYS_BY_TABLE: dict[str, str] = {
    "voucher_check_current_rows": "D3-vc-current-rows",
    "voucher_check_post_rows": "D3-vc-post-rows",
}


def test_d3_7_dual_zone_not_yet_reaching_target_count_of_seven() -> None:
    """D3-P4 转绿（Task 12）：D3-7 两区都已声明，且同在**一个**契约 sheet 条目里（恰 2 个 table）。

    Property 4「受管区 5→7」的目标值已达到（design.md「阶段 3 验收」）。照抄 D3-4 的
    `test_d3_4_dual_zone_both_keys_declared_in_one_sheet` 改法（判据牙齿不变，只把"现状"从
    "未接入红基线"迁到"已接入绿"）。函数名保留历史沿革（无外部代码引用）。
    """
    contract = D3.assert_contract_file_matches_source()
    assert _managed_region_count(contract.sheets) >= 7, "Property 4 目标（受管区达到 7）未达到"
    d37 = [sheet for sheet in contract.sheets if sheet.excel_name == _D37_SHEET_NAME]
    assert len(d37) == 1, (
        f"D3-7 应只有一个契约 sheet 条目（两区共享 sheet_key），实得 {len(d37)} 个 —— "
        "两个条目意味着同一 excel_name 被重复声明"
    )
    sheet = d37[0]
    assert sheet.sheet_key == "d37-managed"
    assert [table.table_key for table in sheet.tables] == list(_D37_KEYS_BY_TABLE), (
        f"D3-7 应恰 2 个 table 且按 Excel 行序（区①本期在上），实得 "
        f"{[table.table_key for table in sheet.tables]}"
    )
    stores = _store_item_ids_by_table(contract)
    for table_key, store_key in _D37_KEYS_BY_TABLE.items():
        assert stores[table_key] == {store_key}, (
            f"{table_key} 的字段应全部归属 {store_key}，实得 {sorted(stores[table_key])} —— "
            "两区串键会让一侧数据在 OO 里不可见"
        )
    # 查法非空转见证：已接入的 D3-4 两键必须能被同一查法查到（保留原判据的空转防护）。
    declared = frozenset().union(*stores.values())
    assert set(_D34_KEYS.values()) <= declared, (
        f"store 键查法没查到已接入的 D3-4 两键（实得 {sorted(declared)}）—— 判据空转"
    )
    assert _D37_KEYS <= declared, (
        f"契约字段里应出现 D3-7 的两个 store 键，实得 {sorted(declared & _D37_KEYS)}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 2. 变异检验：判据要有牙齿 —— 用合成契约模拟「只声明一个受管区」
#
#    D3-4/D3-7 的真实 RowTableSheetSpec 声明代码尚不存在（Task 8/11 待做），故这里不去改
#    生产代码，而是直接构造一份最小化的合成 SheetSpec/TableSpec，形状对齐 Task 1 证据记录
#    的 D3-4/D3-7 真实行段边界与 D4-9 的「同 sheet 双 table」范式，验证：
#      (a) 计数逻辑本身能数出「声明了几个受管区」；
#      (b) 「只声明一个受管区」时，另一键对应的字段确实从 all_fields() 里消失
#          （= tasks.md 原文「另一键数据在 OO 里不可见」的可判据化表达 —— OO 视图渲染的
#          字段来自契约声明的 fields，缺字段 ⇒ 该键数据在 OO 里必然不可见）。
# ═══════════════════════════════════════════════════════════════════════════


def _synthetic_field(stable_key: str, column: str) -> FieldSpec:
    """构造一个最小合法 FieldSpec，字段值本身对本判据的计数/存在性断言无关，只要形状合法。"""
    return FieldSpec(
        stable_field_key=stable_key,
        json_pointer=f"/rows/{{row_uuid}}/{stable_key}",
        mode=FieldMode.editable,
        value_type=ValueType.text,
        source_ref=f"源xlsx!预收账款分析表D3-4!{column}13",
        row_scoped=True,
        column_key=stable_key,
        cell=CellMapping(column=column, row_from="row_identity"),
    )


def _synthetic_dual_zone_sheet(*, include_debit: bool, include_credit: bool) -> SheetSpec:
    """合成「D3-4 分析表」双区 sheet，可选择性只声明一个区（模拟遗漏声明的缺陷场景）。

    行段边界取自 Task 1 证据实测值：段①借方 13-16、段②贷方 22-24（同 managed_sheet，
    不同 table_key/UUID 列，与 D4-9 `phase5_d4_customer_structure.py` 的双 table 范式同型）。
    """
    tables: list[TableSpec] = []
    if include_debit:
        tables.append(
            TableSpec(
                table_key="analysis_debit_rows",
                anchor="A13",
                header_rows=1,
                fields=(_synthetic_field("D3-ana-debit-rows/label", "A"),),
                row_identity=RowIdentitySpec(
                    kind=RowIdentityKind.field,
                    json_pointer="/rows/*/rowId",
                ),
                footer_anchor=FooterAnchorSpec(
                    marker="差异", search_column="A", carries_total_formula=False
                ),
            )
        )
    if include_credit:
        tables.append(
            TableSpec(
                table_key="analysis_credit_rows",
                anchor="A22",
                header_rows=1,
                fields=(_synthetic_field("D3-ana-credit-rows/label", "A"),),
                row_identity=RowIdentitySpec(
                    kind=RowIdentityKind.field,
                    json_pointer="/rows/*/rowId",
                ),
                footer_anchor=FooterAnchorSpec(
                    marker="差异合理性分析", search_column="A", carries_total_formula=False
                ),
            )
        )
    return SheetSpec(
        sheet_key="d34-managed",
        excel_name="预收账款分析表D3-4",
        locator_anchor="A13",
        tables=tuple(tables),
    )


def _synthetic_dual_zone_voucher_check_sheet(
    *, include_current: bool, include_post: bool
) -> SheetSpec:
    """合成「D3-7 检查表」双区 sheet（区①本期 17-26 / 区②期后 31-38，Task 1 证据实测边界）。"""
    tables: list[TableSpec] = []
    if include_current:
        tables.append(
            TableSpec(
                table_key="voucher_check_current_rows",
                anchor="A17",
                header_rows=2,
                fields=(_synthetic_field("D3-vc-current-rows/customer", "A"),),
                row_identity=RowIdentitySpec(
                    kind=RowIdentityKind.field,
                    json_pointer="/rows/*/rowId",
                ),
                footer_anchor=FooterAnchorSpec(
                    marker="合计", search_column="G", carries_total_formula=True
                ),
            )
        )
    if include_post:
        tables.append(
            TableSpec(
                table_key="voucher_check_post_rows",
                anchor="A31",
                header_rows=2,
                fields=(_synthetic_field("D3-vc-post-rows/customer", "A"),),
                row_identity=RowIdentitySpec(
                    kind=RowIdentityKind.field,
                    json_pointer="/rows/*/rowId",
                ),
                footer_anchor=FooterAnchorSpec(
                    marker="合计", search_column="G", carries_total_formula=True
                ),
            )
        )
    return SheetSpec(
        sheet_key="d37-managed",
        excel_name="预收账款检查表D3-7",
        locator_anchor="A17",
        tables=tuple(tables),
    )


def test_mutation_d3_4_declaring_only_debit_zone_loses_credit_key_visibility() -> None:
    """🔴 变异检验（有牙齿）：D3-4 只声明段①（借方）⇒ 贷方键在 OO 视图里必然不可见。

    完整双区（对照组）应有 2 个受管区、debit 与 credit 两个 stable_field_key 均存在。
    退化成单区（变异组）应只剩 1 个受管区，且 credit 键从 all_fields() 消失 ——
    这就是 tasks.md 原文「另一键数据在 OO 里不可见」的可判据化验证：OO 端渲染受管字段时
    读的正是契约 all_fields()，缺字段意味着该 store 键对应的数据在 OO canvas 上根本
    没有对应单元格可以显示。
    """
    full = _synthetic_dual_zone_sheet(include_debit=True, include_credit=True)
    assert _managed_region_count((full,)) == 2, "完整双区声明必须数出 2 个受管区（对照组基线）"
    full_keys = {f.stable_field_key for table in full.tables for f in table.fields}
    assert "D3-ana-debit-rows/label" in full_keys
    assert "D3-ana-credit-rows/label" in full_keys

    # 变异：只声明段①（借方），漏声明段②（贷方）——模拟 Task 8 若疏忽合并成单区的缺陷。
    mutated = _synthetic_dual_zone_sheet(include_debit=True, include_credit=False)
    mutated_count = _managed_region_count((mutated,))
    assert mutated_count == 1, f"只声明一区应数出 1 个受管区，实得 {mutated_count}"
    mutated_keys = {f.stable_field_key for table in mutated.tables for f in table.fields}
    assert "D3-ana-debit-rows/label" in mutated_keys, "借方键应仍然存在（对照）"
    assert "D3-ana-credit-rows/label" not in mutated_keys, (
        "🔴 判据未能检测出贷方键缺失 —— 变异检验失效，这条判据没有牙齿"
    )
    # 判据本身要能打红：受管区计数从 2 掉到 1，且掉的正是 credit 那个键。
    assert mutated_count < 2, "判据必须能感知到受管区从双区退化成单区"


def test_mutation_d3_7_declaring_only_current_zone_loses_post_key_visibility() -> None:
    """🔴 变异检验（有牙齿）：D3-7 只声明区①（本期）⇒ 期后结转键在 OO 视图里必然不可见。

    对照 D3-4 的写法，验证同款缺陷模式在 D3-7 上同样能被判据检出（两张双区结构同型，
    判据逻辑理应通用）。
    """
    full = _synthetic_dual_zone_voucher_check_sheet(include_current=True, include_post=True)
    assert _managed_region_count((full,)) == 2, "完整双区声明必须数出 2 个受管区（对照组基线）"
    full_keys = {f.stable_field_key for table in full.tables for f in table.fields}
    assert "D3-vc-current-rows/customer" in full_keys
    assert "D3-vc-post-rows/customer" in full_keys

    # 变异：只声明区①（本期），漏声明区②（期后结转）。
    mutated = _synthetic_dual_zone_voucher_check_sheet(include_current=True, include_post=False)
    mutated_count = _managed_region_count((mutated,))
    assert mutated_count == 1, f"只声明一区应数出 1 个受管区，实得 {mutated_count}"
    mutated_keys = {f.stable_field_key for table in mutated.tables for f in table.fields}
    assert "D3-vc-current-rows/customer" in mutated_keys, "本期键应仍然存在（对照）"
    assert "D3-vc-post-rows/customer" not in mutated_keys, (
        "🔴 判据未能检测出期后结转键缺失 —— 变异检验失效，这条判据没有牙齿"
    )
    assert mutated_count < 2, "判据必须能感知到受管区从双区退化成单区"


def test_mutation_merging_into_shared_table_key_still_loses_one_key() -> None:
    """🔴 变异检验的另一变体：不是「漏声明整个 table」，而是把两键**误合并成一个** table_key。

    这个变体更贴近真实容易犯的错——不是完全遗漏，而是想「省事」把借贷两区塞进同一个
    table_key 里（design.md 明确禁止：「不得合并为单区」）。用一个只含 debit 字段、
    table_key 却命名为「analysis_rows」（既非 debit 也非 credit 的合并名）的单 table 模拟，
    验证判据同样能检出 credit 键缺失，不会被「table_key 换了个名字」蒙混过关。
    """
    merged_table = TableSpec(
        table_key="analysis_rows",  # 🔴 合并后的模糊命名，design.md 明确禁止的形态
        anchor="A13",
        header_rows=1,
        fields=(_synthetic_field("D3-ana-debit-rows/label", "A"),),
        row_identity=RowIdentitySpec(
            kind=RowIdentityKind.field, json_pointer="/rows/*/rowId"
        ),
    )
    merged_sheet = SheetSpec(
        sheet_key="d34-managed",
        excel_name="预收账款分析表D3-4",
        locator_anchor="A13",
        tables=(merged_table,),
    )
    assert _managed_region_count((merged_sheet,)) == 1, "合并声明必须仍只数出 1 个受管区"
    merged_keys = {f.stable_field_key for table in merged_sheet.tables for f in table.fields}
    assert "D3-ana-credit-rows/label" not in merged_keys, (
        "🔴 合并成单 table_key 后 credit 键仍应检测为缺失 —— 若这里断言失败说明判据被 "
        "table_key 改名蒙混过去了"
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v", "--tb=short"]))
