# 技术设计：ACNR 地址坐标名称库底座缺陷收口（acnr-foundation-defect-closure）

> 修订轮 1（2026-10-26）：逐条回应 `design-review.json` 的 34 条意见（HIGH 5 / MEDIUM 11 / NIT 18），回应表见 §19。需求原文随之修订的条目在 §19 末尾列出。
> 修订轮 2（2026-10-27）：逐条回应第 2 轮评审（HIGH 4 / MEDIUM 9 / NIT 10），回应表见 §20。R2-F1（孤儿 cell 判无效）与 §16 Q0（跨 spec 冲突以本 spec 为准）由用户拍板；R2-F2~F4、F5~F13、N1~N10 均在相应节内落实。本轮现算证据 `tmp_acnr_foundation/out/q01~q06`（HEAD `bb7aff842`）。

## 0. 概述

本设计把需求 1~14 落成可直接实施的方案。总体思路：目录只由生成器写出，写出前跑一组发布门禁（`catalog_release`）；身份判定（`exact_identity`）、显示名（`display`）、底稿单元格读取（与 formula-hub 共用的 `wp_cell_reader`）各只有一个实现，后端、门禁、CCR 检查器、V2、stale 引擎、前端都从这一个实现取值；带项目的取值和写 stale 一律先过项目鉴权；拒绝都给中文原因，不表现为 0、空结果或成功。

技术栈沿用现状并锁定：后端 Python 3.12 + FastAPI + SQLAlchemy 2（async）+ pydantic v2，运行时迁移 `MigrationRunner`，校验库 `jsonschema==4.26.0`（新钉）；前端 Vue 3.5 + TypeScript 5.6 + Pinia 2 + Element Plus，单测 vitest；守卫用 Python `ast` / `symtable`、TypeScript 编译器 API 与 `@vue/compiler-sfc`（`.vue` 的 `<script>` 与模板表达式）。不引入新依赖。

现算口径：HEAD `b5fc200e0`（修订时复核未变）；探针 `tmp_acnr_foundation/probes/p01~p49`，输出在 `out/` 同名文件；评审方证据 `tmp_acnr_design_review/out/r01~r06`。下文「现算」均为本设计阶段重算。

## 1. 现算基线、需求 A2 裁定与并发边界

### 1.1 与审计报告的差异

| 项 | 审计报告 | 现算 | 说明 |
|---|---|---|---|
| 孤儿 cell | 25（I6-7、J2-5、J3-4、J3-5、M6-5） | 25，同上（5/5/6/4/5） | 一致 |
| schema 错误 | 512 | 512 = registry_version 1 + functional_type 201 + purpose 301 + item_id 为数组 9 | 一致 |
| 别名冲突 / 未登记别名 | 5 / 28 | 已提交报告 5 / 28；生成器现算 4 / 28 | 「附注披露信息（国有企业）」改名「（国企）」后并组；报告与目录不是同批 |
| gap_count | 33（gaps 为空） | 生成器现算 32，gaps 仍为空 | gap_count 混入冲突、未登记、skip |
| addr_id / sheet_code 重复 | 0 | 0（4 份快照也是 0） | 一致 |

### 1.2 本轮新增事实（需求未记录，设计据此调整）

- **同父同名 sheet 78 组**（p33）：`(parent_wp_code, sheet_name)` 重复，绝大多数是「父级自身条目借用了子表的 tab 名」（H1 与 H1-1 都叫「审定表H1-1」）。按 §6.2 的编码词元规则，70 组可确定唯一所属（「审定表H1-1」只属 H1-1），8 组仍多义：A21 / A22 / A23 / F2 的「底稿目录」、A3「Word附注」与「已审比率分析」、B50「相关资源」、S32「S32程序表」。静态数据里用同名组名称的三参写法 26 处（CCR 15、`formula_presets_seed.json` 10、`prefill_formula_mapping.json` 1），全部落在可裁决的 70 组，旧解析器全部给了借名的父级（H1），新规则给名称所属的 sheet（H1-1）；8 个多义组没有任何真实写法。PG：`wp_formula` 含 WP 的 18 行三参 0、同名组写法 0；`report_config` 含 WP 0 行（r03）。
- **平台底稿索引名**：372 条索引名写法父级内唯一、并入别名后与既有名不冲突（r05：0）；父级内一名多码 9 组（如 D1 与 D1-1 都叫「应收票据审定表」），记为禁止别名。
- **底稿取值的数据现状**（p32b）：未删项目 1738 份底稿，`parsed_data` 为 SQL NULL 1427、空对象 277、JSON null 4、只有非单元格键 29、含 `html_data` 1；有 `checklist_responses` 的底稿 146 份（全部 `parsed_data` 无单元格）；`file_path` 非空 1252。目录 474 格中 `purpose=conclusion` 的文本格 106。
- **sheet 级底稿实例**（p44、p45）：目录 cell 所在的 163 个 sheet 编码，在项目 `wp_index` 中都出现过独立行；有文件的 sheet 级底稿 210 份，其中 108 份是含本编码 tab 的整本工作簿副本、84 份单表。`resolve_instance` 以 `wp_index.wp_code == sheet_code` 绑定实例（resolver.py L882），取值必须与它同口径（§2.4）。
- **stale 图身份**（p35）：图中 WP 键 47073。旧正则把 1869 个键压进 813 个碰撞组且全部错并。新规则（§10）分类：已登记 cell 5、未登记 A1 格 19264、语义标签 938、同名歧义 283、sheet 不在目录 25515、底稿不在目录 324、非四段形态 744；581 个身份键合并多种写法，均为同一 sheet、同一末段。
- **K14~K18**（p38、p39）：模板目录只有 K0~K13，2025 映射 0 条；4 个未删项目各有 1 份底稿（和平药房缺 K17），`parsed_data` 全空，3 个项目有文件；公式引用 0。这些项目只有 H10、K10、G11、G13、K7 父底稿，没有 sheet 级的 H10-1 等实例。
- **D5-1 是 D5 册的审定表，不是独立 sheet**（p39、p49）：D5 册 8 个 tab，审定表 tab 名「审定表D5」（D1/D3/D6/D7 的审定表都编 n-1）；映射里 D5 与 D5-1 同名同科目「应收款项融资审定表」；标签源 D5-1 =「应收款项融资审定表D5-1」；3 个项目的 D5-1 底稿 2 份无文件、1 份是只有一个「D5-1」tab 的占位册，均无数据。
- **13 张种子名不一致 sheet 的 47 个坐标**（p42，修正了 p22 的 StopIteration）：在模板已用范围内且行有文字 31、行空 2、超出模板已用范围 14（F3-6 E30、F4-3 E50~H50、G14-2 E40/F40/B50、G8-3 E30/B35、J1-3 F30~I30）；在范围内的格，行文字与种子语义均不符。静态数据与 PG 中引用这 47 个 addr_id 的 0 处（p43）。
- **归档状态**（p38）：142 个项目（含软删）没有任何一个 `status=archived` 或有 `archived_at`，`archive_jobs` 0 行。
- **项目审计年度**（p38）：85 个未删项目中 `audit_year` 与期末都有 4、都没有 73、只有 `audit_year` 8；`EXTRACT(YEAR FROM audit_period_end)` 对这 8 个取不到。
- **业务视图并发解析**：`AddressingService.resolve_many` 用 `asyncio.gather` 在同一个 `AsyncSession` 上并发 `full_resolve`，带项目时会查库，SQLAlchemy 异步会话不允许并发操作，异常被归为 `resolve_unavailable`。
- **下钻在新标签页丢登录**：`useAcnrDrill.drill` 用 `window.open(route, '_blank', 'noopener')` 打开站内路由，新标签不复制 sessionStorage（ai-chat-adopt spec 已修过同类问题）。
- **绕过点基线**（§14.1，修订后口径）：BP-1 8 处 / 7 个文件；BP-2 按 R2-F12 窄定义实施时现算后冻结（旧「47 处 / 12 个文件」不可复现，r07 C 现算约 10 文件 / 35 处且 9 个只读 CCR 业务规则）；BP-3 3 个文件；BP-4 `useWorkpaperRegistry(` 3 处 + `/api/workpapers/index-resolve` 1 个文件 + `/api/wp-index-resolve` 2 个文件。前端无参 `useAcnr()` 28 处 / 27 个文件（p40）。`notifyCellChange` 只有路径常量。全局异常处理器集中在 `app/main.py`。

### 1.3 需求 A2：classification 离线缓存与库表（现查与裁定）

| 维度（p30、p30b、p30c、r04、r06） | 离线缓存 `sources/classification_cache.json` | 本地库表 `workpaper_sheet_classification` |
|---|---|---|
| 行数 / 模板版本 | 4640 行，全部 `bbc0190d…`（库中无此版本） | 3875 行，全部 `d3710183…`（v2025-R5，唯一 is_current） |
| distinct wp_code | 1215（= 目录 sheet 数） | 444（全部也在缓存中；其中 443 个编码的 sheet_name 集合与缓存完全相同，只有 S17 不同） |
| 仅一侧有的 (wp_code, sheet_name) | 773 = 772 条 sheet 级拆分记录（771 个编码）+ S17 的占位「S17」 | 8 条，全部是 2026-10-25 S17 补分类 |
| 拆分记录能否由库表复算 | 759 条的 sheet_name 是库表父码记录之一；13 条没有库表依据（A18、A18-1、A18-2、A26、A26-1~4、A27、A27-1、B5 的纯编码名，及 F1-12、L2A 各 1） | — |
| functional_type | 共有 pair 3867 中 675 条缓存有值、库表为空；拆分记录 194 条同类 | 未跑 `infer_functional_type` |

裁定：**生成器的 classification 权威输入是已提交的离线缓存**，本地库表不是权威环境。理由：缓存是「库表 + `split_classification_wp_codes --apply` + `infer_functional_type`」的物化结果，来自另一个环境的库（模板版本号不同）；本地库缺 771 个拆分编码与 869 条 functional_type，若以库表为准，目录会少 771 张 sheet，违反铁律 3。差异处置：

- 772 条拆分记录、869 条 functional_type：以缓存为准，不动；
- 13 条无库表依据的拆分记录：保留（都是目录在用的 sheet），登记进 `sources/classification_reconcile.json` 的 `cache_only_without_db_basis`；
- S17 新增 8 条：本 spec 不并入（会新增 S17-1/2/3/11/21 并改 S17 的名称，属 S 循环在研范围），登记为 `db_newer_than_cache`，刷新流程见 §16 Q11；
- `export_classification_cache.py` 直接按本地库重导会丢掉 771 个编码：本 spec 不改它，§5 的不可变门禁会拦下由此产生的目录（删除已发布 addr_id）。

可伪证的报告：生成器把缓存的 `template_version_id`、记录数与 sha256 写进报告 `release.classification`；`test_classification_cache_vs_db_pg.py`（`pg_only`、只读）现算上表，断言「库表 current 版本的每个 (wp_code, sheet_name) 都在缓存里，例外恰为登记的 8 条」与「缓存独有编码要么能由库表父码记录复算，要么在 13 条登记清单里」，清单有失效条目也红。需求 A2 原文据此修订。

### 1.4 并发 spec 复用与边界

| 产物 / spec | 现状（2026-10-26 核对） | 本 spec 用法 |
|---|---|---|
| formula-hub-integrity-closure（INDEX 0/40） | ADR-FHIC-06 第 1~2 点与 §8.2 定义 `wp_cell_reader.resolve_wp_cell` 契约（现读无 `reason_code`/`raw`、无 A1 分支），任务 22 先提交；同时改 `evaluate_wp_formula_expression` 两个 WP 代入循环 | 逐字采用其契约与先后（§2.4）；只做三参接线与 acnr_targets 调用；**J1 两字段（`reason_code`/`raw`）走回退流程 B 由本 spec 单独追加（§2.4），不假设对方已写同一段**；三参循环的 A1 分支由本 spec 单独落地（§2.5），`formula_wp_semantics.py` 共享登记文件只此一份（§2.5） |
| advanced-query-linkage-closure（0/37，设计 18:06 更新） | ADR-AQL-12 / R6.5 把 ACNR 选字段面板标「开发中」、前端不再发 acnr_targets（W4 不做）；同时给 `QueryDSL` 加 `project_id` / `year`（2000..2100）、给 `QueryRequest` 加 conditions、模板执行年度 = body.year 或 `fetch_project_audit_year`（None → 422 `YEAR_REQUIRED`） | **§16 Q0 已裁定（用户拍板）：以本 spec D1「实现、不下线」为准**，对方撤回「面板开发中」；`acnr_targets` 字段只在本 spec 定义一次；`QueryDSL.project_id` / `year`、`QueryRequest` 新字段「谁先实施谁加、另一方复用」；年度规则与对方一致；不改对方 spec 文件，INDEX 登记注明以本 spec 为准 |
| formula-fetch-followup R4（地址库鉴权） | 4.1 已完成；4.5 未完成 | 不改 V1 地址库端点；只改 V2 与 linkage-bus 三个写 stale 端点 |
| `formula_ref_check.py` | 非底稿域单引用判定 | 不调用；acnr_targets 非底稿域直接 422 |
| `utils/formulaRefIssues.ts` | `formatRefIssues` / `refIssueDetailText` 两个函数，只认 `REF_ISSUE_ERROR_CODES` 两个码并读 `detail.issues`；http 拦截器与 `errorHandler` 也调用它 | 422 体用 `issues`；把 `ACNR_TARGETS_REJECTED` 登记进 `REF_ISSUE_ERROR_CODES`（§2.3） |
| `project_audit_year.fetch_project_audit_year` / 前端 `resolveAuditYear.ts`、`projectStore.auditYear` | 全平台年度单一来源 | 后端补年度、前端只发已知年度（§2.3、§11） |
| `formula_ref_preload.load_note_values` | NOTE 唯一取数 | 不涉及 |
| `useAcnr` 在途合并与缓存纪元 | 已入库 | D9 只改订阅 |

## 2. D1　acnr_targets：跨模块单元格取值（需求 1）

### 2.1 现状确认

- 构建器 `QueryDSL`（`builder_dsl.py` L65-77）没有 `acnr_targets` / `project_id` / `year`，pydantic 默认忽略多余键。业务视图 `QueryRequest` 声明了 `acnr_targets`，编排器 `_resolve_targets` 经 `addressing.resolve_many` 全有或全无（不可解析 400 `TARGET_UNRESOLVABLE`；超时与异常被归成「不可解析」，从不返回 503），而 `business_fetcher(req, resolved, db)` 不读 `resolved`（AST）。模板执行把 `config.acnr_targets` 原样转成 `QueryRequest`。库内带 acnr_targets 的模板 0 个（r03）。
- 前端下钻的既有期待（`useAcnrDrill.ts`、`AdvancedQueryBuilder.vue` L301-317、`GtIndexChip.vue`）：列元数据 `{key,title,addr_id,drillable,dtype}`，`normalizeColumns` 以列级 addr_id 决定可下钻；`drill(addrId)` 走 resolveIndex → `/api/acnr/resolve-instance(parent, sheet_code)` → 新标签页。后端常规查询从不产出 addr_id，下钻分支只能由 acnr_targets 结果触达（需求 1.7 的结论）。
- `WPExecutor.execute` 两参取首个同名格（不分 sheet）；三参非 D2-3 把 sheet 名当列名，恒 0；取不到返回 0。

### 2.2 返回形状

acnr_targets 结果单独成块，不混入常规结果的 `rows/columns`。业务视图 execute、模板执行、构建器 execute 的响应增加（示例为数值格；E1-14 的 B30 是「分析程序结论」文本格，会得到 `state=text`）：

```json
"acnr_results": {
  "registry_version": "20261027xxxxxx",
  "year": 2025,
  "items": [{
    "input": "E1/E1-14/C10",
    "addr_id": "E1/E1-14/C10",
    "display_label": "E1-14 货币资金分析程序（一） › C10 货币资金余额变动率",
    "formula_ref": "WP('E1','货币资金分析表E1-14','C10')",
    "state": "ok", "value": "0.1250", "text": "0.125", "reason_code": null, "reason": null,
    "source": {"wp_code": "E1-14", "sheet_code": "E1-14", "sheet_key": "货币资金分析表E1-14", "cell": "C10",
               "wp_id": "…", "jump_route": "…"}
  }]
}
```

| state | value | text | reason_code（reason 为对应中文） |
|---|---|---|---|
| ok | Decimal 字符串 | 单元格原文 | — |
| text | null | 单元格原文 | `non_numeric`（文本格，如结论） |
| missing | null | null | `year_mismatch`、`wp_missing`（项目中没有该底稿）、`sheet_missing`、`cell_empty`、`value_in_form_storage`（该底稿以表单录入，值不在单元格数据中，本期不支持，见 Q1）、`value_in_file`（只有在线编辑文件、未解析出单元格数据） |
| blocked | null | null | `wp_ambiguous`（底稿记录有歧义）、`sheet_ambiguous`、`sheet_name_borrowed`（§2.4） |

- `items` 与请求一一对应、顺序相同（重复目标逐项各答一次）。`display_label` 取目录字段（§13）。`source.wp_code` 是实际读取的底稿（§2.4 绑定规则），`jump_route` 与 `resolve_instance` 同形态。**R2-N7：绑定到父底稿时 `source.jump_route` 必填**（`resolve_instance` 查不到 sheet 级行即返回 not found、无父底稿回退，故由本层在回落父底稿时自行拼 `jump_route`，追加 `sheet={sheet_code}` 让导航定位到父底稿内的该表）；前端优先用它下钻，缺它才 `drill(addr_id)`。用例覆盖「项目只有父底稿、无 sheet 级实例」时 `jump_route` 非空、前端不提示「目标已失效」。
- 构建器 `/preview` 只返回 `acnr_resolved: [{input, addr_id, display_label, formula_ref}]`；`/export-excel` 追加「单元格取值」工作表（中文名 / 引用 / 状态 / 值 / 原因）。`registry_version` 为本次解析实际使用的目录版本（锁定项目为锁定版本，§8）。

### 2.3 解析与拒绝（后端）

新模块 `backend/app/services/custom_query/acnr_target_values.py` 是 acnr_targets 唯一的解析 + 取值编排；`services/acnr/limits.py` 定义 `ACNR_BATCH_LIMIT = 50`，`resolve-batch` 与本处共用。

输入校验（R2-N8：校验器放 `strict_model.py` 的共享 `Annotated` 类型 `AcnrTargetList`，路由与各模型只改字段类型，不把校验写进 `routers/custom_query.py`，省下 +4 行余量）：`acnr_targets: AcnrTargetList = []`，`AcnrTargetList` 用 `Annotated[list[str], AfterValidator(...)]`，单项去首尾空白后非空且 ≤ 512 字符、条数 ≤ 50、不去重，不合则 `PydanticCustomError` 中文消息（FastAPI 422）。严格模式只作用于顶层请求模型：新模块 `custom_query/strict_model.py` 的 `StrictRequestModel`（`extra="forbid"` + `model_validator(mode="before")` 抛 `unknown_field`「请求包含未声明的字段「{key}」，已拒绝」），`QueryDSL`、`QueryRequest` 继承它；**R2-N9：`ExportDSL` 由 advanced-query 新建、HEAD 不存在，若对方已引入则同样继承 `StrictRequestModel`（谁先实施谁加）**；嵌套模型（`FilterCond` 等）不变。

解析：`resolve_acnr_targets(targets, *, project_id, db, addressing)` 逐项调用 `AddressingService.resolve_target`（保留其 5 秒 `wait_for` 与异常归 `resolve_unavailable`）。`resolve_many` 在 `db is not None` 时改为顺序执行（修 §1.2 的同会话并发），`ResolvedTarget` 只增 `result: ResolveResult | None`。**R2-F9（整体时限与短路）**：顺序执行遇到**第一个** `resolve_unavailable` 立即停止并返回 503（不把 50 项跑完）；整批套 `asyncio.timeout(ACNR_BATCH_DEADLINE_S)`（常量放 `services/acnr/limits.py`，取 8 秒，远低于前端 axios 180 秒超时且不长时间占用数据库连接），超时同样按 503 处理。用例：解析桩每项睡 6 秒，断言总耗时不超过 `ACNR_BATCH_DEADLINE_S` 加余量、返回 503、取数函数调用 0 次。逐项分类（字段即判据）：

| error_code | 判定 |
|---|---|
| `resolve_unavailable` | `ResolvedTarget.error == "resolve_unavailable"`（超时或解析器异常，含 `CatalogLoadError`） |
| `external_namespace` | `result.error == "external_module_not_resolved"` |
| `unsupported_domain` | `result.source_layer == "V1"`（tb / report / note / aux 委托） |
| `runtime_entry` | `result.source_layer == "L3"` |
| `sheet_level` | `result.entry_type == "sheet"` |
| `deprecated` | `result.deprecated is True`（候选给 `replaced_by`，不自动跟随） |
| `ambiguous` | `result.error == "ambiguous"`（带候选 ≤5 与 `required_context`） |
| `unresolvable` | 其余 `found == False` |
| 接受 | `found` 且 `entry_type == "cell"` 且 `source_layer == "L1_cell"`（R2-N10：resolver 只产出 `L1_cell` / `L1_sheet` / `L3` / `V1`，overlay 命中同样标 `L1_cell`，`"L2"` 不会出现；用例钉住 overlay 命中标记为 `L1_cell`） |

任一项为 `resolve_unavailable` → 503 `{"error_code": "RESOLVE_UNAVAILABLE", "message": "地址解析服务暂不可用，未执行查询，请稍后重试", "issues": [...]}`；否则任一项不接受 → 422 `{"error_code": "ACNR_TARGETS_REJECTED", "message": "所选单元格中有 N 项无法取值，未执行查询", "issues": [{"ref", "error_code", "message", "candidates", "required_context"}]}`。两者都不取数（全有或全无）。`issues` 与 `formulaRefIssues.ts` 同构；前端 `REF_ISSUE_ERROR_CODES` 增加 `ACNR_TARGETS_REJECTED`。

项目与年度（R2-F5 修订：构建器鉴权复用业务视图的同一守卫，不另起一条）：
- 构建器三个端点：`acnr_targets` 非空而缺 `project_id` → 422「选择单元格取值时须指定项目」；否则把 `body.project_id` 传给 HEAD 已有的 `builder_scope.resolve_builder_scope(requested_project_id=body.project_id)`（其内部即调 `ownership_guard.assert_target_accessible`，`_ALL_ACCESS_ROLES=("admin","partner")` 全可访问、并含 `project_assignments` 委派），**与业务视图同一个守卫**，不再另调 `assert_project_permission`（后者只放行 admin 与 `project_users` 成员，与业务视图放行集合不同——非成员合伙人、只有委派的员工会被误判 403）。不带 `acnr_targets` 的普通构建器请求照旧（`project_id` 可为 None，不触发该校验）。业务视图由编排器 step1 `assert_target_accessible` 先行判定（403），解析在其后。
- body-carried 扫描器要看得到时，把 `resolve_builder_scope` 登记为项目级校验函数（带可伪证条目，仿 `check_project_access` 的登记方式），而不是靠「函数体首句无条件调 `assert_project_permission`」。
- 年度 = `body.year`，**`year` 为 None 或 ≤ 0 视为缺省**，用 `fetch_project_audit_year(db, project_id)` 补齐，仍为 None → 422 `YEAR_REQUIRED`「项目审计年度未知，请指定年度后再取值」（与 advanced-query 模板执行同一规则；修掉 `int(config.get("year") or 0)` 的 0 歧义）。`year` 取值范围按对方定义 2000..2100。
- 构建器 `QueryDSL.project_id` / `year` 与 advanced-query 同一字段定义，谁先实施谁加，另一方只复用。
- 权限矩阵用例须覆盖**非成员合伙人**与**只有委派的员工**，并断言构建器与业务视图两个入口对同一 (用户, 项目) 的放行结果一致。
- **R2-N5（模板执行里的非法 acnr_targets 不得 500）**：`execute_template` 在函数体内构造 `QueryRequest`，模板 config 里若存了超 50 条 / 空串 / 超长的 acnr_targets，会抛 pydantic `ValidationError` 变成 500（且非 `_silent` 请求前端还会自动重发）。处置两道：①保存模板时就按 `AcnrTargetList` 校验 acnr_targets（不合格 422 不入库）；②执行端把构造 `QueryRequest` 包进 `try/except ValidationError` → 422（中文原因，指出模板里的非法项）。

