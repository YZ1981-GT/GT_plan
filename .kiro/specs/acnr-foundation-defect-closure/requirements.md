# 需求文档：ACNR 地址坐标名称库底座缺陷收口（acnr-foundation-defect-closure）

## 概述

问题来源：`.agents/tasks/acnr-platform-foundation-assessment-2026-10-26.md`（下称「审计报告」）的 ACNR-P0-01~03、P1-01~05、P2-01~02，及其 §9 任务包、§10 门禁清单、§11 勘误。本轮在 HEAD `b5fc200e0` 上现读现算，又确认了一批同根缺陷（§1 标【新】）。用户授权「你是专业的，直接修复」，决策 D1~D12 已代为拍板（§2）；源码事实与决策冲突处按事实调整，并在 §2 注明。

目标：把 ACNR 从「可用内核 + legacy 委托」收口为可发布、可校验、可复现的寻址底座：

- 目录产物只由生成器写出，写出前门禁全过；CI 判据确定，并且能打红；
- 在公式选址器选得到的地址，保存公式一定通过；在高级查询里选中的单元格，一定出现在结果里；
- 同一地址在各界面同名、同引用；解析不到时说清原因和下一步；
- 归档项目重启后仍按归档时的目录解析；会写 stale 的端点有项目鉴权。

铁律：

1. 根因修复，禁止换参数绕开；失败不得表现为 0、成功、空结果或「已是最新」。
2. 生成产物（`global_catalog.json`、`catalog_report.json`、快照、分片、classification 离线导出缓存）禁止手改，修正落在生成器的权威输入。
3. 被真实项目使用或被引用的 addr_id 不得直接消失：要么继续可解析，要么 deprecated 并给出可解析的 `replaced_by`；给不出迁移映射时暂停，向用户说明。
4. 每条门禁都用真实产物或真实请求链验证，并有磁盘变异证明它能打红，且红在预期的那一条上。

术语：

- **目录**：L1 `backend/data/acnr/global_catalog.json`。**发布批次**：同一次生成写出的目录、报告、快照（以及分片，若保留）。
- **往返**：把目录条目自带的 addr_id / formula_ref / uri / index_ref 交给 `full_resolve`，得到同一 addr_id。
- **模板 sheet 名**：classification 记录的 `sheet_name`（即目录 `sheet_name`）。**平台底稿索引名**：`backend/data/wp_account_mapping.json` 的 `wp_name`，也就是真实项目 `wp_index.wp_name`，用户在底稿列表里看到的名字。
- **真 PG**：`pg_only` 标记、连本机 `audit_platform` 的测试；写入一律在回滚事务或【测试】项目内。
- **变异证明**：先把原文件与 sha256 备份到 `tmp_acnr_foundation/mutations/`，再对磁盘文件注入缺陷，确认对应守卫红、且红的形态符合预期，最后逐字节还原并核对 sha256。

## 0. 工作方式与约束

0.1 临时产物一律放仓库内的 `tmp_acnr_foundation/`（`tmp_*` 已被 .gitignore 忽略；用户 2026-10-26 要求，原因是仓库外读写每次都要用户确认）：

- `probes/`：一次性探针脚本，定位仓库根用 `Path(__file__).resolve().parents[2]`；
- `out/`：探针输出与长跑测试日志（本文件引用的 `out/pNN` 均在此目录）；
- `mutations/`：变异前的原文件备份与 sha256。禁止在源文件旁边留 `*.mutbak`，其他会话的还原脚本会从仓库根 rglob 找到并还原它们；
- `screenshots/`：浏览器实测截图，截图时传该目录下的文件名；
- `verify_wt/`：干净的分离头验证 worktree。

