# Lane 2 (i2-i4-i5) 批量现算证据

**日期**：2026-09-27

```
============================================================
T3: IC-6 位置化身份在 I2/I4/I5 命中数
============================================================
  I2: 位置化 site = 0
  I4: 位置化 site = 0
  I5: 位置化 site = 0

============================================================
T4: I2 第二写路径 — useI2FormData.ts 消费方
============================================================
  useI2FormData.ts: 501 行
  useI2FormData import_prod = 4 (expected 4)
  useI4FormData import_prod = 0 (expected 0)

============================================================
T12: I5 内置行重置 — useI5Detail.ts#L821-839
============================================================
  L821:   function removeRow(rowId: string): void {
  L822:     const idx = rows.value.findIndex((r) => r.rowId === rowId)
  L823:     if (idx < 0) return
  L824:     const row = rows.value[idx]
  L825:     if (row.isBuiltin) {
  L826:       rows.value[idx] = emptyI5DetailRow({
  L827:         projectName: row.projectName,
  L828:         name: row.projectName,
  L829:         isBuiltin: true,
  L830:         indexRef: row.indexRef || I5_BUILTIN_CATEGORIES.find((c) => c.name === row.projectName)?.indexRef || '',
  L831:       })
  L832:     } else {
  L833:       rows.value.splice(idx, 1)
  L834:     }
  L835:     if (activeRowIndex.value >= rows.value.length) {
  L836:       activeRowIndex.value = rows.value.length - 1
  L837:     }
  L838:     _persist()
  L839:   }
  L840: 

  emptyI5DetailRow 里的 rowId 生成：
  L303: export function emptyI5DetailRow(partial?: Partial<I5DetailRow>): I5DetailRow {
  L305: rowId: generateRowId(),

============================================================
T15: gate_layer 三值
============================================================
  I2: composable=0 vue=4 → gate_layer=host_tab
  I4: composable=3 vue=2 → gate_layer=composable
  I5: composable=3 vue=2 → gate_layer=composable

============================================================
T16: I2-2-rows 引用点集合
============================================================
  I2-2-rows 引用文件数: 11
    composables\i2ConsistencyModel.ts: 1 处
    composables\useI1AdditionCheck.ts: 2 处
    composables\useI2Adjudication.ts: 1 处
    composables\useI2Capitalization.ts: 1 处
    composables\useI2CrossSheet.ts: 1 处
    composables\useI2Detail.ts: 1 处
    composables\useI2Disclosure.ts: 1 处
    composables\useI2Impairment.ts: 1 处
    composables\useI2ProjectDetail.ts: 1 处
    composables\useI2TargetedCheck.ts: 1 处
    i2\inspection\I2TabWorkHourCheck.vue: 1 处
  总引用次数: 12

============================================================
T9/T11: 三册几何
============================================================
  明细表I2-2: max_row=51 max_col=61 eff=20 formulas=92
  明细表I4-2: max_row=53 max_col=25 eff=22 formulas=98
  明细表I5-2: max_row=63 max_col=26 eff=17 formulas=334
```
