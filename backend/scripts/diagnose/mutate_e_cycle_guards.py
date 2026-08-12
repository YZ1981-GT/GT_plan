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

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

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


@dataclass
class Mut:
    """一条变异。

    ``kind`` 取值：

    - ``replace``  单行整行替换（``old`` 是**去掉行尾**后的整行文本）
    - ``delete``   删除单行
    - ``insert``   在锚点行**之后**插入 ``new``（可多行，缩进自带）
    - ``swap``     交换 ``anchor`` 与 ``anchor2`` 各自所属的括号块
    - ``move``     把 ``anchor`` 所属块移到 ``anchor2`` 所属块**之后**
    """

    id: str
    side: str  # be | fe
    path: str
    kind: str
    anchor: str
    want: str
    why: str
    new: str = ""
    anchor2: str = ""
    line: int = 0  # 1-based；仅当 anchor 多处命中时用于消歧
    block_open: str = ""  # swap/move 定位块首的标记
    tags: tuple[str, ...] = field(default_factory=tuple)

    @property
    def abspath(self) -> Path:
        return REPO / self.path


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


# ─── 文件读写（bytes → utf-8，保留 CRLF）────────────────────────────────────────


def md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def read_lines(path: Path) -> list[str]:
    return path.read_bytes().decode("utf-8").splitlines(keepends=True)


def write_lines(path: Path, lines: list[str]) -> None:
    path.write_bytes("".join(lines).encode("utf-8"))


def eol_of(line: str) -> str:
    for e in ("\r\n", "\n", "\r"):
        if line.endswith(e):
            return e
    return ""


def strip_eol(line: str) -> str:
    e = eol_of(line)
    return line[: len(line) - len(e)] if e else line


class AnchorMiss(RuntimeError):
    """锚点命中数 != 1，或行号消歧后逐字不符 —— 本脚本缺陷，不是生产代码问题。"""


def find_anchor(lines: list[str], anchor: str, want_line: int = 0) -> int:
    """返回锚点行下标（0-based）。命中必须唯一，否则抛 :class:`AnchorMiss`。"""
    if "\n" in anchor or "\r" in anchor:
        raise AnchorMiss("锚点含换行 —— CRLF 工作树下必然 MISS，改用单行锚点")
    hits = [i for i, ln in enumerate(lines) if strip_eol(ln) == anchor]
    if want_line:
        idx = want_line - 1
        if not (0 <= idx < len(lines)):
            raise AnchorMiss(f"消歧行号 {want_line} 越界（文件 {len(lines)} 行）")
        if strip_eol(lines[idx]) != anchor:
            raise AnchorMiss(
                f"消歧行号 {want_line} 内容不符\n  期望 {anchor!r}\n  实为 {strip_eol(lines[idx])!r}"
            )
        return idx
    if len(hits) != 1:
        preview = "; ".join(str(h + 1) for h in hits[:8])
        raise AnchorMiss(f"锚点命中 {len(hits)} 次（应为 1），行号：{preview or '无'}\n  {anchor!r}")
    return hits[0]


_STR_RE = re.compile(r'"[^"\\]*(?:\\.[^"\\]*)*"|\'[^\'\\]*(?:\\.[^\'\\]*)*\'')


def _paren_delta(line: str) -> int:
    """计算一行的括号净增量。**先剥字符串** —— ``source_ref="…(国企)…"`` 会骗到计数。"""
    bare = _STR_RE.sub('""', strip_eol(line))
    return bare.count("(") - bare.count(")")


def block_range(lines: list[str], anchor_idx: int, block_open: str) -> tuple[int, int]:
    """由块内锚点行反查整块行区间 ``[start, end)``（含尾随逗号行）。"""
    start = -1
    for i in range(anchor_idx, -1, -1):
        if block_open in lines[i]:
            start = i
            break
    if start < 0:
        raise AnchorMiss(f"锚点上方未找到块首标记 {block_open!r}")
    depth = 0
    for i in range(start, len(lines)):
        depth += _paren_delta(lines[i])
        if depth <= 0:
            return start, i + 1
    raise AnchorMiss("块括号未闭合 —— 计数被字符串或注释干扰")


# ─── 变异应用 ────────────────────────────────────────────────────────────────


