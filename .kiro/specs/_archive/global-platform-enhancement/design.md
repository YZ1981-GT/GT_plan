# 设计文档：审计平台全局化增强

## 设计原则

1. **composable 优先**：可复用逻辑抽 composable，不在组件里重复
2. **Pinia store 管全局状态**：项目上下文、显示偏好、字典、地址坐标
3. **组件层只做 UI**：GtToolbar/GtEditableTable 等只组合 composable，不含业务逻辑
4. **向后兼容**：新组件逐步替换，不一次性重写，旧代码可以和新组件共存
5. **一处修改全局生效**：格式化、样式、路径、枚举等集中管理

## 架构分层

```
┌─────────────────────────────────────────────┐
│  Views（页面）                                │
│  TrialBalance / ReportView / DisclosureEditor│
│  ConsolidationIndex / ConsolNoteTab / ...    │
├─────────────────────────────────────────────┤
│  Components（通用组件）                       │
│  GtToolbar / GtEditableTable / GtPageHeader  │
│  GtInfoBar / GtAmountCell / GtStatusTag      │
│  SelectionBar / TableSearchBar / CommentTooltip│
│  CellContextMenu / ExcelImportPreviewDialog  │
├─────────────────────────────────────────────┤
│  Composables（可复用逻辑）                    │
│  useCellSelection / useFullscreen / useLazyEdit│
│  useTableSearch / useEditMode / useExcelIO   │
│  useTableToolbar / useCopyPaste / useAutoSave│
│  useProjectSelector / useWorkflowGuide       │
│  useKnowledge / usePermission / useLoading   │
├─────────────────────────────────────────────┤
│  Stores（全局状态）                           │
│  auth / displayPrefs / project / dict        │
│  roleContext / addressRegistry               │
├─────────────────────────────────────────────┤
│  Utils（工具函数）                            │
│  formatters / http / apiPaths / statusMaps   │
│  confirm / eventBus(mitt) / sse / shortcuts  │
│  operationHistory / queryClient              │
└─────────────────────────────────────────────┘
```

## 关键设计决策

### D1：事件通信 — mitt 替代 CustomEvent

```ts
// utils/eventBus.ts
import mitt from 'mitt'
type Events = {
  'formula-changed': { action: 'saved' | 'applied' }
  'standard-change': { standard: 'soe' | 'listed' }
  'four-col-switch': { tab?: string }
  // ...
}
export const eventBus = mitt<Events>()
```
- 类型安全，IDE 自动补全
- 200 字节零依赖
- 不需要 `_redispatched` 防循环补丁

### D2：项目上下文 — useProjectStore

```ts
// stores/project.ts
export const useProjectStore = defineStore('project', () => {
  const projectId = ref('')
  const year = ref(currentYear - 1)
  const standard = ref<'soe' | 'listed'>('soe')
  const clientName = ref('')
  // 从路由自动同步（DefaultLayout watch route）
  function syncFromRoute(route) { ... }
  // 切换年度/准则自动通知所有模块
  function changeYear(y) { ... }
  function changeStandard(s) { ... }
})
```
- 所有子页面 `const { projectId, year } = useProjectStore()`
- 不再从 route.params/query 各自解析

### D3：枚举字典 — useDictStore

- 后端新增 `GET /api/system/dicts` 返回所有枚举 `{key, label, color}`
- 前端启动时加载一次，sessionStorage 缓存
- 模板中 `dictStore.label('wp_status', row.status)` 替代硬编码

### D4：GtEditableTable — 高阶表格组件

```vue
<GtEditableTable
  v-model="tableData"
  :columns="columns"
  :editable="isEditing"
  :show-selection="true"
  :lazy-edit="true"
  sheet-key="basic_info"
  @save="onSave"
>
  <template #col-company_name="{ row, editing }">
    <el-input v-if="editing" v-model="row.company_name" />
    <span v-else>{{ row.company_name }}</span>
  </template>
</GtEditableTable>
```
内置能力：查看/编辑切换、单元格选中+拖拽框选、右键菜单、批注标记、增删行+多选、全屏、懒加载编辑、小计行、Excel导入导出、displayPrefs响应、Ctrl+F搜索、SelectionBar

### D5：后端统一化

- PaginationParams：`Depends(PaginationParams)` 注入 page/page_size
- SortParams：`Depends(SortParams)` 注入 sort_by/sort_order
- BulkOperationMixin：批量 ID 校验+事务+部分失败处理
- 审计日志装饰器：`@audit_log(action="delete")` 记录 before/after diff

### D6：数据库迁移

- 方案：版本化 SQL 脚本目录 `backend/migrations/V001__init.sql`
- 启动时自动检测并执行未应用的脚本
- 记录已执行版本到 `schema_version` 表
- 不用 Alembic（之前已放弃，复杂度不匹配）

## 执行策略

分 4 个 Sprint：
1. **Sprint 1（收尾+快速见效）**：R2 收尾 + R6.7/R6.3/R6.2/R3.4/R5.3/R5.6/R5.7/R6.6（11 Task，~3天）
2. **Sprint 2（核心基础设施）**：R3.1/R3.2/R6.1/R7.2/R3.10/R7.1/R1.4/R1.6/R6.4（10 Task，~5天）
3. **Sprint 3（组件层+后端）**：R5.1/R5.4/R3.5/R3.3/R4.1/R7.3/R7.4/R7.5/R5.8/R3.6/R3.7/R3.8/R3.9/R4.2（15 Task，~8天）
4. **Sprint 4（高阶+验证）**：R5.2/R1.1/R1.2/R1.5/R1.3/R6.5/R8/R9/R10/R11（10 Task，~7天）
