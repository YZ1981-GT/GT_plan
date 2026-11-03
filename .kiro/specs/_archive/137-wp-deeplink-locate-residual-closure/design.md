# 设计：底稿深链定位残项收口（wp-deeplink-locate-residual-closure）

## 1. 调整分录页跳来源底稿（需求 1）

### 1.1 打开调整分录表

- 别名 `ADJUSTMENT_SHEET_ALIAS = '@adjustment'`（`utils/normalizeSheetName.ts`，与 `@program` 并列）。`resolveSheetNameByDeepLink` 收到它时取**名称（归一后）含「调整分录」的唯一一张表**；没有或多于一张返回 null（HTML 渲染器照旧提示「已打开底稿但未能定位到目标位置」，Univer 不切）。按名称判定，HTML（`resolveRenderSheet`）与 Univer（`applyLocate`）两条路径同一口径。
- 不按 `sheet_type` 判：表名「调整分录汇总表D1-5」含「汇总」，前后端启发式都判成 `audit_sheet`。
- `Adjustments.vue` 的 `jumpToSourceWorkpaper` 改为 `?sheet=@adjustment&highlight=<source_ref>`；行内「底稿 X」的显示不变。
- 否决：①前端维护 item_id → 表编码对照（81 个页签各写一份，与组件里的 item_id 两处真源会漂）；②后端在汇聚时存表编码（要迁移，且 `adjustment_sync_service` / 调整分录路由正被并发会话 `adjustment-client-booking-status` 改动）。

### 1.2 定位分录组

- `composables/adjustmentEntryGroupLocate.ts`：
  - `entryGroupOfHighlight(highlight, wpId)`：`source_ref` 形如 `{wp_id}:{item_id}`，按第一个冒号拆，`wp_id` 等于当前底稿才返回 item_id，否则 null（别的页面带来的 `highlight` 不误用）；
  - 登记表：`registerAdjustmentEntryGroup(wpId getter, locate)` 返回注销函数；`locateAdjustmentEntryGroup(wpId, itemId)` 依次问本底稿已登记的页签，有一个认领即 true。
- `useAdjustmentCentralSync`（81 个页签共用）挂载时登记、卸载时注销。认领规则：`resolveItemId() === itemId`；不等且传了新选项 `entryType`（`Ref<'AJE' | 'RJE'>`）时依次试 AJE / RJE，等于则停在该类型，都不等则还原原类型。认领后高亮组件根元素里第一张 `.el-table`（D4 的在线编辑区等没有表格时高亮根元素），经 `highlightElement`（滚到可见 + 3 秒淡出，与单元格定位同一实现）。
- 24 个按类型取 item_id 的页签（K10 / K12 / K13、L1~L8、M1~M10、N1~N3，类型都是 `'AJE' | 'RJE'`，`adj_types.txt`）传 `entryType`，即其 item_id 模板串里用的那个 ref。
- 渲染器：`useRendererCellLocate` 的请求增 `entryGroup`，依赖增 `entryGroup(wpId, itemId)`。切到表后按 `waits + TEXT_ANCHOR_EXTRA_WAITS`（约 8.35 秒；页签是异步组件且要先取数）重试认领；都不认领提示 `「{表名}」里没有找到这组调整分录（可能已删除或改了类型）`。`GtWpRenderer` 把登记表交给调度，并从 `route.query.highlight` 取初始请求（渲染器已有 `route`，编辑器外壳不改，行数棘轮不动）。
- 守卫 `components/workpaper/composables/__tests__/adjustmentEntryGroupWiring.spec.ts`：扫 81 个调用点，item_id 是函数的必须传 `entryType` 且就是模板串里的 ref；读 `backend/data/acnr/global_catalog.json`，这 81 个底稿编码在目录里各恰有一张「调整分录」表，别名对其表名列表能解析到它。

## 2. 底稿列表页入口参数（需求 2）

