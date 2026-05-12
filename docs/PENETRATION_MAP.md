# 穿透闭环路径文档

> 日期：2026-05-12
> 对应需求：R9 F6

## 穿透路径总览

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐     ┌──────────────┐
│  报表视图    │────▶│  试算平衡表   │────▶│  序时账          │────▶│  凭证详情     │
│ ReportView  │     │ TrialBalance │     │ LedgerPenetration│     │  Drilldown   │
└─────────────┘     └──────────────┘     └─────────────────┘     └──────────────┘
       │                    │                      │
       ▼                    ▼                      ▼
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐
│  附注编辑器  │     │  底稿编辑器   │     │  辅助余额汇总    │
│ Disclosure  │     │ WorkpaperEdit│     │ AuxSummaryPanel  │
│   Editor    │     │              │     │                  │
└─────────────┘     └──────────────┘     └─────────────────┘
       │                    │
       ▼                    ▼
┌─────────────┐     ┌──────────────┐
│  调整分录    │◀───│  未更正错报   │
│ Adjustments │     │ Misstatements│
└─────────────┘     └──────────────┘
```

## 穿透方法清单（usePenetrate composable）

| 方法 | 源视图 | 目标视图 | 参数 |
|------|--------|----------|------|
| `toLedger(accountCode)` | TrialBalance / Adjustments / Misstatements | LedgerPenetration | 科目编码 |
| `toReportRow(type, rowCode)` | ReportView | TrialBalance | 报表类型 + 行编码 |
| `toWorkpaper(wpCode)` | TrialBalance | WorkpaperList | 底稿编码 |
| `toWorkpaperEditor(wpId)` | DisclosureEditor / TrialBalance | WorkpaperEditor | 底稿 UUID |
| `toAdjustment(account)` | WorkpaperWorkbench / TrialBalance | Adjustments | 科目编码 |
| `toMisstatement(id)` | Adjustments | Misstatements | 错报 ID |
| `toNote(sectionId)` | ReportView | DisclosureEditor | 附注章节 ID |

## 穿透触发方式

| 触发方式 | 适用场景 | 实现 |
|----------|----------|------|
| 双击金额单元格 | 表格中的金额列 | `@row-dblclick` |
| 点击 GtAmountCell | 带穿透的金额组件 | `@click` + `:clickable="true"` |
| 右键菜单 | 需要多个穿透方向 | CellContextMenu |
| 面包屑返回 | 穿透后返回上级 | GtPageHeader `@back` |

## 完整闭环路径

### 路径 1：报表 → 科目 → 凭证

1. **ReportView** — 点击报表行金额 → `toReportRow()`
2. **TrialBalance** — 双击科目余额 → `toLedger()`
3. **LedgerPenetration** — 双击序时账行 → 进入凭证详情（Drilldown）
4. **Drilldown** — 查看凭证分录明细

### 路径 2：底稿 → 调整 → 错报

1. **WorkpaperWorkbench** — 审定数穿透 → `toAdjustment()`
2. **Adjustments** — 查看调整分录，金额穿透 → `toLedger()`
3. **Misstatements** — 错报金额穿透 → `toLedger()`

### 路径 3：附注 → 底稿

1. **DisclosureEditor** — 右键"查看相关底稿" → `toWorkpaperEditor()`
2. **WorkpaperEditor** — 查看底稿内容

## 面包屑导航验证

每个穿透目标视图的 GtPageHeader 组件均配置了 `@back` 事件，支持：
- 浏览器后退（`router.back()`）
- 面包屑点击返回上级

验证清单：
- [x] LedgerPenetration → 返回 TrialBalance
- [x] Drilldown → 返回 LedgerPenetration
- [x] Adjustments → 返回上级
- [x] Misstatements → 返回上级
- [x] DisclosureEditor → 返回上级
- [x] WorkpaperEditor → 返回 WorkpaperList
