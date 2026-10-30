# 平台响应速度热点 — 任务

基线与口径见 design §1。每个任务完成时写一行实测 / 测试证据。

## 批 0 顺带修复与数据库

- [x] 0. R0 编译错误：`GtChecklistTable.vue` 默认值内联、`MyTemplatesDialog.vue` 去掉 setup 内 export；开发服两组件返回 200；组件单测；全仓 `.vue` 编译扫描 0 失败
  - 证据：开发服两组件 500 → 200；`GtChecklistTable.spec.ts` 4 passed；全仓 2468 个 `.vue` 扫描，剩 6 个是探针解析 `@/` 别名类型的口径问题，逐个请求开发服均 200
- [x] 1. R9 数据库无需重启的参数（jit / work_mem）生效并复测序时账聚合；需要重启的两项写清待用户
  - 证据：`pg_settings` 显示 jit=off、work_mem=32MB（来源 configuration file）；序时账聚合热查询 0.56s → 0.34~0.37s，无有损块；冷读仍约 3s（shared_buffers 128MB，待用户定重启时间）

## 批 1 打开底稿（R1~R4）

- [x] 2. R2 d1~d7 渲染器同请求 memo + 单测；真库 D1~D7 全部底稿开 / 关逐页对拍
  - 证据：守卫 `test_render_config_workbook_scoped_memo.py` 28 passed（AST 扫 7 个渲染器 + 两个 D 循环取数包 + `report_line_accounts.py`：页签相关字段 / `getattr(ctx, …)` / ctx 传给扫描范围外的函数都打红；在真实 `_d2_accounts_receivable.py` 内存副本里注入 4 种页签读取 + 1 个新去向，5 条全被认出）；真库只读对拍（独立引擎 `default_transaction_read_only=on`）5 个项目 27 份 D1~D7 底稿，开 / 关 memo 序列化后逐字节相同、`RenderConfigResponse` 校验通过，渲染器调用 D4 41→2、D1 20→2、D2 16→2，impl 耗时 D4 1.24~1.63s → 66~85ms、安徽 D2 331→49ms；回归 19 个相关测试文件 2481 例，工作树与 HEAD 干净检出失败集合相同（同 13 例预存失败）
- [x] 3. R1 后端 `share_duplicated_html_data` + 路由参数 + 契约字段 + 契约测试；单测覆盖分组规则与「不带参数不变」
  - 证据：`test_render_config_share_html_data.py` 13 passed（分组只认对象身份、标量带类型、空容器 / 单页不共享、不改入参、展开回原响应；TestClient 真发请求：不带参数 / `=0` / `=false` 与基线 wire 相同且无新字段，`=1` 下发共享形状并可展开回基线；直接调用路由函数拿到的是 `Query` 默认对象（实测 `bool(Query(False))` 为真），按 `is True` 判，不会误开）；契约测试按「按参数出现」两项改写，顺带修正预存失败（golden 于 33b3b67fd 重抓后 `not_applicable` 已在真实样本中出现、前端登记 active，原断言过时）；三文件 54 passed。真库只读：重药安徽 929 份底稿 0 报错，93 份发生共享且全部展开后与原响应相等，D2 线上体积 14,718,217 → 996,110 B，全项目合计 36.7 → 18.6 MB。为守 `wp_render_config.py` 行数门（白名单 1135 +5% = 1191），R2 的常量与 memo 函数移到 `wp_render_config_helpers.py`、本文件只留调用（现 1191 行，门禁 exit 0）
- [x] 4. R1 前端类型 / 字段登记 / `expandSharedHtmlData` / `useWpRenderer` 接入 + 单测；真库 D2 等多册对拍展开结果与旧形状深度相等
  - 证据：`renderConfigSharedHtml.spec.ts` 8 passed（逐页深度相等、页签之间 / 与共享块之间不共享对象、不改入参、差异键覆盖、引用缺失抛错、响应式入参、`useWpRenderer` 请求带 `?share_html_data=1` 且不加 config）；字段登记 `shared_html_data: 'active'`，wire 守卫与后端双向契约检查通过；单区域 vue-tsc 本次文件 0 新错（`useWpRenderer.ts` 8 处 `sheet_uid` 为既有）。浏览器（开发服真实模块）：D2 / D4 / D1 带参数响应经 `expandSharedHtmlData` 展开后与不带参数响应规范化深比较相等、页签独立；D2 请求 14.1M → 0.96M 字符、520 → 134ms，展开 20ms；打开 D2 编辑页只剩 1 次 render-config；把 render-config 改回旧形状（拦截改 URL）做 A/B，D2-2 页签正文逐字相同
