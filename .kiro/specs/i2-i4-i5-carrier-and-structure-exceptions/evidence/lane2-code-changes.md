# Lane 2 代码改动 + 交接证据

**日期**：2026-09-27

## 代码改动

### useI5Detail.ts — 内置行重置保留 rowId（IE-4 修复①）

```diff
- rows.value[idx] = emptyI5DetailRow({
-   projectName: row.projectName,
+ rows.value[idx] = emptyI5DetailRow({
+   rowId: row.rowId,  // BP-6 修复：重置时保留原 rowId，不让身份漂移
+   projectName: row.projectName,
```

**改动量**：1 行。`emptyI5DetailRow` 的 partial 参数增加 `rowId: row.rowId`，
使重置后 rowId 不变（之前会调 `generateRowId()` 生成新值）。

修复②（契约层声明 `builtin_row_identity_field=projectName`）写入 i5 契约。

## 三份契约

| 契约 | contract_id | gate_layer | defined_name_baseline | uuid_column | regions | 特殊字段 |
|---|---|---|---|---|---|---|
| i2 | development_expenditure_detail | **host_tab** | 0 | 21 | 0 | frozen_key=true, second_write_path, secondary_ui_gate=false |
| i4 | long_term_prepaid_detail | composable | **476** | 23 | 2 | forbidden_carriers=[useI4FormData.ts], dual_write unverified |
| i5 | other_noncurrent_assets_detail | composable | **334** | 18 | **3** (含 fully_derived_region) | builtin_row_identity_field=projectName, region_mirror, passthrough unverified, E2E seed |

## 现算验证摘要

| 项 | 现算 | 与 design | 
|---|---|---|
| IC-6 位置化 I2/I4/I5 | 各 0 | ✅ |
| useI2FormData 消费 | 4（活） | ✅ |
| useI4FormData 消费 | 0（死） | ✅ |
| I5 removeRow L826 不含 rowId | 已确认+已修 | ✅ |
| gate_layer | I2=host_tab / I4=composable / I5=composable | ✅ |
| I2-2-rows 引用 | 11 文件 12 处（跨 entry=useI1AdditionCheck.ts） | ✅ |
| 三册几何 eff | I2=20 / I4=22 / I5=17 | ✅ |
| definedName | I4=476 / I5=334 | ✅ |

## 阻塞项

- T18 roundtrip: `[ ]*` 阻塞于 BP-4（三条都只能合成载荷；I5 E2E 种子不可作基线）
- T19 人工审核: `[ ]*` 阻塞于 BP-2/BP-3
- I2 发布门收敛到 composable: `[ ]*` 需 UI 回归实测
- useI4FormData.ts 删文件: 另起清理 spec

## 交接核验

- IC 引用闭合性: 已在地基 Task 25 验证（20/20 全闭合无悬空）
- entry 归属: {I2, I4, I5} 与地基 Task 25 一致
- 与 lane 1 对账: `I2-2-rows` 冻结在两份 spec 一致；两 lane 的 `row_delete_api_kind` 未复用同一断言（lane 1 全 index，lane 2 是 1:2 index/identity/identity）
