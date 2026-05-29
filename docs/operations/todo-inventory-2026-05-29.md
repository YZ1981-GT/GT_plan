# TODO/FIXME 清单（2026-05-29 全仓扫描）

> migration-runner-resilience / 全局改进 #6 落地。
> 用途：模块打磨时按「该模块的 TODO 一并消化」原则使用。
> 自动生成：`backend/scripts/_collect_todos.py`（一次性，已删）

## 一、汇总

- 扫描路径：backend/app, audit-platform/frontend/src
- 总条目：**289**
- 涉及文件：**101**

### 按类别

| 类别 | 数量 | 说明 |
|------|------|------|
| cleanup | 224 | HACK/workaround 临时方案待清 |
| bug | 52 | FIXME/XXX 标记或含 bug/broken 关键词 |
| feature | 12 | implement/add/实现等待开发 |
| docs | 1 | doc/comment 文档补充 |

### 按模块

| 模块 | 条目数 | 涉及文件 |
|------|-------|---------|
| frontend/components | 87 | 16 |
| backend/services | 65 | 23 |
| frontend/views | 56 | 8 |
| frontend/其他 | 51 | 38 |
| backend/routers | 15 | 7 |
| frontend/composables | 6 | 3 |
| backend/core | 3 | 2 |
| frontend/services | 3 | 2 |
| backend/其他 | 2 | 1 |
| backend/models | 1 | 1 |

## 二、各模块详情

### frontend/components（87 条）

