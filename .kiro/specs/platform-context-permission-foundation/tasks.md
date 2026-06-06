# 实施计划：平台上下文、年度与权限基础统一

## 任务总览

> 本节保留主任务索引；实际排期和执行以“详细落地拆解”为准。

- [ ] 1. ProjectContext 单一真源
  - [ ] 1.1 扩展 `stores/project.ts` 或新建 `useProjectContext`
  - [ ] 1.2 收敛 route/query/localStorage 中项目与年度解析逻辑
  - [ ] 1.3 实现 `resetProjectScopedState()`
  - [ ] 1.4 单元测试：项目切换清理旧项目状态
  - _Requirements: 1.1, 1.2, 1.3_

- [ ] 2. ProjectContextBar 全局组件
  - [ ] 2.1 新建 `ProjectContextBar.vue`
  - [ ] 2.2 接入项目、年度、准则、状态、当前职责展示
  - [ ] 2.3 在 `DefaultLayout` 或高频项目页接入
  - [ ] 2.4 视觉验收：不同状态 badge 与只读提示一致
  - _Requirements: 1.1, 2.1, 4.2_

- [ ] 3. 年度切换协议
  - [ ] 3.1 梳理所有使用 `selectedYear/year` 的页面和 composable
  - [ ] 3.2 实现年度切换事件与缓存清理
  - [ ] 3.3 禁止页面硬编码年度默认值
  - [ ] 3.4 测试：年度切换后底稿/报表/附注重新加载
  - _Requirements: 2.1, 2.2, 2.3_

- [ ] 4. 权限矩阵后端
  - [ ] 4.1 新建 `permission_matrix_service.py`
  - [ ] 4.2 定义系统角色 × 项目职责 × 操作 code
  - [ ] 4.3 迁移核心写操作 Depends 到权限矩阵
  - [ ] 4.4 契约测试：后端拒绝缺失权限
  - _Requirements: 3.1, 3.3, 3.4_

- [ ] 5. 权限矩阵前端
  - [ ] 5.1 新建 `permissionMatrix.ts` / `usePermissionMatrix`
  - [ ] 5.2 替换高频页面按钮显隐逻辑
  - [ ] 5.3 前后端权限 code 对齐测试
  - _Requirements: 3.1, 3.2_

- [ ] 6. 项目设置中心
  - [ ] 6.1 新建 `ProjectSettingsCenter.vue`
  - [ ] 6.2 接入年度、准则、模板、成员、职责、权限
  - [ ] 6.3 接入只读/签发/归档状态管理
  - [ ] 6.4 临时授权记录审计日志
  - _Requirements: 4.1, 4.2, 4.3_

- [ ] 7. 枚举字典扩展
  - [ ] 7.1 扩展 `_DICTS` 覆盖审计循环、风险等级、AI 状态等
  - [ ] 7.2 前端 `dictStore` 接入新增枚举
  - [ ] 7.3 测试 value 不可修改，label/color 可覆盖
  - _Requirements: 5.1, 5.2, 5.3_

- [ ] 8. 验收
  - [ ]* vue-tsc 0 errors
  - [ ]* pytest 权限矩阵相关测试通过
  - [ ]* 选取 5 个高频项目页验证项目/年度/权限一致

---

## 详细落地拆解（执行以本节为准）

### P0-MVP：一周内最小可交付

- [ ] MVP-1. `stores/project.ts` 暴露 `currentProjectContext`
- [ ] MVP-2. `setCurrentYear()` 触发核心缓存清理
- [ ] MVP-3. 后端 `permission_matrix_service.py` 支持首批 7 个 operation code
- [ ] MVP-4. 前端 `usePermissionMatrix` 支持 `can()` / `whyCannot()`
- [ ] MVP-5. `WorkpaperEditor` 与 `TrialBalance` 两个页面完成试点接入
- [ ] MVP-6. 测试文件落地：
  - `backend/tests/test_permission_matrix_service.py`
  - `audit-platform/frontend/src/__tests__/usePermissionMatrix.spec.ts`
  - `audit-platform/frontend/src/stores/__tests__/projectContext.spec.ts`
  - **验收标准**：后端 pytest mock DB in-memory 可跑；前端 vitest mock API shallow mount；核心 Property 对应 case 必须覆盖

### P0：上下文与权限最小闭环

- [ ] P0-1. 现状扫描与基线冻结
  - [ ] P0-1.1 grep 所有 `route.params.projectId`、`route.query.project_id`、`localStorage` 中项目/年度解析点
  - [ ] P0-1.2 grep 所有 `selectedYear`、`year = new Date()`、`2025`、`2026` 等硬编码年度
  - [ ] P0-1.3 grep 所有 `role ===`、`user.role`、`permission` 字符串判断
  - [ ] P0-1.4 输出 `docs/reference/project-context-migration-inventory.md`
  - _Requirements: 1.3, 2.3, 3.1_

- [ ] P0-2. ProjectContext facade
  - [ ] P0-2.1 在 `stores/project.ts` 增加 `currentProjectContext`
  - [ ] P0-2.2 暴露 `projectId/year/applicableStandard/auditScope/projectStatus/roleInProject`
  - [ ] P0-2.3 实现 `loadProjectContext(projectId)`
  - [ ] P0-2.4 实现 `resetProjectScopedState(reason)`
  - [ ] P0-2.5 单测：项目切换后旧 projectId 相关 state 清空
  - _Requirements: 1.1, 1.2, 1.3_

