/**
 * 披露 Tab 自动同步覆盖率守卫
 *
 * 背景：附注不跟随底稿内容的直接原因之一 —— 披露 Tab 改了数据不会自动同步到附注，
 * 用户必须记得手动点「同步到附注」。机制 `useDisclosureAutoSync` 早已存在
 * （spec `disclosure-note-linkage-completion` Req1），缺的是**接入覆盖**与**正确的触发条件**。
 *
 * 本守卫钉死三件事：
 * 1. 有同步能力（含 `syncToDisclosureNotes`）的 Tab 必须接入 `useDisclosureAutoSync`
 * 2. 接入了就必须真的调 `scheduleAutoSync`（不许只 import / 只建实例 —— E1 曾如此）
 * 3. 触发条件不得**只**监听提示横幅类状态（F2 曾只 watch `dataUpdatedVisible`，
 *    那是「上游数据已更新」的横幅可见性，用户自己改数据一律不触发）
 *
 * 未接入者进 `NOT_WIRED_ALLOWLIST` 且**必须写 reason**，随推广批次逐个移出
 * （对齐 `disclosure-columns-coverage` 的 allowlist 范式）。
 *
 * Spec: .kiro/specs/disclosure-note-follow-actual-content/ R1 / Task 4.3
 */
import { describe, it, expect } from 'vitest'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, resolve } from 'node:path'

const WP_ROOT = resolve(__dirname, '..')

/** 只监听这类状态不算接入：它们是「上游变化」提示，不代表用户编辑 */
const BANNER_ONLY_SOURCES = ['dataUpdatedVisible', 'upstreamUpdatedVisible', 'staleVisible']

/**
 * 🔴 **永久豁免** —— 源模板 / 附注模板依据决定「本来就不该有同步链路」。
 *
 * 与 `SYNC_PATH_GAP`（真实缺口，待补）**语义不同故分表登记**。
 * 拆分前两者混在 `MISSING_SYNC_PATH` 一张表里（6 条 = 4 豁免 + 2 缺口），
 * 后果是「真实缺口应为 0」这个**有价值且可收敛的目标无法被断言**
 * —— 只要还有永久豁免条目在，清单就永远非空。
 *
 * （spec `guard-assertion-attribution-refactor` R4.3 / Property 8、9）
 *
 * 🔴 每条必须写明**源模板或附注模板依据**；接错链路的后果不是「多一个空页面」，
 * 而是**凭空新建虚构章节**或**与共节循环互相覆盖**（见各条理由）。
 * 只许缩不许扩：新增披露 Tab 必须自带链路，不得往本表加条目绕过。
 */
const PERMANENT_EXEMPT: readonly string[] = [
  // 🔴 H5 Listed **永久豁免**（有意无链路，不是缺口；spec
  //   h-cycle-extraction-formula-and-disclosure-completion Task 11 已落地）：
  //   已由「自造两张附注表 + AI 接线」改为**本版不适用说明页**。三条落点侧实证 ——
  //   ① `note_template_variant_matrix.json` · `you_qi_zi_chan` 的
  //      `listed_standalone` / `listed_consolidated` 均为 `null`
  //   ② `note_template_listed.json` 共 204 章节，含「油气」的**实测 0 个**
  //   ③ `h5NoteSectionMap.H5_NOTE_SECTION` 只有 `soe` 键，`buildH5SyncPayload` 恒发 soe
  //   ⇒ 上市准则下油气资产不单独设附注章节，接链路会**凭空新建虚构章节**。
  //   注意与 N4 国企侧**不同构**：H5 的源 sheet `附注披露信息（上市公司）` 是
  //   visible 且**有完整 38 行四层表**（模板作者预留的通用格式），不是「内容为无」。
  //   守卫：`h5/__tests__/h5ListedNotApplicable.spec.ts`
  'H5TabDisclosureListed.vue',
  // 🔴 L2 应付利息 两版写权已收敛到 L2（spec l-cycle-…completion 裁决 A）：
  //   L2 Tab 已接 useDisclosureAutoSync + buildL2SyncPayload 推 §五、42 / §八、42
  //   的「应付利息」+「逾期利息」子表，K3 侧已停止推送这两张表。
  //   原 PERMANENT_EXEMPT 条目已移出。
  // 🔴 N4 国企**豁免**：源模板 `附注披露信息（国企）` 内容为「附注披露信息：无」
  //   → 国有企业格式不单独披露税金及附加，`note_template_variant_matrix` 的
  //   `shui_jin_ji_fu_jia.soe_*` 为 null。该 Tab 已改为「本版不适用」说明页
  //   （无表格、无同步按钮、`buildN4SyncPayload('soe')` 恒 null），
  //   属**有意无链路**，不是缺口。反向锁死见 `n4NoteSectionMap.spec.ts` Property 4。
  'N4TabDisclosureSoe.vue',
]

/**
 * 🔴 **真实缺口** —— 应该有同步链路但还没建，待 owner spec 补齐。
 *
 * 与 `PERMANENT_EXEMPT` 分开的价值：本表可以、也应该**收敛到 0**，
 * 从而成为一个真正可断言的目标（拆分前混在一起时这个目标不可表达）。
 */
const SYNC_PATH_GAP: readonly string[] = [
  // 🔴 L4 应付债券（2）已接入 useDisclosureAutoSync（spec l-cycle-…completion Task 19-22）：
  //   两版已接 buildL4SyncPayload 推 noteTexts 到 §五、46 / §八、50。
  //   从 SYNC_PATH_GAP 移出。
  // 'L4TabDisclosureListed.vue',  ← 已移出
  // 'L4TabDisclosureSoe.vue',     ← 已移出
]

/**
 * 拆分前的合并视图 —— 供「实扫 − 已登记」的关系断言使用。
 *
 * 🔴 保留合并视图而非在断言处每次 `[...A, ...B]`：一处定义、两处语义，
 * 避免将来有人只往其中一张表加条目却忘了关系断言（Property 8 的「不丢不增」）。
 */
const ALL_DECLARED_NO_SYNC: readonly string[] = [...PERMANENT_EXEMPT, ...SYNC_PATH_GAP]

