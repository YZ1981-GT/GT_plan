# Composable 注册表

> 本文档记录前端 composable 的职责、调用方、废弃状态和同族关系。
> 新增 composable 的 PR 必须同步更新此注册表。

## 更新规则

1. 新增 composable → 必须在此文档登记职责和调用方
2. 修改已有 composable 公开接口 → 更新调用方列表
3. 废弃 composable → 标注 `deprecated` 和替代方案

---

## 同族分类

### 🔄 自动保存族

| Composable | 路径 | 职责 | 调用方 | 状态 |
|---|---|---|---|---|
| `useAutoSave` | `src/composables/useAutoSave.ts` | 通用自动保存（防抖 + dirty 检测） | DisclosureEditor, NoteTableEditor | ✅ 活跃 |
| `useWorkpaperAutoSave` | `src/composables/useWorkpaperAutoSave.ts` | 底稿专用自动保存（含 Univer 序列化） | WorkpaperEditor, GtWpRenderer | ✅ 活跃 |
| `useEditorSave` | `src/composables/useEditorSave.ts` | 编辑器保存动作（含冲突检测） | DisclosureEditor, GtDForm | ✅ 活跃 |

### 🔒 编辑锁族

| Composable | 路径 | 职责 | 调用方 | 状态 |
|---|---|---|---|---|
| `useEditingLock` | `src/composables/useEditingLock.ts` | 编辑锁获取/释放（WebSocket 心跳） | WorkpaperEditor, DisclosureEditor | ✅ 活跃 |
| `useSheetLock` | `src/composables/useSheetLock.ts` | Sheet 级锁（底稿内多 sheet 并发编辑） | GtAuditSheet, GtWpRenderer | ✅ 活跃 |
| `useEditMode` | `src/composables/useEditMode.ts` | 编辑/只读模式切换 | 多处 | ✅ 活跃 |
| `useEditorMode` | `src/composables/useEditorMode.ts` | 编辑器模式管理（含权限判断） | WorkpaperEditor | ✅ 活跃 |
| `useEditStateMachine` | `src/composables/useEditStateMachine.ts` | 统一编辑状态机（idle/editing/saving/error） | GtPageShell, 所有可编辑页面 | ✅ 活跃（平台原子） |
| `useLazyEdit` | `src/composables/useLazyEdit.ts` | 延迟编辑模式初始化 | 大表格场景 | ✅ 活跃 |

### 📊 表格族

| Composable | 路径 | 职责 | 调用方 | 状态 |
|---|---|---|---|---|
| `useGlobalTableLayout` | `src/composables/useGlobalTableLayout.ts` | 全局表格布局（列宽/固定列/虚拟滚动） | 多处列表页 | ✅ 活跃 |
| `useVirtualTable` | `src/composables/useVirtualTable.ts` | 虚拟滚动表格（大数据量） | LedgerPenetration, TrialBalance | ✅ 活跃 |
| `useTableSearch` | `src/composables/useTableSearch.ts` | 表格内搜索/过滤 | 多处列表页 | ✅ 活跃 |
| `useTableToolbar` | `src/composables/useTableToolbar.ts` | 表格工具栏（导出/打印/列配置） | 多处列表页 | ✅ 活跃 |
| `useExcelIO` | `src/composables/useExcelIO.ts` | Excel 导入导出（xlsx-js-style） | WorkpaperEditor, TrialBalance | ✅ 活跃 |
| `usePasteImport` | `src/composables/usePasteImport.ts` | 粘贴导入（Excel→表格） | GtAuditSheet | ✅ 活跃 |
| `useCopyPaste` | `src/composables/useCopyPaste.ts` | 通用复制粘贴 | GtAuditSheet | ✅ 活跃 |

### 🔗 Stale/联动族