def apply_mutation(m: Mut) -> None:
    lines = read_lines(m.abspath)
    if m.kind == "replace":
        i = find_anchor(lines, m.anchor, m.line)
        lines[i] = m.new + eol_of(lines[i])
    elif m.kind == "delete":
        i = find_anchor(lines, m.anchor, m.line)
        del lines[i]
    elif m.kind == "insert":
        i = find_anchor(lines, m.anchor, m.line)
        eol = eol_of(lines[i]) or "\n"
        payload = [s + eol for s in m.new.rstrip("\n").split("\n")]
        lines[i + 1 : i + 1] = payload
    elif m.kind in ("swap", "move"):
        ia = find_anchor(lines, m.anchor, m.line)
        ib = find_anchor(lines, m.anchor2)
        a0, a1 = block_range(lines, ia, m.block_open)
        b0, b1 = block_range(lines, ib, m.block_open)
        if a0 == b0:
            raise AnchorMiss("两个锚点落在同一块内")
        blk_a, blk_b = lines[a0:a1], lines[b0:b1]
        if m.kind == "swap":
            if a0 < b0:
                lines = lines[:a0] + blk_b + lines[a1:b0] + blk_a + lines[b1:]
            else:
                lines = lines[:b0] + blk_a + lines[b1:a0] + blk_b + lines[a1:]
        else:  # move: blk_a 挪到 blk_b 之后
            if a0 < b0:
                lines = lines[:a0] + lines[a1:b1] + blk_a + lines[b1:]
            else:
                lines = lines[:b0] + blk_b + blk_a + lines[b1:a0] + lines[a1:]
    else:
        raise AnchorMiss(f"未知 kind：{m.kind}")
    write_lines(m.abspath, lines)


# ─── 测试执行与失败名收集 ──────────────────────────────────────────────────────

_FAILED_RE = re.compile(r"^FAILED\s+(\S+)", re.MULTILINE)
_ERROR_RE = re.compile(r"^ERROR\s+(\S+)", re.MULTILINE)


def _env() -> dict[str, str]:
    e = dict(os.environ)
    e["PYTHONIOENCODING"] = "utf-8"
    e["PYTHONUTF8"] = "1"
    return e


def _short_nodeid(nodeid: str) -> str:
    """``tests/four_table/test_x.py::TestY::test_z`` → ``test_x.py::TestY::test_z``。

    🔴 不能只取末段 —— ``test_strip_comments_is_not_a_noop`` 在
    ``test_e1_bank_accounts.py`` 与 ``test_e1_render_account_prefill.py`` 两处同名，
    只取末段会把两条不同测试折叠成一条，差集判定随之失真。
    """
    parts = nodeid.split("::")
    parts[0] = parts[0].replace("\\", "/").rsplit("/", 1)[-1]
    return "::".join(parts)


