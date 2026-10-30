# 附注链后续优化 — 设计

## 1. 现状实证（2026-10-29，远端 `9f1cb9c7b`）

| 事实 | 证据 |
|---|---|
| 离屏 78/78、M 自动同步、`五、42` 写权、G7 清册已由 `note-pull-residual-governance-closure` 交付 | `9f1cb9c7b` 提交与其 tasks 50/50 |
| 真库 73 条附注存 `sub_table_data`（全部 workpaper 来源），其中只有 1 条同时存旧 `_tables` | PG 只读统计 |
| 公式执行 / 列表 / 目标 / 校验 / 覆盖率都走 `iter_note_tables(td)`：有 `_tables` 用存储表，否则顶层 | `note_formula_tables.iter_note_tables` 及 6 个调用方 |
| 编辑器与 Word 导出显示 `effective_table_data`：workpaper 来源按 `sub_table_data` 投影并替换 `_tables` | `note_content_utils.effective_table_data`、`note_sub_table_projector.project_sub_tables` |
| 探针：【测试】OO公式重算验收 `八、5` 存储视图 1 表 0 行 0 条预设，显示视图 5 表 19 条；和平药房 `八、5` 存储 15 张隐藏旧表 35 条，显示 7 表 19 条 | 仓库外只读探针 |
| 前端对投影格不打人工标记（底稿是这些表的权威） | `noteTableWriteback.ownCellModes` |
| 单元格溯源 `GET /disclosure-notes/{note_id}/cells/{r}/{c}/trace` 只读第 1 张表的 binding | `disclosure_trace.trace_cell` |
| 同名行：读取层只有全表 `_occurrence`；结构指纹不含 occurrence / `_pushed_row_id` | `consol_note_standalone_reader`、`consol_note_detail_source_service` |
| 建议对同名多行按第 k 个同名模板行配对，`exact` 可被自动确认 ⇒ 跨组错配可静默确认 | `consol_note_detail_suggest._split_repeated_labels` |
| 标题行库覆盖率 soe 0.9418（631/670）、listed 0.95（836/880）；可修项 soe B1 6 / B2 6 / C 3，listed B1 6 / B2 7 | 库文件 stats + 逐列核对 |
| `DisclosureEditor.vue` 13 个根节点；`CommentTooltip` 无批注时渲染片段根，外层 `el-tooltip` 触发属性丢失 | 模板现读 + Vue 告警 |

## 2. 架构裁决

### ADR-1 公式只有一个视图

新增 `note_formula_tables.formula_view(td)`：底稿来源且投影非空 ⇒ 显示视图；否则原样返回存储。公式的列表、目标、校验、执行、覆盖率
全部经它取表，杜绝「看到 A 表、算 B 表」。不改 `iter_note_tables` 本身（下推行守卫仍按存储表判定）。

### ADR-2 投影表写回来源、底稿值优先

投影表的格写回 `sub_table_data[_source_sub_table_key][_source_row_indexes[r]][值列键]`，值列键与投影同一函数产出
（`note_sub_table_projector.projected_value_keys`）。预设公式在投影表上只补空格；底稿值与公式不一致时不改、记差异（`anomalies`）。
用户公式照常覆盖，结果标 `overrode_workpaper`。理由：投影格没有人工标记，底稿是数值权威；预设合计与 builder 合计同源时结果相同，
不同则应提示核对而不是静默改数。

### ADR-3 最终来源只读诊断

新服务 `note_cell_sources.py` 只做 select：显示视图、有效公式集（`note_settings.list_section`，含层级）、推送状态（`FormulaPushState`
反解 `note://` 地址）、行内 `_cell_modes` / `_cell_meta`、章节同步字段。判定顺序与写入方一致：人工 / 锁定格 > 用户公式 >
会实际写这一格的预设公式 > 非投影表的 binding > 整节人工覆盖（只挡推送与同步，不挡公式）> 当前值仍等于上次写值的推送 > 底稿同步 >
普通录入。投影表的非空底稿值与预设公式不一致时保留底稿值并报冲突；表内公式可本地求值核实，含跨表引用的标「未核实」。

### ADR-4 同名行分组只做判别，不改身份

读取层与明细模板共用 `consol_note_row_groups.row_groups`：一级编号（`一、` / `（一）`）或冒号结尾的非合计行为分组头；同一一级分组内
仍拥挤的同名行，再用最近的表内唯一行名细分（`其中：` 成员不作锚点）；仍分不开才用组内序号。产出 `_group` / `_group_occurrence`，
二者与 `occurrence` 一样排除在结构指纹外。建议先按（行名, 分组）配对，且只有来源 / 模板两边该分组都唯一时算 `exact`；只能按位置
配对的建议是 `position`、置信度 0.6、不可自动确认。apply 只对带 `source_group` 的新映射按组过滤，组内找不到不跨组兜底；旧映射
逐字节保持原行为。

### ADR-5 标题行库按表覆盖优先

