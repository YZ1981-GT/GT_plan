# 需求文档：审计平台全局化增强

## 背景

审计作业平台已完成 16 个开发阶段，核心审计流程（导入→查账→调整→试算表→底稿→附注→报告→Word导出）理论可走通。但经全面评审发现：前端组件重复度高（17个组件各自实现全屏、35+处重复金额格式化、15+处重复导入导出）、模块间通信脆弱（CustomEvent 无类型安全）、缺少企业级基础设施（权限指令、自动保存、实时通知等）。

本轮开发目标：**不加新功能，把现有功能打磨到企业级水准**。

## 需求分类

### R1：基础设施加固（最高优先级）

- R1.1 用真实审计项目端到端验证全流程，暴露并修复实际问题
- R1.2 引入数据库版本化迁移机制，替代 create_all + 手动 ALTER TABLE
- R1.3 五环联动事件链路失败时，前端需可见的同步状态面板通知用户
- R1.4 前端 API 调用统一收口到 apiProxy.ts，消除 authHttp/http/api 三套并存
- R1.5 合并模块集成测试覆盖主线：合并范围→试算表→抵消分录→差额表→合并报表
- R1.6 批量调整分录支持"批量提交"模式，一次性触发重算

### R2：全局化改造 — 收尾（进行中）

- R2.1 formatters.ts 替换剩余 20+ 组件的本地格式化函数
- R2.2 displayPrefs Store 接入 13 个 worksheet 组件（单位/字号/条件格式）
- R2.3 CommentTooltip 批注气泡接入剩余 4 个核心模块

### R3：全局化改造 — Composable 层

- R3.1 mitt 事件总线替代 CustomEvent，类型安全+自动清理
- R3.2 useProjectStore 统一项目上下文（projectId/year/standard），从路由自动同步
- R3.3 useTableToolbar 通用表格工具栏逻辑（增删行/多选/导入导出/复制）
- R3.4 useEditMode 查看/编辑模式切换+未保存提示+路由拦截
- R3.5 useExcelIO 统一 Excel 导入导出（exportTemplate/exportData/parseFile）
- R3.6 useCopyPaste 表格复制粘贴（选中区域→制表符文本，Excel粘贴→多单元格写入）
- R3.7 useKnowledge 全局知识库调用（search/pickDocuments/buildContext）
- R3.8 useAutoSave 自动保存/草稿恢复（localStorage+恢复提示）
- R3.9 useLoading + NProgress 全局进度条
- R3.10 usePermission + v-permission 前端按钮级权限控制

### R4：全局化改造 — Store 层

- R4.1 useDictStore 枚举字典（后端 /api/system/dicts + 前端 sessionStorage 缓存）
- R4.2 useAddressRegistry 地址坐标全局注册表

### R5：全局化改造 — 组件层

- R5.1 GtToolbar 标准工具栏组件（导出/导入/全屏/公式/模板/编辑切换/显示设置）
- R5.2 GtEditableTable 高阶可编辑表格（内置选中/拖拽/右键/批注/增删行/全屏/懒加载/小计）
- R5.3 ExcelImportPreviewDialog 通用导入预览弹窗
- R5.4 GtPageHeader 通用页面横幅（紫色渐变+返回+标题+InfoBar+操作按钮slot）
- R5.5 GtInfoBar 信息栏组件（单位/年度/模板选择+徽章+分隔线）
- R5.6 GtAmountCell 金额单元格组件（跟随displayPrefs+可点击+hover高亮）
- R5.7 GtStatusTag 状态标签组件（配合statusMaps.ts）
- R5.8 SharedTemplatePicker 扩展到 8 个 configType

### R6：全局化改造 — Utils 层

- R6.1 apiPaths.ts API 路径集中管理
- R6.2 statusMaps.ts 状态标签映射集中管理
- R6.3 confirm.ts 语义化确认弹窗（confirmDelete/confirmBatch/confirmDangerous）
- R6.4 shortcuts.ts 接入各模块（已有13个快捷键未监听）
- R6.5 sse.ts 全局 SSE 连接接入（已有封装未使用）
- R6.6 operationHistory.ts 接入删除/调整等关键操作
- R6.7 VirtualScrollTable 接入 formatters.ts

### R7：全局化改造 — 路由与中间件

- R7.1 路由守卫统一（权限+项目上下文+未保存拦截）
- R7.2 后端响应格式彻底统一
- R7.3 后端 PaginationParams/SortParams 统一
- R7.4 后端批量操作 BulkOperationMixin
- R7.5 后端审计日志装饰器（服务层 before/after diff）

### R8：架构优化

- R8.1 Element Plus 按需导入（当前 index.js 1.3MB）
- R8.2 ResponseWrapperMiddleware 大响应跳过
- R8.3 POST 请求防重复提交
- R8.4 上线前压力测试

### R9：用户体验

- R9.1 合并模块向导式步骤条引导
- R9.2 500 错误重试 loading 提示
- R9.3 423 锁定错误显示锁定人/时间/解锁方式
- R9.4 查看/编辑模式切换推广到全模块
- R9.5 键盘导航（Tab切换单元格）+ 批量粘贴

### R10：表格交互增强（WPS 借鉴）

- R10.1 列显示/隐藏
- R10.2 数值范围校验
- R10.3 单元格锁定（公式行/已复核行/合计行）
- R10.4 分组折叠（大纲）
- R10.5 排序筛选默认开启
- R10.6 打印预览弹窗
- R10.7 批注线程（回复链）

### R11：功能完善

- R11.1 模拟权益法改进（6项子任务）
- R11.2 合并抵消分录表汇总中心
- R11.3 内部抵消表→合并抵消分录表自动汇总
