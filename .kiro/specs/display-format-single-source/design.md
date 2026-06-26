# 显示格式化单一真源 — Design

## 架构总览

```
                    ┌─────────────────────────────────┐
                    │  displayPrefs store (唯一真源)   │
                    │  - amountUnit/decimals/showZero  │
                    │  - negativeRed/highlightThreshold│
                    │                                  │
                    │  暴露方法：                       │
                    │   fmt(v, opts?)  = fmtAmount     │ ← 已有 fmt，补 opts/别名
                    │   fmtDateTime(v)  ──┐            │
                    │   fmtPercent(v,d?)  │            │
                    └─────────┬───────────┼────────────┘
                              │           │ 转发
            ┌─────────────────┘           ▼
            ▼                     utils/formatters.ts
   utils/formatAmount.ts         (fmtDateTime 唯一实现)
   (转发，向后兼容)
            │
            ▼
   43 个组件 / 70+ 散落处 → 改 import 统一出口（分批）
```

设计原则（ponytail 阶梯）：
- **第 1 步「需要存在吗」**：`fmt` 已存在，不重写，只补 `fmtAmount` 别名 + `opts.rawUnit` + null 占位。
- **第 2 步「内置能做」**：百分比/时间用 `Intl` / 现成 `Date`，不引依赖。
- **第 4 步「已有依赖」**：复用 `fmtAmountUnit`（displayPrefs 已 import 的工具）。

## 数据模型

无 DB 变更。纯前端 store + util 重构。

## 接口设计

### displayPrefs store 新增/调整

```ts
// 金额：扩展现有 fmt
function fmt(v: any, opts?: { rawUnit?: boolean }): string {
  if (v == null || (typeof v !== 'number' && isNaN(Number(v)))) return '—'
  if (opts?.rawUnit) {
    // 不做单位换算，仅按 decimals/负数规则格式化原始元值
    return fmtRawAmount(Number(v), decimals.value, showZero.value)
  }
  return fmtAmountUnit(v, amountUnit.value, decimals.value, showZero.value)
}
const fmtAmount = fmt  // 语义别名

// 时间：转发 util 唯一实现
function fmtDateTime(v: string | Date | null | undefined): string {
  return _fmtDateTime(v)  // import from utils/formatters
}

// 百分比：新增
function fmtPercent(v: any, d = 1): string {
  if (v == null || isNaN(Number(v))) return '—'
  return `${Number(v).toFixed(d)}%`
}

return { ...existing, fmt, fmtAmount, fmtDateTime, fmtPercent }
```

### utils/formatters.ts

- `fmtDateTime` 保留为唯一时间实现，补 null/非法日期返回 `'-'`（若未覆盖）。
- 金额相关函数（`fmtAmount` 等）改为从 displayPrefs 逻辑转发，或标注 `@deprecated 改用 displayPrefs.fmt`。

### utils/formatAmount.ts

- 内部不再裸 `toLocaleString`；转发到与 store 同源的 `fmtAmountUnit`/`fmtRawAmount`，保留导出名向后兼容。

### CI 守卫脚本

`audit-platform/frontend/scripts/check-format-single-source.mjs`（node，无依赖）：
- 扫描 `src/**/*.{vue,ts}`，排除出口文件（displayPrefs.ts / formatters.ts / formatAmount.ts）。
- 命中 `toLocaleString('zh-CN'` 或 `style:\s*['"]currency['"]` → 收集行。
- 对照 `scripts/format-legacy-allowlist.json`（存量豁免），新增命中 → 退出码 1 + 打印文件:行。
- 迁移完成后逐步从 allowlist 移除已清理项。

## 迁移策略（需求 5）

分 3 批，每批迁移后跑该页面 vitest + 手测：
- **批 1（核对高频）**：TrialBalance.vue（公式详情/汇总明细/收入费用净利润弹窗）、ReviewWorkbench.vue。
- **批 2（计算弹窗群）**：components/workpaper 下 ~20 个 *Dialog.vue（折旧/减值/ECL/薪酬/所得税/公允价值/权益变动/利息/费用分析等）。
- **批 3（其余）**：confirmation 组件群 + dashboard + 剩余 views。

每批：删组件内 `formatAmount`，`import { useDisplayPrefsStore }`，模板改 `prefs.fmt(x)`。时间同理改 `prefs.fmtDateTime`。

## 测试策略

- **单元（vitest）**：`fmt` 的 null/单位换算/rawUnit/负数；`fmtPercent` 边界；`fmtDateTime` null/非法日期。
- **PBT（fast-check，max 5 examples 风格）**：任意数值 → `fmt` 不抛错且结果可解析回数值（去单位后）。
- **守卫脚本自测**：构造含裸 toLocaleString 的临时片段，断言脚本能捕获；豁免清单内的行不报。
- **回归**：迁移批次涉及组件已有 spec 测试全绿。

## 风险与缓解
- **风险**：批量改 import 可能漏改模板某处 → 缓解：每批后跑该组件测试 + Playwright 抽测金额显示。
- **风险**：`rawUnit` 误用导致该换算的没换算 → 缓解：仅在确需原始元值处用，code review 关注。
