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
- 前端新增依赖：mitt@3.0.1（事件总线）、nprogress@0.2.0（全局进度条）
- PG 144 张表，Redis 6379，后端 9980，前端 3030
- vLLM Qwen3.5-27B-NVFP4 端口 8100（enable_thinking: false）
- ONLYOFFICE 端口 8080（已替换为 Univer，WOPI 保留兼容）
- Paperless-ngx 端口 8010（admin/admin）
- 测试用户：admin/admin123（role=admin）

## 当前系统状态（2026-05-05，全局化增强完成）

- 17 个开发阶段中 16 个完成，vue-tsc 零错误，Vite 构建通过
- 后端约 700 路由，0 个 stub 残留
- 审计员 8 步全流程端到端验证通过
- git 分支：feature/global-component-library（已推送，待合并 master）
- 开发任务 spec：.kiro/specs/global-platform-enhancement/（4 Sprint 46 Task 全部完成）
- **全局化增强项目完成**：4 Sprint，46 Task，~235 文件，+14422/-3164 行
- **Sprint 1 已完成**（10 Task，65 文件，+1856/-697 行）— 全局化收尾+快速见效
- **Sprint 2 已完成**（9 Task，70 文件，+2569/-983 行）— 核心基础设施
- **Sprint 3 已完成**（14 Task，63 文件，+4720/-1224 行）— 组件层+后端统一
- **Sprint 4 已完成**（10 Task，37 文件，+5277/-260 行）— 高阶组件+验证+优化
- Sprint 4 新增前端：GtEditableTable 高阶可编辑表格、GtPrintPreview 打印预览、GtConsolWizard 合并向导、CommentThread 批注线程、SyncStatusIndicator 同步状态、useKeyboardNav 键盘导航
- Sprint 4 新增后端：migration_runner.py 数据库迁移、equity_method_service.py 模拟权益法、elimination_service 增强、load_test.py 压力测试、test_consolidation_chain.py 合并集成测试、test_e2e_audit_flow.py 端到端测试
- Sprint 4 架构优化：Element Plus unplugin 按需导入、ResponseWrapperMiddleware 大响应跳过、POST 防重复提交、SSE 全局接入

## 活跃待办

### 最高优先级
- 合并 feature/global-component-library 到 master（用户手动操作）
- 用真实审计项目进行用户验收测试（UAT）
- 生产环境部署准备（Docker 镜像、环境变量、数据库迁移）

### 功能完善（中期）
- 合并报表前端 TS 错误清理（Phase 2 遗留，标记 developing）
- 性能测试（真实 PG + 大数据量环境）

### 全局化改造 — Sprint 1 已完成 ✅
### 全局化改造 — Sprint 2 已完成 ✅
### 全局化改造 — Sprint 3 已完成 ✅
### 全局化改造 — Sprint 4 已完成 ✅
- ✅ GtEditableTable 高阶可编辑表格组件（Task 4.1）
- ✅ 端到端验证全流程（Task 4.2）
- ✅ 数据库 migration 机制（Task 4.3）
- ✅ 合并模块集成测试（Task 4.4）
- ✅ 事件链路失败通知 + SSE 全局接入（Task 4.5）
- ✅ 架构优化 — Element Plus 按需导入等（Task 4.6）
- ✅ 用户体验改进 — 向导步骤条、重试提示等（Task 4.7）
- ✅ 表格交互增强 — WPS 借鉴（Task 4.8）
- ✅ 功能完善 — 模拟权益法等（Task 4.9）
- ✅ 最终收尾 — 构建验证+推送（Task 4.10）

## 底稿编码体系（致同 2025 修订版）

- D/F/K/N 循环，映射文件：backend/data/wp_account_mapping.json（88 条，v2025-R4）
