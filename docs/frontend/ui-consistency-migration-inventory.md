# UI 一致性迁移清单

> 自动扫描生成，用于跟踪统一治理进度。
> 扫描范围：`audit-platform/frontend/src/views/` + `components/`

## 1. 裸 `el-table` 使用清单

| 文件 | 出现次数 | 场景 | 迁移优先级 |
|------|---------|------|-----------|
| `views/TrialBalance.vue` | 7 | 明细表+汇总表+穿透弹窗+溯源弹窗 | P1（复杂双表头） |
| `views/WorkpaperTableEditor.vue` | 1 | 简单数据表 | P1 |
| `views/WorkpaperSummary.vue` | 1 | 汇总展示 | P1 |
| `views/WorkpaperHybridEditor.vue` | 1 | 行编辑表 | P1 |
| `views/workpaper-list/WorkpaperWorkbenchView.vue` | 3 | 列表+卡片 | P1 |
| `views/WorkHoursPage.vue` | 1 | 工时列表 | P2 |
| `views/ValidationRules.vue` | 1 | 规则列表 | P2 |
| `views/UserManagement.vue` | 1 | 用户管理 | P2 |
| `views/ConsolidationIndex.vue` | 多处 | 合并表 | P1 |
| `views/DeliverableCenter.vue` | 若干 | 交付物表 | P2 |

**治理策略**：新增裸 `el-table` 必须有 `<!-- allow-el-table: 原因 -->` 注释，CI 扫描脚本检查。

---

## 2. 裸 `ElMessage.error` 使用清单

| 文件 | 出现次数 | 场景 |
|------|---------|------|
| `views/TrialBalance.vue` | 1 | 未找到列 |
| `views/DeliverableCenter.vue` | 6 | 加载/生成/审批失败 |
| `views/ConsolidationIndex.vue` | 2 | 错误消息+保存失败 |
| `views/workpaper-editor/CycleDialogHost.vue` | 1 | chunk 加载失败 |
| `composables/useApiError.ts` | 1 | showApiError |
| `composables/useChainExecution.ts` | 1 | 链路执行失败 |
| `components/workpaper/TsjReviewFindings.vue` | 2 | 确认/驳回失败 |
| `components/workpaper/SideTimerTab.vue` | 1 | 缺少信息 |
| `components/workpaper/LineageGraphPanel.vue` | 1 | 溯源查询失败 |
| `components/workpaper/ItemAttachment.vue` | 1 | 文件大小校验 |
| `components/workpaper/InventoryStocktakeDialog.vue` | 1 | 签字校验 |
| `components/workpaper/GtCustomWpEditor.vue` | 1 | 缺少项目上下文 |
| `components/workpaper/GtAuditSheet.vue` | 1 | 刷新失败 |
| `components/workpaper/FixedAssetStocktakeDialog.vue` | 1 | 签字校验 |
| `components/workpaper/ExportProgressBar.vue` | 1 | 导出失败 |
| `components/workpaper/AttachmentDropZoneOverlay.vue` | 1 | 上传失败 |
| `components/workpaper/actions/DocumentRecognizeDialog.vue` | 1 | 识别失败 |
| `components/wizard/ConsolScopeConfigDialog.vue` | 1 | 配置失败 |
| `components/wizard/BatchImportDialog.vue` | 2 | 模板下载/导入失败 |
| `components/notes/NoteOfflineImportDialog.vue` | 1 | 校验失败 |
| `components/extension/TemplateUpload.vue` | 2 | 格式/大小校验 |
| `utils/http.ts` | 1 | 403 拦截 |
| `main.ts` | 2 | 全局/路由错误 |

**治理策略**：API 错误统一走 `handleApiError(e, context)`；前端校验（文件大小/格式）可保留 `ElMessage.warning`；CI 扫描脚本禁止新增裸 `ElMessage.error(err.message)` 模式。

---

## 3. 页面级 `toFixed` 使用清单

| 文件 | 场景 | 是否需迁移 |
|------|------|-----------|
| `views/ReportView.vue` | 变动率百分比展示 | ⚠️ 应走 Decimal |
| `views/QCDashboard.vue` | 比率展示 (×100%) | 低风险（非金额） |
| `views/PerformanceMonitor.vue` | ms/命中率 | 不迁移（性能数据非金额） |
| `views/ProjectDashboard.vue` | 步骤耗时 | 不迁移 |
| `views/ManagerDashboard.vue` | 紧急度百分比 | 低风险 |
| `views/composables/useReportColumns.ts` | 金额格式化 | ⚠️ 应走 `GtAmountCell` |
| `views/LedgerPenetration.vue` | 文件大小 | 不迁移 |
| `views/KnowledgeBase.vue` | 文件大小 | 不迁移 |
| `views/PrivateStorage.vue` | 文件大小 | 不迁移 |
| `views/PDFExportPanel.vue` | 文件大小 | 不迁移 |
| `views/AttachmentManagement.vue` | 文件大小 | 不迁移 |
| `views/AccountMappingPage.vue` | 进度条百分比 | 不迁移 |

