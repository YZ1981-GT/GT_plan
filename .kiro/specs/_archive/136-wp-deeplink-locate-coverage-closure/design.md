# 设计：底稿深链定位覆盖收口（wp-deeplink-locate-coverage-closure）

## 1. 复核结论（需求 1.1，证据 `tmp_wp_locate_cov/out/cell_review.json`）

- 复核口径：一个单元格的「上下文」= 该格的值（落在合并区域里取左上角）+ 同行全部文字 + 同列向上 15 行内最近两处文字；「覆盖率」= 语义标签的二字片段出现在上下文里的比例。整张 sheet 的文字格按同一口径找候选。
- 435 个未停用格里，33 格是既有判定 `keep_semantic_unverified`（语义已标待核对，本 spec 不动）；其余 402 格覆盖率 ≥0.6 的 6 格逐条看过都是假匹配（命中的是第 2 行表名或表头行，如 N1-3 B5「科目名称」实为「类别（报表调整/账项调整/其他）」）。即 402 格没有一格坐标正确。
- 402 格的 addr_id / formula_ref：PG 公式类列引用 0；静态引用只在 ACNR 冻结夹具（`backend/tests/acnr/fixtures/*`，sha256 钉死、不随目录变）、`acknowledgements.json`（只覆盖那 33 格）、`v2_canonical_reconcile.json`（生成物，按 `--check` 重算）与若干测试用例里（`static_refs.json`）。生产代码里出现的只有 docstring 示例 `D2/D2-2/E100`（11 处，不参与逻辑）。

## 2. 目录纠错（需求 1.2~1.5）

### 2.1 处置规则（可现算，守卫复算）

| 情形 | 处置 |
|---|---|
| E1-14 C10「货币资金余额变动率」 | 新增 `E1/E1-14/I18`「货币资金合计本期变动率」（A18「合计」、I14「本期变动」、`=IF(E18=0,1,(C18-E18)/E18)`），原格停用、`replaced_by` 新格 |
| E1-14 C15「货币资金占总资产比例」 | 模板没有这一比例；新增 `E1/E1-14/C34`「银行存款÷资产总额（本期）」（B34 行标签、C33 `=C13` 本期列），原格停用、`replaced_by` 新格 |
| E1-14 B30「分析程序结论」 | 按下一行规则（A50「四、审计结论：」） |
| `purpose=conclusion`，所在 tab 恰有一个文字为「审计结论」的标签格（`^([一二三四五六七八九十]+、)?审计结论[:：]?$`，去空白后） | 新增该标签格（标签「审计结论」、purpose conclusion），同 sheet 的结论种子都停用、`replaced_by` 新格 |
| 其余 | 停用，`replaced_by` 父 sheet |

不改指合计类（53 格）：表头多为多级（期初余额 / 原币 / 人民币），自动配列会造出新的错坐标；按需要另行登记。

结果：402 格全部停用（kind `seed_coordinate_mismatch`）；69 格改指到 65 个新坐标（63 个「审计结论」标签格 + I18 + C34），333 格指父 sheet。有效单元格 98 = 33（待核对，未动）+ 65（模板核对）。

### 2.2 数据落点

- 停用：`backend/data/acnr/sources/sheet_verdicts.json` 的 `cell_verdicts` 追加，`kind=seed_coordinate_mismatch`（`from_sheet_verdicts.CELL_KINDS` 增此值）、`verdict=deprecate`；`evidence` = 模板册 / tab / 类别 / 值 / 同行文字 / 列头 / 覆盖率 / `static_refs` / `pg_formula_refs`。生成器照旧经 `apply_cell_verdicts` 标停用（`cell_label`「{A1}（坐标待核对）」）。
- 新坐标：新种子 `backend/data/t_address_registry_seed.json`（模板核对坐标；loader 与 `input_files` 的通配已覆盖），每个坐标带 `evidence`（行标签、列头、该格值）与 `rule`（`conclusion_label` / `explicit`）。13 份旧种子不改：停用格必须留在目录，来源就是旧种子。
- 生成与校验脚本 `backend/scripts/acnr/review_cell_coordinates.py`：`--write` 由模板现算并写停用判定与新种子，`--check` 现算比对（漂移退出 2）。

### 2.3 发布与守卫

- `python backend/scripts/acnr/generate_catalog.py` 写新批次 `20261030063137`（上一批 `20261029075533`），`--check` 通过；`v2_canonical_reconcile.json`、`editor_save_inputs.json` 等生成物按各自 `--check` 重算。
- `backend/tests/acnr/test_cell_coordinate_review.py`：①`review_cell_coordinates.py --check` 退出 0（判定与新种子都等于模板现算）；②目录里未停用、不在 `keep_semantic_unverified` 里的单元格全部来自 `t_` 种子；③新种子每个坐标按其 `rule` 成立（结论标签正则 / 显式行标签与列头）；④本 spec 停用的格都在目录里、标停用且 `replaced_by` 是父 sheet 或种子声明的新格；⑤PG 公式列对停用格引用 0（pg_only）；⑥文字锚点对照与目录一致且接在 CI 上（见 §3）。
- 依赖目录计数或用这些格做样例的既有测试：样例换成仍有效的格或改断言停用语义，不删用例、不放宽判据。

