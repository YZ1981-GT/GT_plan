# E1 孤儿组件契约核查 (Task 1)

## 1. 8 个组件的 `defineProps` 签名

### 6 个 sheet 专属组件（统一签名）

| 组件 | props |
|------|-------|
| `E1TabCreditCheck` | `wpId` / `projectId` / `allResponses` / `saveImmediate` / `debouncedSave` / `isReadonly` / `bsDate?` |
| `E1TabCashTxnAnalysis` | `wpId` / `projectId` / `allResponses` / `saveImmediate` / `debouncedSave` / `isReadonly` / `sheetName?` / `bsDate?` |
| `E1TabBankAccountAnalysis` | `wpId` / `projectId` / `allResponses` / `saveImmediate` / `debouncedSave` / `isReadonly` / `sheetName?` / `bsDate?` |
| `E1TabDepositInterestDaily` | `wpId` / `projectId` / `allResponses` / `saveImmediate` / `debouncedSave` / `isReadonly` / `sheetName?` / `bsDate?` |
| `E1TabBankFlowReconcile` | `wpId` / `projectId` / `allResponses` / `saveImmediate` / `debouncedSave` / `isReadonly` / `sheetName?` / `bsDate?` |
| `E1TabKeyPersonFlow` | `wpId` / `projectId` / `allResponses` / `saveImmediate` / `debouncedSave` / `isReadonly` / `sheetName?` / `bsDate?` |

**差异**：`E1TabCreditCheck` 没有 `sheetName` prop（硬编码 `sheetCode = 'E1-19'`），
其余 5 个有 `sheetName?`。全部 6 个都有 `bsDate?`。

### 宿主当前传参模式

```
:wp-id :project-id :all-responses :save-immediate :debounced-save :is-readonly :bs-date
```

**缺口**：宿主没有传 `:sheet-name`。对 5 个 IPO 组件需要补传（E1TabCreditCheck 不需要）。

### 两个 OCR 弹窗

| 弹窗 | props |
|------|-------|
| `E1CutoffOcrConfirmDialog` | 待读源码确认 |
| `E1LargeCheckOcrConfirmDialog` | 待读源码确认 |

### `E1IpoSheetChrome`

被 5 个 IPO 组件的 `<template>` 包裹使用（`<E1IpoSheetChrome ...>`），
传 `title` / `sheet-code` / `is-readonly` / `show-applicable` / slots。
接线后这 5 个组件不再是孤儿 → `E1IpoSheetChrome` 也不再是传递性死代码。

## 2. 持久化键

### E1TabCreditCheck（非 IPO 系列）

- pack: `E1-credit-check-pack`
- note: `E1-credit-audit-note-check`
- conclusion: `E1-credit-audit-conclusion-check`
- query form: `E1-credit-query-form`
- **无 legacy 回退**（E1-19 以前走 `E1TabCreditReport variant="check"`，
  其数据键是 `E1-credit-check-rows`/`-query-rows`，与本组件 pack 键不冲突也不需要迁移）

### 5 个 IPO 组件（含 legacy 回退）

各自 composable 含 `allResponses.get('E1-ipo-E1-2X-rows')` 兜底。
写入只用新 pack 键。共享 `E1-ipo-applicable` 开关键。

| sheet | pack 键 | legacy 键 |
|---|---|---|
| E1-26 | `E1-cash-txn-pack` / `-audit-note` / `-audit-conclusion` | `E1-ipo-E1-26-rows` / `E1-ipo-audit-note-E1-26` / `E1-ipo-audit-conclusion-E1-26` |
| E1-29 | `E1-bank-analysis-pack` / `-audit-note` / `-audit-conclusion` | `E1-ipo-E1-29-rows` … |
| E1-30 | `E1-deposit-daily-pack` / `-audit-note` / `-audit-conclusion` | `E1-ipo-E1-30-rows` … |
| E1-31 | `E1-bank-flow-pack` / `-audit-note` / `-audit-conclusion` | `E1-ipo-E1-31-rows` … |
| E1-32 | `E1-keyperson-flow-pack` / `-audit-note` / `-audit-conclusion` | `E1-ipo-E1-32-rows` … |

## 3. 宿主分发现状与接线方案

### 当前
- E1-19 → `E1TabCreditReport variant="check"`（**错误**：应为 `E1TabCreditCheck`）
- E1-26~32 → `E1TabIpoSpecial`（正则 `/^E1-(2[6-9]|3[0-2])$/`）

### 接线后
- E1-19 → `E1TabCreditCheck`（无 variant prop）
- E1-26 → `E1TabCashTxnAnalysis`
- E1-27 → `E1TabIpoSpecial`（保留）
- E1-28 → `E1TabIpoSpecial`（保留）
- E1-29 → `E1TabBankAccountAnalysis`
- E1-30 → `E1TabDepositInterestDaily`
- E1-31 → `E1TabBankFlowReconcile`
- E1-32 → `E1TabKeyPersonFlow`

### ipoSheetCode 收窄
```ts
// 原：/^E1-(2[6-9]|3[0-2])$/ → 匹配 26-32 全部 7 张
// 新：/^E1-(27|28)$/         → 只匹配无专属组件的 2 张
```

## 4. 关键 ⚠️

- `E1TabCreditReport` **没有 `variant` prop**，它从 `sheetName` 推断 variant。
  宿主传 `variant="check"` 是个静默失效的无效 HTML 属性（但无害）
- 接线 E1-19 改指 `E1TabCreditCheck` 后，`variant="check"` 这行要删掉
  （`E1TabCreditCheck` 也没有 `variant` prop）
- 5 个 IPO 组件需要补传 `:sheet-name`（宿主有 `props.sheetName`），
  但 `E1TabCreditCheck` 不需要（它硬编码 sheetCode）
