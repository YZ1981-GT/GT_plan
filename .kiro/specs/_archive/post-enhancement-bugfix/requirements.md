# 需求文档：审计平台缺陷修复与业务优化

## 背景

全局化增强项目（4 Sprint，40 Task）已完成，系统技术完成度约 85%。经过十轮系统性代码复盘和合伙人视角的业务分析，发现以下问题：

1. **业务逻辑缺陷**：试算平衡表数据不一致、底稿上传后五环联动断裂、借贷平衡指示器逻辑错误等，直接影响审计质量
2. **技术 Bug**：内存泄漏、并发竞争、N+1 查询、死代码等，影响系统稳定性和性能
3. **用户体验缺口**：高频操作路径过长、静默失败无提示、看板功能未实现等，导致审计员绕过系统

本轮目标：**修复所有 P0/P1 缺陷，优化 P2 问题，补全关键业务功能缺口**。

---

## 需求分类

### B 类：业务逻辑缺陷（最高优先级，直接影响审计质量）

- **B1** 试算平衡表 AJE/RJE 列不应手动输入，应从调整分录自动汇总
- **B2** 底稿上传后未自动触发解析（审定数不更新，五环联动断裂）
- **B3** 借贷平衡指示器逻辑错误（应为资产=负债+权益，而非审定数合计≈0）
- **B4** 复核通过时未检查未解决批注（复核质量风险）
- **B5** 看板视图核心交互（选中底稿、分配底稿）未实现
- **B6** 批量复核跳过的分录无提示（静默失败，审计员误判）
- **B7** 调整分录科目选择应显示对应报表行次
- **B8** 试算表科目编码链接应直接打开底稿编辑器（而非跳到列表页再找）
- **B9** CommentThread 批注"已解决"状态应与复核流程强制联动（所有批注解决后才能通过复核）

### P0：严重 Bug（数据正确性）

- **P0.1** `useTableSearch.escapeRegex` 替换字符串是 UUID 占位符，应为 `'\\$&'`，影响含特殊字符的搜索替换
- **P0.2** `migration_runner._apply_migration` 整体执行 SQL 文件，多语句文件只执行第一条（asyncpg 限制）
- **P0.3** `bulk_execute` 未用 savepoint 隔离部分失败，失败操作的脏数据可能被 flush
- **P0.4** `ReportFormulaParser.execute` 失败时隐式返回 None，导致后续 Decimal 运算 TypeError

### P1：重要 Bug（稳定性/内存/并发）

- **P1.1** `v-permission` 指令每次 mounted/updated 调用 `usePermission()` 造成内存泄漏
- **P1.2** `router/index.ts` beforeEach 里调用 `usePermission()` 创建游离 computed
- **P1.3** `main.ts` 全量注册 Element Plus 图标（与 unplugin 冲突，增大 bundle）
- **P1.4** `adjustment_service._next_adjustment_no` 并发竞争产生重复编号
- **P1.5** `http.ts` POST 防重复提交 pendingMap 泄漏（超时/取消时 key 未清理）
- **P1.6** `EventBus` 僵尸 SSE 队列未清理（QueueFull 时应直接移除）
- **P1.7** `shortcuts.ts` 在输入框里触发快捷键（缺少 isInputFocused 检查）
- **P1.8** `useProjectStore.loadProjectOptions` 直接 import http 绕过 apiProxy
- **P1.9** `dictStore.load` 直接 import http + 残留 data?.data 双层解包
- **P1.10** `useAutoSave` 改用 sessionStorage（防止多标签页 key 冲突）
- **P1.11** `useEditMode` 加 guardRoute 选项（子组件调用时跳过路由守卫）
- **P1.12** `displayPrefs.amountClass` 上期值为 0 时不高亮（应直接高亮）

### P2：优化项（性能/设计/用户体验）

- **P2.1** 数据同步状态可视化（试算表/报表/附注加"最后更新时间"指示器）
- **P2.2** 试算表科目行加"查看相关分录"快捷入口（双向导航）
- **P2.3** 底稿上传后增加"系统识别结果确认"步骤
- **P2.4** `list_entries` N+1 查询优化（改为批量 IN 查询）
- **P2.5** `disclosure_engine.generate_notes` 上年附注查询移到预加载（165次→1次）
- **P2.6** `_build_table_data` 合计为 0 时显示 None 而非 0
- **P2.7** `useCellSelection` 多实例 document 监听器重复注册问题
- **P2.8** `useAddressRegistry` eventBus 监听器无清理
- **P2.9** `syncFromRoute` 改为非阻塞（先渲染页面，数据异步更新）
- **P2.10** `statusMaps.ts` 和 `dictStore` 统一为一套
- **P2.11** `router_registry.py` 重复调用 `register_phase14_rules()`
- **P2.12** `AuditLogMiddleware` 和 `audit_decorator` 两套审计日志明确分工
- **P2.13** `X-Response-Time` header 被 `ResponseWrapperMiddleware` 覆盖
- **P2.14** `GtPageHeader` 加 backMode prop（支持 router.back()）
- **P2.15** `GtInfoBar` templateOptions 从 dictStore 取
- **P2.16** `useDictStore` 缓存加 TTL（24小时过期）
- **P2.17** `pagination.build_paginated_response` 加 skip_count 选项
- **P2.18** `audit_decorator._resolve_model` 改为注册表模式
- **P2.19** `event_handlers.py` 重构（subscribe_many + 内联逻辑移出）
- **P2.20** `auth.ts` fetchUserProfile 改用 API.users.me

### P3：小优化（文档/注释/低优先级）

- **P3.1** `GtStatusTag` 加 size prop
- **P3.2** `GtEditableTable` lazyEdit 在 editable=false 时不初始化
- **P3.3** `operationHistory.undo()` 加 10 秒超时保护
- **P3.4** `confirm.ts` 对 itemName 做 HTML 转义
- **P3.5** `yearOptions` 改为动态计算当前年份
- **P3.6** `developing` 路由改为跳转专门页面
- **P3.7** `bcrypt rounds=14` 改为 12 或配置项
- **P3.8** `DefaultLayout.vue` watch 里 syncFromRoute 加 await
- **P3.9** `deps.py` 删除死代码 PERM_CACHE_TTL
- **P3.10** `useExcelIO.parseFile` 降级取第一个 sheet 而非最后一个
- **P3.11** `config.py` 加 EVENT_DEBOUNCE_MS 配置项
- **P3.12** `useKnowledge` 注释说明 _pickerResolve 单例限制