- [ ] P0-3. 年度切换协议
  - [ ] P0-3.1 新增 `setCurrentYear(year, { reload: true })`
  - [ ] P0-3.2 在年度切换时清理底稿、试算表、报表、附注、合并相关缓存
  - [ ] P0-3.3 停止旧年度 SSE / stale 订阅并重建
  - [ ] P0-3.4 为 `TrialBalance`、`ReportView`、`DisclosureEditor` 增加年度切换回归测试
  - _Requirements: 2.1, 2.2_

- [ ] P0-4. 权限矩阵后端 facade
  - [ ] P0-4.1 新建 `backend/app/services/permission_matrix_service.py`
  - [ ] P0-4.2 定义首批 operation code：`project:view`、`wp:edit`、`wp:review`、`report:edit`、`report:sign`、`note:edit`、`archive:manage`
  - [ ] P0-4.3 将系统角色 + 项目职责解析为 operation set
  - [ ] P0-4.4 API：`GET /api/projects/{project_id}/permission-matrix`
  - [ ] P0-4.5 pytest：不同角色返回权限集合符合预期
  - _Requirements: 3.1, 3.3_

- [ ] P0-5. 权限矩阵前端 facade
  - [ ] P0-5.1 新建 `usePermissionMatrix(projectId)`
  - [ ] P0-5.2 提供 `can(operationCode)`、`whyCannot(operationCode)`
  - [ ] P0-5.3 兼容旧 `usePermission`，旧调用不立即删除
  - [ ] P0-5.4 Vitest：operation code 前后端快照一致
  - _Requirements: 3.2, 3.4_

- [ ] P0-6. 高频页面试点接入
  - [ ] P0-6.1 `WorkpaperEditor` 接入 ProjectContext 与权限矩阵
  - [ ] P0-6.2 `WorkpaperList` 接入 ProjectContext 与权限矩阵
  - [ ] P0-6.3 `TrialBalance` 接入 ProjectContext 与年度切换
  - [ ] P0-6.4 `ReportView` 接入 ProjectContext 与年度切换
  - [ ] P0-6.5 `DisclosureEditor` 接入 ProjectContext 与年度切换
  - _Requirements: 1.1, 2.1, 3.2_

### P1：项目设置中心与字典扩展

- [ ] P1-1. ProjectContextBar
  - [ ] P1-1.1 新建 `components/common/ProjectContextBar.vue`
  - [ ] P1-1.2 展示项目、年度、准则、审计范围、项目状态、当前职责
  - [ ] P1-1.3 支持年度切换事件
  - [ ] P1-1.4 接入高频页面头部
  - _Requirements: 1.1, 2.1_

- [ ] P1-2. 项目设置中心
  - [ ] P1-2.1 新建 `views/ProjectSettingsCenter.vue`
  - [ ] P1-2.2 Tab：基本信息、年度准则、成员职责、权限、模板、锁定策略
  - [ ] P1-2.3 接入 `project_permissions.py` 与 staff API
  - [ ] P1-2.4 UAT：项目经理可调整成员职责，审计助理不可见权限 Tab
  - _Requirements: 4.1_

- [ ] P1-3. 枚举字典扩展
  - [ ] P1-3.1 扩展 `system_dicts.py`：审计循环、风险等级、AI 内容状态、归档状态
  - [ ] P1-3.2 前端 `dict.ts` 增加新增 dict key 类型
  - [ ] P1-3.3 替换高频页面硬编码中文状态 label
  - [ ] P1-3.4 pytest：value 修改返回 405 或业务错误码
  - _Requirements: 5.1, 5.2, 5.3_

### P2：临时授权与全量迁移

- [ ] P2-1. 临时授权
  - [ ] P2-1.1 先出 ADR：临时授权使用新表还是复用现有权限日志
  - [ ] P2-1.2 如需新表，编写 Vxxx migration + rollback
  - [ ] P2-1.3 同步 ORM 模型、Pydantic schema、service
  - [ ] P2-1.4 编写三层一致契约测试
  - [ ] P2-1.5 字段：operation_code、grantee、approver、reason、expires_at
  - [ ] P2-1.6 过期自动失效
  - [ ] P2-1.7 审计日志记录授权、使用、过期
  - _Requirements: 4.3_

- [ ] P2-2. 全量迁移与删除旧入口
  - [ ] P2-2.1 迁移剩余项目内页面的 project/year/permission 解析
  - [ ] P2-2.2 grep 确认旧解析点下降到白名单
  - [ ] P2-2.3 对旧 `usePermission` 直接角色判断加 deprecated warning
  - [ ] P2-2.4 编写迁移总结与剩余白名单
  - _Requirements: 1.3, 3.2_

### 验收与回归

- [ ] UAT-1 审计助理：切换项目后，待办、底稿、年度、编辑锁全部刷新
- [ ] UAT-2 项目经理：进入项目设置中心调整职责并影响按钮权限
- [ ] UAT-3 QC：无项目管理权限时前端不可见且后端拒绝
- [ ] UAT-4 管理员：修改枚举 label/color 后前端标签更新
- [ ] CI-1 `vue-tsc` 0 errors
- [ ] CI-2 权限矩阵 pytest + Vitest 全绿
- [ ] CI-3 硬编码年度扫描无新增违规
