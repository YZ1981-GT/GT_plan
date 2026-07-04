# Design: F2 存货监盘 f2-stocktake-bundle

## Architecture

```
GtF2StocktakeBundle.vue
├── F2-21A → GtAProgramConsole
├── F2-21   → F2TabStocktakeQuestionnaire → F2StocktakeSectionForm
├── F2-22   → F2TabStocktakePlan
├── F2-23   → F2TabStocktakeSummary
├── F2-24   → F2TabStocktakeReconcile (narrative + table)
├── F2-25   → F2TabStocktakeSampleResult
└── F2-26   → F2TabStocktakeRollforward
```

## Persistence (checklist remark JSON)

| Sheet | Keys |
|-------|------|
| F2-21~23 | `F2-{n}-fields`, `F2-{n}-note` |
| F2-24~26 | `F2-{n}-fields`, `F2-{n}-rows`, `F2-{n}-note` |
| F2-24~26 叙述 | `F2-{n}-narrative-note`（仅占位，结论用 `-note`） |
| Legacy | `F2-21-rows` → 双读迁移 |

## Backend

| Module | Endpoints |
|--------|-----------|
| `_f2_stocktake.py` | render-config |
| `_f2_stocktake_import_export.py` | f2-st/export-template, import-data, export-data（F2-24~26） |
| `_f2_stocktake_contract_ocr.py` | f2-st/contract-ocr（F2-24~26） |
| `_f2_stocktake_ai.py` | f2-st/ai-generate |

## UI 原则

- stack 布局、13px、multiline 叙述字段 fullWidth
- 纯文本 Tab 无 import/export；混合 Tab 工具栏在表格区
- `InventoryStocktakeDialog` 仍可从 F2-21~26 触发（现场监盘）

## ADR

- **文本优先**：F2-21 底稿为 d-form-confirmation，地点表并入 countSchedule/warehouses 叙述字段
- **F2-21 无 Excel round-trip**：避免与问卷语义冲突
