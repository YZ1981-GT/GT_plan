# D1 应收票据披露表与附注对齐 — 设计

## 披露逻辑梳理（源模板两个 sheet）

两版共用一条主线：**分类 → 计提方法 → 明细支撑 → 变动 → 特殊状态 → 核销**。
差异只在编排顺序与列措辞。

```
① 分类总表（票据种类 × 双期 × 账面余额/坏账准备/账面价值）
      ↑ 取自审定表 D1-1（源模板 B9=='审定表D1-1'!I8 等）
      │
② 按计提方法分类（单项 / 组合 × 金额·比例·坏账准备·损失率·账面价值）
      │   勾稽 F4-8/9/10：①合计 = ②合计（账面余额/坏账准备/账面价值 三列各自）
      ├─③ 按单项计提明细（名称·账面余额·坏账准备·损失率·计提依据）
      │       勾稽 F4-4/5：②单项行 = ③小计
      └─④ 按组合计提明细（出票人类型或账龄 × 银承/商承）
              勾稽 F4-4/5：②组合行 = ④小计
      │
⑤ 坏账准备变动（期初 + 计提 − 收回或转回 − 核销 − 其他变动 = 期末）
      │   勾稽 F4-6：①坏账准备期末合计 = ⑤期末合计
      └─ 其中：本期转回或收回金额重要者（逐项）
      │
⑥ 期末已质押  ⑦ 期末已背书或贴现未到期（终止确认 / 未终止确认）
⑧ 期末因出票人未履约而转应收账款（**只列商业承兑**）
      │
⑨ 本期实际核销（总额）
      └─ 其中：重要核销逐项（单位名称·性质·金额·原因·程序·是否关联交易）
```

编排差异：

| | 上市（五、4） | 国企（八、4） |
|---|---|---|
| 分类总表位置 | 顶部（无小节号） | （1） |
| ⑥⑦⑧ 位置 | （1）(2)(3) 在前 | （4)(5)(6) 在后 |
| ②③④ 双期 | 拆两张表（期末 / 续：上年年末） | ②拆两张，③④只期末 |
| ⑤ 变动表形态 | 竖排单列（项目 × 坏账准备金额） | 横排（类别 × 期初·本期变动情况·期末） |
| ④ 组合明细 | 按票据种类各一张（双期并列） | 一张（商承小计 / 银承小计 + 账龄明细） |
| ② 表头层级 | 两级（期间 > 5 列） | 三级（期间 > 账面余额·坏账准备 > 金额·比例） |

设计含义：

- 组合计提的行维度是**出票人类型或账龄**（源模板红字占位 `出票人类型或账龄`），
  故名称列用项目账龄配置枚举点选（`useAgingConfig(projectId,'D1')`）+ 允许自定义。
- 「若票据逾期，则应转入应收账款并计提坏账准备，账龄应连续计算」（源模板红字）
  是 D1 与 D2 的联动口径，故 ⑧ 只列商业承兑。
- ⑦ 的终止确认判断有源模板给定的两段参考披露 → 已在
  `ENDORSED_JUDGMENT_TEMPLATES`，保留。

## 两级表头映射

平台唯一机制：`ColumnDef.group` →（后端 `_extract_column_groups`）→ `_column_groups`
→ 消费方 `DisclosureEditor.activeTableColumns`（嵌套 `el-table-column`）
+ `note_word_exporter._build_two_level_header_rows`。

🔴 前端只认扁平 `{group,start,span}`，`group` 里带 `/` 会走后端树形分支
（`children`/`headerIdx`）导致 `g.start` 为 `undefined` → 渲染崩。**禁止多级 group**。

规则：**同表并列双期 → `group`；拆表双期 / 单期 → `flat`**。

| 表 | 表态 |
|---|---|
| 上市 应收票据 | group 期末余额 / 上年年末余额 |
| 上市 按坏账计提方法分类（期末余额）/（续：上年年末余额） | group 期末余额 / 上年年末余额（源模板 B38:F38 合并） |
| 上市 按单项计提坏账准备的应收票据（期末余额）/（续） | flat（期间在表名） |
| 上市 组合计提项目：银行/商业承兑汇票 | group 期末余额 / 上年年末余额 |
| 上市 变动表 / 转回表 / 质押 / 背书 / 转应收 / 核销 ×2 | flat |
| 国企 应收票据分类 | group 期末数 / 期初数 |
| 国企 按坏账准备计提方法分类披露应收票据（期末数）/（续：期初数） | group 账面余额{金额,比例(%)} + 坏账准备{金额,预期信用损失率(%)} + 账面价值 单列 |
| 国企 变动表 | group 本期变动情况{计提,收回或转回,核销,其他变动}，期初数/期末数 单列 |
| 国企 其余 6 张 | flat |

