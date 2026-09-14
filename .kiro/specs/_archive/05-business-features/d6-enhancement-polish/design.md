# Design: D6 合同资产底稿增强打磨

## Overview

8 项 presentation-layer + 勾稽自动化增强。仅前端改动（Vue 组件 + composable additive），不改后端 API。

## 改动范围

| # | 改动文件 | 改动类型 | 行数估计 |
|---|---------|---------|---------|
| 1 | 新建 useD6DetailColumnPrefs.ts + D6TabDetail.vue | composable + popover | ~80 |
| 2 | D6TabEclCalculation.vue | 勾稽校验 computed + el-alert | ~40 |
| 3 | D6TabInspection.vue | 结论模板 el-select | ~25 |
| 4 | D6TabAdjudication.vue | AI按钮补齐 | ~20 |
| 5 | D6TabRelatedParty.vue | 新增2列 + 底部总结 | ~50 |
| 6 | D6TabAdjustment.vue | 审计目标 el-alert | ~10 |
| 7 | D6TabWriteoffCheck.vue | 勾稽校验 computed + el-alert | ~35 |
| 8 | GtD6ContractAssets.vue | saveImmediate wrapper | ~5 |

## 设计细节

### 1. 列设置 ⚙ popover（套 D5 范式）

```typescript
// useD6DetailColumnPrefs.ts
const COLUMN_GROUPS = [
  { label: '核心', keys: ['seqNo','contractType','customerName','contractName','endAudited','remark'], alwaysShow: true },
  { label: '期初', keys: ['priorUnadjusted','priorAje','priorRje','priorAudited'] },
  { label: '本期变动', keys: ['debitAmount','creditAmount','endUnadjusted'] },
  { label: '期末调整', keys: ['endAje','endRje'] },
  { label: '账龄', keys: ['aging1y','aging1to2','aging2to3','aging3plus'] },
  { label: '期后', keys: ['postPeriodSettlement','postPeriodDate'] },
]
const DEFAULT_HIDDEN = ['priorAje','priorRje','endAje','endRje','postPeriodDate']
// localStorage key: 'd6-detail-column-prefs'
```

与现有 el-segmented（基础/含账龄）互补——segmented 控制账龄组整体可见性，⚙列设置提供更细的单列控制。

### 2. ECL ↔ 政策勾稽

在 D6TabEclCalculation.vue 加 computed：
- 从 allResponses 读 `D6-7-eval-loss-rate-{groupId}` 获取政策评价中的损失率
- 与 D6-8 每个 agingGroup 的 lossRate 比对
- 差异>1%bp 时 warning，全部一致时 success

### 3. 结论模板 select

```typescript
const CONCLUSION_TEMPLATES = [
  '经检查，所抽取样本未发现重大异常，合同资产增减变动真实准确。',
  '经检查，发现差异已提请被审计单位调整，调整后合同资产列报恰当。',
  '检查比例不足，建议扩大样本量后重新评估。',
  '发现重大差异，建议提出审计调整分录。',
  '其他（请手动编写结论）。',
]
```

el-select change 后填入 auditNotes.conclusion。

### 4. 审定表 AI 按钮

确认 D6TabAdjudication opinion-card 中是否已有 AI 按钮：
- 如已有 → 仅验证，标记完成
- 如缺失 → 补 🤖AI辅助 按钮，section='adj-change-analysis' / 'adj-conclusion'

### 5. 关联方结构化判断

在 RelatedPartyRow 接口添加（additive）：
- `isFairValue: string` (是/否/待定)
- `fairValueBasis: string`

模板加两列 el-table-column。底部加"关联方交易公允性总结"textarea + AI 按钮。

### 6. 调整审计目标

在 D6TabAdjustment.vue 编制提示下方加：
```html
<el-alert type="info" :closable="false"
  title="审计目标：验证调整分录的准确性与完整性，确认借贷平衡且调整事由充分合理。"
  class="objective-alert" />
```

### 7. 转回核销勾稽

在 D6TabWriteoffCheck.vue 加 computed：
- 从 allResponses 读 D6-3 减值明细的转回/核销合计
- 与 D6-9 自身 reversalRows/writeoffRows 合计比对
- 差异时 warning

### 8. 快照触发

在 GtD6ContractAssets.vue 中将 `saveImmediate` 传给子组件前 wrap 一层：
```typescript
async function saveImmediateWithSnapshot(itemId: string, data: Partial<ChecklistResponse>): Promise<void> {
  await saveImmediate(itemId, data)
  scheduleAutoSnapshot()
}
```
将 `:save-immediate="saveImmediateWithSnapshot"` 传给所有子组件。

## 不改动

- 后端 render 策略 / 导入导出 / AI 端点
- useD6FormData / useD6CrossSheet 对外接口
- 注册表 / 契约测试
- 其他循环
