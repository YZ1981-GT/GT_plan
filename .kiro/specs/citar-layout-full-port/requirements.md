# 需求：CITAR demo 排版样式全量移植

来源：用户 2026-11-02「把 CITAR demo 平台里面的排版布局、样式都全量拿过来，从项目列表展示到点进去项目展示，以及点击每个菜单右边的展示都全量拿过来」。
参照源：`C:\Users\baiji\Desktop\文件\税务平台\税审AI作业平台\税审AI作业平台\CITAR\src`（React，只读参照）。

## R1 项目列表（CITAR `ProjectListScreen`）
- 顶栏：左 LOGO，右当前用户名 + 「退出登录」；无一级侧栏、无中栏。
- 工具条：标题「项目列表」+ 「共 N 个项目」；按钮「项目导入」「项目导出」（置灰，本期未开放）、「删除项目」「修改项目」「新建项目」。
- 卡片列表：项目名 + 项目类型标签 + 小微企业 / 税收优惠标签；第二行「客户：」「审核年度：」；右侧状态牌 + 更新时间。
- 删除模式多选 → 确认弹层列出项目名；修改模式单选 → 进入修改页。
- 数据来自本平台 `GET /api/projects`；删除走既有 `POST /api/projects/batch-delete`（软删除进回收站，提示文案按真实行为写，不照抄 CITAR「不可恢复」）；新建 / 修改进入既有建项向导（`/projects/new`、`?projectId=`）。

## R2 项目内框架（CITAR `ProjectShell`）
- 第一行：LOGO + 用户名 + 「项目列表」「退出登录」。
- 第二行（浅紫底）：项目简称、审核年度、签字合伙人、项目经理、现场负责人（无数据显示「—」）；进入环节后右侧显示「← 返回」，回到项目空页。
- 左侧一级栏六项：账套导入 / 未审账套、报表 / 调整分录 / 审定科目余额表、审定报表 / 税务底稿（带展开标记） / 鉴证报告。
- 税务底稿：右侧弹出二级栏「底稿目录」；已在税务底稿时再点只开合目录。
- 点项目卡片先进项目空页「请从左侧选择要进入的环节」。

## R3 各菜单内容区（CITAR `part2` / `part3`）
- 账套导入 = `DataImportScreen`；未审账套、报表 = `UnauditedScreen`；调整分录 = `AdjustmentScreen`；审定科目余额表、审定报表 = `AuditedScreen`（含底稿取数余额表 633 科目）；税务底稿 = 已移植的 `TaxWorkpaperView`；鉴证报告 = 「该环节界面待开发」。
- 版式、文案、交互与 CITAR 一致；CITAR 中未实装（置灰 / 不存盘）的按钮在此同样未实装。

## R4 约束
- 原有页面文件（`Projects.vue` / `LedgerImportPage.vue` / `TrialBalance.vue` / `Adjustments.vue` / `ReportView.vue` / `DisclosureEditor.vue` / `WorkpaperList.vue`）不删，只改路由指向，可逐项改回。
- 路由名不变（既有 `router.push({ name })` 不受影响）；非这六个菜单的项目子页面仍走原三栏布局。
- 管理员的「账号权限」入口保留（CITAR 无此入口，移到顶栏按钮）。
- 通过 stylelint（禁 `color/background` 十六进制、`font-size` px 字面量）、eslint、单区域 vue-tsc；Playwright 实测每个页面。
