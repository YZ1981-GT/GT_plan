# 附注链后续优化 — 任务

## R1 附注公式按显示视图生效

- [x] 1. `formula_view` 与投影值列键单一来源；公式列表、目标清单、保存校验、覆盖率改走显示视图
- [x] 2. 执行器：投影表写回 `sub_table_data`、预设只补空并回报差异、用户公式覆盖并标明、旧 `_formulas` 不套投影
- [x] 3. 反例测试：底稿来源章节写入位置、非底稿来源逐字节不变、隐藏旧 `_tables` 不再被写
  - 证据：`test_note_formula_view.py` 9 例 + `useNoteRefresh.spec.ts` 17 例（差异提示 2 例）；磁盘变异后端 15/15、前端 3/3 全红；
    相关后端回归 279 + 31 passed（`test_note_workpaper_pull_service.py` 两处整字典断言补 `differs`）

## R2 单元格最终来源诊断

- [x] 4. 只读服务与接口：显示视图、有效公式层级、推送状态反解、人工 / 锁定 / binding / 同步，判定与冲突
- [x] 5. 原 binding 溯源支持表序号；单元格溯源弹窗显示最终来源与冲突
  - 证据：`note_cell_sources.py` + `GET …/{section}/cell-sources`（readonly 门禁）；`test_note_cell_sources.py` 12 例（真推送 +
    真路由：成员 200 / 非成员 403 / 404 / 422）、`test_note_cell_trace.py` 补第 2 张表、hardening 断言表序号透传；
    前端 `CellTraceDialog.spec.ts` 7 例、`useNoteCellActions.spec.ts` 4 例；磁盘变异后端 16/16、前端 7/7 全红
  - 顺带修：右键溯源原先把选区列号（含行名列）直接当数据列 ⇒ 取到右边一列，且多表只看第 1 张存储表；
    投影表来源行仍按位置存（旧快照）且标人工 / 锁定的格，公式与推送同口径不写（`view_cell_mode`）

## R3 合并同名行按分组判别

- [x] 6. 读取层分组与组内序号（不进指纹），建议按组配对、仅按序号配对的同名建议需复核
- [x] 7. 映射校验 / 自动映射 / apply 支持 `source_group`，旧映射不变；弹窗显示分组
  - 证据：`consol_note_row_groups.row_groups`（一级分组头 / 冒号头 / 表内唯一行细分）；真库单体附注 990 个重复行名 982 个
    分组可分（8 个是同一处结构重复，只能按位置）；真库 1355 次章节读取 × 合并模板：带分组建议 exact 1369 / position 36
    （须复核；其中 4 处目标与旧算法不同，均为五-64-4「租赁收入」旧算法落到模板最后一个同名行）；
    `test_consol_note_row_groups.py` 15 例 + R11 文件改新口径 9 例 + 弹窗 2 例；磁盘变异后端 15/15、前端 4/4 全红；
    consol_note 全量 802 passed（余 2 例 `test_seed_counts_on_real_templates` 远端干净检出同红，非本 spec）

## R4 标题行库

- [x] 8. 逐条核对未对应列，按表覆盖 / 长词别名修复可修项，重新生成并收紧棘轮
  - 证据：词表加 16 条逐表覆盖（带 reason）+ 2 条长词别名；国企 0.9418→0.9536（对上 631→637、取数列 670→668）、
    上市 0.9500→0.9624（836→845、880→878），none 不变、映射分歧 0、`consol_note_section_mapping.json` 重跑逐条不变；
    与远端逐表比对只有登记的 10 张合并表变化。`test_note_table_header_catalog.py` 新增 3 例（逐列钉住、比例列移出取数列、
    覆盖条目必须命中现存表的数据列），相关后端 667 passed；磁盘变异 12/12 全红
  - 未修（需定或结构性）：收入 ↔ 主营业务收入（国企 五-64-3、上市 五-62-3）语义待用户定；五-18-9「发起规模」按既有
    测试是文字列；其余未对上列是单体本就没有的列（数量、互抵金额、业绩承诺、上期 / 上年列等）

## R5 页面告警

- [x] 9. 路由壳单一根、CommentTooltip 单子节点直通、附注单元格两层提示各自生效
  - 证据：`DisclosureEditorRoute` 加无样式单一根；`CommentTooltip` 改渲染函数，无批注时唯一元素原样作根并接收 attrs / 事件，
    有批注时唯一元素作 tooltip 触发器、多个子节点安全包 span，`triggerKeys=[]` 不吃单元格 Enter / 空格；附注校验提示包
    `gt-cell-wrapper`（下方）、批注提示只包 `GtGridCell`（上方）；`ReportView` 两处公式提示同样改为包真实 span
  - `CommentTooltip.spec.ts` 7 例、`DisclosureEditorRoute.spec.ts` 5 例、`DisclosureEditor.cellTooltips.spec.ts` 3 例、
    全仓 `nestedCommentTooltipGuard.spec.ts` 3 例；相关 R5 选集 50 passed；磁盘变异 + 三个整文件回退 17/17 全红

## 验收

- [x] 10. 相关后端 / 前端回归、生成检查、浏览器实测（只写【测试】项目）
  - 候选树核心后端 318 passed / 4 skipped；扩展选集 3925 passed / 10 skipped，11 failed + 6 errors 均由远端基线复现；
    前端候选 868 passed / 4 failed，远端同选集 843 passed / 4 failed，失败节点逐一相同；改动文件 ESLint 22/22 通过
  - 单区域 vue-tsc 候选 / 远端各 1234 条，spec 文件各 8 条，新增 0；金丝雀 TS2322 命中、无 OOM；
    标题行库 / Word 树 / Word 同步三项 `--check`、行数门、hard-cap 棘轮、`git diff --check` 均通过
  - 浏览器（`127.0.0.1:3030`，仅【测试】公式同步甲）：投影表公式列表出现 `SUM(0:1,0/1)`，页面应用后
    `executed=2 / updated=2`、合计写回 `sub_table_data` 为 350 / 100、隐藏 17 张 `_tables` 未写；五、1 银行存款的来源弹窗同时显示
    binding、推送差异、TB 计算值 200；测试后经正式接口恢复，`table_data` MD5 回到 `c69d8ba02b13e3f7020a8822142b953d`，
    推送 / 同步状态行数不变。无本 spec 的 Vue 告警；余 NotificationCenter 两条 ElOnlyChild 告警为远端既有
- [x] 11. 最新远端候选树重放与提交推送；登记环境项与后续建议
  - 最终 fetch 后远端由 `1db8ed43e` 前移至 `bb16db07d`（v1.0.50）；287 个远端变更与本 spec 57 个文件的交集只有
    `INDEX.md`。56 个无冲突文件逐字节搬到最新干净候选，INDEX 在最新版本上重新插入；归属核对 unknown=0 / missing=0
  - 最新候选再跑核心后端 318 passed / 4 skipped、前端 868 passed / 4 failed（同 4 个失败在最新干净远端复现）、
    vue-tsc 1234↔1234 且 spec 新增 0、三项生成检查 / ESLint / 行数门 / diff-check 全通过；单一提交并通过版本工具原子推送