def run_backend() -> tuple[set[str], str]:
    """跑后端守卫，返回 ``(失败测试名集合, 摘要行)``。名字保留 ``文件::类::方法``。"""
    p = subprocess.run(
        [sys.executable, "-m", "pytest", *BE_PYTEST_ARGS],
        cwd=REPO,
        env=_env(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=1800,
    )
    out = (p.stdout or "") + (p.stderr or "")
    names: set[str] = set()
    for nodeid in _FAILED_RE.findall(out) + _ERROR_RE.findall(out):
        names.add(_short_nodeid(nodeid))
    tail = [ln for ln in out.splitlines() if re.search(r"\d+ (passed|failed|error)", ln)]
    return names, (tail[-1].strip() if tail else f"rc={p.returncode} 无摘要行")


def run_frontend() -> tuple[set[str], str]:
    """跑前端守卫。用 JSON reporter 收 ``assertionResults[].status == 'failed'``。

    🔴 不解析 stdout 的 ``FAIL`` 行 —— 长中文标题会折行，正则抓不全。
    """
    if _FE_JSON.exists():
        _FE_JSON.unlink()
    # 🔴 必须走 `cmd /c "<单串>"`。实测 `subprocess.run([...], shell=True)` 形态下
    #    rc=0 但**JSON 从不产出** —— npm 会把 `--reporter/--outputFile` 当成自己的参数
    #    吞掉，不转发给 vitest。单串形式（含 `--`）已亲测可产出 201 KB JSON。
    cmd = (
        'npm exec -- vitest run e1 E1 --reporter=json '
        f'--outputFile="{_FE_JSON}"'
    )
    p = subprocess.run(
        ["cmd", "/c", cmd],
        cwd=FRONTEND,
        env=_env(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=1800,
    )
    if not _FE_JSON.exists():
        tail = ((p.stdout or "") + (p.stderr or ""))[-600:]
        return {"<vitest-no-output>"}, f"rc={p.returncode} 未产出 JSON: {tail}"
    data = json.loads(_FE_JSON.read_text(encoding="utf-8"))
    names: set[str] = set()
    total = passed = 0
    _FE_NAME2FILE.clear()
    for suite in data.get("testResults", []):
        fname = str(suite.get("name") or "").replace("\\", "/").rsplit("/", 1)[-1]
        for a in suite.get("assertionResults", []):
            total += 1
            full = str(a.get("fullName") or a.get("title") or "")
            _FE_NAME2FILE[full] = fname
            if a.get("status") == "failed":
                names.add(full)
            elif a.get("status") == "passed":
                passed += 1
    nfs = data.get("numFailedTestSuites")
    return names, f"{passed}/{total} passed, numFailedTestSuites={nfs}"


def matched(want: str, names: set[str]) -> list[str]:
    """``want`` 命中判定。

    ``want`` 有两种写法：

    - 裸方法名 ``test_xxx``：按 nodeid **末段**前缀匹配（吃掉 parametrize 的 ``[...]``）
    - 带文件/类的片段 ``test_a.py::TestB::test_c``：按 nodeid 子串匹配（用于同名消歧）
    - 前端标题（含中文）：按子串匹配
    """
    out: set[str] = set()
    for n in names:
        if want in n:
            out.add(n)
            continue
        if n.split("::")[-1].startswith(want):
            out.add(n)
    return sorted(out)


# ─── 主流程 ──────────────────────────────────────────────────────────────────


def _guard_files_of(failed: list[str], side: str) -> set[str]:
    """把失败名映射回守卫文件名。

    后端失败名形如 ``test_x.py::TestY::test_z``（首段即文件名）；前端是 vitest 的
    ``fullName``（不含文件名），靠 :data:`_FE_NAME2FILE` 反查 —— 该表在每次
    :func:`run_frontend` 里按 ``testResults[].name`` 重建，故是**实测**而非声明。
    """
    out: set[str] = set()
    for n in failed:
        if side == "be":
            out.add(n.split("::")[0])
        else:
            f = _FE_NAME2FILE.get(n)
            if f:
                out.add(f)
    return out


def restore_all(verbose: bool = True) -> int:
    n = 0
    for p in sorted(REPO.rglob(f"*{BAK_SUFFIX}")):
        target = p.with_suffix("")
        if str(target).endswith(BAK_SUFFIX):
            target = Path(str(p)[: -len(BAK_SUFFIX)])
        else:
            target = Path(str(p)[: -len(BAK_SUFFIX)])
        target.write_bytes(p.read_bytes())
        p.unlink()
        n += 1
        if verbose:
            print(f"[RESTORE] {target.relative_to(REPO)}")
    return n


def select(spec: str) -> list[Mut]:
    if not spec or spec == "all":
        return list(MUTATIONS)
    if spec in ("be", "fe"):
        return [m for m in MUTATIONS if m.side == spec]
    ids = {s.strip().upper() for s in spec.split(",") if s.strip()}
    got = [m for m in MUTATIONS if m.id in ids]
    missing = ids - {m.id for m in got}
    if missing:
        raise SystemExit(f"未知变异 id：{sorted(missing)}")
    return got


def check_anchors(muts: list[Mut]) -> int:
    bad = 0
    for m in muts:
        try:
            lines = read_lines(m.abspath)
            i = find_anchor(lines, m.anchor, m.line)
            extra = ""
            if m.kind in ("swap", "move"):
                j = find_anchor(lines, m.anchor2)
                a = block_range(lines, i, m.block_open)
                b = block_range(lines, j, m.block_open)
                extra = f"  blockA={a[0]+1}..{a[1]} blockB={b[0]+1}..{b[1]}"
            print(f"[OK  ] {m.id} {m.kind:<8} L{i+1} {m.path}{extra}")
        except AnchorMiss as exc:
            bad += 1
            print(f"[MISS] {m.id} {m.kind:<8} {m.path}\n        {exc}")
    print(f"\n锚点自检：{len(muts) - bad}/{len(muts)} OK，{bad} MISS")
    return 1 if bad else 0


def run_one(m: Mut, base: set[str], runner) -> dict:
    bak = Path(str(m.abspath) + BAK_SUFFIX)
    before = md5(m.abspath)
    bak.write_bytes(m.abspath.read_bytes())
    rec = {"id": m.id, "side": m.side, "want": m.want, "why": m.why}
    t0 = time.time()
    try:
        apply_mutation(m)
        if md5(m.abspath) == before:
            rec["verdict"] = "ANCHOR-MISS"
            rec["detail"] = "变异后 md5 未变 —— 改动未落盘（无效变异）"
            return rec
        names, summary = runner()
        added = sorted(names - base)
        gone = sorted(base - names)
        hit = matched(m.want, set(added))
        rec.update(
            summary=summary,
            added=added,
            gone=gone,
            hit=hit,
            added_files=sorted(_guard_files_of(added, m.side)),
        )
        if not added:
            rec["verdict"] = "GREEN"
        elif hit:
            rec["verdict"] = "RED"
        else:
            rec["verdict"] = "WRONG-TEST"
    except AnchorMiss as exc:
        rec["verdict"] = "ANCHOR-MISS"
        rec["detail"] = str(exc)
    except Exception as exc:  # noqa: BLE001 - 记录并继续，还原在 finally
        rec["verdict"] = "ERROR"
        rec["detail"] = f"{type(exc).__name__}: {exc}"
    finally:
        # 🔴 还原必须在 finally：留下污染文件会让后续变异全变 WRONG-TEST
        m.abspath.write_bytes(bak.read_bytes())
        bak.unlink()
        rec["restored"] = md5(m.abspath) == before
        rec["seconds"] = round(time.time() - t0, 1)
    return rec


def main() -> int:
    # 🔴 PS 控制台默认 GBK，本脚本报告含中文与箭头 → 不重配会 UnicodeEncodeError
    #    崩在报告阶段（变异已还原但结论看不到）。
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except Exception:  # noqa: BLE001 - 老版本 Python 无 reconfigure
            pass

    ap = argparse.ArgumentParser(description="E 循环守卫变异检验")
    ap.add_argument("--list", action="store_true", help="列出全部变异")
    ap.add_argument("--check-anchors", action="store_true", help="只做锚点自检，不改文件")
    ap.add_argument("--run", metavar="SPEC", help="执行：all | be | fe | M01,M02")
    ap.add_argument("--restore", action="store_true", help="还原所有 .mutbak")
    ap.add_argument("--out", metavar="PATH", help="结果 JSON 落盘路径")
    args = ap.parse_args()

    if args.restore:
        n = restore_all()
        print(f"还原 {n} 个备份文件")
        return 0

    if args.list:
        for m in MUTATIONS:
            print(f"{m.id}  {m.side}  {m.kind:<8} {m.path}")
            print(f"      want: {m.want}")
            print(f"      why : {m.why}")
        return 0

    muts = select(args.run or "all")

    if args.check_anchors:
        return check_anchors(muts)

    if not args.run:
        ap.print_help()
        return 2

    stale = list(REPO.rglob(f"*{BAK_SUFFIX}"))
    if stale:
        print("[ABORT] 存在残留备份，先 --restore：")
        for p in stale:
            print(f"  {p.relative_to(REPO)}")
        return 3

    sides = {m.side for m in muts}
    print(f"变异 {len(muts)} 条，涉及侧：{sorted(sides)}")

    baselines: dict[str, set[str]] = {}
    if "be" in sides:
        print("\n── 后端基线 ──")
        names, summary = run_backend()
        baselines["be"] = names
        print(f"  {summary}")
        print(f"  失败名集合：{sorted(names) or '空集'}")
        if names:
            print("  [ABORT] 基线非空，变异差集判定不可信")
            return 4
        if f"{BASELINE_BE_PASSED} passed" not in summary:
            print(f"  [WARN] 与冻结基线 {BASELINE_BE_PASSED} passed 不符（差异需说明）")
    if "fe" in sides:
        print("\n── 前端基线 ──")
        names, summary = run_frontend()
        baselines["fe"] = names
        print(f"  {summary}")
        print(f"  失败名集合：{sorted(names) or '空集'}")
        if names:
            print("  [ABORT] 基线非空，变异差集判定不可信")
            return 4
        if f"{BASELINE_FE_PASSED}/" not in summary:
            print(f"  [WARN] 与冻结基线 {BASELINE_FE_PASSED} passed 不符（差异需说明）")

    results: list[dict] = []
    for m in muts:
        runner = run_backend if m.side == "be" else run_frontend
        print(f"\n── {m.id} [{m.side}] {m.kind} {Path(m.path).name} ──")
        print(f"   {m.why}")
        rec = run_one(m, baselines[m.side], runner)
        results.append(rec)
        v = rec["verdict"]
        print(f"   判定 {v}  ({rec.get('seconds')}s)  还原={rec.get('restored')}")
        if rec.get("summary"):
            print(f"   {rec['summary']}")
        if rec.get("detail"):
            print(f"   detail: {rec['detail']}")
        if v == "RED":
            print(f"   命中 want：{rec['hit'][:4]}")
            print(f"   新增失败 {len(rec['added'])} 条")
        elif v == "WRONG-TEST":
            print(f"   want 未命中：{m.want}")
            print(f"   实际新增：{rec['added'][:10]}")
        elif v == "GREEN":
            print("   [守卫缺陷] 变异未被任何守卫捕获")
        if rec.get("gone"):
            print(f"   [WARN] 基线中消失的失败项：{rec['gone'][:5]}")
        if not rec.get("restored"):
            print("   [FATAL] 还原核验失败，停止后续变异")
            break

    print("\n" + "=" * 72)
    print(f"基线：后端 {BASELINE_BE_PASSED} passed / 前端 {BASELINE_FE_PASSED} passed")
    tally: dict[str, int] = {}
    for r in results:
        tally[r["verdict"]] = tally.get(r["verdict"], 0) + 1
    for k in ("RED", "GREEN", "WRONG-TEST", "ANCHOR-MISS", "ERROR"):
        if k in tally:
            print(f"  {k:<12} {tally[k]}")
    for r in results:
        flag = "OK " if r["verdict"] == "RED" else "!! "
        files = ",".join(r.get("added_files") or []) or "-"
        print(f"  {flag}{r['id']}  {r['verdict']:<12} {r['want'][:40]:<40} [{files}]")

    # ── 守卫文件覆盖面（实测：由各变异的失败名反查文件，不是声明）────────────────
    covered: set[str] = set()
    for r in results:
        covered |= set(r.get("added_files") or [])
    if len(muts) == len(MUTATIONS):
        missing = sorted(set(SPEC_GUARD_FILES) - covered)
        print(
            f"\n守卫文件覆盖面：{len(SPEC_GUARD_FILES) - len(missing)}/{len(SPEC_GUARD_FILES)}"
            " 个本 spec 守卫文件被至少一条变异打红"
        )
        for f in missing:
            print(f"  [GAP] {f}  （{SPEC_GUARD_FILES[f]}）—— 全绿但未经反证，需补一条变异")
        if missing:
            print("  🔴 「变异全 RED」不等于「守卫都被反证过」：前者按清单计数，后者按文件计数")
    else:
        print(f"\n守卫文件覆盖面：本次为子集运行（{len(muts)}/{len(MUTATIONS)} 条），不做覆盖面结论")
    extra = sorted(covered - set(SPEC_GUARD_FILES))
    if extra:
        print(f"  [INFO] 另打红 {len(extra)} 个未登记文件（多为他 spec 守卫）：{extra[:6]}")

    if args.out:
        Path(args.out).write_text(
            json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\n结果已落盘：{args.out}")

    left = list(REPO.rglob(f"*{BAK_SUFFIX}"))
    if left:
        print(f"[FATAL] 残留备份 {len(left)} 个，需手动 --restore")
        return 5
    return 0 if tally.get("RED") == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