| 文件 | 行 | 类别 | Marker | 内容 |
|------|----|------|--------|------|
| `audit-platform/frontend/src/components/__tests__/PanoramaComponents.spec.ts` | 49 | bug | XXX | ')).toBe(SEVERITY_COLOR_MAP.info) |
| `audit-platform/frontend/src/components/ai/AIContentReviewPanel.vue` | 406 | bug | XXX | 元，上年余额人民币XXX元，变动额XXX元，变动率XX%。变动原因主要为...`, |
| `audit-platform/frontend/src/components/assignment/BatchAssignDialog.vue` | 383 | cleanup | TODO | [Batch 3]: by_level 策略的前端预览逻辑应改为调用后端 preview endpoint |
| `audit-platform/frontend/src/components/collaboration/AuditLogView.vue` | 49 | cleanup | TODO | open detail dialog |
| `audit-platform/frontend/src/components/collaboration/ConfirmationPanel.vue` | 170 | cleanup | TODO | integrate with backend |
| `audit-platform/frontend/src/components/collaboration/ConfirmationPanel.vue` | 183 | cleanup | TODO | integrate with backend |
| `audit-platform/frontend/src/components/consolidation/ConsolMiddleNav.vue` | 59 | bug | XXX | 0X（统一社会信用代码）" /> |
| `audit-platform/frontend/src/components/consolidation/ConsolMiddleNav.vue` | 65 | bug | XXX | 0X" /> |
| `audit-platform/frontend/src/components/consolidation/ConsolMiddleNav.vue` | 71 | bug | XXX | XX0X" /> |
| `audit-platform/frontend/src/components/consolidation/worksheets/ConsolWorksheetTabs.vue` | 319 | cleanup | TODO | 后续接入公式引擎后，这里触发重算各表的公式列 |
| `audit-platform/frontend/src/components/dashboard/MyTodoCard.vue` | 2 | cleanup | TODO | -card"> |
| `audit-platform/frontend/src/components/dashboard/MyTodoCard.vue` | 3 | cleanup | TODO | -header"> |
| `audit-platform/frontend/src/components/dashboard/MyTodoCard.vue` | 4 | cleanup | TODO | -title">我的待办</span> |
| `audit-platform/frontend/src/components/dashboard/MyTodoCard.vue` | 5 | cleanup | TODO | s" :loading="loading"> |
| `audit-platform/frontend/src/components/dashboard/MyTodoCard.vue` | 10 | cleanup | TODO | -loading" v-loading="true" style="min-height: 120px" /> |
| `audit-platform/frontend/src/components/dashboard/MyTodoCard.vue` | 14 | cleanup | TODO | s.length" class="my-todo-empty"> |
| `audit-platform/frontend/src/components/dashboard/MyTodoCard.vue` | 19 | cleanup | TODO | -list"> |
| `audit-platform/frontend/src/components/dashboard/MyTodoCard.vue` | 21 | cleanup | TODO | s" |
| `audit-platform/frontend/src/components/dashboard/MyTodoCard.vue` | 23 | cleanup | TODO | -item" |
| `audit-platform/frontend/src/components/dashboard/MyTodoCard.vue` | 26 | cleanup | TODO | -item-left"> |
| `audit-platform/frontend/src/components/dashboard/MyTodoCard.vue` | 34 | cleanup | TODO | -wp-code">{{ item.wp_code }}</span> |
| `audit-platform/frontend/src/components/dashboard/MyTodoCard.vue` | 35 | cleanup | TODO | -wp-name">{{ item.wp_name }}</span> |
| `audit-platform/frontend/src/components/dashboard/MyTodoCard.vue` | 37 | cleanup | TODO | -item-right"> |
| `audit-platform/frontend/src/components/dashboard/MyTodoCard.vue` | 38 | cleanup | TODO | -cycle">{{ item.cycle }}</span> |
| `audit-platform/frontend/src/components/dashboard/MyTodoCard.vue` | 39 | cleanup | TODO | -time">{{ formatTime(item.updated_at) }}</span> |
| `audit-platform/frontend/src/components/dashboard/MyTodoCard.vue` | 52 | cleanup | TODO | Item { |
| `audit-platform/frontend/src/components/dashboard/MyTodoCard.vue` | 62 | cleanup | TODO | Response { |
| `audit-platform/frontend/src/components/dashboard/MyTodoCard.vue` | 63 | cleanup | TODO | Item[] |
| `audit-platform/frontend/src/components/dashboard/MyTodoCard.vue` | 72 | cleanup | TODO | s = ref<TodoItem[]>([]) |
| `audit-platform/frontend/src/components/dashboard/MyTodoCard.vue` | 100 | cleanup | TODO | Item) { |
| `audit-platform/frontend/src/components/dashboard/MyTodoCard.vue` | 107 | cleanup | TODO | s() { |
| `audit-platform/frontend/src/components/dashboard/MyTodoCard.vue` | 110 | cleanup | TODO | Response>( |
| `audit-platform/frontend/src/components/dashboard/MyTodoCard.vue` | 111 | cleanup | TODO | ` |
| `audit-platform/frontend/src/components/dashboard/MyTodoCard.vue` | 113 | cleanup | TODO | s.value = data.items \|\| [] |
| `audit-platform/frontend/src/components/dashboard/MyTodoCard.vue` | 115 | cleanup | TODO | s.value = [] |
| `audit-platform/frontend/src/components/dashboard/MyTodoCard.vue` | 122 | cleanup | TODO | s() |
| `audit-platform/frontend/src/components/dashboard/MyTodoCard.vue` | 127 | cleanup | TODO | -card { |
| `audit-platform/frontend/src/components/dashboard/MyTodoCard.vue` | 134 | cleanup | TODO | -header { |
| `audit-platform/frontend/src/components/dashboard/MyTodoCard.vue` | 141 | cleanup | TODO | -title { |
| `audit-platform/frontend/src/components/dashboard/MyTodoCard.vue` | 147 | cleanup | TODO | -empty { |
| `audit-platform/frontend/src/components/dashboard/MyTodoCard.vue` | 154 | cleanup | TODO | -list { |
| `audit-platform/frontend/src/components/dashboard/MyTodoCard.vue` | 162 | cleanup | TODO | -item { |
| `audit-platform/frontend/src/components/dashboard/MyTodoCard.vue` | 173 | cleanup | TODO | -item:hover { |
| `audit-platform/frontend/src/components/dashboard/MyTodoCard.vue` | 178 | cleanup | TODO | -item-left { |
| `audit-platform/frontend/src/components/dashboard/MyTodoCard.vue` | 186 | cleanup | TODO | -wp-code { |
| `audit-platform/frontend/src/components/dashboard/MyTodoCard.vue` | 193 | cleanup | TODO | -wp-name { |
| `audit-platform/frontend/src/components/dashboard/MyTodoCard.vue` | 201 | cleanup | TODO | -item-right { |
| `audit-platform/frontend/src/components/dashboard/MyTodoCard.vue` | 209 | cleanup | TODO | -cycle { |
| `audit-platform/frontend/src/components/dashboard/MyTodoCard.vue` | 214 | cleanup | TODO | -time { |
| `audit-platform/frontend/src/components/extension/ExternalAPIConfig.vue` | 16 | bug | XXX | "}' /> |
| `audit-platform/frontend/src/components/formula/StructureEditor.vue` | 707 | cleanup | TODO | 调用 trace-forward 显示来源弹窗 |
| `audit-platform/frontend/src/components/ledger-import/LedgerBalanceTreeView.vue` | 6 | bug | XXX | )   ← 按 aux_type 分组聚合 |
| `audit-platform/frontend/src/components/ledger-import/UploadStep.vue` | 171 | cleanup | TODO | 真正分片需后端加 chunked upload 端点，>500MB 文件浏览器内存会承压 |
| `audit-platform/frontend/src/components/template-library/AuditReportTab.vue` | 371 | bug | XXX | } 格式） |
| `audit-platform/frontend/src/components/template-library/FormulaTab.vue` | 601 | bug | XXX | ') 在 row_codes 集合中不存在的（Property 15 + 需求 7.6） |
| `audit-platform/frontend/src/components/trial-balance/ReportLineMappingDialog.vue` | 383 | bug | XXX | /ISXXX,与新报表不兼容)。\n\n是否强制刷新为新格式 BS-XXX/IS-XXX?\n\n注:仅刷新 AI 建议的记录,手工调整的不动。`, |
| `audit-platform/frontend/src/components/workpaper/WorkpaperLifecycleView.vue` | 37 | cleanup | TODO | s.length"> |
| `audit-platform/frontend/src/components/workpaper/WorkpaperLifecycleView.vue` | 38 | cleanup | TODO | s.length }}</span> |
| `audit-platform/frontend/src/components/workpaper/WorkpaperLifecycleView.vue` | 205 | cleanup | TODO | s.length" class="gt-wp-lc-todo-panel"> |
| `audit-platform/frontend/src/components/workpaper/WorkpaperLifecycleView.vue` | 206 | cleanup | TODO | -panel__header"> |
| `audit-platform/frontend/src/components/workpaper/WorkpaperLifecycleView.vue` | 207 | cleanup | TODO | -panel__title">📋 我的待办</span> |
| `audit-platform/frontend/src/components/workpaper/WorkpaperLifecycleView.vue` | 208 | cleanup | TODO | s.length }}</el-tag> |
| `audit-platform/frontend/src/components/workpaper/WorkpaperLifecycleView.vue` | 210 | cleanup | TODO | -panel__list"> |
| `audit-platform/frontend/src/components/workpaper/WorkpaperLifecycleView.vue` | 211 | cleanup | TODO | in myTodos.slice(0, 8)" :key="todo.id" class="gt-wp-lc-todo-panel__item" |
| `audit-platform/frontend/src/components/workpaper/WorkpaperLifecycleView.vue` | 212 | cleanup | TODO | .id)"> |
| `audit-platform/frontend/src/components/workpaper/WorkpaperLifecycleView.vue` | 213 | cleanup | TODO | -panel__code">{{ todo.wp_code }}</span> |
| `audit-platform/frontend/src/components/workpaper/WorkpaperLifecycleView.vue` | 214 | cleanup | TODO | -panel__name">{{ todo.wp_name }}</span> |
| `audit-platform/frontend/src/components/workpaper/WorkpaperLifecycleView.vue` | 215 | cleanup | TODO | .status) }}</el-tag> |
| `audit-platform/frontend/src/components/workpaper/WorkpaperLifecycleView.vue` | 220 | cleanup | TODO | -empty-placeholder"> |
| `audit-platform/frontend/src/components/workpaper/WorkpaperLifecycleView.vue` | 221 | cleanup | TODO | -empty-placeholder__icon">✅</div> |
| `audit-platform/frontend/src/components/workpaper/WorkpaperLifecycleView.vue` | 222 | cleanup | TODO | -empty-placeholder__title">暂无待办任务</div> |
| `audit-platform/frontend/src/components/workpaper/WorkpaperLifecycleView.vue` | 223 | cleanup | TODO | -empty-placeholder__desc">当前阶段没有分配给您的底稿任务，可以查看其他阶段或协助团队成员</div> |
| `audit-platform/frontend/src/components/workpaper/WorkpaperLifecycleView.vue` | 592 | cleanup | TODO | s = computed(() => { |
| `audit-platform/frontend/src/components/workpaper/WorkpaperLifecycleView.vue` | 749 | cleanup | TODO | -panel { |
| `audit-platform/frontend/src/components/workpaper/WorkpaperLifecycleView.vue` | 754 | cleanup | TODO | -panel--empty { |
| `audit-platform/frontend/src/components/workpaper/WorkpaperLifecycleView.vue` | 758 | cleanup | TODO | -panel__empty-text { font-size: 13px; color: var(--gt-color-text-tertiary); } |
| `audit-platform/frontend/src/components/workpaper/WorkpaperLifecycleView.vue` | 759 | cleanup | TODO | -panel__header { |
| `audit-platform/frontend/src/components/workpaper/WorkpaperLifecycleView.vue` | 763 | cleanup | TODO | -panel__title { font-size: 14px; font-weight: 600; color: var(--gt-color-primary |
| `audit-platform/frontend/src/components/workpaper/WorkpaperLifecycleView.vue` | 764 | cleanup | TODO | -panel__list { display: flex; flex-direction: column; gap: 6px; } |
| `audit-platform/frontend/src/components/workpaper/WorkpaperLifecycleView.vue` | 765 | cleanup | TODO | -panel__item { |
| `audit-platform/frontend/src/components/workpaper/WorkpaperLifecycleView.vue` | 770 | cleanup | TODO | -panel__item:hover { background: #fff; border-color: var(--gt-color-primary); bo |
| `audit-platform/frontend/src/components/workpaper/WorkpaperLifecycleView.vue` | 771 | cleanup | TODO | -panel__code { font-size: 12px; font-weight: 700; color: var(--gt-color-primary) |
| `audit-platform/frontend/src/components/workpaper/WorkpaperLifecycleView.vue` | 772 | cleanup | TODO | -panel__name { flex: 1; font-size: 13px; color: var(--gt-color-text-primary); ov |
| `audit-platform/frontend/src/components/workpaper/WorkpaperLifecycleView.vue` | 775 | cleanup | TODO | -empty-placeholder { |
| `audit-platform/frontend/src/components/workpaper/WorkpaperLifecycleView.vue` | 781 | cleanup | TODO | -empty-placeholder__icon { font-size: 32px; margin-bottom: 10px; opacity: 0.6; } |
| `audit-platform/frontend/src/components/workpaper/WorkpaperLifecycleView.vue` | 782 | cleanup | TODO | -empty-placeholder__title { font-size: 14px; font-weight: 600; color: var(--gt-c |
| `audit-platform/frontend/src/components/workpaper/WorkpaperLifecycleView.vue` | 783 | cleanup | TODO | -empty-placeholder__desc { font-size: 12px; color: var(--gt-color-text-placehold |

### backend/services（65 条）

| 文件 | 行 | 类别 | Marker | 内容 |
|------|----|------|--------|------|
| `backend/app/services/account_chart_service.py` | 117 | bug | XXX | =权益类（实收资本/资本公积） |
| `backend/app/services/account_chart_service.py` | 119 | bug | XXX | 损益类（6001-6201=revenue, 6401+=expense） |
| `backend/app/services/account_chart_service.py` | 125 | bug | XXX | 损益类细分 |
| `backend/app/services/account_chart_service.py` | 126 | bug | XXX | _EXPENSE_START = "64" |
| `backend/app/services/account_chart_service.py` | 187 | bug | XXX | 损益类细分 |
| `backend/app/services/account_chart_service.py` | 193 | bug | XXX | 损益类细分 |
| `backend/app/services/account_chart_service.py` | 195 | bug | XXX | _EXPENSE_START: |
| `backend/app/services/account_chart_service.py` | 199 | bug | XXX | — 需要区分成本类（生产成本4001）和权益类（实收资本4001） |
| `backend/app/services/account_chart_service.py` | 200 | bug | XXX | 是成本类，但部分企业用 4xxx 表示权益类 |
| `backend/app/services/ai_plugin_service.py` | 92 | cleanup | TODO | 对接税务局发票查验 API |
| `backend/app/services/ai_plugin_service.py` | 106 | cleanup | TODO | 对接天眼查/企查查 API 或定期导入缓存 |
| `backend/app/services/ai_plugin_service.py` | 120 | feature | TODO | 实现银行流水自动匹配算法 |
| `backend/app/services/ai_plugin_service.py` | 134 | feature | TODO | 实现印章 OCR 识别与比对 |
| `backend/app/services/ai_plugin_service.py` | 148 | cleanup | TODO | 对接 Whisper 或其他 ASR 服务 |
| `backend/app/services/ai_plugin_service.py` | 162 | feature | TODO | 实现 LLM 驱动的底稿质量复核 |
| `backend/app/services/ai_plugin_service.py` | 176 | feature | TODO | 实现 ERP 数据实时监控 |
| `backend/app/services/ai_plugin_service.py` | 190 | feature | TODO | 实现多人 AI 协同对话空间 |
| `backend/app/services/confirmation_service.py` | 50 | feature | TODO | O1 spec 实现真实业务逻辑（更新 DB、计算差异、生成差异调节表等） |
| `backend/app/services/consol_disclosure_service.py` | 238 | cleanup | TODO | 从公司详情取 |
| `backend/app/services/consol_disclosure_service.py` | 344 | cleanup | TODO | 从变动记录取 |
| `backend/app/services/consol_disclosure_service.py` | 345 | cleanup | TODO | 从变动记录取 |
| `backend/app/services/dashboard_aggregator_service.py` | 254 | bug | XXX | " → "D") |
| `backend/app/services/drilldown_service.py` | 36 | cleanup | TODO | F41: 渐进迁移——未来 __init__ 应接收 current_user_id 参数， |
| `backend/app/services/ledger_import/aux_dimension.py` | 97 | bug | XXX | " 开头（即另一个类型）才切 |
| `backend/app/services/ledger_import/aux_dimension.py` | 121 | bug | XXX | '"的位置作为分隔点 |
| `backend/app/services/ledger_penetration_service.py` | 93 | cleanup | TODO | F41: 渐进迁移——未来 __init__ 应接收 current_user_id 参数， |
| `backend/app/services/manager_dashboard_service.py` | 58 | cleanup | TODO | s: {...},       # 跨项目待办汇总 |
| `backend/app/services/manager_dashboard_service.py` | 66 | cleanup | TODO | s": _empty_cross_todos(), "team_load": []} |
| `backend/app/services/manager_dashboard_service.py` | 76 | cleanup | TODO | s, team_load = await asyncio.gather( |
| `backend/app/services/manager_dashboard_service.py` | 78 | cleanup | TODO | s(project_ids, user.id), |
| `backend/app/services/manager_dashboard_service.py` | 84 | cleanup | TODO | s": cross_todos, |
| `backend/app/services/manager_dashboard_service.py` | 461 | cleanup | TODO | s( |
| `backend/app/services/manager_dashboard_service.py` | 643 | cleanup | TODO | s() -> dict: |
| `backend/app/services/mapping_service.py` | 194 | bug | XXX | =资产/2xxx=负债/3xxx=权益/5xxx=收入/6xxx=费用）。 |
| `backend/app/services/my_todo_service.py` | 6 | cleanup | TODO | Item 列表。 |
| `backend/app/services/my_todo_service.py` | 48 | cleanup | TODO | Item(BaseModel): |
| `backend/app/services/my_todo_service.py` | 58 | cleanup | TODO | Response(BaseModel): |
| `backend/app/services/my_todo_service.py` | 59 | cleanup | TODO | Item] |
| `backend/app/services/my_todo_service.py` | 68 | cleanup | TODO | ( |
| `backend/app/services/my_todo_service.py` | 72 | cleanup | TODO | Response: |
| `backend/app/services/my_todo_service.py` | 99 | cleanup | TODO | Response(items=[], total=0) |
| `backend/app/services/my_todo_service.py` | 135 | cleanup | TODO | Item 列表 |
| `backend/app/services/my_todo_service.py` | 136 | cleanup | TODO | Item] = [] |
| `backend/app/services/my_todo_service.py` | 157 | cleanup | TODO | Item( |
| `backend/app/services/my_todo_service.py` | 171 | cleanup | TODO | Response(items=items, total=len(items)) |
| `backend/app/services/note_md_template_parser.py` | 67 | bug | XXX | } or {{xxx}} |
| `backend/app/services/note_offline_export_service.py` | 195 | bug | XXX | ] 标记下方插入数据", FONT_NORMAL), |
| `backend/app/services/note_source_resolvers.py` | 9 | bug | XXX | (binding, ctx) -> Any``： |
| `backend/app/services/notification_types.py` | 39 | bug | XXX | } 由 metadata 字段填充 |
| `backend/app/services/ocr_service_v2.py` | 456 | bug | XXX | \",\"field_value\":\"xxx\",\"confidence\":0.9}]" |
| `backend/app/services/pdf_export_engine.py` | 278 | cleanup | TODO | 15.3 — xlsx→PDF 转换 |
| `backend/app/services/pdf_export_engine.py` | 279 | cleanup | TODO | 15.4 — PDF 合并与后处理 |
| `backend/app/services/pdf_export_engine.py` | 280 | cleanup | TODO | 15.5 — PDF 密码保护 |
| `backend/app/services/report_line_mapping_service.py` | 166 | bug | XXX | /2xxx/3xxx: 资产/负债/权益 → 资产负债表 |
| `backend/app/services/report_line_mapping_service.py` | 167 | bug | XXX | /5xxx/6xxx: 成本/损益 → 4xxx 在新版准则归成本类(进利润表), 但 30/40 系列偶有权益用法 |
| `backend/app/services/report_line_mapping_service.py` | 199 | bug | XXX | 格式. manual / reference_copied 永远不动. |
| `backend/app/services/report_line_mapping_service.py` | 294 | bug | XXX | →BS-XXX) |
| `backend/app/services/report_placeholder_service.py` | 100 | bug | XXX | } 占位符""" |
| `backend/app/services/rotation_check_service.py` | 102 | cleanup | TODO | read from system_settings.rotation_policy when admin UI is built |
| `backend/app/services/rotation_check_service.py` | 135 | cleanup | TODO | read from system_settings.rotation_policy when admin UI is built |
| `backend/app/services/trial_balance_service.py` | 189 | bug | XXX | /6xxx）：取单边发生额（不做借-贷，因为结转后两边相等） |
| `backend/app/services/trial_balance_service.py` | 595 | bug | XXX | 负债/3xxx权益/4xxx权益/收入类）取反为正数 |
| `backend/app/services/word_template_filler.py` | 75 | bug | XXX | } placeholders in all paragraphs of a document.""" |
| `backend/app/services/word_template_filler.py` | 196 | bug | XXX | } replacement |
| `backend/app/services/wp_xlsx_export_service.py` | 95 | bug | XXX | }: 从 project_meta[xxx] 取值 |

### frontend/views（56 条）

| 文件 | 行 | 类别 | Marker | 内容 |
|------|----|------|--------|------|
| `audit-platform/frontend/src/views/AttachmentHub.vue` | 39 | feature | TODO | replace window.open with AttachmentPreviewDrawer when per-file preview is added  |
| `audit-platform/frontend/src/views/AttachmentManagement.vue` | 191 | cleanup | TODO | replace AttachmentPreview dialog with AttachmentPreviewDrawer for unified drawer |
| `audit-platform/frontend/src/views/LedgerPenetration.vue` | 1879 | feature | TODO | 抽凭联动到底稿（后续实现） |
| `audit-platform/frontend/src/views/ManagerDashboard.vue` | 7 | cleanup | TODO | Total }} 项待办 |
| `audit-platform/frontend/src/views/ManagerDashboard.vue` | 129 | cleanup | TODO | Tab" class="gt-cross-todo-tabs"> |
| `audit-platform/frontend/src/views/ManagerDashboard.vue` | 133 | cleanup | TODO | -card" @click="goToReviewInbox()"> |
| `audit-platform/frontend/src/views/ManagerDashboard.vue` | 134 | cleanup | TODO | -icon">📋</div> |
| `audit-platform/frontend/src/views/ManagerDashboard.vue` | 135 | cleanup | TODO | -info"> |
| `audit-platform/frontend/src/views/ManagerDashboard.vue` | 136 | cleanup | TODO | -count">{{ overview.cross_todos.pending_review }}</span> |
| `audit-platform/frontend/src/views/ManagerDashboard.vue` | 137 | cleanup | TODO | -label">待复核</span> |
| `audit-platform/frontend/src/views/ManagerDashboard.vue` | 142 | cleanup | TODO | -card" v-permission="'assignment:batch'" @click="goToUnassigned()"> |
| `audit-platform/frontend/src/views/ManagerDashboard.vue` | 143 | cleanup | TODO | -icon">📝</div> |
| `audit-platform/frontend/src/views/ManagerDashboard.vue` | 144 | cleanup | TODO | -info"> |
| `audit-platform/frontend/src/views/ManagerDashboard.vue` | 145 | cleanup | TODO | -count">{{ overview.cross_todos.pending_assign }}</span> |
| `audit-platform/frontend/src/views/ManagerDashboard.vue` | 146 | cleanup | TODO | -label">待分配</span> |
| `audit-platform/frontend/src/views/ManagerDashboard.vue` | 151 | cleanup | TODO | -card" @click="goToWorkHoursApprove()"> |
| `audit-platform/frontend/src/views/ManagerDashboard.vue` | 152 | cleanup | TODO | -icon">⏱️</div> |
| `audit-platform/frontend/src/views/ManagerDashboard.vue` | 153 | cleanup | TODO | -info"> |
| `audit-platform/frontend/src/views/ManagerDashboard.vue` | 154 | cleanup | TODO | -count">{{ overview.cross_todos.pending_approve }}</span> |
| `audit-platform/frontend/src/views/ManagerDashboard.vue` | 155 | cleanup | TODO | -label">待审批工时</span> |
| `audit-platform/frontend/src/views/ManagerDashboard.vue` | 481 | cleanup | TODO | s { |
| `audit-platform/frontend/src/views/ManagerDashboard.vue` | 510 | cleanup | TODO | s: CrossTodos |
| `audit-platform/frontend/src/views/ManagerDashboard.vue` | 545 | cleanup | TODO | Tab = ref('overview') |
| `audit-platform/frontend/src/views/ManagerDashboard.vue` | 593 | cleanup | TODO | Total = computed(() => { |
| `audit-platform/frontend/src/views/ManagerDashboard.vue` | 595 | cleanup | TODO | s |
| `audit-platform/frontend/src/views/ManagerDashboard.vue` | 608 | cleanup | TODO | s = overview.value.cross_todos |
| `audit-platform/frontend/src/views/ManagerDashboard.vue` | 609 | cleanup | TODO | s.pending_review > 0) { |
| `audit-platform/frontend/src/views/ManagerDashboard.vue` | 610 | cleanup | TODO | s.pending_review} 张底稿待复核`, priority: 'high' }) |
| `audit-platform/frontend/src/views/ManagerDashboard.vue` | 612 | cleanup | TODO | s.pending_assign > 0) { |
| `audit-platform/frontend/src/views/ManagerDashboard.vue` | 613 | cleanup | TODO | s.pending_assign} 张底稿待分配`, priority: 'high' }) |
| `audit-platform/frontend/src/views/ManagerDashboard.vue` | 615 | cleanup | TODO | s.pending_approve > 0) { |
| `audit-platform/frontend/src/views/ManagerDashboard.vue` | 616 | cleanup | TODO | s.pending_approve} 条工时待审批`, priority: 'medium' }) |
| `audit-platform/frontend/src/views/ManagerDashboard.vue` | 1012 | cleanup | TODO | Tab, (val) => { |
| `audit-platform/frontend/src/views/ManagerDashboard.vue` | 1020 | cleanup | TODO | Tab.value === 'commitments') { |
| `audit-platform/frontend/src/views/ManagerDashboard.vue` | 1210 | cleanup | TODO | -card { |
| `audit-platform/frontend/src/views/ManagerDashboard.vue` | 1221 | cleanup | TODO | -card:hover { |
| `audit-platform/frontend/src/views/ManagerDashboard.vue` | 1225 | cleanup | TODO | -icon { |
| `audit-platform/frontend/src/views/ManagerDashboard.vue` | 1228 | cleanup | TODO | -info { |
| `audit-platform/frontend/src/views/ManagerDashboard.vue` | 1232 | cleanup | TODO | -count { |
| `audit-platform/frontend/src/views/ManagerDashboard.vue` | 1237 | cleanup | TODO | -label { |
| `audit-platform/frontend/src/views/ManagerDashboard.vue` | 1354 | cleanup | TODO | -tabs { |
| `audit-platform/frontend/src/views/ManagerDashboard.vue` | 1357 | cleanup | TODO | -tabs :deep(.el-tabs__header) { |
| `audit-platform/frontend/src/views/PartnerProjectDashboard.vue` | 63 | cleanup | TODO | CycleProgressRing.vue 组件（Task 3.3） --> |
| `audit-platform/frontend/src/views/PartnerProjectDashboard.vue` | 73 | cleanup | TODO | VRSummaryCard.vue 组件（Task 3.4） --> |
| `audit-platform/frontend/src/views/PartnerProjectDashboard.vue` | 87 | cleanup | TODO | ReviewOpinionList.vue 组件（Task 3.5） --> |
| `audit-platform/frontend/src/views/PartnerProjectDashboard.vue` | 109 | cleanup | TODO | ProjectTimeline.vue 组件（Task 3.7） --> |
| `audit-platform/frontend/src/views/PersonalDashboard.vue` | 25 | cleanup | TODO | s" :key="t.id" class="gt-p-todo-item"> |
| `audit-platform/frontend/src/views/PersonalDashboard.vue` | 29 | cleanup | TODO | s.length" :image-size="50" description="暂无待办" /> |
| `audit-platform/frontend/src/views/PersonalDashboard.vue` | 50 | cleanup | TODO | s, getMyStaffId } from '@/services/commonApi' |
| `audit-platform/frontend/src/views/PersonalDashboard.vue` | 53 | cleanup | TODO | s = ref<any[]>([]) |
| `audit-platform/frontend/src/views/PersonalDashboard.vue` | 69 | cleanup | TODO | sRes = await getMyTodos() |
| `audit-platform/frontend/src/views/PersonalDashboard.vue` | 70 | cleanup | TODO | s.value = Array.isArray(todosRes) ? todosRes : ((todosRes as any)?.items ?? []) |
| `audit-platform/frontend/src/views/PersonalDashboard.vue` | 72 | cleanup | TODO | s.value = [] |
| `audit-platform/frontend/src/views/PersonalDashboard.vue` | 100 | feature | TODO | -item { display: flex; justify-content: space-between; align-items: center; padd |
| `audit-platform/frontend/src/views/TrialBalance.vue` | 202 | bug | XXX | =资产、2xxx=负债...） |
| `audit-platform/frontend/src/views/WorkpaperEditor.vue` | 1478 | cleanup | TODO | 完整 Univer 右键菜单集成需要 @univerjs/ui 的 IMenuService |

### frontend/其他（51 条）

| 文件 | 行 | 类别 | Marker | 内容 |
|------|----|------|--------|------|
| `audit-platform/frontend/src/__tests__/ManagerDashboard.spec.ts` | 26 | cleanup | TODO | s: { pending_review: 0, pending_assign: 0, pending_approve: 0 }, |
| `audit-platform/frontend/src/__tests__/MyTodoCard.spec.ts` | 2 | cleanup | TODO | Card 前端测试 |
| `audit-platform/frontend/src/__tests__/MyTodoCard.spec.ts` | 21 | docs | TODO | Card from '@/components/dashboard/MyTodoCard.vue' |
| `audit-platform/frontend/src/__tests__/MyTodoCard.spec.ts` | 24 | cleanup | TODO | s = [ |
| `audit-platform/frontend/src/__tests__/MyTodoCard.spec.ts` | 30 | cleanup | TODO | Card', () => { |
| `audit-platform/frontend/src/__tests__/MyTodoCard.spec.ts` | 35 | cleanup | TODO | list after loading', async () => { |
| `audit-platform/frontend/src/__tests__/MyTodoCard.spec.ts` | 36 | cleanup | TODO | s, total: 3 }) |
| `audit-platform/frontend/src/__tests__/MyTodoCard.spec.ts` | 37 | cleanup | TODO | Card, { |
| `audit-platform/frontend/src/__tests__/MyTodoCard.spec.ts` | 48 | cleanup | TODO | s, total: 3 }) |
| `audit-platform/frontend/src/__tests__/MyTodoCard.spec.ts` | 49 | cleanup | TODO | Card, { |
| `audit-platform/frontend/src/__tests__/MyTodoCard.spec.ts` | 63 | cleanup | TODO | s', async () => { |
| `audit-platform/frontend/src/__tests__/MyTodoCard.spec.ts` | 65 | cleanup | TODO | Card, { |
| `audit-platform/frontend/src/__tests__/MyTodoCard.spec.ts` | 74 | cleanup | TODO | s, total: 3 }) |
| `audit-platform/frontend/src/__tests__/MyTodoCard.spec.ts` | 75 | cleanup | TODO | Card, { |
| `audit-platform/frontend/src/__tests__/MyTodoCard.spec.ts` | 80 | cleanup | TODO | -item') |
| `audit-platform/frontend/src/__tests__/useWpDetailGuard.spec.ts` | 45 | bug | XXX | /D2.xlsx', |
| `audit-platform/frontend/src/stories/business/CycleProgressRing.stories.ts` | 8 | cleanup | TODO | cs'], |
| `audit-platform/frontend/src/stories/business/ForceGraph.stories.ts` | 8 | cleanup | TODO | cs'], |
| `audit-platform/frontend/src/stories/business/ProcedureTrimmingPanel.stories.ts` | 7 | cleanup | TODO | cs'], |
| `audit-platform/frontend/src/stories/business/ReviewLayerBadges.stories.ts` | 7 | cleanup | TODO | cs'], |
| `audit-platform/frontend/src/stories/business/VRSummaryCard.stories.ts` | 8 | cleanup | TODO | cs'], |
| `audit-platform/frontend/src/stories/common/BatchActionBar.stories.ts` | 7 | cleanup | TODO | cs'], |
| `audit-platform/frontend/src/stories/common/CellContextMenu.stories.ts` | 7 | cleanup | TODO | cs'], |
| `audit-platform/frontend/src/stories/common/CommentThread.stories.ts` | 7 | cleanup | TODO | cs'], |
| `audit-platform/frontend/src/stories/common/CommentTooltip.stories.ts` | 7 | cleanup | TODO | cs'], |
| `audit-platform/frontend/src/stories/common/ConflictDialog.stories.ts` | 7 | cleanup | TODO | cs'], |
| `audit-platform/frontend/src/stories/common/DrilldownBreadcrumb.stories.ts` | 7 | cleanup | TODO | cs'], |
| `audit-platform/frontend/src/stories/common/ExcelImportPreviewDialog.stories.ts` | 7 | cleanup | TODO | cs'], |
| `audit-platform/frontend/src/stories/common/GlobalSearchDialog.stories.ts` | 7 | cleanup | TODO | cs'], |
| `audit-platform/frontend/src/stories/common/GtAmountCell.stories.ts` | 7 | cleanup | TODO | cs'], |
| `audit-platform/frontend/src/stories/common/GtConsolWizard.stories.ts` | 7 | cleanup | TODO | cs'], |
| `audit-platform/frontend/src/stories/common/GtEditableTable.stories.ts` | 7 | cleanup | TODO | cs'], |
| `audit-platform/frontend/src/stories/common/GtInfoBar.stories.ts` | 7 | cleanup | TODO | cs'], |
| `audit-platform/frontend/src/stories/common/GtPageHeader.stories.ts` | 7 | cleanup | TODO | cs'], |
| `audit-platform/frontend/src/stories/common/GtPrintPreview.stories.ts` | 7 | cleanup | TODO | cs'], |
| `audit-platform/frontend/src/stories/common/GtStatusTag.stories.ts` | 7 | cleanup | TODO | cs'], |
| `audit-platform/frontend/src/stories/common/GtToolbar.stories.ts` | 7 | cleanup | TODO | cs'], |
| `audit-platform/frontend/src/stories/common/KnowledgePickerDialog.stories.ts` | 7 | cleanup | TODO | cs'], |
| `audit-platform/frontend/src/stories/common/LoadingState.stories.ts` | 7 | cleanup | TODO | cs'], |
| `audit-platform/frontend/src/stories/common/OperationFeedback.stories.ts` | 7 | cleanup | TODO | cs'], |
| `audit-platform/frontend/src/stories/common/PrefillDiffPanel.stories.ts` | 7 | cleanup | TODO | cs'], |
| `audit-platform/frontend/src/stories/common/SelectionBar.stories.ts` | 7 | cleanup | TODO | cs'], |
| `audit-platform/frontend/src/stories/common/SharedTemplatePicker.stories.ts` | 7 | cleanup | TODO | cs'], |
| `audit-platform/frontend/src/stories/common/SignGateChecklist.stories.ts` | 7 | cleanup | TODO | cs'], |
| `audit-platform/frontend/src/stories/common/SyncStatusIndicator.stories.ts` | 7 | cleanup | TODO | cs'], |
| `audit-platform/frontend/src/stories/common/TableSearchBar.stories.ts` | 7 | cleanup | TODO | cs'], |
| `audit-platform/frontend/src/stories/common/VRHeatmap.stories.ts` | 7 | cleanup | TODO | cs'], |
| `audit-platform/frontend/src/stories/common/ValidationList.stories.ts` | 7 | cleanup | TODO | cs'], |
| `audit-platform/frontend/src/stories/common/VirtualScrollTable.stories.ts` | 7 | cleanup | TODO | cs'], |
| `audit-platform/frontend/src/utils/confirm.ts` | 34 | bug | XXX | 」" |
| `audit-platform/frontend/src/utils/sse.ts` | 8 | bug | XXX | ') |

### backend/routers（15 条）

| 文件 | 行 | 类别 | Marker | 内容 |
|------|----|------|--------|------|
| `backend/app/routers/adjustments.py` | 853 | bug | XXX |  |
| `backend/app/routers/batch_export_progress.py` | 11 | feature | TODO | ，本任务不实现清理 worker） |
| `backend/app/routers/ledger_penetration.py` | 995 | bug | XXX | /6xxx）期初期末天然为0，只检查有期初或期末的科目 |
| `backend/app/routers/my_todo.py` | 5 | cleanup | TODO |  |
| `backend/app/routers/my_todo.py` | 21 | cleanup | TODO | _service import MyTodoResponse, get_my_todo |
| `backend/app/routers/my_todo.py` | 26 | cleanup | TODO | ", |
| `backend/app/routers/my_todo.py` | 27 | cleanup | TODO | "], |
| `backend/app/routers/my_todo.py` | 31 | cleanup | TODO | Response) |
| `backend/app/routers/my_todo.py` | 32 | cleanup | TODO | _list( |
| `backend/app/routers/my_todo.py` | 36 | cleanup | TODO | Response: |
| `backend/app/routers/my_todo.py` | 44 | cleanup | TODO | ( |
| `backend/app/routers/my_todo.py` | 52 | cleanup | TODO | requested: project_id=%s user_id=%s items=%d elapsed=%.1fms", |
| `backend/app/routers/qc_rotation_due.py` | 52 | cleanup | TODO | join qc_inspections 取最近抽查时间 |
| `backend/app/routers/report_line_mapping.py` | 33 | bug | XXX | →BS-XXX 格式"), |
| `backend/app/routers/wp_procedures.py` | 104 | cleanup | TODO | 从 auth context 获取 user_id |

### frontend/composables（6 条）

| 文件 | 行 | 类别 | Marker | 内容 |
|------|----|------|--------|------|
| `audit-platform/frontend/src/composables/useAutoSave.ts` | 52 | bug | XXX | ` 的边界情况。 |
| `audit-platform/frontend/src/composables/useNavigationStack.ts` | 12 | bug | XXX | /trial-balance', query: { tab: 'detail' } }) |
| `audit-platform/frontend/src/composables/useNavigationStack.ts` | 13 | bug | XXX | /workpapers') |
| `audit-platform/frontend/src/composables/useNavigationStack.ts` | 14 | bug | XXX | /trial-balance?tab=detail |
| `audit-platform/frontend/src/composables/useNoteStale.ts` | 17 | cleanup | TODO | + console.info 提示后续 Sprint 接入。 |
| `audit-platform/frontend/src/composables/useNoteStale.ts` | 89 | feature | TODO | (Sprint 4+): 后端端点 POST /api/disclosure-notes/{id}/dismiss-stale 尚未实现。 |

### backend/core（3 条）

| 文件 | 行 | 类别 | Marker | 内容 |
|------|----|------|--------|------|
| `backend/app/core/container.py` | 9 | bug | XXX | ") |
| `backend/app/core/migration_runner.py` | 44 | bug | XXX | .sql 格式 |
| `backend/app/core/migration_runner.py` | 47 | bug | XXX | .sql 格式（回滚脚本） |

### frontend/services（3 条）

| 文件 | 行 | 类别 | Marker | 内容 |
|------|----|------|--------|------|
| `audit-platform/frontend/src/services/apiPaths/collaboration.ts` | 14 | cleanup | TODO | s: '/api/staff/me/todos', |
| `audit-platform/frontend/src/services/commonApi.ts` | 55 | cleanup | TODO | s(): Promise<any[]> { |
| `audit-platform/frontend/src/services/commonApi.ts` | 56 | cleanup | TODO | s, { validateStatus: () => true }) |

### backend/其他（2 条）

| 文件 | 行 | 类别 | Marker | 内容 |
|------|----|------|--------|------|
| `backend/app/router_registry/collaboration.py` | 221 | cleanup | TODO | import router as my_todo_router |
| `backend/app/router_registry/collaboration.py` | 222 | cleanup | TODO | _router, tags=["my-todo"]) |

### backend/models（1 条）

| 文件 | 行 | 类别 | Marker | 内容 |
|------|----|------|--------|------|
| `backend/app/models/archive_models.py` | 77 | feature | TODO | (Round2-Task-E): Add GIN index on section_progress for operational queries |
