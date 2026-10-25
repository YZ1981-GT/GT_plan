# 设计：公式推送附注铺开 · 批 C

## §1 方案概述

在 `TierAAnchorBinding` 上增加 `note_rows()` 实现，从试算表取数输出附注行；为目标科目在规则清单追加 `stage: "note"` 规则。**推送引擎和附注写入层零改动**——全部复用 `formula-push-all-subjects-rollout` 已验证的路径。

## §2 Task 1 现读实证（2026-10-05，探针二次校正 2026-10-06）

**🔴 关键发现：`wp_account_mapping.json` 的 `note_section` 是附注全局序号，与章节内容严重错位。**

> 探针脚本 `backend/scripts/analyze/_batch_c_note_probe.py` 对 4 个模板文件逐科目按**编号**和**科目名**双路查询。

### 10 科目 `note_section` 错位全表（现读实证）

| 编码 | 科目名 | mapping note_section | listed 该编号实际内容 | listed 按名匹配 | soe 按名匹配 |
|------|------|------|------|------|------|
| K1 | 其他应收款 | 五、5 | ❌ 应收账款（非本科目） | ✅ **五、8** 其他应收款 | ✅ **八、9** 其他应收款 |
| I3 | 商誉 | 五、13 | ❌ 其他流动资产 | ✅ **五、28** 商誉 | ✅ **八、29** 商誉 |
| H5 | 油气资产 | 五、17 | ❌ 设定受益计划净资产 | ❌ listed 无"油气资产"章节 | ✅ 八、25 油气资产 |
| H7 | 生产性生物资产 | 五、18 | ❌ 长期股权投资 | ✅ 五、24 生产性生物资产 | ✅ 八、24 生产性生物资产 |
| H8 | 使用权资产 | 五、19 | ❌ 其他权益工具投资 | ✅ 五、25 使用权资产 | ✅ 八、26 使用权资产 |
| H9 | 租赁负债 | 五、34 | ❌ 交易性金融负债 | ✅ 五、47 租赁负债 | ✅ 八、52 租赁负债 |
| H10 | 资产处置损益 | 五、46 | ❌ 应付债券 | ❌ listed 无 | ❌ soe 无 |
| I1 | 无形资产 | 五、12 | ❌ 一年内到期的非流动资产 | ✅ 五、26 无形资产 | ✅ 八、27 无形资产 |
| I4 | 长期待摊费用 | 五、14 | ❌ 债权投资 | ✅ 五、29 长期待摊费用 | ✅ 八、30 长期待摊费用 |
| I6 | 研发费用 | 五、34 | ❌ 交易性金融负债 | ✅ 五、66 研发费用 | ✅ 八、67 研发费用 |

**结论**：`note_section` 编号**10 个全部错位**（含 K1/I3，requirements 原以为正确），不可直接用作附注章节定位。正确编号必须**按科目名**在模板中搜索。

### 交付范围调整（探针校正后）

| 编码 | 可行性 | 按名匹配结果 listed / soe | 主表结构 | 排除原因 |
|------|------|------|------|------|
| **K1** | ✅ 可做 | **五、8** / **八、9** | 主表"其他应收款" 4 行，cols `[label, 期末余额, 上年年末余额]`（soe 列名"期初余额"） | — |
| **I3** | ⚠ 可做但结构复杂 | **五、28** / **八、29** | listed 主表"商誉账面原值" `[项目, begin, inc_merge, inc_jv, inc_other, dec_disposal, dec_other, end]` 2 行；soe 主表"商誉账面价值" `[项目, begin, increase, decrease, end]` 1 行。**是变动表（begin/inc/dec/end），非简单 end_amount + prior_amount** | 🔴 requirements 假设 `end_amount + prior_amount` 不成立，需降级为只推 end（原值期末）和 begin（原值期初），或不推 |
| H5 | ⚠ 仅 soe | ❌ / 八、25 | 变动表 | listed 无章节 |
| H7 | ⚠ 排除（复杂表） | 五、24 / 八、24 | 成本+公允两张子表，多栏分品种 | 非简单期末/期初 |
| H8 | ⚠ 排除（复杂表） | 五、25 / 八、26 | 多分类变动表 39/25 行 | 非简单期末/期初 |
| H9 | ✅ 可做 | 五、47 / 八、52 | 主表 `[label, end_balance, prior_balance]` 3/5 行 | ⚠ 原 requirements 排除；按名搜实际可匹配，但不在本 spec 范围 |
| H10 | ❌ | 两版均无 | — | 模板无章节 |
| I1 | ⚠ 排除（复杂表） | 五、26 / 八、27 | 多分类变动表 38/52 行 | 非简单期末/期初 |
| I4 | ⚠ 排除（变动表） | 五、29 / 八、30 | 变动表 `[begin, increase, amort, other_decrease, end]` | 非简单期末/期初 |
| I6 | ✅ 可做 | 五、66 / 八、67 | `[项目, 本期发生额, 上期发生额]` 7/6 行 | ⚠ 原 requirements 排除；按名搜实际可匹配，但不在本 spec 范围 |

