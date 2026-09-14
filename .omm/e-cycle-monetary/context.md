# 上下文：E1 承载的全局机制

渲染链路、持久化、跨底稿事件、共享能力与 D 循环完全一致 → 见 `.omm/d-cycle-sales/context.md`
与 `.omm/d-cycle-sales/shared-runtime/`。本文只写 **E1 特有 / E1 首发** 的部分。

## 1. 四表取数（E1 是 pilot，后推广到 D 循环）

后端 `_e1_monetary_fund.py::_build_four_table_prefill`：
从 `tb_balance` **叶子子科目**提取（`_is_leaf` = 该 code 不是任何其它 code 的前缀，防父子双算；过滤全零空账户），
资产借方口径 增加=`debit_amount` / 减少=`credit_amount` / 期末=`closing_balance`，
每行附 `source` + `TB('code','期末余额')` 公式，输出 `html_data.four_table_prefill = {cash(1001), bank(1002), other(1012), account_list}`。

前端 `e1FourTablePrefill.ts`（纯函数）映射到各 composable 的行 schema，
主入口 `onMounted` **persist-first 种子**（仅当 rows 键缺失才 seed，内存态；未编辑不落库），
并额外 seed **跨 sheet 聚合键**（供 E1-1 审定表在未打开明细 tab 时也能取数）。
`E1FourTableSourcePanel.vue` 在 E1-2/E1-3/E1-10 顶部展示来源科目 + TB 公式 + 🔄重新取数。

## 2. 审定表的 TB 核对走「报表规则映射」而非硬编码前缀

审定表核对科目取自 `report_config` 的报表行公式（货币资金 BS-002 = `TB('1001')+TB('1002')+TB('1012')`，
项目级可覆盖 = 企业自定义口径单一真源），后端 `report_account_mapping.resolve_report_line_account_codes(db, pid, row_code, fallback)`
解析，`build_trial_balance_code_filter` 生成参数化过滤，并把 `project_context.tb_source_codes` 输出供追溯。
若项目映射含明细未覆盖的科目 → 差异会如实暴露"明细漏报表口径科目"（正确的审计行为）。

## 3. 金额显示偏好（平台级，E1 首个全面消费）

`stores/displayPrefs.ts` 的 `fmtAmount()` 是**平台唯一金额格式真源**（千分符 + 两位小数 + 单位默认**元**，
localStorage `gt_display_prefs` 持久化，切换实时响应全平台）。
只读金额一律 `displayPrefs.fmtAmount()`；可编辑金额用共享 `composables/wpAmountInput.ts` 的 formatter/parser
（Element Plus 的 `el-input-number` **不支持 `:formatter`**，要千分符必须用 `el-input` + formatter/parser）。
防折行由 `styles/global.css` 的 `.el-table td.is-right .cell{white-space:nowrap;font-variant-numeric:tabular-nums}` 全局兜底。

## 4. 公式管理 surfacing（E1 是试点，后铺到 D~N）

专属组件的数据存 `checklist_responses` 而非网格，故中央公式库无记录；
后端 `wp_formula.py::_build_surfaced_formulas` 把 E1 各 sheet 的取数/计算/勾稽公式作为**只读 surfaced 条目**暴露给公式管理中心
（E1 共 65 条，E1-1 审定表 13 条含跨 sheet `WP('E1-x',...)` 取数 + 表间计算 + TB 核对）。
每条带 `sheet_codes` 归属，前端按选中 sheet 过滤（否则工作簿级全量会在每个 sheet 重复显示）。

## 5. 双模式统一封装（E1 与 B1 同期收敛）

`composables/useWpDualMode.ts`：health 双层解析 `res?.data?.healthy ?? res?.healthy`，
不健康时摘掉「在线编辑」并回退结构化，切到 OnlyOffice 前 flush 未保存内容。
E1 全部 sheet 都显示工具栏（结构化视图 / 在线编辑 + 版本历史 + 📖编制手册 / 使用手册），
`sheet-name` 直接用 `props.sheetName`（E1 的 sheet 名就是真实 xlsx tab 名，无需 resolve）。

## 6. 目录页范式（E1 是 E1 标准的定义者）

`E1TabDirectory` = 目录卡（标题 + 复核 + 编制/使用手册按钮 + 进度条 → 跨表结论口径看板 → 编制提示）
+ `GtBArchitectureTree` 4 阶段泳道 + 本循环底稿目录 grid（`loadCycleWorkpaperCards`，源模板 canonical 清单）。
这套结构后来被逐科目铺到 D/H/I/J/K/L/M/N 全部目录页。
