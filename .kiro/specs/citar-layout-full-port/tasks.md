# 任务：CITAR demo 排版样式全量移植

- [x] 1. 数据与样式转写：`report-lines` / `standard-accounts` 转 TS（`src/citar/data/`）；CITAR CSS 转写到 `src/citar/styles/`，字面量换 `citar-tokens.css` 同值变量（42 色 + 10 字号）
- [x] 2. 布局：`citarRoutes.ts`（路径判定单一来源）+ `CitarLayout.vue`（顶栏 / 项目信息行 / 一级栏 / 内容区）+ `DefaultLayout` 分支
- [x] 3. 项目列表 `CitarProjectList.vue`（浏览 / 删除 / 修改三态 + 确认弹层，接 `GET /api/projects`、`POST /api/projects/batch-delete`）
- [x] 4. 项目空页 `CitarProjectHome.vue` + 鉴证报告待开发页 `CitarPendingNode.vue`
- [x] 5. 账套导入 / 未审账套、报表 / 调整分录 / 审定科目余额表、审定报表 四页（`src/citar/screens/`）
- [x] 6. 税务底稿接入 CITAR 框架（目录开合经 `CITAR_SUBNAV_OPEN_KEY`，去掉负边距）
- [x] 7. 路由切换（`Projects` / `LedgerImport` / `TrialBalance` / `Adjustments` / `Reports` / `DisclosureNotes` 换 component，新增 `CitarProjectHome`；`WorkpaperList` 上一轮已换）
- [x] 8. stylelint / eslint 通过；单区域 vue-tsc 通过，注入 TS2322 能报出
- [x] 9. Playwright 逐页实测：列表、删除 / 修改模式（只进模式未真删）、进项目、六个菜单、目录开合、返回、项目列表、新建页顶栏、账号权限仍为三栏；控制台 0 错误

## 交付备注
- 路由 / 布局回归 5 个文件 19/20 通过；失败的 `ThreeColumnLayoutFormulaRuntime.spec.ts` 是测试自身的 `vue-router` mock 缺 `createRouter`（链路 ThreeColumnLayout → openLedgerWindow → router/index.ts，三个文件本次均未改动）。在 HEAD 干净 worktree 复跑时 vitest 报内部错误「failed to find the current suite」，未能在 HEAD 上复现同一失败形态。
- 未提交。