混合分组（部分列无 `group`）已被前端与后端同时支持：
后端单级分支只为带 group 的连续列产出条目，前端 `activeTableColumns`
用 `grouped` Set 标记被占用的 headerIdx，其余走 `flat` 分支。

## 改动清单

### 后端

1. **`backend/scripts/fix/fix_note_d1_notes_receivable_structure.py`**（新建）
   —— 沿用 `fix_note_g_cycle_structure.py` 范式：`SECTION_PLANS` 表驱动
   （`aliases` 游标匹配 / `headers` / `columns` / `rows` / `guidance`），
   `_derive_column_groups` 派生 `_column_groups`，`validate_section` 校验，
   `--dry-run` / `--check` / `_aligned_by` 标记。
2. **`backend/tests/test_note_d1_structure.py`**（新建）—— 参数化锁死 R1。
3. **CI job** `note-d1-structure` 挂 `--check`。

### 前端

4. **`composables/d1NoteSectionMap.ts`**
   - `SUMMARY_COLUMNS_SOE` group → `期末数`/`期初数`
   - `SUMMARY_COLUMNS_LISTED` / `PORTFOLIO_COLUMNS_LISTED` group → 期间全名
   - 分类列拆成按期间带 group 的 builder（上市）/ 按 账面余额·坏账准备 分组（国企）
   - 变动列（国企）加 group `本期变动情况`
   - 单期 / 拆表双期的列标 `flat`
   - 国企转回表 `cumulative_provision` → `format: amount`，取 `cumulativeProvision`
   - 新增零参 `buildD1ListedColumns()` / `buildD1SoeColumns()` 供契约测试
     （`P1_ROUTE` 登记要求 builder 零参可调）
5. **`composables/useD1Disclosure.ts`**
   - `defaultTransferRows` → 只保留「商业承兑票据」
   - 质押/背书/转应收固定行名 汇票 → 票据
   - `ReversalDetailRow` 加 `cumulativeProvision: number`，
     加载时若缺失且 `reversalBasis` 可解析为数则迁移
   - 新增 `addPortfolioPairRow(type, name)` / `renamePortfolioPair(type, old, next)`
     / `fillPortfolioAgingBandsPair(type, labels)`：让上市双期并列表的行成对对齐
6. **`d1/D1TabDisclosure.vue`**
   - 上市：分类表加父表头 + 列名对齐 + 计提依据列
   - 上市：新增「按组合计提坏账准备」两张双期并列录入表
   - 上市：质押/背书/转应收 表头与金额列名对齐；转应收支持增删行
   - 国企：组合小计行名加「小计：」；转回表列名 + 金额输入
   - 同步快照补 `cumulativeProvision`
7. **`composables/__tests__/d1NoteSubtableContract.spec.ts`**（新建）
   —— `runDisclosureSubtableContract`
8. **`composables/__tests__/d1NoteSectionMap.spec.ts`** —— 跟随更新断言

## 双期成对行对齐

上市组合表在源模板里是一张表、双期并列。底稿侧数据存两份
（`bankPortfolioEndRows` / `bankPortfolioPriorRows`），同步时 `mergePortfolio`
按 `drawerTypeOrAging` 名称对齐。为避免「改了期末名称导致上年末行变孤儿」：

- 新增行：`addPortfolioPairRow` 先 `ElMessageBox.prompt` 取名，再向两期各插一行同名行。
- 改名：`renamePortfolioPair` 同时改两期同名行。
- 按账龄段生成：对两期各调 `fillPortfolioAgingBands`。

UI 行 = 两期按名称合并的视图（`listedPortfolioRows(type)`），
每行携 `endRowId` / `priorRowId`（可缺），金额编辑分别落到对应期。

## 风险

- 改 `columns` 会改变 `headers` 顺序/文字 → 既有项目**不受影响**
  （`_sub_table_columns` 是上次同步写入的旧值，模板 JSON 只对 seed 路径生效）；
  交付说明须写清「新建项目 / 重新生成附注才可见」。
- 上市分类表新增「计提依据」列属**底稿多留审计列**，同步时仍投影成附注 6 列形状
  （`CLASS_COLUMNS_LISTED` 不含该列），符合平台口径。

---

# 第二阶段设计

