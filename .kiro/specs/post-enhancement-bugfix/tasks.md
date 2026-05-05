# 任务清单：审计平台缺陷修复与业务优化

## Sprint 1：业务逻辑缺陷修复（~3天）

### Task 1.1 — 试算平衡表 AJE/RJE 自动汇总 [B1]
- [x] 后端新增 `GET /api/projects/{pid}/trial-balance/summary-with-adjustments` 接口
- [x] 接口按报表行次汇总 AJE/RJE，从 adjustments 表自动计算
- [x] 前端 `loadTbSummary()` 改为调用新接口
- [x] 移除试算平衡表 AJE/RJE 列的手动 `el-input-number` 编辑
- [x] 验证构建

### Task 1.2 — 底稿上传后自动触发解析 [B2]
- [x] `WorkpaperList.vue` `doUpload()` 成功后自动调用 `parseWorkpaper` 接口
- [x] 解析期间显示 loading 状态
- [x] 解析完成后刷新底稿状态和试算表数据
- [x] 验证五环联动：上传→解析→试算表更新→报表更新

### Task 1.3 — 借贷平衡指示器修正 [B3]
- [x] 修改 `isBalanced` computed：改为资产类合计 = 负债+权益类合计
- [x] 允许 1 元误差（浮点精度）
- [x] 在指示器 tooltip 里显示具体差额
- [ ] 验证构建

### Task 1.4 — 复核通过时检查未解决批注 [B4/B9]
- [x] `onReviewPass()` 前检查 `unresolvedCount`
- [x] 有未解决批注时弹出强制确认框（"强制通过" vs "返回处理"，默认取消）
- [x] 确认框使用 danger 样式的确认按钮，明确提示风险
- [ ] 验证构建

### Task 1.5 — 看板视图核心交互实现 [B5]
- [x] `onKanbanSelect`：切换到列表视图并自动选中对应底稿
- [x] `onKanbanAssign`：弹出分配弹窗（编制人/复核人）
- [x] 分配成功后刷新看板数据
- [ ] 验证构建

### Task 1.6 — 批量复核跳过提示 [B6]
- [x] `batchReview()` 统计跳过的分录数量
- [x] 有跳过时显示 warning 提示（"已跳过 N 条非待复核状态的分录"）
- [ ] 验证构建

### Task 1.7 — 调整分录科目显示报表行次 [B7]
- [x] 后端 `get_account_dropdown` 接口返回 `report_line` 字段
- [x] 前端科目下拉选项右侧显示报表行次（灰色小字）
- [ ] 验证构建

### Task 1.8 — 科目编码链接直接打开底稿编辑器 [B8]
- [x] `TrialBalance.vue` `onOpenWorkpaper()` 改为直接跳转到 WorkpaperEditor
- [x] 底稿已生成时直接打开编辑器，未生成时跳到列表页并高亮
- [ ] 验证构建

### Task 1.9 — CommentThread 批注与复核流程强制联动 [B9]
- [x] `WorkpaperList.vue` `onReviewPass()` 检查 `unresolvedCount`
- [x] 有未解决批注时弹出强制确认框（"强制通过" vs "返回处理"）
- [x] 验证复核通过流程

### Task 1.10 — Sprint 1 收尾
- [-] vue-tsc 零错误 + Vite 构建通过
- [x] git commit + push

---

## Sprint 2：P0/P1 技术 Bug 修复（~3天）

### Task 2.1 — escapeRegex 修复 [P0.1]
- [ ] `utils/useTableSearch.ts` 中 `escapeRegex` 替换字符串改为正确写法：`str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')`
- [x] 验证含特殊字符（`.`、`*`、`(`、`)`）的搜索替换正常工作

### Task 2.2 — migration_runner 多语句分割 [P0.2]
- [x] `_apply_migration` 按分号分割 SQL 语句
- [x] 过滤空语句和纯注释语句
- [ ] 处理 `DO $$ ... END $$;` 块（不按分号分割，整体执行）
- [x] 更新 `test_migration_runner.py` 测试用例
- [x] 验证 V003 迁移文件正常执行

### Task 2.3 — bulk_execute savepoint 隔离 [P0.3]
- [x] `bulk_execute` 每个操作用 `db.begin_nested()` 包裹
- [x] 失败时 `await sp.rollback()`，不影响其他操作
- [x] 更新相关测试

### Task 2.4 — ReportFormulaParser 返回值修复 [P0.4]
- [x] `execute()` 失败时明确 `return Decimal("0")`
- [x] 验证报表生成不再出现 TypeError