**治理策略**：金额相关 `toFixed` 必须替换为 `GtAmountCell` 或 `formatAmount` + Decimal；非金额数据（文件大小/耗时/百分比）可保留。

---

## 4. 试点页面现状盘点

### 4.1 TrialBalance.vue（试算表）

| 维度 | 当前实现 | 目标 |
|------|---------|------|
| Header | `GtPageHeader` + `GtInfoBar` | ✅ 已对齐 |
| Toolbar | `GtToolbar` (show-copy/fullscreen/formula) + 自定义按钮组 | ✅ 已对齐 |
| Loading | `v-loading` 指令 | ✅ 可接受 |
| Empty | `el-empty` (原生) | 应改 `GtEmpty` |
| Save | 无保存状态（只读展示） | N/A |
| 金额展示 | 模板内 `formatAmount` + 条件格式 | 部分应走 `GtAmountCell` |
| 错误处理 | 1 处裸 `ElMessage.error` | 应改 `handleApiError` |

### 4.2 WorkpaperEditor.vue（底稿编辑器）

| 维度 | 当前实现 | 目标 |
|------|---------|------|
| Header | `EditorBanners` + 自定义工具栏 | 可考虑 `GtPageShell` 包裹 |
| Toolbar | 手写 `gt-wp-editor-toolbar` | 应走 `GtToolbar` |
| Loading | `v-loading` 指令 | ✅ 可接受 |
| Empty | 无（始终有内容） | N/A |
| Save | 手写 `dirty` ref + 手动保存逻辑 | 应走 `useEditStateMachine` |
| 错误处理 | 混用 `handleApiError` + 裸 ElMessage | 统一走 `handleApiError` |

### 4.3 DisclosureEditor.vue（附注编辑器）

| 维度 | 当前实现 | 目标 |
|------|---------|------|
| Header | `GtPageHeader` + `GtInfoBar` | ✅ 已对齐 |
| Toolbar | `GtToolbar` + 自定义按钮组 | ✅ 已对齐 |
| Loading | `v-loading` 指令 | ✅ 可接受 |
| Empty | 条件渲染 el-empty | 应改 `GtEmpty` |
| Save | 手写 saving ref | 应走 `useEditStateMachine` |
| 错误处理 | 裸 catch + ElMessage | 应走 `handleApiError` |

### 4.4 ReportView.vue（财务报表）

| 维度 | 当前实现 | 目标 |
|------|---------|------|
| Header | `GtPageHeader` + `GtInfoBar` | ✅ 已对齐 |
| Toolbar | `GtToolbar` + radio group + 按钮 | ✅ 已对齐 |
| Loading | `v-loading` 指令 | ✅ 可接受 |
| Empty | 条件渲染 | 应改 `GtEmpty` |
| Save | 无（展示为主） | N/A |
| 金额展示 | `useReportColumns.ts` 内 `toFixed(2)` | ⚠️ 应走 Decimal |
| 错误处理 | 混用 | 应统一 |

### 4.5 ConsolidationIndex.vue（合并报表）

| 维度 | 当前实现 | 目标 |
|------|---------|------|
| Header | `GtPageHeader` + `GtInfoBar` | ✅ 已对齐 |
| Toolbar | `GtToolbar` + 自定义按钮 | ✅ 已对齐 |
| Loading | `v-loading` 指令 | ✅ 可接受 |
| Empty | `GtEmpty` developing | ✅ 已对齐 |
| Save | 无独立保存逻辑 | N/A |
| 错误处理 | 2 处裸 `ElMessage.error` | 应改 `handleApiError` |

---

## 5. 迁移优先级汇总

### P0（已完成 ✅）
- [x] `GtPageShell` 增强（slots: header/context/toolbar/banners/default）
- [x] `GtAmountCell` 使用规范文档化
- [x] `handleApiError` 扩展至 views + components
- [x] `useEditStateMachine` 增强 + 接入 WorkpaperEditor/DisclosureEditor

