# F1 预付款项披露表 ↔ 附注模板对齐 — 设计

## 一、源模板结构（逐字摘录）

### F1 xlsx `附注披露信息(上市公司)`

```
（1）预付款项按账龄披露
账  龄 | 期末数{金  额, 比例%} | 上年年末数{金  额, 比例%}
1年以内 / 1至2年 / 2至3年 / 3年以上 / 合  计     ← 取数 ='审定表F1-1'!I17..I20 / E17..E20

（2）账龄超过1年的重要预付款项
债务人名称 | 账面余额 | 占预付款项合计的比例（%） | 减值准备      ← 3 空行 + 合  计
说明：（账龄超过1年的金额重要预付账款，应说明未及时结算的原因。）

（3）按预付对象归集的预付款项期末余额前五名单位情况
（按预付对象集中度，汇总或分别披露期末余额前五名的预付款项的期末余额及占预付款项期末余额合计数的比例。）
汇总披露格式：本期按预付对象归集的期末余额前五名预付款项汇总金额XXXX元，占预付款项期末余额合计数的比例  %。
分别披露格式：单位名称 | 预付款项期末余额 | 占预付款项期末余额合计数的比例%   ← 5 行(='实质性分析F1-4'!A41..A45) + 合  计
```

### F1 xlsx `附注披露信息(国企)`

```
（1）预付款项按账龄列示
账  龄 | 期末数{账面余额{金 额, 比例（%）}, 坏账准备} | 期初数{账面余额{金 额, 比例（%）}, 坏账准备}
1年以内（含1年） / 1至2年 / 2至3年 / 3年以上 / 合  计

（2）账龄超过1年的大额预付款项
债权单位 | 债务单位 | 期末余额 | 账龄 | 未结算的原因   ← ='长期挂款检查表F1-5' 取数 + 合  计（账龄/原因列 ——）

（3）按欠款方归集的期末余额前五名的预付款项情况
债务人名称 | 账面余额 | 占预付款项合计的比例（%） | 坏账准备   ← 5 空行 + 合  计
```

### 附注模版 md（两版 T1 均为 5 列 + 7 行）

```
账  龄 | 期末余额|期末数 {金  额, 比例%|比例（%）} | 上年年末余额|期初数 {…}
1年以内(（含1年）) / 1至2年 / 2至3年 / 3年以上 / 小  计 / 减：减值准备 / 合  计
```

国企 T3 列头 = `减值准备`（非「坏账准备」）。

## 二、三源冲突裁决

| 冲突 | xlsx | 附注模版 md | 校验预设 F7-* | 裁决 |
|------|------|------------|---------------|------|
| T1 是否有 `小计`/`减：减值准备`/`合计` 三行 | 只有 `合计` | 有三行 | F7-6/F7-7 依赖三行 | **三行**（2:1） |
| 国企 T1 是否有逐段「坏账准备」列 | 有（空占位，无公式） | 无 | F7-8「期末/期初各列独立」暗示 5 列 | 附注侧 **5 列**；底稿侧保留逐段列作审计明细，**同步时聚合**为 `减：减值准备` 行（信息不丢，两侧各自守其源） |
| 上市 T2 是否有「未结算原因」列 | 无 | 无 | F7-9(listed) 明确「上市版②表无…」 | **无列**；底稿改为行展开区录入 |
| 上市 T3 是否有「减值准备」列 | 无 | 无 | F7-13(listed)「上市版③表无减值准备列，跳过」 | **无** |
| 国企 T3 第 4 列名 | 坏账准备 | 减值准备 | F7-13(soe) 用「减值准备」 | **减值准备**（2:1） |

**原则**：附注是交付物，其列结构以「附注模版 md + 校验预设」为准；底稿是工作纸，可保留更细的审计列，但同步投影必须投成附注形状。

## 三、附注模板修订（`fix_note_prepayment_structure.py`）

沿用 `fix_note_inventory_structure.py` 范式：按 `tables` 顺序游标匹配 → patch `headers`/`columns`/`_column_groups`/`guidance`/`rows` → 结构自洽校验 → 通过才写 → 打 `_aligned_by` / `_aligned_at`。

### listed §五、7

| 序 | 表名 | headers（叶子列） | `_column_groups` | rows |
|----|------|------------------|------------------|------|
| 0 | 预付款项按账龄披露 | `账龄, 金额, 比例%, 金额, 比例%` | `期末余额`(1,2) / `上年年末余额`(3,2) | 4 段 + 小计 + 减：减值准备 + 合计（删 `header_label`） |
| 1 | 账龄超过1年的重要预付款项 | `债务人名称, 账面余额, 占预付款项合计的比例（%）, 减值准备` | —（`flat`） | 3 空行 + 合计 |
| 2 | **按预付对象归集的预付款项期末余额前五名单位情况**（原「单位名称」） | `单位名称, 预付款项<br/>期末余额, 占预付款项期末余额<br/>合计数的比例%` | —（`flat`） | 5 空行 + 合计 |

### soe §八、7

| 序 | 表名 | headers | `_column_groups` | rows |
|----|------|---------|------------------|------|
| 0 | 预付款项按账龄列示 | `账龄, 金额, 比例（%）, 金额, 比例（%）` | `期末数`(1,2) / `期初数`(3,2) | 4 段 + 小计 + 减：减值准备 + 合计 |
| 1 | 账龄超过1年的大额预付款项 | `债权单位, 债务单位, 期末余额, 账龄, 未结算的原因` | —（`flat`） | 5 空行 + 合计 |
| 2 | **按欠款方归集的期末余额前五名的预付款项**（原重名） | `债务人名称, 账面余额, 占预付款项合计的比例（%）, 减值准备` | —（`flat`） | 5 空行 + 合计 |

