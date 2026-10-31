# 平台响应速度热点 — 设计

## 1. 实测基线（2026-10-27，重药安徽 2025，admin，开发服 3030 / 后端 9980）

探针都放在仓库外（`C:\Users\Administrator\perf_probe\`），只发 GET，浏览器探针拦掉全部非 GET 的 /api 请求；测完删除。复测用同一口径。

| 场景 | 实测 | 原因（文件） |
|---|---|---|
| 轻接口（未读数、项目详情、角色上下文） | 后端 7~30ms；无登录 `/api/version` 1ms | 每请求约 8 次 PG + 2 次 Redis 往返（各约 0.4ms），不是瓶颈 |
| 重启后约 1 分钟 | 所有接口 3~6 秒 | `startup_prewarm.py` 在事件循环上跑：注册段中位 40~53 秒、基线段 10~30 秒；8 天 715 条 >3s 慢请求 615 条落在 16 个分钟 |
| 重启频率 | 预热完成记录 10-27 54 次、10-23 130 次 | `--reload` + 并发会话改 `backend/app`（10-27 改了 170 个 .py） |
| D2 render-config | 后端 450ms，响应 14.7MB（gzip 后 1.0MB） | 15 个页签的 html_data 只差 `sheet_name`（`responses_snapshot` 916KB）；d1~d7 不在整册 memo 集合里，渲染器逐页重跑 15 次 |
| 打开 D2 | render-config 2 次 + guidance 2 次，约 29MB JSON | 外壳 `WorkpaperEditor.vue` 自带一个 `useWpRenderer` 只为 `decision_trace`；guidance 先按未定上下文请求一次；`wp_guidance_chat.py` 每次调 `_get_render_config_impl` 整套重算 |
| 底稿列表 | 最后一个请求 3.4~4.4 秒，长任务最长 1.7 秒 | `listWorkpapers` 串行 10 页（每页后端 COUNT / stats / 分页三遍 CTE）；`wpList` / `wpIndex` 深层 ref 约 930×2 行，CPU 剖析 1.24 秒在 Vue 响应式 |
| 只改 `?view=list` | 再发 14 个请求，2.7 秒 | `DefaultLayout.vue` 按 `fullPath` 做 key，整页重建 |
| 试算表 | 约 2.5 秒 | `TrialBalance.vue` 为「跳转底稿」也调 `listWorkpapers` |
| 序时账聚合（70 万行） | 冷 3.6s / 热 0.56s（JIT 0.41s）；关 JIT 0.30s；再加 work_mem 64MB 0.27s | 出厂参数；`shared_buffers` 128MB 装不下这张表 |
| 生产构建对比 | 模块请求约 330 → 80，页面完成时间只快 5~10% | 瓶颈在接口，不在打包 |

## 2. 设计

### R0 编译错误
- `GtChecklistTable.vue`：`withDefaults` 的默认值工厂改内联对象（提升到 setup 外后不能引用局部常量）。
- `MyTemplatesDialog.vue`：去掉 `<script setup>` 里的 `export`（无外部调用方）。
- 验证：开发服请求两个组件 200；全仓 `.vue` 用 `@vue/compiler-sfc` 同参数扫描（带 fs 选项，避免「解析外部类型」误报）。

### R1 render-config 共享载荷（可选开启）
- 后端 `wp_render_config_helpers.share_duplicated_html_data(resp)`：只在路由层、`_get_render_config_impl` 返回之后调用（`inject_applicable_standards` 已执行），impl 输出与 guidance 调用不变。
  - 分组键：除 `sheet_name` 外每个键的值，容器按对象身份（`id`）、标量按值；两个以上页签同组、且至少一个值是非空容器才共享。memo 产出的页签（整册专属同一对象、R2 的 `{**memo, sheet_name}`）天然同组，无需序列化比较。
  - 线上形状：顶层 `shared_html_data: {"h1": {...}}`；页签 `html_data` 只留差异键（D2 为 `{"sheet_name": ...}`），加 `html_data_ref: "h1"`。
  - `get_render_config` 加 `share_html_data: bool = Query(False)`；不带参数不调用，响应逐字节不变。
- 契约：`RenderConfigResponse.shared_html_data: dict[str, dict] | None = None`、`SheetRenderConfig.html_data_ref: str | None = None`；`response_model_exclude_unset` 下不设置即不出现。`test_render_config_wire_contract.py` 的 model-only 集合加「按参数出现」两项（golden 是不带参数的生产路径，不重抓）；前端 `RenderConfigWire` / `SheetRenderConfigWire` 同步，`RENDER_CONFIG_FIELD_STATUS.shared_html_data = 'active'`。
- 前端 `composables/renderConfigSharedHtml.ts` 的 `expandSharedHtmlData(config)`：每个带 `html_data_ref` 的页签 `html_data = { ...structuredClone(shared[ref]), ...差异键 }`，删引用与顶层字段。逐页深拷贝，保持原先「各页签独立对象」的语义（避免原地修改串页）。`useWpRenderer` 用 URL 内联参数 `?share_html_data=1`（不加 config，保留 apiProxy 在途共享）。

### R2 D 循环渲染器 memo
- 现状：`_dedicated_render_memo` 只对 `_WHOLE_WP_MULTISHEET_DEDICATED`（91 种）生效，d1~d7 只在 `_ONLYOFFICE_HTML_WHITELIST`，所以逐页重跑。
- 核对：d3~d7 渲染器只读 `ctx.wp_id / db / project_id / year / business_category`；d1 / d2 另写 `html_data["sheet_name"] = ctx.classification.sheet_name`。
- 改法：新增 `_WORKBOOK_SCOPED_RENDERERS = {d1..d7}`；同一请求第二次起命中 memo，结果含 `sheet_name` 时返回 `{**memo, "sheet_name": 本页}`，否则返回 memo 本身。整册专属集合的原行为（含 sheet_name 取第一页的既有现象）不动。
- 验证：真库探针对 D1~D7 全部底稿，memo 开 / 关两次调 impl，逐页深度比较（回滚事务）。

### R3 guidance 只算清册
- `_get_render_config_impl(..., manifest_only=False)`。为 True 时：不查 cross_ref / 项目年度 / 模板类型，不加载 schema，不跑渲染器、不取网格、不做 custom 投影与函证注入，循环后不做 auto-fill / 签字状态 / 准则注入 / 静态指引。
- 清册口径不变的依据：componentType 在调用渲染器之前已定；之后只有「无渲染器且不在白名单 → onlyoffice-sheet」改写（只看渲染器是否存在，保留）、skip 排除、自包含整册折叠（保留）、`sheet_code_reason` 补全（保留）；模板页签排序（保留，已缓存且在线程里）。
- guidance 端点改传 `manifest_only=True`。ETag 输入只含清册身份字段（`guidance_runtime_facts`），不受影响。
- 验证：真库探针对重药安徽全部底稿比较清册字段（`sheet_name / sheet_code / sheet_code_reason / whole_workbook / componentType`、顺序、`template_version`）；单测钉住 manifest_only 不调用渲染器。

### R4 打开底稿去重
- `WorkpaperEditor.vue` 删掉外壳的 `useWpRenderer(wpId, { silent: true })`；`GtWpRenderer` 的 `defineExpose` 增加 `renderConfig`、`loading`；侧栏 `decision_trace` 在 HTML 模式读 `wpRendererRef.renderConfig`，Univer 模式读 `loadUniverSheetIdentityCatalog` 已取到的配置。
- 编制说明面板加闸门 `guidanceContextReady`：页签上下文有 `sheetName / sheetCode / sheetUid / wholeWorkbook` 之一即放行；否则 HTML 模式等 GtWpRenderer 加载结束（拿不到上下文时整册请求一次）、Univer 模式等目录就绪。
- 同步测试：`WorkpaperEditor.chainWiring.spec.ts` 按新接线断言；`editorDetailRace.spec.ts` 的 composable 级用例前提已过时，改为断言外壳不再自带实例。

### R5 全部可见底稿端点
- `WorkpaperListQueryService.list_all_workpapers(context, filters)`：复用 `visible_wp_index_ids` 与 `_DEDUPED_CTE` / `_build_filters`，一条 `SELECT ... ORDER BY wp_code ASC NULLS LAST, wp_index_id ASC`，项结构与分页端点相同（抽出共用的 hydrate + 姓名批量查询），返回 `{items, total}`；异常同分页端点 fail-closed 返回空。
- 路由 `GET /working-papers-all`（与分页端点同文件、同一 `require_project_access("readonly")` + `VisibilityRoleClassifier.classify`），用连字符路径避开 `/working-papers/{wp_id}`。
- 前端 `listWorkpapersAll(projectId, filters)`：同 URL + 参数在途共享；`listWorkpapers` 改为基于它（保留「去掉未生成 + normalizeWorkpaper」的返回形状）；`cycleDirectory.ts`、`AttachVoucherToWpDialog.vue`、`ProcedureTrimming.vue`（原只取第 1 页 100 条，顺带修截断）改用它。
- 验证：PG 测试三种可见性下与分页端点逐页拼接逐条相等；前端服务层单测。

### R6 底稿列表按路径复用页面
- `DefaultLayout.vue`：页面与 ErrorBoundary 的 key 改为 `routeViewKey(route)`：`route.meta.reuseOnQueryChange` 为真时用 `route.path`，否则仍用 `fullPath`。只给底稿列表路由加该 meta，其他页面不变。
- `WorkpaperList.vue` 增加对 `route.query.view / filter` 的监听：按原挂载时的同一规则同步 `viewMode` / `filterStale`（`filter=stale` ⇒ 列表视图）；已有「状态 → 地址栏」的两个监听保持，规则幂等不会互相触发循环。
- 挂载前先核对页面及子视图读 `route.query` 的全部位置。

### R7 底稿列表浅层响应式
- `wpList` / `wpIndex` 改 `shallowRef`（一直整体替换）；`fetchWpIndex` 合并改 `Map`；`WorkpaperWorkbenchView.vue` 里对 `wpIndex.find` 的循环查找改为按 id 的 `Map`（computed 一次）。
- 改前核对：脚本与模板里没有对数组元素的原地修改 / `v-model="row.x"`。

### R8 启动预热
- 先测：仓库外探针在独立进程里跑 `warm_workpaper_sync_registry()`，同时 10ms 心跳测事件循环滞后，滞后超过 200ms 时由监视线程抓主线程栈（`sys._current_frames`），汇总最长段与所在函数。
- 再改（按测量结果取舍）：
  1. `store_projection_response.compute_store_projection_response`：`build_*_store_projection`、overlay、flatten 进 `asyncio.to_thread`（纯 CPU，输入是冻结对象；先例 `wp_sync_router.py` 的 build_projection）。
  2. `published_identity_observer` 第 6~8 段并入已有的 `to_thread`。
  3. 预热专用的让出：注册段 entry 之间、基线段每行之间短暂 `asyncio.sleep`（只在预热路径传入，请求路径冷建不受影响）。
- 不碰被 `onlyoffice_excel_instrumentation_gate.json` 钉住哈希的模块（`excel_structure_fingerprint`）。同步更新钉住调用序列的测试（`test_target_bound_registration_wiring.py`、`test_sync_registration_prewarm.py`、`test_startup_prewarm_loop_offload.py`）。

### R9 数据库参数
- 已执行：`ALTER SYSTEM SET jit = off`、`ALTER SYSTEM SET work_mem = '32MB'` + `pg_reload_conf()`（写入数据卷里的 `postgresql.auto.conf`，容器重建不丢；`-c` 命令行参数里没有这两项，不会被覆盖）。work_mem 取 32MB 而非 64MB：max_connections 200，32MB 已足够消除该查询的有损块。
- 待用户：`shared_buffers`（建议 8GB）、`shared_preload_libraries = 'pg_stat_statements'` 需要重启 audit-postgres。正在运行的容器来自 `D:\GT_workplan\docker-compose.yml`。

## 3. 风险与回退

- R1 开关只给 `useWpRenderer`；后端不带参数零变化。前端展开逐页深拷贝，与原语义一致。
- R2 只扩到核对过的 d1~d7；对拍不等即回退。
- R3 以真库全量对拍为准入；不等则只在 guidance 用完整渲染。
- R6 只对底稿列表生效；其他页仍按 fullPath。
- 每批改完跑相关后端 / 前端测试，并在临时 worktree 干净检出比对失败集合，区分预存失败。

## 4. 实施偏差（以代码为准）

- R1：分组只认对象身份（容器）+ 类型与值（标量），没有非空容器的页签不参与；`share_duplicated_html_data` 与 R2 的常量 / memo 函数放在 `wp_render_config_helpers.py`（`wp_render_config.py` 已到行数门白名单上限，canonical identity 两个函数也原样移过去并 re-import）。路由判开关用 `share_html_data is True`：直接调用路由函数时参数是 `Query` 默认对象（真值），不能按真值判。
- R4：外壳删掉自带实例后，`useWpRenderer` 的 `silent` 选项无调用方，一并删除。侧栏 decision_trace 与编制说明闸门两项放在 `views/workpaper-editor/useEditorRendererFacts.ts`，Univer 目录请求的 wp_code / decision_trace 合成一个 `univerCatalog`（任务 12 回归抓到外壳 1380 行超 `line-budget.spec.ts` 棘轮 1362，按此收回到 1362）。现行 render-config 路由不下发 decision_trace（只有 `wp_render_pipeline.py` 那条路径产出），D1 / D2 / D4 实测都没有该字段，侧栏改前改后拿到的都是 null。
- R5：除设计列出的三处调用方外，`listWorkpapers` 本身改为基于 `listWorkpapersAll`，底稿列表 / 试算表 / G7 推送 / AI 选目标随之一次取完。edit 级影响清单与覆盖台账各补一条（清单生成器在 HEAD 即因 3 处既有问题拒绝写出，按生成器同口径手工插入）。
- R6：key 含 `?year=`（年度变了整页重取，保持原样重挂）；地址栏 → 状态的规则挂载与同页变化共用 `applyRouteQuery`，状态已一致但地址栏 view 不一致时回写一次（浏览器实测抓到：否则取消待重算后按旧 `view=workbench` 跳回工作台）。
- R7：同一写法的生命周期、委派矩阵两个子视图一并改为 computed Map；`indexFirstBy` 同键保留第一个，与原 find 命中同一项。
- R8：测量后没做设计列出的三项线程卸载 / 让出 —— 预热自身停顿已在 1s 以内（合计 6.8s / 42s），最长段是首次导入与已在线程池里的解析，收益小而注册链调用序列被多份测试钉住。改修测量中抓到的 `event_bus.replay_pending_events` `xreadgroup(block=0)`：每次启动白等 5s（`wait_for` 超时），去掉 block。冷启动导入 10s、预热期 1~2s 停顿未解决，见 tasks 任务 11。
