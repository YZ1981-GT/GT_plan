# K1 其他应收款披露表与附注对齐增强 — 设计

## 一、架构定位

```
K1-1 审定 ┐
K1-2 明细 ├─► autoFillFromK1Sources / autoFillSoeFromK1Sources
K1-3 坏账 │        │
K1-7 阶段 │        ▼
K1-9 转销 ┘   payload(V2)  ──persist──► working_paper_item(K1-note-listed-rows / K1-note-soe-rows)
                   │
                   ├──► K1TabDisclosureListed.vue / K1TabDisclosureSoe.vue（编制 UI）
                   │
                   └──► buildK1*SyncPayloads ──POST /disclosure-notes/sync-from-workpaper──►
                        disclosure_notes.table_data.sub_table_data[表名]
                                                     │
                                                     ▼
                                        DisclosureEditor.vue currentNoteTables（TAB 页签）
                                        note_template_{listed,soe}.json §五、8 / §八、9（骨架真源）
```

**单向推送**：底稿 → 附注。附注侧 `tables[]` 提供骨架（表名=TAB 标签、headers=列头、`_column_groups`=两级表头、`guidance`=TAB 提示、`rows`=静态行占位）；底稿同步覆盖 `sub_table_data`。因此**表名必须逐字一致**，否则产生孤儿子表。

## 二、数据模型变更（`k1DisclosureModel.ts`）

### 2.1 账龄行类型扩展

```ts
export type K1AgingRowKind = 'data' | 'sub' | 'subtotal1y' | 'subtotal' | 'provision' | 'total'
```

- `sub`：1 年以内月度细分行（`label` 可编辑，金额可编辑，**不参与** `subtotal` 求和）
- `subtotal1y`：`1年以内小计`（只读，取 `within1` 的 `data` 行金额）

`buildAgingDisclosureRows(segments, agg, provision, opts?: { withinOneYearBreakdown?: boolean })`
当 `segments` 含 `within1` 且开启细分时，在其后插入 2 条 `sub` + 1 条 `subtotal1y`。

新增校验：
```ts
export function calcWithinOneYearTieOut(rows): { subSum, within1, diff, matched }
```

### 2.2 Listed payload V2 增量（保持 `version: 2`，向后兼容解析）

```ts
export interface K1ContinuedInvolvementRow {
  rowId: string
  side: 'asset' | 'liability'
  item: string
  amount: number
}

export interface K1ListedDisclosurePayloadV2 {
  // …既有字段…
  priorStage1Rows: K1StageEclDisclosureRow[]   // 新增
  priorStage2Rows: K1StageEclDisclosureRow[]   // 新增
  priorStage3Rows: K1StageEclDisclosureRow[]   // 新增
  stage2NoneEnd: boolean                        // 新增（【或】不存在第二阶段·期末）
  stage2NonePrior: boolean                      // 新增（【或】不存在第二阶段·上年年末）
  continuedInvolvementRows: K1ContinuedInvolvementRow[]  // 新增（替代两个标量的明细化，标量保留兼容）
  notes: Record<string, string>  // key 约定见 §2.4
}
```

`parseK1ListedPayload` 对新增字段做 `?? default` 兜底，旧 payload 无痛升级。

### 2.3 SOE payload V2 增量

```ts
export interface K1ReversalDisclosureRow {
  // …既有…
  cumulativeProvision: number   // 新增：转回或收回前累计已计提坏账准备金额（国企特有）
}

export interface K1OtherPortfolioRow {   // 新增类型（区别于 K1PortfolioAgingRow：比例语义不同）
  rowId: string
  label: string          // 组合名称
  endBalance: number
  endRatePct: number | null   // 计提比例(%)（人工输入，非派生占比）
  endProvision: number
  priorBalance: number
  priorRatePct: number | null
  priorProvision: number
  editable: boolean
}

export interface K1SoeDisclosurePayloadV2 {
  // …既有…
  otherPortfolioRows: K1OtherPortfolioRow[]      // 类型变更（原复用 K1PortfolioAgingRow）
  continuedInvolvementRows: K1ContinuedInvolvementRow[]   // 新增
}
```

`otherPortfolioRows` 的 `endProvision` 派生：`endBalance × endRatePct / 100`（人工可覆盖）。

### 2.4 `notes` key 约定（两版共用）