`columns[].key` 与同步载荷逐字一致：

- T1：`label / end_amount / end_pct / prior_amount / prior_pct`
- listed T2：`label / balance / proportion_pct / impairment`
- listed T3：`label / end_amount / proportion_pct`
- soe T2：`creditor_unit(is_label) / debtor_unit / end_balance / aging / reason`
- soe T3：`label / end_amount / proportion_pct / impairment`

## 四、底稿披露表

### 上市（`useF1DisclosureListed` + `F1TabDisclosureListed.vue`）

```
agingRows        ← buildAgingDisclosureRows(crossSheet.agingAggregation, crossSheet.agingSegments)
agingSubtotal    ← Σ agingRows                             （label「小计」）
impairmentEnd    ← F1-note-listed-impairment-provision        （可编辑）
impairmentPrior  ← F1-note-listed-impairment-provision-prior  （新增，可编辑）
agingNet         ← 小计 − 减值准备                          （label「合计」）
agingTableData   = [...agingRows, 小计, 减：减值准备, 合计]   ← 单表 7 行，与附注同构
```

(2) 超1年重要表：列 `债务人名称 / 账面余额 / 占预付款项合计的比例（%） / 减值准备`（+ 操作列）；
`el-table type="expand"` 展开区放「未及时结算原因」textarea（沿用 `over1ReasonMap` / `over1DynamicRows.reason` 持久化）；
「据此生成说明」按钮把 `债务人：原因` 汇编写入 note2。

### 国企（`useF1DisclosureSoe` + `F1TabDisclosureSoe.vue`）

```
agingRows        （逐段：账面余额金额/比例 + 减值准备，期末/期初两组，共 7 列）
agingSubtotal    label「小计」
agingImpairment  = Σ 逐段减值准备（期末/期初）  → 派生行「减：减值准备」（只读，来自列求和）
agingNet         = 小计 − 减：减值准备          → label「合计」
```

底稿表内呈现 `逐段 + 小计 + 合计`（源 xlsx 口径，`减值准备` 已作列）；
同步投影时展开为附注 5 列 7 行：逐段 `{金额,比例}` ×2 + 小计 + 减：减值准备（列求和）+ 合计。

## 五、同步载荷（`f1DisclosureSyncPayload.ts`）

```ts
F1_LISTED_COLUMNS = {
  预付款项按账龄披露: [label(账龄), end_amount(金额,group 期末余额), end_pct(比例%,group 期末余额),
                       prior_amount(金额,group 上年年末余额), prior_pct(比例%,group 上年年末余额)],
  账龄超过1年的重要预付款项: [label(债务人名称,flat), balance(账面余额), proportion_pct(占…（%）), impairment(减值准备)],
  按预付对象归集的预付款项期末余额前五名单位情况:
      [label(单位名称,flat), end_amount(预付款项期末余额), proportion_pct(占…比例%)],
}
F1_SOE_COLUMNS = {
  预付款项按账龄列示: [label(账龄), end_amount(金额,group 期末数), end_pct(比例（%）,group 期末数),
                       prior_amount(金额,group 期初数), prior_pct(比例（%）,group 期初数)],
  账龄超过1年的大额预付款项: [creditor_unit(债权单位,is_label,flat), debtor_unit, end_balance, aging, reason],
  按欠款方归集的期末余额前五名的预付款项: [label(债务人名称,flat), end_amount(账面余额), proportion_pct, impairment(减值准备)],
}
```

- listed `sub_table_data._removed_table_keys = ['单位名称']`（过滤本次推送键）。
- `buildF1SoeSubTableData` 账龄表行序：逐段 → `小计`(is_total) → `减：减值准备` → `合计`(is_total)。
- `buildF1ListedSubTableData` 同上，`小计`/`减：减值准备`/`合计` 三行的期末与上年年末两列都给值（F7-7 双期独立校验）。

## 六、账龄枚举

单一真源 `useF1AgingScope`（表级覆盖 > 项目级 `useAgingConfig(projectId,'F1')` > `DEFAULT_SUBJECT_PRESETS.F1 = THREE_YEAR`），经 `useF1CrossSheet.agingSegments` 注入披露 composable。

| 预设 | 段 key | 上市附注标签 | 国企附注标签 |
|------|--------|-------------|-------------|
| THREE_YEAR | within1/y1to2/y2to3/over3 | 1年以内 / 1至2年 / 2至3年 / 3年以上 | 1年以内（含1年）/ 1至2年 / 2至3年 / 3年以上 |
| FIVE_YEAR | within1/y1to2/y2to3/y3to4/y4to5/over5 | …/ 3至4年 / 4至5年 / 5年以上 | 同上 |
| CUSTOM | custom-0..n | `segment.label` | `segment.label` |

附注 seed 骨架固定 3 年段四档（源模板默认）；同步整表覆盖行 → 5 年段推 6 段、自定义推 n 段，附注自动跟随（F7-5「引擎自动适配3段或5段」）。

## 七、影响面与已知限制

- `disclosure_notes.table_data._tables` 是生成时快照 → 模板改名/加列只对**新建项目或重新生成附注**生效；既有项目的 TAB 数不变，「🔄 恢复模板结构」只重置当前单表。
- 后端 `_carry_seed_column_meta` / `_carry_seed_table_guidance` 已在 `generate_notes` / `get_note_detail` 两条多表分支调用，无需改动。
- 改 `note_template_*.json` 不触发后端 `--reload`（模块级 `load()` 只加载一次）→ 验证前需重启或改一个 `.py`。