/*
 * ════════════════════════════════════════════════════════════════════════════
 * 📜 墓碑注释块 —— 原 `MISSING_SYNC_PATH` 的完整演进记录
 * ════════════════════════════════════════════════════════════════════════════
 *
 * 🔴 该常量已按语义拆为上方 `PERMANENT_EXEMPT`（4 条）+ `SYNC_PATH_GAP`（2 条）。
 *    本块**只是历史记录，不参与任何断言**；块内出现的
 *    `'XTabDisclosure*.vue',` 是拆分前的原始清单快照，保留以便追溯。
 *
 *    保留理由：下面每条「已补齐」记录都写明了**是哪个 spec / 哪个 Task 补的、
 *    补进了哪个章节、原来错在哪**（如 L7 的 `l7NoteSectionMap` 曾是死 import 且
 *    映射本身 6 处缺陷、G6 曾是 7 个虚构小节 + 137 行 `成本项目N` 自造行）。
 *    这些是 41 → 6 收敛过程的唯一档案，删掉就再也查不到某个 Tab 何时被谁接通。
 *
 * 📌 计数修正史：先按 emit 计入链路 → 低估为 27；改为不计 emit → 64；
 * 再加**委托解析**（`resolveDelegate`）→ 60（G10/G11 的 Listed/SOE 各是 15~21 行薄壳，
 * `v-bind="$props"` 委托给已带完整链路的 Base，属虚报）；
 * 批 1 补齐 G8/G9/G12 → 54；再补 G5 → **52**。
 *
 * 这批比「没接自动同步」严重得多：它们**没有 `syncToDisclosureNotes`、不打
 * `sync-from-workpaper` 端点、也不 emit 给父组件** —— 披露数据只停在
 * `checklist_responses`，附注模块永远拿不到。抽查 N2/L2 确认 `disclosure-notes`
 * 端点 0 命中。这是全库 569 个附注章节仍是 legacy 快照的根本原因之一。
 *
 * 补齐一个 Tab 需要：sheet→section 映射（`XNoteSectionMap.ts`）+ 载荷构建器
 * （`buildXSyncPayload`）+ `columns` 定义 + `syncToDisclosureNotes` + 自动同步接线，
 * 工作量对齐 F2/K1 的单循环量级 → 见 spec Task 12（按循环分批）。
 *
 * 本清单只允许**变短**：新增披露 Tab 必须自带同步链路。
 *
 * ── 以下为拆分前的原始清单内容（含条目与墓碑注释）────────────────────────────
 *
  // D2（1）已补齐：薄壳 D2TabDisclosure.vue 委托 D2DisclosureNoteBody.vue
  //   （非标委托：版本切换 + :key 挂载 ⇒ 要注入 :variant 故不能整体 v-bind="$props"）
  //   🔴 2026-08-15 修：`resolveDelegate` 旧判据只认 v-bind="$props" ⇒ 把 D2 误判为
  //      「完全无链路」并报违规（假红）。已放宽为「整体转发 ∨ 关键 prop 全转发」。
  //      注释里当年就写了「resolveDelegate 无法识别但链路完整」却没人去修判据。
  // F4（2）已补齐：spec f-cycle-disclosure-parity R6（原为只有手动 syncToNotes、
  // 未接 useDisclosureAutoSync → 用户改数据不点按钮永不进附注）
  // G10 / G11：Listed+SOE 是薄壳，链路在 Base 里 → 由 `resolveDelegate` 解析，不算缺口
  // G12 已补齐（spec disclosure-sync-path-buildout Task 2.8）
  // G4 已补齐（Task 2.1）；G5 已补齐（Task 2.2）
  // G6 已补齐（Task 2.3）：组件原是自造的 7 个虚构小节 + `generateRows()` 137 行
  //   `成本项目N`，已按权威模板 `backend/wp_templates/G/G6 其他债权投资.xlsx`
  //   重写为 6 小节 / 14 张表后接链路。
  // G8 已补齐（Task 2.4）；G9 已补齐（Task 2.5，Base + 2 个薄壳一并转绿）
  // H4（1）已补齐：接入 useDisclosureAutoSync + syncToNotes + buildH4SoeSyncPayloads
  //   推送到 §八、23 在建工程（与 H2 共享章节），子表「在建工程」汇总行
  // 🔴 H5 Listed（1）**永久豁免**（有意无链路，不是缺口；spec
  //   h-cycle-extraction-formula-and-disclosure-completion Task 11 已落地）：
  //   已由「自造两张附注表 + AI 接线」改为**本版不适用说明页**。三条落点侧实证 ——
  //   ① `note_template_variant_matrix.json` · `you_qi_zi_chan` 的
  //      `listed_standalone` / `listed_consolidated` 均为 `null`
  //   ② `note_template_listed.json` 共 204 章节，含「油气」的**实测 0 个**
  //   ③ `h5NoteSectionMap.H5_NOTE_SECTION` 只有 `soe` 键，`buildH5SyncPayload` 恒发 soe
  //   ⇒ 上市准则下油气资产不单独设附注章节，接链路会**凭空新建虚构章节**。
  //   注意与 N4 国企侧**不同构**：H5 的源 sheet `附注披露信息（上市公司）` 是
  //   visible 且**有完整 38 行四层表**（模板作者预留的通用格式），不是「内容为无」。
  //   守卫：`h5/__tests__/h5ListedNotApplicable.spec.ts`
  'H5TabDisclosureListed.vue',
  // H6（2）已补齐：改为 v-bind="$props" 薄壳，由 resolveDelegate 解析到 H6TabDisclosure.vue
  //   （已有 useDisclosureAutoSync + syncToNotes + buildH6*SyncPayloads 完整链路）
  // H7（2）已收口（spec h7-biological-assets-disclosure-rebuild）：两个 Tab 由「单行只读
  //   movementRows」整体重建为源模板结构（上市 = 产业分组的两级表头列转置表，34 行 / 11 行；
  //   国企 = 4 产业 + 可扩类别行 5 列表），并建立 h7NoteSectionMap / h7DisclosureSyncPayload
  //   与自动同步 → 按「清单只许变短」移出。
  // J2（2）已补齐（spec disclosure-sync-path-buildout 批6）：
  //   两版接 useDisclosureAutoSync + syncToDisclosureNotes + buildJ2Listed/SoeSyncPayload
  //   推 §五、49 / §八、54「长期应付职工薪酬/设定受益计划净资产」
  // 🔴 L2 应付利息 两版**豁免**（有意无链路，不是缺口）：
  //   ① `note_template_{listed,soe}.json` 都**没有**「应付利息」独立章节
  //      （`note_template_variant_matrix.json` 亦无 `ying_fu_li_xi` 条目）；
  //   ② 新准则下应付利息并入「其他应付款」，披露归 K3 §五、42 / §八、42 的
  //      子表「应付利息」+「重要的逾期未付利息」，且 K3 源 xlsx 的应付利息行清单
  //      （分期付息到期还本的长期借款利息 / 企业债券利息 / 短期借款应付利息 /
  //      划分为金融负债的优先股\永续债利息 / 其中：工具1…）与 L2 源 xlsx **逐字相同**；
  //   ③ `buildK3SyncPayload` 已实装推这两张表 → L2 再推会**同章节同表名互相覆盖**
  //      （谁最后保存谁赢，数据随机跳变），比不推更糟。
  'L2TabDisclosureListed.vue',
  'L2TabDisclosureSoe.vue',
  // 🔴 L4 应付债券（2）**需结构对齐重建**（暂留缺口）：源模板 §五、46/§八、50 是
  //   「应付债券」主表 +「增减变动」+「（续）」+「优先股/永续债等其他金融工具变动情况」
  //   两级表头 9 列（期初/本期增加/本期减少/期末 × 数量·账面价值）+ 可转债/其他金融工具
  //   定性披露段。与 H7 同属多级/转置复杂结构，现有组件不同构，不做仓促自造 →
  //   按 G6 范式另立批次重建。
  'L4TabDisclosureListed.vue',
  'L4TabDisclosureSoe.vue',
  // L5（2）已补齐（Task 4.3）：接入 useDisclosureAutoSync + buildL5SyncPayload
  //   推 §五、48 / §八、53「长期应付款」主表（净额）；专项应付款子表由 L6 推（共章节浅合并）
  // L6（2）已补齐（Task 4.4）：**无独立章节** —— 专项应付款表在 L5 的 §五、48 / §八、53
  //   里（源模板 L6 两版都写「【长期应付款与专项应付款的合计数披露详见P5-1】」）。
  //   两个底稿各推**不同子表**、按 key 浅合并（同 H4→H2 已验证范式）：
  //   L5 推「长期应付款」主表 + 明细表，L6 推「专项应付款」/「①专项应付款…前5 项」。
  // L7（2）已补齐（Task 4.5）：`l7NoteSectionMap` 原是**死 import**（组件只 import
  //   `buildL7SyncPayload` 从未调用），且映射本身 6 处缺陷（上市表名会造孤儿表 /
  //   sheet 名多「核对」/ 国企列序反 / 位置化 values / columns 键不匹配 / 未表态 flat）
  //   → 已重写映射 + 两版接线（§五、52 / §八、57）
  // L8（2）已补齐（Task 4.6）：新建 `l8NoteSectionMap`（§五、67 / §八、68），
  //   并按源模板 12 行重建行结构（原两版各自造 7 行 / 10 行且互不相同）
  // 🔴 M1 应付股利（利润）两版**豁免**（同 L2 同理）：附注模板无「应付股利」独立章节，
  //   披露归 K3 §五、42 / §八、42 的「应付股利」+「重要的超过1年未支付的应付股利」，
  //   `buildK3SyncPayload` 已实装 → 双推会撞表。
  // M1（2）已补齐（Task 7，本 spec）：浅合并推 K3 §五、42/八、42
  //   接入 useDisclosureAutoSync + buildK3SyncPayloads（应付股利相关子表）。
  // M10（2）已补齐：接入 useDisclosureAutoSync + buildM10ListedSyncPayload / buildM10SoeSyncPayload
  //   推 §五、54「其他权益工具」（上市三表）/ §八、59（国企单表）。
  // M2（2）已补齐：接入 useDisclosureAutoSync + buildM2ListedSyncPayload / buildM2SoeSyncPayload
  //   推 §五、53「股本」两级 8 列 / §八、58「实收资本」两级 7 列。
  // M3（1）已补齐（Task 5）：接入 useDisclosureAutoSync + buildM3SyncPayload
  //   推 §五、56「库存股」5 列 flat 变动表。
  // M4（2）已补齐（Task 5，批 4）：接入 useDisclosureAutoSync + buildMEquitySyncPayload('M4',…)
  //   推 §五、55 / §八、60「资本公积」标准变动表（项目|期初|本期增加|本期减少|期末）。
  // M5（2）已补齐（Task 5，批 4）：同范式推 §五、59 / §八、62「盈余公积」变动表；
  //   国企侧多「国有企业专项披露」文本段并入 _note_texts。
  // M6（2）已补齐（Task 6）：接入 useDisclosureAutoSync + buildM6SyncPayload
  //   推 §五、61 / §八、63「未分配利润」固定行。
  // M7（2）已补齐（Task 5，批 4）：推 §五、58 / §八、61「专项储备」变动表。
  //   源模板附注为标准 5 列（上市）/ 6 列（国企含「备注」）→ 组件 Listed 的「增减原因说明」
  //   列不进附注（模板无此列，宁缺勿造，留底稿），国企侧「费用化使用/资本化使用」两列
  //   合并为「本期减少」、「计提依据」→「备注」列（`buildMEquitySyncPayload('M7','soe')`）。
  // M8（2）已补齐（Task 10）：接入 useDisclosureAutoSync + buildM8SyncPayload
  //   推 §五、60 / §八、94「一般风险准备」5 列 flat 变动表。
  // M9（2）已补齐（Task 12）：接入 useDisclosureAutoSync + buildM9Listed/SoeSyncPayload
  //   推 §五、57「其他综合收益」两级 8 列 / §八、79「OCI 各项目」两级 7 列。
  // N2 两版已补齐（spec n-cycle-tax-disclosure-alignment Task 4）：
  //   原两组件是复制粘贴关系，上市误用国企变动口径，两版都无同步链路
  // N3 已**删除**披露 Tab：源模板 `N3 递延所得税负债.xlsx` 无「附注披露信息」sheet
  //   （classification 里 wp_code=N3 同样 0 条），递延所得税负债披露与 N1 共节
  //   （五、30 / 八、31，N1 表(1) 已含负债段）。原组件是自造三小节且入口不可达。
  //   反向守卫见下方 `CYCLES_WITHOUT_DISCLOSURE`。
  // N4 上市已补齐（Task 5.2）；原为自造 6 列（多变动额/变动率/变动原因）
  // 🔴 N4 国企**豁免**：源模板 `附注披露信息（国企）` 内容为「附注披露信息：无」
  //   → 国有企业格式不单独披露税金及附加，`note_template_variant_matrix` 的
  //   `shui_jin_ji_fu_jia.soe_*` 为 null。该 Tab 已改为「本版不适用」说明页
  //   （无表格、无同步按钮、`buildN4SyncPayload('soe')` 恒 null），
  //   属**有意无链路**，不是缺口。反向锁死见 `n4NoteSectionMap.spec.ts` Property 4。
  'N4TabDisclosureSoe.vue',
  // N5 两版已补齐（Task 6）：薄壳委托 `n5/shared/N5DisclosureBody.vue`
  //   （由 `resolveDelegate` 解析），并修掉两表重名丢表 + 国企 sheet 名缺右括号
 *
 * ════════════════════════════════════════════════════════════════════════════
 * 📜 墓碑注释块结束（以上全部为历史记录，不参与断言）
 * ════════════════════════════════════════════════════════════════════════════
 */