| key | 语义 | 源模板行 |
|-----|------|---------|
| `balanceChange` | 本期发生损失准备的账面余额显著变动情况 | listed R59 / soe R88 |
| `eclBasis` | 本期坏账准备计提金额以及评估信用风险是否显著增加的依据 | listed R60 / soe R89 |
| `writeoffNote` | 核销段说明 | listed R122 |
| `transferNote` | 继续涉入说明（资产转移方式/关系/风险） | listed R160 / soe R124 |
| `stage2NoneTextEnd` / `stage2NoneTextPrior` | 「不存在第二阶段」标准语句（开关开启时生成） | listed R49/R80 |

## 三、子表名映射（`k1NoteSectionMap.ts`）

### 3.1 上市（`K1_LISTED_SUBTABLE`）

| key | 附注 §五、8 表名 |
|-----|-----------------|
| aging | 按账龄披露 |
| nature | 按款项性质披露 |
| stage1/2/3 | 期末处于第一/二/三阶段的坏账准备 |
| **priorStage1/2/3**（新增） | 上年年末处于第一/二/三阶段的坏账准备 |
| stageMovement | 本期计提、收回或转回的坏账准备情况 |
| reversal | 本期转回或收回金额重要的坏账准备 |
| writeoffSummary | 本期实际核销的其他应收款情况 |
| writeoffDetail | 重要的其他应收款核销情况（逐项披露） |
| top5 | 按欠款方归集的其他应收款期末余额前五名单位情况 |

`transferRows` / `govGrantRows` / `fundCentralization*` **不进 §五、8**（真源在其他章节），仅存底稿 + 在 UI 提示去向。

### 3.2 国企（`K1_SOE_SUBTABLE`）

| key | 附注 §八、9 表名 | 变更 |
|-----|-----------------|------|
| aging | 按账龄披露其他应收款项 | — |
| methodEnd | 按坏账准备计提方法分类披露其他应收款项 | — |
| methodPrior | 续： | — |
| individualDetail | 单项计提坏账准备的其他应收款项 | — |
| **portfolioAging**（新增） | 账龄组合 | 原错挂 portfolioOther |
| portfolioOther | 采用余额百分比法或其他组合方法计提坏账准备的其他应收款项 | 改为承载 `otherPortfolioRows` |
| eclMovement | 其他应收款项坏账准备计提情况 | — |
| **balanceMovement**（改名） | 其他应收款项账面余额变动 | 原 `…账面余额三阶段变动`（附注无此名） |
| **reversal**（改名） | 收回或转回的坏账准备 | 原 `本期收回或转回金额重要的坏账准备` |
| writeoff | 本期实际核销的其他应收款项 | — |
| top5 | 按欠款方归集的期末余额前五名的其他应收款项 | — |
| govGrant | 涉及政府补助的应收款项 | 附注新增表 |
| transfer | 由金融资产转移而终止确认的其他应收款项 | 附注新增表（改名） |
| **continuedInvolvement**（新增） | 其他应收款项转移继续涉入形成的资产、负债的金额 | 附注新增表 |

### 3.3 契约测试（新增 `k1NoteSubtableContract.spec.ts`）

读 `backend/data/note_template_listed.json` / `note_template_soe.json`，断言：
```
∀ v ∈ values(K1_LISTED_SUBTABLE) → v ∈ {t.name | t ∈ section('五、8').tables}
∀ v ∈ values(K1_SOE_SUBTABLE)    → v ∈ {t.name | t ∈ section('八、9').tables}
```

## 四、附注模板 JSON 结构设计

### 4.1 两级表头表达

`test_note_template_row_type.py` 禁止 `headers` 出现空串，因此二级表头用**扁平非空列名 + `_column_groups`**：

```json
{
  "name": "按款项性质披露",
  "headers": ["项  目", "账面余额", "坏账准备", "账面价值", "账面余额 ", "坏账准备 ", "账面价值 "],
  "_column_groups": [
    { "group": "期末金额", "start": 1, "span": 3 },
    { "group": "上年年末金额", "start": 4, "span": 3 }
  ],
  "guidance": "…",
  "rows": [ … ]
}
```

> 同名列在同一 `headers` 数组内重复不影响渲染（`activeTableColumns` 按 index 取值），
> 但为避免 `deriveLegacyTableHeaders` 与列搜索歧义，第二期列名加**尾部窄空格 U+2009**? —
> **不采用**：`headers` 用 `期末账面余额 / 期末坏账准备 / …` 全限定列名，`_column_groups.group` 提供合并标题。
> 这样既无空串、无重复，且底稿同步的行键（`期末账面余额` 等）与列名天然一致。

**最终列名约定（与 `k1DisclosureSyncPayload.ts` 行键逐字一致）**：