- [x] 5. R3 `manifest_only` + guidance 改用 + 单测；真库重药安徽全部底稿清册对拍
  - 证据：`test_render_config_manifest_only.py` 2 passed（同一套桩：完整渲染调渲染器 2 次 / 加载 schema 4 次 / 查库 >3 条，清册模式 0 / 0 / 3 条；清册与完整渲染的身份元组、componentType（含「无渲染器 ⇒ onlyoffice-sheet」改写）、template_version 逐项相同）；`test_wp_guidance_router.py` 钉住 guidance 传 `manifest_only=True`。真库只读：重药安徽 929 份底稿清册（template_version / redirect / 每页 sheet_name·sheet_code·sheet_code_reason·whole_workbook·componentType 与顺序）929 份全同，guidance 实际消费的 `normalize_render_sheet_facts` 摘要 928 份全同、1 份两种模式抛同一 ValueError；impl 合计 163.4s → 8.6s。接口：D2 guidance 629ms → 103~129ms。为守行数门，canonical identity 辅助函数原样移入 helpers 并 re-import（引用它们的两个测试文件通过）
- [x] 6. R4 外壳不再自带 render-config 实例、编制说明闸门 + 同步测试
  - 证据：外壳去掉 `useWpRenderer`，侧栏 decision_trace 读 `GtWpRenderer` 暴露的 `renderConfig`（Univer 读目录请求顺带取到的配置），编制说明面板按 `guidanceContextReady` 挂载；`useWpRenderer` 的 `silent` 选项随之无调用方、已删。`WorkpaperEditor.chainWiring.spec.ts` 7 passed（新增两例）、`editorDetailRace.spec.ts` 4 passed（外壳实例两例改为 GtWpRenderer 主路径对照），相关 6 文件 40 passed。单区域 vue-tsc（20GB 堆；变异注入 2 处均报 TS2322）改动文件与 HEAD 错误逐条相同。浏览器打开 D2：render-config 1 次（原 2 次）、解码体 0.99MB（原 2 × 14.7MB），guidance 1 次且带 `sheet_name=底稿目录`（原 2 次），点开编制说明栏内容正常、不再多发请求；D4 同样 1 + 1
  - 注：首屏最后一个接口仍在 2.9~4.0s（两次实测），没随请求量变小而变短：瓶颈是串行瀑布（布局层 `custom-query/indicators` 约 1.06s、`projects/tree` / `role-context/me/homepage` 约 0.73s → 归类 + 前置状态约 0.62s → render-config 约 0.39s → guidance / 能力快照约 0.39s），且轻接口在浏览器里普遍 300~600ms（服务端单测 7~10ms），指向事件循环被占，留给任务 11（R8）与任务 12 复测

## 批 2 底稿清单（R5）

- [x] 7. R5 后端 `working-papers-all` 端点与服务方法 + PG 测试（三种可见性与分页逐页拼接相等）
  - 证据：`list_all_workpapers`（同一可见集 / 业务过滤 / 去重 / hydrate + 姓名，排序 wp_code ↑ + wp_index_id ↑，异常 fail-closed 空集）+ 路由 `GET /api/projects/{pid}/working-papers-all`（`require_project_access("readonly")` + 服务端角色分类）。PG 测试 `test_workpaper_list_all.py` 12 passed（admin / supervisor / restricted × 无过滤 / 循环 / 文件状态共 9 组与分页 2 条一页逐页拼接逐条相等；三种可见性结果确有差异；空可见集；路由层），连同原分页测试 42 passed。真库接口：929 份一次 98ms（685KB），分页 10 次串行 1615ms，逐条相等；`audit_cycle=D` 36 份 56ms。edit 级影响清单手工补一条（生成器在 HEAD 即因 3 处既有问题拒绝写出），覆盖台账补一条（照 `working-papers-kanban` 先例 non_wp_bound；本路由漂移 0，`test_x3_entry_coverage_ledger.py` 11 passed）。回归 30 个相关测试文件：工作树失败集合是 HEAD 的子集（HEAD 多 1 例 wire contract 预存失败已在任务 3 修正）
