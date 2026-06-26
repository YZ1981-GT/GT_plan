# Requirements Document

## Introduction

D0-1 函证汇总表通过 `useConfirmationDispatch` composable 向下游底稿（D0-4/D0-5/D0-6/D0-7）分发行数据。当前分发记录仅存于前端 `dispatchedMap`（内存 Map），刷新即丢失，下游底稿无法从后端加载"从上游带入"的数据，多人协同时分发状态不可见。本特性为分发逻辑接入后端持久化 API，实现跨页面、跨用户的分发状态一致性。

## Glossary

- **Dispatch_Service**: 后端分发记录持久化服务，负责创建、查询、去重分发记录
- **Dispatch_Record**: 单条分发记录，描述"哪条函证行被分发到了哪个下游底稿"
- **Upstream_Workpaper**: 分发源底稿（D0-1 函证汇总表）
- **Downstream_Workpaper**: 分发目标底稿（D0-4/D0-5/D0-6/D0-7）
- **Dispatch_API**: 后端 RESTful 端点，提供分发记录的 CRUD 和查询能力
- **useConfirmationDispatch**: 前端 composable，封装分发逻辑（路由规则、去重、执行）
- **dispatchedMap**: 前端内存中的分发状态映射（confirm_index → target Set）
- **confirm_index**: 函证索引号，D0 系列跨底稿引用的全局唯一主键
- **DispatchTarget**: 分发目标底稿标识（D0-4 / D0-5 / D0-6 / D0-7）

## Requirements

### Requirement 1: 分发记录持久化

**User Story:** As a 审计助理, I want 分发记录被保存到后端数据库, so that 刷新页面后分发状态不丢失。

#### Acceptance Criteria

1. WHEN 用户在 D0-1 执行分发操作, THE Dispatch_Service SHALL 将每条 Dispatch_Record 持久化到数据库，包含 project_id、confirm_index、target（D0-4/D0-5/D0-6/D0-7）、account_type、amount、reason、dispatched_by、dispatched_at 字段
2. WHEN Dispatch_Record 已存在相同 project_id + confirm_index + target 组合, THE Dispatch_Service SHALL 拒绝重复写入并返回去重标识（skipped）
3. WHEN 分发操作包含多条记录, THE Dispatch_Service SHALL 在单个数据库事务中批量写入，全部成功或全部回滚
4. IF 数据库写入失败, THEN THE Dispatch_Service SHALL 返回错误详情且不修改任何已有记录

### Requirement 2: 分发记录查询 API

**User Story:** As a 审计助理, I want 打开底稿时自动加载已有的分发记录, so that 刷新页面或切换设备后能看到完整的分发状态。

#### Acceptance Criteria

1. THE Dispatch_API SHALL 提供按 project_id 查询全部分发记录的端点
2. WHEN 前端请求指定 target 参数时, THE Dispatch_API SHALL 仅返回该目标底稿的分发记录
3. WHEN 前端请求指定 confirm_index 参数时, THE Dispatch_API SHALL 仅返回该函证行的分发记录
4. THE Dispatch_API SHALL 在响应中包含 dispatched_by 用户标识和 dispatched_at 时间戳

### Requirement 3: 下游底稿加载上游带入数据

**User Story:** As a 审计助理, I want 打开 D0-4/D0-5/D0-6/D0-7 时自动获取从 D0-1 分发来的行数据, so that 无需手动录入上游已确认的信息。

#### Acceptance Criteria

1. WHEN 下游底稿组件挂载时, THE Downstream_Workpaper SHALL 调用 Dispatch_API 查询 target 为自身的全部 Dispatch_Record
2. WHEN 查询返回分发记录, THE Downstream_Workpaper SHALL 将记录中的 confirm_index、entity_name、account_type、amount、reason 填充到组件的"从 D0-1 带入"区域
3. WHEN 下游底稿已存在相同 confirm_index 的本地行, THE Downstream_Workpaper SHALL 跳过该行不重复填充（前端去重）
4. IF Dispatch_API 请求失败, THEN THE Downstream_Workpaper SHALL 显示加载失败提示且不阻断底稿正常使用

### Requirement 4: 分发状态跨用户可见

**User Story:** As a 现场经理, I want 看到其他团队成员已分发的记录, so that 多人协同时不会重复分发相同数据。

#### Acceptance Criteria

1. WHEN 用户 A 分发记录成功, THE Dispatch_Service SHALL 使该记录对同一 project_id 下的所有用户可见
2. WHEN 用户 B 打开 D0-1 时, THE useConfirmationDispatch SHALL 从后端加载已有分发记录初始化 dispatchedMap，使已分发行不再出现在待分发列表中
3. WHEN 用户 A 分发后用户 B 同时尝试分发相同 confirm_index + target, THE Dispatch_Service SHALL 通过唯一约束拒绝第二次写入并返回 skipped 标识

### Requirement 5: 前端 dispatchedMap 与后端同步

**User Story:** As a 审计助理, I want dispatchedMap 在页面加载时自动从后端恢复, so that 分发逻辑的去重判断基于持久化数据而非内存临时状态。

#### Acceptance Criteria

1. WHEN D0-1 组件挂载时, THE useConfirmationDispatch SHALL 调用 Dispatch_API 获取当前 project_id 的全部分发记录并填充 dispatchedMap
2. WHEN executeDispatch 成功写入后端后, THE useConfirmationDispatch SHALL 同步更新本地 dispatchedMap
3. IF 后端 API 返回 skipped 条目, THEN THE useConfirmationDispatch SHALL 将这些条目也标记到 dispatchedMap 中（表示已被其他用户分发）
4. WHILE dispatchedMap 初始化未完成, THE useConfirmationDispatch SHALL 禁用分发按钮并显示加载状态

### Requirement 6: 分发撤回

**User Story:** As a 审计助理, I want 能撤回错误的分发操作, so that 误分发的数据不会污染下游底稿。

#### Acceptance Criteria

1. WHEN 用户请求撤回指定 Dispatch_Record, THE Dispatch_Service SHALL 删除该记录并返回成功
2. WHEN 撤回成功, THE useConfirmationDispatch SHALL 从 dispatchedMap 中移除对应条目，使该行重新出现在待分发列表中
3. THE Dispatch_API SHALL 仅允许 dispatched_by 本人或具有项目管理权限的用户执行撤回操作
4. *(v2)* WHEN 下游底稿已基于分发数据创建了本地行, THE Downstream_Workpaper SHALL 在分发撤回后标记该行为"上游已撤回"供用户决定是否保留

### Requirement 7: 分发事件通知

**User Story:** As a 审计助理, I want 分发操作完成后下游底稿能实时感知, so that 无需手动刷新即可看到新带入的数据。

#### Acceptance Criteria

1. WHEN 分发记录写入成功, THE Dispatch_Service SHALL 通过 EventBus 发布 DISPATCH_CREATED 事件（EventPayload 含 project_id、extra 中含 confirm_index 列表和 target）
2. WHEN 下游底稿组件收到 DISPATCH_CREATED 事件且 target 匹配自身, THE Downstream_Workpaper SHALL 自动拉取新增的分发记录并追加到"从 D0-1 带入"区域
3. WHEN 分发记录被撤回, THE Dispatch_Service SHALL 通过 EventBus 发布 DISPATCH_REVOKED 事件
4. THE Dispatch_Service SHALL 通过 SSE 将事件推送到前端，使同一项目的其他在线用户实时感知分发状态变化