### P1（已完成 ✅）
- [x] TrialBalance 表格能力对账（双表头、合计、右键、编辑列）
- [x] ReportView 表格能力对账（动态列、合并单元格、横向滚动）
- [x] DisclosureEditor 表格能力对账（动态行列、合并、公式）
- [x] 复制粘贴增强（HTML table + 纯文本 matrix + diff 预览 + undo）
- [x] 加载空态统一（skeleton + GtEmpty 四类预设 + AsyncJobProgress）
- [x] 显示偏好扩展（density/fontSize/amountUnit/fixedColumns）

### P2（全量治理 — 当前阶段）

#### P2-1. 全量页面迁移

按访问频率排序，剩余页面迁移计划：

| 优先级 | 页面 | el-table 数量 | 场景 | 迁移目标 | 状态 |
|--------|------|--------------|------|---------|------|
| 高频 | `TrialBalance.vue` | 7 | 明细+汇总+穿透+溯源 | `GtTableExtended`（P1 已对账，代码级保留 el-table） | ⚠️ 豁免（复杂双表头+span-method） |
| 高频 | `ConsolidationIndex.vue` | 8+ | 合并报表+穿透+映射 | `GtTableExtended`（复杂 span-method） | ⚠️ 豁免（矩阵视图+动态子表头） |
| 高频 | `WorkpaperWorkbenchView.vue` | 2 | 底稿列表+卡片 | `GtTableExtended` | 待迁移 |
| 中频 | `WorkpaperTableEditor.vue` | 1 | 简单数据表 | `GtFormTable`（行编辑） | 待迁移 |
| 中频 | `WorkpaperHybridEditor.vue` | 1 | 行编辑混合表 | `GtFormTable` | 待迁移 |
| 中频 | `WorkpaperSummary.vue` | 1 | 汇总展示 | `GtTableExtended` | 待迁移 |
| 低频 | `WorkHoursPage.vue` | 1 | 工时列表 | `GtTableExtended` | 待迁移 |
| 低频 | `ValidationRules.vue` | 1 | 规则列表 | `GtTableExtended` | 待迁移 |
| 低频 | `UserManagement.vue` | 1 | 用户管理 | `GtTableExtended` | 待迁移 |

#### 裸 `el-table` 豁免白名单

以下页面因场景复杂度允许保留裸 `el-table`，但必须标注豁免注释：

| 页面 | 豁免原因 | 注释要求 |
|------|---------|---------|
| `TrialBalance.vue` | 双表头+span-method+汇总行+穿透弹窗内嵌表 | `<!-- allow-el-table: 双表头+span-method，GtTableExtended 暂不支持 -->` |
| `ConsolidationIndex.vue` | 矩阵视图+动态子列表头+span-method+转置 | `<!-- allow-el-table: 合并矩阵报表，需 span-method+动态多级表头 -->` |

**其余页面均应迁移至 `GtTableExtended` 或 `GtFormTable`，不得新增豁免。**

#### PR 组件选择声明（CI 强制）

所有新增页面 PR 必须在 PR 描述中声明表格组件选择（已在 `.github/pull_request_template.md` 追加）：

```markdown
## 表格组件选择声明（新增含表格页面必填）
- [ ] 使用 `GtTableExtended`（展示型：排序/筛选/复制/只读）
- [ ] 使用 `GtFormTable`（编辑型：行内编辑/dirty/校验/撤销）
- [ ] 使用裸 `el-table` + 豁免注释（说明原因：___________）
- [ ] 本 PR 不涉及表格
```

#### P2-2. `GtEditableTable` 退役计划

详见 `docs/frontend/gt-editable-table-retirement-plan.md`。

---

## 6. 适用边界说明

以下页面**不接入** `GtPageShell`：
- `Login.vue` — 登录页，无项目上下文
- `Register.vue` — 注册页
- `NotFound.vue` — 404 页
- `DevelopingPage.vue` — 开发中占位页
- 纯弹窗/抽屉组件 — 无独立页面骨架需求
- 系统管理页面（`UserManagement`/`SystemSettings`）— 非项目维度

---

## 7. CI 治理门禁

| 检查项 | 脚本 | 行为 |
|--------|------|------|
| 裸 `el-table` 新增 | `check_naked_el_table` | 无豁免注释 → CI fail |
| 裸 `ElMessage.error` 新增 | `check_elmessage_error` | CI fail |
| `GtEditableTable` 新增引用 | `check_gteditabletable_new_usage` | CI warning（观察期后升级 fail） |
| 新页面未声明组件选择 | PR template 自检 | reviewer 手动拒绝 |
