# Task 14 / C-13 — G3 应收股利 lane 交付（方案 A 整表重建）

commit `e1c838228`（12 文件）

## 前端改造（useG3Detail.ts）

**DividendDetailRow** 整表重建：按模板 `明细表G3-2` 的 32 列矩阵重建。
旧 34 字段中 30 个不在模板里的保留为非受管（`@deprecated` 移交 G3-4/G3-5）。

新增字段：
- `agingCategory: G3AgingCategory`（区归属：`within_one_year` / `over_one_year`）
- 32 个受管字段（对应模板 A + C..AG 列）

`enrich()` 计算 12 个模板公式列 + 保留旧非受管公式（权益份额/分红总额/逾期天数等）兼容。

## 后端两区 spec

`phase5_g3_02_detail.py`：两区 `RowTableSheetSpec`：
- 区① R13-R20（账龄一年以内），uuid=AH
- 区② R23-R28（账龄一年以上），uuid=AI
- 三级表头 R9/R10/R11（`header_rows=3`，G 循环唯一）
- 12 公式列 F M N O P T AA AB AC AD AE AF，两区**完全相同**

## entry 层

`phase5_g3_dividend_receivable.py`：从 G9 entry 派生适配（638 行）。
- ENTRY_ID = `xlsx/gt-g3-dividend-receivable`
- ADAPTER_ID = `g3.dividend_receivable_detail`
- PAYLOAD_COLUMN = `conclusion`（conclusion_only 族）

## 契约

`g3.dividend_receivable_detail.json`，digest = `5c195b1640c41b9e7208d9be479dcc2231ea213c307d12dfb342e4fe32c82e8f`

## 验证

- 六 lane 全套：**761 passed / 1 failed**（仅剩 P18 = Task 15）
- 前端 G3 兼容性：17 passed / 0 failed
- 行数门禁：whitelist 更新后全通过
- resync source_ref 已同步