接线：`QueryOrchestrator._resolve_targets` 改调 `resolve_acnr_targets`；`execute` 在缓存读取之后（无论命中）调 `read_acnr_target_values`，取值不进缓存；`QueryResult.acnr_results` 只增，缺省 None、无目标不输出。`routers/custom_query.py` 只改基类与 import（≤ +4 行，余量 27）。

T15 实施记录（段七第 5 轮，待评审核实）：
- 落点：业务视图在 `QueryOrchestrator._resolve_targets` 调 `resolve_acnr_targets`（传编排器自己的寻址服务）后经 `complete_year` 补年度，`execute` 在 `get_or_compute` 之后调 `read_acnr_target_values`，`ExecuteCompatibilityAdapter.to_legacy_response` 仅在有块时输出 `acnr_results`。构建器三端点在 `_builder_scope` 之后调 `acnr_target_values.plan_builder_targets`（缺项目 422 `PROJECT_REQUIRED`「选择单元格取值时须指定项目」、`complete_year`、解析拒绝 422 / 503，均在 SQL 与缓存之前）；`/preview` 返回 `acnr_resolved`，`/execute` 命中与未命中缓存都用 `with_acnr_results` 现读后附加（缓存里不带它），`/export-excel` 经 `acnr_sheet` 追加「单元格取值」工作表（`export_service.stream_xlsx` / `query_export.respond_xlsx` / `export_builder_query` 各加一个可选参数，缺省行为不变）。`routers/custom_query.py` 净增 3 行（模板 config 字段类型改 `TemplateConfig`、`execute_template` 包 `ValidationError → template_config_rejected`）。
- body-carried 扫描器把 `_builder_scope` 登记为额外项目级标识，证明链 `_builder_scope → resolve_builder_scope → OwnershipGuard.assert_target_accessible → _can_access_project → _accessible_project_ids（ProjectUser / ProjectAssignment）`。三端点原本已因 `require_query_builder_access` 记为项目档，档位与基线（84）不变，未加入 `_FIXED_ENDPOINTS`（该钉子的变异会连带删掉 `body.project_id` 读取，端点退出本维，判据不适用）。
- 年度：业务视图请求 `year` 必填（2000~2100），`complete_year` 只对编排器直调时的 None 生效；构建器 `year` 可缺省，按项目审计年度补齐。模板执行的年度补齐仍归 advanced-query 任务 24（其 ADR-AQL-15 统一走 `deps.require_project_audit_year`，HEAD 尚无该函数）；本 spec 只把模板 config 构造失败（含年度缺失、acnr_targets 非法）由 500 改为 422 `TEMPLATE_CONFIG_INVALID` 并点名非法项，对方任务 24 按其原文「沿用其实现」。
- 跨 spec 观察（不改对方代码，需用户转达 advanced-query）：`POST /api/custom-query/templates` 传 `scope="private"` 或 `"personal"` 时，路由先归一成 `private`，`template_service.save_template` 的 `_normalize_scope` 又不认 `private`，抛 `TemplateInvalidError` 成 500（端到端用例因此用 `scope="public"`）。

### 2.4 读取：与 formula-hub 共用 `wp_cell_reader`

契约逐字采用 formula-hub ADR-FHIC-06 第 1 点：`services/wp_cell_reader.py::resolve_wp_cell(db, *, project_id, year, wp_code, sheet_key: str | None, cell) -> WpCellRead{state ∈ ok|missing|blocked, value: Decimal | None, reason, wp_id, sheet, matches}`，步骤、三态与原因按其原文（年度不符 missing、0 份底稿 missing、多份 blocked、`normalize_sheet_key(rec.sheet) == sheet_key` 过滤、同一归一键多个真实表名 blocked、无此表 missing、空值 missing、非数值 blocked）。先后按其 §8.2：任务 22 先提交；本 spec 动手前 `git log -S "resolve_wp_cell"`，未入库则按该原文建模块并登记 `WP_CELL_READER_IMPL`，入库则只接线。

J1 字段补充（R2-F6 修订：formula-hub 的 ADR-FHIC-06 第 1 点现读只有 `WpCellRead{state, value, reason, wp_id, sheet, matches}`，**没有 `reason_code` / `raw`、没有 A1 分支、§8.2 也只写 ACNR 侧「只调用 `resolve_wp_cell`」**；「两份设计同文」在对方设计里不成立，删去该表述，不比对中文原因串）。本 spec 需要 `reason_code`（区分文本格与各 missing 原因）与 `raw`（文本格原文）。采**回退流程 B**（不依赖对方设计阶段修订）：
- 本 spec 动手前 `git log -S "reason_code" -- backend/app/services/wp_cell_reader.py` 核对任务 22 是否已带这两个字段；
- 已带：直接用；
- 未带（预期）：由本 spec 单独一次提交给 `WpCellRead` **追加两个默认 `None` 的可选字段** `reason_code: str | None = None`、`raw: str | None = None`，并在 `resolve_wp_cell` 的七条返回路径填值（`year_mismatch` / `wp_missing` / `wp_ambiguous` / `sheet_ambiguous` / `sheet_missing` / `cell_empty` / `non_numeric` 与原 `reason` 一一对应；找到单元格时 `raw` 为原文否则 None），逐条列出要同步改的 `test_wp_cell_reader.py` 断言（整对象相等断言改为允许新两字段），并在 formula-hub 任务 22 下登记这次跨 spec 修订。因两字段默认 None，不改对方任何现有判定与三态语义。

ACNR 一侧的唯一接线模块 `services/acnr/wp_cell_target.py`（不读 `parsed_data`、不调 `extract_custom_cells`）：

- `sheet_key_for(entry)`：目录 sheet 的名称归属本 sheet（`exact_identity.name_owner(parent, sheet_name) is entry`）→ `normalize_sheet_key(entry["sheet_name"])`；名称被借用或父级内多义 → blocked `sheet_name_borrowed`（现算影响 F2-33/B20、F2-34/B20 两格）。
- `bind_wp_code(db, project_id, entry)`：项目中存在 `wp_index.wp_code == sheet_code`（与 `resolve_instance` 第 1 步同一查询）→ 读该 sheet 级底稿；否则读父底稿。只在「sheet 级底稿不存在」时回落，sheet 级底稿存在但无数据照实返回 missing。
- `read_entry_cell(db, *, project_id, year, entry, cell)`：上两步后调 `resolve_wp_cell`，返回 `TargetRead(read, bound_wp_code)`。
- `read_formula_cell(db, *, project_id, year, wp_code, sheet_text, cell)`：`exact_identity.sheet_of` 命中 → `read_entry_cell`；`not_found` / `wp_not_in_catalog` → 按原文 `resolve_wp_cell(wp_code=wp_code, sheet_key=normalize_sheet_key(sheet_text))`；`ambiguous` / `alias_forbidden` → 不读，返回 blocked（`reason_code="sheet_ambiguous"`，reason 带候选或禁止理由）。
- 原因细化：`missing` 且 `reason_code ∈ {sheet_missing, cell_empty}` 且 `wp_id` 非空时，每个 `wp_id` 一次元数据查询（`db.info` 内记忆）：有 `checklist_responses` → `value_in_form_storage`；`parsed_data` 无 `html_data` 且有 `file_path` → `value_in_file`。PG 专有 SQL，SQLite 方言下不细化。
- **R2-F7（锁定项目用锁定目录判身份）**：`full_resolve` 按锁定快照解析，但 `sheet_key_for`/`read_formula_cell` 的名称归属（`exact_identity.name_owner`、`sheet_of`）与三参取值若用当前目录，升级后锁定项目会被误判 `sheet_name_borrowed` 或取到不同结果；打开归档项目底稿时 `wp_formula.py` L570 的 Tier A GET 求值同样走当前目录。修法：新增 `async effective_catalog(db, project_id) -> CatalogIndex`（`get_locked_version(db, project_id)` 命中 → `load_versioned_catalog(版本)`，否则 `get_catalog()`），`wp_cell_target`（`sheet_key_for` / `read_entry_cell` / `read_formula_cell`）、acnr_targets、三参取值统一用它，并把该 `CatalogIndex` 显式传给 `exact_identity.*(…, index=…)`（`exact_identity` 的 `index` 缺省参数本就支持，§6.2）。`test_project_registry_lock_pg.py` 加一例：v1 与 v2 对同一名称归属不同，锁定项目取数按 v1。
- 数据库异常一律上抛（端点 500 + ERROR 日志，带项目与 addr_id），不伪装成 missing。

**T11 实施记录与跨 spec 登记（2026-10-28，段七第 2 轮；formula-hub 的 tasks.md 是对方未跟踪文件，按约定只在本节登记，不改对方文件）**：
- 核对：`git log --all -S "resolve_wp_cell"` 无 `wp_cell_reader.py` 的提交，`refs/wip/formula-hub/A~C` 与 `_tmp_formula_hub/wt` 也没有该文件 ⇒ 读取函数未入库，本 spec 先落地。编号勘误：本设计与 tasks.md 写的「formula-hub 任务 22」在对方现行 tasks.md 里是任务 23（任务 22 是「依赖解析认双引号」）。
- 提交一（`bd49254f4`）：按 ADR-FHIC-06 第 1 点 / §8.2 原文建 `services/wp_cell_reader.py`，并提交 §8.2 指定由先落地方提交的契约测试 `tests/test_wp_cell_reader_contract.py`（逐行钉签名、返回、年度、底稿绑定、工作表、单元格、异常）。`WpCellRead` 字段名按 §8.2 用 `sheet_key`（本节上文写的 `sheet` 以 §8.2 为准）；签名六参均为位置或关键字参数（本节上文写的 `*` 仅关键字以 §8.2 为准，关键字调用照样成立）。`_catalog_sheet_keys` 按 §8.2 首次落地恒 `not_found`：本 spec 不改写它——ACNR 的身份判定在 `wp_cell_target` 里用 `effective_catalog`（R2-F7）做，读取函数若自读当前目录，锁定项目会按新目录判名。`formula_wp_semantics.py` 只新增 `WP_CELL_READER_IMPL` 一条登记；`EXECUTOR_WP_IMPL.data_source` 改写与 `typed_eval_strictness` 属两参分支改调，归 formula-hub。
- 提交二（`17e8acab0`，回退流程 B 的单独一次提交）：`WpCellRead` 追加 `reason_code` / `raw`（默认 None），各返回路径填值。码表：`year_unknown`（§8.2「项目未设置审计年度」，七个码之外的第八个，原文七条路径未含这一条）、`year_mismatch`、`wp_missing`、`wp_ambiguous`、`sheet_ambiguous`（目录判名歧义、别名不能用于取值、同一工作表有多份数据三处共用，与 T12 对 ambiguous / alias_forbidden 的写法一致）、`sheet_missing`、`cell_empty`、`non_numeric`。`test_wp_cell_reader.py` 原不存在、没有整对象相等断言要改，新建该文件钉码表与 `raw`。
- 与真库的差异：真库 `working_paper` 有 `(project_id, wp_index_id)`、`wp_index` 有 `(project_id, wp_code)` 非部分唯一索引（2026-10-28 现查），「多份底稿 ⇒ blocked」分支真库造不出来，契约测试拆掉 SQLite 里的索引钉这条防御分支。
- T12 实施差异（同日）：`sheet_key_for` 用 `sheet_of(父级, sheet_name)` 命中本 sheet 判归属（含名称等于自身编码，如 S17/S17），不用 `name_owner`（不认编码命中，会把 S17/S17/E30、E35 误判借名）；现算借名 / 多义下的有效 cell 恰为 F2-33/B20、F2-34/B20。`effective_catalog` 的锁定来源在 T17 / T18 之前与 `full_resolve` 同为进程内登记。
- 需 formula-hub 知悉（由用户转达）：读取函数与契约测试已入库，对方任务 23 按其「已提交则以其提交为底，只做向后兼容扩展」执行；两参分支改调、`EXECUTOR_WP_IMPL.data_source` 与 `typed_eval_strictness` 仍归对方。

### 2.5 WP 三参接线与 `formula_wp_semantics`

`WPExecutor.execute` 现有 4 个调用方（AST）：

| 调用方 | 形态 | 本 spec 后 |
|---|---|---|
| `formula_engine` L1816（`FormulaEngine.execute` WP 预载，`_extract_wp_refs` 只匹配 1~2 参） | 两参 | 不变 |
| `report_engine` L895（预载） | 两参 | 不变 |
| `wp_formula_eval_service` L375（`_WP3_PATTERN` 三参循环，结果 `str(val)` 代入） | 三参（语义第三参、D2-3、A1） | A1 第三参改走 `read_formula_cell`，见下 |
| `wp_formula_eval_service` L390（两参循环） | 两参 | 不变 |

`WPExecutor` 增加 `read_sheet_cell(db, project_id, year, wp_code, sheet_text, cell) -> TargetRead`（委托 `read_formula_cell`）；`execute` 在 `field` 匹配 `^[A-Z]{1,3}[0-9]{1,7}$` 且第二参不含 D2-3 标记时返回 `read.value if state == "ok" else None`（原来恒 0）。两参与 D2-3 分支逐字节不变；formula-hub 给 `execute` 加的 `year` 透传给本分支。

三参循环改法（R2-F6：formula-hub 第 6 点现读无 A1 分支，删「两份设计同文」表述；下面前两支 `wp_values` / `strict_wp` 沿用 formula-hub 第 6 点语义，第三支 `_A1` 分支为本 spec 新增，由本 spec 单独落地，不声称对方已写同一段）：

```python
for match in _WP3_PATTERN.finditer(raw):
    wp_code, sheet_text, field = match.group(1), match.group(2), match.group(3)
    key = (wp_code.upper(), normalize_sheet_key(sheet_text), field)
    if wp_values is not None and key in wp_values:            # formula-hub 第 6 点
        val = wp_values[key]
    elif strict_wp:                                           # formula-hub 第 6 点
        errors.append(f"{match.group(0)}：批内未求得值"); val = Decimal("0")
    elif _A1.match(field) and _D23_SHEET_MARKER not in sheet_text:   # 本 spec
        tr = await WPExecutor.read_sheet_cell(db, project_id, year, wp_code, sheet_text, field)
        if tr.read.state == "ok":
            val = tr.read.value
        else:
            errors.append(f"{match.group(0)}：{tr.read.reason}"); val = Decimal("0")  # 占位
    else:
        val = await WPExecutor.execute(db, project_id, wp_code, sheet_text, field=field)  # 原逻辑
    expr = expr.replace(match.group(0), str(val), 1)
```

循环体外沿用现有的 `try/except`（异常记入 errors、该式不出数）。非 ok 时 `0` 只是占位：`evaluate_wp_formula_expression` 的 4 个调用方（`wp_formula` L570 / L1079、`tier_a_seed` L100、`prev_wp_field` L178）在 errors 非空时都丢弃该值，该式不出数（现读确认）。报表 / 自定义公式路径不加三参预载：`report_config` 三参 0 条，该路径三参继续抛 `FormulaColumnError`「锚点未对齐或底稿未录入」，不出 0；需求 1.2 的「公式引擎三参求值」以底稿公式路径为准。`formula_engine.py` 净增 ≤ 14 行（余量 45），`wp_formula_eval_service.py` 432 行、净增 ≤ 12。

`formula_wp_semantics.py` 的最终文本（两 spec 合计只此一份）：

| 条目 | 内容 | 负责方 |
|---|---|---|
| `WP_CELL_READER_IMPL` 与其 `WP_IMPLS` 条目 | 按 formula-hub ADR-FHIC-06 第 1 点 | formula-hub 任务 22 |
| `EXECUTOR_WP_IMPL` 两参的 `data_source / on_missing / measured` | 按 formula-hub 原文 | formula-hub 任务 22 |
| `EXECUTOR_WP_IMPL.positional_args` | 改为 `("wp_code", "column", "field")`；`data_source` 追加「第三参为 A1 时经 `acnr.wp_cell_target.read_formula_cell` 按目录 sheet 精确取值（先 sheet 级底稿、无则父底稿），取不到返回 None」 | 本 spec |
| `WP_KNOWN_DIFFERENCES` | 维度集合不变；只改 `positional_arg_count.detail`：「预填路径三参读 checklist_responses；WPExecutor 三参只对 A1 第三参按 sheet 精确取值，语义第三参仍不支持；报表路径三参报错」 | 本 spec |

T13 实施记录（2026-10-28）：三个文件实际在 `backend/app/services/` 下。formula-hub 第 6 点的 `wp_values` / `strict_wp` 两支尚未入库，三参循环现只有本 spec 的 `_A1` 一支与原逻辑；`WPExecutor.execute` 签名尚无 formula-hub 要加的 `year`，其 A1 分支暂传 `year=None`（不做年度闸门），等对方加 `year` 后透传（需用户转达 formula-hub）。底稿公式路径的 A1 分支直接调 `read_sheet_cell` 并传 `evaluate_wp_formula_expression` 的年度。
- 归属更正（RV7.2-01，段七续做复审第 2 次）：上表把 `EXECUTOR_WP_IMPL` 两参的 `data_source / on_missing / measured` 划给 formula-hub，但 T13 实际整条改写了 `on_missing` 与 `measured`（内容同时写了两参与三参 A1 的情况），`data_source` 只追加 A1 一句。这两个字段的现行文字由本 spec 写入（`c2384a8df`）；formula-hub 任务 23（本设计写的「任务 22」）接手时以本 spec 的提交为底，只做向后兼容扩展（需用户转达 formula-hub）。模块文档对照表「取不到时」一行同步补了「第三参为 A1 时返回 None」。

### 2.6 前端

- 新组件 `components/custom-query/AcnrTargetResults.vue`：列 中文名 / 引用 / 值 / 状态 / 原因 / 下钻。`missing` / `blocked` 显示原因、值列「—」；`text` 显示原文。下钻：`GtIndexChip`（`value=addrIdToIndexRef(addr_id)`、`prevent-navigate`）+ 点击时优先 `useAcnrDrill.openRoute(item.source.jump_route, cell)`（新导出，复用 drill 的占位替换与高亮拼接），没有 `jump_route` 才 `drill(addr_id)`。
- 请求体构造抽成纯函数 `components/custom-query/queryPayloads.ts`（`buildBuilderPayload` / `buildBusinessPayload`），`AdvancedQueryBuilder.vue`、`CustomQueryTab.vue` 只减不增。`project_id` 取路由项目；`year` 只在 `projectStore.auditYear` 已知时发送，不用 `useAuditContext().year`（含日历年兜底）；没有项目上下文时地址选择区提示「请先进入项目再选择单元格」，不发 acnr_targets。
- 三个执行请求带 `_silent: true`；422 `ACNR_TARGETS_REJECTED` 与 `YEAR_REQUIRED` 用 `refIssueDetailText(detail)` / `detail.message`；`unknown_field` 422 显示中文 `msg`；403「无权访问该项目」；503「地址解析服务暂不可用，请稍后重试」。
- `useAcnrDrill`：站内路由（以 `/` 开头）用 `window.open(route, '_blank')`，站外保留 `noopener`。
- 与 advanced-query 的过渡（§16 Q0 已裁定）：以本 spec D1 为准，acnr_targets 面板与结果区**实现、不下线**。若对方「面板开发中」（R6.5 / W4）已先入库，本 spec 交付时撤回该前端状态并在 tasks 记录；若本 spec 先入库，对方该项失去前提。不改对方 spec 文件；`acnr_targets` 字段只在本 spec 定义一次。
- **T16 返工 RV7.5-01 决策（2026-10-28，用户拍板选①）**：浏览器实测 chip 打开的新标签是 404——ACNR 跳转路由 `/workpapers/{wp_id}?sheet=…`（目录 1225 个 sheet 的 `jump_route_template`、`resolver._build_jump_route` 缺省、`acnr_target_values` 回落父底稿）在前端没有路由，前端只有 `projects/:projectId/workpapers/:wpId/edit`（`WorkpaperEditor`）。这早于 T16：`useAcnrDrill.drill`、AI 提及（`mention_service`）、证据治理（`typed_adapters`）同形。
  - 选①：前端加短链 `workpapers/:wpId`（`WorkpaperShortLink`，DefaultLayout 下、需登录；未登录时守卫带 `redirect=完整路径`）。页面经新只读端点 `GET /api/acnr/workpapers/{wp_id}/locate`（键 = `working_paper.id`，不是 `wp_index.id`；先查行、再 `assert_project_permission(…, "readonly")`、鉴权通过后才区分回收站：401 / 403 / 404 / 410「底稿已移入回收站」）拿到项目，用 `useWorkpaperNavigation.workpaperEditorRoute`（新导出，原 `resolveRoute` 四处同改为调它）生成目标 `router.replace`，查询串原样带过去（编辑器按 `route.query.sheet` / `cell` 定位，参数名相同不需映射）；失败显示中文原因与「返回上一页 / 进入项目列表」，不跳转，无重定向循环。一处修好所有产出 `/workpapers/{id}` 的入口；目录不重新发布（1225 个模板与既有快照不变，addr_id 与 jump_route 契约不变）；保留 `useAcnrDrill`「不自行拼底稿路由」。端点放在已注册的 ACNR 路由（`router_registry/system.py` 有并发会话未提交改动，未碰），不进底稿组的 `dedicated_wp_gate` 循环（那会在端点之前把回收站底稿判成 404）。
  - 不选②（后端模板改成 `/projects/{project_id}/workpapers/{wp_id}/edit`）：要重新发布全部 1225 个模板，影响快照、不可变门禁与依赖现形态的测试和其他会话。不选③（`openRoute` 里改写）：违背「不自行拼底稿路由」，且只修好本 spec 两个入口。
  - 防同类守卫：后端 `test_frontend_route_shapes_fixture.py` 用 AST 扫 `backend/app` 路由位置（`route` / `jump_route` 关键字、`route` 赋值、名含 route 的函数 return）上的站内 `/workpapers` 形态写进夹具 `fixtures/frontend_route_shapes.json`（漏登 / 失效条目都红）；前端 `router/__tests__/backendRouteShapes.contract.spec.ts` 用真实路由表（`router/index.ts` 改为导出 `routes`）建 memory history router，把目录模板与夹具形态逐个 `resolve`，断言不落兜底 `NotFound`。现算夹具 11 条：本 spec 目录 / resolver / acnr_targets 与 AI 提及、证据治理均为 `/workpapers/{…}`（短链后可命中）；联动三处 `/projects/{…}/workpapers/{…}`（`linkage_resolve`、`linkage_contract_builder`、`linkage_facade_service`，缺 `/edit`，后者部分还把 wp_code 当 id）同样落 404、不归本 spec，登记在契约的 `KNOWN_UNROUTABLE`（只许删，并断言它们确实仍落 404），转达对应 spec。
  - 鉴权基线：该端点路径只有 `{wp_id}`、不带 `{project_id}`，两个基线扫描器都不覆盖（请求体维显式排除对象 id 路径），登记进 `_FIXED_ENDPOINTS` 只会得到恒真的钉子，故未登记；改由 `test_workpaper_locate_endpoint.py` 的 AST 用例与现状节判据钉住「函数体调用 `assert_project_permission(…, "readonly")`」。

### 2.7 错误处理

| 操作 | 失败条件 | 可恢复 | 调用方收到 | 日志 |
|---|---|---|---|---|
| 请求体校验 | 未知键 / 单项空或超长 / 超 50 条 / `year` 越界 / `project_id` 非 UUID | 是 | 422（中文 msg） | 不记 |
| 缺项目或年度 | 带 acnr_targets 缺 `project_id`；年度补不出 | 是 | 422 / 422 `YEAR_REQUIRED` | 不记 |
| 项目鉴权 | 非成员或级别不足 | 是 | 403 | INFO（现有鉴权日志） |
| 解析超时 / 解析器异常 | `resolve_target` 5 秒超时、`CatalogLoadError` 等 | 是（重试） | 503 `RESOLVE_UNAVAILABLE`，取数 0 次 | WARNING（现有） |
| 目标不合格 | 分类表任一拒绝 | 是 | 422 `ACNR_TARGETS_REJECTED` + `issues` | 指标 `acnr_targets_rejected{error_code}` |
| 锁定快照缺失 / 损坏 | 见 §8 | 否（运维恢复快照） | 409 | WARNING |
| 取值 | missing / blocked / text | — | 200，逐项状态与原因 | 不记 |
| 取值 | 数据库异常 | 否 | 500 | ERROR |