## 派生列改为读时推导（R5）

根因在两处叠加：

```ts
// useD1Disclosure.updateCell('classEnd')
const totalBal = classEndTotal.value.balance          // 编辑前的合计（stale 分母）
...map(r => r.rowId === rowId ? recalcClassRow({...r, [field]: numVal}, totalBal) : r)
//                              ^ 只重算被编辑的那一行，其余行保留旧分母
```
```ts
// D1TabDisclosure.soeClassEndRows
ratio: (bank?.ratio || 0) + (commercial?.ratio || 0)  // 两个不同分母的比率相加
lossRate: 0                                           // 硬编码
```

设计：**账面余额 / 坏账准备是唯一真源，比例 / 损失率 / 账面价值一律读时推导**。

- 新增纯函数 `deriveClassRows(rows, totalBalance)`（`d1SharedFormulas.ts`），
  对每行重算 `ratio = balance/total`、`lossRate = provision/balance`、
  `bookValue = balance − provision`。
- `classEndRows` / `classPriorRows` 拆成 `*Raw` 内部 ref（持久化只写录入列）
  + 对外 computed（推导后）。`updateCell` 写 raw，不再算派生列。
- 合计行 `ratio` 恒 1（展示 100.00%），`lossRate = 总坏账/总余额`。
- 组件层 `soeClassEndRows` / `buildBadDebtRows` / `soeAgingRows` 全部改用
  `ratioOf(part, whole)`，删除 `?.ratio` 透传与 `lossRate: 0`。

这样导入路径写进来的旧派生值也会被推导覆盖（R5.4），从源头消除漂移。

## AI 调用契约（R6）

前端两处改为平台正解形状（对齐 `useReviewDialog.ts`）：

```ts
{ section_id, related_data, existing_content }   // 请求
res.data?.generated_text ?? res.generated_text  // 响应（信封已被中间件包一层）
```

后端 `review_dialog.py` 加 `_SECTION_PROMPTS: dict[str, str]`，按 `section_id` 精确命中
则用专属 prompt，否则回退现有通用 prompt（**纯增量，不影响既有调用方**）。
D1 披露 5 个子节 + 审定表 2 个各写一条 ≥20 字、含源模板/15 号文口径 + 「不得虚构」。

## 校对附注（R7）

`pickNoteTotal(detail, mainTableName)` 改为按表名定位 → 取 `is_total` 行 →
按列头找「账面价值」列（`_sub_table_columns` 里 `end_book_value`），落到 `values` 下标。
本页值取 `categorySummaryTotal.endBookValue`；为 0 且附注有值时报「本页主表未取数」。

## 变动表「其中：」明细（R9）

`movementDetailRows`（`movement-detail-rows` 持久化键）新增/删除需先
`ElMessageBox.prompt` 命名。`soeMovementRowsForDisplay` 在「其中：」后插入明细行；
有明细时「按组合计提预期信用损失的应收票据」行 6 列改为明细汇总（只读）。
同步载荷 `soeMovementRows` 顺序：单项 / 组合 / 其中： / 明细… / 合计。

## 勾稽引擎（R10）

`d1DisclosureConsistency.ts` 纯函数：

```ts
export interface D1CheckResult { label; rule; left; right; diff; level; detail?; refs? }
export function runD1DisclosureChecks(variant, snap): D1CheckResult[]
```

`eqCheck(label, rule, left, right, {level, detail, refs})` 容差 0.01；
`skip` 当任一侧无数据（避免空表刷屏 warning）。入参用与
`buildD1SyncPayload` 同一份 snapshot 形状，保证面板与附注同源。

展示 `D1DisclosureConsistencyPanel.vue`：紧凑 bar（通过 n / 提示 n / 差异 n）+
折叠明细表（项目 / 规则 tooltip / 左值 / 右值 / 差异 / 追溯 chip）。

## 附件（R11）

复用平台底稿附件组件（`GtWpAttachments` 若存在，否则用既有 `el-upload` +
`/api/workpapers/{id}/attachments` 通道），挂在核销 / 质押 / 背书三个子节的说明区上方。
**不新建上传后端**；若平台无现成通道则只做占位入口并在 tasks 里标注。

## 导入导出（R12）

`_d1_disclosure_export.py` 增 2 个 sheet（组合计提项目 · 银行 / 商业承兑汇票，
双期 6 列 + 名称列）+ 国企转回表加一列；统一列名与半角括号。
后端镜像常量用读 `d1NoteSectionMap.ts` 源码的正则契约测试守住。
