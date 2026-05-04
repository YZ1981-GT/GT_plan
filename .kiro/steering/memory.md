---
inclusion: always
---

# 持久记忆

每次对话自动加载。详细架构见 `#architecture`，编码规范见 `#conventions`，开发历史见 `#dev-history`。
当 memory.md 超过 ~200 行时，自动将已完成事项迁移到 dev-history.md，技术决策迁移到 architecture.md，规范迁移到 conventions.md，保持自身简洁（只留状态摘要+活跃待办）。

## 用户偏好（核心）

- 语言：中文
- 部署：本地优先、轻量方案
- 启动：`start-dev.bat` 一键启动后端 9980 + 前端 3030
- 打包：build_exe.py（PyInstaller），不要 .bat
- 功能收敛：停止加新功能，核心 6-8 个页面做到极致，空壳标记 developing
- 前后端联动：不能只开发后端不管前端
- 删除必须二次确认，所有删除先进回收站
- 一次性脚本用完即删
- 文档同步：功能变更后同步更新需求文档
- 记忆拆分：memory.md 只放精简状态+待办，技术决策→architecture.md，规范→conventions.md，修复记录→dev-history.md
- 目标并发规模 6000 人
- 表格列宽要足够大，不折行不省略号截断
- 表格编辑需支持查看/编辑模式切换
- 复制按钮命名：工具栏"复制整表" vs 右键"复制选中区域"

## 环境配置

- Python 3.12（.venv），Docker 28.3.3，Ollama 0.11.10
- 前端新增依赖：mitt@3.0.1（事件总线）
- PG 144 张表，Redis 6379，后端 9980，前端 3030
- vLLM Qwen3.5-27B-NVFP4 端口 8100（enable_thinking: false）
- ONLYOFFICE 端口 8080（已替换为 Univer，WOPI 保留兼容）
- Paperless-ngx 端口 8010（admin/admin）
- 测试用户：admin/admin123（role=admin）

## 当前系统状态（2026-05-04）

- 17 个开发阶段中 16 个完成，vue-tsc 零错误，Vite 构建通过
- 后端约 700 路由，0 个 stub 残留
- 审计员 8 步全流程理论可走通
- git 分支：feature/global-component-library（已推送）
- 开发任务 spec：.kiro/specs/global-platform-enhancement/（requirements 62项 + design 6决策4Sprint + tasks 46Task ~23天，一致性已核对）
- 全局组件库已建立：7 个新工具 + 24 个组件修改（详见 #architecture "前端全局组件库"章节）
- 5 核心模块全部接入：displayPrefs/拖拽框选/SelectionBar/搜索/条件格式/右键保持选区
- 14 个 worksheet 组件完成 useFullscreen + fmtAmount 迁移
- **Sprint 1 已完成**（10 Task，65 文件，+1856/-697 行）— 全局化收尾+快速见效
- **Sprint 2 已完成**（9 Task，70 文件，+2569/-983 行）— 核心基础设施
- Sprint 2 新增基础设施：eventBus.ts（mitt 类型安全事件总线）、stores/project.ts、apiPaths.ts（500+ 路径）、usePermission + v-permission 指令、路由守卫统一（认证+权限+项目上下文）、batch_mode 批量提交
- 后端 5 个路由文件修复双重包装（"data"字段名→"rows"/"content"），前端 30+ 文件清理 data?.data 兼容代码
- 前端 21 个 view/component 文件从 http 直接导入迁移到 apiProxy

## 活跃待办

### 最高优先级
- 用真实审计项目端到端验证（全流程）
- 引入数据库 migration 机制（版本化 SQL 脚本管理）
- 事件链路失败通知机制（前端可见的同步状态面板）
- 合并模块集成测试

### 功能完善（中期）
- 模拟权益法改进（6 项子任务）
- 合并抵消分录表汇总中心（5 个区域）
- 3 张内部抵消表→合并抵消分录表自动汇总

### 全局化改造 — Sprint 1 已完成 ✅
- ✅ formatters.ts 剩余替换：22 组件批量替换为 fmtAmount（Task 1.1）
- ✅ displayPrefs 接入 13 个 worksheet 组件（Task 1.2）
- ✅ CommentTooltip 接入 4 个核心模块（Task 1.3）
- ✅ VirtualScrollTable 接入 formatters（Task 1.4）
- ✅ confirm.ts 语义化确认弹窗（Task 1.5）
- ✅ statusMaps.ts + GtStatusTag 组件（Task 1.6）
- ✅ useEditMode composable（Task 1.7）
- ✅ ExcelImportPreviewDialog 通用导入预览（Task 1.8）
- ✅ operationHistory 接入（Task 1.9）
- ✅ GtAmountCell 金额单元格组件（Task 1.10）

### 全局化改造 — Sprint 2 已完成 ✅
- ✅ mitt 事件总线替代 CustomEvent（Task 2.1）
- ✅ useProjectStore Pinia store（Task 2.2）
- ✅ apiPaths.ts API 路径集中管理（Task 2.3）
- ✅ 后端响应格式统一（Task 2.4）
- ✅ usePermission + v-permission 指令（Task 2.5）
- ✅ 路由守卫统一 router beforeEach（Task 2.6）
- ✅ API 调用统一收口（Task 2.7）
- ✅ 批量操作场景优化（Task 2.8）
- ✅ shortcuts.ts 接入各模块（Task 2.9）

### 全局化改造 — Sprint 3+ 待开始
- ❹ useTableToolbar composable（1天）
- ❼ useDictStore 枚举字典（2天含后端）
- ❾ useAddressRegistry 地址坐标 Store（1天）
- ⑩ useExcelIO composable（1天）
- ⑪ SharedTemplatePicker 扩展到 8 个 configType（1天）
- ⑫ useKnowledge + KnowledgePickerDialog（1.5天）
- ⑬ GtToolbar 标准工具栏组件（1天）
- ⑭ GtEditableTable 高阶组件（3-5天，中期）
- ⑯ useCopyPaste composable（1天）
- ⑰ 模板市场全局入口（半天）
- ⑳ useLoading + NProgress 全局进度条（1天）
- ㉑ 表格列配置声明式管理（中期）
- ㉒ 后端 PaginationParams/SortParams 统一（1天）
- ㉓ 后端批量操作 BulkOperationMixin（1天）
- ㉔ 后端审计日志装饰器 before/after diff（1.5天）
- ㉘ useAutoSave 自动保存/草稿恢复（1天）
- ㉙ TanStack Query 接入高频 API（2天）
- ㉛ sse.ts 全局连接接入（1天）
- ㉜ ErrorBoundary 细粒度错误隔离（半天）
- ㉝ useExport 统一导出服务（1.5天）
- ㉞ GtPageHeader 通用页面横幅（1天）
- ㉟ GtInfoBar 信息栏组件（半天）

### 架构优化（低优先级）
- 前端主 bundle 优化（Element Plus 按需导入）
- ResponseWrapperMiddleware 大响应性能
- POST 请求防重复提交
- 上线前压力测试

### 用户体验（持续）
- 合并模块向导式步骤条引导
- 500 错误重试 loading 提示
- 423 锁定错误显示详情
- 查看/编辑模式切换推广
- 键盘导航 + 批量粘贴

### 表格交互增强（WPS 借鉴）
#### P2
- 列显示/隐藏、数值范围校验、单元格锁定、分组折叠、排序筛选默认开启
#### P3
- 打印预览弹窗、批注线程（回复链）

## 底稿编码体系（致同 2025 修订版）

- D/F/K/N 循环，映射文件：backend/data/wp_account_mapping.json（88 条，v2025-R4）