### Task 2.5 — v-permission 内存泄漏修复 [P1.1]
- [x] `directives/permission.ts` 改为直接访问 authStore.user?.role
- [x] 不在指令里调用 `usePermission()`
- [x] 验证权限隐藏/显示功能正常

### Task 2.6 — router beforeEach 权限检查修复 [P1.2]
- [x] `router/index.ts` beforeEach 里直接访问 `authStore.user?.role`
- [x] 导入 `ROLE_PERMISSIONS` 常量用于权限判断
- [x] 验证路由权限守卫正常

### Task 2.7 — main.ts 图标注册修复 [P1.3]
- [x] 删除 `main.ts` 里的全量图标注册循环
- [x] 验证 Vite 构建通过，bundle 大小减小
- [x] 验证页面图标正常显示（由 unplugin 自动处理）

### Task 2.8 — 调整分录编号并发修复 [P1.4]
- [x] `_next_adjustment_no` 使用 `pg_advisory_xact_lock` 防并发
- [x] 验证并发创建分录时编号不重复

### Task 2.9 — http.ts pendingMap 泄漏修复 [P1.5]
- [x] `addPending` 里对 POST/PUT/PATCH 请求设置 5 分钟自动清理定时器
- [x] 或在 `removePending` 里确保超时/取消的请求也被清理
- [x] 验证重复 POST 请求不会永久被拒

### Task 2.10 — EventBus 僵尸队列清理 [P1.6]
- [x] `_notify_sse` 里 `QueueFull` 时调用 `self.remove_sse_queue(queue)`
- [x] 验证 SSE 连接断开后队列被正确清理

### Task 2.11 — shortcuts.ts 输入框检查 [P1.7]
- [x] `handleKeydown` 开头加 `isInputFocused` 检查
- [x] 在 input/textarea/contenteditable 里忽略快捷键（Escape 除外）
- [x] 验证在搜索框里按 Ctrl+S 不触发保存

### Task 2.12 — useProjectStore/dictStore 改用 apiProxy [P1.8/P1.9]
- [x] `useProjectStore.loadProjectOptions` 改用 `api.get` 或 `listProjects`
- [x] `dictStore.load` 改用 `api.get`，删除 `resp.data?.data ?? resp.data` 兼容代码
- [ ] 验证构建

### Task 2.13 — useAutoSave 改用 sessionStorage [P1.10]
- [x] `useAutoSave.ts` 所有 `localStorage` 改为 `sessionStorage`
- [x] 验证关闭标签页后草稿自动清除

### Task 2.14 — useEditMode guardRoute 选项 [P1.11]
- [x] `useEditMode` 加 `guardRoute?: boolean` 选项（默认 true）
- [x] `ConsolNoteTab` 等子组件调用时传 `{ guardRoute: false }`
- [x] 验证控制台不再出现路由守卫警告

### Task 2.15 — displayPrefs.amountClass 修复 [P1.12]
- [x] `prior === 0` 且本期不为 0 时直接高亮
- [x] 验证新增科目（上期为0）的变动高亮正常

### Task 2.16 — Sprint 2 收尾
- [ ] vue-tsc 零错误 + Vite 构建通过
- [~] Python 语法检查通过
- [ ] git commit + push

---

## Sprint 3：P2 优化项（~4天）

### Task 3.1 — 数据同步状态可视化 [P2.1]
- [x] `GtPageHeader` 加 `showSyncStatus` prop 和同步状态指示器
- [ ] 通过 `eventBus.on('sse:sync-event')` 更新为"同步中"
- [ ] 通过 `eventBus.on('sse:sync-failed')` 更新为"数据可能过时"
- [ ] 同步完成后显示"最后更新：X分钟前"
- [ ] 接入 TrialBalance、ReportView、DisclosureEditor

### Task 3.2 — 试算表双向导航 [P2.2]
- [ ] 试算表右键菜单加"查看相关分录"选项
- [ ] 跳转到调整分录页面并按科目过滤
- [ ] 调整分录页面接收 `account` query 参数自动过滤
- [ ] 验证构建

### Task 3.3 — 底稿识别确认步骤 [P2.3]
- [ ] 上传弹窗改为两步：上传文件 → 确认识别数据
- [ ] 步骤2 显示系统识别出的关键数字（审定数、未审数）
- [ ] 用户确认后才写入 parsed_data
- [ ] 验证构建

### Task 3.4 — list_entries N+1 优化 [P2.4]
- [x] 先获取所有 entry_group_id
- [ ] 一次性批量查询所有 Adjustment 和 AdjustmentEntry
- [ ] 内存里按 entry_group_id 分组
- [ ] 验证查询次数从 100 次降到 3 次

