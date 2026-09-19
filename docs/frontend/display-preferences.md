# 显示偏好使用指南

> 全局显示偏好管理金额单位、字号、密度、固定列等用户级配置。
> 持久化到 localStorage，切换后所有接入页面实时响应。

## 1. 概述

`useDisplayPrefsStore` 是基于 Pinia 的全局偏好 store，提供：

- **金额单位**：元 / 千元 / 万元
- **字号**：紧凑(11px) / 标准(12px) / 舒适(13px) / 大字(14px)
- **表格密度**：紧凑(32px行高) / 标准(40px) / 宽松(48px)
- **固定列**：按页面记忆用户选择的固定关键列
- **零值显示**：是否显示 0.00 或用横杠 `-` 代替
- **负数红字**：负数金额是否标红
- **变动高亮**：变动超过阈值的行高亮标记

## 2. 基本用法

### 2.1 在组件中使用

```vue
<script setup lang="ts">
import { useDisplayPrefsStore } from '@/stores/displayPrefs'

const displayPrefs = useDisplayPrefsStore()
</script>

<template>
  <!-- 金额格式化 -->
  <span>{{ displayPrefs.fmt(row.amount) }}</span>

  <!-- 表头单位标识 -->
  <span>单位：{{ displayPrefs.unitSuffix }}</span>

  <!-- 表格字号 -->
  <el-table :style="{ fontSize: displayPrefs.fontConfig.tableFont }">

  <!-- 表格密度 -->
  <el-table :size="displayPrefs.tableDensity">
</template>
```

### 2.2 偏好设置面板

```vue
<template>
  <div class="gt-prefs-panel">
    <!-- 金额单位 -->
    <el-select v-model="displayPrefs.amountUnit" @change="displayPrefs.setUnit($event)">
      <el-option v-for="opt in displayPrefs.unitOptions" :key="opt.value" v-bind="opt" />
    </el-select>

    <!-- 字号 -->
    <el-select v-model="displayPrefs.fontSize" @change="displayPrefs.setFontSize($event)">
      <el-option v-for="opt in displayPrefs.fontOptions" :key="opt.value" v-bind="opt" />
    </el-select>

    <!-- 密度 -->
    <el-select v-model="displayPrefs.density" @change="displayPrefs.setDensity($event)">
      <el-option v-for="opt in displayPrefs.densityOptions" :key="opt.value" v-bind="opt" />
    </el-select>

    <!-- 零值显示 -->
    <el-switch v-model="displayPrefs.showZero" @change="displayPrefs.setShowZero($event)" />

    <!-- 负数红字 -->
    <el-switch v-model="displayPrefs.negativeRed" @change="displayPrefs.setNegativeRed($event)" />
  </div>
</template>
```

## 3. 配置项详解

### 3.1 金额单位 (amountUnit)

| 值 | 标签 | 除数 | 说明 |
|---|------|------|------|
| `yuan` | 元 | 1 | 原值展示 |
| `qian` | 千元 | 1000 | ÷1000 展示 |
| `wan` | 万元 | 10000 | ÷10000 展示（默认） |

> 报表金额以"元"存储，显示时按用户选择的单位换算。

### 3.2 字号 (fontSize)

| 值 | 标签 | 表格字号 | 表头字号 |
|---|------|---------|---------|
| `xs` | 紧凑 | 11px | 11px |
| `sm` | 标准 | 12px | 12px |
| `md` | 舒适 | 13px | 13px |
| `lg` | 大字 | 14px | 14px |

### 3.3 表格密度 (density)

| 值 | 标签 | 行高 | 内边距 | el-table size |
|---|------|------|--------|--------------|
| `compact` | 紧凑 | 32px | 4px 8px | small |
| `default` | 标准 | 40px | 8px 12px | default |
| `comfortable` | 宽松 | 48px | 12px 16px | large |

### 3.4 固定列 (fixedColumns)

按页面 key 存储用户选择固定在左侧的列：

