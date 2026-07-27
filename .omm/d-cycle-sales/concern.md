# 关注点 / 已知脆弱处

## 1. 跨表键漂移（本循环最高频缺陷类型）

消费端读的 `item_id` 与生产端实际写入的键不一致 → 静默返 0 / 恒显"一致" / 带入为空。已在 D 循环各科目反复出现过，典型形态：

- 读 `Dx-1-audited-total` 但生产端只写 `Dx-1-rows`
- 读计算列字段（`endBalance`）但存储只有原始录入字段（期初/借/贷）
- 前端存 `Dx-2-detail-rows` 而后端导入导出写 `Dx-2-rows`

排查方法：对照两端源码的确切键名 + 存储字段（`remark` vs `conclusion`），不看功能声明。

## 2. 四表取数覆盖率有天花板

`d-cycle-four-table-extraction-formulas` 的结论：D1/D2/D3/D4/D5/D7 的审定表分类行是
**按信用风险组合 / 性质+账龄 / 产品 / 类别派生的 SUMIF 行**，而 `trial_balance` 只有科目总额、
没有对应维度 → **宁缺勿造，不 seed**；只有 D6 合同资产 block1 原值动态行能从 `tb_balance` 叶子干净 seed。

灰度开关 `D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED` 默认关闭，开关开/关时 render 输出逐字节等价。

## 3. 双模式（结构化 / OnlyOffice 在线编辑）易假可用

正确范式：切 OnlyOffice 前先 `GET .../onlyoffice-config` **拉取成功才切**，失败回退结构化。
两个反复踩的坑：

- `el-segmented` 用 `v-model` 会抢先改值，使 `switchMode` 的守卫短路 → 健康门控失效，必须 `:model-value` + `@change`
- 健康检查/config 请求要带鉴权（`http.get` 而非裸 `fetch`），`onlyoffice-config` 必带 `project_id` query

## 4. 附注章节号必须精确匹配

纯编号章节（如 `五、4`）判定一律 `===`，用 `startsWith` 会串到 `五、40`~`五、49`。
D1 = `五、4` / `八、4`，D2 = `五、5` / `八、5`（权威源 `note_template_variant_matrix.json`）。
披露 sheet 名各科目命名不统一（半角/全角括号都有），必须核对 `workpaper_sheet_classification` 真实 tab 名。

## 5. 整册专属组件的两类"Vite 200 但运行时全崩"

- 主入口未 `provide` 子 tab `inject` 的共享 formData → 全模块 ErrorBoundary
- props 声明为 `Ref<>` 但父级模板绑定会自动解包 → `props.x.value` 为 undefined 崩溃

两者 `get_diagnostics` 与 Vite transform 都查不出，只有浏览器实测能抓。
