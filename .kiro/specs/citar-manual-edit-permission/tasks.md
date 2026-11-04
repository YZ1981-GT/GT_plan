# 任务：账号「允许修改」开关

- [x] 1 V261 / R261 + ORM + schema + 用户接口（列表 / 修改 / me）+ 审计；V261 已用 `MigrationRunner.run_pending` 落本地库（6 个账号全为允许）
- [x] 2 `manual_edit_permission` + 七个人工修改接口拦截 + `save_sheet_inputs` 按格比对（`is_auto_cell`：公式格、非「需人工填写」的取数格、样表数字常量）
- [x] 3 后端测试：税审底稿按格比对（含手工清空成 null）、鉴证报告三接口 + 申报表、审定报表、余额表 / 序时账、用户接口（PG）
- [x] 4 前端：`useManualEditPermission` + 用户管理「允许修改」列 + `TaxWorkpaperGrid.manualEdit`（`withDefaults` 默认 true）与底稿 / 申报表页 + 报告正文金额 / 审核说明 / 审定报表 / 单体报表 / 余额表 / 序时账 / 试算表入口 + CitarLayout 进入项目重读账号信息
- [x] 5 前端测试：用户管理开关 2 例、表格组件可点范围 2 例
- [x] 6 回归与实测
  - 后端：改动模块 6 个测试文件 72 passed（含 PG 用户接口）；鉴权基线守卫 + 底稿接口 49 passed；磁盘变异 8 条全部打红（首轮「是否存在」判断存活 —— 只比值时手工清空成 null 与缺省相等，补用例后打红）
  - 前端：CITAR / 税审底稿 / 申报表 / 用户管理 / stores 17 个文件 126 passed；单区域 vue-tsc（`tsconfig._manual-edit-permission.json`）0 错误，注入 TS2322 能报出；ESLint 0 错误（1 条既有 toFixed 警告，未改该行）；行数门通过
  - 浏览器实测（真后端 + ABC餐饮_2025，admin）：账号权限页关开关 → 本人账号信息即时变为关闭；税审底稿 2-02 公式格 23 个全部不可点、可点格 71 → 36、点公式格不出编辑框；报告正文金额只读、审核说明无修改 / 删除、审定报表 / 单体报表金额不可点、余额表无修改、试算表审定数不弹窗；后端报表手工值 / 审核说明 403；打开后底稿可点格恢复 71。实测后开关已复原为允许，页面无报错
  - 实测抓到 1 处：`manualEdit` 是布尔 prop，父组件不传时 Vue 转成 false ⇒ 改 `withDefaults(..., { manualEdit: true })`（单测「缺省可点」先打红）