/**
 * 🔴 源模板**没有**披露 sheet 的循环 —— 不得存在披露 Tab 组件。
 *
 * 造一个出来的后果不是"多个空页面"，而是**自造披露内容有机会被推进别人的附注章节**
 * （N3 递延所得税负债与 N1 共节 五、30 / 八、31，N1 表(1) 已含负债段）。
 * 原 `N3TabDisclosure.vue` 就是这种产物：三个自拟小节（概述 / 应纳税暂时性差异明细 /
 * 余额变动表），源模板一张都没有，且宿主判定 `currentSheet === '附注'` 永不命中
 * （classification 里 wp_code=N3 零条附注 sheet）→ 死代码 + 污染源，已删除。
 *
 * 每条必须写明「源模板依据」，新增前先 openpyxl 读 `wb.sheetnames` 确认。
 */
const CYCLES_WITHOUT_DISCLOSURE: Readonly<Record<string, string>> = {
  F0: '源模板 F0 存货循环函证.xlsx 为 11 张函证程序底稿，无「附注披露信息」sheet；'
    + '函证结果归函证模块，不产生附注章节',
  F5: '源模板 F5 营业成本.xlsx 为 10 张成本程序底稿，无「附注披露信息」sheet；'
    + '营业成本附注归损益类章节（IS-002），不由 F5 底稿产生披露 Tab',
  N3: '源模板 N3 递延所得税负债.xlsx 仅 底稿目录/N3A/N3-1/N3-2/N3-3/GT_Custom，无附注披露 sheet；'
    + '递延所得税负债披露与 N1 共节（五、30 / 八、31，N1 表(1) 含负债段）',
  J3: '源模板 J3 股份支付.xlsx 仅 底稿目录/J3A/J3-1/J3-2/J3-3/GT_Custom，无附注披露 sheet；'
    + '附注「十二、股份支付」（listed 5 节 6 表）与「八、83」（soe 3 表）无底稿数据来源，'
    + '属平台级结构缺口，待用户裁决',
}

