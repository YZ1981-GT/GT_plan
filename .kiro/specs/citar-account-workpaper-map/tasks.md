# 任务：底稿映射页「科目 → 税审底稿」页签

- [x] 1. 执行器 `RuleResult.nodes` / `RuleResult.scope` + 执行器测试（取数匹配本身不变；`tops(loose=False)` 只给 scope 用）
- [x] 2. service `account_workpaper_map`（与 `evaluate_keys` 共用 `_prepare_inputs` / `_make_runner`）+ 接口 `GET /tax-workpapers/account-map` + 接口测试（上下级 / 三级科目、未取到 + 原因、申报表域不算、鉴权）+ 跨语言编号守卫
- [x] 3. 前端：`taxWorkpaperIndex.ts` 上次打开的表存取 + `TaxWorkpaperView` 改用；apiPaths；`CitarWorkpaperMapTab.vue`（含隐藏标为「无」的底稿）；`CitarAccountMapping.vue` 两个页签 + 联动刷新
- [x] 4. eslint / stylelint / 单区域 vue-tsc（`tsconfig._account-workpaper-map.json`，注入 TS2322 能报出）；后端回归 136 passed（税审底稿 / 公式引擎 / 鉴证报告规则与接口 / 鉴权基线 / 函数全局名棘轮）；隔离副本磁盘变异 14 条全部打红、无害对照存活
- [x] 5. 真库核对（四川医药 2025，只读）+ 浏览器实测（无头 Chromium，admin）：两个页签、筛选（底稿 / 未进底稿 / 关键字 / 只看有余额）、切页签不重读、改映射后重读（保存请求被拦截不写库，事后查库原值未变）、点底稿打开税审底稿 3-07-02、控制台 0 错误

## 验收摘要
- 四川医药 2025：287 个客户科目，有余额或发生额 158 个，其中 67 个进入税审底稿、23 个规则指向底稿但没取到数（主营业务成本 → 2-04「未找到明细科目销售商品」、固定资产 → 3-03-01「未找到明细科目房屋建筑物」等）；接口 1.0~2.7 s。
- 未改：取数兜底包含匹配让「借款」同时进短期 / 长期借款表；该项目映射错位待重新导入（design §6）。