### 2.8 验证

- 端到端 `test_acnr_targets_query_e2e.py`（`pg_only`，回滚事务内建【测试】项目与 E1 底稿，`parsed_data.html_data` 写 E1-14!C10=0.125、E1-15!C8=222、E1-14!B30=「结论文本」，另建一份只有 `checklist_responses` 的底稿）：TestClient 真发三个入口；逐字段断言 §2.2；两 sheet 各取各的值；文本格 `text`；表单底稿 `value_in_form_storage`；未生成底稿 `wp_missing`；sheet 级底稿存在时读它、不存在时读父底稿；顺序与重复项逐项对应。
- 参数化 422 / 503：每种 error_code 一例（`resolve_unavailable` 用超时桩），spy `resolve_wp_cell` 调用 0 次；非成员 403；缺年度且项目无年度 → `YEAR_REQUIRED`；不带 acnr_targets 的旧请求响应与基线逐字段相等。
- 三者相等：同一夹具上 `evaluate_wp_formula_expression("WP('E1','货币资金分析表E1-14','C10')")`、acnr_targets、库内值逐值相等；三参取不到时该式 errors 非空、四个调用方不写值；两参 `WP('E1','C10')` 旧行为保留并有断言；`test_formula_wp_semantics` 全绿。
- `test_acnr_targets_single_reader.py`（AST）：`acnr_target_values.py`、`wp_cell_target.py` 不引用 `extract_custom_cells`、不下标 `parsed_data`，取值只经 `resolve_wp_cell`；若 formula-hub 的 `test_wp_cell_reader_single_source.py` 已入库，并入它，不另写第二份。
- 需同步改断言的既有测试：`test_advanced_query_hardening_wave012.py` L512-515（400 `TARGET_UNRESOLVABLE` → 422 `ACNR_TARGETS_REJECTED`，取数 0 次保留）、L701 起 `test_multi_target_one_inaccessible_rejects_all_not_partial` 的寻址替身补 `result`（`entry_type="cell"`、`source_layer="L1_cell"`）；`test_addressing_service_*` 按顺序执行补一例。
- 前端：`queryPayloads.contract.spec.ts` 解析两个后端模型（`QueryDSL` / `QueryRequest`）的字段声明，断言构造的键是其子集。**R2-F10（契约覆盖全部生产调用方）**：`/api/custom-query/execute` 现算共 5 个前端调用点（q04 之外的 grep 现证）——`CustomQueryTab.vue`、`CustomQueryDialog.vue` L819、`SheetCellRangePicker.vue` L211、`useBatchQuery.ts` L107、`AdvancedQueryBuilder.vue`（经 builder 入口）。契约测试只验两个纯函数会漏掉后三处（它们现发的键恰在模型内，日后加键即在生产上 422 而非测试红）。处置：①把 `CustomQueryDialog.vue`、`SheetCellRangePicker.vue`、`useBatchQuery.ts` 三处改为调用 `buildBusinessPayload`（推荐，构造函数收敛为一个）；②或用 TS 语法树抽取所有 `post(customQuery.execute | '/api/custom-query/execute', {…})` 调用点对象字面量的键，断言是 `QueryRequest` 字段的子集。设计中已列全 5 个调用点；顺带把 `SheetCellRangePicker.vue` 的 `year: props.year || new Date().getFullYear()` 日历年兜底去掉（改走 `buildBusinessPayload` 的年度规则）。vitest 用后端真实 422 / 503 形状断言逐项原因可见；`AcnrTargetResults` 四种状态渲染。
- 变异（磁盘级，备份到 `tmp_acnr_foundation/mutations/`）：删 `QueryDSL.acnr_targets`；分类表恒接受；`resolve_wp_cell` 不比 sheet；缺数返回 0；摘端点 `assert_project_permission`；`resolve_many` 改回 gather —— 各自红在对应断言上。
- 浏览器（chrome-devtools，【测试】项目）：业务视图与构建器各选 2 个单元格执行并截图；点 chip 打开对应底稿且仍在登录态；选 sheet 级地址看到逐项中文原因。

## 3. D2　孤儿 cell 与历史移除（需求 2）

### 3.1 现状确认（逐张证据）

| 编码 | 模板册真实 tab（openpyxl） | classification（缓存 / 库表，§1.3） | 种子 | I/E manifest | wp_account_mapping | 真库 wp_index | 其他 |
|---|---|---|---|---|---|---|---|
| I6-7 | I6 册 11 个 tab，无 | 0 / 0 | i 种子「研发加计扣除测算」5 格 | 无 | 研发加计扣除测算 | 1 项目 1 份，无数据 | overrides 有 componentType |
| J2-5 | J2 册 9 个 tab，无 | 0 / 0 | j 种子「精算重新计算」5 格 | 无 | 精算重新计算 | 1 / 1，无数据 | J2-1、J2-3 渲染 schema 跨引 |
| J3-4 | J3 册 6 个 tab，无 | 0 / 0 | j 种子「期权公允价值测算」6 格 | 无 | 期权公允价值测算 | 1 / 1，无数据 | J3-1 渲染 schema 跨引 |
| J3-5 | 同上，无 | 0 / 0 | j 种子「等待期费用分摊」4 格 | 无 | 等待期费用分摊 | 1 / 1，无数据 | J3-1 渲染 schema 跨引 |
| M6-5 | M6 册 10 个 tab，无 | 0 / 0 | m 种子「损益联动验证」5 格 | 无 | 损益联动验证 | 1 / 1，无数据 | overrides 有；M6-1 渲染 schema 跨引 |
| K14~K18 | `wp_templates/K` 只有 K0~K13 | 0 / 0 | 无 | 无 | 0 条 | 4 个未删项目各 1 份（和平药房缺 K17），parsed_data 全空 | 公式引用 0；替代目标 H10-1、K10-1、G11-1、G13-1、K7-1 在目录中 |

5 张孤儿父 sheet 都是平台编码、真实项目生成过、4 张被其他底稿跨引，编码前缀与父级一致（挂错父级不成立）。K14~K18 是 2025 修订前的旧编码。

### 3.2 判定与修正落点

生成器新权威输入 `backend/data/acnr/sources/sheet_verdicts.json`（手工维护，每条带证据），loader `app/services/acnr/loaders/from_sheet_verdicts.py`。记录分 `sheet_verdicts` 与 `cell_verdicts` 两段。sheet 记录 `{sheet_code, parent_wp_code, verdict, sheet_name, replaced_by, evidence{template_tabs, renderer_tabs, project_files, classification_count, seeds, ie_manifest, wp_account_mapping, wp_index{projects, as_of}, extra}, owner, reason, decided_on}`；sheet `verdict` 只取需求 2.1 的三种：

- `add_platform_sheet`：I6-7、J2-5、J3-4、J3-5、M6-5。生成器在 classification 骨架之后补 `SheetCatalogEntry`：`sheet_name` 取平台索引名，`source_of_truth="sheet_verdicts"`，其余按现规则推导。补这 5 张 sheet 的唯一目的是**让 K-F1 停用掉的那 25 个 cell 有一个可解析的 `replaced_by` 父级、让导航能落到项目已有的 wp_index 实例**；sheet 本身不带任何有效 cell（见下 `cell_verdicts`）。classification 日后出现同编码记录时门禁报「判定记录已过期」。
- `fix_parent`：本轮 0 条，保留枚举。
- `deprecate`：K14→`H10/H10-1`、K15→`K10/K10-1`、K16→`G11/G11-1`、K17→`G13/G13-1`、K18→`K7/K7-1`。证据：K15~K18 的项目底稿名与映射中目标审定表同名（其他收益 / 投资收益 / 公允价值变动收益 / 递延收益审定表，科目 6117 / 6111 / 6101 / 2401）；K14「资产处置收益审定表」与 H10-1「资产处置损益审定表」不同名，依据是同一科目 6115：映射 H10 / H10-1 的 `account_codes` 为 6115，`prefill_formula_mapping` 的 H10 中「资产处置收益」= `TB('6115','本期发生额')`，「资产处置收益」是该科目的利润表项目名（`report_config_seed` IS-039）。生成器写出 `deprecated: true`、`replaced_by`、`deprecated_at_version`（首次停用取本次版本，之后沿用上一批次），`sheet_name` 取业务名，`source_of_truth="sheet_verdicts"`。

**R2-F1（用户拍板 2026-10-27）：25 个孤儿 cell 判为无效，从种子输入清除，登记 deprecated 迁移映射。** 现算复核（q01、q02）证实这 25 个坐标只存在于目录自身的 4 份快照里；它们的 addr_id、formula_ref（如 `WP('I6','研发加计扣除测算','C5')`）在 `formula_presets_seed.json`、`cross_wp_references.json`、`prefill_formula_mapping.json` 与全 `backend/data` 的其它 JSON/YAML 中 0 命中（种子名出现在 i/j/m 种子、`wp_account_mapping`、`procedure_table_templates` 与 J2-1/J2-3/J3-1/M6-1 渲染 schema 的 `cross_refs.target_wp`，但都**不带这些坐标的 addr_id / formula_ref**，只是数据流声明）；真库 `wp_formula` 对这 5 个种子名与 5 个父编码的引用为 0（q01 之 PG 现查）。渲染组件 `i6-research-development-expense.yaml` 不含 I6-7 tab、`m6-retained-earnings` 不含 M6-5（R2-F1 原查，q02 复核同口径）。结论：这些坐标在模板册、渲染组件、真实底稿、公式预设、真库公式、交叉引用中均无物理来源也无引用 ⇒ **无效**，不作为有效地址发布。

- 生成器把这 25 个 cell 从种子 loader 的输入中清除（种子里本就只有它们、不影响其它格）；
- 逐个写进 `cell_verdicts`：`{addr_id, parent_sheet_code, verdict: "deprecate", replaced_by: "{父}/{sheet_code}"（指向上面 `add_platform_sheet` 新补的父 sheet addr_id，如 `I6/I6-7`）, reason: "该表格在模板册、渲染组件与真实底稿中均无对应表格，种子坐标无物理来源", evidence{renderer_tabs, project_files{file_path, parsed_data_null}, static_refs: 0, pg_formula_refs: 0}, owner, decided_on}`；
- 生成器据此产出 `deprecated: true` 的 cell 条目（`replaced_by` 为父 sheet），`cell_label` 为「{A1}（坐标待核对）」；默认**不进地址树**，acnr_targets 对它返回 422 `deprecated`（§2.3 分类表 `deprecated` 一类；不自动跟随）。保留别名指向（`replaced_by`）正是为了「将来若出现引用可解释、可导航到父 sheet 的项目实例」，符合铁律 3「被引用的 addr_id 不得静默消失」。
- 实施前仍须以当时 HEAD 现算复核一次：这 25 个 addr_id / formula_ref 是否被公式预设、真库公式（`wp_formula` / `report_config` / 公式设置各域 / `wp_user_formulas`）、交叉引用实际使用；**若发现被引用，不得静默消失**，须把该条从「无物理来源」降级为「保留父级限定别名或 deprecated + 可解析 `replaced_by`」并在 tasks 记证据，仍存疑则按铁律 3 暂停向用户说明。

D5-1 不在本节：它是 D5 册审定表 tab 的平台编号（§1.2），按需求 6.3「并入既有 sheet 作为别名」处置（§7.3），不新增 sheet。修正只落在 `sheet_verdicts.json`，不改 classification 缓存与 `global_catalog.json`（需求 2.4）。发布后目录 sheet 1215 + 5（补登父 sheet）+ 5（K14~K18 停用）= 1225；cell 474 − 25（孤儿停用）= 449 个有效 cell（另有 25 个 deprecated cell 条目与 14 个 §6.4 超范围停用 cell 条目，发布后 `parent_addr_id` 都在 sheets 集合内、孤儿计数 0）。

### 3.3 停用条目在各处的行为

下表同时适用于**停用 sheet**（K14~K18）与**停用 cell**（R2-F1 的 25 个孤儿 cell），二者 `full_resolve` 均带 `deprecated=true` + `replaced_by`；区别只在 `replaced_by` 分别指向替代 sheet 与父 sheet。

| 场景 | 行为 |
|---|---|
| `full_resolve` / `/api/acnr/resolve*` | `found=true`、`deprecated=true`、`replaced_by`、`reason`「该地址已停用，建议改用 {replaced_by 的 display_label}」（`ResolveResult` 只增 `deprecated`、`replaced_by`） |
| `resolve_instance` 与导航（GtIndexChip、`useWorkpaperNavigation`、下钻） | 不看停用标记，仍按 `wp_index.wp_code` 绑定项目已有底稿，导航可达；chip 提示附停用原因 |
| 公式保存校验 `validate_refs_via_acnr` | `found=true` 即接受，不出 issue；记 INFO 与指标 `deprecated_ref_saved`；公式编辑器的引用提示（`GtFormulaSourceTooltip`）显示停用原因 |
| acnr_targets | 422 `deprecated`（不自动跟随） |
| CCR 检查器 | 解析为停用条目计入报告 `deprecated` 组的引用清单，不阻断（现算 0 条） |
| `/api/acnr/entries`、`/tree` | 默认不列出，`include_deprecated=true` 时列出；`/anchors` 不受影响 |

承接登记（段七复审 RV7-03，2026-10-28）：上表各行由哪个任务落地——`full_resolve` / 保存校验接受与指标 / `/entries` 默认不列已随 T10；acnr_targets 422 `deprecated` 随 T14；CCR 检查器「计入报告 `deprecated` 组」随 T22（T10 时只在 `check_ccr_resolve` 输出里计数，T22 重写检查器时把这份清单写进其报告并钉住计数）；chip 提示附停用原因与 `GtFormulaSourceTooltip` 显示停用原因随 T31（同属「可解释原因」的前端展示）。前端另有两处按 sheet 列单元格的入口（`FormulaRefPicker.vue` 的 `acnr.listCells`、`stores/addressRegistry.ts` 的搜索）仍列出停用 cell（RV7-02），随 T30 改为与 `useAcnr.loadCellNodes` 同口径。

### 3.4 验证

- `test_sheet_verdicts.py`：`sheet_verdicts` 与 `cell_verdicts` 两段结构；sheet 结论在三种内、cell 结论为 `deprecate`；离线证据现算（openpyxl 读模板 tab、渲染 schema `renderer_tabs`、缓存、种子、manifest、映射、K14 的 6115 依据，以及 25 个孤儿 cell 的 `static_refs=0` / `pg_formula_refs=0` 现算）与记录逐项相等，变了即红；`pg_only` 断言「在用」记录的 wp_index 计数仍 > 0，且 25 个孤儿 cell 的 `project_files.parsed_data_null` 为真。
- `test_catalog_release_integrity.py`：读真实目录，孤儿 0（含停用）；**原 25 个孤儿 cell 发布后都是 `deprecated=true` 条目**，逐个 `full_resolve` 命中并带可解析的 `replaced_by`（父 sheet），默认不进地址树（`/api/acnr/tree`、`/entries` 不列出，`include_deprecated=true` 时列出）；acnr_targets 对它们返回 422 `deprecated`。K14~K18 五个 sheet addr_id 逐个 `full_resolve` 可解析、带 `replaced_by`；5 张补登父 sheet 经 TestClient `/api/acnr/entries` 列出，K14~K18 默认不列出。
- `test_deprecated_navigation_pg.py`（`pg_only`、只读）：4 个项目的 K14~K18 底稿经 `resolve_instance` 可达，`full_resolve` 标停用；孤儿 cell 的父 sheet（如 I6-7）在有 wp_index 实例的项目里经 `resolve_instance` 可达（导航落到已有实例）。
- 变异：从 `sheet_verdicts.json` 删 I6-7 的 sheet 条目 → 门禁报孤儿并点名 `I6/I6-7`；把某个孤儿 cell 的 `verdict` 改回有效（不清除、不停用）→ `test_catalog_release_integrity` 报「无物理来源的有效 cell」并红；K15 的 `replaced_by` 改成不存在的地址 → 门禁红；直接改 `global_catalog.json` 删一个父 sheet → `--check` 红。

## 4. D3　目录契约只有一份（需求 3）

### 4.1 现状确认

`docs/acnr/schemas/_build_schema.py` 手写枚举生成 schema，`_verify_schema.py` 只校验样例。真实目录 functional_type 10 种（838 条缺省），schema 的 8 个枚举只有 detail_table 重合；purpose 183 种全部满足 `^[a-z][a-z0-9_]{0,63}$`（最长 28），消费方只有写入的种子 loader、`useAcnr.ts` 类型与 `useH3TitleCrossSheet.ts` 1 处读取，无按取值分支的逻辑。

### 4.2 方案

新模块 `services/acnr/catalog_contract.py` 为唯一来源，`build_schema() -> dict`（Draft-07）由它生成，生成器同批写出 schema 文件（`--check` 比对），`_build_schema.py` / `_verify_schema.py` 删除（删前 grep 调用方）。常量逐项：

| 常量 | 取值 |
|---|---|
| `REGISTRY_VERSION_PATTERN` | `^\d{14}$` |
| `FUNCTIONAL_TYPES` | impairment、confirmation、detail_table、sampling、aging、monthly_analysis、cutoff、reconciliation、depreciation、amortization（缺省时省略字段） |
| `PURPOSE_PATTERN` | `^[a-z][a-z0-9_]{0,63}$`（受控模式：183 种长尾自由值、无分支消费方，列词表只是冻结噪声） |
| `SOURCE_OF_TRUTH` | `classification_db`、`sheet_verdicts`（补登与停用条目） |
| `EDITOR_ENGINES` | html、univer、onlyoffice、mixed（现值 html 1198 / univer 16 / onlyoffice 1） |
| `SKIP_REASONS` | null、no_import_export、univer_only、onlyoffice_only、procedure_checkbox、word_template、readonly_directory、custom_univer_only（沿用现 schema，现值全为 null） |

`import_export.item_id` 为 `oneOf: string | array<string>`（`minItems 1`、`uniqueItems`）。新增字段：sheet 的 `deprecated`、`deprecated_at_version`、`replaced_by`；cell 的 `deprecated`、`replaced_by`、`display_label`、`cell_label`；顶层 `alias_policy`（§7.2）。sheet 的 `display_label` 保留字段名，取值规则改为 §13 的统一显示名（描述随之更新）。`additionalProperties: false` 与禁止 `project_id` / `wp_id` 保留。生成器写出前用 `Draft7Validator(build_schema())` 校验内存目录，`--check` 校验已提交产物，错误点名 `error.absolute_path`；词表外 functional_type 或不合模式的 purpose 即失败并点名 addr_id。`backend/requirements.txt` 增 `jsonschema==4.26.0`。

### 4.3 验证

`test_catalog_schema_single_source.py`：schema 文件与 `build_schema()` 逐字节相等；四类约束与常量逐值相等；真实目录 0 错误；4 份历史快照只做加载测试。变异（产物副本）：注入词表外 functional_type、`registry_version="2026.1.1"`、删 `sheet_code`、给 cell 加 `project_id` → 生成器与 `--check` 各自报错并点名 JSON 路径。

## 5. D4　生成器发布门禁（需求 4）

### 5.1 现状确认

`generate_catalog.py` 写出前不查重复、外键、往返、不可变；`write_catalog` 遇同名快照静默跳过；分片 `catalog_ALL.json` 0 条、`catalog_D.json` 停在 20260710102744，全仓无消费方；`check_catalog_drift.py` 同版本重算后文本比对。已提交目录与重算差 57 张 sheet（p08、p37）：import_export 53 张、别名 4 张（G1-8、G1-10、G1-12、G1A）。53 张的来源：D1-15 与 G4/G6/G7 的 14 张是 `fix_acnr_dangling_api_prefix.FIX_MAP` 改的 api_prefix；H5-2/H5-3/H7-2/H7-3、I 循环 24 张、L1/L3/L4/L5 的 8 张、N4-2/N4-3 是 `fix_acnr_catalog_ie_gap` SAFE 档（13 个前缀，item_id / storage_field 从后端 specs 字典 AST 抽取且有 bulk 适配器）直接写进目录的条目。

### 5.2 门禁模块

新模块 `services/acnr/catalog_release.py`（生成器、CI、测试共用）：`GateViolation(check, addr_id, detail)`；`run_release_gates(new, previous, report, *, today) -> list[GateViolation]` 全部跑完再汇总，`check` ∈ schema / duplicate / sheet_code / orphan / a1 / roundtrip / immutable / alias / ack / verdict / override。往返用新目录解析：`catalog.py` 增 `use_catalog(index)`（`ContextVar` 覆盖，只供门禁与测试；守卫断言生产代码不调用）。

段四审计 F4-08 补记（实现细节，不改上述口径）：①往返的身份判定用 `exact_identity`，`sheet:{code}` / `cell:{code}!{A1}` 用生产解析函数 `catalog._index_ref_to_addr_id`（在 `use_catalog(新目录)` 内），父 sheet 不在目录的 cell 只由 orphan 报；②immutable 用 `immutability.validate_addr_id_immutable`（`check_addr_id_immutable` 的不抛版本，同一判据）；③「所指问题是否还在」需要本批次现算的问题清单，约定由生成器在跑门禁前放进 `report["open_problems"]`：`unregistered_alias_keys`（标签源里不在目录的键，§7.3 的 28 条属此类）、`alias_conflicts`（别名冲突，§7.2）、`ccr_unresolved`（§10.3 统一判定后仍不可解析的 CCR id），分别由 T07 / T09 / T22 产出；覆盖这几类问题的 `alias_policy`（non_address_label / merge_into）与豁免在对应清单缺失时按「无法核实」阻断，不放行；④带 `head_resolvable_at` 的豁免须登记 `writing{wp_code, sheet}`（HEAD 时错配的那条写法），写法在新目录里若已解析到别的 sheet 即判失效（§7.4）。

### 5.3 生成流程、幂等与 `--check`

CLI 只保留 `--write`（缺省）、`--check`、`--registry-version`；删除 `--offline`（恒读缓存，参数无意义）、`--cycle` 与 `--no-shards`（单循环写出会缺其他循环的 import_export）。**R2-N3：`generate_catalog()` 函数签名保留 `offline`（接受但忽略）与 `cycle` 关键字参数**（`test_x3_ie_manifest_registration.py` L274/441/622/637、`test_x3_ie_registrar.py` L436 以 `generate_catalog(offline=True, …, cycle=…)` 调用，须保持全绿），只删 CLI 选项；同步改模块 docstring 的 Usage（L6）。函数参数 `cycle` 只留给单测，非 `"all"` 时 `write_catalog` 拒写。流程：

1. 加载全部输入：classification 缓存、I/E manifest、render registry、标签源、种子、`wp_account_mapping.json`、`sheet_display_names.json`、`sheet_verdicts.json`、`alias_policy.json`、`acknowledgements.json`、`global_catalog.overrides.json`、`release_exceptions.json`，以及**上一发布批次的快照**（由上一份报告的 `release.registry_version` 定位到 `catalog_snapshots/{版本}.json`，§6.3 别名沿用的唯一来源）；`inputs_fingerprint` = 按相对路径排序的 `(路径, sha256)` 再取 sha256（**含上一批次快照文件的 sha256**，不含绝对路径与时间）。首个合规批次无上一批次时，沿用来源为空、`previous_version=null`。
2. 以上一批次版本号构建一次；目录与报告（不计 `generated_at`）都与已提交产物逐字节相等 → 不写任何文件，退出 0。
3. 否则以新版本号（UTC `%Y%m%d%H%M%S` 或显式值）重建并跑门禁；有违规按 `check` 分组打印、退出 1、不写文件。
4. 通过后同批写出：快照 `{版本}.json`（与目录同字节）→ schema → 报告（含 `release`：版本、`previous_version`（上一批次版本号，用于 `--check` 定位沿用来源）、目录 sha256、schema sha256、`inputs_fingerprint`、`classification`）→ 目录；每个文件先写临时文件再 `os.replace`，中途失败由加载期互校拒绝不一致批次，重跑即恢复。
5. 已存在同名快照且内容不同 → 失败。唯一例外登记在 `release_exceptions.json`：20260727115337 的快照内容 sha256（前缀 e98a127ed7c4f275）与已提交目录内容 sha256（前缀 b3a988ed2dc63e67）各记全长，哈希不匹配即失效；以该快照为此版本权威内容（目前无项目锁定任何版本，§8）。哈希口径（段四审计 F4-07 更正）：一律是 LF 规范内容的 sha256（`catalog_integrity.content_sha256`，即 git blob 内容哈希）；此前记的 ee0032ffcab40663 / 95175fcbcf97203d 是 Windows CRLF 检出字节的哈希，Linux 检出不成立。

