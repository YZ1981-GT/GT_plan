# 设计：账号「允许修改」开关

## 1 存储与接口

- V261 / R261：`users.allow_manual_edit BOOLEAN NOT NULL DEFAULT TRUE`；ORM `User.allow_manual_edit`。
- `UserUpdate.allow_manual_edit: bool | None`（显式 null 视为不改）；`UserResponse.allow_manual_edit`（登录、`/api/users/me` 都带）；`GET /api/users/` 每行带。变化记进 `user.security_changed` 审计。
- 判定单一来源 `app/services/manual_edit_permission.py`：`manual_edit_allowed(user)`、`assert_manual_edit(user)`（403 + 中文提示）。

## 2 后端拦截

- 只做人工修改的接口，处理函数首句 `assert_manual_edit`：`PUT tax-assurance/report-body/amounts`、`PUT tax-assurance/review-notes`、`PUT tax-assurance/financial-statements`、`PUT /api/reports/{pid}/{year}/manual`、`PUT ledger/balance-rows/{id}`、`PUT ledger/entries/{id}`、`POST ledger/{table}/{id}/restore`。
- 税审底稿 / 申报表 `PUT sheets/{code}` 是手填与人工修改混在一起的整表替换：`save_sheet_inputs(..., allow_manual_edit)` 未开通时，比对本表已存值与提交值，「自动生成的格」（公式格、规则状态不是 manual 的取数格、样表数字常量）有新增 / 删除 / 改值即 403，点名格子；其余格照常。他人手工值原样提交 = 未改动，放行（R4）。
- 项目级鉴权不变（仍是 `require_project_access("edit")`），本开关只在其上再收一道。

## 3 前端

- `UserProfile.allow_manual_edit`；`composables/useManualEditPermission.ts`：`canManualEdit`（缺省视为允许，兼容旧会话）+ `refreshCurrentUser()`（`_silent`、`_dedupe: false` 读 `/api/users/me`）；`CitarLayout` 挂载时调一次（R5）。
- 用户管理「允许修改」列：`el-switch` + `before-change` 调 `updateUser(id, {allow_manual_edit})`，成功才翻转；改的是自己时刷新本人账号信息。
- `TaxWorkpaperGrid` 新 prop `manualEdit`（默认 true）：false 时公式格、预置值、自动取数格不可点、不显示「恢复自动值」，与后端同一口径。底稿页 / 申报表页传入。
- 报告正文金额、审核说明、审定报表、单体财务报表、科目余额表、序时账、试算表：`canManualEdit` 为假时不给修改入口，提示「账号未开通修改」。

## 4 不做

- 不改项目成员权限级别与角色矩阵；不按项目单独配置（账号级一个开关）。
- 调整分录、科目映射、导入、生成报表不受本开关控制（R3）。

## 5 修订：整表只读（需求 R2′ / R2″ / R3′）

- 后端：去掉 `save_sheet_inputs` 的按格比对（`is_auto_cell` / `_auto_cell_changes` / `allow_manual_edit` 参数），改为路由层整表拦截。新增拦截点：`PUT tax-workpapers/sheets/{code}`、`PUT tax-workpapers/params`、`PUT tax-assurance/tax-return/sheets/{code}`（含 TR-FORMS 是否填报）、`PUT tax-assurance/report-body`（报告日期）、`POST/PUT/DELETE adjustments`、`POST adjustments/batch-delete`、`POST import-templates/adjustments/import`、`POST/PUT mapping`、`POST mapping/batch-confirm`、`POST mapping/auto-match`。复核 / 撤回复核、账套导入内部的自动匹配（走 service，不经接口）不拦。
- 前端：`TaxWorkpaperGrid.canEdit = manualEdit && !readonly && 有 ref`（不再分格子类型），关闭时提示只保留数据来源说明；底稿 / 申报表工具栏隐藏导入 / 放弃修改 / 保存，图例去掉「可点击修改」；表头信息不给「编辑」按钮只显示摘要；是否填报勾选框换成 √；报告日期显示文字；摘录表金额去掉文本光标；调整分录隐藏导入 / 增加 / 编辑 / 删除（`CitarAdjustmentCard.canEdit`，`withDefaults` 默认 true）；科目映射隐藏智能匹配 / 保存 / 修改、未映射行显示「未映射」；各页头部说明里的「可修改」字样随开关隐藏。
- 范围外：主平台（非 CITAR）调整分录 / 科目映射页面未做界面隐藏，未开通账号在那里点保存会收到 403 提示。
