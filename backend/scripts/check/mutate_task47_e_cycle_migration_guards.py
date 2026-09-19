# -*- coding: utf-8 -*-
"""Task 47 守卫变异检验（E 循环 slice/deletion plan + E1 行身份行为侧守卫）。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 5 Task 47
Requirements: 14.7 · Property 57（变异检验本身）
被检守卫: Property 23 / 69 / 70

## 四态

| 判定 | 含义 | 归因 |
|---|---|---|
| ``RED`` | **预期那条**判据打红 | 守卫有效 |
| ``GREEN`` | 无新增失败 | **守卫缺陷** |
| ``WRONG-TEST`` | 打红了但不是预期项 | 锚点错行 / 污染残留 |
| ``ANCHOR-MISS`` | 锚点非唯一命中 / 未落盘 | **本脚本缺陷** |

## 两侧分工（为什么必须两侧都变异）

- ``be`` 侧变异打到 **slice/deletion plan 登记表**与**被登记的真实源码符号**，
  验证「登记 ↔ 源码/模板」的双向锁；
- ``fe`` 侧变异打到 **真实 composable 的行身份实现**，验证 Property 23 的行为侧判据
  真的在跑 composable 而不是在扫字符串。

只做 be 侧会漏掉「登记写得漂亮但实现用下标」这一类；只做 fe 侧会漏掉「实现对但登记表
指向不存在的符号/模板漂移」这一类。

## 用法

    py -3 backend/scripts/check/mutate_task47_e_cycle_migration_guards.py --list
    py -3 backend/scripts/check/mutate_task47_e_cycle_migration_guards.py --check-anchors
    py -3 backend/scripts/check/mutate_task47_e_cycle_migration_guards.py --run be --out <path>
    py -3 backend/scripts/check/mutate_task47_e_cycle_migration_guards.py --run fe --out <path>
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "backend" / "scripts"))

from _mutation_kit import Mutation, run_cli  # noqa: E402

FRONTEND = REPO / "audit-platform" / "frontend"
_FE_JSON = REPO / "backend" / "scripts" / "check" / "_wip_task47_fe.json"

SLICE = "backend/data/workpaper_sync_e_cycle_manifest_slice.json"
PLAN = "backend/data/workpaper_sync_e_cycle_deletion_plan.json"
PREFILL = "audit-platform/frontend/src/components/workpaper/composables/e1BankAccountPrefill.ts"
BANK = "audit-platform/frontend/src/components/workpaper/composables/useE1BankDetail.ts"
DUAL = "audit-platform/frontend/src/components/workpaper/composables/useG1DualMode.ts"
G1LABELS = "audit-platform/frontend/src/components/workpaper/composables/g1SheetLabels.ts"
HOST = "audit-platform/frontend/src/components/workpaper/GtE1MonetaryFund.vue"

#: 覆盖面分母：本任务的守卫文件 → 归属说明。空分母会让覆盖统计恒成功。
GUARD_FILES = {
    "test_task47_e_cycle_migration.py": "slice/deletion plan ↔ 全量 manifest ↔ 权威模板 ↔ 源码符号的双向锁（P23 登记侧 / P69 / P70）",
    "e1SyncEntryRowIdentity.spec.ts": "E1 动态行身份行为侧：跨 variant 身份相等、账号派生、删增不复用、按 id 定位（P23 行为侧）",
}

BE_ARGS = [
    "backend/tests/workpaper_sync/test_task47_e_cycle_migration.py",
    "-q",
    "--tb=no",
    "-rf",
    "-p",
    "no:randomly",
]
FE_FILTERS = ["e1SyncEntryRowIdentity"]

MUTATIONS: list[Mutation] = [
    # ═══════════════ be：行身份登记（Property 23 登记侧）═══════════════
    Mutation(
        id="B01",
        side="be",
        path=SLICE,
        kind="replace",
        scope='          "template": "bank-{section}-{group}-acct-{account_no}",',
        offset=1,
        anchor='          "identity_field": "account_no",',
        new='          "identity_field": "row_index",',
        want="test_identity_field_is_account_number",
        why="把行身份字段从账号改成下标 —— Requirement 6.5 明令禁止数组下标作持久化身份。"
        "两张动态表都有这一行，故必须用 scope+offset 相对定位，否则 ANCHOR-MISS",
    ),
    Mutation(
        id="B02",
        side="be",
        path=SLICE,
        kind="replace",
        anchor='          "template": "bank-{section}-{group}-acct-{account_no}",',
        new='          "template": "bank-{section}-{group}-row-{index}",',
        want="test_identity_template_has_no_index_placeholder",
        why="把 id 模板换成 `{index}` 占位 —— 这是 Property 23 的原始缺陷形态。"
        "只断言「模板非空」的判据抓不到它，必须逐个占位符白名单",
    ),
    Mutation(
        id="B03",
        side="be",
        path=SLICE,
        kind="replace",
        scope='          "template": "bank-{section}-{group}-acct-{account_no}",',
        offset=7,
        anchor='        "variant_independent_identity": true',
        new='        "variant_independent_identity": false',
        want="test_identity_is_variant_independent",
        why="声明行身份与 variant 耦合 —— 那正是 E1-3 两版共用持久化键时会让行全部错位的"
        "形态。两张表都有这一行，用 scope+offset 锁到 E1-3 那张",
    ),
    Mutation(
        id="B04",
        side="be",
        path=SLICE,
        kind="replace",
        anchor='        "sha256": "8317e2bac2e57a70778755923332450bd07634e1ff68eb8c14e74d259e58a9ea",',
        new='        "sha256": "8317e2bac2e57a70778755923332450bd07634e1ff68eb8c14e74d259e58a9eb",',
        want="test_frozen_template_digests_match_disk",
        why="改一位 hex —— 模板 digest 判据必须现算比对而不是自比自（Requirement 6.10 "
        "模板漂移 fail closed）。只存 size 的判据抓不到内容漂移",
    ),
    Mutation(
        id="B05",
        side="be",
        path=SLICE,
        kind="replace",
        anchor='        "max_column": 28,',
        new='        "max_column": 41,',
        want="test_variant_column_counts_and_identity_columns_derived_from_source",
        why="把 rmb 版列数改成与 multi 相同 —— 若判据不真读 xlsx，「两个 variant 列集不同」"
        "这条源侧依据就空转，于是「variant 只影响字段集」变成一句无从核实的声明",
    ),
    Mutation(
        id="B06",
        side="be",
        path=SLICE,
        kind="replace",
        anchor='        "has_foreign_currency_columns": false,',
        new='        "has_foreign_currency_columns": true,',
        want="test_foreign_currency_columns_only_in_multi",
        why="声明 rmb 版有原币列 —— 与源模板表头区（rmb 版无「原币币种/期末汇率/原币」"
        "任一 label）矛盾。只断言 JSON 布尔值等于自己是同义反复，必须现扫源模板 label",
    ),
    Mutation(
        id="B07",
        side="be",
        path=SLICE,
        kind="replace",
        anchor='          "C9": "银行账号",',
        new='          "C9": "开户行账户",',
        want="test_variant_column_counts_and_identity_columns_derived_from_source",
        why="改 identity 列标签 —— 「两个 variant 的 identity 列逐字相同」是行身份与 "
        "variant 解耦的源侧依据；判据必须读源 xlsx 单元格而不是比较 JSON 内部两处",
    ),
    # ═══════════════ be：裁决自洽（Requirement 12.1 / 12.8）═══════════════
    Mutation(
        id="B08",
        side="be",
        path=SLICE,
        kind="replace",
        anchor='      "adapter_id": null,',
        new='      "adapter_id": "e1.monetary_fund",',
        want="test_single_capability_implies_all_identity_fields_null",
        why="裁决 single_onlyoffice 却挂 adapter —— 正是「为凑数伪造 contract/adapter」"
        "的形态。裁决与身份字段必须蕴含自洽，否则 single 裁决可以同时声称有 adapter",
    ),
    Mutation(
        id="B09",
        side="be",
        path=SLICE,
        kind="replace",
        anchor='        "verification_state": "UNVERIFIABLE",',
        new='        "verification_state": "VERIFIED",',
        want="test_evidence_is_unverifiable_with_enumerated_reasons",
        why="没跑真实 OO 就标 VERIFIED —— Requirement 12.10 要求 evidence 由服务端从"
        "逐 scenario 实体重算；自填验收态是本 spec 反复点名的假绿入口",
    ),
    Mutation(
        id="B10",
        side="be",
        path=SLICE,
        kind="replace",
        anchor='      "capability": "single_onlyoffice",',
        new='      "capability": "bidirectional",',
        want="test_capability_matches_full_manifest",
        why="slice 单方面把 entry 改成 bidirectional —— capability 必须与 source-backed "
        "全量 manifest 一致，否则 slice 变成第二真源、迁移进度可以自己宣布",
    ),
    Mutation(
        id="B11",
        side="be",
        path=SLICE,
        kind="replace",
        anchor='      "entry_id": "xlsx/gt-e1-monetary-fund",',
        new='      "entry_id": "xlsx/gt-e2-imaginary-fund",',
        want="test_slice_entry_set_equals_manifest_derived_set",
        why="换成一个 manifest 里不存在的 entry —— 判据必须做集合相等（按选取规则现算），"
        "抄一份 id 名单的判据既抓不到凑数也抓不到漏迁",
    ),
    Mutation(
        id="B12",
        side="be",
        path=SLICE,
        kind="replace",
        anchor='        "audit-platform/frontend/src/components/workpaper/composables/useG1DualMode.ts#resolveOoSheetName",',
        new='        "audit-platform/frontend/src/components/workpaper/composables/useG1DualMode.ts#resolveOoSheetNameV2",',
        want="test_bp4_source_refs_point_at_real_symbols",
        why="让阻断项指向一个不存在的符号 —— 阻断项若不与真实符号锁死，重构后它会静静"
        "指向空气，复核者读到的是一条无法验证的「已登记缺陷」",
    ),
    Mutation(
        id="B13",
        side="be",
        path=SLICE,
        kind="replace",
        anchor='        "recalcRow(row,\'multi\') 若无条件由「原币 × fxRate」派生本位币六列，rmb 形态种子恒得 0",',
        new='        "口径不一致时金额会变成 0",',
        want="test_root_cause_chain_records_all_four_links",
        why="把根因链里最关键的一环换成模糊描述 —— 归档 spec 已实测过：措辞准确但断言半径"
        "不足的守卫放行了本缺陷。根因链缺环时后来者会把它当「只是显示问题」",
    ),
    Mutation(
        id="B14",
        side="be",
        path=SLICE,
        kind="replace",
        anchor='      "本 slice 不引用任何 D/G/H/B60 pilot 的 contract_id、definition_bundle、candidate 或 evidence id",',
        new='      "本 slice 复用 d2.receivable_detail 的 contract 作为 E1 的契约",',
        want="test_slice_borrows_no_other_entry_identity",
        why="显式借用 D2 pilot 的契约身份 —— Property 70 的核心禁令。只读 isolation.rule "
        "文本的判据抓不到，必须真在整份 slice 里搜其它 entry 的契约 id",
    ),
    Mutation(
        id="B15",
        side="be",
        path=SLICE,
        kind="replace",
        anchor='    "total_independent": 1,',
        new='    "total_independent": 2,',
        want="test_summary_counters_match_entries",
        why="汇总计数与 entry 数脱钩 —— 迁移进度就是靠这些计数报出去的；计数必须从 entries "
        "现算，不能是人手维护的第二真源",
    ),
    # ═══════════════ be：删除计划（Requirement 12.4）═══════════════
    Mutation(
        id="B16",
        side="be",
        path=PLAN,
        kind="replace",
        anchor='          "inbound_production_reference_count": 0,',
        new='          "inbound_production_reference_count": 1,',
        want="test_delete_justification_is_source_backed",
        why="声称被删文件还有生产消费方却仍标 executed —— 免 Task 45 gate 的唯一依据就是"
        "「入边为 0」，这条一破，删除就变成未经等价性验证的破坏性操作",
    ),
    Mutation(
        id="B17",
        side="be",
        path=PLAN,
        kind="replace",
        anchor='      "audit-platform/frontend/src/components/workpaper/GtG1TradingFinancialAssets.vue"',
        new='      "audit-platform/frontend/src/components/workpaper/GtG9OtherNoncurrentFinancial.vue"',
        want="test_shared_dual_mode_is_preserved_with_both_consumers",
        why="把共享 dual-mode 的消费方登记改错 —— 判据必须现扫宿主 import 求集合；"
        "登记与源码脱节时「删它会不会拆掉别的循环」这个判断就没有依据",
    ),
    Mutation(
        id="B18",
        side="be",
        path=DUAL,
        kind="replace",
        anchor="const STORAGE_PREFIX = 'g1-dual-mode:'",
        new="const STORAGE_PREFIX = 'e1-dual-mode:'",
        want="test_localstorage_collision_verdict_is_derived",
        why="改 localStorage 前缀 —— 「跨循环共用前缀但不冲突」这个结论是从 key 形态"
        "（以 wpId 收尾）推出来的；前缀一改，结论必须重新推导而不是继续沿用",
    ),
    Mutation(
        id="B19",
        side="be",
        path=BANK,
        kind="replace",
        anchor="    if (classifyFxForm(row) === 'base-identity') {",
        new="    if (false) {",
        want="test_zeroing_defect_status_is_backed_by_source",
        why="删掉 multi 分支的形态分派 —— 抹零缺陷本体（无条件由原币派生本位币）。"
        "登记为 FIXED_AND_GUARDED 时，修复点必须真的在 recalcRow 的函数体作用域内",
    ),
    Mutation(
        id="B20",
        side="be",
        path=PREFILL,
        kind="replace",
        anchor="export function buildBankSeedRowsFromAccounts(",
        new="export function buildBankSeedRowsFromAccts(",
        want="test_seed_builders_and_consumers_exist_on_disk",
        why="把 slice 登记的种子构造器改名 —— 「文件存在」不足以证明登记有效；符号改名后"
        "登记表会变成指向空气的第二真源",
    ),
    Mutation(
        id="B21",
        side="be",
        path=HOST,
        kind="insert",
        anchor="import { useG1DualMode } from './composables/useG1DualMode'",
        new="import { useD1DualMode } from './composables/useD1DualMode'",
        want="test_host_still_imports_only_the_shared_dual_mode",
        why="给宿主加第二条 dual-mode import —— Task 45 范式禁止双路并存。判据必须求"
        "import 到的 dual-mode 符号集合，只查「有没有 import 目标那一个」抓不到多出来的",
    ),
    # ═══════════════ fe：行身份行为侧（Property 23 行为侧）═══════════════
    Mutation(
        id="F01",
        side="fe",
        path=PREFILL,
        kind="replace",
        anchor="    const id = uniqueId(`bank-principal-${group}-acct-${key}`, used)",
        new="    const id = uniqueId(`bank-principal-${group}-${variant}-acct-${key}`, used)",
        want="两个 variant 的种子 id 序列逐项相等",
        why="把 variant 编进行身份 —— 于是「仅人民币」种下的行在「人民币及外币」Tab 里"
        "全部认不出来，两版共用持久化键会让行翻倍或错位。只测金额守恒的守卫放行这一形态",
    ),
    Mutation(
        id="F02",
        side="fe",
        path=PREFILL,
        kind="replace",
        anchor="    const id = uniqueId(`bank-principal-${group}-acct-${key}`, used)",
        new="    const id = uniqueId(String(used.size), used)",
        want="id 由账号派生",
        why="把行身份换成「已用条数」= 事实上的数组下标 —— Requirement 6.5 的原始禁令。"
        "单次往返内下标自洽，所以只有跨删/增/重排的身份判据能抓到",
    ),
    Mutation(
        id="F03",
        side="fe",
        path=PREFILL,
        kind="replace",
        anchor="      id: uniqueId(`acct-a-${key}`, used),",
        new="      id: uniqueId(`bank-principal-institution-acct-${key}`, used),",
        want="与 E1-3 不撞键",
        why="让 E1-10 与 E1-3 共用 id 命名空间 —— 两张表的种子会互相覆盖（平台已登记的"
        "「行 id 撞键让两种口径互相覆盖」形态）",
    ),
    Mutation(
        id="F04",
        side="fe",
        path=BANK,
        kind="replace",
        anchor="    rows.value = rows.value.filter(row => row.id !== rowId)",
        new="    rows.value = rows.value.slice(1)",
        want="删中间一行再新增，新行 id 不等于任何已删 id",
        why="删除改成按位置切首行 —— 用户点第 2 行的删除按钮却删掉第 1 行。"
        "断言「行数少了 1」的判据会放行它，必须断言「被删的那个 id 不在了」",
    ),
    Mutation(
        id="F05",
        side="fe",
        path=BANK,
        kind="replace",
        anchor="    const index = rows.value.findIndex(row => row.id === rowId)",
        new="    const index = 0",
        want="updateCell 按 id 定位而非下标",
        why="改格改成恒改第一行 —— 删行后下标与 id 不再对应，审计师在末行录的数会落到"
        "首行。必须同时断言「目标行改了」与「其它行没被改」",
    ),
    Mutation(
        id="F06",
        side="fe",
        path=BANK,
        kind="replace",
        anchor="  return `bank-${section}-${group}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`",
        new="  return '3'",
        want="新增行的 id 不是「当前行数」这类下标派生值",
        why="新增行的 id 变成「当前行数」—— 再删再增就会复用已删身份（Property 23 原文"
        "禁止的「旧 row_uuid 复用」）。身份宽度与非下标性都要断言",
    ),
    Mutation(
        id="F07",
        side="fe",
        path=BANK,
        kind="replace",
        anchor="    if (classifyFxForm(row) === 'base-identity') {",
        new="    if (false) {",
        want="rmb 种子被 multi Tab 消费时，本位币账户的身份与金额同时保住",
        why="恢复抹零缺陷本体 —— 本条是「防 variant 切换抹零」在身份守卫里的回归支点："
        "身份保住而金额被抹成 0 时，界面显示的是一排 `-`，比取不到更坏",
    ),
    Mutation(
        id="F08",
        side="fe",
        path=BANK,
        kind="replace",
        anchor="  watch(variant, next => { rows.value = rows.value.map(row => recalcRow(row, next)) })",
        new="  watch(variant, next => { rows.value = rows.value.map((row, i) => recalcRow({ ...row, id: String(i) }, next)) })",
        want="运行时切 variant 后行 id 不变",
        why="切 variant 时按下标重建身份 —— 与平台已登记的「resolveRestrictedRows 按数组"
        "下标重算 id 覆盖稳定序号」同型：删后再增会复用已删序号、历史备注串到新行",
    ),
    Mutation(
        id="F09",
        side="fe",
        path=G1LABELS,
        kind="replace",
        anchor="  if (/调整分录/.test(sheetName)) return 'G1-3'",
        new="  if (/调整分录汇总表XX/.test(sheetName)) return 'G1-3'",
        want="extractG1SheetCode 把 E1-5",
        why="BP-4 的 characterization 必须可 falsify：改掉那条分支后本节应打红，"
        "提示复核者「缺陷已变化，去更新 slice 的 blocking_preconditions[BP-4]」。"
        "characterization 若不可 falsify，就退化成把错值当基线锁死",
    ),
]


if __name__ == "__main__":
    raise SystemExit(
        run_cli(
            mutations=MUTATIONS,
            guard_files=GUARD_FILES,
            repo=REPO,
            description="Task 47 E 循环 slice/deletion plan 与 E1 行身份守卫变异检验",
            backend_args=BE_ARGS,
            frontend_filters=FE_FILTERS,
            frontend_dir=FRONTEND,
            vitest_json=_FE_JSON,
        )
    )
