# 操作日志与最后登录时间 — 需求

> 用户四点确认（2026-11-27）：①失败登录要记录 ②保留 180 天 ③操作日志页带类型筛选（登录/退出/新建项目等）④页面叫「操作日志」。
> 附带：权限管理账号列表显示最后登录时间；左侧菜单新增「操作日志」（admin）。

## 背景

- `users` 表无最后登录时间字段；`auth_service.login` 成功后不写任何记录。
- `GET /api/security/login-attempts` 读内存列表，`record_login_attempt` 全仓只有测试调用 ⇒ 恒空、重启即丢。
- 写操作已有 `AuditLogMiddleware` 落 `logs` 表（2xx、POST/PUT/PATCH/DELETE），但没有任何查询端点/页面。
- 登录失败会走 FastAPI 异常处理，请求事务不提交 ⇒ 失败日志必须独立会话提交。

## 需求

### R1 登录留痕（含失败）
1. 登录成功：更新 `users.last_login_at / last_login_ip`（请求事务内），并在 `sys_login_log` 写 `result=success`（独立会话）。
2. 密码错误（含账号不存在，统一 401 文案）：写 `result=failed`。
3. 账号锁定（423）：写 `result=locked`。
4. 登出：按 refresh_token 解出用户，写 `result=logout`；解不出（已失效 token）记 `user_id=NULL`。
5. 日志写入 fail-open：登录/登出主流程不因日志失败失败；失败记 CRITICAL。
6. 刷新令牌（refresh）不算登录，不更新最后登录时间。

### R2 数据与保留
1. 新表 `sys_login_log`：id/ts/user_id(可空)/username/result/ip/user_agent；索引 (ts)、(user_id, ts)。
2. 保留期：`sys_login_log` 180 天、`logs` 365 天（settings 可调），后台 worker 每日清理；logs 有既有消费方（工时/编辑时间段），保留期必须 ≥ 365 默认。
3. `users` 加列 `last_login_at` / `last_login_ip`（可空，存量 NULL）。

### R3 查询接口
1. `GET /api/system/operation-logs`：仅 admin；合并 `sys_login_log` 与 `logs`，统一投影（时间/类型/结果/人名/账号/部门/IP/对象）。
2. 服务端分页（page/page_size≤200）；筛选：时间范围、关键字（账号/人名）、类型（login_success/login_failed/login_locked/logout/create/update/delete）、部门。
3. `GET /api/users/` 响应增加 `last_login_at / last_login_ip`。

### R4 前端
1. 权限管理「账号权限」表：新增「部门」「最后登录」列；从未登录显示「从未登录」；部门名用已加载的部门列表映射（不新增请求）。
2. 左侧菜单「部门管理」后新增「操作日志」（`/settings/operation-logs`，仅 admin，路由 meta.permission=admin）。
3. 操作日志页：筛选栏（时间范围/关键字/类型/部门）+ 表格 + 分页；登录失败/锁定行结果列红色标识。
4. 全部用户可见文案中文；时间经 `fmtDateTime`。

## 验收要点
- 失败登录在 401 响应后仍能在库里查到（独立会话证据）。
- 类型筛选「新建」只返回 logs 的 create；「登录失败」只返回 login_log 的 failed。
- 非 admin 访问接口/页面 401/403。
- 清理函数只删超期行。
