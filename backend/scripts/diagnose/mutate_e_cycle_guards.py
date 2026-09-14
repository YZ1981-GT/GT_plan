"""E 循环守卫变异检验（spec e-cycle-extraction-formula-and-disclosure-completion / Task 20）。

## 为什么需要它

守卫全绿只证明「当前代码没触发断言」，**不证明断言有效**。memory 记录的假绿三源
（additive 注入即死代码 / grep 式守卫只查字符串存在 / 守卫把错值当基线锁死）都表现为
「全绿」。唯一可靠的反证是**故意把生产代码改坏，看守卫是否打红**。

## 判定四态（只看失败测试名集合的差集，不看退出码）

- ``RED``          变异后新增失败集合 **非空且包含** 声明的 ``want`` → 守卫有效
- ``WRONG-TEST``   新增失败集合非空但不含 ``want`` → 污染残留或锚点落在错误位置
- ``GREEN``        新增失败集合为空 → **守卫缺陷**，该属性没有真正被锁死
- ``ANCHOR-MISS``  锚点命中数 != 1（或行号消歧后逐字不符）→ **本脚本缺陷**，非代码问题

退出码不可作判据：pytest 因收集错误也会非零，vitest 有噪声 warning 亦然。

## 硬约束（踩坑记录）

- 锚点**行级唯一且不跨行**。工作树是 CRLF，含 ``\\n`` 的锚点必然 MISS。
- 同一锚点多处出现时用**行号消歧 + 该行逐字相等 + hits==1** 三重断言。
- 还原写在 ``finally``：任何异常都不能留下污染文件，否则后续变异全变 WRONG-TEST。
- 还原后用 **md5 与变异前逐字相同** 核验，不信「写回成功」。
- 全程 bytes→utf-8 解码、``splitlines(keepends=True)`` 保留行尾，写回不改 CRLF。

用法::

    python backend/scripts/diagnose/mutate_e_cycle_guards.py --list
    python backend/scripts/diagnose/mutate_e_cycle_guards.py --check-anchors
    python backend/scripts/diagnose/mutate_e_cycle_guards.py --run M01,M02
    python backend/scripts/diagnose/mutate_e_cycle_guards.py --run be
    python backend/scripts/diagnose/mutate_e_cycle_guards.py --restore
"""
from __future__ import annotations

import sys
from pathlib import Path

# 共享件位于 backend/scripts/ 下，两个变异脚本目录（check/ 与 diagnose/）都从这里取。
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _mutation_kit import Mutation as Mut  # noqa: E402  —— 字段与原 Mut 逐一对齐
from _mutation_kit import run_cli  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
FRONTEND = REPO / "audit-platform" / "frontend"
BAK_SUFFIX = ".mutbak"

# ─── 冻结基线（本会话亲测，见 tasks.md Task 20 / Task 22 Notes）──────────────────
BASELINE_BE_PASSED = 368
#: Task 22 修 Property 28 端到端缺陷时，`e1RestrictedSeq.spec.ts` 新增 5 条断言
#: （46 → 51 例），全量前端随之 563 → 568。改这个常量必须同时说明来源，
#: 否则下一轮跑变异只会看到一行 WARN 而不知道涨的是哪几条。
BASELINE_FE_PASSED = 568

BE_PYTEST_ARGS = [
    "backend/tests/four_table",
    "-k",
    "e1 or e_cycle",
    "-q",
    "--tb=no",
    "-rf",
]

_FE_JSON = REPO / "backend" / "scripts" / "diagnose" / "_wip_mut_fe.json"

#: vitest 的 ``fullName`` → 守卫文件名。每次 :func:`run_frontend` 重建。
#: 后端不需要（nodeid 首段就是文件名）。
_FE_NAME2FILE: dict[str, str] = {}

