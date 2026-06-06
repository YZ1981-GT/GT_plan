# 设计文档：平台 UI、编辑状态与全局组件一致性

## 概述

本 spec 收敛全平台页面框架、表格、金额、复制粘贴、编辑状态、加载空态、异常处理和显示偏好。目标是让审计人员在试算表、底稿、报表、附注、合并、复核等页面获得一致的操作和视觉体验。

## 核心设计

### 1. 页面骨架

新增或固化 `GtPageShell`：

```text
GtPageShell
  ├─ GtPageHeader
  ├─ ProjectContextBar
  ├─ GtToolbar / DomainToolbar
  ├─ StatusBanners
  └─ PageContent
```

业务页面优先组合该骨架，不再手写各自的 header/action row。

### 2. 表格决策树

延续 `docs/frontend/component-usage.md`：

| 场景 | 组件 |
|---|---|
| 展示、排序、筛选、复制 | `GtTableExtended` |
| 行内编辑、撤销、校验 | `GtFormTable` |
| 旧代码兼容 | `GtEditableTable`，限期迁移 |
| 特殊第三方渲染 | 豁免注释 |

CI 继续扫描裸 `el-table`，新增 `allow-el-table` 必须写原因。

### 3. 金额与复制粘贴

统一：

- `GtAmountCell`
- `decimal.ts`
- `formatAmount`
- `useCopyPaste`
- `usePasteImport`

粘贴过程：

```text
clipboard text/html
  -> parse matrix
  -> normalize amount
  -> preview diff
  -> validate editable cells
  -> apply with undo stack
  -> audit trail
```

### 4. 编辑状态机

新增 `useEditStateMachine`：

```text
pristine -> dirty -> saving -> saved
dirty -> conflict
any -> readonly / locked / archived
```

所有编辑页面状态栏显示：

- 是否已保存
- 保存时间
- 锁定人
- 冲突状态
- 只读原因

### 5. 统一反馈组件

| 场景 | 组件 |
|---|---|
| 首屏加载 | skeleton |
| 局部刷新 | v-loading |
| 异步任务 | `AsyncJobProgress` |
| 空数据 | `GtEmpty` no-data |
| 无权限 | `GtEmpty` no-permission |
| 开发中 | `GtEmpty` developing |
| API 错误 | `handleApiError` |

### 6. 显示偏好

扩展 `displayPrefs`：

- 字号：compact / normal / large
- 金额单位：元 / 千元 / 万元
- 深色模式
- 表格密度
- 固定关键列

## 不在范围

- 不重做完整设计系统。
- 不删除 Element Plus，继续作为基础组件库。
- 不立即删除 `GtEditableTable`。

## 现有代码锚点

### 全局组件

- `components/common/GtPageHeader.vue`
- `components/common/GtToolbar.vue`
- `components/common/GtTableExtended.vue`
- `components/common/GtFormTable.vue`
- `components/common/GtEditableTable.vue`
- `components/common/GtAmountCell.vue`
- `components/common/GtEmpty.vue`
- `components/common/AsyncJobProgress.vue`

### Composables / Utils

- `composables/useEditMode.ts`
- `composables/useEditorSave.ts`
- `composables/useWorkpaperAutoSave.ts`
- `composables/useCopyPaste.ts`
- `composables/usePasteImport.ts`
- `stores/displayPrefs.ts`
- `utils/decimal.ts`
- `utils/errorHandler.ts`
- `utils/formatAmount.ts`

### 首批试点页面

- `views/TrialBalance.vue`
- `views/WorkpaperEditor.vue`
- `views/ReportView.vue`
- `views/DisclosureEditor.vue`
- `views/ConsolidationIndex.vue`

## 迁移策略

1. P0 不做全量视觉重构，只接入骨架、金额、错误处理、编辑状态。
2. P1 迁移表格时按页面逐个 readCode，确认列定义、合并单元格、右键菜单、虚拟滚动后再替换。
3. `GtEditableTable` 保持兼容，但新增使用加 warning。
4. 裸 `el-table` 采用 baseline + 豁免注释治理。

## CI 草案

- `check_naked_el_table`
- `check_elmessage_error`
- `check_amount_float_usage`
- `check_page_shell_adoption`
- `check_gteditabletable_new_usage`

## 风险与回滚

- 风险：表格迁移破坏合并单元格或虚拟滚动。  
  回滚：逐页面 feature flag，保留旧表格实现到 UAT 结束。
- 风险：统一编辑状态机与旧 auto-save 冲突。  
  回滚：先在单页面启用，旧保存逻辑保留 facade 兼容。