/**
 * 尚未接入自动同步的 Tab —— 每条**必须**有 reason。
 *
 * ⚠️ 2026-07-30 重新统计后本表**应为空**：实测 `syncToDisclosureNotes && !scheduleAutoSync`
 * 的真实缺口为 **0**。此前 60 条「未接入」全是没有同步链路的 Tab（已移入
 * `MISSING_SYNC_PATH`）或用别的 syncFn 的 Tab（25 个，合规）。保留本表结构以便
 * 将来新增 Tab 时登记。
 */
const NOT_WIRED_ALLOWLIST: Record<string, string> = {
  // 实测为空：真实缺口（有同步能力却未接自动同步）= 0
}

interface TabInfo {
  name: string
  path: string
  src: string
  hasSyncFn: boolean
  hasImport: boolean
  hasCall: boolean
  /** 薄壳委托目标（`<Base variant="x" v-bind="$props" />`）的绝对路径，无则 null */
  delegatesTo: string | null
}

/**
 * 识别「变体薄壳」：整个 `<template>` 只有一个组件标签且带 `v-bind="$props"`。
 *
 * 🔴 这类文件（G9/G10/G11 的 Listed/SOE，15~21 行）本身没有任何同步代码，
 * 同步链路在被委托的 `XTabDisclosureBase.vue` 里 → 直接按文件判定会**虚报缺口**。
 * 返回委托目标的绝对路径（从 import 语句解析），非薄壳返回 null。
 */
function resolveDelegate(src: string, path: string): string | null {
  const tpl = /<template>([\s\S]*?)<\/template>/.exec(src)?.[1] ?? ''
  const tags = tpl.replace(/<!--[\s\S]*?-->/g, '').match(/<([A-Z][\w.]*)\b/g) ?? []
  if (tags.length !== 1) return null
  const tag = tags[0].slice(1)

  // 🔴 **委托的本质是「把数据源整体转发给唯一的子组件」**，`v-bind="$props"` 只是写法之一。
  //
  // 旧判据只认 `v-bind="$props"` ⇒ 把 `D2TabDisclosure.vue` 误判为「完全无同步链路」
  // 并报违规。D2 实际是**非标委托**：顶部版本切换 + `:key="activeVariant"` 重建
  // `D2DisclosureNoteBody`（持久化前缀 `D2-disc-{variant}-` 随版本变化，必须重挂），
  // 因此要注入 `:variant="activeVariant"` 而不能整体 `v-bind="$props"`
  // —— 逐个显式转发 `wp-id` / `project-id` / `all-responses`，链路完整。
  // `MISSING_SYNC_PATH` 的注释早就写明「resolveDelegate 无法识别但链路完整」，
  // 却没人去修判据 ⇒ 该条自 D2 补齐起就是**假红**（形态 A 的断言因判据能力不足而误报，
  // 与本 spec 治的「等值断言假红」同族）。
  //
  // 放宽为「整体转发 ∨ 关键 prop 全转发」。放宽不会漏判：`hasAnySyncPath` 仍会
  // **递归检查被委托组件本身有没有链路**，被委托方无链路时照样报违规（见下方反向自检）。
  const forwardsAll = /v-bind="\$props"/.test(tpl)
  const forwardsKeyProps = /:wp-id|:wpId/.test(tpl)
    && /:project-id|:projectId/.test(tpl)
    && /:all-responses|:allResponses/.test(tpl)
  if (!forwardsAll && !forwardsKeyProps) return null

  const imp = new RegExp(`import\\s+${tag}\\s+from\\s+['"](.+?)['"]`).exec(src)
  if (!imp) return null
  const dir = path.replace(/[\\/][^\\/]+$/, '')
  return resolve(dir, imp[1])
}

function walk(dir: string, out: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    const p = join(dir, entry)
    if (statSync(p).isDirectory()) {
      if (entry === '__tests__' || entry === 'node_modules') continue
      walk(p, out)
    } else if (/TabDisclosure.*\.vue$/.test(entry)) {
      out.push(p)
    }
  }
  return out
}

/** 全部 `.vue`（含宿主 `Gt*.vue`）—— 用于扫「宿主是否给披露 Tab 传 projectId」 */
function walkVue(dir: string, out: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    const p = join(dir, entry)
    if (statSync(p).isDirectory()) {
      if (entry === '__tests__' || entry === 'node_modules') continue
      walkVue(p, out)
    } else if (entry.endsWith('.vue')) {
      out.push(p)
    }
  }
  return out
}

const TABS: TabInfo[] = walk(WP_ROOT).map((p) => {
  const src = readFileSync(p, 'utf8')
  return {
    name: p.split(/[\\/]/).pop() as string,
    path: p,
    src,
    hasSyncFn: src.includes('syncToDisclosureNotes'),
    hasImport: src.includes('useDisclosureAutoSync'),
    hasCall: src.includes('scheduleAutoSync('),
    delegatesTo: resolveDelegate(src, p),
  }
})

/**
 * 取 `syncToDisclosureNotes` 的函数体（大括号配平），找不到返回 ''。
 *
 * 用于识别「自递归假接入」：见下方 `selfScheduleOnly` 断言。
 */
function syncFnBody(src: string): string {
  const m = /\b(?:async\s+)?function\s+syncToDisclosureNotes\s*\(/.exec(src)
  if (!m) return ''
  const open = src.indexOf('{', m.index + m[0].length)
  if (open < 0) return ''
  let depth = 0
  for (let i = open; i < src.length; i += 1) {
    if (src[i] === '{') depth += 1
    else if (src[i] === '}') {
      depth -= 1
      if (depth === 0) return src.slice(open, i + 1)
    }
  }
  return ''
}

/** 去注释（守卫源码里会用注释解释"为什么不能这么写"，不去会误判） */
function stripComments(code: string): string {
  return code.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/.*$/gm, '$1')
}

