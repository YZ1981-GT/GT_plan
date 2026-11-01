# 实施计划：S3　写入方归属与过期状态机（formula-writer-ownership-and-stale）

> 以 requirements.md 和 design.md §11 为准，需求编号 R1~R4。
> 本版任务顺序先重基线，再改生产代码；旧设计中“14 处写入点”“saved.data.rows 缺陷”“R4 固定 14 处”均不得直接照抄。
> 当前文档重整轮只修改三件套，不执行下列生产任务、不执行 D1 拍板，不修改 INDEX/memory。
>
> 通用纪律：临时产物放仓库根 `tmp_writer_ownership/`；PG 写入只在回滚事务内的【测试】项目；标完成必须有真实代码、测试和至少一条磁盘变异，变异单独运行并 sha256 恢复；提交前在干净候选树运行要提交的树并与 HEAD 基线按测试节点比较；禁止用并发会话的脏工作区代替候选树。
> 前置：母 spec `formula-hub-integrity-closure` 已入库；S4 `formula-settings-durable-outbox` 已完成，但其附注 stale 写入必须在任务 1 接入本 spec 的 `stale_state`。

## 第一阶段　不依赖 D1

- [x] 0. 当前树重基线与清单冻结
  - 现算并保存当前 HEAD、候选树、源码 sha256、`DisclosureNote` stale 标记/清除全清单、S4 接缝、重算入口、试算表持久化链和全部写请求 AST 清单。
  - 产物：`tmp_writer_ownership/baseline/baseline.json`、`disclosure_stale_writers.json`、`write_validate_status.json`、`tb_persistence.json`；清单按模块/函数身份记录，不写死行号。
  - `validateStatus` 探针必须解析 `api` / `http` / `httpApi` 等别名，区分 POST/PUT/PATCH/DELETE 和合法 GET 例外；禁止用就近文本匹配替代 TypeScript AST。
  - Verify：现算值与旧 14 处分母差异写入 design §11 末尾；若 HEAD 在任务期间前移，候选树重跑；任务 1~5 不得引用旧数字。

- [x] 1. 统一附注 stale 写入口（R2，ADR-WOS-01）
  - 新建 `backend/app/services/stale_state.py`，实现 `StaleSource`、中文 label 映射、`mark_note_stale`、`clear_note_stale`；只用调用方 `db`，只 flush，不 commit/rollback。
  - 接入 design §11.2 的全部当前写入/清除路径：`disclosure_stale_marker`、事件处理器、`consol_note_stale_handler`、`stale_propagation_engine`、S4 `formula_settings/stale_marks.py` 与 `propagation.py`、`note_stale_service`、`report_note_sync_service`、公式推送、底稿同步和附注刷新。
  - `_mark_stale_by_uri` 显式透传传播起点 source；失败原因返回结果和结构化日志，不写 `table_data._stale_reason`。
  - 建立 AST + 原生 SQL 守卫：`DisclosureNote` 的 stale 写入只能出现在 `stale_state.py`，其他模型的 `is_stale` 不误报。
  - Verify：指定章节/整项目标记与清除、source 非法值、只 flush 不 commit、PG 回滚；变异恢复任一直接 stale 写入或删除 source，守卫必须变红；新产生 stale 行 source 非空率 100%。

- [x] 2. 重算成功与值变化分离（R2，ADR-WOS-02）
  - 扩展 `DisclosureEngine.RefillReport`，保留旧字段兼容，同时增加 `requested_sections`、`changed_sections`、`recomputed_sections`、`failed_sections`、`cleared_sections`、章节级 `errors`。
  - 成功集合必须覆盖绑定取数、表内公式二次求值和最终公式写回；值不变进入 `recomputed_sections`，但不进入 `changed_sections`；纯文本、缺表、部分失败不能清 stale。
  - 接入 `refresh-all-bindings`、`refresh-from-workpapers`、单章节刷新、`NoteStaleService.refresh_stale_sections`、后台事件刷新及公式推送；公式阶段失败的章节不得因仍在旧 `sections_recomputed` 中而被清除。
  - Verify：真实生产 `refill_sections` 链测试值变/值不变/纯文本/resolver 失败/公式失败五类；变异把成功判据改回“值变化才成功”必须红，把失败章节加入清除集合必须红。

- [x] 3. 写入方登记表冻结（R1a，ADR-WOS-03）
  - 新建 `backend/app/services/note_writers.py`，登记 `writer_id`、入口、触发、作用域、标准、规范字段、`_cell_modes`、事务边界和状态。
  - AST/SQL 守卫覆盖属性赋值、构造/更新载荷、`flag_modified`、SQLAlchemy `values(table_data/text_content)`、原生 SQL、writeback adapter、JSONB 原地修改和 `DisclosureEngine.update_note` 闭包；不得只扫描直接赋值。
  - 复用既有 `*SyncPayload` builder 守卫，任务 0 重新现算分母；不在本任务执行唯一写方拒绝。
  - Verify：登记入口真实存在、`writer_id` 不重复、字段键合法、排除项可伪证；新增未登记 writer 变异必须红；前端 builder 清单只许减少。

