# GtAmountCell 使用规范

> 统一金额展示组件，内部 Decimal.js 精确计算，避免浮点误差。

## 何时使用

| 场景 | 使用 `GtAmountCell` | 说明 |
|------|:---:|------|
| 表格金额列 | ✅ | 替换手写 `{{ formatAmount(row.amount) }}` |
| 穿透弹窗金额 | ✅ | 统一千分位/负数红/单位 |
| 报表行金额 | ✅ | 替换 `toFixed(2)` + 手动千分位 |
| 非金额数值（百分比/耗时） | ❌ | 用原生 `toFixed` 或专用 formatter |
| 文件大小展示 | ❌ | 用 `formatFileSize` utility |

## 基本用法

```vue
<template>
  <GtAmountCell :value="row.audited_amount" />
</template>
```

## 可点击（穿透查询）

```vue
<GtAmountCell
  :value="row.audited_amount"
  :clickable="true"
  @click="onDrilldown(row)"
/>
```

## 变动高亮（对比上期）

```vue
<GtAmountCell
  :value="row.current_amount"
  :prior-value="row.prior_amount"
/>
```

## 带批注

```vue
<GtAmountCell
  :value="row.amount"
  :comment="cellComments[row.id]"
/>
```

## Props

| Prop | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `value` | `number \| string \| null` | — | 金额值 |
| `clickable` | `boolean` | `false` | 是否可点击（穿透） |
| `comment` | `CellComment \| null` | `undefined` | 批注对象 |
| `priorValue` | `number \| string \| null` | `undefined` | 上期金额（变动高亮对比） |

## 显示偏好联动

`GtAmountCell` 自动读取 `displayPrefs` store：

- **amountUnit**：元 / 千元 / 万元（自动 Decimal 除法）
- **decimals**：小数位数（Decimal.toFixed 精确）
- **showZero**：零值显示 `0.00` 还是 `-`
- **negativeRed**：负数红色
- **highlightThreshold**：变动率阈值

## 禁止模式

```vue
<!-- ❌ 禁止：原生浮点 toFixed -->
<span>{{ (row.amount / 10000).toFixed(2) }}</span>

<!-- ❌ 禁止：手动千分位 + Number 转换 -->
<span>{{ Number(row.amount).toLocaleString() }}</span>

<!-- ✅ 正确：统一组件 -->
<GtAmountCell :value="row.amount" />
```

## Decimal 计算规范

```typescript
import { toDecimal, decimalSum } from '@/utils/decimal'

// ✅ 正确：Decimal 求和
const total = decimalSum(rows.map(r => r.amount))

// ❌ 禁止：原生浮点求和
const total = rows.reduce((s, r) => s + r.amount, 0)
```

## 复制行为

用户复制 `GtAmountCell` 内容时，剪贴板获得**纯数值字符串**（无千分位），
确保粘贴到 Excel 后可直接参与计算。
