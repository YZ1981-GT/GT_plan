# Design: D7 合同负债底稿增强打磨

## Overview

7 项增强对齐 D5/D6 标准。改动范围全部前端。

## 改动范围

| # | 改动文件 | 行数估计 |
|---|---------|---------|
| 1 | GtD7ContractLiabilities.vue | ~10 |
| 2 | 新建 useD7DetailColumnPrefs.ts + D7TabDetail.vue | ~80 |
| 3 | D7TabAnalysis.vue | ~40 |
| 4 | D7TabAdjustment.vue | ~10 |
| 5 | D7TabVoucherCheck.vue | ~25 |
| 6 | D7TabLongTerm.vue | ~35 |
| 7 | D7TabRelatedParty.vue | ~50 |

## 设计细节

### 1. 快照触发（同 D6 范式）
```typescript
async function saveImmediateWithSnapshot(...args: Parameters<typeof saveImmediate>): Promise<void> {
  await saveImmediate(...args)
  scheduleAutoSnapshot()
}
```
所有子组件 `:save-immediate` prop 改用包装版。

### 2. 列设置（同 D5/D6 范式）
```typescript
// useD7DetailColumnPrefs.ts
const COLUMN_GROUPS = [
  { label: '核心', keys: ['customerName','contractName','natureType','endAudited','remark'], alwaysShow: true },
  { label: '期初', keys: ['priorUnadjusted','priorAje','priorRje','priorAudited'] },
  { label: '本期变动', keys: ['creditAmount','debitAmount','endUnadjusted'] },
  { label: '期末调整', keys: ['endAje','endRje'] },
  { label: '账龄', keys: ['endAging1','endAging2','endAging3','endAging4'] },
  { label: '关联方', keys: ['relatedPartyType'] },
]
DEFAULT_HIDDEN: ['priorAje','priorRje','endAje','endRje']
localStorage key: 'd7-detail-column-prefs'
```

### 3. TB 发生额勾稽
从 allResponses 读 `D7-4-tb-debit-total` / `D7-4-tb-credit-total`（TB auto_data resolver 产出）。比对 D7-4 表内借方/贷方合计。

### 4. 调整审计目标
```html
<el-alert type="info" :closable="false"
  title="审计目标：验证调整分录的准确性与完整性，确认借贷平衡且调整事由充分合理。"
  class="objective-alert" />
```

### 5. 结论模板 select（同 D6-6）
5 个预设：无异常/已调整/扩样/重大差异/其他。

### 6. 长期挂账勾稽
从 allResponses 读 D7-2-rows JSON 筛选账龄>1年行合计 vs D7-5 rows 期末余额合计。

### 7. 关联方公允判断（同 D6-5）
加 isFairValue/fairValueBasis 两列 + 底部公允性总结 textarea + AI。