| 表 | headers |
|----|---------|
| 按款项性质披露（listed） | `项  目`,`期末账面余额`,`期末坏账准备`,`期末账面价值`,`上年年末账面余额`,`上年年末坏账准备`,`上年年末账面价值` |
| 按账龄披露其他应收款项（soe） | `账  龄`,`期末账面余额`,`期末坏账准备`,`期初账面余额`,`期初坏账准备` |
| 按坏账准备计提方法分类披露其他应收款项 / 续： | `类  别`,`账面余额`,`比例(%)`,`坏账准备`,`预期信用损失率(%)`,`账面价值` |
| 单项计提坏账准备的其他应收款项 | `债务人名称`,`账面余额`,`坏账准备`,`预期信用损失率(%)`,`计提理由` |
| 账龄组合 | `账  龄`,`期末账面余额`,`期末比例(%)`,`期末坏账准备`,`期初账面余额`,`期初比例(%)`,`期初坏账准备` |
| 采用余额百分比法或其他组合方法计提坏账准备的其他应收款项 | `组合名称`,`期末账面余额`,`期末计提比例(%)`,`期末坏账准备`,`期初账面余额`,`期初计提比例(%)`,`期初坏账准备` |
| 其他应收款项账面余额变动 | `账面余额`,`第一阶段`,`第二阶段`,`第三阶段`,`合计` |
| 由金融资产转移而终止确认的其他应收款项 | `债务人名称`,`终止确认金额`,`与终止确认相关的利得或损失` |
| 其他应收款项转移继续涉入形成的资产、负债的金额 | `项  目`,`期末金额` |
| 涉及政府补助的应收款项 | `单位名称`,`政府补助项目名称`,`期末余额`,`期末账龄`,`预计收取的时间、金额及依据` |

### 4.2 `guidance` 内容来源

只允许三类来源，逐字引用：
1. 源模板红字/注释（K1 xlsx 对应行）
2. 附注模版 md 括注（15号文条款、提示块）
3. 平台自动生成的**勾稽关系**描述（明确标注"勾稽："前缀，属工具提示非披露内容）

## 五、UI 设计

### 5.1 上市披露表分区（`el-card` 顺序）

```
① 按账龄披露                  ← sub 行缩进 + 1年以内小计校验 alert
② 按款项性质披露
③ 坏账准备计提情况
   ├ 方法论上下文块（15号文（四）5 + 二/三阶段划分依据）  ← 琥珀色左边线
   ├ 期末第一阶段 / 期末第二阶段(开关) / 期末第三阶段
   ├ 说明：账面余额显著变动（textarea + AI）
   ├ 说明：计提金额及信用风险显著增加依据（textarea + AI）
   └ 上年年末第一 / 第二(开关) / 第三阶段        ← el-collapse 默认折叠
④ 本期计提、收回或转回（两级表头）
   └ 其中：重大转回逐笔 + 源模板注释
⑤ 本期实际核销（汇总 + 逐项）+ 15号文引用 + 说明（textarea + AI）
⑥ 前五名
⑦ 资金集中管理（金额 + 说明 + 3 条解释15号提示）
⑧ 应收政府补助（表 + 说明 + 重大业务咨询程序提示 + 去向提示→附注「计入其他应收款的政府补助」）
⑨ 因金融资产转移而终止确认（表 + 去向提示→附注 §七 金融工具）
⑩ 转移且继续涉入形成的资产、负债（资产区/负债区 + 小计 + 说明）
```

### 5.2 国企披露表（保持 `el-collapse`，新增/调整项）

```
① 按账龄列示
② 按坏账准备计提方法分类（期末 / 期初双表）
③ 单项计提明细
④ 组合计提
   ├ 账龄组合（补期初比例列）
   └ 其他组合（新增，动态行 + prompt 命名）
⑤ 坏账准备三阶段变动
⑤b 账面余额三阶段变动（补方向提示 + 异常标红）
   ├ 说明：账面余额显著变动（textarea + AI）
   └ 说明：计提依据（textarea + AI）
⑥ 前五名（改可编辑）
⑦ 收回或转回（补累计已计提列，改可编辑）+ 源模板注释
⑧ 本期实际核销（改可编辑）
⑨ 前五名 → 合并入 ⑥
⑩ 由金融资产转移而终止确认（去掉转移方式列，改可编辑）
⑪ 继续涉入形成的资产、负债（多行 + 小计 + 说明）
⑫ 涉及政府补助（改可编辑）+ 源模板注
```