- `views/workpaper-list/workpaperListEntryQuery.ts`：`WORKPAPER_LIST_QUERY_KEYS`（`view` `filter` `year` `highlight` `wp_code` `search` `cycle` `upload`，列表页读的全部参数）；`readListEntryQuery(query)` → `{ code, cycle, upload, signature }`：`code` 取 `highlight` > `wp_code` > `search` 的第一个词（去空白、按空白 / 逗号截断，入口里有「D2-1 应收账款」这类带名称的写法），`cycle` 只认单个字母 A~S（转大写）。
- `WorkpaperList.vue` 的 `applyRouteQuery` 改收整个 query：入口参数按**签名变化**处理（进入时与同页地址变化时各一次），`cycle` → 筛选栏「审计循环」（`filterCycle`，触发既有按循环取数）；`code` → 上下文 `locateTarget = { code, seq }`；`upload` → 打开「增强导入」（`WpImportDialog`，按文件认底稿）并 `router.replace` 去掉该参数。有 `code` / `cycle` 到达时强制列表视图；签名没变时视图照旧按 `?view=`（否则带着 `highlight` 就切不出列表视图）。监听增加这五个键。筛选栏循环选项补 A 类（原来缺，`?cycle=A` 会显示原始值）。
- `views/workpaper-list/useWorkpaperListLocate.ts`（工作台 SFC 的列表模式调用）：每个 `seq` 只执行一次；列表在加载时等。查找：编码精确相等（不分大小写）→ 按连字符向前找最近的上级底稿（提示「没有编码为 X 的底稿，已定位到 Y」）→ 都没有时按原因提示：底稿索引有、列表没有且开着「仅看待重算」⇒「底稿 X 不在「仅看待重算」的结果里」；索引有、列表没有 ⇒「底稿 X 尚未生成」；都没有 ⇒「本项目没有底稿 X」。找到后左栏选中所在循环、`wbPage` 翻到所在页、`setCurrentRow`，等渲染后对该行 `tr` 调 `highlightElement`（`.el-table tr.gt-locate-highlight` 全局样式已有）。
- 入口改正：`UniverEditorCore.goToLifecycle` 的 `tab: 'lifecycle'` → `view: 'lifecycle'`；`ReviewLayerBadges` 删 `source_wp`（全仓无人读）。
- 守卫 `views/workpaper-list/__tests__/workpaperListEntryQuery.spec.ts`：解析函数单测；全仓扫跳列表页的 `router.push/replace` 对象字面量（`query: {…}` 的顶层键，展开 `...x` 忽略）与 `` `/projects/${…}/workpapers?…` `` 字符串里的参数，都须在清单里；判据带双向样例（`tab` / `source_wp` 命中，`highlight` / `view` 不命中）。

## 3. 复合结论标题（需求 3）

- `textAnchorLocate.findTextAnchorElement` 一次遍历收两类：一级 = 归一后（去空白、去序号、去尾冒号）整段等于锚点文字；二级 = 归一后**包含**锚点文字且长度 ≤ 锚点长度 + 8，且不在 `th, td, button, a, [role="button"], [role="tooltip"], .el-popper` 内。一级恰 1 处 → 它；一级 ≥2 → null（不改原判据）；一级 0 且二级恰 1 → 它；其余 null。命中后的高亮块规则不变（`.el-card, .el-form-item`）。
- 「+8」取自组件模板普查：带别的字的结论标题最长 12 字（「分析结论（四、审计结论）」），提示句最短 13 字（「完成核对清单并填写审计结论」）。按钮「🤖 AI 生成审计结论」靠祖先排除。「部分(一) 审计结论」「部分(二) 审计结论」同页两处 ⇒ 不认。
- 静态影响：登记了锚点的 64 张表里 F2-18、F2-62 由二级认出（`anchor_components.txt`），其余一级已认、行为不变。

## 4. 33 格与合计行（需求 4、5）

### 4.1 复核脚本收口

- `review_cell_coordinates.build()` 的复核范围由「没有别的判定」改为「没有别的判定，或别的判定是 `keep_semantic_unverified`」；这类旧判定在 `_merged_verdicts` 里被本 kind 的判定取代（删除），`--check` 发现仍有 `keep_semantic_unverified` 记录即漂移。T06 的 14 格超范围停用判定不动。
- 豁免 `ack-seed-semantic-unverified-2026-10-27`（只覆盖这 33 格）删除：格停用后它即「所覆盖的问题已不存在」的失效条目，发布门禁会拦。
- `from_sheet_verdicts` / `catalog_names` 对 `keep_semantic_unverified` 的支持保留（判定类型仍合法），文档改写为「现 0 格，由复核脚本接管」。