不再使用 `C:\acnr_probe\` 与 `C:\acnr_verify_wt`。

0.2 verify_wt 只在验证期间存在，建立后执行 `git worktree lock`。若建了 node_modules 联接，跑完立即用 `cmd /c rmdir` 拆掉。删除顺序按目录内 README.txt：确认没有联接 → unlock → Remove-Item → `git worktree prune`。verify_wt 存在期间，不在主树跑从仓库根全量遍历的检查（如 check_file_size、check_utf8_integrity 的无参全量模式），否则副本会被重复计入；pre-commit / pre-push 钩子只查暂存文件，不受影响。

0.3 他人改动：setup 记录的他人脏文件一律不改、不暂存。包括 `.agents/tasks/` 下三组评估目录、S 循环 bundle 组件与 composables、`auto-imports.d.ts`、`components.d.ts`、`workpaperApi.ts`、`workpaper_schemas.py`、`wp_relation_router.py`、`test_render_config_wire_contract.py`、`BundleAssignee*` 与 `test_wp_index_assignee_display.py` 等。审计报告只读、不提交。每次提交前用 `git diff --cached --name-only` 核对只含本 spec 的文件。

0.4 并发 spec：

- `formula-hub-integrity-closure`（0/40，2026-10-26 核对）负责共享读取函数 `wp_cell_reader.resolve_wp_cell`（其 ADR-FHIC-06、§8.2，任务 22 先提交）。本 spec 逐字采用该契约，只做三参 `WP(底稿,sheet,A1)` 接线与 acnr_targets 调用，`formula_wp_semantics.py` 的登记两份设计只写一份；动手前核对对方是否已提交。
- `advanced-query-linkage-closure`（0/37）。本 spec 只动 acnr_targets 相关接线，高级查询的其余缺陷归对方；对方 ADR-AQL-12 / R6.5 把 ACNR 选字段面板标「开发中」，与本 spec D1 冲突，登记在 design §16 Q0 待用户裁定；两边共用的请求字段（`QueryDSL.project_id` / `year` 等）只定义一次。

0.5 分支与推送：直接提交到当前分支 `spec/disclosure-note-doc-upload-and-batch-fill`，不新建分支、不直推 master；push 前先 fetch 同步。主树有他人脏文件导致 pre-push 拒推时，在 verify_wt 分离头推 `HEAD:<当前分支>`，推前手工跑 `backend/scripts/check/check_staged_tree_self_consistency.py`。不用 `--no-verify`，不 stash 他人文件，不在共享终端设置 git 环境变量。

0.6 行数门：新增逻辑放新模块，不让已登记的大文件越过白名单 +5% 阈值（余量见 F19），不为凑行数新增白名单条目。

0.7 测试约定：后端用 `python -m pytest -p no:playwright`；hypothesis `max_examples=5`；PG 专有 SQL 加方言判断；前端用 vitest。全量 vue-tsc 在本仓库会 OOM，类型检查用单区域 tsconfig 并配变异证明。共享开发环境不重启 start-dev，迁移用 `MigrationRunner(...).run_pending()` 落本地库。

0.8 前端改动都要浏览器实测。用 chrome-devtools（Playwright 浏览器与并发会话共用当前页），关键点击前在同一段脚本里校验 `location.pathname`。写入型验收只用【测试】项目，清理走平台路径并对账。

0.9 本 spec 要登记到 `.kiro/specs/INDEX.md`。该文件纯 CRLF，按 bytes 读写；表格单元格内禁用裸竖线，校验时只数未转义的竖线。

## 1. 现状事实表（F 编号只在本文件维护）

| F | 事实 | 来源 |
|---|---|---|
| F1 | 目录 `registry_version=20260727115337`，sheets 1215、cells 474。sheet / cell 的 addr_id 与 sheet_code 重复均为 0，sheet 与 cell 互撞为 0；非 semantic_only 的 cell 都满足 addr_id = 父级/A1 | out/p01 |
| F2 | 孤儿 cell 25 个（I6/I6-7 5、J2/J2-5 5、J3/J3-4 6、J3/J3-5 4、M6/M6-5 5）。这 5 张父 sheet 不在模板册（I6、J2、J3、M6 四本册的 sheet 清单里没有），也不在 classification（4640 条）；但在种子（i、j、m 三份）和 `wp_account_mapping` 有登记（如「研发加计扣除测算」）。真库安徽骨科医院_2025（2d2d819b）各有 1 条 wp_index 和 1 份 draft 底稿（2026-10-25 由模板生成，无 parsed_data）。I6-7、M6-5 在 `wp_code_overrides.json` 有 componentType；J3-1 渲染 schema 跨引 J3-4、J3-5；`wp_formula`、`report_config` 中没有公式引用这 5 张 | out/p04、p07；PG 现查 |
| F3 | 用 Draft-07 校验真实目录共 512 错：registry_version 格式 1、functional_type 枚举 201、purpose 枚举 301、`import_export.item_id` 为数组 9。schema 由 `docs/acnr/schemas/_build_schema.py` 手写枚举生成，`_verify_schema.py` 只校验样例。目录里 functional_type 实有 10 种（来自 classification 表，VARCHAR(50)，无约束），purpose 实有 183 种（来自种子）。jsonschema 4.26.0 已装，但未在 `backend/requirements.txt` 钉版本 | out/p01、p10 |
| F4【新】 | 已提交目录与生成器重算不一致，差 57 张 sheet：import_export 53 张（api_prefix、item_id、storage_field、enabled），来自 3 个直接改写 `global_catalog.json` 的 fix 脚本（dangling_api_prefix、catalog_ie_gap、x3_adjustment_ie_registration）；sheet_name_aliases 4 张（G1-8、G1-10、G1-12、G1A），来自标签源改动后未重新生成。CI 的 `check-acnr-catalog-drift` 与 `acnr-ie-catalog-sync`（19 条 api_prefix 不一致：D 1、G 14、H 4）在 HEAD 即红 | out/p08、p11、p14 |
| F5【新】 | 同一版本对应两份内容：快照 `20260727115337.json` 与当前同版本目录有 70 张 sheet 的 import_export 不同；`write_catalog` 遇到同名快照会静默跳过归档。快照 20260727114738 → 20260727115337 之间移除了 K14~K18 五个 sheet addr_id，移除前没有标 deprecated；而真库有 3~4 个项目各自在用这 5 个底稿 | out/p01、p13、p17；PG 现查 |
| F6 | 报告与目录不是同批：报告 generated_at 为 2026-08-01，冲突 5 条，gap_count 33，gaps 却是空数组。生成器现算冲突 4 条（差异来自一处标签由「（国有企业）」改为「（国企）」），gap_count 32，未登记别名 28 条 | out/p01、p12 |
| F7【新】 | 分片过期：`shards/catalog_ALL.json` 为 0 sheet、0 cell；`catalog_D.json` 停在版本 20260710102744；全仓没有消费方 | out/p01；grep |
| F8【新】 | 真实目录逐条往返（无项目上下文）：cell addr_id 474/474；sheet addr_id 与 `sheet:{code}` 均 1215/1215；`cell:{code}!{A1}` 449/474（失败的 25 个都是孤儿）；cell 自带的 formula_ref 与 uri 只有 30/474 能往返。失败 444 个 = 第二参写的是平台底稿索引名 372 + 种子名与模板名、索引名都不同 47（13 张 sheet，例如种子把 F4-3 记为「应付账款账龄分析」，而模板 F4-3 是「调整分录汇总F4-3」）+ 孤儿 25 | out/p02、p16、p17 |
| F9【新】 | 真 PG（安徽骨科医院_2025 上下文）：`validate_refs_via_acnr` 拒绝选址器插入的 `WP('E1','货币资金分析程序（一）','B30')`，接受模板 sheet 名与 sheet_code 的写法。即 E~S 循环里在公式选址器选出的单元格，保存公式时会被平台自己拒绝 | out/p15 |
| F10 | `CatalogIndex` 遇到重复 addr_id 时后写覆盖前写；生成器写出前不查重复、外键、往返，也不调用 `check_addr_id_immutable`。4 份快照都没有重复 addr_id；最早的 2 份各含 332 个孤儿 | 源码；out/p10 |
| F11 | 构建器 `QueryDSL`（`/api/query/preview`、`/execute`、`/export-excel`）没有声明 `acnr_targets`，被 pydantic 静默丢弃，请求也不带项目与年度。业务视图 `QueryRequest` 已声明该字段，并经 `AddressingService` 做全有或全无解析（不可解析返回 400，`verify_existence=False`），但 `business_fetcher` 不引用解析结果（AST 现算）【新】。所以两个入口的结果都不含所选单元格。构建器结果的 columns 是 `list[str]`，业务视图的列元数据不带 addr_id，后端也不产出 `{列}__addr_id`。所以常规查询从不产生可下钻列，前端下钻分支不可达【新】 | 源码；AST |
| F12【新】 | 公式引擎 WP 取数 `WPExecutor.execute`：两参写法的 A1 不区分 sheet（E1-14!B30=111、E1-15!B30=222 时，两参取到 111）；三参写法（非 D2-3）恒返回 0；取不到时返回 0。三处 WP 实现的差异登记在 `formula_wp_semantics.py`（守卫做精确相等断言） | out/p09；源码 |
| F13 | 版本锁只存在进程内 dict，生产调用方为 0。项目归档有两个写入方【新】：归档作业成功后 `_set_project_retention` 写 archived_at（并吞掉异常）；交付件全部归档后写 status=archived。取消归档只把 status 改回 execution。锁定版本的快照缺失时，resolver 抛 `VersionNotFoundError`，`/api/acnr/*` 路由没有映射（源码推断会返回 500，未实测）。projects 表没有版本列；迁移现扫最高 V205 | 源码；out/p12、p14 |
| F14【新】 | `CrossSheetResolver._sync_resolve` 在运行中的事件循环里返回 None。`/cross-sheet-trace` 使用的异步编排器把节点转成 `cell:{sheet 名}!{A1}`，而 ACNR 只认 sheet_code，所以用真实 sheet 名时 addr_id 仍为 None。`wp_formula_eval_service` 在 async 求值里调用同步追溯 | out/p07；源码 |
| F15 | V2 的 `/resolve`、`/anchors`、`/stale-impact` 用包含匹配，响应中没有 addr_id。`notify-cell-change` 只要求登录，就能对任意 project_id 写 stale，缺 year 时写死 2025；前端没有调用方，已被 `/api/linkage-bus/impact` 替代【新】。linkage-bus 的 `POST /impact`、`GET /impact-by-addr` 同样只要求登录就写 stale，鉴权基线已登记为欠账【新】。stale 引擎用正则从 sheet 显示名里抠 sheet_code，抠不到就用显示名拼 id【新】 | 源码 |
| F16 | 前端生产代码中无参 `useAcnr()` 有 28 处、分布在 27 个文件，带参 1 处【新：审计报告只列了 2 处】。`useAcnr(projectId?: string)` 只接受静态字符串；地址 store 是没有组件实例的 Pinia store | out/p03；源码 |
| F17 | grammar_v1 有 6 个外部命名空间（Adj、Att、EQCR、Calc、Sample、Confirm），解析返回 `external_module_not_resolved`，没有中文原因。GtIndexChip 的提示只按层级拼「跳转 → ns:target」 | 源码 |
| F18【新】 | ACNR 相关 CI 门禁基线（HEAD 输入干净）：14 项中 4 项红。分别是 drift、ie-catalog-sync（同 F4）、ccr-resolve-blocking（CCR 源 425 个，不可解析 57 个，均为 `3arg_sheet_miss`：平台索引名 10、源底稿不在目录 4、其他 43）、consumer-coverage --strict（`services/ai_chat` 下 4 个文件未登记）。消费方扫描器按行做正则匹配，台账里有「纯注释引用」条目 | out/p11、p13、p16 |
| F19 | 行数门（`len(text.split("\n"))` 口径，白名单 +5%）余量：`acnr/resolver.py` 1087 行（白名单 1086，余约 53 行）；`formula_engine.py` 2198 行（2137，余约 45 行）；`routers/custom_query.py` 3087 行（2966，余约 27 行） | out/p10 |
| F20【新】 | 目录 sheet_code 与平台底稿编码的差集：平台独有 172 个编码（如 A10-1、K14~K18、I6-8、M6-6），目录独有 362 个 | out/p14 |

## 2. 决策与按事实调整

| 决策 | 要点（摘自任务说明） | 按事实调整 |
|---|---|---|
| D1 | acnr_targets 实现、不下线，语义为「跨模块单元格取值」；取值复用公式引擎 WP 取数的同一实现；结果可审计；不可解析、无权或不支持时返回 422，逐项给中文原因；QueryDSL 不再吞未知字段；核实常规查询能否产生下钻列 | ① 现有 WP 取数不能按 sheet 精确取值（F12）：在同一实现内补齐，公式引擎的三参写法随之由「恒 0」变为真实值，并登记到 `formula_wp_semantics`，不另写读取逻辑。② 构建器请求没有项目与年度（F11）：带 acnr_targets 时必须携带并鉴权。③ 业务视图现在返回 400，改为 422。④ 本期只支持底稿域单元格（地址树只出底稿域），其余域返回 422 |
| D2 | 孤儿逐张判定：真实存在则补输入源 sheet；挂错父级则修父级；都不成立则 deprecated 并给迁移映射 | 5 张父 sheet 在平台底稿编码和真实项目中都存在（F2），判定证据须包含这两项；K14~K18（F5）按同一口径处置 |
| D3 | 契约只留一份；保留时间戳版本；schema 跟随真实契约；枚举以生成器受控词表为单一来源；生成器与 CI 都校验真实产物 | purpose 是 183 种自由取值（F3），用受控词表还是受控模式由设计裁定 |
| D4 | 写出前强制查重复、外键、A1、往返、不可变；别名三类处置；豁免可伪证；同批互校；幂等；`--check`；CatalogIndex fail-closed；冲突与未登记别名逐条处置；报告分组 | 先把 F4 的 57 张补丁迁回生成器输入，否则 `--check` 首跑即红；往返门禁依赖名称体系修复（F8、F9）；同版本异内容（F5）须处置 |
| D5 | 归档与取消归档在同一事务内持久化 registry_version；旧项目为空即未锁定；锁定后按快照解析，缺快照 fail-closed；清理只删未引用版本；真 PG 重启验证 | 锁定与解锁按 `status` 接线（置 archived 1 处、离开 archived 1 处；只写 `archived_at` 的归档作业不加锁，design §8.1）；缺快照时返回中文业务错误，而不是 500 |
| D6 | 运行中事件循环拿到真实 addr_id；真实 async 请求链测试 | 异步编排器路径同样失效（F14），一并修 |
| D7 | V2 节点与边以只增方式加 addr_id 或 unresolved_reason；包含匹配只作候选；写操作只按精确或规范命中；双读对账 | stale 写入的身份不得由正则猜测（F15） |
| D8 | notify-cell-change：复现 → 按真实调用方定权限级别加鉴权 → 前端同步 → 更新鉴权基线；排查 V2 其余带 project_id 的端点 | 该端点没有前端调用方；真实写 stale 的调用方走 linkage-bus `/impact`（底稿编辑器保存、公式管理），三个写 stale 端点做同类修复 |
| D9 | 无参 useAcnr() 改为带当前 projectId 订阅；只清本项目缓存、切项目不串、不重复订阅 | 范围是 28 处，不是 2 处（F16） |
| D10 | 统一显示（共享格式化函数为单一来源）；歧义时显示候选与所需上下文；外部命名空间给中文原因与下一步 | — |
| D11 | 消费方迁移台账 + AST 级棘轮守卫（基线只减不增，配变异证明） | 现有扫描器是行正则且 HEAD 即红（F18），改由 AST 守卫取代 |
| D12 | 架构提案补「现状（2026-10-26）」节；勘误记在本 spec 的 design，不改历史报告 | — |

## 3. 功能需求与验收标准

> 验收编号为「需求 X.Y」；「核查」写明机器核查方式。测试文件名是设计约定，实施时可以微调，但须在 tasks 中同步。每条需求至少有一条变异验收。

### 需求 1　高级查询里选中的单元格出现在结果中（ACNR-P0-01 · D1）

作为审计助理或现场经理，我在高级查询（业务视图或构建器）的地址树里选中若干底稿单元格并执行，希望结果逐格给出它们在本项目本年度的值、中文名、来源和下钻入口；选错、无权或暂不支持时，立即看到逐项中文原因。

1.1 当查询请求携带非空 `acnr_targets` 时，系统应先校验调用者对请求项目的访问权，再在请求的项目与年度上下文中逐个经 ACNR 解析，并按请求顺序为每个目标返回恰好一条结果。字段至少包括：规范 `addr_id`、中文 `display_label`（目录统一显示名，见需求 12.1）、`registry_version`（本次解析实际使用的目录版本；已锁定项目为锁定版本）、`value`、`state`（`ok` / `text`（文本格，返回原文）/ `missing` / `blocked`）、`reason`（非 `ok` 时为非空中文，并带机器可读的 `reason_code`）、下钻元数据（前端 `useAcnrDrill` 可直接消费）。业务视图 `POST /api/custom-query/execute`、模板执行与构建器 `POST /api/query/execute` 返回上述结果；构建器 `/preview` 只返回解析结果、不取值；`/export-excel` 把取值结果导出到独立工作表。核查：`test_acnr_targets_query_e2e.py`，用 TestClient 真发请求，在真 PG 回滚事务内建【测试】项目并写入已知的底稿值，逐字段断言。

1.2 取值调用公式引擎 WP 取数的同一函数（与第三参为 A1 的三参写法 `WP(底稿,sheet,A1)` 共用），按「项目、底稿、sheet、A1」精确取值；读取的底稿与 `resolve_instance` 同口径（先 sheet 级底稿，项目中没有时读父底稿）。同一底稿两个 sheet 的同一 A1 写入不同值时，两个目标各取各的值；底稿未生成或单元格无值时，`state=missing`、`value=null`，不得返回 0。在同一夹具上，公式引擎三参求值（底稿公式求值路径）、acnr_targets 取值与库内值三者逐值相等；两参写法行为不变（报表与底稿公式的既有回归全绿）；`formula_wp_semantics.py` 的登记随之更新，其守卫全绿。核查：同上，另加 `test_acnr_targets_single_reader.py`（AST 守卫：acnr_targets 取值路径只调用登记的 WP 读取函数，不直接遍历 parsed_data）。

1.3 若任一目标不可解析或有歧义、已停用、只是 sheet 级地址，或属于本期不支持的域（非底稿域、外部命名空间、项目内运行时条目），则系统应返回 HTTP 422（`error_code=ACNR_TARGETS_REJECTED`），`detail.issues` 逐项给出原文、`error_code`、中文原因与候选（如有），与前端 `formulaRefIssues.ts` 同构；调用者无权访问请求项目时返回 403；地址解析超时或解析器不可用时返回 503 `RESOLVE_UNAVAILABLE`。以上情形都不执行任何取数（全有或全无）。核查：参数化端点用例覆盖每一类原因；用 spy 断言取数函数调用 0 次。

1.4 若构建器请求带 `acnr_targets` 却缺少 `project_id`，则返回 422「选择单元格取值时须指定项目」；缺 `year` 时按项目审计年度（`fetch_project_audit_year`）补齐，仍取不到返回 422 `YEAR_REQUIRED`；前端不以日历年兜底。不带 `acnr_targets` 的构建器请求行为不变。单次请求的目标数上限与 `resolve-batch` 现行上限一致（50），超限、单项为空或超过 512 字符返回 422（中文消息）。

1.5 `QueryDSL` 拒收未声明的字段：请求体含未知键时返回 422，中文消息点名该键。业务视图请求模型同样不得静默丢弃字段：契约测试现算全部前端调用方（AdvancedQueryBuilder、CustomQueryTab、模板执行）发送的键，必须是模型声明字段的子集。核查：`test_query_dsl_rejects_unknown_fields.py`。

1.6 前端两个查询入口单独展示 acnr_targets 结果区（中文名、值、状态、原因、下钻 chip）。`missing` 显示原因，不显示空白或 0；422 的逐项中文原因由调用方自管提示展示（请求带 `_silent`，不出现 pydantic 英文）。构建器在项目内使用时自动带上当前项目与审计年度；没有项目上下文时，地址选择区提示先选项目，不发送 acnr_targets。保存为模板的 acnr_targets 在执行时走同一语义。核查：vitest + 浏览器实测（截图存 `tmp_acnr_foundation/screenshots/`）。

1.7 常规查询的下钻核实：设计中记录「常规查询结果能否产生可下钻列元数据」的现算结论（F11：不能）。前端下钻分支至少被 acnr_targets 结果真实触达一次（浏览器中点击 chip 打开对应底稿）。不为常规列新增下钻（范围外）。

1.8 变异：删掉 DSL 的 acnr_targets 声明 → 1.1、1.5 红；把 resolver 改为恒 miss → 1.1 红；把取值改回「取首个同名格」或「缺数返回 0」→ 1.2 红；去掉项目访问校验 → 非成员用例红。

### 需求 2　孤儿 cell 清零，历史移除按同一口径处置（ACNR-P0-02 · D2）

作为目录维护者，我希望每个单元格都挂在地址树里看得到的 sheet 下，目录里出现过的地址不会无声消失，这样「解析得到」与「选得到」才一致。

2.1 对 5 张父 sheet（以现算为准）和 K14~K18 五个历史 sheet，逐张形成机器可读的判定记录。证据字段至少包含：模板册 sheet 清单、classification 记录、种子、I/E manifest、`wp_account_mapping`、真实项目 wp_index 计数。结论只能是「补输入源 sheet」「修输入源父级」「deprecated + 迁移映射」三者之一，并写明修正落在哪个生成器权威输入。核查：守卫断言记录齐全、证据字段非空、结论在三者之内。

2.2 发布后的目录中，`parent_addr_id` 不在 sheets 集合内的 cell 数为 0（包括 deprecated cell）。核查：生成门禁（需求 4.1），另加 `test_catalog_release_integrity.py` 读真实目录现算。

2.3 原 25 个 cell addr_id 与 K14~K18 五个 sheet addr_id 发布后全部可解析：有效条目直接命中；deprecated 条目返回 deprecated 标记和可解析的 `replaced_by`。其父 sheet 能经 `GET /api/acnr/entries`、`/anchors` 列出；deprecated 条目按设计标注，默认不进地址树。核查：逐个调用 `full_resolve`，并对端点断言。

2.4 修正不得落在 `global_catalog.json` 或 classification 离线导出缓存本体上：生成器 `--check` 对已提交产物为 0 差异。变异：从输入源删掉一条补登的 sheet → 门禁报孤儿并点名该 sheet。

### 需求 3　目录契约只有一份（ACNR-P0-03 · D3）

作为下游工具和 CI 的维护者，我希望机器可读的目录契约只有一份，而且用它校验真实产物恰好通过，这样能据它判断目录，而不是被它误导。

3.1 机器可读契约只有一个权威来源。若保留 `docs/acnr/schemas/global_catalog.schema.json`，它由该来源生成并受 `--check` 守护，枚举与模式不在两处手工维护。核查：`test_catalog_schema_single_source.py` 断言 schema 中 functional_type、purpose、import_export、registry_version 的约束与生成器受控词表逐值相等。

3.2 `registry_version` 保持 14 位 UTC 时间戳格式（`^\d{14}$`），schema、生成器与架构提案三处一致。

3.3 functional_type 受控词表覆盖目录现有的全部取值（现算 10 种加缺省）；purpose 的受控词表或受控模式覆盖现有 183 种取值；`import_export.item_id` 接受单值与数组两种形态（现有 9 张多项 sheet）。生成器遇到词表外的取值即失败，并点名条目。

3.4 用 Draft-07 校验真实的 `global_catalog.json`，结果为 0 错误。生成器写出前与 CI 中各执行一次，校验对象是真实产物，不是样例。

3.5 校验依赖在 `backend/requirements.txt` 中钉精确版本（当前环境为 jsonschema 4.26.0）。

3.6 变异（对输入或产物副本）：注入词表外的 functional_type、把 registry_version 改成 `2026.1.1`、删掉一个必填字段、给 cell 加 `project_id` → 生成器与 CI 的校验各自红，报错点名 JSON 路径。

### 需求 4　生成器发布门禁（ACNR-P1-01 · D4）

作为平台工程师，我希望目录只能由生成器经完整门禁写出，重复、断链、改主键都在写出前被拦下，这样唯一性与可复现才是发布保证，而不是巧合。

4.1 生成器写出前强制执行以下检查，任一不过即非零退出、不写任何文件，并逐条点名：

- sheet / cell addr_id 重复为 0（含 sheet 与 cell 互撞）；
- sheet_code 全局唯一（现行政策；放开属范围外）；
- cell 父级外键孤儿为 0；
- 非 semantic_only 的 cell 满足 `addr_id = parent_addr_id/A1`；
- 往返（需求 5.1）；
- 与上一发布批次相比 addr_id 不可变（接 `check_addr_id_immutable`：未 deprecated 即移除、不可变字段改值，均阻断）；
- schema（需求 3.4）；
- 别名处置的 blocking 组为 0（需求 6）。

4.2 输出幂等：输入不变时重跑，目录、报告、快照逐字节不变（`registry_version` 与报告时间戳沿用）；只有内容变化才产生新的 `registry_version`。核查：连续两次生成的 sha256 相同。

4.3 提供 `--check`：比对已提交产物与重算结果，有漂移时非零退出，并点名差异条目（addr_id 加字段）。CI 用 `--check`，不用「`--write` 后 `git diff`」；`check_catalog_drift.py` 与之合并，或调用同一实现，只保留一份判据。

4.4 迁回外科补丁：F4 的 57 张 sheet 差异逐条迁入生成器权威输入（全量登记循环的 manifest；带 owner、理由与可复算来源的 overrides；标签源），x3 部分登记 manifest 与其未覆盖基线不动。迁移后重算的目录与迁移前已提交的目录在 53 张 import_export 上逐字段相等，4 张别名 sheet 的别名是已提交值的超集（旧别名沿用）；x3 相关守卫全绿；`fix_acnr_dangling_api_prefix`、`fix_acnr_catalog_ie_gap`、`fix_x3_adjustment_ie_registration`、`gen_cycle_import_export_registry` 的 `--check` 仍为 0。直接改写 `global_catalog.json` 的脚本改为写生成器输入或下线，由设计逐个裁定。

4.5 发布批次：目录、报告、快照同批写出，带同一个 `registry_version` 与目录内容 sha256，报告记录目录哈希；CI 与加载期互校，不一致即失败。同一 `registry_version` 只能对应一份内容：已存在同名快照且内容不同时失败，不跳过、不覆盖。F5 的存量那一对登记为一次性例外，例外条目写明版本与两份内容哈希，不匹配即失效。4 份既有快照逐字节不变（sha256 前缀依次为 3ab8a81e6a322da6、4085ddfcd12bd8ef、af590468c529ad74、ee0032ffcab40663）。

4.6 分片要么纳入同批互校，要么不再产出并移除过期文件，由设计裁定；不得留下版本或内容与目录不一致的分片。

4.7 `CatalogIndex` 加载时遇到重复 addr_id（sheets 内、cells 内或互撞）即 fail-closed，抛出点名重复项的错误；新目录与 4 份既有快照都能加载（历史快照中的孤儿不影响加载）。核查：合成重复数据的单测，加真实目录与快照的加载测试。

4.8 变异（磁盘级，针对生成器输入或产物副本）：注入重复 addr_id、删除父 sheet、改 cell 的 A1、删除已发布的 addr_id、改 parent_wp_code → 门禁各自红，且红在对应的检查上；绕过生成器直接改 `global_catalog.json` → `--check` 红。

### 需求 5　选得到就保存得了：名称体系与往返（ACNR-P1-01 延伸 · D4）

作为审计助理，我在公式选址器里选中任一底稿单元格后保存公式，希望一定能通过；按底稿列表里看到的名字写公式，也能被识别。

5.1 目录中每个非 deprecated cell 自带的 addr_id、formula_ref、uri 与 `cell:{sheet_code}!{A1}`，经 `full_resolve` 都回到自身 addr_id（现算 formula_ref 与 uri 只有 30/474 能往返）；每个 sheet 的 addr_id 与 `sheet:{sheet_code}` 也回到自身。核查：`test_catalog_roundtrip_real.py` 逐条遍历真实目录，禁止 mock 目录。

5.2 公式选址器插入的引用，在真实项目上下文中全部通过公式保存时的引用校验：真 PG 只读用例遍历目录全部 cell 的插入写法，拒绝数为 0。核查：`test_picker_refs_pass_save_validation_pg.py`。变异：把一个循环的目录 formula_ref 退回平台索引名写法 → 本用例红。

5.3 平台底稿索引名可以作为 sheet 名被识别（作为别名或等价写法，由设计裁定）：以现目录中 372 条平台索引名写法为固定夹具，发布后全部可解析。同名多码（现算 15 组，如「函证结果汇总」对应 D0-1、E0-1、F0-1、K0-1、L0-1）按需求 6.2 的歧义规则处理，不得任选其一。

5.4 已能解析的写法不得因本 spec 变得不能解析：以发布前全量可解析写法（模板 sheet 名、sheet_code、既有别名）为基线，发布后逐条仍解析到同一 addr_id。唯一例外是同父同名组（旧解析器任选其一）：名称中含某成员完整编码且最长唯一的，改判到该名称所属的 sheet；仍多义的改为返回歧义与候选。例外逐条写进基线夹具，静态数据中的真实写法（现算 26 处）必须解析到名称所属的 sheet，有真实使用的写法不得变为歧义。

5.5 种子名与模板名、平台索引名都不一致的 13 张 sheet（47 个 cell），逐格核实：坐标在该 sheet 模板已用范围内的保留地址、引用改用规范名，种子语义与模板行文字不符者显示名不带该语义并标「语义待核对」、登记豁免；坐标超出模板已用范围的做 deprecated，`replaced_by` 为父 sheet；挂错 sheet 的按需求 2 的口径做 deprecated 并用 `replaced_by` 迁到正确的 sheet（受不可变规则约束，不得直接改 addr_id）。种子名不作别名。核查：逐格判定记录带证据（行文字、模板范围、本格值），守卫现算比对。

### 需求 6　目录报告可追责，别名冲突逐条处置（ACNR-P1-03 · D4）

作为目录维护者，我希望报告里每个计数都能展开到具体条目和负责人，让缺口从长期警告变成可追责的清单。

6.1 报告指标分组：`blocking`（发布前必须为 0）、`acknowledged`（豁免，带 owner、理由、到期日）、`deprecated`（带迁移映射）、`info`。每组计数等于该组条目列表的长度，不再出现「gap_count 非零而 gaps 为空」。核查：`test_catalog_report_buckets.py`。

6.2 一对多的别名冲突逐条归入以下三类，并按类解析：

- 可消歧（给出父底稿即唯一）：保留为父级限定别名；带父级时命中，缺父级时返回歧义、候选与所需上下文；
- 禁止（父级内仍多义或指向错误）：移除；解析时返回未找到，并给出原因；
- 需项目上下文：没有项目时返回歧义，并说明需要项目。

现算冲突 4 条（已提交报告记为 5 条，差异来自标签改名）逐条处置，无遗漏。

6.3 未登记别名（现算 28 条，标签源中有、目录里没有对应 sheet_code，如 D4A、D5-目录、参考中证协）逐条处置：并入既有 sheet 作为别名；或标为「非地址标签」排除并写明理由；或按需求 2 补 sheet。未处置的条目计入 blocking。

6.4 豁免清单可伪证：每条都有 owner、理由、到期日，以及覆盖的别名与 sheet_code。条目过期即门禁失败；所指冲突已不存在也门禁失败（清单不得有失效条目）。变异：把一条的到期日改到过去、删除一条豁免所指冲突的来源 → 各自红。

6.5 报告与目录同批写出（需求 4.5），并记录目录内容哈希与生成器输入指纹。

### 需求 7　归档项目按归档时的目录解析（ACNR-P1-02 · D5）

作为签字合伙人，我希望项目归档后，即使平台目录升级、服务重启，归档项目里的地址仍按归档时的目录解析；取消归档后再跟随最新目录。

7.1 用运行时迁移为项目持久记录锁定的 `registry_version`（加列还是建专表，由设计裁定；V / R 脚本配对，使用 `IF NOT EXISTS`；迁移号在实施时动态取）。迁移、ORM、服务三层一致。存量项目该值为空，即未锁定，不回填、不伪造。

7.2 锁定与解锁以项目 `status` 为准（与平台只读判定、取消归档同口径）：把 `status` 置为 archived 的全部生产写入方（现算 1 个：交付件全部归档）在同一事务内记录锁定版本，取值为当时的目录版本；锁定写入失败时，状态变更整体不提交并报告原因。让项目离开 archived 的写入方（现算 1 个：取消归档）在同一事务内清除锁定；其他会改 `status` 的写入方须证明不会从 archived 出发（必要时加前置拒绝）。只写 `archived_at` 的归档作业不加锁。守卫（AST 赋值与原生 SQL 一并现扫）断言：写入点集合等于登记集合，锁定项目集合 ⊆ 有解锁路径的集合，新增写状态的位置没有接线即红。

7.3 resolver 以持久记录作为锁定版本的真源，进程内 dict 至多作缓存。锁定版本与当前版本不同时，按该版本的快照解析。快照缺失时 fail-closed：`/api/acnr/*` 与查询入口返回非 5xx 的明确业务错误（前端拦截器会对 5xx 自动重发两次），附中文原因，如「项目锁定的地址目录版本 {版本} 快照缺失」；不得静默回退到当前目录。

7.4 快照清理（DB-aware 作业）只删除未被任何项目锁定、且不在最近 N 份之内的快照；生成器的离线清理保持「引用不可验证即不删」。核查：真 PG 用例，锁定的旧版本超出保留数时不删，未被引用的被删。

7.5 真 PG 端到端：在回滚事务内的【测试】项目上走真实归档路径 → 清空进程内缓存，模拟重启 → 把当前目录换成更新的版本（夹具中两个版本对同一写法的解析结果不同）→ 该项目仍按归档版本解析；取消归档后按当前版本解析。核查：`test_project_registry_lock_pg.py`。变异：删掉归档接线 → 红。

### 需求 8　异步追溯拿到规范 addr_id（ACNR-P1-04 · D6）

作为复核人员，我希望跨 sheet 追溯里看到的每个节点都是平台统一的地址，可以直接跳转。

8.1 当跨 sheet 追溯在运行中的事件循环里执行时（真实 async 请求链），每个可解析的节点都返回规范 addr_id 与 `resolved=true`；不可解析的节点返回 `resolved=false` 与中文原因。节点身份按「父底稿 + sheet（模板 sheet 名或编码）+ A1」解析，使用真实 sheet 名同样命中。核查：`test_cross_sheet_trace_async_e2e.py`，经 TestClient 调用 `GET /api/custom-query/cross-sheet-trace`，夹具 sheet 名用目录权威名（如「货币资金分析表E1-14」），不 mock `_sync_resolve` 与 resolver。

8.2 async 上下文中的追溯使用方（现算：路由编排器、底稿公式求值各 1 处）要么拿到真实 addr_id，要么显式声明只取值、不取身份；不得依赖「在运行中的事件循环里返回 None」的降级。若保留同步桥接的降级分支，须由守卫证明生产路径不可达。

8.3 追溯响应字段向后兼容（只增不改）；既有的 PBT 与契约测试全绿。

8.4 变异：把编排器的节点身份退回 `cell:{sheet 名}!{A1}` → 8.1 红；把 async 路由改回调用同步桥接取身份 → 8.2 的守卫红。

### 需求 9　V2 依赖图规范化（ACNR-P1-05 · D7）

作为联动与 stale 影响分析的使用者，我希望依赖图里的节点和平台地址是同一种身份，写 stale 时只按精确命中，这样改名、别名、版本变化都不会让影响分析悄悄失效。

9.1 V2 的 `/resolve`、`/anchors`、`/stale-impact`、`/dependencies` 响应中，每个节点与边端点都增加规范 `addr_id`（可经 `full_resolve` 回到同一物理格）或中文 `unresolved_reason`，二者恰有其一；旧字段保持不变（只增，保持只读兼容）。

9.2 包含匹配只作为候选：凡由包含匹配产生的结果都标为候选（不得标记为 `matched=true`，字段由设计给出），并且不出现在任何写路径的输入中。

9.3 写 stale 的路径只接受规范 addr_id，或经 ACNR 精确解析得到的 addr_id；解析不到时不写，并返回原因；不得用正则从显示名里猜 sheet_code 再拼 id。stale 图的键与入口的规范化使用同一个函数。

9.4 双读对账：遍历 V2 的全部静态数据（L2 语义锚点、resolved refs、L3 依赖、CCR），输出「旧字段 → addr_id 或 unresolved_reason」的对账表；规范 addr_id 的覆盖数与 unresolved 的分类计数写入报告，每一类都有原因。核查：`test_v2_canonical_reconcile.py`（使用真实数据文件）。

9.5 CCR 不可解析源（HEAD 检查器现算 57 个；检查器改用统一身份判定后按新口径重算，design §10.3）逐条处置：能修的修（含需求 5.3 覆盖的平台索引名写法）；修不了的登记原因、owner、到期日（规则同需求 6.4）。`check_ccr_resolve --blocking` 对登记清单之外的条目零容忍，CI 作业转绿。

9.6 变异：把一个精确命中改成只剩包含匹配 → 写路径用例证明没有写库；删除 addr_id 字段 → 9.1 红。

### 需求 10　写 stale 的端点有项目鉴权（ACNR-P2-02 · D8）

作为项目负责人，我希望其他项目的人无法给我的项目打 stale 标记。

10.1 先用 TestClient 复现，并把证据写入设计：修复前，非成员带他人的 project_id 调用 `POST /api/address-registry/v2/notify-cell-change` 会触发 stale 写入（spy 显示 `stale_engine.on_change` 被调用）。

10.2 带 project_id 且会写 stale 的端点，现算 3 个：V2 `notify-cell-change`、linkage-bus `POST /impact`、`GET /impact-by-addr`。要求如下：

- 未登录返回 401；
- 非成员返回 403，且 `on_change` 调用 0 次；
- 该项目的 edit 级成员（审计员、经理、合伙人）与 admin 放行，与真实调用方（底稿编辑器保存、公式管理）同级；
- review / readonly 级返回 403。

没有真实调用方、且已被替代的端点可以改为下线（返回 410，不触达数据），登记为桩豁免，并断言它确实是桩；前端路径常量同步删除。核查：`test_stale_write_endpoint_authz.py`，表驱动权限矩阵。

10.3 不以写死的年度兜底：缺 `year` 时按项目审计年度补齐，取不到返回 422；前端调用方不以日历年兜底。`test_audit_year_calendar_fallback_ratchet.py` 中 `routers/address_registry_v2.py` 与前端年度棘轮中相应调用方的基线随之下调。

10.4 V2 其余端点逐个排查，并在设计中登记结论；不带 project_id 的静态数据读端点维持「登录即可」。已修的端点从鉴权基线守卫（如 `test_project_endpoint_authz_body_carried.py`）中删除欠账条目、下调计数，不得回填。

10.5 会写库的 GET 端点（`/impact-by-addr`）须给出处置：改为 POST，或改为只读；调用方同步修改。

10.6 变异：逐个摘掉新加的鉴权依赖 → 对应的 403 用例红；鉴权判定用 AST，docstring 里写了鉴权不算数。

### 需求 11　前端失效订阅与多项目缓存隔离（ACNR-P2-01 · D9 · 审计报告 §9 P2 多项目 SSE / 缓存验收）

作为同时处理多个项目的审计人员，我希望在一个项目里改了底稿或地址补丁后，这个项目的选址和解析立即刷新，另一个项目不受影响。

11.1 生产代码中处于项目上下文的 `useAcnr()` 调用都带当前项目订阅失效（现算无参 28 处、27 个文件，逐处分类）。确实没有项目上下文的调用（如全局模板库）登记为「目录级、仅 TTL」，并写明理由。守卫（语法树级）现算的无参调用集合必须等于登记集合，新增未登记的无参调用即红。

11.2 项目切换：同一组件或 store 实例从项目 A 切到 B 后，取消 A 的订阅、建立 B 的订阅；同一项目的多处调用共享一个总线订阅（引用计数），不重复订阅；卸载后订阅数归零。核查：vitest 计数订阅与取消。

11.3 失效隔离：A 收到 `acnr:invalidate` 时只清 A 的解析缓存，B 的缓存仍然命中；只有目录版本变化才清目录级缓存。核查：vitest。

11.4 地址 store 在 `refresh(projectId)` 切换绑定项目时同步切换订阅（store 没有组件实例，不得依赖 `onUnmounted`）。

11.5 多项目浏览器验收（chrome-devtools，两个【测试】项目，两个标签页）：在 A 保存底稿或修改 overlay 后，A 的选址或解析结果在 SSE 事件到达后刷新，B 不变；断开 SSE 再重连后清除 A 的缓存；降级为仅 TTL 时 300 秒内收敛。截图存 `screenshots/`。多 worker + Redis pub/sub 场景需要相应环境，不具备时如实标为 `[ ]*`「代码已改但未实测」。

11.6 变异：去掉某处调用的项目参数 → 11.1 的守卫红；把按项目清缓存改成全部清空 → 11.3 红。

### 需求 12　统一显示与可解释的错误（D10 · 审计报告 §9 P2 统一地址工作台）

作为使用公式、查询和导航的审计人员，我希望同一个地址在各处叫同一个名字、写成同一个引用；解析不到时知道原因，也知道下一步该做什么。

12.1 同一 addr_id 在公式选址器、高级查询的地址树与结果区、导航 chip 中，显示同一个中文名与同一个规范引用（formula_ref 加 addr_id）。显示名的组成规则只在一处定义（以现行前端口径为基线，下沉为后端单一函数并由生成器写入目录 `display_label`），导入守卫证明三处都从它取值、不自行拼接；后端需求 1 的 `display_label` 与前端对同一夹具的显示逐字相等（跨语言契约测试共享夹具）。

12.2 歧义：resolver 返回 `ambiguous` 时附带候选（最多 5 个，含中文名）、中文 `reason` 与所需上下文（父底稿编码或项目）。三处界面都展示候选与所需上下文；选中候选后得到唯一结果。

12.3 外部命名空间（grammar_v1 中 `external_module=true`，现算 6 个）：解析结果为 `found=false`、`error=external_module_not_resolved`，中文 `reason` 为「「{名称}」类引用暂不支持定位到物理地址」，并附下一步提示（打开对应模块）。chip 显示该原因，而不是只显示「跳转 → ns:target」。核查：后端用例按 grammar 遍历全部外部命名空间（新增命名空间没配文案即红），另加 vitest。

12.4 用户可见文案全部为中文（addr_id、URI、API 等技术术语保留），不直接显示后端的英文错误码。

12.5 变异：某组件改回自行拼接显示名 → 12.1 的守卫红；删掉一个命名空间的文案 → 12.3 红。

### 需求 13　消费方台账、绕过棘轮与门禁转绿（D11 · 审计报告 §9 P1 消费方迁移台账）

作为平台架构负责人，我希望知道每个模块是否已经走统一寻址；新代码不能再绕过；现有门禁不再长期红着。

13.1 台账逐项列出寻址消费方（公式选址与保存校验、高级查询、导航、追溯、报告、附注、合并、同步、导入导出、AI 对话提及），以及各自的状态（已迁移、legacy 回退、未接入）与迁移目标。台账机器可读，守卫校验每条所指的文件与符号真实存在。

13.2 绕过点由设计精确定义，例如：后端直接调用 V1 地址服务做底稿域寻址、读 V2 静态 JSON 做身份判定、前端直调 legacy 地址端点或旧导航解析。识别用 AST 或语法树，注释与文档字符串不计。现有绕过点冻结为基线，只许减少；新增即红；基线所指的调用已不存在也红（清单不得有失效条目）；基线不得虚高。

13.3 现有的 `check_acnr_consumer_coverage --strict`（HEAD 即红）由新守卫取代，或改为调用同一实现；CI 作业转绿。台账删除「纯注释引用」条目。

13.4 变异：在临时副本中注入一处新的绕过 → 红；只在注释里提到 legacy 函数 → 不红；删掉一个基线所指的调用 → 报「失效条目」并红。

13.5 F18 中 HEAD 即红的 4 个作业，交付后都是确定的绿：drift 与 ie-catalog-sync 按需求 4 真实修复，ccr-resolve-blocking 按需求 9.5，consumer-coverage 按 13.3。不得用 continue-on-error 或补豁免来蒙绿。

### 需求 14　文档与勘误（D12）

14.1 在 `docs/proposals/address-coordinate-name-registry-architecture.md` 中新增「现状（2026-10-26）」一节，写明：已落地的组件、目录规模、版本格式（时间戳）、L1 只覆盖底稿域、V1 / V2 / legacy 的并行关系、本 spec 完成后的门禁清单。定位写为「canonical resolver + legacy 委托」，不称全平台唯一入口。原有内容不改写，过时的陈述在新节中逐条指出。

14.2 本 spec 的 design 设「勘误」节，承接审计报告 §11 与上一轮公式管理评估中需要勘误的结论：高级查询只复用了地址树；ACNR 不是唯一入口；157 个定向测试没有覆盖真实产物与端到端链路；只能称「resolver 支持版本锁定」。同时补入本轮的新发现。不修改历史报告原文：本 spec 的提交不含 `.agents/tasks/` 下的任何文件。核查：现算 `git diff --name-only`。

14.3 在 `.kiro/specs/INDEX.md` 登记本 spec（CRLF 与竖线规则见 0.9）。

14.4 文档一致性守卫读取架构提案与生成器常量，断言「现状（2026-10-26）」节存在，且其中写明的版本格式与生成器、schema 一致（承接需求 3.2）。变异：把该节的版本格式改回 `YYYY.N.N`，或删掉该节 → 守卫红。

## 4. 非功能需求

- 安全：本 spec 新增或修改的带 project_id 端点都有 401、403、放行三类的角色矩阵测试；放行一侧测真实角色，不只测 401。错误信息不泄露其他项目的数据。新增依赖钉精确版本。
- 兼容：响应字段只增不改；V1、V2 不删除；不带 acnr_targets 的旧请求、两参 WP 公式的行为不变。
- 确定性：生成产物逐字节可复现；CI 判据不含时间戳、随机数、绝对路径或机器名。
- 性能：目录加载（含重复检测）耗时不超过现状的 120%（基线在设计中实测记录）；生成器全量门禁在 CI 内不超过 2 分钟；acnr_targets 单次请求的目标数上限同 1.4。
- 可观测：版本锁命中、锁定快照缺失、acnr_targets 各类拒绝，计入现有 ACNR 指标（`/api/acnr/metrics`）。

## 5. 范围外（只在 design「待拍板」登记建议）

- 删除 V1 / V2；改 addr_id 格式；把报告、附注、合并纳入 L1 静态目录；放开 sheet_code 全局唯一；外部命名空间的真实物理定位。
- acnr_targets 扩展到试算表、报表、附注取值（各自的唯一读取实现已存在，另立需求）。
- 让目录 sheet 集合补齐平台底稿编码（F20：平台独有 172 个）。本 spec 只处理孤儿的父 sheet、K14~K18，以及 13 张种子挂错疑点。
- 种子坐标与模板册逐格核对的系统工程（本轮粗测只示量级，见 out/p06）。
- overlay CAS 两写者、回滚后缓存不脏的真 PG 验收（审计报告 §10.3，不属于本 spec 的问题编号）。
- 高级查询的其余缺陷（模板 scope、业务视图双计、报表快照为空、调整分录枚举等），归 advanced-query-linkage-closure。
- 两参 WP 缺数返回 0 的全局口径（本 spec 只在 acnr_targets 调用方区分缺数），归 formula-hub-integrity-closure。
- 多 worker + Redis pub/sub 的实机验收（待环境）。

## 6. 假设

- A1：本机 PG `audit_platform` 可用，能在回滚事务内建【测试】项目；本文件中的 PG 数字以动手时现查为准。
- A2（设计阶段现查后修订）：生成器的 classification 权威输入是已提交的离线缓存（含 sheet 级拆分记录与 functional_type 推断）；本地库表与缓存是两个模板版本、缺 771 个拆分编码，不作权威，只用于核对。差异逐类处置并由 `pg_only` 守卫现算（design §1.3）。
- A3：并发会话可能在实施期间提交同一区域的改动；每批动手前以 HEAD 重算本文件的数字，变化记入 tasks。
- A4：「真实项目在用」以未删除的 wp_index 行计；外部系统的引用不在判定范围内。
- A5：需求 10 的放行级别按 `assignment_service.ROLE_MAP` 的现行映射：合伙人、经理、审计员为 edit；质控、EQCR 为 review。

## 7. 问题编号覆盖

| 编号 | 需求 |
|---|---|
| ACNR-P0-01 | 1 |
| ACNR-P0-02 | 2 |
| ACNR-P0-03 | 3 |
| ACNR-P1-01 | 4、5 |
| ACNR-P1-02 | 7 |
| ACNR-P1-03 | 6 |
| ACNR-P1-04 | 8 |
| ACNR-P1-05 | 9 |
| ACNR-P2-01 | 11 |
| ACNR-P2-02 | 10 |
| D1 / D2 / D3 | 1 / 2 / 3 |
| D4 | 4、5、6 |
| D5 / D6 / D7 / D8 | 7 / 8 / 9 / 10 |
| D9（含多项目 SSE / 缓存验收） | 11（11.5） |
| D10 / D11 / D12 | 12 / 13 / 14 |
| 审计报告 §9 任务包 | P0：1、2、3、4、6；P1：7、8、9、13；P2：12、11.5、12.3 |
| 审计报告 §10 门禁 | schema 校验真实产物 3.4；重复、孤儿、往返 4.1 与 5.1；真实目录 full_resolve 5.1；别名白名单 6.4；磁盘变异见各需求末条；高级查询 TestClient 1.1；真实 async 8.1；401 / 403 矩阵 10.2 与 §4 |
| 审计报告 §11 勘误 | 14.2 |
| 本轮新发现（§1 标【新】） | F4 → 4.3、4.4；F5 → 4.5、2.1；F7 → 4.6；F8、F9 → 5；F11 → 1.1、1.7；F12 → 1.2；F13 → 7.2、7.3；F14 → 8；F15 → 9.3、10；F16 → 11.1；F18 → 13.5；F20 → §5 |
