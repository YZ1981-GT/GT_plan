# 操作日志与最后登录时间 — 任务

- [ ] 1. 迁移 V274/R274 + ORM（User 两列、SysLoginLog、__init__ 登记）+ UserResponse 字段
- [ ] 2. client_ip 服务抽取 + auth_service 登录/登出留痕（独立会话 fail-open）+ /security/login-attempts 改读新表
- [ ] 3. GET /api/system/operation-logs 合并查询端点 + router_registry 注册
- [ ] 4. list_users 返回 last_login 字段
- [ ] 5. log_retention_worker + 三处注册（bindings / names / candidate policy）
- [ ] 6. 前端：apiPaths + OperationLogs.vue + 菜单/路由 + UserManagement 部门与最后登录列
- [ ] 7. 测试：登录成功/失败/锁定留痕、端点 admin 门与筛选、清理函数；后端 pytest + 前端 vitest 相关文件
- [ ] 8. 真库迁移执行 + 浏览器实测（登录后查列表、失败登录留痕、筛选）

## 交付记录（2026-11-27）

- 任务 1~6 全部完成：迁移 V274/R274、ORM（User 两列 + SysLoginLog）、auth_service 留痕（独立会话 fail-open）、`GET /api/system/operation-logs`、list_users 字段、log_retention_worker（三处注册）、前端（apiPaths / OperationLogs.vue / 菜单 / 路由 / UserManagement 部门与最后登录列）。
- 任务 7：后端 10/10（`test_operation_log_and_last_login.py`，隔离 SQLite）+ 审计中间件 29/29 + phase8 安全监控 3 条红按新口径改绿；`TestReportEngineCache` 5 例 HEAD 基线同红（预存，依赖真 Redis）。前端 operationLogs 守卫 7/7 + 用户管理/权限中心 66/66。
- 任务 8（真库 + 浏览器）：
  - 本机库脱钩遗留修复后 V274 落库（schema_version 274 登记、表结构与 users 两列核对通过）。顺带真修 7 条历史失败迁移：V033/V073 补建缺失表、V106 补 service_identities.id 默认值、V253 建空壳表让幂等退役可执行、V261 撞号（库里登记的是 user_allow_manual_edit，rerank 枚举从未提交）补 ADD VALUE 'rerank'、V222/V226 用 build_ledger_query_indexes.py 并发预建三个大索引（38 万/70 万行）。清掉 3 条 version 存文件名的脏行（正常版本行都在）。
  - 真实后端验证：admin 登录 → sys_login_log success 行 + users.last_login_at/ip 更新；故意错密码 401 后 failed 行立即可查（独立会话证据）；登出 logout 行带 user_id；`/api/system/operation-logs` 合并 349+ 条（type=failed 只出登录失败、type=create 只出业务 create、非法 type 422、未登录 401）；`/api/users/` 带 last_login_at。
  - 浏览器实测（node 无头 + 系统 Chrome）：登录成功、菜单 20 项含「操作日志」且点击跳转 `/settings/operation-logs`、用户表「部门」「最后登录」两列、操作日志页标题/类型筛选/表格 20 行数据、筛选「登录失败」生效、console error 0、未登录直连保持 URL（路由守卫由 store 判定，页面接口 401 兜底）。截图 `tmp_operation_log/operation_logs_page.png`。
- 已知边界：失败登录的账号锁定（423）留痕在测试环境验证（共享 Redis 桩），生产 423 路径同一代码分支；`user_agent` 在浏览器实测中记录 UA 原文。