### 4.2 合计行规则 `total_row`

- 条件（全部成立才改指）：种子不是结论格、语义标签含「合计」；指标 = 标签去空白、去「合计行-」前缀与末尾「合计」（「X合计-Y」取 Y）；所在 tab 恰有一行的行标签（行内第一处文字）去空白后为「合计」「总计」「合计数」；该行以上 15 行内、表头单元格（合并区取左上角）去空白后恰等于指标的列恰好一列；目标格是公式或数值。
- 新坐标：`description` = `{指标}合计`，`purpose` 沿用种子，`rule = total_row`，证据 = 模板册 / tab / 该格值 / 行标签 / 表头行 / 列头（`_target_evidence` 同一实现）。守卫逐格复算上述条件。
- 不做模糊或同义词表头匹配：种子语义常挂错表（F2-5「周转材料」表上挂「在产品」），放宽会重新造出错坐标；也不为没有消费方的审定合计臆造坐标。

### 4.3 结果与重新发布（现算，提交前以生成器输出为准）

- 本 kind 判定 402 → 435 格；改指 69 → 72（G8-4 B35 → A24 `conclusion_label`；D1-3 E50 → J21、D2-2 E100 → Q26 `total_row`），指父表 333 → 363；新坐标 65 → 68；有效单元格 98 → 68，目录单元格 539 → 542；文字锚点 63 → 64 张表（G8-4 A24）。
- `generate_catalog.py` 写新批次；`reconcile_v2_canonical.py`、`gen_editor_save_inputs.py`、`generate_cell_text_anchors.py` 各自 `--write` 后 `--check`；依赖 33 / 98 / 539 / 441 等计数或这些格的既有守卫与架构文档事实表按新目录改写，判据不放宽。

## 5. 测试与变异

- 后端：`test_cell_coordinate_review.py`（增 `total_row` 复算、无待核对判定残留）、`test_name_system.py`（§6.4 的 33 格改由复核判定覆盖）、ACNR 全套与 CI 同口径 17 条检查。
- 前端：`textAnchorLocate.spec.ts`（二级）、`normalizeSheetName.spec.ts`（别名）、`adjustmentEntryGroupLocate.spec.ts`、`useAdjustmentCentralSync` 定位用例、`useRendererCellLocate.spec.ts`（分录组）、`adjustmentEntryGroupWiring.spec.ts`、`workpaperListEntryQuery.spec.ts`、`useWorkpaperListLocate.spec.ts`、`workpaperListQueryReuse.spec.ts`（入口参数不破坏既有同步），及引用改动文件的既有用例与全前端扫描类用例（基线归因）。
- 磁盘变异：别名不判唯一；跳转不带别名；高亮串解析不校验底稿；登记表不注销；不切类型；类型试完不还原；渲染器不发分录组请求；分录组不重试；列表定位不翻页；不回落上级；签名不变也强制列表；不去掉 `upload`；守卫漏扫字符串路径；二级不排除按钮；二级不限长度；二级不判唯一；复核不纳入待核对格；合计行不判唯一；表头不判唯一列。

## 6. 范围外

- 调整分录页「底稿 X」显示的编码仍取 item_id 前缀（H9 显示 H9-5，表是 H9-4）：只影响显示，不改（避免与并发会话改同一文件的展示区）。
- 列表页工作台 / 看板等视图不做定位（只有列表视图有表格与分页）。
- 复合标题之外的结论写法（「审计结论确认」类按钮文字已排除）与非「审计结论」锚点。
- 合计格（D1-3 J21、D2-2 Q26）在网页视图没有登记位置：深链切到该表并提示「网页视图里没有单元格 X 的对应位置」（浏览器实测 D2-2 Q26），目录坐标供 Univer / OnlyOffice 选格与公式引用。要在网页视图标出合计行，需各页签组件提供定位钩子或目录登记合计行文字锚点，另议。
- F2-62 等 IPO 专用页签在非 IPO 项目显示「此底稿仅适用于 IPO/上市/新三板/重组项目」，锚点无从定位，提示即为正确结果。
- 走查中看到的既有问题（与本 spec 无关，未改）：G8 页 `GET /projects/{id}/materiality` 422；`components/workpaper/WorkpaperLifecycleView.vue` 用 GET 调 `/ai/recommend-workpapers`（后端只有 POST）⇒ 405。