### Task 3.5 — disclosure_engine 预加载优化 [P2.5]
- [ ] `_preload_data_for_notes` 里一次性加载上年所有附注到 `_prior_notes_cache`
- [ ] `generate_notes` 循环里从缓存取，不再逐章节查询
- [ ] 验证生成 165 个附注的查询次数减少

### Task 3.6 — _build_table_data 合计为 0 修复 [P2.6]
- [ ] 移除 `row["values"][ci] = total if total != 0 else None` 的条件
- [ ] 改为 `row["values"][ci] = total`
- [ ] 验证合计为 0 的行正确显示 0

### Task 3.7 — syncFromRoute 非阻塞 [P2.7]
- [ ] 移除 `router/index.ts` beforeEach 里的 `await projectStore.syncFromRoute(to)`
- [ ] 改为 `projectStore.syncFromRoute(to)` 不等待（后台更新）
- [ ] 验证路由切换速度提升，数据仍然正确加载

### Task 3.8 — router_registry.py 重复调用清理 [P2.8]
- [ ] 删除 `router_registry.py` 末尾的 `register_phase14_rules()` 调用
- [ ] 保留 `main.py` lifespan 里的调用
- [ ] 验证门禁规则正常注册

### Task 3.9 — GtPageHeader backMode prop [P2.9]
- [ ] 加 `backMode: 'route' | 'history'` prop（默认 'route'）
- [ ] `history` 模式调用 `router.back()`
- [ ] 更新 TrialBalance/ReportView/DisclosureEditor 等使用 GtPageHeader 的页面

### Task 3.10 — useDictStore 缓存 TTL [P2.10]
- [ ] sessionStorage 缓存加 24 小时过期时间戳
- [ ] 过期时强制重新加载
- [ ] 验证字典更新后前端能感知

### Task 3.11 — statusMaps.ts 和 dictStore 统一 [P2.11]
- [ ] `GtStatusTag` 优先使用 dictStore 数据，dictStore 未加载时回退到 statusMaps.ts
- [ ] 确保两套数据的 key/label/type 一致
- [ ] 验证构建

### Task 3.12 — 其余 P2 优化
- [ ] `useCellSelection` 多实例监听器：加引用计数，最后一个实例卸载时才移除 document 监听
- [ ] `useAddressRegistry` 加 `dispose()` 方法，清理 eventBus 监听器
- [ ] `AuditLogMiddleware` 注释说明与 `audit_decorator` 的分工
- [ ] `X-Response-Time` header：在 `ResponseWrapperMiddleware` 里保留原始 header
- [ ] `GtInfoBar` templateOptions 从 dictStore 取
- [ ] `pagination.build_paginated_response` 加 `skip_count` 选项
- [ ] `audit_decorator._resolve_model` 改为注册表模式
- [ ] `event_handlers.py` 加 `subscribe_many` 辅助函数
- [ ] `auth.ts` fetchUserProfile 改用 `API.users.me`
- [ ] 验证构建

### Task 3.13 — Sprint 3 收尾
- [ ] vue-tsc 零错误 + Vite 构建通过
- [ ] Python 语法检查通过
- [ ] git commit + push

---

## Sprint 4：P3 小优化 + 最终收尾（~2天）

### Task 4.1 — P3 小优化批量处理
- [x] `GtStatusTag` 加 size prop（默认 small）
- [ ] `GtEditableTable` lazyEdit 在 editable=false 时不初始化
- [ ] `operationHistory.undo()` 加 10 秒超时保护
- [ ] `confirm.ts` 对 itemName 做 HTML 转义
- [ ] `yearOptions` 改为动态计算当前年份
- [ ] `developing` 路由改为跳转专门的"开发中"页面
- [ ] `bcrypt rounds=14` 改为 12（或加配置项）
- [ ] `DefaultLayout.vue` watch 里 syncFromRoute 加 await
- [ ] `deps.py` 删除死代码 PERM_CACHE_TTL
- [ ] `useExcelIO.parseFile` 降级取第一个 sheet 而非最后一个
- [ ] `config.py` 加 EVENT_DEBOUNCE_MS 配置项
- [ ] `useKnowledge` 注释说明 _pickerResolve 单例限制
- [ ] `TrialBalanceService.recalc_unadjusted` 注释"需清零"改为"已清零"
- [ ] `body_limit.py` DELETE 跳过原因注释说明
- [ ] `deps.py` SoD 检查注释说明只检查全局撤销的限制

### Task 4.2 — 最终收尾
- [x] 全量 vue-tsc + Vite 构建验证
- [ ] Python 全量语法检查
- [ ] git commit + push + 合并到 master
- [x] 更新 memory.md + dev-history.md
