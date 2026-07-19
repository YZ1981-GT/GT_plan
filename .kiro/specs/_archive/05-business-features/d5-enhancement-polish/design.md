# Design: D5 应收款项融资底稿增强打磨

## Overview

7 项 presentation-layer 增强，不改架构/composable 接口/后端 API。所有改动限于前端 Vue 组件模板 + 少量 composable 扩展。

## 改动范围

| # | 改动文件 | 改动类型 | 行数估计 |
|---|---------|---------|---------|
| 1 | D5TabDetail.vue + 新建 useD5DetailColumnPrefs.ts | 新 composable + 模板加 ⚙ popover | ~80 |
| 2 | D5TabDetail.vue | opinion-card 补结论区段 | ~30 |
| 3 | D5TabDetail.vue + useD5Detail.ts 或 useD5CrossSheet.ts | 勾稽校验逻辑 + el-alert | ~40 |
| 4 | D5TabFairValue.vue | 统计卡片区 | ~30 |
| 5 | D5TabFairValue.vue | 方法论琥珀块 details | ~25 |
| 6 | D5TabDisclosure.vue + useD5Disclosure.ts | Section 3 改结构化 | ~50 |
| 7 | D5TabFairValue.vue | 利率参考 details grid | ~35 |

## 设计细节

### 1. 列设置 ⚙ popover（套 K7-5 范式）

```typescript
// useD5DetailColumnPrefs.ts
const COLUMN_GROUPS = [
  { label: '核心', keys: ['category', 'itemName', 'endAudited', 'remark'], alwaysShow: true },
  { label: '期初', keys: ['priorUnadjusted', 'priorAje', 'priorRje', 'priorAudited'] },
  { label: '本期变动', keys: ['ociImpairment', 'periodIncrease', 'periodDecrease', 'endBalance'] },
  { label: '重分类与调整', keys: ['entityReclass', 'endUnadjusted', 'endAje', 'endRje'] },
  { label: 'OCI减值', keys: ['endOciImpairment'] },
]
const DEFAULT_HIDDEN = ['priorAje', 'priorRje', 'ociImpairment', 'endOciImpairment']
// localStorage key: 'd5-detail-column-prefs'
```

模板：toolbar-right 内加 `<el-popover>` 触发按钮 ⚙，popover 内分组 checkbox + 重置默认。el-table-column 加 `v-if="isColVisible(key)"` 控制显隐。

### 2. 审计结论字段

在 D5TabDetail opinion-card 中，现有"审计说明"section 下方新增：

```html
<div class="opinion-section">
  <div class="opinion-section-header">
    <span class="opinion-section-label">审计结论</span>
    <div class="opinion-actions">
      <el-button ...AI辅助.../>
      <el-button ...💬.../>
    </div>
  </div>
  <el-input v-model="auditConclusion" type="textarea" :autosize="{ minRows: 3, maxRows: 7 }" .../>
</div>
```

新增 `auditConclusion` ref，watch 绑定 `D5-2-note-conclusion`。

### 3. 勾稽校验提示

在 useD5CrossSheet 中暴露 `crossCheckD1D2` computed：
- `notesReceivableEndAudited` vs `d1SoldModeTotal`（从 allResponses 读 `D1-6-sold-total`）
- `accountsReceivableEndAudited` vs `d2SoldModeTotal`（从 allResponses 读 `D2-13-sold-total`）

若 allResponses 中无对应 item_id（D1/D2 未实例化），显示"无法核对"info 而非 warning。

模板：tab-toolbar 下方 `<el-alert v-if="crossCheckMessage" :type="crossCheckType" ... />`

### 4. 到期预警统计卡片

computed 从 `rows` 分三桶：
- expired: `remainingDays <= 0 && maturityDate`
- nearExpiry: `0 < remainingDays <= 30`
- normal: `remainingDays > 30`

每桶统计 count + sumFaceValue。

模板：3 个 el-statistic 包在 flex 容器中，放 tab-toolbar 和 el-table 之间。

### 5. 方法论琥珀块

```html
<details class="amber-context">
  <summary>📖 方法论上下文：CAS22 FVOCI 公允价值计量</summary>
  <div class="amber-content">
    <p><strong>分类条件：</strong>...FVOCI 三条件...</p>
    <p><strong>贴现法估值：</strong>...公式说明...</p>
    <p><strong>层次判定：</strong>第二层次=可观察市场数据；第三层次=不可观察输入值</p>
  </div>
</details>
```

样式：`border-left: 3px solid #e6a23c; background: #fdf6ec;`（琥珀色，同项目其他琥珀块）

### 6. 风险敞口节

在 `useD5Disclosure` 的 `listedSections` computed 中，将 section 3 改为含结构化表格：
- 行：应收票据 / 应收账款 / 合计
- 列：账面金额（=D5-1 审定数）/ 信用风险最大敞口 / 前五名集中度占比

集中度占比为手动输入（el-input-number %），保存到 `D5-note-listed-exposure-{rowId}` item_id。保留原说明 textarea（`noteTexts['listed-3']`）作补充。

### 7. 利率参考 details

```html
<details class="guidance-details">
  <summary>📊 利率参考（评价贴现利率合理性）</summary>
  <div class="rate-reference-grid">
    <!-- 2×3 grid -->
    <div class="rate-item">
      <span>央行LPR(1Y)</span>
      <el-input-number v-model="rateRefs.lpr1y" :precision="4" .../>
    </div>
    <!-- ... shibor3m / discountRate / entityRate ... -->
  </div>
</details>
```

`rateRefs` 存 `D5-4-rate-references` item_id（JSON），debouncedSave。

## 不改动

- 后端 render 策略 / 导入导出端点 / AI 生成端点
- composable 对外接口（仅 additive 扩展）
- 注册表 / 契约测试
- 其他循环