## 7. 实施与设计的差异（2026-10-31，以代码为准）

- 列表页参数清单 10 个：比 §2 多 `account`（试算表右键「查看关联底稿」带科目编码）与 `assigned=me|unassigned`（待办通知 / 经理看板「待分配」），实施时由守卫全仓现扫补上。`account` 经 `getWpMappingByAccount`（与试算表同一映射）取关联编码，等首次取数结束后只认本项目已生成的底稿（映射里还有表级编码 D2-2 与本项目没有的底稿，浏览器实测科目 1122 给出 13 个），定位第一张、多张时点名，一张都没生成时按映射第一张定位（列表页按原因提示），映射为空时提示；`unassigned` 用 `UNASSIGNED_FILTER`（`'__unassigned__'`）只在前端按 `assigned_to` 为空筛，不传后端，筛选栏增「未分配」。签名变化时 `account` / `assigned` 同样强制列表视图。
- 入口改正另 4 处（守卫扫出的列表页不读的参数）：经理看板「待分配」`filter_assigned` → `assigned`；联动气泡的关联底稿 `?wpId=` → 直接打开编辑器（`workpaperEditorRoute`）；`usePenetrate.toWorkpaper` `?code=` → `?highlight=`；「我的程序任务」深链改为打开该底稿的程序表页签（`programConsoleRoute`，带 `task_id` / `sheet_key` / `definition_key`，程序表按后两者定位行；原先跳列表页，列表页不读）。`usePenetrate.toWorkpaperFromReport`（带 `fromReport`）全仓无调用方：登记在守卫 `KNOWN_UNREAD`，其 `holds()` 断言仍无调用方，有人调用即打红、届时再定列表页怎么读。
- 列表定位多两条依赖：`loaded`（列表至少取到过一次；首屏取数前 `loading` 也是 false，只看 `loading` 会先报「本项目没有」）与 `active`（只在列表视图显示时执行；工作台、手册与列表共用一个组件实例）。工作台 SFC 用上下文版 `useWorkpaperListLocateInView(ctx, codeOf, view)`：入口目标、取数状态、编码清单、待重算筛选与当前视图取自列表上下文，表格引用由它建。手册视图点底稿（`onGuideWpClick`，原先只写无人读的 `ctx.selectedWpId`）改走 `locateCode`。
- 复核脚本：复核范围抽成 `review_scope()`（`build` 与守卫同一函数）；被本 kind 判定取代的 `keep_semantic_unverified` 由 `_superseded` 找出、`_merged_verdicts` 写出时删除；`check_lines` 对残留的这类判定逐条点名。
- 既有测试的样本替换（判据不放宽）：e2e 的 `value_in_form_storage` 样本 S15 C12（本轮停用）→ H3/H3-4/A27（H3 底稿 + 程序表结论 `H3-4-conclusion`），比较前去掉 `count_token`（含到秒的 `exp`）；展示名夹具样本 F3-5 B25 → D1/D1-3/J21，另断言目录里没有「（语义待核对）」的格，保留路径由 `test_name_system` 的合成 `apply_cell_verdicts` 用例覆盖。
- 行数：`WorkpaperWorkbenchView.vue` 1723 → 1727（列表页 line-budget 用例的 1210 预算在基线已超，红是既有的；pre-commit 白名单 1768）；`Adjustments.vue` 1974（白名单 1932 的 +5% 内）。
- D2 / F2 底稿经主树后端生成（`POST /api/projects/{id}/working-papers/generate`，模板集「精简版」，只选 D2 / F2）：worktree 后端按模块位置把文件写进 worktree 自己的 `backend/wp_storage`，拆树后 `file_path` 悬空（P1 原有 7 张底稿的 `file_path` 就指向 `tmp_attachment_spec_b/remote_wt` 下）。主树后端是 v1.0.50，请求模型还没有 `operation_id`（extra=forbid ⇒ 422），走同步路径。