```ts
// 设置试算表固定"科目编码"和"科目名称"列
displayPrefs.setFixedColumns('trial-balance', ['standard_account_code', 'account_name'])

// 获取
const fixed = displayPrefs.getFixedColumns('trial-balance')
// → ['standard_account_code', 'account_name']
```

## 4. 接入页面清单

| 页面 | 接入内容 | 状态 |
|------|---------|------|
| 试算表 (TrialBalance) | 单位、字号、密度 | ✅ 单位+字号已接入，密度待接入 |
| 底稿编辑器 (WorkpaperEditor) | 字号、密度 | 待接入 |
| 财务报表 (ReportView) | 单位、字号、密度 | ✅ 单位+字号已接入，密度待接入 |
| 附注编辑器 (DisclosureEditor) | 字号、密度 | ✅ 字号已接入，密度待接入 |
| 合并报表 (ConsolidationIndex) | 单位、字号、密度 | 待接入 |

## 5. 与导出/打印的映射

### 5.1 Excel 导出

| 偏好 | 导出行为 |
|------|---------|
| 金额单位 | 导出原值（元），表头标注"单位：万元" |
| 字号 | 导出使用 12px 固定（Excel 标准） |
| 密度 | 不影响导出 |
| 负数格式 | 导出使用会计格式 `(1,234.56)` |

### 5.2 PDF/打印

| 偏好 | 打印行为 |
|------|---------|
| 金额单位 | 与屏幕显示一致 |
| 字号 | 打印使用 10pt 固定 |
| 密度 | 打印使用紧凑模式 |
| 负数格式 | 与屏幕一致 |

## 6. localStorage 存储格式

```json
{
  "amountUnit": "wan",
  "fontSize": "sm",
  "showZero": false,
  "decimals": 2,
  "negativeRed": true,
  "highlightThreshold": 0.2,
  "density": "default",
  "fixedColumns": {
    "trial-balance": ["standard_account_code", "account_name"],
    "report-view": ["row_name"]
  }
}
```

Key: `gt_display_prefs`

## 7. API 参考

### Store 属性（响应式）

| 属性 | 类型 | 说明 |
|------|------|------|
| `amountUnit` | `Ref<AmountUnit>` | 当前金额单位 |
| `fontSize` | `Ref<FontSize>` | 当前字号 |
| `density` | `Ref<TableDensity>` | 当前密度 |
| `showZero` | `Ref<boolean>` | 是否显示零值 |
| `decimals` | `Ref<number>` | 小数位数 |
| `negativeRed` | `Ref<boolean>` | 负数标红 |
| `highlightThreshold` | `Ref<number>` | 变动高亮阈值 |
| `fixedColumns` | `Ref<FixedColumnsConfig>` | 各页面固定列 |

### 计算属性

| 属性 | 类型 | 说明 |
|------|------|------|
| `unitSuffix` | `ComputedRef<string>` | 单位后缀文本（"万元"） |
| `unitDivisor` | `ComputedRef<number>` | 单位除数（10000） |
| `fontConfig` | `ComputedRef<{...}>` | 字号配置对象 |
| `densityConfig` | `ComputedRef<{...}>` | 密度配置对象 |
| `tableDensity` | `ComputedRef<string>` | el-table size prop 值 |

### 方法

| 方法 | 参数 | 说明 |
|------|------|------|
| `setUnit(unit)` | AmountUnit | 切换金额单位 |
| `setFontSize(size)` | FontSize | 切换字号 |
| `setDensity(d)` | TableDensity | 切换密度 |
| `setShowZero(v)` | boolean | 切换零值显示 |
| `setDecimals(d)` | number | 设置小数位数 |
| `setNegativeRed(v)` | boolean | 切换负数标红 |
| `setHighlightThreshold(v)` | number | 设置变动阈值 |
| `setFixedColumns(pageKey, cols)` | string, string[] | 设置固定列 |
| `getFixedColumns(pageKey)` | string | 获取固定列 |
| `fmt(v)` | any | 格式化金额 |
| `amountClass(v, prior?)` | any, any | 获取金额 CSS 类 |