报告 `generated_at` 只在其余内容变化时更新。`--check` 以已提交版本号重算（别名沿用来源取已提交报告 `release.previous_version` 对应的快照，不读工作区目录），结构化比对目录（逐 addr_id 逐字段）、报告、schema、当前版本快照，漂移退出 2 并逐条打印 `addr_id: 字段`（最多 50 条另报总数）；同时对已提交产物跑门禁，违规退出 1。CI 改为 `generate_catalog.py --check`，`check_catalog_drift.py` 改为调用同一 `main(["--check"])` 的薄壳。分片不再产出，删 `shards/` 两个文件与 `write_shards` / `_cell_belongs_to_cycle`（删前重 grep）。

### 5.4 外科补丁迁回输入（与 x3 治理对齐）

| 差异 | 落点 | 依据 |
|---|---|---|
| D 1、G 14（api_prefix） | `d_` / `g_cycle_ie_manifest.yaml` 改为已核验前缀 | 全量登记循环，manifest 即该循环 I/E 真源；manifest 只被生成器与检查器读取 |
| H 4、I 24、L 8、N 2（共 38） | `global_catalog.overrides.json`（生成器 Step 6，现为空），每条 `{addr_id, fields:{import_export}, reason, owner, source:"fix_acnr_catalog_ie_gap:SAFE:{前缀}"}` | 值由 SAFE 档 AST 抽取复算，可伪证；partial manifest 与 `_PARTIAL_UNCOVERED_BASELINE={"L":8,"M":0,"N":2}` 不动 |
| 别名 4 张 | 不迁 | 标签源为权威，已提交值是旧值；按 §6.3 沿用规则保留，重算值为已提交值的超集 |

脚本改动：`fix_acnr_catalog_ie_gap` 的 `--apply` 改写 overrides 文件（不再写目录）；`--check` 保留现有缺口判定（现跑：可安全补 0、已登记不补 28），另对 overrides 中每条 SAFE 来源条目用脚本同一 AST 抽取逻辑现算 api_prefix / item_id / storage_field 并逐字段比对（CI 已在跑它的 `--check`）；`fix_acnr_dangling_api_prefix` 删写入分支，`--check` 改为核对 manifest 中 FIX_MAP 目标前缀与适配器；`fix_x3_adjustment_ie_registration` 的 16 张 X-3 表本就在 partial manifest，生成器已产出，删其目录写入分支、`--check` 改为核对生成后的目录；`gen_cycle_import_export_registry` 不变。`check_ie_catalog_sync` 的 Step 4（全量登记循环）增加一种登记来源：该 sheet 的目录 import_export 与一条 `source` 以 `fix_acnr_catalog_ie_gap:SAFE:` 开头的 override 逐字段相等，即视为已登记并在输出中点名「经 overrides 登记」（只影响 H 4）；其余判据与 partial 模式不变。

守卫 `test_only_generator_writes_catalog.py`（AST，扫描 `backend/app` 与 `backend/scripts`，排除 `backend/tests`）：既引用 `global_catalog.json` 字面量又调用写文件 API 的模块集合恰为 `{scripts/acnr/generate_catalog.py}`。`test_overrides_provenance.py`：每条 override 有 owner、reason、可识别的 `source`，所指 sheet 在骨架中存在，SAFE 条目与脚本现算相等。

迁移验收（现跑并记录输出）：53 张 import_export 与迁移前已提交目录逐字段相等；4 张别名 sheet 的别名 ⊇ 已提交值；`check_ie_catalog_sync`、四个 fix / gen 脚本 `--check`、`check_x3_deviation_registry.py --check`、`test_x3_ie_registrar.py`（含 `test_real_preflight_is_16_of_16`）、`test_x3_ie_manifest_registration.py`、`test_x3_ie_catalog_sync_partial_mode.py`、CI X3 作业列出的 `test_x3_*` 全绿。

### 5.5 CatalogIndex fail-closed 与加载期互校

- `CatalogIndex.__init__` 收集三类重复（sheets 内、cells 内、互撞），非空即抛 `CatalogIntegrityError(duplicates)`（继承 `CatalogLoadError`），消息列前 10 个与总数。sheet_code 重复不在此拦（以列表承载、解析时报歧义）。同时建 `sheets_by_parent`、父级禁止别名、名称归属三个索引（§6.2）。
- `_load_catalog` 把它并入现有降级分支：有上一版缓存则只读上一版并 `_alert_admin("catalog_integrity_failed")`，无缓存则失败；`load_versioned_catalog` 遇到它上抛（§8 映射 409）。
- 加载期互校：目录同目录有 `catalog_report.json` 时比对 `release.registry_version` 与 `release.catalog_sha256`，不一致按 `CatalogIntegrityError`；默认生产路径缺报告同样处理；`ACNR_CATALOG_PATH` 指向的测试目录无报告时跳过（守卫断言生产路径报告存在）。
- 段四审计 F4-07 落实（实现在 `services/acnr/catalog_integrity.py`，`catalog.py` 只做薄封装并把执行状态写进 `CatalogIndex.release_check_status`）：release 段存在时 `registry_version` 与 `catalog_sha256` 两个字段必填（缺字段、键名写错即失败，不再「缺字段就跳过」）；报告无法解析即失败；内容哈希一律按 LF 规范内容计算。T08 先于 T07 入库（与 §18 发布顺序①不符），过渡期内对无 release 段的报告跳过互校、运行时行为不变，过渡期由 `LEGACY_REPORT_WITHOUT_RELEASE` 登记（owner、理由、到期 2027-01-31、退出条件）；守卫 `test_production_report_release_or_registered_legacy` 钉住「生产报告无 release 段 ⇒ 必须是登记的那份旧报告（内容哈希相等）且未过期」「生产报告有 release 段 ⇒ 互校真实执行（状态 checked）且登记已删除」——T07 漏写或写错 release 段、报告被改动都会红，登记删除后无 release 段的报告一律被加载器拒绝。
- 验证：合成三类重复各一例；真实目录与 4 份快照全部可加载；临时目录注入重复后分别验证「无缓存失败」与「有缓存降级 + 告警」。加载耗时基线（p28，7 次中位）8.3 ms，加检测与互校后 ≤ 10.0 ms。

### 5.6 验证（门禁整体）

- 变异（输入或产物副本）：注入重复 addr_id、删父 sheet、改 cell 的 A1、删已发布 addr_id、改 parent_wp_code、删一条 override 的 `source` → 门禁各自红在对应 `check`；绕过生成器改 `global_catalog.json` → `--check` 退出 2 并点名。**R2-F11 新增变异：只在 `global_catalog.json` 中给某 sheet 加一个别名（不改任何输入与上一批次快照）→ `--check` 必须退出 2 并点名该 addr_id 的别名字段**（证明沿用来源是上一批次快照、不是工作区目录）。
- 幂等：连续两次生成 sha256 相同且第二次不写文件；改一条种子后版本号变化、旧快照内容不变；4 份既有快照内容 sha256（LF 规范内容）前缀保持 8645205d291992d3、ba831e5f75e1857b、8c0a7c47ec3211cd、e98a127ed7c4f275（段四审计 F4-07：原记 3ab8a81e… 等为 CRLF 检出字节口径，已更正；守卫 `test_catalog_index_fail_closed::test_snapshot_content_hashes_pinned` 钉住）。
- 确定性：指纹与报告不含绝对路径与机器名；CI 中门禁全量 < 2 分钟。

## 6. D4　名称体系与往返（需求 5）

### 6.1 现状确认

同一 sheet 有三套名字：模板 sheet 名（目录 `sheet_name`，来自 classification）、平台底稿索引名（`wp_account_mapping.wp_name` = 项目 `wp_index.wp_name`）、种子名。cell 的 `formula_ref` / `uri` 由种子 loader 用种子名拼出，只有 30/474 能往返；失败 444 = 索引名 372 + 三名都不同 47 + 孤儿 25。解析侧依次「同父同名首个命中 → 同父 sheet_code → 别名父级内唯一 → 名称含 sheet_code 取最长（子串）→ 直接拼接」，第一步在 78 组上任选其一。CCR 检查器 `check_ccr_resolve._find_sheet`（L150-171）另有一套「编码 → 名称首个命中 → 子串」判定，与运行时不一致：现算 94 个 CCR 源被它解析到别的 sheet（如「ERP销售订单核对D4-13」被判为 D4-1）。

### 6.2 唯一的精确身份判定：`exact_identity`

新模块 `backend/app/services/acnr/exact_identity.py`，纯函数，输入 `CatalogIndex`（缺省 `get_catalog()`，可传入任意索引）：

- `sheet_of(wp_code, text) -> SheetMatch(state, entry, match_kind, reason, candidates, required_context)`，`state` ∈ ok / ambiguous / alias_forbidden / not_found / wp_not_in_catalog。规则按序（文本逐字比较，不做空白或全半角归一）：
  1. 父级：`wp_code` 是某 sheet 的 `parent_wp_code` 即为父级 P；否则若是某 sheet 的 `sheet_code`，P 取其父级（`text` 为空时直接取该 sheet）；都不是 → `wp_not_in_catalog`。
  2. `text` 等于 P 内某 sheet 的 `sheet_code` → ok（`sheet_code`）。
  3. `text` 属于 P 的禁止集合 → `alias_forbidden`，带禁止理由与候选。
  4. P 内恰一个 sheet 的 `sheet_name == text` → ok（`sheet_name`）。
  5. 没有 sheet_name 命中、P 内恰一个 sheet 的别名（含平台索引名）`== text` → ok（`alias`）。
  6. 编码词元裁决：候选池 = 第 4 / 5 步命中 ≥ 2 个时取这些 sheet，否则取 P 内全部 sheet；池中 `sheet_code` 以完整词元出现在 `text` 里（左右相邻字符都不是 `[A-Za-z0-9-]`）的，取编码最长且唯一者 → ok（`code_token`）；最长并列 → ambiguous。
  7. 第 4 / 5 步命中 ≥ 2 而第 6 步无结果 → ambiguous（候选 ≤5，`required_context=["sheet_code"]`）；否则 → `not_found`。
- `cell_of(wp_code, sheet_text, a1) -> CellMatch(state, addr_id, in_catalog, reason)`：A1 须匹配 `^[A-Z]{1,3}[0-9]{1,7}$`（大写归一），sheet 用 `sheet_of`，得到 `{sheet.addr_id}/{A1}`，`in_catalog` 标是否为登记 cell。
- `name_owner(parent, name) -> entry | None`：该名在父级内按第 4~7 步裁出的唯一 sheet。现算 78 组：70 组有唯一所属，8 组为 None（§1.2）。
- 不变量（门禁 `alias` 检查）：父级禁止集合与父级内 sheet_name、sheet_code 不相交。

使用者（全部改为调用它，不再各自判定）：`catalog._formula_ref_to_addr_id` / `_uri_to_addr_id`（结构化版本 `_formula_ref_to_sheet_match` / `_uri_to_sheet_match` 前置调用；ambiguous / alias_forbidden 直接作为结果，not_found 即未命中，删除子串与直接拼接两段旧启发式；原签名保留为薄壳，歧义返回 None），`full_resolve` 第 1 步（歧义返回 `found=false`、`error="ambiguous"`、`reason`、`required_context`、`candidates`），`acnr.wp_cell_target`（§2.4），`check_ccr_resolve`（`_find_sheet` 改为委托 `sheet_of`、删私有匹配；该脚本只依赖标准库，`app.services.acnr.catalog` / `exact_identity` / `reasons` 也只导入标准库，CI 无需新增依赖；AST 守卫钉住这三个模块的导入集合），V2 规范化与 stale 引擎（§10），发布门禁往返与生成器名称规则（§6.3）。`catalog.py` 现 747 行（上限 800），新增逻辑放 `exact_identity.py`，删旧启发式后净减。

### 6.3 生成器的名称规则

- cell 的 `formula_ref` / `uri` 在合并完所有 sheet 后统一生成：父 sheet 的模板名归属本 sheet（`name_owner` 是它）时第二参用模板名，否则用 sheet_code。预演：非孤儿 449 个 cell 全部往返（含 `F2/F2-34/B20`，改用编码）。
- 新 loader `from_wp_account_mapping.py`：`wp_name` 与模板名不同时并入别名；同一名字在父级内对应多个 sheet（现算 9 组）时对这些 sheet 一律记禁止别名，理由「平台底稿名「X」在 {父级} 下同时用于 {编码…}，请改用 sheet 编码」；只跨父级重名（6 组）按父级限定别名保留。并入前断言 `sheet_of(P, 平台名)` 回到本 sheet（r05 现算冲突 0）。
- 别名沿用（R2-F11：「上一发布批次」有明确来源，不取工作区 `global_catalog.json`）：上一批次定为报告 `release.previous_version` 对应的**快照**文件，读取时校验其 sha256 等于当时报告记录的 `release.catalog_sha256`（§5.3），并把该 sha256 计入本次 `inputs_fingerprint`。该快照中某 addr_id 的别名在本次输入中消失时仍保留（`alias_policy` 明确禁止的除外），别名只增不减，G1 四张的旧别名由此保留。**不取工作区目录作沿用来源**，否则手工往 `global_catalog.json` 加的别名会被「沿用」原样重算出来、`--check` 照样退出 0（需求 4.8 对这类变异落空）；§5.6 据此加变异「只在 `global_catalog.json` 加一个别名 → `--check` 退出 2 并点名」。
- `display_label` / `cell_label` 在这里生成（§13）。

### 6.4 13 张种子名不一致的 sheet（需求 5.5）

逐格证据见 §1.2（p42）：13 张的编码绑定都与种子一致，种子名与模板名、平台名都不同，同册里没有种子名对应的 tab。处置按需求 5.5 修订后的三路：

- 坐标在模板已用范围内（33 格）：地址保留（真实物理格），`formula_ref` 按 §6.3 用模板名；种子语义与模板行文字不符，生成器输出 `semantic_label=null`、`cell_label="{A1}（语义待核对）"`，原种子语义记入豁免 `seed_semantic_unverified`（owner、到期 2027-04-30，覆盖 33 个 addr_id），选址器与结果区据此显示「语义待核对」。
- 坐标超出模板已用范围（14 格）：`deprecated` + `replaced_by` 父 sheet addr_id，`reason`「种子坐标超出模板已用范围（{sheet} 共 {max_row} 行 {max_col} 列）」；默认不进地址树。
- 挂错 sheet：0 张。
- 种子名不作别名（描述的不是这张 sheet）。47 个 addr_id 现算引用 0 处（p43），停用不影响任何公式或模板。逐格重新核对种子属范围外工程（§16 Q3）。判定逐格写进 `sheet_verdicts.json` 的 `cell_verdicts` 段（证据含行文字、模板范围、本格值）。

### 6.5 往返、保存校验与基线夹具

- 往返门禁与 `test_catalog_roundtrip_real.py`（读真实目录、禁止 mock）：每个非停用 cell 的 addr_id、formula_ref、uri、`cell:{sheet_code}!{A1}` 经 `full_resolve` 回到自身；每个 sheet 的 addr_id、`sheet:{sheet_code}` 回到自身。
- `validate_refs_via_acnr` 的 fail-open 分支先 `except (VersionNotFoundError, CatalogIntegrityError): raise`。
- `test_picker_refs_pass_save_validation_pg.py`（`pg_only`、只读、回滚）：以安徽骨科医院_2025 为上下文，对目录全部非停用 cell 的 `formula_ref` 调 `validate_refs_via_acnr`，拒绝数 0。
- 固定夹具（实施第一步从 HEAD 目录导出并提交，之后不随目录变化）：`platform_name_writings.json`（372 条索引名写法 → 期望 addr_id）、`same_name_group_writings.json`（26 处静态写法 → 名称所属 sheet，如 `WP('H1','审定表H1-1','本期增加')` → `H1/H1-1`）、`resolvable_writings_baseline.json`（每张 sheet 的 sheet_code / 模板名 / 既有别名，现算 2599 条：结果不变 2434；同父同名组内由借名的父级改判到名称所属 sheet 147；8 个多义组的 18 条改为 `ambiguous`——均为合成写法，静态数据与 PG 中 0 处真实使用）。需求 5.4 原文据此修订。
- **R2-F2（勘误并补）：`resolvable_writings_baseline.json` 的「仅靠旧子串启发式命中 现算 0」只对上述合成基线成立（按构造就不含子串写法），是错口径。** 实施第一步须另跑真实数据的 HEAD 可解析集并导出独立夹具 `head_resolvable_static_writings.json`：用 HEAD 运行时 `catalog._formula_ref_to_addr_id` 四步判定，遍历全部静态写法（`cross_wp_references` 的 source 与 `targets.formula`、`formula_presets_seed.json` 的 `expression` 与 `refs[].formula_ref`、`prefill_formula_mapping.json`、渲染 schema 内公式）与 PG 公式存储（`wp_formula.expression`、`report_config`、公式设置各域表、附注公式、`wp_user_formulas`），记录「写法 → HEAD addr_id」。现算复核（q03，预设用 `WP('D5', 'D5-1', '审定数')` 带逗号后空格，前述零口径正因正则漏了空格）：**只靠子串一步命中、按 §6.2 编码完整词元规则会变 not_found 的有 14 处 / 7 组**——`formula_presets_seed.json` 的 `report-cross-check-rw-74 WP('D5','D5-1','审定数')`（`expression`+`refs` 各 1）与 `rw-83 WP('I1','I1-1','审定数')`（各 1）共 4 处（HEAD 分别落到 D5/D5、I1/I1）；CCR 10 处（`审定表I1-1`×4→I1/I1、`B23-2 货币资金控制了解`×2→B23/B23、`摊销测算表（不含减值）I1-10（剩余年限法）`×2→I1/I1、`A13-3 评价识别出的错报`、`错报明细A13-2` 各 1→A13/A13）。
- 处置（发布后对 `head_resolvable_static_writings.json` 逐条断言仍可解析或有登记处置，否则红）：
  - D5-1、I1-1、审定表I1-1 三组共 8 处，HEAD 的父 sheet 结果业务上正确（与 §1.2/§7.3 判 D5-1=D5 审定表 tab 同一依据，2025 审定表编 n-1）：经 `alias_policy` `merge_into` 落父级限定别名——D5/D5 加别名键「D5-1」、I1/I1 加「I1-1」「审定表I1-1」（证据：模板 tab 名「审定表D5」「审定表I1」+ 映射科目同一），由 `exact_identity` 第 4/5 步命中，发布后仍解析到父 sheet；
  - 其余 4 组（B23-2、I1-10、A13-2、A13-3）原本就解析到错误的父 sheet（错配），不是正确结果、不加别名：逐条登记 `ccr_unresolved` 豁免，并**显式标注 `head_resolvable_at: {HEAD addr_id}`（即「HEAD 原可解析到父 sheet（错配）」）**，owner 按循环、到期 2027-04-30，使「HEAD 能解析、改动后变 not_found」在清单里可见、可追责（满足需求 5.4 与铁律 3）；
  - 导出时若出现清单外的「仅靠旧子串启发式命中」写法，逐条登记并暂停向用户说明。
- 变异：某循环 cell 的 formula_ref 改回索引名写法并删对应别名 → 往返与保存校验用例红；`exact_identity` 第 6 步改成「取第一个」→ 同名组夹具红；删一条禁止别名 → `alias` 门禁红。

## 7. D4　报告可追责与别名处置（需求 6）

### 7.1 报告分组

`catalog_report.json` 改为四组 `{"count": n, "items": [...]}`（`count` 由 `len(items)` 计算）：`blocking`（未处置冲突与未登记别名、过期或失效豁免、门禁违规；发布时必须为 0，故已提交报告恒为 0）、`acknowledged`（有效豁免）、`deprecated`（停用条目、`replaced_by`、仍引用停用条目的 CCR 源）、`info`（父级限定别名、禁止别名、非地址标签、沿用旧别名、补登 sheet、经 overrides 登记的 I/E、显示名为纯编码的 sheet）。另有 `release` 段（§5.3）。旧 `summary` 只留 `total_sheets`、`total_cells` 与四组计数；`gap_count` 等三个旧字段在 grep `catalog_report` 改完读取方后删除。**R2-N2：`catalog_report.json` 现有读取方同批改写**——`scripts/check/check_acnr_catalog_drift.py`（校验 `gap_count` 守恒、且要求 `generated_at` 不超过 7 天，后者与「内容不变则时间戳沿用」的幂等规则冲突，删掉陈旧度判据或整体并入 `--check`）、`tests/acnr/test_catalog_gap_count_integrity.py::TestRealCatalogReport`（读真实报告，改为断言四组 `count==len(items)`）。

### 7.2 别名冲突三类处置

新生成器输入 `sources/alias_policy.json`，条目 `{alias, sheet_codes, disposition, reason, owner}`，`disposition` ∈ `parent_qualified` / `forbidden` / `project_context` / `non_address_label` / `merge_into`（带 `target`）。生成器对「标签源别名 ∪ 平台索引名」按父级分组判冲突：只跨父级重名 → 自动 `parent_qualified`（缺父级时返回歧义与 `required_context=["parent_wp_code"]`）；父级内多义 → 须有 `forbidden`（平台索引名按 §6.3 自动生成），否则 blocking；`project_context` 0 条。禁止别名写入目录顶层 `alias_policy.forbidden`，`exact_identity` 第 3 步据此返回理由。现算 4 条冲突：「底稿目录」对 D5、D6、D7、G8~G14、H10 共 11 张记 `forbidden`（各工作簿目录页的通用名，而这些 sheet 是审定表或程序表，如 D5 是「审定表D5」），其余成员是未登记键随 §7.3 处置；另三组成员全是未登记键，处置后不再有目录内冲突。

### 7.3 未登记别名 28 条

| 键 | 处置 | 理由 |
|---|---|---|
| D5-1 | `merge_into` → `D5/D5`（别名「应收款项融资审定表D5-1」） | D5 册审定表 tab 的平台编号（§1.2）；并入后平台名「应收款项融资审定表」在 D5 父级内唯一，不再是禁止别名 |
| D4-目录、D5-目录、D6-目录、D7-目录、G8~G14-目录、H10-目录（12 个） | `non_address_label` | 前端 tab 伪键；目录页无可寻址单元格 |
| D4/D5/D6/D7 的「附注上市」「附注国企」（8 个）、附注上市、附注国企 | `non_address_label` | 前端 tab 伪键；附注披露 tab 未收录目录（补齐属范围外） |
| D4-31T、D4-访谈模板 | `non_address_label` | 示例 / 模板 tab |
| D4A、D4-22A | `non_address_label` | D4 册程序表 tab，目录未收录（§16 Q4） |
| 参考中证协 | `non_address_label` | 参考资料 tab |

合计 1 + 12 + 10 + 2 + 2 + 1 = 28。`non_address_label` 可伪证：守卫断言该键仍在标签源中且不是目录 sheet_code，否则为失效条目。

### 7.4 豁免清单

`sources/acknowledgements.json`，条目 `{id, kind, covers{sheet_codes|addr_ids|ccr_ids|aliases}, owner, reason, created_on, expires_on, evidence, head_resolvable_at?}`，`kind` ∈ `seed_semantic_unverified`（§6.4，33 格）/ `ccr_unresolved`（§10.3，R2-F3 后 ≥48 条逐条，含 B60 的 6 条与 S14 的 1 条）/ `head_resolvable_errmatch`（§6.5 的 4 组子串错配写法，带 `head_resolvable_at`）。门禁：`expires_on < 今天（UTC）`→ blocking；所覆盖问题已不存在 → blocking「清单有失效条目」；带 `head_resolvable_at` 的条目若其写法在发布后目录里反而能正确解析（不再错配），也判失效。到期判定只在门禁运行时计算、不写入报告。

### 7.5 验证

`test_catalog_report_buckets.py`：四组 `count == len(items)`；真实报告 blocking 0；4 条冲突与 28 条未登记逐条有处置。变异：一条豁免到期日改到过去、删一条豁免所指问题的来源、删一条禁止别名 → 各自红。

## 8. D5　归档项目按归档时的目录解析（需求 7）

### 8.1 现状确认与口径

