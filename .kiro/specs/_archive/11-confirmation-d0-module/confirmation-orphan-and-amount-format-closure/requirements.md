# Requirements Document

## Introduction

本 spec 收口 `g0-confirmation-source-alignment` Task 23 浏览器实测复盘提出的 4 条建议。它们的共同点是**「代码写对了但用户拿不到」**：孤儿组件没有渲染宿主、孤儿模块没有消费方、共享列渲染器让金额格式在结构上不可能生效。

**为什么值得单独立 spec**：3 条落在**七枢纽共享文件**（`GtConfirmationSummary.vue` / `CrossWorkpaperNav.vue` / `alternativeD05/CheckBlock.vue`），第 3 条要改 **9 个区块列配置文件里 125 个 `type:'number'` 列**（D0-5 / D0-6 / F0-5 / F0-6 / G0-6 / H0-5 / K0-5 / K0-6 + 共享基准）。改动面跨 3+ 组件且影响 D0/E0/F0/G0/H0/K0/L0 七个循环，不能当「顺手修一下」。

**范围外（登记不做）**：
- `useH0ImportExport` / `useK0ImportExport` / `useL0ImportExport` 三个同族孤儿包装（属各自循环 spec；本 spec 只把它们登记进孤儿基线，禁止再增长）
- 存量 `el-input-number :formatter` 空操作的全库替换（memory 已登记「存量替换待单独 spec 收口」）
- 两张 G0 差异表的可编辑单元格从 `el-input-number` 换 `WpAmountInput`（同上）

## Glossary

| 术语 | 含义 |
|------|------|
| 七枢纽 | D0/E0/F0/G0/H0/K0/L0 七个函证循环，共用 `confirmation/` 下的组件与列注册表 |
| 渲染宿主 | 真正把某组件写进模板的 `.vue`（或 `htmlRendererRegistry` 注册项）。「有渲染宿主」≠「有代码引用」 |
| 孤儿组件 | 零渲染宿主的 `.vue`；用户在界面上永远看不到 |
| 孤儿模块 | 零非测试消费方的 `.ts`；其逻辑永不执行 |
| 「链条上游合格」 | A 有消费方 B、但 B 自己没有消费方 → 只断言 A 的守卫会误判整链健康（本 spec Property 4 修正之） |
| 区块（block） | 替代程序检查表的检查过程记录分区，由共享 `alternativeD05/CheckBlock.vue` 渲染，列定义来自各循环 `blockColumnConfigs*.ts` |
| `render: 'amount'` | 本 spec 新增的列语义标记；标了才走平台金额格式（千分符 + 单位偏好），缺省为普通数值 |
| 定位值 vs 展示值 | 跨表导航里 `sheetName`（源模板真实 tab 名，用于 `?sheet=` 定位）与 `label`（底稿目录索引号，用于展示）分离 |

## Requirements

### Requirement 1: 跨表导航条接入渲染宿主

**User Story:** 作为审计助理，我在函证汇总表选中一笔函证后，应当看到「本笔相关底稿」导航条并能点击切到对应 sheet；而不是这个组件写好了却全仓没人渲染。

#### Acceptance Criteria

1.1 WHEN `GtConfirmationSummary.vue` 处于列表视图且已选中某行 THEN 系统 SHALL 渲染 `CrossWorkpaperNav`，并传入 `confirmIndex` / `wpCode` / `currentWpCode` 三个已声明 prop。
1.2 WHEN 未选中行或选中行无 `confirm_index` THEN 系统 SHALL NOT 渲染导航条（由组件自身 `v-if="confirmIndex"` 保证），完整表格视图同样不渲染。
1.3 WHEN 用户点击任一导航项 THEN 系统 SHALL emit `navigate-sheet`，取值为 `sheetName ?? wpCode`，由 `GtWpRenderer.onChildNavigateSheet` 经 `resolveSheetNameByDeepLink`（原样 → 归一 → 归一后缀/包含三级）解析并切页。
1.4 WHERE 导航项的 `wpCode` 含 `/`（组合替代程序 `X0-5/X0-6`）THE 系统 SHALL 取 `/` 前的主编码作为定位值，SHALL NOT 把含斜杠的字面量传给 sheet 解析。
1.5 WHEN `existsMap` 未提供或某项为 false THEN 系统 SHALL 仍允许点击（`exists` 仅驱动视觉与 tooltip 文案），SHALL NOT 在 `!exists` 时静默 return。
1.6 WHEN 传入 prop THEN 系统 SHALL 从 `CrossWorkpaperNav` 的 `defineProps` 动态抽合法 prop 名比对调用点（防「传不存在的 prop = 静默失效」）。
1.7 WHEN 平台守卫运行 THEN 系统 SHALL 断言 `CrossWorkpaperNav.vue` 有真实渲染宿主，SHALL NOT 只断言其内部函数有消费方。