| Composable | 路径 | 职责 | 调用方 | 状态 |
|---|---|---|---|---|
| `useStaleStatus` | `src/composables/useStaleStatus.ts` | stale 状态查询/展示 | ReportView, TrialBalance | ✅ 活跃 |
| `useStaleRefresh` | `src/composables/useStaleRefresh.ts` | stale 刷新触发 | ReportView | ✅ 活跃 |
| `useStaleFilter` | `src/composables/useStaleFilter.ts` | stale 数据过滤 | 列表页 | ✅ 活跃 |
| `useStaleImpact` | `src/composables/useStaleImpact.ts` | stale 影响范围预览 | LinkageContract 相关 | ✅ 活跃 |
| `useStaleImpactConfirm` | `src/composables/useStaleImpactConfirm.ts` | stale 影响确认对话框 | 编辑保存前 | ✅ 活跃 |
| `useStaleSummaryFull` | `src/composables/useStaleSummaryFull.ts` | stale 全量汇总 | Dashboard | ✅ 活跃 |
| `useNoteStale` | `src/composables/useNoteStale.ts` | 附注 stale 特化 | DisclosureEditor | ✅ 活跃 |
| `useLinkageIndicator` | `src/composables/useLinkageIndicator.ts` | 联动指示器 UI | 穿透相关组件 | ✅ 活跃 |
| `useLineagePanel` | `src/composables/useLineagePanel.ts` | 数据血缘面板 | ReportView, DisclosureEditor | ✅ 活跃 |
| `useImpactPreview` | `src/composables/useImpactPreview.ts` | 修改影响预览 | 编辑保存前 | ✅ 活跃 |

### 🧭 导航/路由族

| Composable | 路径 | 职责 | 调用方 | 状态 |
|---|---|---|---|---|
| `useNavigationStack` | `src/composables/useNavigationStack.ts` | 导航栈（面包屑+返回） | WorkpaperEditor, 穿透 | ✅ 活跃 |
| `usePenetrate` | `src/composables/usePenetrate.ts` | 穿透跳转 | ReportView, TrialBalance | ✅ 活跃 |
| `useResolveLinkageRoute` | `src/composables/useResolveLinkageRoute.ts` | LinkageContract 路由解析 | 穿透入口 | ✅ 活跃（平台原子） |
| `useWpNavigationHistory` | `src/composables/useWpNavigationHistory.ts` | 底稿浏览历史 | WorkpaperEditor | ✅ 活跃 |
| `useSheetNavFacade` | `src/composables/useSheetNavFacade.ts` | Sheet 导航 facade | GtWpRenderer | ✅ 活跃 |
| `useUniverSheetNav` | `src/composables/useUniverSheetNav.ts` | Univer sheet 导航 | GtWpRenderer | ✅ 活跃 |

### 🎯 循环编辑器族（按审计循环分）

| Composable | 路径 | 职责 | 状态 |
|---|---|---|---|
| `useDCycleEditor` | `src/composables/useDCycleEditor.ts` | D 循环（销售收入） | ✅ 活跃 |
| `useECycleEditor` | `src/composables/useECycleEditor.ts` | E 循环（货币资金） | ✅ 活跃 |
| `useFCycleEditor` | `src/composables/useFCycleEditor.ts` | F 循环（采购存货） | ✅ 活跃 |
| `useGCycleEditor` | `src/composables/useGCycleEditor.ts` | G 循环（投资） | ✅ 活跃 |
| `useHCycleEditor` | `src/composables/useHCycleEditor.ts` | H 循环（固定资产） | ✅ 活跃 |
| `useICycleEditor` | `src/composables/useICycleEditor.ts` | I 循环（无形资产） | ✅ 活跃 |
| `useKCycleEditor` | `src/composables/useKCycleEditor.ts` | K 循环（管理） | ✅ 活跃 |
| `useLCycleEditor` | `src/composables/useLCycleEditor.ts` | L 循环（筹资） | ✅ 活跃 |
| `useMCycleEditor` | `src/composables/useMCycleEditor.ts` | M 循环（股东权益） | ✅ 活跃 |
| `useNCycleEditor` | `src/composables/useNCycleEditor.ts` | N 循环（税费） | ✅ 活跃 |
| `useSimpleCycleEditor` | `src/composables/useSimpleCycleEditor.ts` | 通用简单循环编辑器 | ✅ 活跃 |

### 📋 Sheet Groups 族（循环 sheet 分组配置）