版本锁只在 `immutability._project_registry_versions`（进程内），生产调用方 0；现算没有任何项目处于归档（§1.2）。`Project.status` 写入点（AST，4 个函数）：置 archived 1 处（`deliverable_service` 交付件全部归档后）；离开 archived 1 处（`archived_exception.unarchive_project`，要求 `status == archived`、改回 execution）；`event_handlers/_impl` 只从 created / planning 推进到 execution；`project_wizard_service.confirm_project` 无前置条件地置 planning（其路由只要求登录，§16 Q14）。归档作业 `archive_orchestrator._set_project_retention` 只写 `archived_at` / `retention_until`、不改 status。平台的只读判定 `deps._check_project_not_archived` 与取消归档都只看 `status`。

裁定：**锁定与解锁都以 `status` 为准**——`status` 置为 archived 的同一事务内加锁，离开 archived 的同一事务内解锁；只写 `archived_at` 的归档作业不加锁（这类项目仍可编辑、按当前目录解析，与平台只读口径一致，避免「选得到保存不了」与无法解锁）。由此锁定项目集合 ⊆ status=archived 集合 = 有解锁路径的集合。归档作业与「取消归档不清 archived_at」的语义统一归归档模块（§16 Q9）。需求 7.2 原文据此修订。

### 8.2 持久化：加列

裁定加列：锁与项目一对一、每次带项目解析都要读、写入方本就在改 `Project` 这一行。

- 迁移 `V{N}__acnr_project_registry_lock.sql`：`ALTER TABLE projects ADD COLUMN IF NOT EXISTS acnr_registry_version VARCHAR(14);`、`... acnr_registry_locked_at TIMESTAMPTZ;`；配对 `R{N}__...sql` 用 `DROP COLUMN IF EXISTS`。版本号：实施时现扫 `backend/migrations/V*.sql`（含未跟踪文件，对照 gt-plan `migration_status` 与其他 worktree 的未提交迁移；formula-hub、advanced-query 也计划新迁移）取最大 + 1；当前最大 V205（无未跟踪）。
- ORM：`acnr_registry_version: Mapped[str | None] = mapped_column(sa.String(14), nullable=True)`、`acnr_registry_locked_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)`，`@validates` 校验 `^\d{14}$`。存量为空即未锁定，不回填。共享开发库用 `MigrationRunner(...).run_pending()` 落库。

### 8.3 接线

新模块 `services/acnr/project_registry_lock.py`：

- `lock_project_registry(project, *, now)`：已锁定不改（幂等）；否则取当前目录版本，要求 `catalog_snapshots/{版本}.json` 存在且 sha256 等于当前目录文件（`CatalogIndex` 加载时记录 `content_sha256`），不满足抛 `RegistryLockError`「当前地址目录版本 {v} 没有对应快照，不能锁定」。依赖 §5 的首个合规发布批次（§18）。
- `unlock_project_registry(project)`：两列置空。
- `async get_locked_version(db, project_id) -> str | None`：按主键读一列，记忆在 `db.info["acnr_lock"]`（请求级会话即请求级记忆，同一请求每项目 1 次查询；不跨请求缓存，避免另一 worker 归档后读到旧值）。

写入方：`deliverable_service` 在 `project.status = ProjectStatus.archived` 之前调用 `lock_project_registry`，失败异常上抛、路由不提交，交付件归档状态一并回滚（`deliverable_service.py` 925 行、阈值 970，净增 ≤ 6）；`unarchive_project` 改状态的同一事务内 `unlock_project_registry`；`confirm_project` 增加前置条件：`status == archived` 时抛 409 `PROJECT_ARCHIVED`「项目已归档，不能重新确认项目向导」（否则它会绕过解锁让项目离开 archived）；`archive_orchestrator` 不改。`full_resolve` 的锁定版本改由 `get_locked_version` 取，与当前版本不同时 `load_versioned_catalog`；`project_id` 有值而 `db` 为空时不查锁、结果标 `version_lock_checked=false` 并计指标，守卫现扫生产代码中这类调用。

**R2-F6/N6（现算，不留到守卫实施时）：「`project_id` 有值而 db 为空」的生产调用点逐个核对结论——`routers/wp_render_registry.py` 传 `db=None` 但不带 `project_id`，不触发版本锁查询，不受影响；`formula_management/engine.resolve_ref` 原样透传调用方的 db，可能为 None。故 D6 后「`project_id` 非空且 `db` 为空」的生产调用应为 0，由守卫钉住（出现即红、标 `version_lock_checked=false` 计指标）。**

`immutability.py` 删除进程内 dict 及 `record_` / `get_` / `remove_project_registry_version`、`clear_all_project_versions`（生产调用方 0，测试改为打桩 `get_locked_version`）。

**R2-F4（修订）：`list_archived_projects` 不是「生产调用方 0」——`services/acnr/catalog_snapshot_gc.py::query_referenced_versions`（现读 L230-243）import 它作引用集，`run_db_aware_gc`（L246-274）用其结果，而 `core/startup_registry.py::_task_acnr_catalog_snapshot_gc`（L600-605）每次启动执行 `run_db_aware_gc(keep_recent=10)`、`scripts/acnr/gc_snapshots.py` 也调同一入口（q05 之外的 grep 现证）。** 直接删掉它，启动 GC 的 import 失败被 `except` 吞成 fail-closed（从此永不删，需求 7.4 落空）；为消除 ImportError 而保留空壳又会恒返回空集、被当成 verified，最近 10 份之外的被锁快照在启动时被删、归档项目随即 409。修法：

- `query_referenced_versions` 改为 **异步查库** `referenced_registry_versions(db)`（§8.4）：`SELECT DISTINCT acnr_registry_version FROM projects WHERE acnr_registry_version IS NOT NULL`，**含软删项目**（锁定版本的真源是 §8.2 新加的列，不是进程内 dict）；
- `run_db_aware_gc(session=None, …)` 在 `session` 为空时自开一个短会话；查库失败时 `referenced_versions=None`（保持 fail-closed，不删）；
- 启动任务与 `gc_snapshots.py` 沿用这一个入口，不另加分叉；
- `list_archived_projects` 随进程内 dict 一并删除，但须先改完上述两个真实调用方（删除顺序：先改 GC 查库、再删函数），否则启动即崩。

错误映射（`app/main.py` 现有全局处理器处新增，均 409，避免前端对 5xx 自动重发）：`VersionNotFoundError` → `ACNR_REGISTRY_SNAPSHOT_MISSING`「项目锁定的地址目录版本 {v} 快照缺失，无法按归档时的目录解析；请联系管理员恢复快照」；锁定快照的 `CatalogIntegrityError` → `ACNR_REGISTRY_SNAPSHOT_INVALID`「…快照内容损坏：{原因}」；`RegistryLockError` → `ACNR_REGISTRY_LOCK_FAILED`「无法记录归档时的地址目录版本：{原因}；本次归档未生效」。`AddressingService.resolve_target` 与 `validate_refs_via_acnr` 对前两类改为上抛。指标增加 `version_lock_hit`、`version_lock_snapshot_missing`、`version_lock_unchecked`。

**R2-N4：`RegistryLockError` 不继承 `ValueError`**——交付件归档路由 `archive_deliverables` 把 `ValueError` 映射为 400，若 `RegistryLockError` 继承 `ValueError`，409 `ACNR_REGISTRY_LOCK_FAILED` 会被 400 抢先。令它继承 `CatalogLoadError`（或独立基类），全局处理器与归档路由据此映射 409（归档失败、状态不提交）。

**R2-F13：前端不得吞 409 回退 V1。** `stores/addressRegistry.ts` 的 `resolve()`（现读 L339-367）、`validate()`（L375-398）与 `useWorkpaperNavigation` 的 legacy 回退，对任何 ACNR 异常都回退 legacy `/api/address-registry/resolve`（按当前 V1 数据），锁定快照缺失时会静默按当前目录解析，违反需求 7.3。改法：回退分支先判错误——`status === 409` 且 `detail.error_code ∈ {ACNR_REGISTRY_SNAPSHOT_MISSING, ACNR_REGISTRY_SNAPSHOT_INVALID}` 时**直接返回** `{found:false, reason: detail.message}`（`validate` 返回 `{valid:false}` 加中文 issue），**不回退 V1**；其它异常保留现有回退。vitest 用后端真实 409 形状断言这两类不发 legacy 请求；`test_project_registry_lock_pg.py` 删快照那一步同时做 chrome-devtools 浏览器核对（归档项目打开底稿 / 选址时显示中文 409 文案、网络面板无 legacy 请求）。

### 8.4 快照清理（R2-F4 重写）

`catalog_snapshot_gc` 新增 `async referenced_registry_versions(db) -> set[str]`：查 `projects.acnr_registry_version IS NOT NULL`（含软删），取代 `query_referenced_versions`（删除后者，连同其对 `list_archived_projects` 的 import）。`run_db_aware_gc(session=None, *, keep_recent=10, dry_run=False)`：`session` 为 None 时用 `async with get_session()` 自开短会话；在其中 `await referenced_registry_versions(db)`；**查库异常时 `referenced_versions=None`、fail-closed 不删**（与现状 except 分支语义一致，但来源从进程内集合换成库）。启动任务 `_task_acnr_catalog_snapshot_gc` 与 `scripts/acnr/gc_snapshots.py` 都走这一个入口（不再有 `--db` / 内存两套路径）。生成器内离线清理（无 db）保持「引用不可验证即不删」。启动期这条路径现在能真正保护被锁的旧快照：被某项目锁定、但不在最近 keep_recent 之内的快照不会被 GC 删除。

### 8.5 验证

- 三层一致：迁移列、ORM 字段（含 `DateTime(timezone=True)`）、服务读写同名同型，守卫读迁移文本与 ORM 元数据逐项比对类型。
- 写入点守卫（AST + 原生 SQL）：给 `Project.status` 赋值的函数集合等于登记集合（现算 4 个），其中赋 archived 的函数必须调用 `lock_project_registry`、可从 archived 离开的函数必须调用 `unlock_project_registry`、其余两个登记前置条件（`event_handlers` 的 created / planning 判断、`confirm_project` 的 archived 拒绝）且 AST 断言该判断存在；`UPDATE projects ... status` 的原生 SQL 0 处，出现即红。另断言：调用 `lock_project_registry` 的函数集合 ⊆ 赋 archived 的函数集合。`confirm_project` 对已归档项目 409 有单测。
- `test_project_registry_lock_pg.py`（`pg_only`）：测试连接上开外层事务，会话以 `join_transaction_mode="create_savepoint"` 绑定；建【测试】项目经交付件归档真实路径归档；同一连接另建会话并清空进程内缓存（目录单例、上一版缓存、版本化目录 lru_cache）模拟重启；`ACNR_CATALOG_PATH` / `ACNR_SNAPSHOTS_DIR` 换到夹具 v2（v1、v2 对同一别名写法解析到不同 sheet）→ 该项目仍按 v1；TestClient 调取消归档 → 按 v2；删除 v1 快照 → `/api/acnr/resolve` 409 `ACNR_REGISTRY_SNAPSHOT_MISSING`；结束整体回滚。
- **R2-F4 启动期 GC 用例（`pg_only`）**：在回滚事务内把某【测试】项目的 `acnr_registry_version` 设为一个超出 `keep_recent=10` 的旧版本（对应快照存在于临时副本目录）→ 跑 `run_db_aware_gc`（经启动任务同一入口、session=None 自开短会话读本连接）→ 断言该被锁旧快照**仍在**；查库失败桩 → 断言 fail-closed 不删。快照清理的纯文件判定用例在临时目录副本上跑。
- R2-F4 受影响的既有测试（改为打桩 `get_locked_version` / `referenced_registry_versions`，不再打桩进程内 dict）：`test_full_resolve.py`（L550-643 项目版本段）、`test_immutability.py`（项目版本段，删对进程内 dict 的断言）、`test_versioned_resolve_determinism.py`、`test_resolve_instance_memo.py`。
- 变异：删 `deliverable_service` 的 `lock_project_registry` 调用 → 写入点守卫与端到端红；快照缺失时改为回退当前目录 → 409 用例红；把 `referenced_registry_versions` 改成恒返回空集 → 启动期 GC 用例（被锁旧快照被删）红。

## 9. D6　异步追溯拿到规范 addr_id（需求 8）

### 9.1 现状确认

`/cross-sheet-trace` 先跑同步 BFS（`CrossSheetResolver.resolve`），编排器再把节点转成 `cell:{sheet 名}!{A1}` 交 ACNR；`_index_ref_to_addr_id` 的 `cell:` 只认 sheet_code，真实 sheet 名恒解析不到。BFS 内 `_sync_resolve` 在运行中的事件循环里返回 None。另一 async 使用方 `wp_formula_eval_service._resolve_cross_sheet_refs` 只取链首节点的值。模块单例 `cross_sheet_resolver = CrossSheetResolver()`（L413）只被编排器作缺省值使用；既有守卫 `test_cross_sheet_trace_wiring.py` 与 `mutate_cross_sheet_trace_wiring.py` 防止路由直调单例。

### 9.2 方案

- `CrossSheetResolver.__init__` 增 `resolve_identity: bool = True`；为 False 时 BFS 不调 `_sync_resolve`，节点保持 `{sheet}!{cell}` 与 `resolve_missed=True`（与今天 async 路径输出相同）。缺省值不变，既有 PBT 与单测不改。生产构造全部显式传 False：模块单例改为 `CrossSheetResolver(resolve_identity=False)`（编排器缺省值随之安全），`wp_formula_eval_service` 构造处传 False 并注明「只取值、不取身份」。
- `RefChainNode` 只增 `sheet`、`cell`，BFS 填入。
- **R2-F8（未登记格也要拿到身份，不能一律 resolved=false）**：目录只有 474 个登记 cell，而 V2 图里未登记 A1 键 19264 个、登记的仅 5 个；若编排器靠 `full_resolve(addr_id)` 判身份，则「sheet 已登记、A1 未登记」的 addr_id 会落到 miss（resolver Step 3~8 精确 cell 命中失败后只剩语义包含与别名），真实追溯里绝大多数节点仍是 `resolved=false`，e2e 若只用登记格会假通过。改法：编排器 `trace(..., parent_wp_code)`（路由传入端点 `wp_code`）对每个节点 `exact_identity.cell_of(parent_wp_code, node.sheet, node.cell)`——**只要 sheet 识别出且 A1 合法即 `resolved=true`，返回规范 `addr_id`，另增 `in_catalog: bool`（标是否为登记 cell）**；`wp_id` / `jump_route` 改由 `resolve_instance(project, parent, sheet_code)` 按 sheet 记忆获取（不再调 `full_resolve(addr_id)`）；只有 **sheet 未识别 / 多义 / 命中禁止别名 / A1 非法** 时才 `resolved=false` 并写中文 `unresolved_reason`。`TracedRefNode` 增 `unresolved_reason`、`in_catalog`（只增）。
- 守卫 `test_cross_sheet_identity_paths.py`（AST）：`backend/app` 中每个 `CrossSheetResolver(` 构造都显式传 `resolve_identity`（含单例），生产代码不引用 `_sync_resolve`；由此证明同步桥接的降级分支在生产路径不可达。

### 9.3 验证

`test_cross_sheet_trace_async_e2e.py`：TestClient 调 `GET /api/custom-query/cross-sheet-trace`（不 mock `_sync_resolve` 与 resolver），夹具 `univer_snapshot` 用目录权威名「货币资金分析表E1-14」等。断言：登记格节点 addr_id 规范、`resolved=true`、`in_catalog=true`；**R2-F8 新增一个未登记格（如 `E1-14!Z99`，sheet 已识别、A1 合法但不在目录），期望 `resolved=true`、`in_catalog=false`、addr_id=`E1/E1-14/Z99`、`jump_route` 由 `resolve_instance` 得到**；目录外 sheet / A1 非法 / 多义的节点 `resolved=false` 且有中文原因。既有 `test_cross_sheet_*`、`test_cross_sheet_trace_wiring.py` 全绿，响应只增。变异：编排器退回 `cell:{sheet 名}!{A1}` → e2e 红；把「sheet 已识别、A1 合法」也判 `resolved=false` → 未登记格用例红；某生产构造去掉 `resolve_identity=False` → 守卫红。

**T20 实施记录（段七续做第 8 轮，待评审核实）**：

- 编排器 `trace(..., parent_wp_code=…)`：目录经 `wp_cell_target.effective_catalog(db, project_id)` 取（锁定项目用锁定目录），每个节点 `exact_identity.cell_of(父底稿, 节点 sheet, 节点 A1, index=…)`；`ok` 即 `resolved=true`、`addr_id` 规范、`in_catalog` 取自 `cell_of`；其余状态 `resolved=false`、`unresolved_reason` 用 `cell_of` / `sheet_of` 的中文原因（`reasons` 模块，不另写文案）。`parent_wp_code` 缺省 None 时原因为「缺少父底稿编码，无法确定单元格身份」（路由总会传端点的 `wp_code`）。编排器不再调用 `AddressingService`，构造参数 `addressing` 与 `trace` 的 `timeout_s` 删除（唯一调用方是路由，两项都不传）。
- `wp_id` / `jump_route`：按 sheet addr_id 记忆。先 `resolve_instance(项目, 父底稿, sheet_code)`，命中用它的结果；**补充（原文未写）**：结果为 `not_found` 且 sheet 不是父底稿本身时，`resolve_instance(项目, 父底稿, 父底稿)` 取父底稿，再 `resolve_instance(项目, 父底稿, sheet_code, explicit_wp_id=父底稿 id)` 生成带 `sheet=` 的路由。理由：真实项目的 `wp_index` 多数只有父级编码（T16 走查项目即如此），只按原文 sheet 级底稿不存在时 `jump_route` 恒空，与需求 8「可以直接跳转」不符；回落口径与 `wp_cell_target.bind_wp_code`（sheet 级底稿优先、仅不存在时回落父底稿）一致，两步都是 `resolve_instance` 公开入口（显式 wp_id 分支校验底稿属于本项目）。查库异常上抛（旧 `_attach_wp_id` 吞异常）。
- `CrossSheetResolver`：`resolve_identity` 缺省 True（既有 PBT 不改）；同步桥接调用移入 `_bridge_identity`，只在 `if self._resolve_identity` 分支调用。生产构造两处：模块单例 `CrossSheetResolver(resolve_identity=False)`、`wp_formula_eval_service._resolve_cross_sheet_refs`（注明只取值）。`RefChainNode` 增 `sheet` / `cell`，`TracedRefNode` 增 `in_catalog` / `unresolved_reason`，旧字段不变。
- 既有测试同步改：`test_cross_sheet_trace_orchestrator.py` 第 2 节三例原断言寻址层收到 `["cell:A!A1", "cell:B!B1"]`（即本缺陷的形态），改为新契约（真实目录、权威 sheet 名）+ 寻址层调用 0 次；`test_cross_sheet_trace_wiring.py` 加「把端点 wp_code 作为 parent_wp_code 传下去」；advanced-query-hardening 的 `scripts/check/mutate_cross_sheet_trace_wiring.py` 的 T01 / T06 锚点随之改（`--check-anchors` 6/6 OK）。
- 前端没有 `cross-sheet-trace` 的调用方（现算全仓前端源码 0 处引用，`CrossSheetTracePopover` 已不存在），响应只增字段，本任务无浏览器实测项。

## 10. D7　V2 依赖图与 stale 身份规范化（需求 9）

### 10.1 现状确认

V2 读四个静态文件（`l2_semantic` 181 个底稿键、`resolved_refs`、`l3_dependencies` 42163 条、`cross_wp_references` 425 条）；`/resolve` 先精确后包含，包含也返回 `matched: true`；响应没有 addr_id。stale 引擎 `_detect_and_normalize` 用正则 `[A-Z]\d+(?:-\d+)?[A-Z]?` 从 sheet 显示名抠编码再拼 id，`_build_addr_id_index` 以 `setdefault` 让碰撞组中先到者胜出（813 组全部错并）。唯一真实写入调用方是编辑器保存：`useEditorSave` → `useStaleImpact.notify` 发 `WP:{wp_code}:{活动 sheet 名}:审定数`（不传 cell 时末段默认「审定数」）。

### 10.2 方案

新模块 `services/acnr/v2_canonical.py`：`canonical_node(wp_code, sheet, last) -> CanonicalNode(addr_id, sheet_addr_id, identity_key, unresolved_code, unresolved_reason)`，只调用 `exact_identity`，`addr_id` 与 `unresolved_reason` 恰有其一：

| 分类（图中 WP 键 47073，p35） | 数量 | addr_id | identity_key | unresolved_code |
|---|---|---|---|---|
| 末段 A1，且为登记 cell | 5 | `{sheet_addr_id}/{A1}` | 同 addr_id | — |
| 末段 A1，sheet 已识别、格未登记 | 19264 | — | `{sheet_addr_id}/{A1}` | `cell_not_in_catalog`（附 `sheet_addr_id`） |
| 末段为语义标签（审定数、期初余额、AJE调整等） | 938 | — | `{sheet_addr_id}#{原样标签}` | `label_not_a1`（附 `sheet_addr_id`） |
| sheet 父级内多义 / 命中禁止别名 | 283 | — | — | `ambiguous_sheet_name` / `alias_forbidden` |
| sheet 不在目录 | 25515 | — | — | `sheet_not_in_catalog` |
| 底稿不在目录 | 324 | — | — | `wp_not_in_catalog` |
| 非 `WP:{底稿}:{sheet}:{末段}` 形态（含 `WP:{码}::docx:…` 自定义占位） | 744 | — | 自定义形态为 `custom:{wp}:{suffix}`，其余无 | `not_wellformed` |

`identity_key` 是 stale 引擎的内部身份（不对外宣称为 addr_id）：同一物理格或同一 sheet 的同一标签的多种写法并入同一键（现算 581 个键合并多写法，均同 sheet、同末段）。

- V2 四个读端点的每个节点与边两端增加 `addr_id` / `sheet_addr_id` / `unresolved_code` / `unresolved_reason`（只增）。`/resolve` 的包含匹配改为 `matched: false`、`candidate: true`、`match_kind: "contains"`（需求 9.2 唯一一处取值变化；前端 `resolveAddress` 无调用方）。
- stale 引擎：`_addr_id_index` 改为 `_identity_index: dict[str, list[str]]`，载图时对每个图键算 `identity_key`；入口 `_start_keys(source_uri) -> (keys, unresolved)`：输入是图键或 `WP:` 写法或 addr_id → 先算 `identity_key` 再查索引；非 WP 域图键（TB: / REPORT: 等）按字面。`identity_key` 为空（sheet 多义或禁止、sheet / 底稿不在目录、非四段且非自定义占位）→ 不写库，返回 `{"affected": [], "total": 0, "degraded": false, "unresolved_code", "unresolved_reason"}`；身份算出但图中无此节点 → 返回空影响（不是错误，`unresolved_reason` 为空）。图键与入口共用 `canonical_node`；`linkage_graph_builder._normalize_wp_uri_to_addr_id` 不再被写路径使用（只读使用方登记台账，§16 Q6）。
- 真实入参对照（p35，用 D~N 每张 sheet 模拟编辑器保存）：以目录名为活动 sheet 名的 947 条中，旧逻辑正确命中 113（字面 97 + 正则归一 16），新规则命中同样 113，其余 834 条两者都无起点（832 条身份已识别但图中无该标签节点、2 条 F2「底稿目录」多义）；以模板册真实 tab 名为活动 sheet 名的 1128 条中，旧逻辑正确 100、新规则 100。两组都没有旧逻辑「命中但错 sheet」的样本。
- 前端：`useStaleImpact` 暴露 `unresolvedReason`；`useEditorSave` 在其非空时 `ElMessage.info`「未能分析下游影响：{原因}」，同一会话对同一 (底稿, sheet) 只提示一次；后端计指标 `stale_start_unresolved{code}`。
- 双读对账：`scripts/acnr/reconcile_v2_canonical.py --write | --check` 生成 `data/acnr/v2_canonical_reconcile.json`（按「来源文件 × 分类」计数，每类附中文原因与前 20 个样本，不含时间戳），CI 跑 `--check`。

### 10.3 CCR 不可解析源（需求 9.5）

