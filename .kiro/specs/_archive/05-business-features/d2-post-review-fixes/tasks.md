# Implementation Plan: D2 复盘修复

## Overview

D2 模块复盘后发现的 3 个缺口修复：①版本链组件未挂载（provide 了 ref 但模板没渲染 GtWpVersionTrail）；②导入导出 round-trip PBT 因 remark trim 问题失败；③D2-10 ECL↔D2-3 勾稽 alert 未在 UI 展示。

## Tasks

- [x] 1. GtWpVersionTrail 组件挂载
  - [x] 1.1 在 GtD2AccountsReceivable.vue template 末尾（</template> 前）添加 `<GtWpVersionTrail ref="versionTrailRef" :wp-id="props.wpId" :project-id="props.projectId" />`
  - 确保 import GtWpVersionTrail 组件
  - 确保 versionTrailRef 已由 useWorkpaperVersionToolbar 返回且在 setup 中可用
  - get_diagnostics 验证无错误

- [x] 2. 修复 import/export remark trim bug
  - [x] 2.1 在 useD2VcImportExport.ts 的 deserializeSheetDataToRows 函数中，对所有 string 类型字段反序列化时做 `.trim()`（或在 serializeRowsToSheetData 导出时 trim）
  - 根因：remark 字段含 " "（单空格）导出到 xlsx → 反序列化时原样保留 → 与 trim 后的 "" 不等
  - 修复策略：反序列化时 trim（因为源数据可能含意外空格，trim 是安全的）
  - [x] 2.2 运行 useD2VcImportExport.pbt.spec.ts 确认 P17 全绿

- [x] 3. D2-10 ECL 勾稽 alert 展示
  - [x] 3.1 在 D2TabEcl.vue 顶部添加 el-alert 展示 eclVsBadDebtDiff（inject d2CrossSheet，读 eclVsBadDebtDiff.value）
  - 样式与主入口 reconciliationDiff alert 一致（type=warning, show-icon, :closable=false）
  - 文案："D2-10 ECL单项合计(X) 与 D2-3坏账准备期末(Y) 差异 Z 元，请核实"
  - 仅在 !isBalanced 时显示
  - get_diagnostics 验证无错误

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "2.1"] },
    { "id": 1, "tasks": ["2.2", "3.1"] }
  ]
}
```