## 3. 文字锚点（需求 2）

- 对照生成：`backend/scripts/acnr/generate_cell_text_anchors.py` 读目录，取未停用、purpose=conclusion、语义标签「审计结论」的格（现为 t_ 种子的 63 格），写 `audit-platform/frontend/src/generated/catalogTextAnchors.ts`（与 `dSheetLabels.ts` 等同目录）：`{ [sheet_code]: { [A1]: '审计结论' } }` 与查询函数 `catalogTextAnchor(sheetCode, cellRef)`（编码与 A1 都去空白、不分大小写）；`--check` 比对，CI 作业 `acnr-cell-text-anchors-generated`（只依赖标准库）。
- 查找（`composables/textAnchorLocate.ts`）：在根元素内取文字（去空白、去序号、去尾部冒号）等于锚点文字的元素；序号认「四、」「2、」「2.」「（三）」「(3)」「IV.」。排除 `th` / `td` 内的、祖先 `display:none` / `hidden` / `aria-hidden` 的；恰好一个时高亮 `closest('.el-card, .el-form-item')`（须在根元素内），没有则高亮该元素；0 个或多个返回 false。
  - 序号口径来自组件模板普查（`heading_forms.txt`）：标签文字含「审计结论」587 处，只认中文序号时 511 处可认，阿拉伯 / 括号 / 罗马序号另 52 处（多在审定表、调整分录页签）；放宽后每个文件可认的标题只会 0 → 1、不会 1 → 2（`heading_forms2.txt`），唯一性判据不受影响。「总体审计结论」「分析结论（四、审计结论）」这类带别的字的仍不认，照旧提示。
- 调度：`useRendererCellLocate` 增可选依赖 `textAnchor(sheetCode, cellRef)` 与 `anchorWaits`，顺序为组件钩子 → `[data-cell-ref]`（`useCellLocate`）→ 文字锚点。每个请求查一次对照：
  - sheet 编码：渲染配置给了 `sheet_code` 用它；**模板页签渲染配置不给 `sheet_code`**（原因 `template_sheet_name`，E1 / D4 / H3 全部页签都是），按页签名末尾的结构化编码取（`locateSheetCode`，与公式右栏 `extractSheetCodeFromName` 同一口径，「银行存单盘点表E1-9」→ E1-9）。前端用例读目录逐张核对：63 张登记表的模板页签名都能对回登记编码。
  - 重试窗口：登记了锚点的请求在默认 `waits`（0/100/250/500/1000 ms，共 1.85 秒）后追加 `TEXT_ANCHOR_EXTRA_WAITS`（1.5/2/3 秒，共 8.35 秒）——浏览器计时 D4 结论区标题比页签晚约 2.3 秒出现（取完数才渲染）；没有登记锚点的格（如 I18）仍 1.85 秒后提示，不因此变慢。
- GtWpRenderer 传入 `catalogTextAnchor`（源码结构用例钉住接线）。
- 「按使用频率」核对：对照覆盖到的组件按真实底稿数排序，d2-accounts-receivable 排第一（D2-5 应收账款分析表、D2-6 关联方及交易检查表）：只做了静态核对（`D2TabAnalysis.vue` 有一处 `.section-title`「四、审计结论」、`D2TabRelatedParty.vue` 有一处卡片标题「审计结论」），【测试】项目里没有 D2 底稿，未实测；e1 / d4 / h3 浏览器实测（`【测试】附件小眼睛走查_2025`）。F1 / G8 / K3 / L1 在目录里没有结论格（对照里无这些编码），不在实测范围；c-control-test、a-program-console 同。

## 4. 定位入口（需求 3）

