# ADR-030: 临时授权使用独立新表

## 状态

已接受 (2026-06-07)

## 上下文

平台需要支持临时授权（Temporary Grants）功能：项目经理或合伙人可授予特定用户
在有限时间内执行某些操作的权限（如 archived 项目的紧急解锁、代理复核等）。

需要决定临时授权数据的存储方案：

### 方案 A：复用现有 `app_audit_log`

- 优点：无需新表，减少 schema 膨胀
- 缺点：
  - `app_audit_log` 是 best-effort 操作流水（可丢失），不适合作为权限判断依据
  - 缺少 `expires_at`、`grantee`、`approver`、`is_active` 等业务字段
  - 查询活跃授权需复杂 JSONB 过滤，性能差
  - 混合用途导致表语义不清晰
  - 不支持高效的"是否有有效授权"查询（每次写操作都需判断）

### 方案 B：独立新表 `temporary_grants`

- 优点：
  - 专用表结构，字段语义清晰
  - `expires_at` + `is_active` 支持高效索引查询
  - 与 `app_audit_log` 解耦（授权记录 ≠ 操作审计）
  - 可独立设置 TTL 清理策略
  - Service 层 `can()` 判断只需简单 WHERE 查询
- 缺点：新增一张表（可接受）

### 方案 C：复用哈希链 `audit_log_entries`

- 不适用：哈希链是不可变追加式，无法标记"已过期/已撤销"

## 决策

**选择方案 B：独立新表 `temporary_grants`**

理由：
1. 临时授权是运行时权限判断依据，需要高效的"是否有效"查询
2. 审计日志是 best-effort 流水记录，语义完全不同
3. 独立表支持 `is_active` 状态管理（撤销、过期自动失效）
4. 审计日志记录（grant/use/expire 事件）仍写入 `app_audit_log`，两者互补

## 表结构概要

```sql
CREATE TABLE temporary_grants (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL,
    operation_code VARCHAR(64) NOT NULL,
    grantee UUID NOT NULL,         -- 被授权人
    approver UUID NOT NULL,        -- 审批人
    reason TEXT NOT NULL,           -- 授权原因
    expires_at TIMESTAMPTZ NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

## 后果

- 新增 V060 迁移文件
- 新增 ORM 模型 `TemporaryGrant`
- `permission_matrix_service.can()` 需扩展：先查静态矩阵，再查临时授权
- 授权/使用/过期事件写入 `app_audit_log`（action: `temp_grant:create`/`temp_grant:use`/`temp_grant:expire`）
- 定时任务或查询时惰性标记过期授权 `is_active=FALSE`