逐表 `overrides.columns`（必须带 reason）优先；全局 `measure_aliases` 只用于跨表无歧义的长词（递延所得税互抵余额、占位方括号）。
「收入 / 成本」这类短词不做全局同义。

### ADR-6 告警在组件边界修

`DisclosureEditorRoute` 包单一元素根（无样式，`.gt-disclosure-editor` 无高度约束，布局不变）；`CommentTooltip` 改渲染函数：无批注且只有
一个元素 / 组件子节点时原样作为根并显式承接 attrs / 事件；有批注时由 `ElTooltip` 包唯一子节点，多个子节点才包 span，且清空
`triggerKeys`，不抢单元格里的 Enter / 空格。附注单元格的校验提示包 `gt-cell-wrapper`（下方），批注提示只包 `GtGridCell`（上方）；
`ReportView` 两处公式提示改包真实 span。全仓守卫扫描 `el-tooltip / el-popover` 直接包批注根组件的同类写法，并验证登记组件的真实根。

## 3. 文件计划

| 批 | 文件 | 说明 |
|---|---|---|
| R1 | `note_formula_tables.py`、`note_sub_table_projector.py`、`note_formula_generator.py`、`note_formula_service.py`、`formula_settings/note_settings.py` | 视图、写回、预设补空、列表 / 目标 / 校验 / 覆盖率 |
| R2 | 新 `note_cell_sources.py`、`disclosure_notes.py`（薄路由）、`disclosure_trace.py`、`CellTraceDialog.vue`、`DisclosureEditor.vue`、`apiPaths` | 诊断接口与弹窗 |
| R3 | `consol_note_standalone_reader.py`、`consol_note_detail_source_service.py`、`consol_note_detail_suggest.py`、`consol_note_auto_mapping.py`、`consol_note_mapping_rule_service.py`、`consol_note_detail_apply_service.py`、映射弹窗与类型 | 分组判别 |
| R4 | `note_table_header_vocabulary.json`、生成的库 / 对应文件、`test_note_table_header_catalog.py` 棘轮 | 词表与覆盖 |
| R5 | `DisclosureEditorRoute.vue`、`CommentTooltip.vue`、`DisclosureEditor.vue`、`ReportView.vue`、全仓嵌套提示守卫 | 告警、键盘与两层提示 |

行数：候选树 `DisclosureEditor.vue` 3170，hard cap 从陈旧的 3228 收紧到 3170；`ReportView.vue` 1943 行且本轮净增 0；
`consolidationApi.ts` 1475（上限 1500）、`consol_note_detail_source_service.py` 773（上限 800）。新增逻辑放新模块或现有小文件，
路由与大组件只留接线。

## 4. ROI 裁定

| 项 | 文件数 | 收益 | 风险 | 裁定 |
|---|---:|---|---|---|
| R1 公式视图 | 5 | 高：78/78 离屏后多数章节成为底稿来源，公式管理在这些章节上原本不生效或写进隐藏表 | 中：预设只补空，写入位置有反向测试 | 本轮做 |
| R2 来源诊断 | 6 | 高：公式管理的溯源主入口 | 低：只读 | 本轮做 |
| R3 同名分组 | 7~8 | 中：消除跨组错配被自动确认 | 中：不改指纹、旧映射不变 | 本轮做 |
| R4 标题行库 | 3 | 中：减少合并取数漏列 | 低：生成门 + 逐列钉测 | 本轮做 |
| R5 告警 | 3 | 中：校验提示恢复可用、控制台干净 | 低 | 本轮做 |
| R6 环境 | — | — | 归属他人在途 spec | 只登记 |

## 5. 验证

1. 每批先写反例：底稿来源章节公式写进 `sub_table_data`、预设不改底稿非空值、旧 `_formulas` 不套投影、非底稿来源逐字节不变；
   诊断各来源与冲突；同名跨组、旧映射不变、指纹不变；词表覆盖逐列；CommentTooltip 无告警且属性落到元素。
2. 相关后端 / 前端既有测试、三项生成检查、标题行库 `--check` 全部重跑。
3. 浏览器在 `http://127.0.0.1:3030`、只写【测试】项目：底稿来源章节应用公式、单元格来源弹窗、控制台告警。
4. 最新远端分离头候选树重放，提交前对比 HEAD。

## 6. 实施与验证记录（2026-10-30）

### 6.1 功能结果

- **R1**：列表、目标、保存校验、覆盖率和执行共用 `formula_view`；投影写回 `sub_table_data` 源行业务键；位置化旧行的
  `_cell_modes` 也按来源坐标判断。预设只补空，差异回 `kept_workpaper / workpaper_differs`；用户公式覆盖回
  `overrode_workpaper`；刷新回执聚合 `formula_differs` 并在前端提示。
