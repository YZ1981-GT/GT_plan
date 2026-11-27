# 操作日志与最后登录时间 — 设计

## 1. 迁移 V274 / R274

- `users` 加列：`last_login_at TIMESTAMPTZ NULL`、`last_login_ip VARCHAR(45) NULL`（IF NOT EXISTS 幂等）。
- 新表 `sys_login_log`：id UUID PK（应用生成）/ ts TIMESTAMPTZ NOT NULL DEFAULT now() / user_id UUID NULL REFERENCES users(id) ON DELETE SET NULL / username VARCHAR(150) NOT NULL / result VARCHAR(20) NOT NULL / ip VARCHAR(45) NULL / user_agent TEXT NULL；CHECK result ∈ {success, failed, locked, logout}；索引 `idx_sll_ts (ts)`、`idx_sll_user_ts (user_id, ts)`。
- R274：DROP TABLE IF EXISTS sys_login_log + ALTER TABLE users DROP COLUMN IF EXISTS 两列。

## 2. ORM / schema

- `User` 加 `last_login_at`、`last_login_ip`（Mapped 可空；comment）。
- 新 ORM `SysLoginLog` 放 `app/models/core.py`（与 User/Log 同文件，避免新模块），登记进 `models/__init__.py` `__all__`。
- `UserResponse` 加 `last_login_at / last_login_ip`（可空；TokenResponse 用户信息自动带上）。

## 3. 登录/登出写入（auth_service）

- login 签名加 `request: Request`；router 从 FastAPI 注入传入（保持 service 单测可传 stub）。
- 成功路径：请求事务内 `user.last_login_at=now; user.last_login_ip=ip`（随 TokenResponse 由 get_db 关闭时提交——注意：get_db 不自动 commit！**必须显式 `await db.commit()` 在返回 token 前**，这在 login 内是安全的：登录事务只含本次更新）；随后经独立会话 `async_session()` 写 success 行 + fail-open。
- 失败路径（401/423）：HTTPException 抛出前，先经独立会话写 failed/locked 行（fail-open try/except）。**不使用请求事务**——异常路径请求会话未提交，写进去必回滚。
- logout 签名加 `db, request`；先 decode refresh_token 拿 sub（解不出 user_id=None），黑名单逻辑不变，独立会话写 logout 行。
- `security_monitor.record_login_attempt / get_login_attempts` 删除；`GET /security/login-attempts` 改为查 `sys_login_log`（字段 username/ip/success(bool)/timestamp iso），保持既有响应形状。
- IP 提取：复用 audit_log 的 X-Forwarded-For 优先逻辑，抽 `app/services/client_ip.py`（audit_log 中间件与 auth_service 共用）。

## 4. 查询端点（routers/operation_logs.py，自带 /api 前缀）

- `GET /api/system/operation-logs`，`require_role(["admin"])`。
- UNION ALL 两源（PG 与 SQLite 都走 SQLAlchemy Core select union）：
  - login_log：ts→时间；type=result（原值 success/failed/locked/logout）；detail=NULL；user_id/username LEFT JOIN users→full_name；dept 经 users.dept_id LEFT JOIN sys_dept.name。
  - logs：created_at→时间；type=action_type；detail=object_type(+object_id 截断)；user_id JOIN users；dept 同上。
- 筛选下推：from/to/keyword(账号/人名 ILIKE)/type(白名单映射到具体过滤：login 系→login_log.result IN；create/update/delete→logs.action_type)/dept_id。
- 排序 created_at DESC；offset/limit 分页；`total` 用同条件 count（union 子查询外层 count）。SQLite 无 ILIKE ⇒ 用 lower(col) LIKE lower(:kw)（两库通用）。
- 响应行：{id, ts, type, result?, detail, user_id, full_name, username, dept_name, ip}。
- 注册：`router_registry/system.py` §8 后追加 include（自带前缀，直接注册）。

## 5. 用户列表

`list_users` 每行加 `"last_login_at": isoformat or None, "last_login_ip"`（dict 返回，直接加键）。

## 6. 清理 worker（app/workers/log_retention_worker.py）

- 模式复用 export_cleanup_worker：30s 心跳、86400s 业务间隔、启动即跑一次、leader lock。
- 删除 `sys_login_log.ts < now-180d` 与 `logs.created_at < now-365d`，各 limit 5000/轮。
- 注册：`_WORKER_BINDINGS` + `WORKER_TASK_NAMES`（两处同步）；`CANDIDATE_MODE_POLICY["log_retention_worker"]=("skip","writes_shared_state")`（skip 集合经 WORKER_TASK_NAMES 自动覆盖，EXPECTED_SKIP 无需手改）。

## 7. 前端

- `apiPaths/system.ts` 加 `operationLogs: { list: '/api/system/operation-logs' }`。
- 新页 `views/OperationLogs.vue`：GtPageHeader + 筛选栏（el-date-picker range / el-input / el-select 类型 / el-select 部门复用 listDepartments）+ el-table + el-pagination；取数 `api.get`（经 apiProxy，信封已解包）；失败行 el-tag type=danger。
- 菜单：`ThreeColumnLayout.vue` FALLBACK_NAV 在 departments 后加 `{ key:'operation-logs', label:'操作日志', icon: Document, path:'/settings/operation-logs', maturity:'production', roles:['admin'] }`（Document 已导入）。
- 路由：`router/domains/system.ts` 加 `{ path:'settings/operation-logs', name:'OperationLogs', component:()=>import('@/views/OperationLogs.vue'), meta:{permission:'admin'} }`。
- UserManagement.vue：状态列后加「部门」（dept_id→departments.name 映射）与「最后登录」（fmtDateTime，空显示「从未登录」）列；后端已返回 dept_id 与部门列表已在加载，不加请求。

## 8. 权衡

- 不把登录写进 audit_log_entries 哈希链（高频写会锁链尾；登录无需防篡改证明）。
- logs 保留 365 而非 180：`workhours.py`/`wp_batch_router.py` 按 action_type 查编辑时间段，删 180 天前的编辑记录会断工时审计。
- 分页在 SQL 层做，不整表拉内存（日志表会很大）。