### Requirement 2: 渲染宿主存在性守卫（递归到宿主为止）

**User Story:** 作为平台维护者，我要让「A 有消费方 B、但 B 自己没有消费方」这类整链死代码在 CI 上打红，而不是等下一轮浏览器实测才发现。

#### Acceptance Criteria

2.1 WHEN 守卫运行 THEN 系统 SHALL 扫描函证域全部 `.vue` 组件（`confirmation/**` ∪ `g0-confirmation/**`），对每个组件判定是否存在**渲染宿主**（其它 `.vue` 的模板里出现 `<X` 或 `<x-y`，或 `htmlRendererRegistry` 注册）。
2.2 WHEN 某组件无渲染宿主且不在基线名单内 THEN 系统 SHALL 打红并列出组件路径。
2.3 WHERE 组件是 registry 注册的 componentType 入口 THE 系统 SHALL 视为有宿主（由 `htmlRendererRegistry.ts` 引用即算）。
2.4 WHEN 基线名单为空 THEN 系统 SHALL 通过（本 spec 目标是把函证域清零）。
2.5 WHEN 守卫运行 THEN 系统 SHALL 包含反向自检：对一个内联的「无宿主」替身路径断言判定为孤儿，证明扫描非恒真。
2.6 WHEN 守卫扫描 composable/模块（`.ts`）THEN 系统 SHALL 用**只许缩短的基线名单**登记既有孤儿（每条必须带理由），新增孤儿即打红。

### Requirement 3: G0 目录 4 个零消费方模块收口

**User Story:** 作为平台维护者，死代码要么删掉要么接上，不能留着让每次复盘重复提议。

#### Acceptance Criteria

3.1 WHEN 处置 `composables/useG0DualMode.ts` THEN 系统 SHALL 删除该文件，理由：G0 十张 sheet 全部注册为 `confirmation-*` HTML 组件，无 OnlyOffice 双模式落点。
3.2 WHEN 处置 `composables/useG0ImportExport.ts` THEN 系统 SHALL 删除该文件，理由：页面级 `CycleImportExportDropdown` 直接用共享 `useWorkpaperImportExport` + `CYCLE_IMPORT_EXPORT.g0.apiPrefix`，本包装是重复件。
3.3 WHEN 处置 `composables/useG0ReviewDialogProvide.ts` THEN 系统 SHALL 删除该文件，理由：`openReviewDialog` 已由 Runtime Boundary（`GtWpRenderer`）统一 provide，子组件直接用 `<GtReviewTrigger>`。
3.4 WHEN 处置 `g0DiffSourceManifest.ts` THEN 系统 SHALL **接线而非删除** —— 它声明了两张差异表逐列的 `kind`（`amount` / `number` / `ratio` / `text` / `enum` / `term`），是列语义的单一真源。
3.5 WHEN 两张差异表渲染只读派生金额格 THEN 系统 SHALL 按 manifest 的 `kind` 决定格式化：`amount` 走平台金额格式、`number`/`ratio` 不做金额单位换算。
3.6 WHEN 守卫运行 THEN 系统 SHALL 断言两张差异表模板里的列标签集合与 manifest 的 `label` 集合一致（归一全/半角括号后比对），且 manifest 有真实非测试消费方。
3.7 WHEN 处置 `composables/useG0FormulaEngine.spec.ts` THEN 系统 SHALL 移动到 `composables/__tests__/`，与全平台测试位置约定一致。
3.8 WHERE `CYCLE_IMPORT_EXPORT.g0.sheets` 含 `G0-3S` THE 系统 SHALL **保留该值不改** —— 勘查实证它是后端 `_SHEET_NAME_MAP` 的 **API sheet key**（映射到真实 tab 名 `函证差异核对表G0-3（证券投资）`），不是 `wp_code`；SHALL 加守卫钉死「registry 声明的 sheet ⊆ 后端 `_SHEET_NAME_MAP` 键集」并在注释写明该键的性质，防后来者按「`wp_index` 无 G0-3S」再次误判为错值。