| Composable | 路径 | 职责 | 状态 |
|---|---|---|---|
| `useBAuditPlanSheetGroups` | `src/composables/useBAuditPlanSheetGroups.ts` | B 循环 sheet 分组 | ✅ 活跃 |
| `useCControlTestSheetGroups` | `src/composables/useCControlTestSheetGroups.ts` | C 循环 sheet 分组 | ✅ 活跃 |
| `useDSalesCycleSheetGroups` | `src/composables/useDSalesCycleSheetGroups.ts` | D 循环 sheet 分组 | ✅ 活跃 |
| `useFPurchaseInventorySheetGroups` | `src/composables/useFPurchaseInventorySheetGroups.ts` | F 循环 sheet 分组 | ✅ 活跃 |
| `useGInvestmentCycleSheetGroups` | `src/composables/useGInvestmentCycleSheetGroups.ts` | G 循环 sheet 分组 | ✅ 活跃 |
| `useHFixedAssetSheetGroups` | `src/composables/useHFixedAssetSheetGroups.ts` | H 循环 sheet 分组 | ✅ 活跃 |
| `useIIntangibleAssetSheetGroups` | `src/composables/useIIntangibleAssetSheetGroups.ts` | I 循环 sheet 分组 | ✅ 活跃 |
| `useJPayrollSheetGroups` | `src/composables/useJPayrollSheetGroups.ts` | J 循环 sheet 分组 | ✅ 活跃 |
| `useKAdminCycleSheetGroups` | `src/composables/useKAdminCycleSheetGroups.ts` | K 循环 sheet 分组 | ✅ 活跃 |
| `useLDebtCycleSheetGroups` | `src/composables/useLDebtCycleSheetGroups.ts` | L 循环 sheet 分组 | ✅ 活跃 |
| `useMEquityCycleSheetGroups` | `src/composables/useMEquityCycleSheetGroups.ts` | M 循环 sheet 分组 | ✅ 活跃 |
| `useNTaxCycleSheetGroups` | `src/composables/useNTaxCycleSheetGroups.ts` | N 循环 sheet 分组 | ✅ 活跃 |

### 🤖 AI/LLM 族

| Composable | 路径 | 职责 | 调用方 | 状态 |
|---|---|---|---|---|
| `useAiChat` | `src/composables/useAiChat.ts` | 通用 AI 对话 | AICommandBar | ✅ 活跃 |
| `useDocAiChat` | `src/composables/useDocAiChat.ts` | 文档级 AI 对话（含 RAG 上下文） | DocAiChatPanel | ✅ 活跃 |
| `useWpAiSuggest` | `src/composables/useWpAiSuggest.ts` | 底稿 AI 建议 | WorkpaperEditor | ✅ 活跃 |

### 🔐 权限族

| Composable | 路径 | 职责 | 调用方 | 状态 |
|---|---|---|---|---|
| `usePermission` | `src/composables/usePermission.ts` | 通用权限检查 | 全局 | ✅ 活跃 |
| `usePermissionMatrix` | `src/composables/usePermissionMatrix.ts` | 权限矩阵查询（ProjectContext 驱动） | GtPageShell, 页面级 | ✅ 活跃（平台原子） |
| `useProjectRole` | `src/composables/useProjectRole.ts` | 项目角色判断 | 多处 | ✅ 活跃 |

### 🏗️ 底稿/工作台族

| Composable | 路径 | 职责 | 调用方 | 状态 |
|---|---|---|---|---|
| `useWpRenderer` | `src/composables/useWpRenderer.ts` | 底稿渲染器状态管理 | GtWpRenderer | ✅ 活跃 |
| `useWpRenderSchema` | `src/composables/useWpRenderSchema.ts` | 底稿渲染 schema 解析 | GtWpRenderer | ✅ 活跃 |
| `useWpClassification` | `src/composables/useWpClassification.ts` | 底稿分类管理 | WorkpaperEditor | ✅ 活跃 |
| `useWpCompletionRate` | `src/composables/useWpCompletionRate.ts` | 底稿完成率计算 | WorkpaperWorkbenchView | ✅ 活跃 |
| `useWpAutoFill` | `src/composables/useWpAutoFill.ts` | 底稿自动填充 | WorkpaperEditor | ✅ 活跃 |
| `useWpFunctionalActions` | `src/composables/useWpFunctionalActions.ts` | 底稿功能操作集 | WorkpaperEditor toolbar | ✅ 活跃 |
| `useWpOfflineCache` | `src/composables/useWpOfflineCache.ts` | 底稿离线缓存 | WorkpaperEditor | ✅ 活跃 |
| `useWorkpaperRefresh` | `src/composables/useWorkpaperRefresh.ts` | 底稿刷新控制 | WorkpaperEditor | ✅ 活跃 |
| `useWorkpaperAutoSave` | `src/composables/useWorkpaperAutoSave.ts` | 底稿自动保存（同自动保存族） | WorkpaperEditor | ✅ 活跃 |
| `useWorkpaperListContext` | `src/composables/useWorkpaperListContext.ts` | 底稿列表上下文 | WorkpaperList | ✅ 活跃 |
| `useWorkpaperReviewMarkers` | `src/composables/useWorkpaperReviewMarkers.ts` | 底稿复核标记 | ReviewWorkbench | ✅ 活跃 |