- `services/openWorkpaperCell.ts`：`openWorkpaperCell(router, { projectId, wpId?, wpCode?, sheet?, cell? })`。`wpId` 是 UUID 时直接用，否则经 `resolveWorkpaperByCode`（静默，失败不弹全局错）；sheet 级编码（D2-1）本项目没有独立底稿时回落父底稿（D2）并把原编码当 `sheet`（已给 sheet 不覆盖）；成功 `router.push(workpaperEditorRoute(projectId, wpId, query))` 返回 null，失败返回中文原因（调用方 `ElMessage.warning`）。
- 调用方：TrialBalance / Misstatements / ConsolidationIndex / useReportTrace 的「定位」（溯源数据来自本项目 `/lineage`，按本项目取底稿）；ReviewOpinionList；`usePenetrate.toWorkpaperFromNote`（改 async，保留 `_pushCurrentRoute`）；LineageGraphPanel：在编辑器里且节点就是当前底稿（`wp_id` 相同；没带 `wp_id` 时编码与「当前对象」相同）发 `workpaper:locate-cell`（带当前 wpId），否则 `openWorkpaperCell`，成功后关闭抽屉。LineageGraphPanel 现无挂载点，按同一口径修。
- 守卫 `views/__tests__/deepLinkEntryGuard.spec.ts`：源码里 `wpId:` 后跟 `.wp_code` 的定位事件为 0；跳底稿列表页（`name: 'WorkpaperList'` 或 `/projects/${…}/workpapers`）的对象字面量与其 query 变量都不带 `sheet` / `cell`；`on*TraceLocate` 处理函数都调 `openWorkpaperCell`（新增同名函数自动纳入）；另 3 处同类入口导入并调用它。判据自带双向样例（旧写法命中、编辑器跳转 + 列表筛选不命中）。
- 顺带：`cellTrace.spec.ts` 里原「点击来源节点 → 发 locate-cell」用例在测试里自己发事件再断言发了（不经生产代码）且记的是错误行为，改为调用生产的 `useReportTrace`。

## 5. Univer（需求 4）

- `UniverEditorCore` 增 props `initialSheet` / `initialCell`；`onBusLocateCell` 与初始属性都经 `requestLocate` 记为待办（只留最后一个），`applyLocate` 在 `univerAPI` 已有、`loading` 为假且有活动工作簿时执行：按 `resolveSheetNameByDeepLink` 找 sheet → `onSwitchSheet`（找不到不切也不选）；单元格是 A1 形态时 `target.getRange(A1)` + `workbook.setActiveRange(range)`（Univer 0.21 facade，函数不存在时只切 sheet）。`watch([univerAPI, loading])` 触发重试；深链属性变化（同页再次跳转）立即执行。
- `WorkpaperEditor` 删去模式判定后的 `setTimeout(300)` 发事件，改传两个属性；`line-budget` 棘轮 1348 → 1341。

## 6. 测试与变异

- 后端：`test_cell_coordinate_review.py`（7 例，含 pg_only 与 CI 接线）、ACNR 全套（`backend/tests/acnr`）、引用了停用坐标的 24 个 acnr 外用例、`test_*_cycle_address_registry.py` 与 CI 接线用例。
- 前端：`textAnchorLocate.spec.ts`、`useRendererCellLocate.spec.ts`（文字锚点 / 模板页签编码 / 追加等待）、`openWorkpaperCell.spec.ts`、`deepLinkEntryGuard.spec.ts`、`UniverEditorCore.locate.spec.ts`、`deepLinkInitialCell.spec.ts`、`cellTrace.spec.ts`、`LineageGraphPanel.spec.ts`、`usePenetrate.spec.ts`、`ReviewOpinionList.spec.ts`，及引用改动文件的全部既有用例（选集 60 个文件）与全前端扫描类用例（85 个文件）。
- 变异（磁盘注入、sha256 还原）：V1 判定脚本把结论规则放宽为「含结论二字」；V2 新种子改错一个 A1；V3 文字锚点不排除表格单元格；V4 不检查唯一性；V5 openWorkpaperCell 不解析编码直接拿编码当 id；V6 Lineage 跨底稿仍只发事件；V7 Univer 未就绪直接丢；V8 生成对照被手改（`--check` 漂移）；V9 渲染器不把对照交给调度；V10 调度里文字锚点一级不生效；V11 弹窗「定位」恢复发事件；V12 编辑器恢复定时器发定位事件；V13 有锚点时不追加等待；V14 模板页签不按页签名取编码；V15 对照查询不归一编码大小写；V16 序号只认中文序号。

## 7. 范围外

- 调整分录页跳来源底稿带 `highlight=source_ref`（HTML 行身份，不是 A1），编辑器不读该参数：需要按行身份定位的机制，另立 spec。
- 底稿列表页不处理 `highlight`：本 spec 只把带单元格的入口改到编辑器。
- 既有 33 格 `keep_semantic_unverified`（豁免到 2027-04-30）与合计类坐标的补登。
- 文字锚点只覆盖「审计结论」；组件里写成「分析结论（四、审计结论）」「总体审计结论」的认不出，照旧提示「没有对应位置」。
- 整本走 Univer 的底稿：目录 editor_engine univer 16 张 sheet，【测试】项目里没有整本走 Univer 的底稿；浏览器实测用只读响应改写把 F4 导到 Univer 分支、工作簿用合成数据（不请求 xlsx-to-json，避免后端落文件、改 `file_path`）。