/** 提取包含 scheduleAutoSync 的 watch 的监听源片段 */
function watchSourcesFor(src: string): string[] {
  const out: string[] = []
  const re = /watch\(\s*([\s\S]{0,400}?)\s*,\s*\(/g
  let m: RegExpExecArray | null
  while ((m = re.exec(src))) {
    const after = src.slice(m.index, m.index + 900)
    if (after.includes('scheduleAutoSync')) out.push(m[1])
  }
  return out
}

describe('披露 Tab 自动同步覆盖率', () => {
  it('扫描到足量披露 Tab（防止 glob 失效导致守卫空转）', () => {
    expect(TABS.length).toBeGreaterThan(140)
  })

  it('接入了 useDisclosureAutoSync 就必须真的调 scheduleAutoSync（不许只 import 或只建实例）', () => {
    const halfWired = TABS.filter((t) => t.hasImport && !t.hasCall).map((t) => t.name)
    expect(
      halfWired,
      `以下 Tab import 了 useDisclosureAutoSync 却从不调 scheduleAutoSync（等于没接，E1 曾如此）：${halfWired.join(', ')}`,
    ).toEqual([])
  })

  it('有 syncToDisclosureNotes 的 Tab 必须接入自动同步（未接入需登记 allowlist + reason）', () => {
    const unwired = TABS.filter((t) => t.hasSyncFn && !t.hasCall).map((t) => t.name)
    const undeclared = unwired.filter((n) => !(n in NOT_WIRED_ALLOWLIST))
    expect(
      undeclared,
      `以下 Tab 有同步能力但未接自动同步且未登记 allowlist：${undeclared.join(', ')}`,
    ).toEqual([])
  })

  // ── 🔴 自递归假接入（2026-07-30 静态扫出 16 处，横跨 G1/G2/G3/G6/H3/I4/I5/I6/K1） ──
  //
  // `scheduleAutoSync(fn)` 的语义是「**数据变更后**防抖调度一次同步」。写在
  // `syncToDisclosureNotes()` 内部就是调度自己：
  //
  //   async function syncToDisclosureNotes() {
  //     await disc.syncToNotes()
  //     autoSync.scheduleAutoSync(syncToDisclosureNotes)   // ← 每次调用都排下一次
  //   }
  //
  // 后果：①用户点一次同步就进入 800ms 周期的无限 POST（直到组件卸载 cancelPending）
  //       ②`hasCall` 只看「有没有 scheduleAutoSync」→ **被这行骗过**，8 个 Tab 的
  //         自动同步从未接到任何数据变更（与 F2 只 watch 横幅可见性同款「假接入」）。

  it('🔴 syncToDisclosureNotes 内不得调 scheduleAutoSync（自触发 → 周期性重复 POST）', () => {
    const offenders = TABS.filter((t) =>
      stripComments(syncFnBody(t.src)).includes('scheduleAutoSync('),
    ).map((t) => t.name)
    expect(
      offenders,
      `以下 Tab 在同步函数内调度自己，会 800ms 周期重复发同一个 POST：${offenders.join(', ')}`,
    ).toEqual([])
  })

  it('🔴 不得只靠自递归充当"已接入"（自动同步必须由数据变更触发）', () => {
    const fake = TABS.filter((t) => {
      if (!t.hasCall) return false
      const clean = stripComments(t.src)
      const total = (clean.match(/scheduleAutoSync\(/g) ?? []).length
      const inSyncFn = (stripComments(syncFnBody(t.src)).match(/scheduleAutoSync\(/g) ?? []).length
      return total > 0 && total === inSyncFn
    }).map((t) => t.name)
    expect(
      fake,
      `以下 Tab 的 scheduleAutoSync 全部在同步函数内 → 自动同步是假接入（骗过 hasCall）：${fake.join(', ')}`,
    ).toEqual([])
  })

  it('自检替身：能识别自递归假接入（防守卫本身空转）', () => {
    const fixture = `
async function syncToDisclosureNotes() {
  await disc.syncToNotes()
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}`
    expect(stripComments(syncFnBody(fixture)).includes('scheduleAutoSync(')).toBe(true)

    const fixed = `
async function syncToDisclosureNotes() {
  await disc.syncToNotes()
}
watch([() => disc.rows], () => autoSync.scheduleAutoSync(syncToDisclosureNotes), { deep: true })`
    expect(stripComments(syncFnBody(fixed)).includes('scheduleAutoSync(')).toBe(false)
  })

  it('allowlist 每条都必须有非空 reason', () => {
    const blank = Object.entries(NOT_WIRED_ALLOWLIST)
      .filter(([, r]) => !r || !r.trim())
      .map(([k]) => k)
    expect(blank, `allowlist 缺 reason：${blank.join(', ')}`).toEqual([])
  })

  it('allowlist 不得残留已接入的 Tab（推广完成后必须移出）', () => {
    const stale = Object.keys(NOT_WIRED_ALLOWLIST).filter((n) => {
      const t = TABS.find((x) => x.name === n)
      return t?.hasCall
    })
    expect(stale, `以下 Tab 已接入但仍在 allowlist 中，请移出：${stale.join(', ')}`).toEqual([])
  })

  it('真实缺口（有同步能力却未接自动同步）应为 0', () => {
    const gap = TABS.filter((t) => t.hasSyncFn && !t.hasCall).map((t) => t.name)
    expect(gap, `出现新的自动同步缺口：${gap.join(', ')}`).toEqual([])
  })
})

describe('披露 Tab 同步链路完整性', () => {
  /** 有任何同步痕迹：自有 syncFn / 别的 syncFn 走 autoSync / 打端点 / emit 给父组件 */
  /**
   * 真正的同步链路：自有 syncFn / 别的 syncFn 走 autoSync / 直打同步端点。
   *
   * 🔴 **emit 不算**（2026-07-30 实证）：37 个 emit 型披露 Tab 的事件只有
   * `navigate`(27) / `imported`(7) / `disclosure:note-text-updated`(5)。前两者与同步无关；
   * 后者的消费方 `useNoteRefresh.onDisclosureNoteTextUpdated` 仅调 `fetchDetail`
   * 刷新界面，且首行 `if (!currentNote.value) return`（附注页未打开直接返回）——
   * **完全不推数据落库**。此前把 emit 计入链路，导致缺口被低估为 27。
   */
  function hasOwnSyncPath(t: TabInfo): boolean {
    return (
      t.hasSyncFn ||
      t.hasCall ||
      t.src.includes('sync-from-workpaper') ||
      t.src.includes('syncFromWorkpaper')
    )
  }

  /**
   * 含**委托解析**：薄壳（`v-bind="$props"` 单标签）继承被委托 Base 的链路判定。
   * 深度上限 3 防环。
   */
  function hasAnySyncPath(t: TabInfo, depth = 0): boolean {
    if (hasOwnSyncPath(t)) return true
    if (depth >= 3 || !t.delegatesTo) return false
    const target = TABS.find((x) => x.path === t.delegatesTo)
    if (!target) {
      // 委托目标不在披露 Tab 集合内（命名不含 TabDisclosure）→ 直接读文件判定
      try {
        const src = readFileSync(t.delegatesTo, 'utf8')
        return (
          src.includes('syncToDisclosureNotes') ||
          src.includes('scheduleAutoSync(') ||
          src.includes('sync-from-workpaper')
        )
      } catch {
        return false
      }
    }
    return hasAnySyncPath(target, depth + 1)
  }

  it('每个无同步链路的披露 Tab 都必须已登记（豁免或缺口二者之一）', () => {
    const actual = TABS.filter((t) => !hasAnySyncPath(t)).map((t) => t.name).sort()
    const unexpected = actual.filter((n) => !ALL_DECLARED_NO_SYNC.includes(n))
    expect(
      unexpected,
      `以下披露 Tab 完全没有同步到附注的链路且未登记：${unexpected.join(', ')}。` +
        `披露数据会停在 checklist_responses，附注模块永远拿不到。` +
        `\n若确属有意无链路 → 加入 PERMANENT_EXEMPT 并写明源模板/附注模板依据；` +
        `若是待补缺口 → 加入 SYNC_PATH_GAP 并写明 owner spec。`,
    ).toEqual([])
  })

  it('SYNC_PATH_GAP 中已补齐链路的条目必须移出（缺口清单只许缩）', () => {
    const fixed = SYNC_PATH_GAP.filter((n) => {
      const t = TABS.find((x) => x.name === n)
      return t && hasAnySyncPath(t)
    })
    expect(
      fixed,
      `以下 Tab 已有同步链路，请从 SYNC_PATH_GAP 移出：${fixed.join(', ')}`,
    ).toEqual([])
  })

  /**
   * 🔴 与上一条**方向相反**：`PERMANENT_EXEMPT` 里的条目出现链路是**真缺陷**，不是好事。
   *
   * 拆表前这两种情形混在同一条断言里（「已补齐的必须移出」），于是
   * 「有人给 L2 接了链路」和「有人给 L4 接了链路」会给出同一句提示
   * ——前者是**要撤销的错误接线**（L2 与 K3 §五、42 同章节同表名，双推互相覆盖，
   * 谁最后保存谁赢、数据随机跳变），后者是**该庆祝的补齐**。
   * 语义相反的两件事共用一条判据，等于把最贵的一类事故降级成了待办提醒。
   */
  it('PERMANENT_EXEMPT 中的条目不得出现同步链路（接了就是撞章节/造虚构章节）', () => {
    const wired = PERMANENT_EXEMPT.filter((n) => {
      const t = TABS.find((x) => x.name === n)
      return t && hasAnySyncPath(t)
    })
    expect(
      wired,
      `以下 Tab 是**永久豁免**却接上了同步链路：${wired.join(', ')}。\n` +
        `后果不是「多一个页面」而是数据事故 —— H5 Listed / N4 Soe 会**凭空新建虚构章节**` +
        `（附注模板里根本没有该章节）；L2 两版会与 K3 §五、42/§八、42 的` +
        `「应付利息」子表**同名互相覆盖**。\n` +
        `请撤销接线；若确认准则口径已变 → 先改 note_template_variant_matrix.json，` +
        `再把条目从 PERMANENT_EXEMPT 移到 SYNC_PATH_GAP。`,
    ).toEqual([])
  })

  it('两张登记表每条都能在代码库中找到对应文件（防清单腐烂）', () => {
    const missing = ALL_DECLARED_NO_SYNC.filter((n) => !TABS.some((t) => t.name === n))
    expect(missing, `清单中的文件已不存在，请更新：${missing.join(', ')}`).toEqual([])
  })

  it('两张登记表不得有重复条目（同一 Tab 不能既豁免又是缺口）', () => {
    const dup = PERMANENT_EXEMPT.filter((n) => SYNC_PATH_GAP.includes(n))
    expect(
      dup,
      `以下条目同时出现在 PERMANENT_EXEMPT 与 SYNC_PATH_GAP：${dup.join(', ')}。` +
        `「有意无链路」与「待补缺口」互斥，必须二选一。`,
    ).toEqual([])
  })

  // 只允许变短：G 循环批1 补 11 条 → 49；F4 两条补齐（f-cycle-disclosure-parity R6）→ 47；
  // N 循环税务类补 5 条（N2×2 / N4 上市 / N5×2，n-cycle-tax-disclosure-alignment）→ 42
  // （N4 国企按源模板「附注披露信息：无」豁免留在清单，理由见常量注释）
  // 再删 N3 自造披露 Tab（源模板无披露 sheet，披露与 N1 共节）→ 41
  // H6×2 改 v-bind="$props" 委托到 Base → 39；H4 Soe 补齐 → 38
  // H7×2 一度接线后**撤回**（源模板转置矩阵，需结构对齐重建，不做自造）→ 回 40
  // L7×2 + L8×2 补齐 → 36（L2×2 / M1×2 仍在清单但已登记豁免理由：披露归 K3 章节）
  // L6×2 补齐 → 34；L5×2 补齐 → 30
  // M 循环批 4：M4×2 / M5×2 / M7×2 补齐（标准权益变动表）→ 24
  //   （M1×2 豁免归 K3、M2/M3/M6/M8/M9/M10 结构不同构留清单）
  // H7×2 整体重建后补齐（h7-biological-assets-disclosure-rebuild）→ 21
  // J2×2 补齐（disclosure-sync-path-buildout 批6）→ 19
  // M1×2 + M2×2 + M3×1 + M6×2 + M8×2 + M10×2 补齐（m-cycle spec Wave 1~2）→ 8
  // M9×2 补齐（Task 12）→ 6 = 4 永久豁免 + 2 真实缺口 → 自此拆两表分别设界

  /**
   * 🔴 天花板而非等值 —— **只许缩不许扩**。
   *
   * 原判据是 `expect(MISSING_SYNC_PATH.length).toBe(6)`，等值型的两个代价：
   * ① 补齐一个 Tab（把条目从清单移出，**正确的改进**）会打红这条，
   *    于是补齐者被迫顺手改数字，判据从「防线」退化成「记账」；
   * ② 反过来，往清单里**加**一条（绕过守卫）只要同时把 6 改成 7 也能全绿
   *    —— 等值断言对「变长」和「变短」一视同仁，而这两件事一个是事故一个是进步。
   *
   * 天花板则只在**变长**时打红，且打红时提示明确指向「不许绕过」。
   * 变短永远不会打红，因此不会再有人为了让测试变绿而去改数字。
   */
  const MAX_PERMANENT_EXEMPT = 4
  const MAX_SYNC_PATH_GAP = 2

  it('PERMANENT_EXEMPT 只许缩不许扩（新增披露 Tab 不得靠加豁免绕过守卫）', () => {
    expect(
      PERMANENT_EXEMPT.length,
      `永久豁免清单从 ${MAX_PERMANENT_EXEMPT} 条增长到 ${PERMANENT_EXEMPT.length} 条。` +
        `\n豁免必须有源模板 / 附注模板依据（openpyxl 读 sheetnames 或 ` +
        `note_template_variant_matrix.json 的 null 声明），不是「暂时没空接」的借口。` +
        `\n若确实新增了有依据的豁免 → 连同依据一起下调本上限。`,
    ).toBeLessThanOrEqual(MAX_PERMANENT_EXEMPT)
  })

  it('SYNC_PATH_GAP 只许缩不许扩（缺口不得新增）', () => {
    expect(
      SYNC_PATH_GAP.length,
      `真实缺口从 ${MAX_SYNC_PATH_GAP} 条增长到 ${SYNC_PATH_GAP.length} 条。` +
        `新增披露 Tab 必须自带同步链路，不得往缺口表里加。`,
    ).toBeLessThanOrEqual(MAX_SYNC_PATH_GAP)
  })

  /**
   * 🔴 **可收敛目标** —— 拆表后才能表达的断言。
   *
   * 拆表前「缺口应为 0」这个目标不可表达：清单里永远有 4 条永久豁免，
   * 非空是常态，于是「还差多少」这个真正要紧的数字被永久遮蔽。
   * 拆表后 `SYNC_PATH_GAP` 归零是**可达且应达**的终点 —— L4 两版补齐时这条转绿。
   *
   * 现在故意让它以 `toBeLessThanOrEqual` 而非 `toBe(0)` 表达，是因为 L4 需要
   * 结构对齐重建（两级表头 9 列 + 定性披露段，同 H7 量级），owner spec
   * `l-cycle-extraction-formula-and-disclosure-completion` 尚未排到。
   * 一旦补齐，把上限改 0 即锁死。
   */
  it('真实缺口有明确终点（L4 两版补齐后应归零）', () => {
    expect(
      SYNC_PATH_GAP.filter((n) => !n.startsWith('L4')),
      `除 L4 两版外不应再有未接链路的缺口；多出来的条目说明有 Tab 被漏接：` +
        `${SYNC_PATH_GAP.filter((n) => !n.startsWith('L4')).join(', ')}`,
    ).toEqual([])
  })

  /**
   * 🔴 宿主必须给披露 Tab 传 `projectId` —— 漏传 = 同步（含自动同步）**永久静默失败**。
   *
   * `syncToDisclosureNotes` 首行就是 `if (!props.projectId) return`，而披露组件不会
   * 因缺 prop 崩溃，只在控制台留一条 `Missing required prop` 警告 → vitest 与
   * `get_diagnostics` 都查不出。G9 两个薄壳曾因此让同步按钮永久 disabled；
   * 2026-07-30 浏览器实测发现 N2 / N4 / N5 三个宿主同样漏传（已修）。
   *
   * 判定：宿主模板里的 `<XTabDisclosure*>` 使用点必须有 `:project-id`
   * （或 `v-bind="$props"` 整体转发）。
   */
  it('宿主给披露 Tab 传了 projectId（漏传 = 同步永久静默失败）', () => {
    const TAG_RE = /<([A-Z]\w*TabDisclosure\w*)\b((?:[^<>]|\n)*?)\/?>/g
    const offenders: string[] = []
    let usages = 0
    for (const p of walkVue(WP_ROOT)) {
      const src = readFileSync(p, 'utf8')
      const tpl = /<template>([\s\S]*?)<\/template>/.exec(src)?.[1]
      if (!tpl) continue
      for (const m of tpl.matchAll(TAG_RE)) {
        const [, tag, attrs] = m
        usages += 1
        if (/v-bind="\$props"/.test(attrs)) continue
        if (/:project-id|:projectId/.test(attrs)) continue
        offenders.push(`${p.split(/[\\/]/).pop()} → <${tag}>`)
      }
    }
    // 防正则失效导致空转
    expect(usages, '未扫到任何披露 Tab 使用点，正则可能失效').toBeGreaterThan(100)
    expect(
      offenders,
      '以上宿主未向披露 Tab 传 projectId → 同步按钮点了没反应、自动同步永不落库',
    ).toEqual([])
  })

  it('源模板无披露 sheet 的循环不得有披露 Tab（防自造内容污染他人附注章节）', () => {
    const offenders: string[] = []
    for (const [cycle, reason] of Object.entries(CYCLES_WITHOUT_DISCLOSURE)) {
      // 只认「循环号 + 非数字」的前缀，避免 N3 误伤 N30（若将来有）
      const re = new RegExp(`^${cycle}(?![0-9])\\w*TabDisclosure`)
      const hit = TABS.filter((t) => re.test(t.name)).map((t) => t.name)
      if (hit.length) offenders.push(`${cycle}: ${hit.join(', ')}（${reason}）`)
    }
    expect(
      offenders,
      '这些循环源模板没有披露 sheet，造披露 Tab 等于自造披露内容，'
        + '一旦接上同步链路就会污染与其共节的别的循环的附注章节',
    ).toEqual([])
  })

  it('反向自检：谓词能抓住真实存在的披露 Tab（防上一条空转）', () => {
    const re = new RegExp('^N5(?![0-9])\\w*TabDisclosure')
    expect(TABS.filter((t) => re.test(t.name)).length).toBeGreaterThan(0)
  })

  it('委托解析生效：薄壳继承 Base 的链路判定（G10/G11 不得被虚报）', () => {
    for (const name of [
      'G10TabDisclosureListed.vue',
      'G10TabDisclosureSOE.vue',
      'G11TabDisclosureListed.vue',
      'G11TabDisclosureSOE.vue',
    ]) {
      const t = TABS.find((x) => x.name === name)!
      expect(t.delegatesTo, `${name} 应被识别为薄壳`).toBeTruthy()
      expect(hasOwnSyncPath(t), `${name} 自身不应有同步代码`).toBe(false)
      expect(hasAnySyncPath(t), `${name} 应通过委托继承 Base 的链路`).toBe(true)
    }
  })

  // 反向自检用替身：不依赖某个真实循环的当前状态（G9 曾用于此，补齐后会假红）
  it('委托解析不得误判：委托目标无链路时仍算缺口', () => {
    const stub: TabInfo = {
      name: 'StubTabDisclosureListed.vue',
      path: join(WP_ROOT, 'stub', 'StubTabDisclosureListed.vue'),
      src: '<template><Base variant="listed" v-bind="$props" /></template>',
      hasSyncFn: false,
      hasImport: false,
      hasCall: false,
      delegatesTo: join(WP_ROOT, 'stub', 'BaseWithoutSync.vue'), // 不存在 → 读不到 → false
    }
    expect(hasOwnSyncPath(stub)).toBe(false)
    expect(hasAnySyncPath(stub)).toBe(false)
  })

  it('委托识别只认单标签 + v-bind="$props"（多标签模板不算薄壳）', () => {
    expect(
      resolveDelegate(
        '<template><A v-bind="$props" /><B /></template>\nimport A from "./A.vue"',
        join(WP_ROOT, 'x.vue'),
      ),
    ).toBeNull()
    expect(
      resolveDelegate(
        '<template><A variant="listed" /></template>\nimport A from "./A.vue"',
        join(WP_ROOT, 'x.vue'),
      ),
    ).toBeNull()
  })

  /**
   * 🔴 平台级：禁止 `_xxxMounted` 一次性防护（2026-07-30 浏览器实测确认是 bug）。
   *
   * ```ts
   * let _xxxMounted = false
   * watch([...], () => { if (!_xxxMounted) { _xxxMounted = true; return }
   *                     autoSync.scheduleAutoSync(syncToDisclosureNotes) })
   * ```
   *
   * 防护的消耗时机取决于「数据是否已加载」：首次挂载时 `allResponses` 异步填充让
   * computed 变化、watch 触发一次 → 防护被消耗（符合设计意图）；但**切走再切回**时
   * 数据已在内存、computed 不变、watch 不触发 → 防护未被消耗 → 吞掉用户回到本页后的
   * **第一次真实编辑**（实测：`checklist_responses` 已写入但 `_last_sync_at` 不变）。
   * Vue `watch` 默认 `immediate:false`，挂载本身不触发，故该防护从一开始就不必要。
   *
   * 清除脚本：`backend/scripts/fix/fix_disclosure_mounted_guard.py`（带 `--check`）。
   */
  const MOUNTED_GUARD_RE = /if \(!(_\w*Mounted)\)\s*\{\s*\1\s*=\s*true;?\s*return\s*\}/
  const MOUNTED_DECL_RE = /\blet _\w*Mounted\s*=\s*false/

  it('禁止 `_xxxMounted` 一次性防护（会吞掉「切走再切回后的第一次编辑」）', () => {
    const offenders = TABS.filter((t) => MOUNTED_GUARD_RE.test(t.src)).map((t) => t.name)
    expect(
      offenders,
      `以下 Tab 仍有一次性防护：${offenders.join(', ')}；` +
        `请跑 python backend/scripts/fix/fix_disclosure_mounted_guard.py`,
    ).toEqual([])
  })

  it('一次性防护的声明也不得残留（死变量）', () => {
    const offenders = TABS.filter((t) => MOUNTED_DECL_RE.test(t.src)).map((t) => t.name)
    expect(offenders).toEqual([])
  })

  it('自检替身：守卫正则能命中真实写法（防正则失效导致空转）', () => {
    const sample = `let _l1SoeMounted = false
watch([a], () => {
  if (!_l1SoeMounted) { _l1SoeMounted = true; return }
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
})`
    expect(MOUNTED_GUARD_RE.test(sample)).toBe(true)
    expect(MOUNTED_DECL_RE.test(sample)).toBe(true)
    // 不误伤：正常的 onMounted 钩子与普通布尔变量
    expect(MOUNTED_GUARD_RE.test('onMounted(() => { load() })')).toBe(false)
    expect(MOUNTED_DECL_RE.test('let isMountedRef = false')).toBe(false)
  })

  it('自动同步的触发条件不得只监听提示横幅类状态', () => {
    const offenders: string[] = []
    for (const t of TABS) {
      if (!t.hasCall) continue
      const sources = watchSourcesFor(t.src)
      if (sources.length === 0) continue // 非 watch 触发（如 persistXxx 内直接调）→ 合规
      // 若**全部** watch 源都只是横幅类状态 → 视为未真正接入
      const allBannerOnly = sources.every((s) => {
        const hasBanner = BANNER_ONLY_SOURCES.some((b) => s.includes(b))
        const hasOther = /[A-Za-z_$][\w$]*/.test(s.replace(new RegExp(BANNER_ONLY_SOURCES.join('|'), 'g'), ''))
        return hasBanner && !hasOther
      })
      if (allBannerOnly) offenders.push(t.name)
    }
    expect(
      offenders,
      `以下 Tab 的自动同步只监听「上游已更新」横幅，用户自己改数据不会触发（F2 曾如此）：${offenders.join(', ')}`,
    ).toEqual([])
  })
})

describe('F2 披露 Tab 自动同步触发条件（定点回归）', () => {
  const listed = TABS.find((t) => t.name === 'F2TabDisclosureListed.vue')!
  const soe = TABS.find((t) => t.name === 'F2TabDisclosureSoe.vue')!

  it('两个 Tab 都已接入', () => {
    expect(listed.hasCall).toBe(true)
    expect(soe.hasCall).toBe(true)
  })

  it.each([
    ['上市', 'listed'],
    ['国企', 'soe'],
  ])('%s Tab 不再只监听 dataUpdatedVisible', (_label, key) => {
    const t = key === 'listed' ? listed : soe
    expect(t.src).not.toMatch(/watch\(dataUpdatedVisible,\s*\(v\)\s*=>\s*\{\s*if \(v\) autoSync\.scheduleAutoSync/)
  })

  it('上市 Tab 监听全部 8 个表格数据源 + 6 个文本域', () => {
    const sources = watchSourcesFor(listed.src).join(' ')
    for (const s of [
      'section1Rows', 'section2Rows', 'section2QualRows',
      's3EndRows', 's3PriorRows', 's5Rows', 's6Rows', 's7Rows', 'drRows',
      'noteCategory', 'noteNrv', 'noteProvision', 's4BorrowText', 's4AmortText', 'noteRe',
    ]) {
      expect(sources, `上市 Tab 自动同步未监听 ${s}`).toContain(s)
    }
  })

  it('国企 Tab 监听全部表格数据源 + 5 个文本域', () => {
    const sources = watchSourcesFor(soe.src).join(' ')
    for (const s of [
      'section1Rows', 'section2Rows', 'drRows',
      'noteCategory', 's3BorrowText', 's4AmortText', 'noteText', 'landNote',
    ]) {
      expect(sources, `国企 Tab 自动同步未监听 ${s}`).toContain(s)
    }
  })

  it.each([
    ['上市', 'listed'],
    ['国企', 'soe'],
  ])('%s Tab 不得用 mounted 一次性防护（会吞掉「切走再切回后的第一次编辑」）', (_label, key) => {
    // 🔴 浏览器实测（2026-07-30）：防护的消耗时机取决于「数据是否已加载」。
    // 首次挂载时 allResponses 异步填充 → computed 变化 → 消耗掉防护（符合设计意图）；
    // 但切走再切回时 allResponses 已有值 → computed 不变 → watch 不触发 → 防护未消耗
    // → 吞掉用户回到本页后的第一次真实编辑（实测：checklist_responses 已存但附注
    // `_last_sync_at` 不变；同一挂载内再改一次才同步）。
    // Vue watch 默认 immediate:false，挂载本身不触发，故无需防护。
    const t = key === 'listed' ? listed : soe
    expect(t.src).not.toMatch(/_f2\w*SyncMounted/)
    expect(t.src).not.toMatch(/if \(![_a-zA-Z]*Mounted\)\s*\{[^}]*return[^}]*\}\s*\n?\s*autoSync\.scheduleAutoSync/)
  })
})