- [x] 8. R5 前端 `listWorkpapersAll` 与调用方改造 + 单测同步
  - 证据：`listWorkpapersAll`（同项目 + 同过滤在途共享，各调用方拿独立数组与浅拷贝项）；`listWorkpapers` 改为基于它（返回形状不变：去掉未生成、normalizeWorkpaper），底稿列表 / 试算表 / G7 推送 / AI 选目标随之一次取完；`cycleDirectory.ts`、`AttachVoucherToWpDialog.vue` 去掉逐页循环，`ProcedureTrimming.buildSuggestionTargets` 原只取第 1 页 100 条，顺带修截断。`workpaperVisibilityApi.spec.ts` 按新口径改写（11 passed），3 个裁剪页测试的 mock 名与 `delegationSuggestionTable.spec.ts` 的接线判据同步，5 文件 218 passed；另跑引用这些服务的 3 组 40 例，工作树与 HEAD 干净检出同为 10 例预存失败、失败名逐条相同。浏览器：底稿列表进入时只发 1 次 `working-papers-all`（原 10 页串行）

## 批 3 底稿列表页（R6、R7）

- [x] 9. R6 路由按路径复用 + 底稿列表监听 view / filter + 测试
  - 证据：`utils/routeViewKey.ts`（默认 fullPath；`meta.reuseOnQueryChange` 的页面按路径 + `?year=`）；DefaultLayout 页面与 ErrorBoundary 两处 key 改用它；只给 WorkpaperList 路由开启。页面「地址栏 → 状态」挂载与同页 query 变化共用 `applyRouteQuery`（同一规则：`filter=stale` ⇒ 列表 + 待重算，否则白名单 view，否则工作台）。浏览器实测抓到 1 处回归并修复：已在列表视图时跳 `?view=workbench&filter=stale`，状态不变 ⇒ 地址栏留着 `view=workbench`，之后取消勾选跳回工作台（原先挂载时总会写回 view=list），现改为状态已一致但地址不一致时回写一次。`routeViewKey.spec.ts` 6 passed + `workpaperListQueryReuse.spec.ts` 7 passed；磁盘变异 8 条（去掉监听 / key 改回 fullPath / 去掉开关 / key 不含年度 / 改回深层 ref / 索引留最后一个 / 挂载不按地址栏 / 不回写地址栏）全部只打红对应用例；列表页、布局、路由相关 18 文件与 HEAD 失败集合逐条相同（5 例预存）。浏览器同口径对比（R5 后 → R6/R7 后）：点「列表」页签 4 个接口 / 重挂 → 0 / 同一实例；站内跳 `?filter=stale` 10 个接口 / 重挂 → 0；取消勾选、后退均 0 接口且停在列表
- [x] 10. R7 底稿列表浅层响应式与按键查找 + 测试
  - 证据：`wpList` / `wpIndex` 改 `shallowRef`（只在 fetchWpIndex 整体替换，全仓核对无元素原地修改）；合并与 `batchAssignWpList` 改按 id 的 Map；子视图里同一写法的工作台（4 处）、生命周期、委派矩阵一并改为 computed Map；新工具 `utils/indexFirstBy.ts` 同键保留第一个（与原 find 命中同一项，变异「保留最后一个」被打红）。浏览器：进入底稿列表最长任务 1243ms → 815~986ms，点「列表」页签 589ms → 398~412ms。`WorkpaperWorkbenchView.vue` HEAD 已 1764 行未登记行数门（line-budget 1210 在 HEAD 即红），本次 +4 行，已登记 whitelist 1768 并写拆分方向

## 批 4 启动预热（R8）