#: 本 spec 创建或扩展的守卫文件全集（覆盖面判据的分母）。
#:
#: 🔴 **为什么要显式列出**：2026-08-10 复核时，21 条变异全 RED、但按文件逐一核对后发现
#: **7 个前端守卫文件从未被任何变异打红**（e1HostSeedWiring / e1SourcePanelWiring /
#: e1CurrencyScope / e1FxNoteSectionMap / e1RestrictedL2 / e1NegativeBalance /
#: e1NoteTextsAndPayload）。「20 条变异全红」与「全部守卫都被反证过」是**两件事** ——
#: 前者按 design 清单计数，后者要按守卫文件计数。M22~M29 即为补齐这条缺口而加。
#: 报告末尾会打印未被覆盖的文件；新增守卫文件时必须同时加一条变异，否则这里会显示欠账。
SPEC_GUARD_FILES: dict[str, str] = {
    # 后端
    "test_e1_bank_accounts.py": "Task 4 新建",
    "test_e1_bank_accounts_live.py": "Task 1 新建（连库）",
    "test_e1_preset_coverage.py": "Task 2 新建",
    "test_e1_render_account_prefill.py": "Task 5 新建",
    "test_e1_restricted_buckets.py": "Task 13 扩展",
    "test_note_e1_structure.py": "Task 3 扩展",
    # 前端
    "e1BankAccountPrefill.spec.ts": "Task 7 新建",
    "e1CurrencyScope.spec.ts": "Task 15 / 23 诚实改写",
    "e1FxNoteSectionMap.spec.ts": "Task 13 扩展",
    "e1HostSeedWiring.spec.ts": "Task 8 新建",
    "e1MainRowPrefill.spec.ts": "Task 24 新建",
    "e1NegativeBalance.spec.ts": "Task 17 扩展",
    "e1NoteSubtableContract.spec.ts": "Task 16 条件表语义（防回退）",
    "e1NoteTextsAndPayload.spec.ts": "Task 15 扩展",
    "e1RestrictedL2.spec.ts": "Task 14 新建（L2 逐户归集 + L1/L2 勾稽）",
    "e1RestrictedSeq.spec.ts": "Task 16 / 22 新建",
    "e1SourcePanelWiring.spec.ts": "Task 9 新建",
}


# ─── 变异声明 ────────────────────────────────────────────────────────────────


BE_ACCOUNTS = "backend/app/services/four_table/e1_bank_accounts.py"
BE_BUCKETS = "backend/app/services/four_table/e1_restricted_buckets.py"
BE_TPL_SOE = "backend/data/note_template_soe.json"
FIX_ORPHAN = "backend/scripts/fix/fix_e1_orphan_sheet_presets.py"
FIX_PRESETS = "backend/scripts/fix/fix_e1_prefill_presets.py"
FE_BANK = "audit-platform/frontend/src/components/workpaper/composables/e1BankAccountPrefill.ts"
FE_MAIN = "audit-platform/frontend/src/components/workpaper/composables/e1MainRowPrefill.ts"
FE_NOTEMAP = "audit-platform/frontend/src/components/workpaper/composables/e1NoteSectionMap.ts"
FE_RESTRICTED = (
    "audit-platform/frontend/src/components/workpaper/composables/e1RestrictedScope.ts"
)
FE_FXMAP = "audit-platform/frontend/src/components/workpaper/composables/e1FxNoteSectionMap.ts"
FE_CONSIST = (
    "audit-platform/frontend/src/components/workpaper/composables/e1DisclosureConsistency.ts"
)
FE_NEGATIVE = (
    "audit-platform/frontend/src/components/workpaper/composables/e1NegativeBalance.ts"
)
FE_DISCSCOPE = (
    "audit-platform/frontend/src/components/workpaper/composables/e1DisclosureScope.ts"
)
FE_HOST = "audit-platform/frontend/src/components/workpaper/GtE1MonetaryFund.vue"
FE_PANEL = "audit-platform/frontend/src/components/workpaper/e1/E1FourTableSourcePanel.vue"