**确定本 spec 可做的：K1（2 个新章节编号）+ I3（需降级处理）= 2 个**。H9/I6 按名搜实际可匹配，但原 requirements 排除在外；H7/H8/I1/I4 表结构复杂不是简单推送；H5 仅 soe 有章节；H10 两版均无章节。

### 🔴 K1/I3 requirements 原始假设 vs 现读实证

| 项 | requirements 假设 | 现读实证 | 影响 |
|------|------|------|------|
| K1 listed 章节 | 五、5 | **五、8** | 规则 `section_by_template` 必须改 |
| K1 soe 章节 | 八、5 | **八、9** | 同上 |
| K1 主表名 | "按账龄披露" | **"其他应收款"**（按账龄披露是第 6 张子表） | 规则 `table` 和取数逻辑须改 |
| K1 主表列 | `end_amount + prior_amount` | `[label, 期末余额, 上年年末余额]`（中文列名） | 字段映射需适配 |
| I3 listed 章节 | 五、13 | **五、28** | 规则 `section_by_template` 必须改 |
| I3 soe 章节 | 八、14 | **八、29** | 同上 |
| I3 主表列 | `end_amount + prior_amount` | **变动表**（begin/inc_merge/.../end） | 🔴 结构不兼容，不能简单推 end_amount/prior_amount |

## §3 K1 附注推送

K1 附注章节**按科目名匹配**：listed **`五、8`** / soe **`八、9`**（`note_section` 五、5 指向的是应收账款，不是其他应收款）。

主表（两版均叫"其他应收款"）：
- **listed `五、8`**：主表 name="其他应收款"，cols=`['label', '期末余额', '上年年末余额']`，4 行（其他应收款 / 应收利息 / 应收股利 / 合计）
- **soe `八、9`**：主表 name="其他应收款"，cols=`['label', '期末余额', '期初余额']`，4 行（同结构，列名差异：上年年末余额 vs 期初余额）

K1 只需推送主表第一行（"其他应收款"行）的期末/期初值。`K1Binding.note_rows()` 从 `k1_calc` 取 `audited_receivable`（原值合计）推期末，取上期同口径推期初。

> 注意：K1 附注共有 21 张表（按账龄披露、坏账分类等），本 spec 只推主表第一行。

## §4 I3 附注推送

I3（商誉）**按科目名匹配**：listed **`五、28`** / soe **`八、29`**（`note_section` 五、13 指向的是其他流动资产，不是商誉）。

🔴 **主表结构是变动表，非简单 end_amount + prior_amount**：
- **listed `五、28`**：主表 name="商誉账面原值"，cols=`['项目', 'begin', 'inc_merge', 'inc_jv', 'inc_other', 'dec_disposal', 'dec_other', 'end']`，2 行；另有"商誉减值准备"表、"减值测试关键假设"表
- **soe `八、29`**：主表 name="（1）商誉账面价值"，cols=`['项目', 'begin', 'increase', 'decrease', 'end']`，1 行；另有"商誉减值准备"表

requirements 假设 `end_amount + prior_amount` 两列在 I3 不成立。实际表结构是**变动表**（期初/增加/减少/期末），公式推送只能推 `end`（原值期末余额）和 `begin`（原值期初余额），其余列（本期增减明细）不在 TB 取数范围。

Tier A 的 `note_rows()` 取 `TB('1711','期末余额')` → `end`，取 `TB('1711','年初余额')` → `begin`。

## §5 规则结构示例

```json
{
  "rule_id": "K1.note.main",
  "page_key": "workpaper:K1",
  "stage": "note",
  "policy": "system",
  "target": {
    "domain": "note",
    "section_by_template": { "listed": "五、8", "soe": "八、9" },
    "table": "其他应收款",
    "fields": ["end_amount", "prior_amount"],
    "rows": "k1_note_main"
  },
  "source": { "kind": "derivation", "name": "k1_note_main" },
  "triggers": ["TRIAL_BALANCE_UPDATED", "WORKPAPER_SAVED", "manual"],
  "description": "其他应收款附注主表推送（listed 五、8 / soe 八、9）"
}
```

I3 规则（变动表，只推 begin/end 两列）：
```json
{
  "rule_id": "I3.note.main",
  "page_key": "workpaper:I3",
  "stage": "note",
  "policy": "system",
  "target": {
    "domain": "note",
    "section_by_template": { "listed": "五、28", "soe": "八、29" },
    "table": "商誉账面原值",
    "fields": ["end", "begin"],
    "rows": "i3_note_main"
  },
  "source": { "kind": "derivation", "name": "i3_note_main" },
  "triggers": ["TRIAL_BALANCE_UPDATED", "WORKPAPER_SAVED", "manual"],
  "description": "商誉附注主表推送（listed 五、28 / soe 八、29，变动表只推期初/期末）"
}
```

## §6 风险与降级

- **`note_section` 映射数据质量差**：72 个主编码的 `note_section` 字段有大面积错位，本 spec 只做精确匹配到的 2 个科目。修正映射数据是独立任务（`wp_account_mapping.json` 的维护归底稿模板管理）
- **K1 只推主表合计**：K1 附注有 12 张子表（坏账变动、账龄分布等），本 spec 只推第一张表的合计行。其余子表需要底稿披露 Tab 的 `buildK1SyncPayload` 数据，不在公式推送范围
