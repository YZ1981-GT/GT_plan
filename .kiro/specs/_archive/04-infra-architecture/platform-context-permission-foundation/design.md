# 设计文档：平台上下文、年度与权限基础统一

## 概述

本 spec 解决平台上线后的基础一致性问题：项目上下文、年度上下文、权限矩阵、项目设置中心和枚举字典扩展。目标是避免跨项目串数据、跨年度缓存污染、前端按钮与后端授权不一致、项目级配置入口分散。

## 核心设计

### 1. ProjectContext 单一真源

新增前端 `useProjectContext` / store 扩展，统一提供：

| 字段 | 说明 |
|---|---|
| `projectId` | 当前项目 ID |
| `projectName` | 当前项目名称 |
| `year` | 当前年度 |
| `applicableStandard` | 适用准则 |
| `auditScope` | 单体/合并 |
| `projectStatus` | draft/active/signed/archived |
| `roleInProject` | 当前人在项目中的职责 |

页面不再自行从 route/query/localStorage 多处解析项目状态。项目切换触发统一 `resetProjectScopedState()`。

### 2. ProjectContextBar

新增全局组件 `ProjectContextBar.vue`，由项目内页面统一使用：

- 项目选择
- 年度选择
- 准则展示
- 项目状态 badge
- 只读/归档提示
- 当前角色/职责提示

### 3. 年度切换协议

年度切换统一触发：

1. 清理底稿/报表/附注/合并本地缓存。
2. 停止旧年度 SSE 订阅。
3. 重新加载字典、模板、stale 状态。
4. 重新计算可用操作权限。

### 4. 权限矩阵

后端新增 `permission_matrix_service.py`，前端新增 `permissionMatrix.ts` 类型定义。权限拆成：

| 层级 | 示例 |
|---|---|
| 系统角色 | admin / auditor / manager / partner / qc / eqcr |
| 项目职责 | preparer / reviewer / manager / partner / eqcr |
| 临时授权 | emergency_unlock / substitute_reviewer |

前端按钮显隐和后端 Depends 使用同一权限 code。

### 5. 项目设置中心

在项目内新增 `ProjectSettingsCenter.vue`，聚合：

- 基本信息
- 年度与准则
- 项目成员与职责
- 权限与临时授权
- 模板选择
- 锁定策略
- 归档/签发状态

### 6. 枚举字典扩展

扩展 `system_dicts`：

- 审计循环 A-N
- 风险等级
- AI 内容确认状态
- 复核状态
- 工时状态
- 归档状态

value 仍由代码锁死，label/color 支持 DB 覆盖。

## 数据流

```text
route projectId
  -> project store load
  -> ProjectContext
  -> ProjectContextBar / permission matrix / page data
  -> year change
  -> reset caches + reload project-scoped resources
```

## 不在范围

- 不替换现有 auth token。
- 不重写所有 `usePermission` 调用，先提供兼容 facade。
- 不改变历史项目数据。

## 现有代码锚点

### 前端

- `audit-platform/frontend/src/stores/project.ts`：项目上下文基础。
- `audit-platform/frontend/src/stores/roleContext.ts`：角色视图上下文。
- `audit-platform/frontend/src/composables/useProjectSelector.ts`：项目选择逻辑。
- `audit-platform/frontend/src/composables/useAuditContext.ts`：审计上下文。
- `audit-platform/frontend/src/composables/usePermission.ts`：现有权限判断入口。
- `audit-platform/frontend/src/composables/useProjectRole.ts`：项目角色判断。
- `audit-platform/frontend/src/stores/dict.ts`：枚举字典缓存。

### 后端

- `backend/app/services/permission_service.py`：权限服务基础。
- `backend/app/routers/project_permissions.py`：项目权限路由。
- `backend/app/routers/system_dicts.py`：枚举字典路由。
- `backend/app/services/project_wizard_service.py`：项目初始化与设置相关逻辑。
- `backend/app/models/staff_models.py` / `staff_schemas.py`：人员与职责模型。

## 迁移策略

1. 先新增 facade，不删除 `usePermission` / `useProjectRole`。
2. 首批只接入 5 个高频项目页：`WorkpaperEditor`、`WorkpaperList`、`TrialBalance`、`ReportView`、`DisclosureEditor`。
3. 所有旧入口通过 console warn 标记 deprecated。
4. 前后端权限 code 稳定后，再迁移二级页面和弹窗。

## API 草案

- `GET /api/projects/{project_id}/context`
- `GET /api/projects/{project_id}/permission-matrix`
- `POST /api/projects/{project_id}/temporary-grants`
- `GET /api/system/dicts?scope=platform`

## 风险与回滚

- 风险：权限矩阵替换过快可能造成按钮消失或误拒绝。  
  回滚：保留旧 `usePermission` fallback，并提供 `PERMISSION_MATRIX_STRICT=false` 开关。
- 风险：项目切换清理过度导致页面状态丢失。  
  回滚：只清理 project-scoped store，不清理用户显示偏好。
