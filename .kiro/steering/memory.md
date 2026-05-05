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
- 提建议前先验证（不要引用过时记录，vue-tsc exit 0 = 零错误，不要再提已修复的问题）
- 文档同步：功能变更后同步更新需求文档
- 记忆拆分：memory.md 只放精简状态+待办，技术决策→architecture.md，规范→conventions.md，修复记录→dev-history.md
- 目标并发规模 6000 人
- 表格列宽要足够大，不折行不省略号截断
- 表格编辑需支持查看/编辑模式切换
- 复制按钮命名：工具栏"复制整表" vs 右键"复制选中区域"

## 环境配置

- Python 3.12（.venv），Docker 28.3.3，Ollama 0.11.10
- 前端新增依赖：mitt@3.0.1（事件总线）、nprogress@0.2.0（全局进度条）、unplugin-auto-import@21.0.0 + unplugin-vue-components@32.0.0（Element Plus 按需导入）
- PG 144 张表，Redis 6379，后端 9980，前端 3030
- vLLM Qwen3.5-27B-NVFP4 端口 8100（enable_thinking: false）
- ONLYOFFICE 端口 8080（已替换为 Univer，WOPI 保留兼容）
- Paperless-ngx 端口 8010（admin/admin）
- 测试用户：admin/admin123（role=admin）

## 当前系统状态（2026-05-05，post-enhancement-bugfix 完成）

- vue-tsc 零错误，Vite 构建通过（37.19s）
- 后端 119 个路由文件，172 个服务文件，42 个模型文件，~144 张表
- 前端 75+ 页面，20 个 common 组件，16 个 composables，9 个 stores，19 个 services，19 个 utils
- 后端约 700 路由，0 个 stub 残留
- git 分支：feature/global-component-library（已推送，待合并 master）
- **全局化增强项目完成**：4 Sprint，40 Task，~235 文件，+14422/-3164 行
- **post-enhancement-bugfix 项目完成**：4 Sprint，修复 B1-B9 业务缺陷 + P0-P3 技术 Bug
  - Sprint 1：试算平衡表 AJE/RJE 自动汇总、底稿上传两步确认、借贷平衡指示器修正、看板交互实现
  - Sprint 2：escapeRegex 修复、migration_runner 多语句分割、bulk_execute savepoint 隔离、v-permission 内存泄漏、router 权限检查、main.ts 图标注册、并发编号锁、pendingMap 泄漏、SSE 僵尸队列、shortcuts 输入框检查、apiProxy 统一、sessionStorage 替换、guardRoute 选项、amountClass 修复
  - Sprint 3：数据同步状态可视化（GtPageHeader showSyncStatus）、试算表双向导航、底稿识别确认步骤、N+1 优化（100→3次）、附注预加载（165→1次）、合计为0修复、syncFromRoute 非阻塞、router_registry 重复调用清理、GtPageHeader backMode、dictStore TTL、statusMaps+dictStore 统一、useCellSelection 引用计数、subscribe_many、auth.ts API.users.me
  - Sprint 4：operationHistory 超时保护、confirm.ts HTML 转义、bcrypt rounds 配置化（12）、DefaultLayout watch await、deps.py 死代码清理、parseFile 降级第一个 sheet、useKnowledge 单例注释

## 活跃待办

### 最高优先级
- 合并 feature/global-component-library 到 master（用户手动操作）
- 用真实审计项目进行用户验收测试（UAT）
- 生产环境部署准备（Docker 镜像、环境变量、数据库迁移）

### 功能完善（中期）
- 性能测试（真实 PG + 大数据量环境）
- token 存 localStorage 有 XSS 风险（考虑 sessionStorage 或 httpOnly cookie）[P3]
- working_paper_service 状态机 draft→edit_complete 是否符合业务流程（需确认）[P3]
- 合并模块需找真实项目做业务测试（技术完成度85%，业务完成度60%）[P1]
- 系统当前是"工程师视角"而非"审计员视角"，下一步重点是 UAT 而非加功能

## 底稿编码体系（致同 2025 修订版）

- D/F/K/N 循环，映射文件：backend/data/wp_account_mapping.json（88 条，v2025-R4）