在统一判定（§6.2，含平台名别名）下重算 425 个源（p33、p36、p47）：可解析 373（其中 12 个是旧判定不可解析、经平台名别名与编码词元新近可解析，如 `WP('C2','销售循环控制测试',…)`；94 个解析到的 sheet 与旧私有判定不同，属旧判定的错配，如「ERP销售订单核对D4-13」由 D4-1 改为 D4-13）；不可解析 52 = 源底稿不在目录 2（`IS` 利润表、`B60D`）+ 名称里的编码不是目录编码 20（E1A 11、E26A 2、I1-1 3、A13-2、A13-3、B23-2、I1-10）+ 名称与目录名 / 别名 / 编码都不符 30。

**R2-F3（修订）：原「30 条中源底稿在目录里只有 1 张 sheet 的 11 条、目标唯一 ⇒ 改 `source_sheet`」是错的——目录 sheet 覆盖不全（审计报告 F20：平台独有 172 个编码），父级只有 1 张目录 sheet 推不出 CCR 指的就是它。** 现算复核（q04、q05）：`CW-60/417/418/419/420/421` 这 6 条的 `source_wp=B60`、`source_sheet=总体审计策略`（审计计划摘要、重要性结论、重要性计算、风险ID/B50行号、SCOT 程序索引、计划版本矩阵），而目录里 B60 唯一子 sheet 是 `B60-1「B61-1工时预算与控制板（按阶段）」`（对应 `wp_templates/B/B60-1 审计项目工时预算与控制表.xlsx`），与这些字段无关；总体审计策略内容在 `B60 总体审计策略及具体审计计划.docx`（docx，未入目录）。`CW-79`（`S14 会计估计审计`→S14-1「了解被审计单位及其环境」）同样可疑。把 `source_sheet` 改成工时预算看板会造出错误的 stale/依赖/chip 数据链路，比保留不可解析更糟。

处置改为：**每条「目标唯一」改写都须两项证据**——①模板册（或 docx）里存在目标 tab；②CCR 的 `source_cell_label` 或字段文字在该 tab 文本中出现（openpyxl / python-docx 文本扫描）。不满足的一律记入 `ccr_unresolved`。按 r09/q04/q05：B60 的 6 条与 S14 的 1 条**不能改写**，**预计修正 ≤ 4 条、豁免 ≥ 48 条**（实施时以当时现算为准、逐条列证据）。`ccr_unresolved` 条目含 owner（按循环）、到期 2027-04-30、以及「两项证据缺哪一项」的理由，不做整类豁免。`§7.4`、`§14.3` 与 `check_ccr_resolve` 的验收数字随之重算（§14.3 由「修 11、豁免 41」改为「修 ≤4、豁免 ≥48，清单外 0」）。`check_ccr_resolve.py --blocking` 读豁免清单：清单外不可解析源与「已可解析仍在清单里」都判失败，CI 作业转绿。

### 10.4 验证

- `test_v2_canonical_reconcile.py`（真实数据文件）：四个读端点经 TestClient 返回的节点都恰有 `addr_id` 或 `unresolved_reason`，非空 addr_id 经 `full_resolve` 回到同一物理格；对账产物 `--check` 通过；每类有中文原因。
- stale 写路径：碰撞组样本（如 `WP:A1:A1-14-7非财务信息分析:A2`）的 BFS 起点只含该格自身；只能包含匹配的输入不写库（spy `_mark_stale_by_uri` 0 次）且返回原因；`editor_save_inputs.json` 夹具（上述 947 + 1128 条模拟入参及期望起点）新规则命中不少于旧逻辑正确命中。
- 变异：`canonical_node` 改回正则猜编码 → 碰撞组用例红；删响应中的 `addr_id` → 9.1 用例红；包含匹配改回 `matched=true` → `/resolve` 用例红。

## 11. D8　写 stale 的端点加项目鉴权（需求 10）

### 11.1 复现证据（修复前，`out/p26_notify_idor_repro.txt`）

TestClient 以「不属于任何项目的审计员」身份（覆盖 `get_current_user`，不连库），`stale_engine.on_change` 打桩计数：V2 `notify-cell-change`（他人 project_id、未带 year）200 且 `on_change` 1 次、年度写死 2025；linkage-bus `POST /impact` 200 且 1 次；`GET /impact-by-addr` 200 且 1 次（GET 写库）；未登录调用 notify-cell-change 401。

### 11.2 处置

| 端点 | 真实调用方（现扫） | 处置 | 级别 |
|---|---|---|---|
| V2 `notify-cell-change` | 无（前端只有路径常量） | 下线：函数只 `raise HTTPException(410, {"error_code": "ENDPOINT_GONE", "message": "该接口已停用，请改用 /api/linkage-bus/impact"})`；去掉请求体，保留 `get_current_user`（未登录 401）；不触达数据 | — |
| linkage-bus `POST /impact` | 编辑器保存（`useStaleImpact.notify`）、公式管理配置变更（`FormulaManagerDialog`） | `project_id: UUID`；`year: int \| None = Field(None, ge=2000, le=2100)`，缺省时 `fetch_project_audit_year` 补齐，仍为 None → 422 `YEAR_REQUIRED`「项目审计年度未知，无法标记下游待更新」；加 `db` 依赖，函数体首句 `assert_project_permission(db, current_user, body.project_id, "edit")` | edit（审计员、经理、合伙人）与 admin；review / readonly 403 |
| linkage-bus `GET /impact-by-addr` | 无 | 改为只读预览：`stale_engine.preview_impact(source_uri, max_depth)`（只 BFS，不写库、不推 SSE、不记审计）；依赖 `require_project_access("readonly")`；删除无用的 `year` | readonly 及以上 |

- 年度：notify-cell-change 下线后不再写死 2025，`test_audit_year_calendar_fallback_ratchet.py` 删除 `routers/address_registry_v2.py` 条目（1 → 0）。前端 `useStaleImpact.notify` 不再用日历年兜底（没有年度就不带 `year`，由后端补齐），`useEditorSave` 传 `wpDetail.year` 不兜底；前端年度棘轮 `auditYearCalendarFallbackBaseline.json` 中 `composables/useStaleImpact.ts`、`composables/useEditorSave.ts` 两条 1 → 0 删除。`useStaleImpact.notify` 在没有 project_id 时不发请求；403 按现有非阻塞告警处理。`services/apiPaths/system.ts` 删除 `notifyCellChange`。
- V2 其余端点（`/stats`、`/resolve`、`/anchors`、`/stale-impact`、`/dependencies`）不带 project_id、只读静态数据，维持登录即可。
- 鉴权基线：`test_project_endpoint_authz_body_carried.py` 中三个端点原计「仅登录」，修后实施时现算下调 `_BODY_IDENTITY_ONLY_BASELINE`（现值 87，预计 84；并发 spec 先调则以现算为准），两个 linkage-bus 端点加入 `_FIXED_ENDPOINTS`。

### 11.3 验证

`test_stale_write_endpoint_authz.py`（表驱动，复用 `test_address_registry_authz.py` 的权限世界夹具，覆盖内层 `get_current_user` / `get_db`，不覆盖鉴权依赖本身）：`/impact` 未登录 401、非成员 403 且 `on_change` 0 次、readonly 与 review 403、审计员 / 经理 / 合伙人 / admin 200、缺年度且项目无年度 422；`/impact-by-addr` 非成员 403、readonly 200 且 `_mark_stale_by_uri` 0 次；notify-cell-change 登录 410、未登录 401，AST 断言函数体只有 `raise`。变异：逐个摘掉新加的鉴权 → 对应 403 用例红；只在 docstring 写鉴权不算数（AST）。

## 12. D9　前端失效订阅与多项目缓存隔离（需求 11）

### 12.1 现状确认

`useAcnr(projectId?: string)` 只在构造时订阅一次；无参 28 处 / 27 个文件，带参 1 处（`FormulaManagerDialog.vue` L1489）。`subscribeInvalidation` 已按项目引用计数复用总线连接；`_onAcnrInvalidate` 在目录版本未变时只清该项目解析缓存、版本变化才清目录级缓存、重连后清该项目缓存——需求 11.3 的隔离逻辑已存在，缺订阅随项目切换与测试。

### 12.2 方案

- 签名改为 `useAcnr(projectId?: MaybeRefOrGetter<string | null | undefined>)`；内部 `watch(() => toValue(projectId) || '', pid => { cleanup(); cleanup = subscribeInvalidation(pid) }, { immediate: true })`，**只在 `getCurrentScope()` 存在时订阅**并 `onScopeDispose(cleanup)`（组件、Pinia setup store 都在 effect scope 内）；在普通函数里调用时不订阅（无从释放），`resolve*` 的项目参数缺省取 `toValue(projectId)`。传静态字符串的旧写法仍可用。
- 新 composable `composables/useCurrentProjectId.ts`：`computed(() => (route.params.projectId as string) || projectStore.projectId || '')`。
- `stores/addressRegistry.ts`：直接 `useAcnr(() => _projectId.value)`（store 已有 `_projectId`，不再加新状态）。
- 28 处逐处改法（p40 现算位置）：

| 文件 | 处数 | 改法 |
|---|---|---|
| `components/consolidation/ConsolNoteTab.vue`、`disclosure/DisclosureSyncCoveragePanel.vue`、`formula/FormulaBar.vue`、`formula/FormulaManagerDialog.vue`（`loadAcnrTree`）、`workpaper/g2-interest-receivable/G2TabDisclosureSOE.vue`、`workpaper/h4/core/H4TabAdjudication.vue`、`workpaper/h6/core/H6TabAdjudication.vue` | 各 1 | `() => props.projectId` |
| `components/formula/FormulaEditDialog.vue` | 2 | `() => props.projectId \|\| route.params.projectId` |
| `components/workpaper/GtIndexChip.vue` | 1 | 复用组件内既有 `projectId` 计算属性（contextProjectId 优先、其次路由） |
| `composables/useAcnrDrill.ts` | 1 | 传入参 `getProjectId` |
| `views/composables/useNoteTree.ts` | 1 | `() => toValue(options.projectId)` |
| `views/AcnrOverlayManager.vue`、`views/DisclosureEditor.vue` | 各 1 | 页面既有的路由项目 `projectId` 计算属性 |
| `components/workpaper/composables/useF2CutoffCrossSheet.ts`、`useH3RentalCrossSheet.ts`、`useH3TitleCrossSheet.ts` | 各 1 | 在普通 async 函数内调用：传函数入参 `projectId`（只作 resolve 缺省项目，不订阅） |
| `components/formula/FormulaRefPicker.vue`、`CellSelector.vue`、`GtFormulaEditDialog.vue`、`GtFormulaSourceTooltip.vue`、`custom-query/CustomQueryFieldPicker.vue`、`consolidation/composables/useConsolReportAddress.ts`、`composables/useWorkpaperNavigation.ts`、`composables/useFormulaScopeCatalog.ts` | 各 1 | `useCurrentProjectId()`（项目页内使用但组件无项目入参） |
| `stores/addressRegistry.ts` | 1 | `() => _projectId.value` |
| `components/template-library/FormulaTab.vue`、`workpaper/composables/useAcnrCatalogIndex.ts` | 各 1 | 保留无参，登记到 `services/acnr/acnrCatalogOnlyCallers.ts`：前者是全局模板库无项目，后者只列目录 sheet、与项目无关 |

合计 7 + 2 + 1 + 1 + 1 + 2 + 3 + 8 + 1 + 2 = 28。

### 12.3 验证

- 守卫 `acnrSubscriptionLedger.spec.ts`：TypeScript 编译器 API 解析非测试 `.ts` 与 `.vue` 的 `<script>`，零参数 `useAcnr()` 集合必须等于登记集合；登记里有已不存在的文件也红；注释不计。
- vitest（打桩 `subscribeProjectEvent` 计数）：A→B 切换后 A 取消、B 建立；同项目多处只有一个总线订阅；卸载后为 0；store `refresh` 切项目同步切换；普通函数内调用不订阅；A 收到失效只清 A 的解析缓存、B 仍命中；目录版本变化才清目录缓存。
- 浏览器（两个【测试】项目、两个标签页）：A 保存底稿或改 overlay 后 A 的选址 / 解析在 SSE 事件后刷新、B 不变；断开重连后 A 缓存被清；降级为仅 TTL 时 300 秒内收敛。多 worker + Redis pub/sub 本机不具备，tasks 中标 `[ ]*`。
- 变异：去掉某处项目参数 → 守卫红；按项目清缓存改为全清 → 隔离用例红。

## 13. D10　统一显示与可解释的错误（需求 12）

### 13.1 现状确认（p29、p31）

| 产物 | 现状 |
|---|---|
| `catalog.list_sheets`（catalog.py L222-255） | 运行时给每个 sheet 注入 `account_name`（父级科目简称）与 `mapped_sheet_name`（优先 `wp_account_mapping.wp_name`，兜底 `sheet_display_names.json`）；现算 1215 张中 853 张取映射名、288 张取 json 名、74 张无 |
| `data/acnr/sheet_display_names.json` | 947 条；由 `scripts/gen_sheet_display_names.py` 读库表 + prefill 生成；按缓存复算只有 911 条一致，31 条值不同（如 G1「长期股权投资审定表」）、5 条（K14~K18）复算不出 ⇒ 已是手工修正过的数据，重跑生成脚本会回退 36 条 |
| `check_sheet_display_names.py` | CI 报告模式（`continue-on-error`），自带一份与前端 `cleanSheetLabelName` 同义的正则 |
| 前端 `sheetDisplayName.ts::composeSheetLabelsForGroup` | 文件头自称单一真源：名称 = `mapped_sheet_name` → 去尾编码的模板名 → 等于编码则空；加「科目简称·」前缀；同组重名加（1）（2）；标签 = `{sheet_code} {名称}`。调用方 3 处：`useAcnr.buildAddressTree`、`FormulaManagerDialog.buildWpDomainTree`、`FormulaEditDialog` |
| 目录 sheet 的 `display_label` | 1215 张全是路径形态「底稿 > 父 > sheet_name」；只作候选显示文本（resolver 4 处、catalog 2 处、`FormulaTab.vue` 1 处原样展示）；测试里出现的路径形态都是测试自造夹具 |
| 各自拼接的另外 9 处 | `FormulaRefPicker.vue` L115 / L240 / L304、`CellSelector.vue` L122（`[父] sheet_name`）、`FormulaBar.vue` L419、`FormulaManagerDialog.vue` L1647、`FormulaEditDialog.vue` L889、`leftPanelAnchors.ts` L123、`stores/addressRegistry.ts` L125 / L142、`useAcnr.loadCellNodes` L780 |

### 13.2 裁定：规则下沉为后端单一函数，由生成器写入目录

- 规则以 `composeSheetLabelsForGroup` 的现行口径为基线逐行移植为 `services/acnr/display.py::compose_sheet_labels(group, names)`（自然排序、名称来源顺序、纯编码置空、科目简称前缀、同组序号消歧完全相同），只多一条：停用条目加「（已停用）」。三棵树（选址器、公式管理、公式编辑）的用户可见名不变，所以不需要另行征求用户确认；其余 9 处由「原始 sheet_name」统一到这条规则。示例：E1-14 →「E1-14 货币资金分析程序（一）」、H1 →「H1 固定资产」、F2-33 →「F2-33 存货检查（五）」（同名组的两张由映射名区分）。
- cell：`display.cell_labels(sheet_label, cell, semantic_verified)` 得 `cell_label` =「{A1} {语义标签}」（无语义时「{A1}」，被 `seed_semantic_unverified` 覆盖时「{A1}（语义待核对）」）与 `display_label` =「{sheet 的 display_label} › {cell_label}」。树的叶子用 `cell_label`（父节点已显示 sheet 名），选中标签、结果区、chip 提示用 `display_label`。
- 不新增 `display_name`：沿用 `display_label` 字段名，取值规则改为上述显示名（只用于显示，消费方均原样展示）；cell 新增同名字段与 `cell_label`。生成器写出，`list_sheets`、resolve 命中与候选、acnr_targets、V2 节点都输出同一字段；L3 运行时条目与 V1 委托结果由 resolver 用同一函数现算。
- 输入：`wp_account_mapping.json` 与 `sheet_display_names.json` 成为生成器输入（进 `inputs_fingerprint`）。`sheet_display_names.json` 改为手工维护；`gen_sheet_display_names.py` 删除（删前 grep 调用方；重跑会回退 36 条）。`check_sheet_display_names.py` 改为薄壳：读已提交目录，用 `display.py` 列出名称为空（纯编码）的 sheet，CI 作业维持报告模式。`list_sheets` 继续注入 `account_name` / `mapped_sheet_name`（只增不改），但前端不再读后者。
- 树的父节点标题「{父级码} {科目简称}」不是某个 addr_id 的显示名，保留在前端单一函数 `sheetDisplayName.groupHeaderLabel`。

### 13.3 前端改动与守卫

- `sheetDisplayName.ts` 保留 `wpCodeNaturalCompare`、新增 `groupHeaderLabel` 与 `sortSheetsForGroup`（按编码自然序返回 `{entry, label: entry.display_label}`），删除 `composeSheetLabelsForGroup` 与 `cleanSheetLabelName`；三棵树改调 `sortSheetsForGroup`。
- 9 处拼接改为读 `display_label` / `cell_label`；`FormulaRefPicker` 的单元格表列为「单元格」（`cell_label`）与「引用」，搜索按 `display_label` 与 `formula_ref` 过滤；`CustomQueryFieldPicker` 的已选标签存 `display_label`；`GtIndexChip` 提示首行显示解析结果的 `display_label`；新组件 `AcnrTargetResults` 显示 `display_label`。涉及 `useAcnr.ts`、`sheetDisplayName.ts`、`FormulaManagerDialog.vue`（4216 行，阈值 4727）、`FormulaEditDialog.vue`（1580 行，阈值 1618，净增 ≤ 0）、`FormulaRefPicker.vue`、`CellSelector.vue`、`FormulaBar.vue`、`leftPanelAnchors.ts`、`stores/addressRegistry.ts`、`CustomQueryFieldPicker.vue`、`GtIndexChip.vue`、`AcnrTargetResults.vue`。
- 守卫 `acnrDisplaySingleSource.spec.ts`（TS 编译器 API 解析 `<script>`，`@vue/compiler-sfc` 取模板表达式再交 TS 解析）：上述登记文件中不出现 `.sheet_name` / `.semantic_label` / `.mapped_sheet_name` 的属性读取（类型声明除外），`.account_name` 只允许出现在 `groupHeaderLabel`；全仓不再有 `composeSheetLabelsForGroup` / `cleanSheetLabelName`。
- 跨语言契约：`backend/tests/acnr/fixtures/display_contract.json`（从真实目录抽样：同组序号、科目前缀、纯编码、停用、语义待核对）；后端断言生成结果与 acnr_targets、`/api/acnr/resolve` 的 `display_label` 与夹具逐字相等；vitest 用同一夹具挂载树、选址器、结果区与 chip，断言渲染文本逐字包含夹具值。

### 13.4 歧义与原因

- `ResolveResult` 增 `reason`（中文）、`required_context`（`parent_wp_code` / `sheet_code` / `project_id`）、`next_step`（外部命名空间用）、`deprecated`、`replaced_by`；候选项增 `display_label`（≤5）。中文原因模板集中在 `services/acnr/reasons.py`（错误码 → 文案），`/api/acnr/*`、acnr_targets、V2 规范化、CCR 检查器都从这里取。
- 前端新组件 `components/acnr/AcnrCandidatesHint.vue`：显示原因、所需上下文与候选，选中候选后按其 addr_id 重新解析；公式选址器（粘贴 / 校验引用时）、高级查询地址树（搜索时）、`GtIndexChip`（解析返回歧义或停用时）三处使用。

### 13.5 外部命名空间

`grammar_v1.json` 的 6 个 `external_module: true` 命名空间（Adj、Att、EQCR、Calc、Sample、Confirm）各增 `label_zh` 与 `next_step_zh`（如 Adj：「调整分录」/「请在调整分录模块中查看该分录」）。resolver 外部分支返回 `found=false`、`error="external_module_not_resolved"`、`reason`「「{label_zh}」类引用暂不支持定位到物理地址」、`next_step`；`GtIndexChip` 显示原因与下一步。后端用例遍历全部外部命名空间，缺文案即红；vitest 覆盖 chip；界面不出现英文错误码（沿用 UI 中文化 ESLint 卡点）。

变异：某组件改回读 `sheet_name` 拼显示名 → 守卫红；删一个命名空间的 `label_zh` → 遍历用例红；`display.py` 去掉序号消歧 → 契约夹具红。

## 14. D11　消费方台账、绕过棘轮与门禁转绿（需求 13）

### 14.1 绕过点定义与现算基线

识别一律用语法树（Python `ast`，TS 编译器 API，`.vue` 含模板表达式），注释与文档字符串不计：

| 编号 | 定义 | 排除 | 现算基线 |
|---|---|---|---|
| BP-1 | 后端 `from app.services.address_registry` / `app.routers.address_registry` 导入寻址符号 | V1 自身；`services/acnr/`（非底稿域委托层，5 个文件）；`router_registry/system.py`；纯取值工具 `extract_custom_cells` / `CellRecord` | 8 处 / 7 个文件：`routers/wp_structure.py`、`services/ai_chat/` 4 个文件（`mention_service.py` 2 处）、`services/event_handlers/_impl.py`、`services/wp_structure_bridge.py` |
| BP-2（R2-F12 重定义） | **加载 `address_registry_l2_semantic.json` / `address_registry_resolved_refs.json` / `address_registry_l3_dependencies.json` 的模块，或读取 CCR 后以 `source_sheet` / `sheet` 字符串推导 sheet 身份（正则抽编码、按名匹配目录）的模块**——不是「只要出现 V2 四个静态文件名字面量」 | V2 路由自身、`acnr/v2_canonical.py`、对账脚本；**只读 `cross_wp_references.json` 做跨底稿业务规则（不推 sheet 身份）的 CCR 消费方**（如 `linkage_panorama`、`template_library_mgmt`、`wp_relation_router`、`wp_step_mapping`、`cross_cycle_breakage_service`、`cross_ref_service`、`formula_check_catalog`、`formula_reverse_index`、`wp_trace_service` 等）只进台账、不算绕过 | 旧「47 处 / 12 个文件」按上述定义现算**不可复现**（r07 C 现算 `backend/app` 10 文件 / 35 处、`scripts` 2 / 2，且 10 个里 9 个只读 CCR 做业务规则）。实施阶段按**窄定义**（字符串常量 + 路径拼接，AST；排除 V2 路由 / `v2_canonical` / 对账脚本）现算后冻结，不写死 47/12 |
| BP-3 | 前端在 `services/apiPaths/` 之外引用 `addressRegistry` 路径常量（含 `as` 别名与 `.v2.*`）或直写 `/api/address-registry` 字面量 | `apiPaths` 定义处 | 3 个文件：`stores/addressRegistry.ts`（`paths.*`）、`composables/useStaleImpact.ts`（`addressRegistry.v2.*`）、`components/formula/FormulaEditDialog.vue`（L853 字面量）。`useConfirmationNavigation.ts` 只在注释中出现，不计 |
| BP-4 | 前端调用 `useWorkpaperRegistry(`，或使用 `/api/workpapers/index-resolve`、`/api/wp-index-resolve`（两个 legacy 门面，后端已转发 ACNR） | `useWorkpaperRegistry` 定义文件 | `useWorkpaperRegistry` 3 处（`WorkpaperHtmlTable.vue`、`WorkpaperTraceView.vue`、`useWorkpaperNavigation.ts`）；`/api/workpapers/index-resolve` 1 个文件（`useWorkpaperNavigation.ts`）；`/api/wp-index-resolve` 2 个文件（`useS34CrossRef.ts`、`useS35CrossRef.ts`，属他人在研文件，只登记不改） |

基线存 `backend/data/acnr/bypass_baseline.json`（「文件 + 符号」，不含行号），后端 `test_acnr_bypass_ratchet.py` 与前端 `acnrBypassRatchet.spec.ts` 读同一文件：现算超出基线即红；基线条目在现算中找不到也红。扫描实现 `backend/scripts/check/acnr_bypass_scan.py`，`check_acnr_consumer_coverage.py --strict` 改为调用它的薄壳；`coverage_ledger.json`（含两条纯注释引用）在读取方改完后删除。

### 14.2 台账

`backend/data/acnr/consumer_ledger.json` 逐项登记消费方（草案见 §17）：`{id, consumer, files, symbols, status: migrated | legacy_fallback | not_wired, target, notes}`。守卫校验文件与符号真实存在（Python 用 AST 定义名，TS 用语法树导出 / 函数名），`migrated` 条目不得出现在 BP 基线中。