## 第二阶段　现有实现核验与写请求收紧

- [x] 4. 试算平衡表持久化核验（R3，ADR-WOS-05）
  - 先核验 `TrialBalance.vue` → `useTbSummaryPersistence` → `loadWorksheetData/saveWorksheetData` 的现有链路；不重复建设旧的 `saved.data.rows` 读取方。
  - 必须读回 `content.rows`、零值、手工未审数、手工重分类、`formula_detached` 和 CAS 版本；页面刷新后逐行比对，非 2xx 不得显示保存成功。
  - 只有当前链路不满足契约时才修改实现；不新增“保存后立即 GET”，除非另有明确性能/一致性决策。
  - Verify：既有持久化 vitest、后端 `consol-worksheet-data` 端点用例；变异改回 `saved.data.rows` 或丢掉零值/断开标记必须红；【测试】项目浏览器刷新读回。

- [x] 5. 写请求按状态码判成功（R4，ADR-WOS-06）
  - 消费任务 0 的 `write_validate_status.json`，只改 AST 判定为 POST/PUT/PATCH/DELETE 的违规点；保留合法 GET blob/轮询兼容。
  - 新增 `writeRequestValidateStatusGuard.spec.ts`：识别导入别名和包装客户端；宽放行变异、显式 404 例外和测试夹具误报均需有正反向断言。
  - 至少补一个 `useEditorSave` 或同类真实 composable 的 409/422/500 行为用例，断言不显示成功、不清 dirty、不推进版本。
  - Verify：受影响组件 vitest、单区域 vue-tsc；注入一处类型错误必须报错；任一写请求恢复 `s < 600` 守卫必须变红。

## 第三阶段　D1 后唯一写方

- [ ] 6. 章节 × 字段唯一写方强制（R1b，ADR-WOS-04，依赖 D1）
  - D1 未拍板时保持 `[ ]`，不得以默认意见代替用户决策；先把决议写入 design §11.10，再生成矩阵。
  - 矩阵键至少为 `(template_type, note_section, table_key, field_key)`，值为唯一自动 writer 和 manual/locked 策略；未知矩阵项 fail-closed。
  - 非所有者自动写入跳过该字段但继续合法字段，记录结构化 `blocked_write`，响应带 `blocked_writes`；手工入口仍需权限/项目锁，自动 writer 不得覆盖 locked 单元格。
  - Verify：每个受限 writer 至少一条“该字段被拒、其他字段照写”用例；矩阵缺行、错误 template_type、locked/manual 变异均须红。

## 第四阶段　回归与收尾

- [x] 7. 候选树回归、浏览器和文档收尾
  - 候选提交树与 HEAD 按测试节点比较；后端单元/PG、前端 vitest、单区域 vue-tsc、磁盘变异全部只允许候选新增红为 0。
  - 浏览器使用【测试】项目：附注已知/未知/未记录来源展示；值不变刷新清 stale 并显示 `recomputed`；失败章节仍过期；试算表手工值/零值/断开标记刷新读回；写请求失败只显示错误。
  - 确认 `formula-settings-durable-outbox` 的只候选红没有被 S3 接线引入；清理 `tmp_writer_ownership/` 前保留必要证据摘要。
  - 最终提交前另行按仓库纪律更新 INDEX/memory；本轮三件套重整不提前修改这两个共享文件。
  - Verify：生产路径调用方、注册、挂载和浏览器均有证据；不得只凭模块级单测标绿。
  - Evidence（2026-11-01）：后端 S3/S4/formula-push 选集 **97 passed**，真实 PG 回滚 **1 passed**（事务内 `【测试】S3 stale 状态机回滚`，独立会话反查项目/附注均 0）；前端父/候选同口径 **candidate-only red = 0**，新增守卫 9 passed，收尾运行时修复 75 passed，单区域 tsc 0 错，Vite 正式构建 3804+ 模块通过；任务 5 五条磁盘变异全红、三条阴性对照全绿且逐字节恢复。
  - Browser（隔离端口 3032/9982，`【UAT】子公司A` 测试上下文，所有写请求由 Playwright 拦截、共享库零写）：**17/17**——500 不显示成功且只请求一次、429 业务分流；adjustment/未知/NULL 三态中文；值不变显示 recomputed+cleared 且 stale 标签消失；失败章节仍过期且不显示“数据已是最新”；TB 零值、手工 RJE 12.34、`formula_detached` 刷新读回；pageerror 0。截图与 JSON 在 `tmp_writer_ownership/`。
  - Runtime note：浏览器首次启动依赖 5 个 batch-project 临时 overlay，随后已由并发提交 `86005b6b6` 正式补入。验收期另修 6f4c5a54a 的三组整文件回退（AI 笔记目标选择、D3 凭证证据）及两个从未提交的组合式模块（首次挂载、附注保存竞态）；最后移除 `pm_dashboard` 中已被新状态机路由替代的旧 batch-review 端点、补齐显示偏好审计脱敏 helper，`app.main` 干净导入且 batch-review 唯一路由已验证。全量路由遮蔽守卫另有 14 条父提交预存红，未扩散处理。正式构建钉住完整前端导入链。
