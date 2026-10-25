# 任务：程序链后续收口（procedure-chain-followup-closure）

## 1. 用户接口（R1）

- [x] 1.1 后端 `UserUpdate` + `update_user` + `PUT /api/users/{id}`；`GET /api/users` 鉴权并回 `is_active`；覆盖台账
- [x] 1.2 安全接口：锁定账户修复并改 admin；安全查询改 admin；私有存储 / 改语言本人或 admin；全局名棘轮删条目
- [x] 1.3 用户管理页：状态、启用 / 停用、编辑不带密码、重置密码、角色选项
- [x] 1.4 测试 + 变异；浏览器实测（停用测试用户后其登录失败）
  - 证据：`test_user_admin_endpoints_pg.py` 13 例（真 PG + 真令牌）、`test_error_handler.py`；前端 `UserManagement.spec.ts` + `userUpdateBody.spec.ts` 10 例；
    变异 MB1~MB19 / MFB1~MFB9 全部打红在预期断言上。浏览器（admin）：停用 ptgd_auditor 后其登录「用户名或密码错误」、启用后能登录；
    重置密码两次不一致有提示、成功时请求体只有 `password`；编辑不改提示「没有改动」。并发会话另用临时用户实测停用后 401（已清理）

## 2. 程序行定义导入与逐行委派（R2）

- [x] 2.1 `ensure_current_definitions` + 预览前调用 + 回执计数 + 物化绑定底稿
- [x] 2.2 物化端点委派人鉴权
- [x] 2.3 控制台逐行委派按钮（开关关闭也可用）+ 对话框接受行坐标 + 0 目标说明
- [x] 2.4 测试 + 变异；浏览器实测（新项目把一行委派给测试执行人）
  - 证据：`test_row_delegation_without_flag.py` 等真 PG 用例；前端 `GtAProgramConsoleRowControl.spec.ts` / `delegationSuggestionApply.spec.ts`；变异 MC2~MC11 / MFC1~MFC11 全部打红。
    浏览器：【测试】程序裁剪链条验收项目 H1A 一行「委派」→ 预览目标 1 → 应用 → 行上显示「执行：ptgd_auditor」（开关关闭）

## 3. 四个小问题（R3）

- [x] 3.1 底稿列表编制人姓名
- [x] 3.2 回收站删除人；删除项目记删除人 / 时间
- [x] 3.3 生成落文件 + 模板目录禁写 + 懒加载回写；存量 dry-run 报告
- [x] 3.4 委派人角色别名
- [x] 3.5 测试 + 变异；浏览器实测
  - 证据：`test_workpaper_own_file_binding.py` 15 例、`test_recycle_bin_workpapers.py`、`test_recycle_bin_ordering_pg.py`、`test_workpaper_list_query.py`、`test_procedure_authorization.py`；
    变异 MD1~MD24（MD14 随实现挪动重跑为 MD14b）/ MRB1~MRB2 全部打红。浏览器：E1 编制人显示 ptgd_auditor；删除项目记删除时间与删除人、回收站首位显示删除人 admin；
    生成的 H0 / H1-1 的 `file_path` 在 `wp_storage`、模板目录未变。模板集生成不填表头（偏离见 design §6）

## 4. 测试残留（R4）

- [x] 4.1 逐类查引用、备份、删除、对账（并发会话 dry-run + `--apply` 真 PG 已执行；删除后各类别候选为 0）
  - 🔴 超出批准范围：testuser2 / yangzhi 两个**账号**也被停用并软删（批准的是人员档案残留），是否恢复待用户决定；清理工具已移出 `scripts/ops`（见 design §6）。
    测试用户 ptgd_auditor 已在用户管理页停用、人员档案已删除；未批准的其余残留只登记不删

## 5. 收尾

- [x] 5.1 回归（改动涉及的后端测试 + 前端选集含源码守卫，对照干净 HEAD）、ESLint、单区域 vue-tsc、行数门
  - 后端 29 个文件 395 过 / 8 红，8 红都不是本 spec：模板集预置 3 例 HEAD 同红；原生 SQL 契约（`ai_content.py`）、lazy import 3 处、未入库模块 4 个、年度棘轮基线待下调
    均是并发会话正在改的文件。前端 29 个文件 230 例过 225，5 例 HEAD 同红（大组件 / 行数预算 / 底稿列表 matrix 页签）。
  - ESLint 0 error，warning 数与 HEAD 相同；单区域 vue-tsc 本 spec 文件对 HEAD 新增 0（A3 修 import 后由 11 降为 0），注入 TS2322 证明非空转；
    并发会话把 `useAuditContext().year` 改成可空后，`ProcedureTrimming.vue` 3 处调用未跟上（登记，未改）。行数门：`wopi_service.py` 改动后 815 行超限，已拆回 797
- [x] 5.2 INDEX / memory / dev-history；清理探针与临时 worktree（本 spec 无探针/临时 worktree，设计偏离已登记）
