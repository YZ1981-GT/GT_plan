# Implementation Plan: 函证域孤儿收口与替代程序金额格式

## Overview

收口 `g0-confirmation-source-alignment` Task 23 复盘的 4 条建议。三条是代码改动（两条落在七枢纽共享文件），一条是流程判据固化。

**并发边界**：`f0-confirmation-linkage-and-structural-enhancement`（含 `[-]`/`[~]`，用户已中止实测轮）也动 `GtConfirmationSummary.vue`。本 spec 对该文件只加**一个渲染块 + 一个 emit 声明**，`str_replace` 最小 hunk，禁重排。

**不做**：H0/K0/L0 三个同族 ImportExport 孤儿包装（只登记进基线）· 存量 `el-input-number` 全库替换 · 两张 G0 差异表可编辑格换 `WpAmountInput`。

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 1, "name": "G0 孤儿收口", "tasks": ["1", "2", "3", "4"] },
    { "wave": 2, "name": "跨表导航接宿主", "tasks": ["5", "6"] },
    { "wave": 3, "name": "替代程序金额格式", "tasks": ["7", "8", "9", "10"] },
    { "wave": 4, "name": "平台守卫 + 回归 + 实测", "tasks": ["11", "12", "13"] }
  ],
  "notes": "Wave 1 与 Wave 3 都改 blockColumnConfigsG06.ts / GtConfirmationAlternativeG06.vue → 串行。Wave 2 独立可并行。Wave 4 依赖 1~3。"
}
```

## Tasks

### Wave 1 — G0 孤儿收口

- [x] 1. 删除三个零消费方 composable：`useG0DualMode.ts`（G0 十张 sheet 全注册为 `confirmation-*` HTML 组件，无 OO 双模式落点）· `useG0ImportExport.ts`（页面级 `CycleImportExportDropdown` 直接用共享 `useWorkpaperImportExport`，本包装重复）· `useG0ReviewDialogProvide.ts`（`openReviewDialog` 由 `useWorkpaperScaffold` → `useWorkpaperReviewProvide` → `useReviewDialogProvider` 链统一 provide；**实测更正**：`GtWpRenderer.vue` 全文不含 `ReviewDialog` 字样，平台 40+ 处宿主注释写的「由 Runtime Boundary(GtWpRenderer) 统一 provide」是过时说法）。删后全仓 grep 三个符号应 0 命中（含 `components.d.ts`）。
  - _Requirements: 3.1, 3.2, 3.3_

- [x] 2. 把 `composables/useG0FormulaEngine.spec.ts` 移到 `composables/__tests__/`，修正相对 import 深度并复跑该文件。
  - _Requirements: 3.7_

- [x] 3. `g0DiffSourceManifest.ts` 接线：新增纯函数 `diffColumnKind(table, field)`；两张差异表的**只读派生格**按 kind 格式化（`amount` → `prefs.fmt` / `number`·`ratio` → 不做金额单位换算）。可编辑格保持现状。
  - _Requirements: 3.4, 3.5_

- [x] 4. `CYCLE_IMPORT_EXPORT.g0.sheets` **不改值**，加注释说明 `G0-3S` 是后端 API sheet key（非 wp_code）+ 加守卫与后端 `_SHEET_NAME_MAP` 键集双向锁死。**立项判断已被勘查推翻**（原以为是错值要替换）。
  - _Requirements: 3.8_

### Wave 2 — 跨表导航接宿主

- [x] 5. `CrossWorkpaperNav.vue` 两处改动：抽 `locatorOf(item)`（同工作簿取 `sheetName`，否则取 `wpCode.split('/')[0]`）· `handleNavigate` 去掉 `!item.exists` 早退（`exists` 仅驱动视觉与 tooltip），统一 emit `navigate-sheet`。
  - _Requirements: 1.3, 1.4, 1.5_

- [x] 6. `GtConfirmationSummary.vue` 挂载导航条：`defineEmits` 加 `navigate-sheet`（加法式）；列表视图 `ConfirmationDetail` 之后渲染 `<CrossWorkpaperNav>`，传 `confirm-index` / `wp-code` / `current-wp-code`（= `getCycleConfirmationMeta(wpCode).summaryCode`），事件向上转发。守卫 Property 1/2/3。
  - _Requirements: 1.1, 1.2, 1.6, 1.7_

### Wave 3 — 替代程序金额格式（七枢纽）

- [x] 7. `BlockColumnDef` 加可选字段 `render?: 'amount'`（加法式，缺省行为不变）；新建非金额登记表 `blockColumnAmountRegistry.ts`（17 条实测明细 + 每条 `reason`）。
  - _Requirements: 4.1_

- [x] 8. `CheckBlock.vue` 三处按 `render` 分流：编辑态（`WpAmountInput` vs `el-input type=number`）· 只读态（`prefs.fmt` vs `formatPlainNumber`）· 合计行。非金额分支保持逐字节等价。
  - _Requirements: 4.2, 4.3, 4.4, 4.5_

- [x] 9. 给 8 个区块配置文件的 **76 个金额列**标 `render: 'amount'`（D0-5 7 / D0-6 7 / F0-5 11 / F0-6 12 / H0-5 6 含 `cap_cost` / K0-5 6 / K0-6 7 / G0-6 20），17 个非金额列不标。
  - _Requirements: 4.6, 4.7_

- [x] 10. `GtConfirmationAlternativeG06.vue`「余额数据」卡片 6 个金额输入改 `WpAmountInput`。
  - _Requirements: 4.9_

### Wave 4 — 平台守卫 + 回归 + 实测

- [x] 11. 新建渲染宿主存在性守卫 `orphanHostCoverage.spec.ts` + 基线 `orphanHostBaseline.ts`（只许缩短）。**实测推翻立项数字**：立项估「组件 0 / 模块 3」，实扫（930 候选消费方）得 **组件 2**（`E0SummaryLowerZone.vue`、`e0-send-list/SendListConsistencyPanel.vue`，均属 E0 侧另两个 spec）+ **模块 23**（6 枚举真源 / 5 个 `useConfirmation*` 与 `useE0BookAmounts`·`useEntitySuggestion` / K0·L0 两个 ImportExport 同族包装（**无 H0**）/ 两个 sendList 校验 / `confirmationColumnSourceManifest`·`confirmationLinkageMatrix`·`migrateDformToConfirmation`·`e0RestrictedToE1`·`k0LowerZoneSpec`·`useD01Linkage`·`alternativeBlockManifest`·`blockColumnAmountRegistry`）。含 4 项变异检验（新增无宿主组件 / 移除测试目录排除 / reason 占位词 / 已接线条目未移出，全部准确打红）。
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

- [x] 12. 金额语义守卫 `blockColumnAmountRender.spec.ts`（Property 9/10/11/12）+ G0 孤儿收口守卫 `g0OrphanClosure.spec.ts`（Property 6/7/8）。每条配反向自检，并逐个做变异检验。
  - _Requirements: 4.8, 4.10, 3.6, 6.2, 6.3_

- [x] 13. 回归 + 浏览器实测 + 实测残留只读复核：`confirmation` 域全量前端测试无新增失败（预存在基线单独列出）· G0-1 选中行后导航条出现并点击切页成功 · G0-6「金额」列输 `1234567.5` 显示 `1,234,567.50` 且同表「数量」列不带小数与单位换算 · 只读查询确认七枢纽函证底稿无「实测」残留 · 测后复原数据并清 `tmp_*`。
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 6.4_

## Notes

### 设计判断留证

- **导航条不传 `existsMap`**：当前没有廉价数据源判「该笔函证在目标 sheet 有无数据」（`GtConfirmationSummary` 只拿到自己 sheet 的 `htmlData`）。放开 `exists` 门后全部 chip 中性可点，`GtWpRenderer` 未命中时已有 `ElMessage.info('未找到 sheet…')` 兜底 → 比「挂上去点不动」好。若日后要点亮，数据源应是 render-config 的 sheet 列表 + 各 sheet 载荷里该 `confirm_index` 是否出现。
- **为什么统一 emit `navigate-sheet` 而不保留 `navigate`**：六枢纽同为单 wp_code 多 sheet 工作簿，按 wp_code 跳会落到 render 出 `html_data=null` 的遗留单 sheet 记录（memory 已登记）；而 `resolveSheetNameByDeepLink` 第 3 级是归一后缀匹配，传 `H0-1` 能命中 `函证结果汇总表H0-1` → 单出口即可覆盖七枢纽。`navigate` 事件声明保留，不破坏潜在外部监听。
- **`g0DiffSourceManifest.ts` 接线而非删除**：它是两张差异表逐列 `kind` 的单一真源（`amount`/`number`/`ratio`/`text`/`enum`/`term`），删掉会连带删掉守卫保护。这也修正了复盘时「4 个孤儿全删」的判断 —— **判「孤儿该删还是该接」要看它是不是某维度的唯一真源**。
- **金额列用「显式标注 + 非金额登记表」而不是按 label 推断**：`金额`/`余额` 这类关键字虽覆盖 75/76，但 `cap_cost`（原值）靠关键字抓不到，而 `成交价`/`每股股利` 会被「价/利」误抓 → 按铁律「避免硬编码 = 单一真源 + 守卫与真源双向锁死」，两侧都显式声明并互相锁死。

### Wave 4 收口实录（2026-08-05，回归 + 浏览器实测 + 残留复核）

#### ① 回归（Requirement 6.4）

`npx vitest run confirmation --reporter=json --outputFile=<abs>.json`（子串过滤天然覆盖 `confirmation/**` ∪ `g0-confirmation/**`）：

**94 files / 2044 passed / 0 failed / success=true**（其中 `g0-confirmation` 12 files / 316 例）。另跑 `cycleImportExportRegistry`（路径不含 `confirmation` 故不被该过滤命中）**1 file / 14 passed**。

**预存在失败清单 = 空**。判归属无需动用 traceback 判据（`numFailedTests=0`，无任何失败可归属）。本 spec 五个守卫全绿：`blockColumnAmountRender` 33 · `crossWorkpaperNavWiring` 25 · `orphanHostCoverage` 23 · `g0OrphanClosure` 25 · `cycleImportExportRegistry` 14 · 迁位后的 `useG0FormulaEngine` 9。清 tmp 后复跑这 6 个文件 **129/129 全绿**。

#### ② 浏览器实测：G0-1 跨表导航条（Requirement 1.1 / 1.3 / 1.5）

项目 `2aa00f57` · 底稿 **`wp_code='G0'` 整册**（wp `b09ec83f`，render 出 10 个 sheet + 完整 Excel，与 Excel 可见 tab 逐字一致）。

| 步骤 | 结果 |
|---|---|
| 打开 G0-1（空底稿） | 命中 onboarding，`.cross-workpaper-nav` **count=0** —— 与 Property 3 一致 |
| 点「+ 新增函证对象」 | 矩阵/下区/审计说明/结论全部渲染；导航条仍 **0**（该行 `confirm_index` 为空） |
| 选中行（`current-row`，`ConfirmationDetail` 已渲染）但索引号仍空 | 导航条仍 **0** —— 组件自身 `v-if="confirmIndex"` 生效（R1.2） |
| 在完整表格视图给该行填 `询证函索引号 = G0-001` → 切回列表视图 → 选中 | **`.cross-workpaper-nav` count=1**，8 个 chip：`G0-2 / G0-1(current) / G0-3 / G0-7 / G0-5 / G0-4 / G0-6 / G0-8` |
| chip tooltip | 三处源模板笔误按「定位用 tab 名 / 展示用目录索引号 + tooltip 标注」渲染：G0-5「差异调节表（源模板 tab 名索引号为 G0-4，底稿目录为 G0-5，以目录为准）」· G0-4「证券差异专表（…tab 名为 G0-3…）」· G0-8「舞弊风险评价（…tab 名为 F0-8…）」 |
| 点击非当前页 chip `G0-6` | **切页成功**：编制信息「索引号：G0-1」→「索引号：**G0-6**」，活动页签变「🔄 替代程序检查表G0-6」，**无 `ElMessage.info('未找到 sheet…')` 兜底**（直接命中） |
| `exists` 门（R1.5） | 全部 chip 带 `--disabled` 类但计算样式 `pointer-events: auto` / `cursor: pointer`，tooltip 写「本笔暂无数据，点击可前往编制」→ **`exists` 只驱动视觉，点击不被挡** |

→ 「链条上游合格、整条链仍是死的」已被修复，用户可达。

#### ③ 浏览器实测：G0-6 金额 vs 数量（Requirement 4.2 / 4.4 / 4.9）

G0-6「替代程序检查表」→ 新增被投资单位 → 区块③「期后出售/赎回检查」新增行。**同一张表内的实际显示值**：

| 列 | field | 配置 | DOM 形态 | 输入 | **实际显示** |
|---|---|---|---|---|---|
| 金额（投资协议/交易确认单/交割单） | `deal_amount` | `render:'amount'` | `type="text"` + `.wp-amount-input` | `1234567.5` | **`1,234,567.50`** |
| 卖出/赎回数量 | `sell_qty` | 无 `render` | `type="number"`，无 `.wp-amount-input` | `1200` | **`1200`**（不带小数、不带单位换算） |
| 成交价 | `trade_price` | 无 `render` | `type="number"` | — | 同上分支 |
| 成交金额 | `trade_amount` | `render:'amount'` | `.wp-amount-input` | `5000000` | `5,000,000.00` |
| 原始成本 | `original_cost` | `render:'amount'` | `.wp-amount-input` | `3000000.25` | `3,000,000.25` |
| 处置损益（**只读派生**） | `disposal_gain` | `render:'amount'`+`editable:false` | 纯文本格 | 派生 | **`1,999,999.75`** = 5,000,000 − 3,000,000.25 → R4.4 只读分支亦按 render 分流 |

同行内 9 个金额格全部 `.wp-amount-input`、2 个数量/单价格全部 `type="number"` → **`render` 维度真的在分流，不是一刀切**（R4.4 核心）。
R4.9 顺带实测：G0-6「余额数据」卡片 6 个输入（年初余额/本期增加/本期减少/期末余额/投资收益/公允价值变动）**全部 `type="text"` + `.wp-amount-input`**，显示 `0.00`。

#### ④ 实测残留只读复核（Requirement 5.1/5.2/5.3，Property 13）

postgres MCP **只读**（`working_paper` 无 `wp_code`，须 JOIN `wp_index`）：

```sql
-- Q1 parsed_data 残留
SELECT wi.wp_code, wp.id, wp.updated_at
FROM working_paper wp JOIN wp_index wi ON wi.id = wp.wp_index_id
WHERE wi.wp_code ~ '^(D0|E0|F0|G0|H0|K0|L0)'
  AND wp.parsed_data IS NOT NULL AND wp.parsed_data::text LIKE '%实测%';
-- → 0 行

-- Q2 checklist_responses 残留（三字段都查：conclusion / remark / item_id）
SELECT wi.wp_code, cr.item_id, cr.conclusion, cr.remark, cr.updated_at
FROM checklist_responses cr
JOIN working_paper wp ON wp.id = cr.wp_id
JOIN wp_index wi ON wi.id = wp.wp_index_id
WHERE wi.wp_code ~ '^(D0|E0|F0|G0|H0|K0|L0)'
  AND (coalesce(cr.conclusion,'') LIKE '%实测%'
    OR coalesce(cr.remark,'')     LIKE '%实测%'
    OR cr.item_id                 LIKE '%实测%');
-- → 0 行

-- Q3 正对照（防 JOIN 写错导致「0 行」是假阴性）
SELECT count(*) total_hub_wp, count(DISTINCT wi.wp_code) codes,
       count(*) FILTER (WHERE wp.parsed_data IS NOT NULL) with_parsed
FROM working_paper wp JOIN wp_index wi ON wi.id = wp.wp_index_id
WHERE wi.wp_code ~ '^(D0|E0|F0|G0|H0|K0|L0)';
-- → total_hub_wp=104 / codes=42 / with_parsed=15
```

**结论：七枢纽函证底稿无「实测」残留**。Q3 正对照证明扫描面非空（104 条 / 42 个 wp_code），故 Q1/Q2 的 0 行是真阴性而非 JOIN 写错。

七枢纽 `X0` 各有 1 条 `checklist_responses`（`{X0}-review-session-2026072507xxxx`，remark 是 AI 复核 session JSON），`created_at == updated_at == 2026-07-24`，属底稿生成期的复核会话记录，**不是实测产物**，未清除。

**登记（不属本 spec，未触碰）**：F0 底稿 `1d23aba1`（项目 `2aa00f57`）`parsed_data` 含 `函证结果汇总表F0-1` / `预付及采购替代程序F0-5`，`updated_at = 2026-08-04 23:03` —— 是并发会话 `f0-confirmation-linkage-and-structural-enhancement` Task 20.1 实测的产物（不含「实测」字样，故不触发 Property 13 的字面判据）。归该 spec 复原。

#### ⑤ 数据复原 + 清 tmp（Requirement 5.1 / 5.2）

**复原动作 = 零** —— 本轮实测**未产生任何落库足迹**，三方交叉证据：

1. 目标底稿 `b09ec83f` 实测后仍 `parsed_data IS NULL`、`updated_at = 2026-06-08 02:00:53`（**与 `created_at` 逐秒相同** = 仍是初始生成时间）、`checklist_responses` **0 行**。
2. 全库 90 分钟窗口写入计数：`working_paper` **0** / `checklist_responses` **0** / `wp_index` **0**。
3. 同表同类底稿常态旁证：另外 6 个 `X0` 整册底稿中未被实测触碰过的记录同样是 `parsed_data IS NULL`。

成因是平台既有未修 P0「函证完整表格视图的编辑永不落库」（`GtConfirmationSummary.handleGridUpdate` 只调 `data.updateField` 不 `emit('save')`），加上 G0-6 区块未点「保存」→ 本轮实测天然只读。**本轮独立复现了该 P0**（属七枢纽共享组件级决策，不在本 spec 范围）。

**tmp 清理**：删 **200** 个 / 保留 **172** 个。判据 = `名字授权 ∪（内容归属本 spec 且 mtime ≥ 三件套创建时间 2026-08-04 19:12 且无他 spec 特征）`，其余一律保留。
- 删：`tmp_t6_*`(25，Task 6) · `tmp_t9_*`(2，Task 9 标注脚本 apply/check 日志) · `tmp_t11_*`(53) · `tmp_t12_*`(17) · `tmp_t13_*`(本轮) · `tmp_task4_g0ie.bak` · `tmp_orphan_*` / `tmp_mut*` / `tmp_run[1-7]*` / `tmp_zz_*` / `tmp_g06_*` / `tmp_cb*` / `tmp_rg*` 等内容命中 `orphanHostBaseline`/`blockColumnAmountRegistry`/`CrossWorkpaperNav`/`CheckBlock` 且无他 spec 特征者。
- **保留**（并发会话在用 / 归属其它 spec / 无正面归属证据）：`tmp_f0_*`(36，f0 spec) · `tmp_task22_*`(6，sampling-compliance-closure) · `tmp_task31_*`(4，semantic-account-resolver) · `tmp_vite*`（用户点名 `tmp_vite2_out.md` 属 deliverable-lineage-*，整族保留） · `tmp_nav_*`（mtime 与并发 F0 会话窗口重叠，归属不确定） · `tmp_party*` / `tmp_pt*` / `tmp_h_audit*` / `tmp_h[345]out*` / `tmp_a3*` / `tmp_d3*` / `tmp_w6*` / `tmp_dump*` / `tmp_q_paths*` 等 mtime 早于本 spec 者 · 全部 `UNKNOWN`（无正面归属证据一律留下）。
- 清前先读了两个 `tmp_*restore*`（`tmp_restore_baseline.py` / `tmp_verify_restore.py` —— 它们是 Task 11 变异检验的还原脚本），并**独立复核** `orphanHostBaseline.ts` 无 `mutation-probe` 残留、`CrossWorkpaperNav` 只出现在文档注释与某条 `reason` 文字里而不是基线条目（正是本 spec 治的「符号级匹配假阴性」同款陷阱）。

#### ⑥ 顺带发现（未修，不属本 spec）

- **组件基线未清零，与 R2.4 / Property 4 的字面「基线为空」有差距**：`KNOWN_ORPHAN_COMPONENTS` 现有 **2** 条（`confirmation/E0SummaryLowerZone.vue` · `confirmation/e0-send-list/SendListConsistencyPanel.vue`），`KNOWN_ORPHAN_MODULES` **23** 条。Task 11 的守卫把这个差距**精确钉死**而不是放行：用例名直写「Req 2.4 目标为空，当前差距被精确钉死」+ 强制两条的 `owner` ∈ {`e0-confirmation-completion`, `e0-send-list-dedicated-components`} + 断言 `CrossWorkpaperNav.vue` 不在基线内 + 条目数上限 ≤2 只许缩短。判断合理（两条都是 E0 域、归属别的 spec），但**文档侧措辞与实现不一致**，宜在 requirements 里把 R2.4 改成「组件基线只许含归属其它 spec 的跨 spec 遗留且只许缩短」。
- **`/api/editing-locks/workpaper/{id}/heartbeat` 恒 500**（本轮 9 次全 500）→ 锁的 `heartbeat_at` 永不推进，只能靠 TTL 过期自愈；实测打开页面时平台顺带释放了 4 条 08-04 遗留的僵尸锁。本轮开的锁 `970598c4` 在关页后 `released_at` 仍为 NULL（同款僵尸），因 postgres MCP 只读未清理，下次打开该底稿会被自动释放。归 editing-locks 模块。

### 实测结论（Task 13，2026-08-04）

**环境**：前端 3030 / 后端 9980（health 路径是 `/api/health`，`/health` 返 404）· 项目 `2aa00f57` · wp `b09ec83f`（**必须用 `wp_code=G0` 整册**，单 sheet 遗留记录 render 出 `html_data=null`）。

**基线与复原**：实测前 `parsed_data IS NULL` / `updated_at = 2026-06-08 02:00:53.647970+00` / `checklist_responses = 0 行`。全程**未点「保存」**（列表视图与完整表格视图的编辑都只在内存），实测后三项与基线**逐字节一致**，硬刷新后二次核实仍一致 → **无需复原动作**。

| 验收项 | 结果 |
|---|---|
| `confirmation` 域全量回归 | **590 文件 / 2034 passed / 0 failed**（改造前 1905）→ 净增 129 例全通过，**零新增失败** |
| 导航条渲染 | G0-1 新增函证对象 → 选中行 → 完整表格填「询证函索引号」= `G0-1-1` → 回列表视图，`.cross-workpaper-nav` **出现**（改造前该组件全仓零渲染宿主 = 用户不可达） |
| 导航条内容 | 8 个 chip（G0-2/G0-1/G0-3/G0-7/G0-5/G0-4/G0-6/G0-8），当前页 G0-1 带 `--current`；**全部 `cursor: pointer`**（灰态也可点 = Task 5 去掉 `!item.exists` 早退的效果）；tooltip 带「本笔暂无数据，点击可前往编制」；三处源模板索引号笔误如实标注（G0-5 tab 名写 G0-4 / G0-4 tab 名写 G0-3 / G0-8 tab 名写 **F0-8**） |
| 导航条点击切页 | 点 `G0-6` → 活动页签由「✉️ 函证结果汇总表G0-1」变「🔄 替代程序检查表G0-6」，无错误提示 |
| Task 10 余额卡片 | 「年初余额」输 `1234567.5` → 失焦显示 **`1,234,567.50`**，`aria-label` 正确；6 个余额字段全为 `WpAmountInput` |
| Task 8/9 区块分流 | G0-6「④源外增强」新增一行后逐列核对：**9 个金额列**（金额/市值/应收股利金额/到账金额/红利税扣缴/实收金额/报价值/账面VS报价差异/交易金额）= `WpAmountInput`（a11y 树里是 `textbox`）；**「数量」「每股股利」= `input[type=number]`**（a11y 树里是 `spinbutton`），恰为登记的非金额列 |
| 金额 vs 非金额对照 | 同输 `1234567.5`：市值显示 **`1,234,567.50`**（千分符+2位小数）· 数量显示 `1234567.5`（原样，无千分符无单位换算） |
| 合计行分流 | `合计： 金额：- 市值：1,234,567.50 应收股利金额：- 交易金额：-` → 金额列带千分符，未填列显示 `-` 而非 `0`（宁缺勿造） |
| 七枢纽实测残留只读复核 | `wp_code ~ '^(D0\|E0\|F0\|G0\|H0\|K0\|L0)(-\|$)'` 共 15 条有 `parsed_data`，**无一含「实测」字样或探针金额 `1234567`**；`checklist_responses` 仅 7 条 2026-07-24 的 `X0-review-session-*`（非本 spec 产物）→ 零残留 |

**变异检验（8 项全部准确打红并还原）**：Task 11 四项（新增无宿主组件未登记 / 移除测试目录排除 / reason 占位词 / 已接线条目未移出基线）· Task 12 四项（去掉一个金额列的 `render` / `CheckBlock` 换回 `el-input` / G0-6 余额输入改回 `el-input type=number` / `composables/` 混入 `.spec.ts`）。

### 实测中新发现（超出本 spec 范围，只登记）

- **平台 40+ 处宿主注释与代码不符**：写着「`openReviewDialog` 由 Runtime Boundary(`GtWpRenderer`) 统一 provide」，而 `GtWpRenderer.vue` 全文（40512 字符）**不含 `ReviewDialog` 字样**。真链是 `useWorkpaperScaffold` → `useWorkpaperReviewProvide` → `useReviewDialogProvider.provide('openReviewDialog')`。`g0OrphanClosure.spec.ts` 已按代码实证钉住真链，并加一条反向自检：若 `GtWpRenderer` 哪天真 provide 了就打红，提醒同步修正那批注释。
- **合成事件驱动 `WpAmountInput` 无效**：`dispatchEvent(new Event('focus'))` 不触发 el-input 的 `@focus` → `focused` 恒 false → `display` 回退 `amountFormatter(0)` 并覆盖 DOM 值，表现为「输了变成 0.00」，**极易误判成组件缺陷**。判金额控件行为必须用真实交互（chrome-devtools 的 `fill`/`fill_form`）。