### 14.3 门禁转绿（需求 13.5）

| CI 作业 | HEAD 状态 | 交付后 |
|---|---|---|
| `check-acnr-catalog-drift` | 红（57 张差异） | `generate_catalog.py --check`；§5.4 迁移后 0 |
| `acnr-ie-catalog-sync` | 红（19 处：D 1、G 14 api_prefix；H 4 目录有、manifest 无） | D / G 改 manifest；H 4 经 overrides 登记 |
| `acnr-ccr-resolve-blocking` | 红（57 个） | 统一判定下 52 个：修 ≤4（每条两项证据），逐条豁免 ≥48（含 B60×6、S14×1），清单外 0（R2-F3） |
| `acnr-consumer-coverage --strict` | 红（4 个 ai_chat 文件未登记） | AST 棘轮取代，基线内即绿 |

不用 `continue-on-error`，不加整类豁免。交付前在 `tmp_acnr_foundation/verify_wt` 干净检出逐个运行四个作业的命令，并加跑 X3 作业与 `fix_acnr_catalog_ie_gap.py --check`。

### 14.4 验证

变异：临时副本注入一处新的 `from app.services.address_registry import address_registry` → 红；只在注释里提到 legacy 函数 → 不红；删掉一个基线所指调用 → 报失效条目并红；台账写一个不存在的符号 → 红。

## 15. D12　文档与勘误（需求 14）

### 15.1 架构提案的「现状（2026-10-26）」节

在 `docs/proposals/address-coordinate-name-registry-architecture.md`（1829 行）标题信息表之后插入新节，原有段落一字不改：已落地组件（生成器与 L1 目录、L2 overlay、L3 运行时、`full_resolve` 与非底稿域 V1 委托、前端 SDK）；发布后的目录规模；版本格式为 14 位 UTC 时间戳；L1 只覆盖底稿域；V1、V2、legacy 导航的并行关系；本 spec 完成后的门禁清单；定位「canonical resolver + legacy 委托」。逐条指出过时陈述：第 18 行「实施 spec 尚未创建」、第 543 / 562 行 `registry_version: "2026.07.10"` 示例、首期仅 D 循环等（行号为现读值，守卫按标题与关键词定位）。守卫 `test_acnr_architecture_status_doc.py`：该节存在，节内版本格式与 `catalog_contract.REGISTRY_VERSION_PATTERN` 一致；变异（删节、改回 `YYYY.N.N`）即红。

段四审计 F4-01 / F4-02 修订（2026-10-27，取代上段中「发布后的目录规模」写成现状的做法）：现状节**只写当前 HEAD 可验证的事实**，结构固定为三张表——「已落地：目录与代码现算事实」（每行带复算键）、「已落地：组件」（模块 / 符号 / 测试）、「计划中（未落地）」（每行带任务号）——加「版本号格式」「V1 / V2 / legacy 导航的并行关系（现状）」「过时陈述勘误」三个正文子节；发布后规模（1225 / 449 / 0）等预演值只能出现在「计划中」并注明是预演值；节末用固定结束行与提案原文分界。

守卫的最终规则（段四复审第 2 轮 F4-02 残留二之后）分两层，每条判据配一条磁盘变异（见 tasks T32 与 `tmp_acnr_foundation/out/段四_修复记录.md`）：

- **登记制**（`backend/tests/acnr/test_acnr_status_doc_statements.py`，切分与判据库 `backend/tests/acnr/_status_doc_checks.py`）：结构封闭——节内每个非空行只能是节标题、登记的六个子节标题（顺序固定）、三张表（表头逐字固定）的行或正文行，其他子节出现表格即红。陈述单元 = 正文行（去掉引用与列表前缀）按「。」「；」「;」切出的每一句（「」、（）、()、反引号内不切）+ 事实表「事实」、组件表「组件」、计划表「事项」三列的每个单元格；每个单元必须逐字登记在 `_STATEMENTS[所在子节]` 并绑定至少一个复算判据（AST / 产物现算 / tasks.md 状态），组件行的类型 / 模块 / 符号 / 测试、计划行的任务、事实行的复算键随单元逐字登记；勘误子节的引文核对它逐字出现在节外原文的所述位置，节外原文以 `96fba2c49^` 提案原文的 LF 内容 sha256 钉住（「本文其余段落未改一字」由此复算）。未登记、判据不成立、登记失效（节内已无此句）、同一子节重复都红。前端组件行的描述另由 vitest 守卫 `audit-platform/frontend/src/services/acnr/tests/acnrArchitectureStatusDoc.spec.ts` 用 TS 编译器 API 逐字登记判据。表格行须以竖线收尾（最后一个竖线之后的文字不进任何单元格，不收尾即红）。复审第 2 轮给出的规则允许不登记的是「计划中（未落地）」子节、事实表「值」列、节末结束行、「…」引文与版本格式字面量（`^\d{14}$`、`%Y%m%d%H%M%S`）；守卫比它更严——计划表「事项」单元格也逐字登记（自动绑定「任务仍未勾选」），引文与版本格式字面量不单独成单元、随所在句整句登记，真正不成为单元的只有事实表「值」列（由下一层复算）与节末结束行。改现状节时先改文档，再登记新句子与能证伪它的判据，删掉失效条目。
- **逐项复算**（`backend/tests/acnr/test_acnr_architecture_status_doc.py`）：事实表每个值从 `global_catalog.json`、`catalog_report.json`、快照与生成器源码 AST 现算并逐字比对，守卫认识的复算键必须全部在表里；组件表后端行用 AST 确认模块定义了所列符号、测试文件有 `test_` 函数，前端行由上述 vitest 守卫核对导出符号；计划表的任务号必须在 tasks.md 里仍为 `[ ]`；节内**每一行**（含表格单元格与组件描述）提到登记的计划中符号（`lock_project_registry`、`v2_canonical`、`--check` 等）而代码里还没有时，同一行必须带仍未勾选的任务号；「已落地」两子节事实表值列以外的数字须同句绑定复算键且等于现算值；完成态措辞须被登记的复算判据证实；resolver 模块与全部函数 / 类文档须定位为「canonical resolver + legacy 委托」，不得称「唯一解析入口 / 方法」。

两层的分工：登记制保证「没有登记过判据的说法写不进现状节」（复审 R2-D5 / R2-D6 / R2-D7 那类换措辞的假现状无从绕过），逐项复算保证已登记的数字与产物同步、计划中任务与 tasks.md 同步。

### 15.2 勘误（不改历史报告原文；本 spec 提交在 `.agents/tasks/` 下只触及本 spec 收尾报告，段四裁定见 §15.4）

| # | 出处与原表述 | 勘误 |
|---|---|---|
| 1 | 审计报告 §11 转述公式管理评估：「高级查询复用 ACNR 地址树 / 跨模块 cell 级字段」 | 只复用了地址树组件。两个执行入口都没有取值：构建器 `QueryDSL` 丢弃字段；业务视图虽解析目标，`business_fetcher` 不用解析结果（AST）。由本 spec §2 实现 |
| 2 | 「ACNR 已是四大消费库唯一解析入口」 | 应称「canonical resolver + legacy 委托」，绕过点见 §14.1；`acnr/resolver.py` 模块注释「四大消费库的唯一解析入口」同样过时（随本 spec 改注释） |
| 3 | 「157 个定向测试全绿」（审计报告 §12：后端 87 + 前端 70） | 这些测试不覆盖真实产物（schema 512 错、孤儿 25、formula_ref 往返 30/474）与端到端链路；同一 HEAD 下 ACNR 相关 CI 作业 14 项中 4 项红 |
| 4 | 「历史版本锁定已经实现」 | 只能称「resolver 支持按快照解析」：锁定记录只在进程内、生产调用方 0，无项目处于锁定 |
| 5 | 公式管理评估报告第 11 节（实际运行命令与结果，基线 HEAD `40561d2c6`） | 其 11.1 所列定向套件均不含 ACNR 目录产物与 acnr_targets 链路的校验，不能据此推出地址底座无缺陷；11.4 的未验证项没有列出地址目录。补记：`40561d2c6..b5fc200e0` 之间 ACNR 目录、生成器、服务、V2 与高级查询代码 0 改动，本轮 §1 现算在该基线同样成立 |
| 6 | 审计报告 §11 把第 1、2、4 条归于公式管理评估 | 该评估目录全部文件现扫关键词（地址树、唯一解析、唯一入口、版本锁定、跨模块 cell、acnr_targets）未找到原文；其 §3 结论是「V1/ACNR/V2/V199 dependency 没有统一成为 Resolver」，与本审计一致。第 1、2、4 条应视为对 resolver 注释与架构提案的复核 |
| 7 | 本轮新发现 | 同父同名 78 组被任选其一（26 处真实写法因此解析到借名的父级）；CCR 检查器自带第二套判定，94 个源配错 sheet；stale 图正则身份 813 组错并；K14~K18 未经停用即移除而 4 个项目在用；同一版本两份内容；选址器插入的写法被保存校验拒绝；classification 缓存与本地库表是两个模板版本、库表缺 771 个拆分编码；acnr_targets 依赖的 `parsed_data` 在 1738 份底稿中只有 1 份含单元格数据；业务视图同会话并发解析；下钻 `noopener` 丢登录；显示名有 4 套写法 |

### 15.3 D12 文档批次交付记录（2026-10-26）

> **段四审计勘误（2026-10-27，F4-01 / F4-10）**：下面第一条所述现状节内容在 HEAD 上大面积不成立——「发布后目录规模（sheet 1225 / 有效 cell 449 / 孤儿 0）」「schema 单一契约与发布门禁」（门禁未接入生成器、无 `--check`）、「版本锁持久化」「acnr_targets 跨模块单元格取值」都尚未实施，「实施 spec 已完成 P0/P1/P2」不实；「`resolver.py` 模块注释更正随 T32」在 T32 勾选时并未兑现。现状节已按 §15.1 段四修订口径重写（HEAD 现算：sheet 1215、cell 474、孤儿 25、报告无 release 段），resolver 模块注释已改为「canonical resolver + legacy 委托」。下文保留为当时的交付记录原文，不作为现状依据。

本批次（P0/P1/P2 评审通过后的文档收口）落地两项，无新开文件：

- **架构提案现状节**：按 §15.1 在 `docs/proposals/address-coordinate-name-registry-architecture.md` 标题信息表之后插入「现状（2026-10-26）」节，原有段落一字不改。该节覆盖已落地组件（生成器 + L1 目录 / L2 overlay / L3 运行时 / `full_resolve` 与非底稿域 V1 委托 / 前端 SDK）、发布后目录规模（sheet 1225 / 有效 cell 449 / 孤儿 0）、`registry_version` 为 14 位 UTC 时间戳、schema 单一契约与发布门禁、版本锁持久化、V1/V2/legacy 并行关系（V2 为 additive 规范化）、acnr_targets 跨模块单元格取值、本 spec 完成后门禁清单，并在节末逐条指出原文过时陈述（第 18 行「实施 spec 尚未创建」、第 543/562 行 `registry_version: "2026.07.10"`、「首期仅 D 循环」）。守卫 `test_acnr_architecture_status_doc.py` 按标题与关键词定位、校验版本格式与 `catalog_contract.REGISTRY_VERSION_PATTERN` 一致。
- **公式管理评估勘误**：按本节现有安排记于 §15.2（第 5、6 条），不另开文件。核心结论：公式管理评估报告第 11 节所列定向套件不含 ACNR 目录产物与 acnr_targets 链路校验，不能据此推出地址底座无缺陷；其 §3「V1/ACNR/V2/V199 dependency 未统一为 Resolver」与本审计一致；审计报告 §11 归于公式管理评估的第 1、2、4 条，经全目录关键词现扫未在该评估原文中找到，应视为对 resolver 注释与架构提案的复核，不改历史报告原文。

不改历史报告原文；本批次提交只含上述两份文档文件（架构提案 + 本 spec design.md），不含 `.agents/tasks/` 任何文件。`resolver.py` 模块注释更正与 INDEX 登记随 T32/T33 代码批次处理，不在本文档批次提交内。

### 15.4 段四补记：收尾报告入库裁定、预存挂起用例与测试数口径

- **需求 14.2 / T33 判据裁定（段四审计 F4-19）**：14.2「不修改历史报告原文：本 spec 的提交不含 `.agents/tasks/` 下的任何文件」保护的是**历史报告原文**——ACNR 审计报告 `.agents/tasks/acnr-platform-foundation-assessment-2026-10-26.md` 与上一轮公式管理评估报告——不得改写。本 spec 自己的收尾报告 `.agents/tasks/acnr-foundation-defect-closure-2026-10-26.md` 是本 spec 的交付物，段四任务书第三节第 6 步明确要求更新它（覆盖 33 个任务的最终状态），因此允许随本 spec 提交与修改（`00d56b039` 新增、`95e03e72a` 就地更正都属此类）。§15.2 标题与 T33 判据据此收窄为：本 spec 的提交在 `.agents/tasks/` 下只触及这一份收尾报告（`git log --name-only` 现算核查），不触及审计报告与公式管理评估报告。需求 14.2 原文加注同一裁定。
- **预存挂起用例（段四审计 F4-18）**：`backend/tests/acnr/test_overlay_persistence_roundtrip.py` 在 HEAD 与 `b5fc200e0` 上都挂起（段四审计实测：HEAD 613 秒无输出被终止，基线 300 秒超时；日志 `tmp_acnr_foundation/out/段四_a04_HEAD_run.log`、`段四_a04_BASE_run.log`），属预存问题，非本 spec 引入。该用例由 `c267ce8c4` 引入，所属 spec（`acnr-runtime-convergence`、`acnr-invalidation-overlay-hardening`）已归档到 `.kiro/specs/_archive/04-infra-architecture/`，归档 spec 不回填修改，故登记在这里并写进最终收尾报告，修复另立工单。初步线索（未定位挂起点）：该文件的 hypothesis 用例每例 `asyncio.new_event_loop()` 并新建 SQLite 内存异步引擎（`StaticPool`）。本 spec 的回归命令一律带 `--ignore=tests/acnr/test_overlay_persistence_roundtrip.py`，tasks.md 文件头注明排除原因。
- **测试数口径（段四审计 F4-17 复审复现）**：交付记录与提交信息里的通过数，一律来自 `tmp_acnr_foundation/verify_wt` 检出当时 HEAD、只覆盖本次提交文件（覆盖前后两侧 sha256 逐个记录、与提交内容逐字节相同）的运行结果；主树运行的数字（可能含下一组未提交改动）不写进交付记录。段四修复第一轮 `7e3603024` 记的「tests/acnr 634 passed」是主树含下一组改动的数，对该提交不可复现（复审在该提交检出只收集到 619 例），以本口径为准更正。
- **现状节勘误子节引文更正（段四修复第三轮登记判据时自查发现）**：「过时陈述勘误」四条里，第 1 条「实施 spec 尚未创建（G8 阻塞项）」、第 3 条「首期仅 D 循环」「L1 仅 wp 域 D 循环骨架」、第 4 条「ACNR 是四大消费库的唯一解析入口」都以「…」引号写出，但在提案原文（`96fba2c49^`）里逐字不存在，是转述；第 2 条把 `registry_version: "2026.07.10"` 示例的位置写成「附录 A / §十三」，现算只在 §5.2 / §5.3 两处（`tmp_acnr_foundation/out/段四修复3_p03_orig_phrases.txt`、`段四修复3_p05.txt`）。已改为原文逐字引文并写明所在表与行（文档体系地图「实施 spec」行的「❌ **尚未创建**（G8 阻塞项）」、执行摘要「M0（先落地）」行的「D 循环 catalog JSON 进库」、执行摘要「L1 首期」行的「经同一 `resolve` 出口」与 15.3 表 D-D10 行的「五域统一 resolve 出口」；resolver 旧注释的「四大消费库的唯一解析入口」注明出处为本 design §15.2 第 2 条），登记制守卫逐条核对引文出现在所述位置。勘误的结论（spec 已创建、版本号格式、L1 覆盖各循环、canonical resolver + legacy 委托）不变。

## 16. 待拍板（本 spec 不做，登记建议）

| # | 事项 | 建议 |
|---|---|---|
| Q0（**已裁定 2026-10-27，用户拍板**） | advanced-query-linkage-closure 的 ADR-AQL-12 / R6.5 / W4（ACNR 选字段面板「开发中」、前端不发 acnr_targets）与本 spec 需求 1（D1：实现、不下线）冲突 | **以本 spec D1 为准：acnr_targets 实现、不下线；取值、结果区与面板归本 spec；对方撤回「把 acnr_targets 标为开发中」的 R6.5 / W4，其余高级查询改动不受影响。`acnr_targets` 请求字段只在本 spec 定义一次（§2.3）；`QueryDSL.project_id` / `year`、`QueryRequest` 新字段按「谁先实施谁加、另一方复用」只定义一次。协调动作：不改对方 spec 文件，仅在本 spec design 记录裁决，并在 INDEX 登记本 spec 时注明「acnr_targets 字段与面板以本 spec 为准」。实施时两边接线以本裁决为唯一依据；本条已不是待拍板项，保留在表内仅作裁决留痕** |
| Q1 | WP 取数的数据源：`parsed_data`（WPExecutor / acnr_targets）、`checklist_responses`（预填）、存储中的 xlsx（在线编辑）三处不统一；真实项目 acnr_targets 多为 `value_in_form_storage` / `value_in_file` | 另立 spec 或并入 formula-hub 已登记的 `data_source` 差异；先定「标准底稿单元格值的权威容器」 |
| Q2 | 两参 WP 缺数返回 0 | 归 formula-hub-integrity-closure |
| Q3 | 13 张 sheet 中 33 个在范围内的种子坐标语义待核对 | 逐格核对种子；核对完成后撤销对应豁免 |
| Q4 | 目录补齐平台独有编码（现算 172 个，如 D4A、D4-22A、E1A、E26A、A13-2）与附注披露 tab；项目里 D5-1 等占位底稿 | 另立 spec；补齐后把本轮记为非地址标签与 CCR 豁免的条目改为别名或 sheet |
| Q5 | 78 组同父同名的根因：`_pick_representative` 为父级自身条目选了子表 tab 名 | 修选名规则或在 classification 中更正名称，旧名进别名；本 spec 已用编码词元裁决消除任选 |
| Q6 | V1 / V2 退役；V2 只读端点标「非权威」；`_normalize_wp_uri_to_addr_id` 的只读调用方迁到 `v2_canonical` | 按 §17 台账逐项迁移，绕过基线归零后再退役 |
| Q7 | 外部命名空间物理定位；acnr_targets 扩展到试算表 / 报表 / 附注；报告附注进 L1；放开 sheet_code 全局唯一 | 各自另立需求 |
| Q8 | `template_service.execute_template`（失效引用跳过语义）生产调用方 0 | 交 advanced-query-linkage-closure 裁定 |
| Q9 | 归档语义：归档作业只写 `archived_at` 不改 status；取消归档不清 `archived_at`；部分模块以「status 或 archived_at」判定 | 归档模块另行统一；本 spec 锁定口径跟随 status（§8.1） |
| Q10 | overlay CAS 两写者、回滚后缓存不脏的真 PG 验收；多 worker + Redis pub/sub 实机验收 | 待环境 |
| Q11 | classification 缓存刷新流程：`export_classification_cache.py` 按本地库重导会丢 771 个拆分编码；S17 新增 8 条未入缓存 | 刷新须「导出 → 拆分 → 推断 functional_type」三步成一个脚本并配 `--check`；S17 随 S 循环 spec 刷新 |
| Q12 | `/api/workpapers/index-resolve/{wp_code}` 与 `/api/wp-index-resolve` 只要求登录，带 project_id 即返回他项目 wp_id | 并入 formula-fetch-followup R4 路径维鉴权（4.2） |
| Q13 | 项目里同一 sheet 既有 sheet 级底稿又有父底稿副本（108 份 sheet 级文件是整本工作簿副本），哪份是数据权威 | 本 spec 取值与 `resolve_instance` 同口径（先 sheet 级、无则父底稿，§2.4）；权威容器随 Q1 一并裁定 |
| Q14 | `POST /api/projects/{project_id}/wizard/confirm` 只要求登录，任何登录用户可把任意项目状态置为 planning（越权写） | 补 `require_project_access("edit")` 与角色矩阵测试，归项目向导或鉴权欠账 spec；本 spec 只加「已归档拒绝」前置（§8.3） |

## 17. 消费方迁移台账草案（`consumer_ledger.json` 初始内容）

| 消费方 | 关键文件 / 符号 | 现状 | 本 spec 后 | 迁移目标 |
|---|---|---|---|---|
| 公式选址 | `FormulaRefPicker.vue`、`CellSelector.vue`；`useAcnr.listSheets/listCells`；非底稿域 `useAddressRegistry` | legacy_fallback（底稿域 ACNR，非底稿域 V1） | 显示名与引用统一；订阅带项目 | 非底稿域保持 V1 委托 |
| 公式保存校验 | `acnr/formula_validation.validate_refs_via_acnr` | migrated（底稿域）；异常时回退 V1 | 版本锁 / 目录完整性异常不再回退；停用引用接受并计指标 | — |
| 公式管理与编辑树 | `FormulaManagerDialog.vue`、`FormulaEditDialog.vue`（BP-3：L853 字面量） | migrated（树）/ legacy（L853） | 显示名读 `display_label` | L853 改走 ACNR |
| 地址 store | `stores/addressRegistry.ts`（BP-3） | legacy_fallback（V1 搜索、ACNR→V1 回退） | 订阅随 `refresh` 切换；显示名统一 | 搜索改走 ACNR |
| 高级查询地址树与取值 | `CustomQueryFieldPicker.vue`；`acnr_target_values`、`wp_cell_target` | 树已迁移、取值 not_wired | migrated | — |
| 高级查询结果引用 | `query_builder._derive_formula_refs` | not_wired（只派生 TB 两表引用） | 不变 | 结果列 addr_id（另立） |
| 底稿导航 | `useWorkpaperNavigation.ts`、`WorkpaperHtmlTable.vue`、`WorkpaperTraceView.vue`（BP-4）；`useS34CrossRef.ts`、`useS35CrossRef.ts`（BP-4，他人在研） | legacy_fallback | 不变 | 只走 `resolveIndex` / `resolve-instance` |
| 跨 sheet 追溯 | `cross_sheet_trace_orchestrator`；`wp_formula_eval_service` | 身份恒缺失 | migrated；后者显式只取值 | — |
| 底稿公式三参 WP | `WPExecutor`、`wp_formula_eval_service` 三参循环 | 三参恒 0 | migrated（经 `wp_cell_target`） | — |
| CCR 检查器 | `scripts/acnr/check_ccr_resolve.py` | 私有判定 | migrated（`exact_identity`） | — |
| 报表 | 报表域经 V1 委托 | not_wired | 不变 | 报表进 L1 或定义非底稿域身份（Q7） |
| 附注 | `DisclosureEditor.vue`、`useNoteTree.ts`（`resolveIndex(note:...)` 经 V1） | legacy_fallback | 订阅带项目 | 同上 |
| 合并 | `ConsolNoteTab.vue`、`useConsolReportAddress.ts` | legacy_fallback | 订阅带项目 | 同上 |
| 同步与失效 | `acnr/events.py`；`event_handlers/_impl.py`、`routers/wp_structure.py`、`wp_structure_bridge.py`（BP-1） | legacy_fallback | 不变 | 失效统一走 `acnr.events.invalidate` |
| 导入导出 | `bulk_tab/manifest_builder.py` | migrated（只读 ACNR manifest，既有守卫） | 依托 §5 门禁 | — |
| AI 对话提及 | `ai_chat/address_mention.py`、`mention_service.py`、`mcp_tools.py`、`address_index_source.py`（BP-1） | legacy（V1 直连） | 登记进基线 | 改走 ACNR facade |
| V2 依赖图与 stale | `routers/address_registry_v2.py`、`stale_propagation_engine.py`、读 V2 JSON 的 12 个模块（BP-2）；`useStaleImpact.ts`（BP-3） | legacy | 节点带 addr_id / 身份键、写路径只按精确身份 | 图边改为 addr_id（Q6） |
| legacy 导航门面 | `routers/wp_index_resolve.py`、`wp_workpaper_index_resolve.py` | 已转发 ACNR，鉴权仅登录 | 不变 | 鉴权见 Q12 |