- [x] 11. R8 预热期间事件循环滞后测量（独立进程探针），按结果修改并同步测试；复测轻接口 p95
  - 测量：独立进程（与启动同一路径：选择器事件循环 + configure_gc + run_then_freeze，只读库）10ms 心跳 + 停顿抓栈：预热 42.2s，停顿合计 6.8s、最长 0.65s、>0.5s 仅 3 次，采样落点主要是预热里首次 import 的大模块（`wp_sync_router` / `excel_extract` 一串约 1.8s）；C 调用剖析里最长的解析（`_read_cell_view` 0.81s、`XMLParser.feed` 0.63s）已在线程池里跑。8 天日志 718 条 >3s 慢请求，605 条落在后端（含热重载）启动后 120s 内，启动 4.1 次 / 小时；稳态 113 条里 55 条是 10s 轮询的 `ledger-import/active-job`（表只有 20 行，是被事件循环占用连累的受害者）。
  - 改动（按测量结果取舍，与设计 §R8 的偏差见 design §4）：线程卸载未做 —— 预热自身停顿已压到 1s 以内，剩下的长段是导入与已在线程里的解析，卸载收益小、而注册链调用序列被多份测试钉住；改修实测抓到的确定性浪费：`/api/health` 启动报告里 `replay_startup_events` 恒 5050ms —— `event_bus.replay_pending_events` 用 `xreadgroup(block=0)`，Redis 的 BLOCK 0 是无限等，Stream 没有新条目时挂到启动任务的 `wait_for(5s)` 超时，每次启动（含热重载）白等 5 秒才开始服务，重放报告也从不更新。去掉 block（与旧 Stream 条目语义无关：只影响「没有新条目时」立即返回）。
  - 证据：临时键实测 redis-py 7.4 `block=0` 2s 仍挂、不传 block 4.8ms 返回；`test_event_bus_replay_nonblocking.py` 3 passed（按 BLOCK 语义的假 Redis + 守卫自身复现旧挂起 + 真 Redis 一次性键，断言 `redis_available` 防「连不上也很快返回」的假绿）；磁盘变异改回 `block=0`，假 Redis 与真 Redis 两例打红；连同 outbox / 启动注册 / 事件总线测试 81 passed。热重载后实测：启动报告 `replay_startup_events` 5050 → 536ms；`/api/version` 每 0.5s 一次共 16.4 分钟：p50 3.2ms、p95 27ms、p99 86ms，重载那次 15.0s 不可用（导入 `app.main` 实测 10.0s + 启动任务约 1s），随后约 35s 预热期间 8 次 1.0~1.8s
  - 未解决（如实列出）：导入 10s、热重载期间的不可用与预热期 1~2s 停顿仍在；共享开发环境里主要靠少重载（已有 `GT_BACKEND_NO_RELOAD=1`），根治要把冷启动拆到独立进程或按需导入，超出本 spec

## 收尾