### 5.3 金额输入统一

新增内部子组件 `K1AmountInput.vue`（薄封装 `composables/wpAmountInput` 的 `el-input` formatter/parser），
两张披露表所有可编辑金额列改用它；只读金额走 `displayPrefs.fmtAmount()`。
**比率列**（`比例(%)`/`预期信用损失率(%)`/`计提比例(%)`/`占比(%)`）继续用 `el-input-number :precision="2"`，禁止套金额格式。

## 六、同步载荷（`k1DisclosureSyncPayload.ts`）

### 6.1 listed 新增

```ts
[K1_LISTED_SUBTABLE.priorStage1]: mapStageRows(snap.priorStage1Rows),
[K1_LISTED_SUBTABLE.priorStage2]: mapStageRows(snap.priorStage2Rows),
[K1_LISTED_SUBTABLE.priorStage3]: mapStageRows(snap.priorStage3Rows),
```
`nature` 行键改为 `期末账面余额` 等全限定名（与 4.1 列名一致，已是现状 ✓）。
`_note_texts` 增 `listed-balance-change` / `listed-ecl-basis` / `listed-writeoff-note` / `listed-transfer-note` /
`listed-stage2-none-end` / `listed-stage2-none-prior`。

### 6.2 soe 变更

```ts
[K1_SOE_SUBTABLE.portfolioAging]: portfolioAgingRows → 期末/期初账面余额·比例·坏账准备
[K1_SOE_SUBTABLE.portfolioOther]: otherPortfolioRows → 期末/期初账面余额·计提比例·坏账准备
[K1_SOE_SUBTABLE.reversal]:   + 转回或收回前累计已计提坏账准备金额
[K1_SOE_SUBTABLE.transfer]:   去掉 转移方式，保留 终止确认金额 / 与终止确认相关的利得或损失
[K1_SOE_SUBTABLE.continuedInvolvement]: 资产行 / 资产小计 / 负债行 / 负债小计
```
`_note_texts` 增 `soe-balance-change` / `soe-ecl-basis` / `soe-transfer-note`。

## 七、勾稽（tie-out）矩阵

| 编号 | 关系 | 位置 |
|------|------|------|
| T1 | 账龄小计 = K1-1 审定其他应收款期末 | 两版（已有） |
| T2 | 性质合计账面余额 = 账龄小计 | listed（已有 `calcNatureTieOut`） |
| T3 | **1年以内细分合计 = 1年以内** | listed 新增 |
| T4 | 期末三阶段坏账合计 = 账龄表「减：坏账准备」 | listed（已有 `provisionTieOut`）；**新增上年年末同构校验** |
| T5 | ④ 期末余额行 = 期末三阶段坏账合计 | listed 新增 |
| T6 | ④ 上年年末余额行 = 上年年末三阶段坏账合计 | listed 新增 |
| T7 | ⑤ 核销汇总 = ④「本期核销」合计 | listed 新增 |
| T8 | 方法分类合计余额 = 账龄小计 | soe（已有 `calcMethodTieOut`） |
| T9 | 单项明细合计 = 方法表单项行 | soe 新增 |
| T10 | 账龄组合 + 其他组合 = 方法表组合行 | soe 新增 |
| T11 | 账面余额三阶段期末合计 = K1-1 审定 | soe（已有） |
| T12 | 前五名占比合计 ≤ 100% | 两版新增（warning） |

勾稽结果统一进 `K1DisclosureTracePanel`（既有溯源面板），open 项计数展示。

## 八、风险与回归面

| 风险 | 缓解 |
|------|------|
| 改 `K1_SOE_SUBTABLE.reversal` 表名后旧同步数据成孤儿 | 附注侧 `sub_table_data` 以表名为 key，旧 key 保留但不再渲染；提供一次性说明（不做数据迁移，因附注表结构本次整体重排） |
| `otherPortfolioRows` 类型变更 | `parseK1SoePayload` 检测旧结构（含 `segmentKey` 字段）→ 映射为新结构 |
| 附注 JSON 新增 4 表影响 TAB 数快照测试 | 检查并更新 `note_soe_listed_diff.json` 生成物；相关脚本为按需运行，不阻塞 |
| `_column_groups` 首次启用 | `activeTableColumns` 已支持；无 `_column_groups` 时降级扁平（零回归） |
| `sub` / `subtotal1y` 新 kind 破坏旧 payload 解析 | 旧 payload 无这些行，`recalcAgingDerived` 只按 `data` 求和，天然兼容 |