- **R2**：新增 readonly `GET …/{section}/cell-sources` 与 `note_cell_sources.diagnose_cell`；旧 trace 补 `table_index`；右键选区列号
  从包含行名列的坐标改为值列 `col - 1`，并通过 `_sourceCellRefs` 传存储坐标。弹窗同时呈现最终来源、逐层状态、冲突和旧 binding 详情。
- **R3**：990 个真库重复行名中 982 个可由分组消歧；1355 次章节读取与合并模板建议得到 grouped exact 1369、position 36。
  与旧算法不同的 4 个目标都在五-64-4「租赁收入」，旧算法原来落到最后一个同名模板行。分组不进指纹，golden hash 不变。
- **R4**：16 条带 reason 的逐表覆盖 + 2 条无歧义长词别名；国企覆盖率 0.9418→0.9536（631→637，取数列 670→668），
  上市 0.9500→0.9624（836→845，880→878），none 不变，mapping_disagreements 均为 0；映射 JSON 重跑逐条不变。
- **R5**：消除附注路由多根、无批注片段根和两层 tooltip 直接嵌套；ReportView 同类两处一并收口。守卫对 src 全部 Vue 文件扫描，
  禁止 `ElTooltip / ElPopover` 直接包带批注的 `CommentTooltip / GtAmountCell / ConsolNoteGridCell`。

### 6.2 自动验证

- 核心后端：318 passed / 4 skipped；扩展选集：3925 passed / 10 skipped。扩展选集的 11 failed 均在干净远端
  `1db8ed43e` 复现；顺序运行出现的 6 errors 是既有 event-loop / 连接池污染，相关文件单跑与远端对照无本轮新增。
- 前端相关 + 全仓扫描守卫：候选 868 passed / 4 failed，最新干净远端 `bb16db07d` 的失败节点逐一相同；
  22 个改动前端文件 ESLint 通过。单区域 vue-tsc 候选 / 最新远端各 1234 条，spec 文件各 8 条，新增 0；TS2322 金丝雀命中，无 OOM。
- 标题行库、Word 树、Word 同步三项 `--check` 通过；映射生成重跑 diff=0；行数门、hard-cap 棘轮、`git diff --check` 通过。
- 磁盘变异 / 整文件回退合计 89/89 打红：R1 18、R2 23、R3 19、R4 12、R5 17。

### 6.3 浏览器实测与数据恢复

在 `http://127.0.0.1:3030` 的独立浏览器上下文，仅使用【测试】公式同步甲：

1. 五、1 银行存款右键「溯源到底稿/试算表」：两个接口均 200；最终来源为模板 binding，显示 E1 上次推送 0、当前值 200 的差异，
   TB 公式计算值与当前值均为 200，坐标是第 2 行第 1 个值列（修复了原 `col` 偏右一列）。
2. 经正式 `sync-from-workpaper` 临时把五、5 投影为三行 `sub_table_data`；编辑器显示投影表，公式管理显示两条系统预设
   `SUM(0:1,0/1)`。点「应用自动运算」响应 `executed=2 / updated=2`，合计 350 / 100 写回来源行；原 17 张隐藏 `_tables` 未改。
3. 经正式附注 PUT 接口恢复 UAT 前备份；`table_data` MD5 回到 `c69d8ba02b13e3f7020a8822142b953d`，`sub_table_data / _source`
   均移除，formula push run / state / sync item 行数保持 16 / 34 / 2。隔离会话已登出关闭。
4. 重载后没有 DisclosureEditor、CommentTooltip 或 Transition 告警；仍有 NotificationCenter 自身的 ElOnlyChild 两条既有告警。

## 7. 未改项与后续裁决

- **需用户定**：国企五-64-3、上市五-62-3 的「收入 / 成本」与单体底稿「主营业务收入 / 主营业务成本」是否视作同一语义；
  当前宁缺不错，不加短词全局别名。上市五-15-3/4/5 的「坏账准备 / 减值准备」写法仍会让一部分同名建议落为 `position`，
  需用户确认词义后再改生成源，不能手改生成的 `note_row_label_aliases.json`。
- **结构性未对应**：五-18-9「发起规模」按既有契约是 G7 两层文字列；其余数量、互抵金额、业绩承诺、上期 / 上年列等是单体表
  本就没有或 1:N 结构，保持 unmatched 并向用户显示。
- **环境归属**：8 条非关键 schema drift 属其他在途迁移 / 模型；离屏运行观测与 PG 连接饱和已由
  `note-pull-residual-governance-closure` §9 登记下一轮 P1，本轮不重复。NotificationCenter 提示根告警也不属于附注链。
- **远端既有测试红**：前端 `authTokenSingleSource`、`FrontendReferenceIntegrity`、`rawRequestAuth`、`composables` preset；后端
  formula endpoint 鉴权旧断言、consol formula seed 计数、preset markdown 缺文件、scope 旧断言、raw-SQL 的 `ai_content.wp_name` 等。
  本轮不靠降级断言或豁免蒙绿，候选与干净远端按节点对照。