- [x] 12. 同口径复测（接口耗时、浏览器页面、CPU 剖析）写回本文件；相关测试在干净检出下比对失败集合；INDEX 登记；清理临时文件
  - 接口（顺序请求、不压缩，后端稳态）：D2 render-config 不带参数 90~97ms / 14.7MB（基线约 450ms，R2 memo 对不带参数的请求同样生效），带 `share_html_data=1` 65~103ms / 0.998MB；D4 87~134ms / 489KB → 79~104ms / 36KB；D2 guidance 89~96ms（基线 629ms）；working-papers-all 94~109ms / 685KB，分页 10 次串行 1708ms，逐条相等；轻接口 20 次中位：`/api/version` 1.5ms、未读数 30ms、项目详情 28ms、角色首页 29ms（与基线同档，本 spec 未动这一层）
  - 浏览器前后对照（同一后端、同一时段 A / B 交替 3 轮；A = 3030 开发服；B = 另起一个 Vite（3031），只把本 spec 改过的 15 个前端运行时文件在内存里换回 HEAD 版，其余同 3030；两边都经 127.0.0.1 访问；B 已用上新后端，不是完整基线，完整基线见 design §1）：
    - 进入底稿列表：最后一个接口 3069~3109 → 1340~1379ms，接口 31 → 22 个（分页 10 次 → 1 次），最长任务 1103~1114 → 794~808ms；随后点「列表」/ 跳 `?filter=stale` / 取消勾选：B 每步 14 / 19 / 14 个接口、整页重挂、1.9~2.7s 才静下来，A 每步 0 个接口、同一实例、34~474ms
    - 进入试算表：最后一个接口 2647~2667 → 1122~1258ms，接口 44 → 35 个（分页 10 次 → 1 次）
    - 打开 D2：最后一个接口 1788~1800 → 1387~1473ms，接口返回解码后合计 30.4MB → 2.6MB（render-config 2 × 14.4MB → 1 × 0.97MB，guidance 2 → 1）
    - CPU 剖析（CDP 采样 0.5ms，按 esbuild 预构建块里的包注释归类，各两轮）：进入底稿列表 1871~1891 → 1467~1484ms，其中 `@vue/reactivity` 自耗时 426~442 → 168~195ms；进入试算表 1606~1721 → 1204~1213ms（差在 NProgress 与 (program)，请求少了）；打开 D2 1163~1208 → 960~995ms
  - 复测新发现（未改，待用户定）：浏览器地址用 `localhost:3030` 时每个新连接多等约 300ms（Chromium 先连 ::1，Vite 只听 IPv4，300ms 后才改连 IPv4）。同一步骤（空闲 6s 后进入底稿列表）：`localhost` 22 个接口里 13~14 个新建连接，其中 9~10 个建连 283~315ms，单个接口中位 325ms；`127.0.0.1` 建连 0~1ms、中位 59~64ms。整页（同一探针交替两轮）：打开 D2 3086~3307 vs 1594~1653ms，进入试算表 3845~4036 vs 1329~1628ms。start-dev 打印的前端地址本来就是 127.0.0.1:3030。任务 6 注里把浏览器里轻接口 300~600ms 归因于事件循环被占，复测证实主要是这个建连回退（本 spec 此前的浏览器探针都用 localhost）
  - 收尾回归抓到 1 处本 spec 引入的失败并已修：`views/workpaper-editor/__tests__/line-budget.spec.ts` 外壳棘轮 1362 行，R4 后 1380 行。侧栏 decision_trace 与编制说明闸门移到 `views/workpaper-editor/useEditorRendererFacts.ts`，Univer 目录的 wp_code / decision_trace 合成 `univerCatalog`，外壳回到 1362 行；新用例 `useEditorRendererFacts.spec.ts` 8 passed，磁盘变异 4 条（未暴露 loading 也算加载完 / HTML 与 Univer 取值对调 / 闸门漏 wholeWorkbook / Univer 不等目录）各打红、逐字节恢复；接线用例同步；单区域 vue-tsc：`WorkpaperEditor.vue` 7 条与 HEAD 逐条相同，新文件 0 条。浏览器打开 D2 仍是 1 次 render-config + 1 次 guidance（`sheet_name=底稿目录`），编制说明内容正常
  - 失败集合（候选树 = HEAD ef098c305 + 本 spec 文件；edit 级影响清单在 HEAD 版上只插本 spec 一条，与工作树那一条逐字段相同）：后端：引用改动模块的测试 + 原回归清单 + 事件总线 / 启动 / 预热，候选 90 个文件 / 目录（HEAD 85 个，少本 spec 新增的 5 个），候选 3788 例 46 失败、HEAD 3729 例 47 失败，候选是 HEAD 的子集（HEAD 多的 1 例是任务 3 修正的 wire contract 用例）；46 例共同失败里 36 例信息相同，10 例只差行号 / fd / UUID / 源码片段（`test_wp_large_file_size_guard` 报 `wp_render_config.py` 候选 1124 行、HEAD 1183 行）。前端：引用改动模块的测试，候选 143 个文件（HEAD 139 个，少本 spec 新增的 4 个），候选 2112 例 28 失败、HEAD 两次 2076 例 30 / 29 失败，只在候选失败的 0 例；只在 HEAD 失败的是 `GtChecklistTable.spec.ts`（R0 编译错误）与偶发红的 `DefaultLayoutNavigation.pbt`。未处理错误全部来自 `WorkpaperListShell.spec.ts`：HEAD 两次 12 / 13 条、候选两次 13 / 14 条，多出的是 NProgress 定时器在测试环境拆除后触发的 `document is not defined`，候选单独连跑 6 次均 12 条。行数门：本 spec 51 个代码 / 数据文件（含收尾新增的 2 个）exit 0
  - 后续建议（未做）：①冷启动导入 10s 与热重载期间不可用（见任务 11）②每请求固定开销：30 个并发轻请求单个约 355ms、顺序约 29ms（单事件循环排队）；路由表 2550 条线性匹配，匹配到未读数（第 2419 条）约 1.13ms；11 个中间件里 9 个是 `BaseHTTPMiddleware` ③数据库 `shared_buffers` / `pg_stat_statements` 需重启 audit-postgres（见任务 1）
  - 清理：仓库外探针目录、临时 Vite（3031）及其 `node_modules/.perf_probe` 缓存、临时 worktree 均已删除