MUTATIONS: list[Mut] = [
    Mut(
        id="M01",
        side="be",
        path=BE_ACCOUNTS,
        kind="replace",
        anchor="        active = await get_active_filter(",
        # 保留续行的参数以维持语法合法：参数被丢进一个吞参 lambda。
        new="        active = TbAuxBalance.is_deleted == False; _mut = (lambda *a, **k: None)(",
        want="test_no_naive_is_deleted_filter",
        why="裸 is_deleted 过滤器跨 dataset 取数 → 账户合计翻倍（真实库实证：0ec33ac9 的 1002 "
        "裸查 23 户/9,406,222.82 vs active 22 户/4,703,056.26，几乎正好翻倍）。"
        "🔴 want 锚在源码级判据上，但连库侧同样会红 —— 实测新增失败含 "
        "test_e1_bank_accounts_live.py::TestImplementationMatchesSqlBaseline::"
        "test_fetch_result_ties_to_sql_baseline。注意**不是** "
        "test_active_sum_is_the_one_tying_to_tb_balance（那条是「类 A 独立 SQL」自检，"
        "自带 active/裸查两套查询、不调被测实现，故任何变异下都恒绿 —— 它证明的是"
        "「dataset 过滤有必要」这个数据事实，不是「实现用了它」）",
    ),
    Mut(
        id="M02",
        side="be",
        path=BE_ACCOUNTS,
        kind="replace",
        anchor="        key = (code, dims.account_no)",
        new="        key = (code, object())",
        want="test_same_account_two_rows_are_summed",
        why="去掉按账号聚合 → 同账号多行不再合并，账户数虚增",
    ),
    Mut(
        id="M03",
        side="be",
        path=BE_ACCOUNTS,
        kind="replace",
        anchor="        return 0.0",
        line=157,
        new='        return float("nan")  # mut: NULL 不再归零',
        want="test_null_amounts_are_coalesced_to_zero",
        why="NULL 归成 NaN 而非 0 → COALESCE 语义失效。🔴 不能只删 `if v is None` 分支："
        "下方 `except (TypeError, ValueError): return 0.0` 会把 float(None) 的 TypeError "
        "吞成 0.0，删了行为不变 = 无效变异（首轮实测 GREEN 即此因）",
    ),
    Mut(
        id="M04",
        side="be",
        path=BE_ACCOUNTS,
        kind="replace",
        anchor='        account_no=str(aux_name or "").strip(), bank_name="", parsed_level=3',
        new='        account_no=str(aux_name or "").strip(), bank_name=str(aux_name or "").strip(), parsed_level=3',
        want="test_bank_name_is_never_the_account_no",
        why="解析失败时把账号臆造成银行名 → level 3 降级断言必红",
    ),
    Mut(
        id="M05",
        side="be",
        path=BE_ACCOUNTS,
        kind="replace",
        anchor="            out.unassigned.append(row)",
        new='            out.by_slot.setdefault("bank", []).append(row)',
        want="test_unrelated_code_goes_to_unassigned_not_dropped",
        why="未归属账户混进 bank 槽 → 归属断言必红（且勾稽被污染）",
    ),
    Mut(
        id="M06",
        side="be",
        path=BE_ACCOUNTS,
        kind="replace",
        anchor="        diff = round(acc_sum - leaf_sum, 2)",
        new="        diff = 0.0  # mut: 自动修正数据而非如实暴露",
        want="test_mismatch_is_exposed_not_corrected",
        why="勾稽差额恒 0 → 不一致被掩盖，如实暴露断言必红",
    ),
    Mut(
        id="M07",
        side="be",
        path=BE_BUCKETS,
        kind="move",
        anchor='        key="statutory_reserve",',
        anchor2='        key="other",',
        block_open="E1RestrictedBucket(",
        want="test_declared_before_fallback_bucket",
        why="新受限桶挪到兜底桶 other 之后 → 声明序即优先级，分类失效",
    ),
    Mut(
        id="M08",
        side="be",
        path=BE_BUCKETS,
        kind="replace",
        anchor='        keywords=("法定存款准备金", "存款准备金", "法定准备金", "备付金"),',
        new='        keywords=("法定存款准备金", "存款准备金", "法定准备金", "备付金", "保证金"),',
        want="test_classification_unchanged_by_new_bucket",
        why="新桶关键词加「保证金」→ 抢走既有三类保证金，零回归断言必红",
    ),
    Mut(
        id="M09",
        side="be",
        path=BE_TPL_SOE,
        kind="replace",
        anchor='              "label": "库存现金",',
        new='              "label": "现金",',
        want="test_template_soe_main_matches_docx",
        why="soe 主表首行改回底稿字面「现金」→ docx 三向比对必红",
    ),
    Mut(
        id="M10",
        side="be",
        path=BE_TPL_SOE,
        kind="replace",
        anchor='              "report_row_code": "BS-041",',
        new='              "report_row_code": "BS-031",',
        want="test_row_code_row_name_matches_segment_label",
        why="短期借款段 row_code 改回 BS-031（实为使用权资产）→ report_config 对账必红",
    ),
    Mut(
        id="M11",
        side="be",
        path=FIX_ORPHAN,
        kind="replace",
        anchor='            print(f"[OK] E1 orphan sheet presets: 0 欠账（{len(E1_NEW_BLOCKS)} blocks 已全部就位）")',
        new='            print(f"\\u2705 E1 orphan sheet presets: 0 欠账（{len(E1_NEW_BLOCKS)} blocks 已全部就位）")',
        want="test_print_literals_are_gbk_encodable",
        why="print 加回 GBK 不可编码字符 → 非 ASCII 守卫必红（真实崩点在写盘之后）",
    ),
    Mut(
        id="M13",
        side="be",
        path=BE_ACCOUNTS,
        kind="replace",
        anchor="        active = await get_active_filter(",
        new="        active = get_active_filter(",
        want="test_get_active_filter_is_awaited",
        why="去掉 await → 拿到 coroutine，Property 39 源码断言必红",
    ),
    Mut(
        id="M14",
        side="be",
        path=BE_BUCKETS,
        kind="replace",
        anchor='            "displayOrder": display_order_of(b.key),',
        new='            "displayOrder": E1_RESTRICTED_BUCKETS.index(b),',
        want="test_payload_carries_display_order",
        why="展示序回退成声明序索引 → Property 36 展示序红、分类保持绿（两序必须分离）。"
        "🔴 want 锚在载荷断言上：`test_display_order_matches_docx_six_categories` 直接调 "
        "`display_order_of()` 绕过载荷，本变异只改 `bucket_defs_payload` 故它不红",
    ),
    Mut(
        id="M15",
        side="be",
        path=BE_BUCKETS,
        kind="swap",
        anchor='        key="overseas",',
        anchor2='        key="pledged_deposit",',
        block_open="E1RestrictedBucket(",
        want="test_classification",
        why="互换 overseas ↔ pledged_deposit 声明序 → `境外冻结存款` 被质押桶抢走，分类红、"
        "displayOrder 保持绿（反向证明两序确已分离）。🔴 不能换 letter_of_credit ↔ "
        "bank_acceptance：两桶关键词（信用证 / 银行承兑）无交集，换序不改变任何分类结果 = "
        "无效变异（首轮实测 GREEN 即此因）。本桶对的敏感性由守卫自带的 "
        "`test_reverse_selfcheck_overseas_after_pledged_breaks` 指明",
    ),
    Mut(
        id="M20",
        side="be",
        path=FIX_PRESETS,
        kind="insert",
        anchor="NON_DATA_SHEETS: frozenset[str] = frozenset({",
        new='    "这张表不存在E1-99",\n',
        want="test_non_data_whitelist_is_effective",
        why="白名单混入不存在的 sheet 名 → 命中数守卫必红（白名单成了免责声明）",
    ),
    # ── 前端 ──
    Mut(
        id="M12",
        side="fe",
        path=FE_BANK,
        kind="replace",
        anchor="    const id = uniqueId(`bank-principal-${group}-acct-${key}`, used)",
        new="    const id = uniqueId(`bank-principal-${group}-ft-${key}`, used)",
        want="E1-3：账户级 id 与叶子口径 id 集合无交集",
        why="账户级行 id 前缀改成与叶子口径相同 → 撞 key，宿主渲染时相互覆盖",
    ),
    Mut(
        id="M16",
        side="fe",
        path=FE_MAIN,
        kind="delete",
        anchor="  finance_co: 'finance_co',",
        want="E1_PREFILL_ROW_KEYS 与 E1_MAIN_ROW_SLOTS 的键集完全一致且字典序冻结",
        why="删掉 finance_co 槽声明 → e1MainRowSlotKey 返空串，整条预填链静默断开",
    ),
    Mut(
        id="M17",
        side="fe",
        path=FE_MAIN,
        kind="delete",
        anchor="      if (isBlankPeriod(row, period)) continue",
        want="三值全 0 的行不产生写入（保持空白而非 0）",
        why="三值全 0 时也写键 → 「无此科目」与「余额为 0」不可区分",
    ),
    Mut(
        id="M18",
        side="fe",
        path=FE_NOTEMAP,
        kind="insert",
        anchor="const RESTRICTED_COLUMNS_LISTED: ColumnDef[] = [",
        new="  { key: 'reason', label: '受限原因' },\n",
        want="②表不推「受限原因」列",
        why="给②表加第 4 列 reason → 源模板只有 3 列，多出的是孤儿列",
    ),
    Mut(
        id="M19",
        side="fe",
        path=FE_BANK,
        kind="replace",
        anchor="      base.fxRate = 0",
        new="      base.fxRate = 1",
        want="非本位币账户原币与汇率一律留 0 且 note 有提示",
        why="外币账户汇率由本位币反推填 1 → 臆造汇率，Property 34「都不带值」必红",
    ),
    Mut(
        id="M21",
        side="fe",
        path=FE_RESTRICTED,
        kind="replace",
        anchor="      id: idByBucket.get(bucketKey) ?? e1RestrictedRowId(bucketKey, i),",
        new="      id: e1RestrictedRowId(bucketKey, i),",
        want="删除后再新增",
        why="🔴 本条对应 Task 22 浏览器实测抓到的真实缺陷（Property 28 端到端失效）："
        "resolveRestrictedRows 末尾按**数组下标 i** 重算全部行 id，把 addRestrictedRow "
        "用 nextRestrictedSeq 算好的稳定序号覆盖掉 ⇒ 删掉 custom_甲_2 再新增 custom_乙，"
        "落库 id 又是 `_2`（复用已删序号），按 row id 索引的历史 reason/金额串到新类别上。"
        "真实库实测（soe 2aa00f57）：计数器已正确涨到 3，落库 id 仍是 `_2`。"
        "原 42 例守卫全绿而缺陷仍在 —— 因为它们只测 nextRestrictedSeq 纯函数返回值，"
        "没有一条断言把「纯函数结果」串到「resolveRestrictedRows 输出」，"
        "属 memory 假绿第一源『additive 注入即死代码』的变体：注入点在、消费方在、结果被覆盖",
    ),
    # ── 覆盖面补齐（2026-08-10 复核发现）───────────────────────────────────────
    # design.md Testing Strategy 那 20 条 + M21 合计 21 条，全部 RED；但按
    # 「变异脚本 targets 必须覆盖**本 spec 全部守卫文件**」逐文件核对后发现
    # **7 个前端守卫文件从未被任何变异打红** —— 它们全绿属未经反证的绿：
    #   e1HostSeedWiring / e1SourcePanelWiring / e1CurrencyScope /
    #   e1FxNoteSectionMap / e1RestrictedL2(Task 14 的 L2 勾稽项) /
    #   e1NegativeBalance / e1NoteTextsAndPayload
    # M22~M29 逐一补上（每条只打红「它自己那个文件」，故也顺带证明这些守卫互不重叠）。
    Mut(
        id="M22",
        side="fe",
        path=FE_HOST,
        kind="replace",
        anchor="  const bankSeed = buildBankSeedRowsFromAccounts(ap, e13Variant.value) ?? buildBankSeedRows(p)",
        new="  const bankSeed = buildBankSeedRows(p)",
        want="账户级优先 + 叶子兜底",
        tags=("coverage",),
        why="宿主种子化退回叶子口径独占（删掉账户级优先链）→ Task 8 的三段链守卫必红。"
        "此前 21 条变异无一触及 `GtE1MonetaryFund.vue`，`e1HostSeedWiring.spec.ts` 的 25 例"
        "属未经反证的绿",
    ),
    Mut(
        id="M23",
        side="fe",
        path=FE_PANEL,
        kind="delete",
        anchor="  accounts?: E1AccountPrefill",
        want="accounts prop 已声明且宿主已传",
        tags=("coverage",),
        why="溯源面板删掉 accounts prop 声明 → 宿主仍传但面板收不到（Vue 对未知属性不报错，"
        "Volar/vitest/Vite 四层全绿而整块静默不渲染，平台已踩两次）⇒ prop 键集交叉锁死必红",
    ),
    Mut(
        id="M24",
        side="fe",
        path=FE_RESTRICTED,
        kind="replace",
        anchor="    bucketDefs.map((d, i) => [d.key, Number.isFinite(d.displayOrder) ? (d.displayOrder as number) : i]),",
        new="    bucketDefs.map((d, i) => [d.key, i]),",
        want="displayOrder 排序键与后端桶数量对齐",
        tags=("coverage",),
        why="🔴 M14 的**前端对侧** —— M14 只改后端载荷、跑 pytest，前端 `bucketDisplayOrderMap` "
        "退回数组下标（= Task 23 修的那个既存缺陷形态）此前无任何变异覆盖。展示序必红、"
        "分类语义须保持绿（两序分离在前端也成立）",
    ),
    Mut(
        id="M25",
        side="fe",
        path=FE_FXMAP,
        kind="replace",
        anchor=" * | 短期借款 | `BS-041` | K |",
        new=" * | 短期借款 | `BS-031` | K |",
        want="段归属表里的 row_code 必须与模板段序列一致",
        tags=("coverage",),
        why="段归属表（给他循环看「谁负责哪一段」的跨循环契约，Task 13 改的正是它）记回 "
        "BS-031 → 与模板段序列交叉锁死必红。记错的后果是 K/L/D2 按错码声明 `_row_scope` → "
        "服务端 fail-closed 整表跳过写入（表现为「推了但没进附注」）",
    ),
    Mut(
        id="M26",
        side="fe",
        path=FE_CONSIST,
        kind="delete",
        anchor="  pushL2Check('期末', rstEnd, nz(input.restrictedL2Ending))",
        want="引擎确实产出该条目",
        tags=("coverage",),
        why="删掉 L1 vs L2 期末勾稽的调用点（Task 14 新增的勾稽项）→ 闭包定义在、调用点没了 = "
        "典型 dead output 形态。此前 M18 只是**顺带**打红 e1RestrictedL2.spec.ts 的列数断言，"
        "L2 勾稽项本身无专属变异",
    ),
    Mut(
        id="M27",
        side="fe",
        path=FE_NEGATIVE,
        kind="replace",
        anchor="        closing: num(r?.closing),",
        new="        closing: Math.abs(num(r?.closing)),",
        want="负余额原样返回，不取绝对值",
        tags=("coverage",),
        why="负余额取值路径套 abs（Property 27 禁止）→ 实测 a7fc75e5 的 −297,771,168.89 会被"
        "翻正，勾稽从 0 变两倍。Task 17 的守卫此前无变异覆盖",
    ),
    Mut(
        id="M28",
        side="fe",
        path=FE_DISCSCOPE,
        kind="delete",
        anchor="    noteLabel: '库存现金',",
        want="载荷首行标签",
        tags=("coverage",),
        why="删掉 soe 主表首行的 `noteLabel` 双口径桥（Task 15 的核心改动）→ 附注载荷首行退回"
        "底稿字面「现金」，与 note_template_soe.json 八、1 不一致。后端侧由 M09 覆盖的是模板，"
        "**前端投影链此前无变异**",
    ),
    Mut(
        id="M29",
        side="fe",
        path=BE_TPL_SOE,
        kind="replace",
        anchor='              "report_row_code": "BS-041",',
        new='              "report_row_code": "BS-031",',
        want="soe 短期借款段 row_code 是 BS-041",
        tags=("coverage",),
        why="🔴 M10 的**前端对侧**（同一锚点、跑 vitest）—— 验证同一份模板数据缺陷在前端也被"
        "锁死（同 M13「源码 + 连库两处同时红」的要求）。只后端红说明前端把模板当可信输入",
    ),
]




# ─── CLI（实现全部来自 `_mutation_kit`，见该包 docstring）──────────────────────
#
# 迁移自本脚本原有的 ~490 行自带实现（md5/find_anchor/apply_mutation/run_backend/
# run_frontend/check_anchors/run_one/main）。共享件在此基础上多四项能力：
#   ① 声明期校验对所有子命令无条件生效（原先只在定位期查换行）
#   ② `guard_files` 是必填关键字参数，「没有分母」在签名层面不可能
#   ③ `--list` 不只打印，还校验锚点唯一命中 / 目标文件存在 / want 可定位
#   ④ `Mutation.scope_check` 作用域自证，落在作用域外判 ANCHOR-MISS 而非 GREEN

if __name__ == "__main__":
    raise SystemExit(
        run_cli(
            mutations=MUTATIONS,
            guard_files=SPEC_GUARD_FILES,
            repo=REPO,
            description="E 循环守卫变异检验",
            backend_args=BE_PYTEST_ARGS,
            frontend_filters=["e1", "E1"],
            frontend_dir=FRONTEND,
            vitest_json=_FE_JSON,
            baseline_backend_passed=BASELINE_BE_PASSED,
            baseline_frontend_passed=BASELINE_FE_PASSED,
        )
    )