现有绕过点基线（§14.1，实施时按语法树重算后冻结）：BP-1 8 处 / 7 个文件；BP-2 按 R2-F12 窄定义实施时现算后冻结（旧 47/12 不可复现）；BP-3 3 个文件；BP-4 `useWorkpaperRegistry` 3 处 + `/api/workpapers/index-resolve` 1 个文件 + `/api/wp-index-resolve` 2 个文件。

## 18. 交付边界与发布顺序

- 新模块（后端）：`services/custom_query/{acnr_target_values,strict_model}.py`；`services/wp_cell_reader.py`（仅当 formula-hub 任务 22 未入库，按其原文 + J1）；`services/acnr/{catalog_contract,catalog_release,exact_identity,display,reasons,project_registry_lock,v2_canonical,wp_cell_target,limits}.py`；`services/acnr/loaders/{from_sheet_verdicts,from_wp_account_mapping}.py`；`scripts/acnr/reconcile_v2_canonical.py`；`scripts/check/acnr_bypass_scan.py`；迁移 V{N} / R{N}。
- 新数据输入：`data/acnr/sources/{sheet_verdicts,alias_policy,acknowledgements,release_exceptions,classification_reconcile}.json`；`global_catalog.overrides.json` 填 38 条；`data/acnr/{consumer_ledger,bypass_baseline,v2_canonical_reconcile}.json`；测试夹具 `platform_name_writings`、`same_name_group_writings`、`resolvable_writings_baseline`、`display_contract`、`editor_save_inputs`。
- 新模块（前端）：`AcnrTargetResults.vue`、`queryPayloads.ts`、`AcnrCandidatesHint.vue`、`useCurrentProjectId.ts`、`acnrCatalogOnlyCallers.ts`。删除：`gen_sheet_display_names.py`、`_build_schema.py`、`_verify_schema.py`、两个分片文件、三个 fix 脚本的目录写入分支、`immutability` 进程内锁、`composeSheetLabelsForGroup` / `cleanSheetLabelName`、`notifyCellChange` 常量。
- 行数门（`len(text.split("\n"))`，阈值 = 白名单 × 1.05）：`acnr/resolver.py` 1087（阈值 1140，净增 ≤ 30，超出则把版本锁段移入 `project_registry_lock.py`）；`acnr/catalog.py` 747（上限 800，删旧启发式后净减）；`formula_engine.py` 净增 ≤ 14（余 45）；`routers/custom_query.py` 净增 ≤ 4（余 27）；`deliverable_service.py` 净增 ≤ 6（余 45）；`FormulaEditDialog.vue` 净增 ≤ 0（余 38）；`DisclosureEditor.vue` 净增 ≤ 0（HARD_CAP 3281）；`AdvancedQueryBuilder.vue`、`CustomQueryTab.vue` 只减不增；不新增白名单条目。
- 发布顺序：①加载器（CatalogIndex fail-closed + 报告互校）、新报告（带 `release`）、新目录、同版本快照、schema 必须同一提交上线——分批会让加载器拒绝旧报告；②版本锁（D5）在①之后或同提交：`lock_project_registry` 要求当前版本快照与目录同哈希，现状 20260727115337 两份内容不同，必须等首个合规批次；③acnr_targets 读取接线排在 formula-hub 任务 22 之后（或按 §2.4 自建）；④前端显示名改动与新目录同提交或之后（旧目录没有 cell 的 `display_label`）。
- 测试分层：纯函数与守卫（`exact_identity`、`display`、`catalog_contract`、门禁、AST / TS 语法树守卫）为单测；端点与权限矩阵用 TestClient；版本锁、取值、保存校验、classification 对照用 `pg_only`（回滚事务或【测试】项目）；前端 vitest + chrome-devtools；变异备份一律在 `tmp_acnr_foundation/mutations/`。
- 提交只含本 spec 文件（`git diff --cached --name-only` 核对），按需求 0.5 推送；INDEX 登记按 0.9 的 CRLF 规则。

## 19. 评审意见回应（第 1 轮，`design-review.json`）

| # | 级别 | 处置 | 位置 |
|---|---|---|---|
| F1 | HIGH | 采纳：补现状确认表；以 `composeSheetLabelsForGroup` 为基线下沉到 `display.py`，生成器写入 `display_label`（不新增 `display_name`）；三棵树与 9 处拼接纳入改动与守卫；`sheet_display_names.json` 定为生成器输入、生成脚本删除 | §13.1~13.3 |
| F2 | HIGH | 采纳：逐字采用 ADR-FHIC-06 契约与 §8.2 先后；本 spec 只做三参接线与 acnr_targets；sheet 别名由调用方求键后传入，无需改签名；联合修订只有 J1（只增字段）；三参循环与 `formula_wp_semantics` 文本各写一份 | §1.4、§2.4、§2.5 |
| F3 | HIGH | 采纳：规则第 6 步编码词元裁决，70 组确定、8 组歧义且无真实使用；26 处写法进夹具并断言所属 sheet；CCR、V2、基线写法按新规则重算 | §1.2、§6.2、§6.5、§10.2、§10.3 |
| F4 | HIGH | 采纳：A2 现查表与裁定（缓存为权威，库表缺拆分记录与推断值），差异逐类处置，报告 `release.classification` + `pg_only` 对照守卫；需求 A2 修订 | §1.3 |
| F5 | HIGH | 采纳：38 条 SAFE 档差异进 overrides（带 source、可由脚本复算），partial manifest 与基线不动；D / G 改 manifest；验收现跑 x3 守卫 | §5.4 |
| F6 | MEDIUM | 采纳：422 体用 `issues`，登记 `ACNR_TARGETS_REJECTED`；需求 1.3 修订；vitest 用真实形状 | §2.3、§2.8 |
| F7 | MEDIUM | 采纳：列出 4 个调用方；三参循环取不到记中文错误、0 只作占位且被 4 个调用方丢弃；与 formula-hub 第 6 点合成一份 | §2.5 |
| F8 | MEDIUM | 采纳：后端 `fetch_project_audit_year` 补年度，取不到 422；前端只发已知年度，`useStaleImpact` / `useEditorSave` 去日历年兜底并下调棘轮；需求 1.4、10.3 修订 | §2.3、§2.6、§11.2 |
| F9 | MEDIUM | 采纳：非 A1 末段身份 =「sheet addr_id + 原样标签」；真实入参新旧对照 113/113、100/100 作验收夹具；前端提示 + 指标 | §10.2、§10.4 |
| F10 | MEDIUM | 采纳并改判：补证据后 D5-1 判为 D5 册审定表的平台编号，并入 D5/D5 作别名、不新增 sheet，矛盾随之消失；规则第 3 步先判禁止集合并加不相交不变量 | §1.2、§6.2、§7.3 |
| F11 | MEDIUM | 采纳：修探针补齐 4 张逐格证据；不再使用第四种结论，按修订后的需求 5.5 分「范围内保留 + 语义待核对」「超出范围停用」两路；显示名不带未核实语义 | §1.2、§6.4、§13.2 |
| F12 | MEDIUM | 采纳：锁定与解锁都以 status 为准，归档作业不加锁；守卫「锁定集合 ⊆ 可解锁集合」；Q9 同口径；需求 7.2 修订 | §8.1、§8.5、§16 Q9 |
| F13 | MEDIUM | 采纳：停用条目在 6 个场景的行为表；K14 证据改为科目 6115；加 4 个项目导航可达的只读回归 | §3.2、§3.3、§3.4 |
| F14 | MEDIUM | 采纳：原因区分表单 / 在线编辑文件 / 未录入；文本格 `state=text` 返回原文；改正示例 | §2.2、§2.4 |
| F15 | MEDIUM | 采纳：复用 `resolve_target` 的超时与不可用归类，503 `RESOLVE_UNAVAILABLE`；补错误表；列出需改断言的既有测试；另修同会话并发 | §2.3、§2.7、§2.8 |
| F16 | MEDIUM | 采纳：CCR 检查器委托 `exact_identity`、删私有匹配；在统一判定下重算 CCR | §6.2、§10.3 |
| F17 | NIT | 采纳：写明同提交上线与 D5 依赖 | §18 |
| F18 | NIT | 采纳：改为 0/40（2026-10-26 核对） | §1.4 |
| F19 | NIT | 采纳：示例改用数值格 C10，显示名按 §13 规则 | §2.2 |
| F20 | NIT | 采纳：两个函数 | §1.4 |
| F21 | NIT | 采纳：5 个文件 | §14.1 |
| F22 | NIT | 采纳：按定义重算 BP-3 为 3 个文件（含别名引用与 L853 字面量，剔除注释） | §14.1 |
| F23 | NIT | 采纳：单例改为显式 `resolve_identity=False`，守卫覆盖单例 | §9.2 |
| F24 | NIT | 采纳：需求原文同步修订（见下） | requirements.md |
| F25 | NIT | 采纳：单项非空、≤512 字符、≤50 条、重复逐项作答、forbid 只作用顶层 | §2.3 |
| F26 | NIT | 采纳：删 `--offline`、`--cycle`、`--no-shards` | §5.3 |
| F27 | NIT | 采纳：扫描 `backend/app` 与 `backend/scripts`，排除 `backend/tests` | §5.4 |
| F28 | NIT | 采纳：`DateTime(timezone=True)`，三层守卫比对类型 | §8.2、§8.5 |
| F29 | NIT | 采纳：`useAcnr(() => _projectId.value)` | §12.2 |
| F30 | NIT | 采纳：外层事务 + `create_savepoint` 会话，同连接另建会话并清进程缓存 | §8.5 |
| F31 | NIT | 采纳：`db.info` 请求级记忆 | §8.3 |
| F32 | NIT | 采纳：歧义 / 禁止的 sheet 不读，返回 blocked 并带候选或理由 | §2.4 |
| F33 | NIT | 采纳：分类表写明判据字段；枚举取值逐项列出 | §2.3、§4.2 |
| F34 | NIT | 采纳：28 处逐处改法表 | §12.2 |

需求原文同步修订（F4、F6、F8、F10、F11、F12、F24 等的结果）：0.4（formula-hub 进度与 advanced-query 边界）、A2、1.1（`display_label`、四种状态）、1.2（三参求值路径与读取绑定）、1.3（`issues`、403、503）、1.4（年度补齐）、4.4（overrides 与别名超集）、5.4（同名组改判）、5.5（三路处置）、7.2（按 status 加解锁）、9.5（统一判定重算）、10.3（`/impact` 年度）、12.1（`display_label`）。需求 2.1 维持三种结论（设计不再使用第四种）。

## 20. 评审意见回应（第 2 轮，`design-review.json`，HIGH 4 / MEDIUM 9 / NIT 10）

本轮现算证据：`tmp_acnr_foundation/out/q01~q06`（HEAD `bb7aff842`，设计原写于 `b5fc200e0`，`b5fc200e0..bb7aff842` 之间 ACNR 目录 / 生成器 / 服务 / V2 / 高级查询 0 改动，§1 现算在新 HEAD 同样成立）。R2-F1、R2-F4 两条 HIGH 由用户拍板（见下）。

| # | 级别 | 处置 | 位置 |
|---|---|---|---|
| R2-F1 | HIGH | **用户拍板采纳**：25 个孤儿 cell 判为无效（现算 q01/q02/PG：addr_id 与 formula_ref 只在目录自身 4 份快照出现，`formula_presets_seed`/`cross_wp_references`/`prefill`/全 `backend/data` 其它 JSON·YAML 与 `wp_formula` 中 0 引用；渲染组件无对应 tab），从种子输入清除，逐个 deprecated 并给可解析 `replaced_by`（父 sheet）；5 张父 sheet 仍 `add_platform_sheet` 仅为让导航落到 wp_index 实例；默认不进地址树、acnr_targets 返 422 deprecated；实施前再现算复核「是否被引用」，被引用不得静默消失 | §3.2、§3.3、§3.4 |
| R2-F2 | HIGH | 采纳：「现算 0」勘误为错口径（正则漏了预设里逗号后的空格）；实施第一步另导出 `head_resolvable_static_writings.json`（含 PG 公式存储），逐条断言；D5-1/I1-1/审定表I1-1 经 `merge_into` 落父级限定别名、其余 4 组登记 `ccr_unresolved` 并标 `head_resolvable_at`（HEAD 原可解析到父 sheet·错配）；无证据组暂停说明 | §6.5、§7.3、§7.4 |
| R2-F3 | HIGH | 采纳：「11 条目标唯一」勘误（现算 q04/q05：B60×6、S14×1 的 `source_sheet` 若改到唯一子 sheet 即工时预算看板·会改错）；每条改写须两项证据（模板 tab 存在 + 字段文字在该 tab），不满足入 `ccr_unresolved`；预计修 ≤4、豁免 ≥48；§10.3/§14.3/`check_ccr_resolve` 数字重算 | §10.3、§7.4、§14.3 |
| R2-F4 | HIGH | **用户拍板采纳**：「生产调用方 0」勘误（现算 q05/grep：`catalog_snapshot_gc.query_referenced_versions`→`list_archived_projects`、启动任务与 `gc_snapshots.py` 每次启动调 `run_db_aware_gc`）；改为异步查库 `referenced_registry_versions(db)`（含软删、读 §8.2 新列）、`run_db_aware_gc(session=None)` 自开短会话、查库失败 fail-closed；加启动期 GC `pg_only` 用例 + 变异；列出受影响测试 | §8.3、§8.4、§8.5 |
| R2-F5 | MEDIUM | 采纳：构建器鉴权改复用 `resolve_builder_scope(requested_project_id=…)`（与业务视图同一 `ownership_guard`），不另起 `assert_project_permission`；`year` None 或 ≤0 视缺省；权限矩阵覆盖非成员合伙人与委派员工并断言两入口一致 | §2.3 |
| R2-F6 | MEDIUM | 采纳：删「两份设计同文」；J1 两字段走回退流程 B（formula-hub 任务 22 无则本 spec 单独追加默认 None 的可选字段，列受影响 `test_wp_cell_reader` 断言并在对方任务 22 登记）；三参 A1 分支由本 spec 单独落地 | §1.4、§2.4、§2.5 |
| R2-F7 | MEDIUM | 采纳：新增 `effective_catalog(db, project_id)`，`wp_cell_target` / acnr_targets / 三参取值统一用它并显式传 `index`；`test_project_registry_lock_pg` 加「v1·v2 名称归属不同、锁定项目按 v1」用例 | §2.4 |
| R2-F8 | MEDIUM | 采纳：`cell_of` 识别 sheet 且 A1 合法即 `resolved=true` 并返规范 addr_id、增 `in_catalog`；`wp_id`/`jump_route` 改由 `resolve_instance` 取；e2e 加未登记格 `E1-14!Z99` | §9.2、§9.3 |
| R2-F9 | MEDIUM | 采纳：遇第一个 `resolve_unavailable` 立即 503；整批套 `asyncio.timeout(ACNR_BATCH_DEADLINE_S=8)`；桩每项睡 6 秒验总耗时 / 503 / 取数 0 次 | §2.3 |
| R2-F10 | MEDIUM | 采纳：列全 5 个 `/execute` 调用点（现算 q04 之外 grep：`CustomQueryTab`/`CustomQueryDialog` L819/`SheetCellRangePicker` L211/`useBatchQuery` L107/`AdvancedQueryBuilder`）；三处改走 `buildBusinessPayload` 或 TS 语法树抽键断言子集；顺带去 `SheetCellRangePicker` 的日历年兜底 | §2.8 |
| R2-F11 | MEDIUM | 采纳：「上一发布批次」定为 `release.previous_version` 对应快照、校验 sha256、计入 `inputs_fingerprint`；`--check` 用它作沿用来源；加变异「只在 `global_catalog.json` 加别名 → `--check` 退出 2」 | §5.3、§6.3、§5.6 |
| R2-F12 | MEDIUM | 采纳：BP-2 重定义为「加载 3 个身份文件 或 读 CCR 推 sheet 身份」，纯 CCR 业务规则消费方只进台账；旧 47/12 勘误（r07 C 现算约 10/35 且 9 个只读 CCR），实施按窄定义现算后冻结 | §14.1、§1.2、§17 |
| R2-F13 | MEDIUM | 采纳：前端 `addressRegistry` store 与导航回退前先判 409（`ACNR_REGISTRY_SNAPSHOT_MISSING/INVALID` 直接返 found=false·不回退 V1）；vitest 用真实 409 形状断言不发 legacy；删快照步做浏览器核对 | §8.3 |
| R2-N1 | NIT | 采纳：Q0 已由用户裁定（见下），tasks 实施时仍把 acnr_targets 前端面板 / 结果区标「用户闸门：Q0（已裁定以本 spec 为准）」，不改对方 spec 文件 | §16 Q0、§2.6 |
| R2-N2 | NIT | 采纳：列出 `catalog_report.json` 读取方（`check_acnr_catalog_drift.py` 删陈旧度判据、`test_catalog_gap_count_integrity::TestRealCatalogReport` 改断言）同批改写 | §7.1 |
| R2-N3 | NIT | 采纳：`generate_catalog()` 保留 `offline`（忽略）与 `cycle`，只删 CLI 选项，改 docstring Usage | §5.3 |
| R2-N4 | NIT | 采纳：`RegistryLockError` 不继承 `ValueError`（继承 `CatalogLoadError`），路由层 409 | §8.3 |
| R2-N5 | NIT | 采纳：保存模板时校验 acnr_targets；`execute_template` 捕 `ValidationError` 转 422 | §2.3 |
| R2-N6 | NIT | 采纳：按调用链现算结论——`wp_render_registry` db=None 但无 project_id 不受影响；`formula_management/engine.resolve_ref` 透传可能 None；D6 后「project_id 非空且 db 为空」应为 0 由守卫钉住 | §8.3 |
| R2-N7 | NIT | 采纳：绑定到父底稿时 `source.jump_route` 必填（本层拼 `sheet={sheet_code}`），用例覆盖「只有父底稿」不提示失效 | §2.2 |
| R2-N8 | NIT | 采纳：校验器放 `strict_model.py` 的共享 `Annotated` 类型 `AcnrTargetList`，路由只改字段类型 | §2.3 |
| R2-N9 | NIT | 采纳：`ExportDSL` 若已由 advanced-query 引入则同样继承 `StrictRequestModel`（谁先实施谁加） | §2.3 |
| R2-N10 | NIT | 采纳：接受集合改 `source_layer == "L1_cell"`（overlay 命中同标 L1_cell，`"L2"` 不会出现），用例钉住 | §2.3 |

**用户拍板两处（2026-10-27）**：
- R2-F1：孤儿 cell 真实性——判无效、从种子输入清除、登记 deprecated 迁移映射（保留别名指向），实施前须现算复核引用（§3.2）。
- §16 Q0（跨 spec 冲突）：以本 spec D1「实现、不下线」为准；`acnr_targets` 字段只在本 spec 定义一次；对方撤回下线计划；不改对方 spec 文件，只在本 spec design 记录裁决、INDEX 登记注明以本 spec 为准（§1.4、§2.6、§16 Q0）。

**本轮未能自行判定、仍登记待拍板**：无新增阻塞级分歧。R2 全部 HIGH/MEDIUM/NIT 均已在设计内落实或给出可执行的实施期现算口径；原 §16 的 Q1~Q14 维持（均为本 spec 范围外、已有建议归属）。

## 21. 段六补记：T06 后半与 T07 主体的实施口径（2026-10-27）

只记与上文不同或上文未写明的实现决定；数字均为现算。

- **首个合规批次的「上一批次」**：§5.3 第 1 条写「首个合规批次无上一批次时 previous_version=null」，§5.4 / §6.3 又要求 G1 四张旧别名由上一批次快照沿用、重算值为已提交值的超集。二者对首批只能满足其一。实现取后者：旧报告没有 release 段时，`catalog_build.locate_previous` 取报告 `registry_version`（20260727115337）的快照，前提是 `release_exceptions.json` 登记了该快照的全长内容哈希（即 §5.3 第 5 条那条唯一例外，内容哈希不符即拒绝）。首批 `release.previous_version` 因此是 20260727115337 而不是 null；该快照同时作为不可变门禁的比对基准。G1 四张现为「旧别名（快照）+ 新别名（标签源）」并存。
- **release 段多两个字段**：`previous_catalog_sha256`（`--check` 以已提交版本重算时，沿用来源是 `previous_version` 的快照，用它校验快照未被改动）与 `inputs`（逐文件路径与 LF 内容哈希，`inputs_fingerprint` 可由它复算）。上一批次快照在 `inputs` 里记规范相对路径。
- **报告分组仍是旧形态**：T07 只给报告加 release 段与 `open_problems.unregistered_alias_keys`（门禁 alias / ack 判失效条目的问题清单，28 条）；四组分组与 `gap_count` 删除属 T09。`summary.total_sheets` / `total_cells` 改为发布后规模，并加停用条目数等计数。
- **「有效 cell 449」口径更正**：§3.2 把「474 − 25 孤儿」记为 449 个有效 cell，同时又说另有 14 个 §6.4 超范围停用条目；这 14 格本在 449 之内。发布后现算：cell 474 = 停用 39（孤儿 25 + 超范围 14）+ 非停用 435，其中语义待核对 33。往返判据（`test_generator_name_rules_roundtrip_all_non_orphan_cells`）覆盖发布后全部 474 格的 formula_ref 与 uri（含停用格），门禁 roundtrip 只核非停用格。
- **47 格的识别以输入为准**：§1.2 的 47 格是「cell 自带 formula_ref 往返失败且第二参不是平台名」，目录重生成后 formula_ref 已改写、这个口径会变成 0。守卫改为从地址种子识别（种子名与模板名、sheet_code、平台名都不同，且不能经编码词元回到本 sheet），与 HEAD 口径逐个相等（47 = 31 + 2 + 14，13 张 sheet）。
- **sheet_verdicts 证据键改名**：`in_catalog_as_sheet` → `in_classification_skeleton`。发布后这 10 张都在目录里（由判定记录写入），判定前提是「classification 骨架没有它」，守卫按骨架现算。
- **（已过时，见下一条：该分支已在 `4ac0d31ff` 删除，T07 已由评审核实）`fix_x3_adjustment_ie_registration` 的目录写入分支未删**（T07 未完成项）：它的 `patch_catalog` 被 x3 的四个测试文件在临时副本上直接调用，删分支须同步重写这些测试。`test_only_generator_writes_catalog` 用 AST 污点分析（写入目标由目录字面量派生）现算出写入方恰为生成器与这一个脚本，严格判据以 `xfail(strict=True)` 钉住，删分支后 XPASS 即逼迫去掉标记与登记。
- **上一条的后续（段六续做复审第 1 次 RV1-01 / RV1-02）**：登记器的目录写入分支已删——`patch_catalog`、`_assert_surgical`、`_structural_diff` 与 `--apply` 一并删除，`--check` 核对生成后的目录（缺段即退出 2 并点名 `generate_catalog.py --write`），保留的唯一写盘是 R5.8 Deviation 侧车（新模式 `--record-deviations`，原由 `--apply` 顺带写）。x3 三个测试文件按「核对只读」重写：Property 5 改在生成后的 committed 目录副本上跑（不注入时退出 0，注入后的 2 只能来自 Preflight 拒绝），Property 6 由「`--apply` 幂等 + 差异集最小」改为「核对只读、pending 恰为 16 − S、N 次零写盘且结论一致」。`test_only_generator_writes_catalog` 去掉待改登记与 xfail，严格判据真绿；该守卫的模块级作用域原把函数体并进来，不同函数里同名局部变量（`doc`）互相串污点，删分支后仍误报登记器，已改为只含函数 / 类定义之外的语句，并加同名不串、`if __name__` 块直写两条自检。x3 偏差登记 G2 组按迁回后的事实重核：overrides 给 `import_export` 的条目是生成器输入的第二兜底，不再计入「重生成即丢」，现算 0（无 manifest 的 38 条全部由 overrides 兜底），按该脚本规范 `--emit --set-baselines --lowered-by-task 7` 把基线 38 下调为 0。
- **`check_ie_catalog_sync` 在本轮之前的 HEAD（`347cf5a7d`）上退出 1、报 19 处**：D1 / G 共 15 张目录 api_prefix 与 manifest 不一致，H 4 张「manifest 未登记」（都是目录外科补丁）。本轮 manifest 改为已核验前缀、按 §5.4 加「经 overrides 登记」来源后退出 0。