### Requirement 4: 替代程序区块金额列千分符（七枢纽）

**User Story:** 作为审计助理，我在替代程序检查表录 1234567.5 应当看到 1,234,567.50；数量列不应被套上金额单位换算。

#### Acceptance Criteria

4.1 WHEN `BlockColumnDef` 声明列语义 THEN 系统 SHALL 新增可选字段 `render?: 'amount'`，缺省即非金额（加法式扩展，未标注列行为逐字不变）。
4.2 WHEN `CheckBlock.vue` 渲染 `type:'number'` 且 `render==='amount'` 的可编辑单元格 THEN 系统 SHALL 使用 `WpAmountInput`（失焦千分符 / 聚焦原始值 / 粘贴带逗号可解析 / 非法输入不写 NaN），SHALL NOT 使用 `<el-input type="number">`。
4.3 WHEN 渲染 `type:'number'` 且未标 `render==='amount'` 的单元格 THEN 系统 SHALL 保持 `<el-input type="number">` 不变。
4.4 WHEN 渲染只读态数值 THEN 系统 SHALL 对 `render==='amount'` 走平台金额格式（`prefs.fmt`），对非金额列 SHALL NOT 做金额单位换算与强制 2 位小数。
4.5 WHEN 渲染合计行 THEN 系统 SHALL 按同一 `render` 维度选择格式化函数。
4.6 WHEN 标注金额列 THEN 系统 SHALL 覆盖 9 个区块配置文件里全部金额语义列（实测 76 列：75 个含「金额/余额/市值/损益/到账/实收/扣缴/成本/费/差异/报价值/净收入」等 + H0-5 的 `cap_cost` 原值），SHALL NOT 标注 17 个非金额列（数量 / 成交价 / 每股股利 / 投资比例）。
4.7 WHERE 列 `field === 'seq'` THE 系统 SHALL 不受影响（`CheckBlock` 的 `seq` 分支早于 number 分支命中）。
4.8 WHEN 守卫运行 THEN 系统 SHALL 断言每个 `type:'number'` 非 `seq` 列**要么**标了 `render:'amount'`**要么**在非金额登记表里带理由，两侧数量与集合双向锁死。
4.9 WHEN `GtConfirmationAlternativeG06.vue` 渲染「余额数据」卡片 6 个金额输入 THEN 系统 SHALL 改用 `WpAmountInput`。
4.10 WHEN 守卫运行 THEN 系统 SHALL 断言 `CheckBlock.vue` 与 G0-6 卡片源码里不再有「金额语义字段 + `el-input type="number"`」的组合，并配反向自检。

### Requirement 5: 实测残留复原判据固化

**User Story:** 作为下一个做实测的会话，我要知道复原基线不能只看「自己实测前那一刻」的快照。

#### Acceptance Criteria

5.1 WHEN 判定实测复原基线 THEN 系统 SHALL 多方交叉：同表同类底稿的常态（`parsed_data IS NULL`）· 该行 `updated_at` 是否仍是初始生成时间 · 仓库内既有 `tmp_*_restore.py` 记录的基线。
5.2 WHEN 字段值含「实测」「XX实测：」等测试标记 THEN 系统 SHALL 按测试产物清除，SHALL NOT 当成用户数据保留。
5.3 WHEN 本 spec 收口 THEN 系统 SHALL 用只读查询确认七枢纽函证底稿无遗留实测残留，并把结论写进 tasks.md。
5.4 WHEN 该判据固化 THEN 系统 SHALL 落进 `.kiro/steering/memory.md` 的踩坑铁律（已于 2026-08-04 落地，本 spec 只做验证与登记）。

### Requirement 6: 七枢纽零回归

**User Story:** 作为其它六个函证循环的使用者，本次改动不能改变我这边的既有行为。

#### Acceptance Criteria

6.1 WHEN 改动共享文件 THEN 系统 SHALL 只做加法式最小 hunk，SHALL NOT 重排既有代码。
6.2 WHEN 守卫运行 THEN 系统 SHALL 断言 `buildCrossWorkpaperNavDefs` 对 D0/E0/F0/H0/K0/L0 的输出与既有 `SIX_HUB_BASELINE` 逐字节相等。
6.3 WHEN 未标 `render:'amount'` 的列渲染 THEN 系统 SHALL 与改动前逐字节等价（同一模板分支）。
6.4 WHEN 回归运行 THEN 系统 SHALL 保证 `confirmation` 域全量前端测试无新增失败，预存在基线单独列出。