### 📐 其他独立 Composable

| Composable | 路径 | 职责 | 调用方 | 状态 |
|---|---|---|---|---|
| `useAuditContext` | `src/composables/useAuditContext.ts` | 审计上下文（ProjectContext 消费） | 全局 | ✅ 活跃 |
| `useApiError` | `src/composables/useApiError.ts` | API 错误统一处理 | handleApiError | ✅ 活跃（平台原子） |
| `useBatchQuery` | `src/composables/useBatchQuery.ts` | 批量查询合并 | Dashboard | ✅ 活跃 |
| `useCellComments` | `src/composables/useCellComments.ts` | 单元格批注 | GtAuditSheet | ✅ 活跃 |
| `useCellSelection` | `src/composables/useCellSelection.ts` | 单元格选择 | GtAuditSheet | ✅ 活跃 |
| `useConflictGuard` | `src/composables/useConflictGuard.ts` | 编辑冲突守卫 | WorkpaperEditor | ✅ 活跃 |
| `useCrossCheck` | `src/composables/useCrossCheck.ts` | 交叉核对 | ReportView | ✅ 活跃 |
| `useDashboardData` | `src/composables/useDashboardData.ts` | Dashboard 数据获取 | Dashboard | ✅ 活跃 |
| `useDecimalCalc` | `src/composables/useDecimalCalc.ts` | Decimal 精确计算（金额铁律） | 金额相关组件 | ✅ 活跃 |
| `useFirstLoad` | `src/composables/useFirstLoad.ts` | 首次加载控制 | 多处 | ✅ 活跃 |
| `useFormulaStatus` | `src/composables/useFormulaStatus.ts` | 公式执行状态 | FormulaManager | ✅ 活跃 |
| `useFullscreen` | `src/composables/useFullscreen.ts` | 全屏切换 | WorkpaperEditor | ✅ 活跃 |
| `useKnowledge` | `src/composables/useKnowledge.ts` | 知识库操作 | KnowledgeBase | ✅ 活跃 |
| `useLoading` | `src/composables/useLoading.ts` | 加载状态管理 | 全局 | ✅ 活跃 |
| `useOfflineCache` | `src/composables/useOfflineCache.ts` | 通用离线缓存 | 多处 | ✅ 活跃 |
| `usePresence` | `src/composables/usePresence.ts` | 在线状态/协同 | WorkpaperEditor | ✅ 活跃 |
| `useProjectEvents` | `src/composables/useProjectEvents.ts` | 项目事件监听（SSE） | 全局 | ✅ 活跃 |
| `useProjectSelector` | `src/composables/useProjectSelector.ts` | 项目选择器 | 顶栏 | ✅ 活跃 |
| `useQualityGate` | `src/composables/useQualityGate.ts` | 质量门禁检查 | GateReadinessPanel | ✅ 活跃 |
| `useSSEDegradation` | `src/composables/useSSEDegradation.ts` | SSE 降级处理 | 全局 | ✅ 活跃 |
| `useTheme` | `src/composables/useTheme.ts` | 主题切换 | 全局 | ✅ 活跃 |

---

## PR 规范

新增 composable 的 PR **必须**：

1. 在此文档对应族中添加一行记录
2. 如果创建新族，新增族标题和表格
3. 明确标注是否与现有 composable 有功能重叠
4. 如果有重叠，说明为什么不复用现有 composable

**PR checklist 检查项**（已集成到 `.github/pull_request_template.md`）：
- [ ] 新增 composable 是否已在 `docs/frontend/composable-ledger.md` 注册？
- [ ] 是否与现有同族 composable 有功能重叠？如有，说明原因。
